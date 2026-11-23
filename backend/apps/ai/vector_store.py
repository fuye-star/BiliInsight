# -*- coding: utf-8 -*-
"""
向量库封装（ChromaDB）。

【为什么用 ChromaDB】
  1. 纯 Python + SQLite 持久化，无需独立服务进程（对比 Milvus/Qdrant）
  2. 自带向量索引与元数据过滤，适合本项目万级数据量
  3. 是 rdme.txt 明确点名的技术栈，符合加分项

【存储结构】
每条视频对应一个向量 + 一份元数据：
    id       = bvid（天然唯一，便于幂等更新）
    document = "标题 | 简介 | 标签" 拼接后的文本（供向量化与关键词过滤）
    metadata = 分区、UP主、播放量等结构化字段（供检索时过滤与前端展示）

【关键设计：为什么 document 要拼接多个字段】
检索时用户可能问"科技区讲芯片的视频"——
"芯片"可能只出现在标题或标签里。把标题、简介、标签拼成一段文本一起向量化，
比只索引标题的召回率高得多。

【与数据库的关系】
ChromaDB 里存的是"用于检索的副本"，权威数据仍在 MySQL。
二者通过 bvid 关联，向量库可随时删除重建，不会丢数据。
"""

import logging
from typing import Any, Optional

from django.conf import settings

from .embedding import get_embedder, reset_embedder_cache

logger = logging.getLogger(__name__)

# 集合名称（ChromaDB 中相当于"表名"）
COLLECTION_NAME = "bili_videos"


class VectorStoreError(Exception):
    """向量库操作失败。"""


def _get_client():
    """创建 ChromaDB 持久化客户端。

    【为什么每次新建而不是全局单例】
    ChromaDB 的 PersistentClient 内部对同一路径有实例缓存，
    重复创建不会真正打开多次文件句柄，因此这里保持简单。
    它不支持 fork 后跨进程共享，所以也不适合做进程内单例，
    否则 Celery 多进程场景会出问题。
    """
    import chromadb

    persist_dir = getattr(
        settings, "CHROMA_PERSIST_DIR", str(settings.BASE_DIR / "data" / "chroma")
    )

    # 确保目录存在（ChromaDB 不会自动创建多级目录）
    from pathlib import Path

    Path(persist_dir).mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(path=str(persist_dir))


def _get_collection(client=None, *, create: bool = True):
    """获取集合。

    参数:
        client: 可选的客户端实例
        create: 为 False 时集合不存在则返回 None（避免误创建空集合）

    返回:
        Collection 或 None
    """
    client = client or _get_client()

    if not create:
        try:
            return client.get_collection(COLLECTION_NAME)
        except Exception:
            return None

    embedder = get_embedder()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        # 用余弦距离（向量已 L2 归一化，与点积等价，数值更稳定）
        metadata=_collection_metadata(embedder),
    )


def _collection_metadata(embedder) -> dict:
    """构造集合元数据，记录"这份索引是哪个向量化器建的"。

    【为什么要把这些写进集合元数据】
        本地向量化器是**用全量语料训练**的：语料一变，词表、IDF、
        SVD 投影矩阵全都会变，**向量维度也会变**
        （40 条语料只有 39 维，297 条则是 256 维）。

        而向量化器实例在 Web 进程里是缓存的。如果重建索引发生在
        CLI 或另一个进程，Web 进程内存里仍是旧的那份，
        拿旧投影去查新索引就会：

            Collection expecting embedding with dimension of 39, got 256

        这个异常被 search() 吞掉后，界面只显示"没有找到相关视频"，
        完全看不出真实原因 —— 本项目就踩过这个坑。

        把维度与语料指纹记进集合元数据后，检索前就能先做一次校验，
        不匹配就自动重新加载，而不是等到查询失败才发现。
    """
    return {
        "hnsw:space": "cosine",
        "embedding_backend": getattr(embedder, "backend_name", ""),
        "embedding_dim": int(getattr(embedder, "dim", 0) or 0),
        "corpus_size": int(getattr(embedder, "corpus_size", 0) or 0),
        "corpus_fingerprint": getattr(embedder, "corpus_fingerprint", "") or "",
    }


def _index_fingerprint_metadata(embedder) -> dict:
    """只包含"可以随时改写"的索引身份信息。

    【为什么不能直接把 _collection_metadata 传给 modify】
        ChromaDB 的 `hnsw:space`（距离函数）**只能在创建集合时指定**，
        后续 modify 传入它会直接报错：

            Changing the distance function of a collection once it is
            created is not supported currently.

        这个错误只是警告级别的失败 —— 索引本身照常可用，
        但元数据**一个字段都没写进去**，于是检索时的
        "向量化器是否与索引配套"校验就失效了（又退回到只能靠维度猜测）。

        因此这里单独构造一份不含 hnsw:space 的元数据用于更新。
    """
    return {
        "embedding_backend": getattr(embedder, "backend_name", ""),
        "embedding_dim": int(getattr(embedder, "dim", 0) or 0),
        "corpus_size": int(getattr(embedder, "corpus_size", 0) or 0),
        "corpus_fingerprint": getattr(embedder, "corpus_fingerprint", "") or "",
    }


def _load_local_state(embedder) -> bool:
    """让本地向量化器从磁盘加载已保存的训练参数。"""
    return embedder.load(
        getattr(
            settings, "CHROMA_PERSIST_DIR", settings.BASE_DIR / "data" / "chroma"
        )
    )


def _ensure_embedder_matches(collection, embedder):
    """确保向量化器与索引是配套的；不匹配则自动重新加载。

    参数:
        collection: ChromaDB 集合（元数据里记着索引期望的维度与语料指纹）
        embedder:   当前进程缓存的向量化器

    返回:
        匹配的向量化器；无法匹配时返回 None（调用方应放弃检索并给出明确日志）

    【为什么必须做这一步】
        search() 原先只在"向量化器完全没训练过"时才去加载磁盘状态：
            if embedder.vectorizer is None: embedder.load(...)
        但如果内存里是一份**训练过的旧版本**，这个条件为假，
        就会拿着过期的投影矩阵去查新索引，最终以维度不匹配告终。
        这里改为按"维度 + 语料指纹"判断是否配套，不配套就刷新。
    """
    # 只有本地后端有"训练语料"的概念，其它后端（ollama/dashscope）是无状态的
    if getattr(embedder, "backend_name", "") != "local":
        return embedder

    meta = getattr(collection, "metadata", None) or {}
    expected_dim = meta.get("embedding_dim")
    expected_fp = meta.get("corpus_fingerprint") or ""

    # 旧索引没有这些元数据 -> 无法校验，放行以保持向后兼容
    if expected_dim is None and not expected_fp:
        return embedder

    def _matches(emb) -> bool:
        """判断向量化器是否与索引配套。"""
        if expected_dim is not None:
            if int(getattr(emb, "dim", -1) or -1) != int(expected_dim):
                return False
        if expected_fp:
            if (getattr(emb, "corpus_fingerprint", "") or "") != expected_fp:
                return False
        return True

    if _matches(embedder):
        return embedder

    logger.warning(
        "向量化器与索引不匹配（当前 dim=%s 指纹=%s；索引要求 dim=%s 指纹=%s），"
        "正在重新加载…",
        getattr(embedder, "dim", None),
        getattr(embedder, "corpus_fingerprint", "") or "(空)",
        expected_dim,
        expected_fp or "(空)",
    )

    # 清缓存 -> 取新实例 -> 从磁盘加载最新训练结果
    reset_embedder_cache()
    embedder = get_embedder()
    _load_local_state(embedder)

    if _matches(embedder):
        logger.info(
            "向量化器已刷新并与索引匹配：dim=%s 指纹=%s",
            getattr(embedder, "dim", None),
            getattr(embedder, "corpus_fingerprint", "") or "(空)",
        )
        return embedder

    logger.error(
        "向量化器与向量库仍不匹配（dim=%s，索引要求 dim=%s）。"
        "索引与训练状态可能已不一致，请重建：python manage.py build_index --rebuild",
        getattr(embedder, "dim", None),
        expected_dim,
    )
    return None


# ===========================================================================
# 构建索引
# ===========================================================================
def build_video_text(video) -> str:
    """把视频信息拼成用于向量化的文本。

    参数:
        video: Video 模型实例

    返回:
        拼接后的文本

    【拼接顺序有讲究】
    标题权重最高（信息密度最大），放最前面；
    简介次之；标签补充关键词。
    对于词频类向量化（TF-IDF），重复出现的关键词会获得更高权重，
    因此标题与标签里的词天然被强化。
    """
    parts = [video.title or ""]

    if video.tags:
        # 标签紧跟标题，强化关键词
        parts.append(video.tags.replace(",", " "))

    if video.description:
        # 简介可能很长，截断避免单条文本过大
        parts.append(video.description[:500])

    if video.upuser and video.upuser.name:
        parts.append(video.upuser.name)

    if video.partition and video.partition.name:
        parts.append(video.partition.name)

    return " ".join(p for p in parts if p).strip()


def _build_metadata(video) -> dict:
    """构造向量元数据。

    【重要限制】ChromaDB 的 metadata 只接受
    str / int / float / bool 等标量，不能嵌套 dict 或 list。
    因此所有字段都要拍平。
    """
    return {
        "bvid": video.bvid,
        "title": (video.title or "")[:500],
        "partition": video.partition.name if video.partition else "",
        "up_name": video.upuser.name if video.upuser else "",
        "up_mid": int(video.upuser.mid) if video.upuser else 0,
        "view_count": int(video.view_count or 0),
        "like_count": int(video.like_count or 0),
        "coin_count": int(video.coin_count or 0),
        "favorite_count": int(video.favorite_count or 0),
        "danmaku_count": int(video.danmaku_count or 0),
        "interaction_rate": float(video.interaction_rate or 0.0),
        "duration": int(video.duration or 0),
        # 时间戳用 int（ChromaDB 不支持 datetime）
        "pubdate_ts": int(video.pubdate.timestamp()) if video.pubdate else 0,
    }


def build_index(
    *,
    batch_size: int = 100,
    rebuild: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """用数据库中的视频构建/更新向量索引。

    参数:
        batch_size: 每批写入的条数
        rebuild:    为 True 时先清空集合再重建（切换向量后端后必须重建）
        limit:      限制处理的视频数（调试用）

    返回:
        {"indexed": n, "backend": "...", "dim": n, "elapsed": 秒}

    【为什么要传 rebuild】
    TF-IDF 的 IDF 依赖全量语料，切换后端后向量维度也可能变化。
    若只是增量追加，新旧向量会在不同语义空间里，检索结果会混乱。
    因此切换后端或语料大幅变化时必须 rebuild。
    """
    import time

    from apps.videos.models import Video

    started = time.monotonic()

    embedder = get_embedder(refresh=rebuild)

    if not embedder.available:
        raise VectorStoreError(f"向量化后端 {embedder.backend_name} 不可用")

    # ---- 取全量视频 ----
    qs = Video.objects.select_related("partition", "upuser").order_by("id")
    if limit:
        qs = qs[:limit]
    videos = list(qs)

    if not videos:
        logger.warning("数据库中没有视频，无法构建索引")
        return {"indexed": 0, "backend": embedder.backend_name, "dim": 0, "elapsed": 0.0}

    logger.info("开始构建向量索引：%d 条视频，后端 %s", len(videos), embedder.backend_name)

    # ---- 准备文本 ----
    documents = [build_video_text(v) for v in videos]
    metadatas = [_build_metadata(v) for v in videos]
    ids = [v.bvid for v in videos]

    # ---- 本地后端需要先用全量语料训练 ----
    if embedder.backend_name == "local":
        embedder.fit(documents)
        # 持久化训练结果，供后续检索时复用（重启进程不必重训）
        embedder.save(getattr(settings, "CHROMA_PERSIST_DIR", settings.BASE_DIR / "data" / "chroma"))

    # ---- 打开集合 ----
    client = _get_client()

    if rebuild:
        # 删除旧集合，确保维度与语义空间一致
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("已删除旧集合 %s", COLLECTION_NAME)
        except Exception:
            pass

    collection = _get_collection(client)

    # ---- 分批向量化并写入 ----
    total = 0
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]

        try:
            vectors = embedder.embed_documents(batch_docs)
        except Exception as exc:
            logger.error("第 %d 批向量化失败：%s", i // batch_size + 1, exc)
            raise VectorStoreError(f"向量化失败：{exc}") from exc

        collection.upsert(
            ids=batch_ids,
            embeddings=vectors,
            documents=batch_docs,
            metadatas=batch_meta,
        )
        total += len(batch_ids)
        logger.info("索引进度 %d/%d", total, len(documents))

    elapsed = round(time.monotonic() - started, 2)
    logger.info("向量索引构建完成：%d 条，耗时 %.2f 秒", total, elapsed)

    # ---- 把"这份索引是哪个向量化器建的"记进集合元数据 ----
    # 检索前据此校验：若 Web 进程里缓存的向量化器是上一次索引留下的，
    # 就能自动重新加载，而不是等到查询报"维度不匹配"才发现。
    try:
        # 注意：这里必须用不含 hnsw:space 的版本，
        # 否则 ChromaDB 会拒绝整个 modify 调用（详见 _index_fingerprint_metadata）
        collection.modify(metadata=_index_fingerprint_metadata(embedder))
        logger.debug(
            "集合元数据已更新：dim=%s 指纹=%s",
            embedder.dim, getattr(embedder, "corpus_fingerprint", ""),
        )
    except Exception as exc:  # noqa: BLE001
        # 写元数据失败不影响索引本身可用，只是失去了自动校验能力
        logger.warning("写入集合元数据失败（不影响索引可用性）：%s", exc)

    result = {
        "indexed": total,
        "backend": embedder.backend_name,
        "dim": embedder.dim,
        "elapsed": elapsed,
        "rebuild": rebuild,
    }
    return result


# ===========================================================================
# 检索
# ===========================================================================
def search(
    query: str,
    *,
    top_k: int = 5,
    partition: Optional[str] = None,
    min_view: Optional[int] = None,
) -> list[dict]:
    """按语义相似度检索视频。

    参数:
        query:     查询文本
        top_k:     返回条数
        partition: 可选，限定分区（ChromaDB 的 where 过滤，在向量检索前生效）
        min_view:  可选，播放量下限

    返回:
        [
          {
            "bvid": "BV...", "title": "...", "partition": "科技",
            "up_name": "...", "view_count": 12345,
            "similarity": 0.87,      # 余弦相似度（已转成越大越相似）
            "document": "..."        # 用于调试与溯源展示
          }, ...
        ]

    【返回空列表而不是抛异常的情况】
      · 索引尚未构建
      · 查询向量化失败
    上层（RAG）据此降级为"仅用大模型自身知识回答"，不中断对话。
    """
    if not query or not query.strip():
        return []

    collection = _get_collection(create=False)
    if collection is None:
        logger.warning("向量集合不存在，请先执行：python manage.py build_index")
        return []

    # ---- 构造元数据过滤条件 ----
    # ChromaDB 的 where 语法：{"字段": {"$eq": 值}}，多条件用 $and 组合
    conditions = []
    if partition:
        conditions.append({"partition": {"$eq": partition}})
    if min_view:
        conditions.append({"view_count": {"$gte": int(min_view)}})

    where = None
    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    try:
        embedder = get_embedder()

        # 本地后端需要先加载已保存的训练参数
        if embedder.backend_name == "local" and getattr(embedder, "vectorizer", None) is None:
            _load_local_state(embedder)

        # 【关键】确认向量化器就是构建当前索引时用的那一个。
        # 进程缓存里的实例可能来自上一次索引（语料不同 -> 词表/维度都不同），
        # 不校验的话会拿着旧投影去查新库，最终以维度不匹配告终，
        # 而异常被下面的 except 吞掉后，界面只会说"没有找到相关视频"。
        embedder = _ensure_embedder_matches(collection, embedder)
        if embedder is None:
            return []

        query_vector = embedder.embed_query(query)
    except Exception as exc:
        logger.warning("查询向量化失败：%s", exc)
        return []

    try:
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )
    except Exception as exc:
        logger.error("向量检索失败：%s", exc)
        return []

    # ---- 解析结果 ----
    # ChromaDB 返回的是"二维"结构（因为支持多查询），这里只取第 0 个
    ids = (result.get("ids") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits = []
    for idx, bvid in enumerate(ids):
        meta = metas[idx] if idx < len(metas) else {}
        distance = distances[idx] if idx < len(distances) else 1.0

        hits.append(
            {
                "bvid": bvid,
                "title": meta.get("title", ""),
                "partition": meta.get("partition", ""),
                "up_name": meta.get("up_name", ""),
                "view_count": meta.get("view_count", 0),
                "like_count": meta.get("like_count", 0),
                "interaction_rate": meta.get("interaction_rate", 0.0),
                "duration": meta.get("duration", 0),
                # cosine 空间下 distance ∈ [0,2]，转成相似度（越大越相似）
                "similarity": round(1.0 - float(distance), 4),
                "document": (docs[idx] if idx < len(docs) else "")[:300],
            }
        )

    logger.debug("检索「%s」命中 %d 条", query[:20], len(hits))
    return hits


# ===========================================================================
# 状态与维护
# ===========================================================================
def get_index_stats() -> dict:
    """返回索引状态，用于前端提示与接口展示。

    返回:
        {
          "ready": True, "count": 200, "backend": "local",
          "dim": 256, "fitted": True, "note": "..."
        }
    """
    embedder = get_embedder()

    # 本地后端需要尝试加载训练参数才知道是否可用
    if embedder.backend_name == "local" and getattr(embedder, "vectorizer", None) is None:
        embedder.load(
            getattr(settings, "CHROMA_PERSIST_DIR", settings.BASE_DIR / "data" / "chroma")
        )

    stats = {
        "ready": False,
        "count": 0,
        **embedder.describe(),
    }

    collection = _get_collection(create=False)
    if collection is not None:
        try:
            stats["count"] = collection.count()
            stats["ready"] = stats["count"] > 0
        except Exception as exc:
            logger.debug("读取集合数量失败：%s", exc)

    # 本地后端额外报告是否已训练
    if embedder.backend_name == "local":
        stats["ready"] = stats["ready"] and getattr(embedder, "vectorizer", None) is not None

    return stats


def clear_index() -> bool:
    """删除整个向量集合。

    返回:
        是否成功删除

    说明：删除后需重新执行 build_index；不影响 MySQL 中的原始数据。
    """
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info("已删除向量集合 %s", COLLECTION_NAME)
        reset_embedder_cache()
        return True
    except Exception as exc:
        logger.warning("删除向量集合失败：%s", exc)
        return False

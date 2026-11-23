# -*- coding: utf-8 -*-
"""
文本向量化模块 —— 可插拔设计。

【向量化的作用】
RAG（检索增强生成）的核心是"先检索、再生成"。
要让机器理解"最近科技区什么视频最火"这类问题，
必须把文本转成向量，才能按语义相似度检索。

【三种后端，逐级降级】
    ┌─────────────────────────────────────────────────────┐
    │ ollama    本地模型（bge-m3 等），语义最好、可离线    │  需 Ollama 服务
    │ dashscope 通义千问 embedding，效果好                 │  需 API Key + 外网
    │ local     TF-IDF + SVD 降维，纯本地、零依赖、确定性  │  开箱即用 ← 默认
    └─────────────────────────────────────────────────────┘

【为什么把 local 设为默认】
本项目在依赖问题上已经踩过两次坑（paddlenlp 装不上、Ollama 服务未运行）。
若把 RAG 强绑定到外部模型服务，答辩现场一旦服务没起来，AI 模块就整体失效。
local 后端用 scikit-learn 实现（它已是情感分析的依赖），
只需向量化一次并持久化到 ChromaDB，检索时零外部依赖。

【诚实的局限说明】
local 后端基于词频统计，属于**词法匹配**而非真正的语义理解：
  · 能匹配"芯片"↔"芯片"，但匹配不了"芯片"↔"半导体"
  · 对中文用字符 n-gram，因此对同义词、语序变化不敏感
因此它适合演示与开发；要真正的语义检索，应启用 ollama 或 dashscope。
README 与接口返回中都会如实说明当前用的是哪种后端。
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# 统一向量维度。
# 【为什么要固定维度】ChromaDB 的集合在创建时确定维度，
# 后续插入不同维度的向量会报错。固定维度后，切换后端只需重建索引。
EMBEDDING_DIM = 256


class EmbeddingError(Exception):
    """向量化失败。"""


# ===========================================================================
# 抽象接口
# ===========================================================================
class BaseEmbedder(ABC):
    """向量化器抽象基类。

    子类只需实现 embed_documents()，单条向量化由基类复用实现。
    """

    backend_name = "base"

    #: 该后端产出的向量维度
    dim = EMBEDDING_DIM

    def __init__(self):
        """初始化时探测依赖可用性，避免每次调用都判断。"""
        self.available = self._check_dependency()

    @abstractmethod
    def _check_dependency(self) -> bool:
        """检查依赖是否就绪。"""
        raise NotImplementedError

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一组文本转成向量。

        参数:
            texts: 文本列表

        返回:
            向量列表，与输入等长且顺序一致

        异常:
            EmbeddingError: 转换失败
        """
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        """把查询文本转成向量。

        默认与 embed_documents 走同一逻辑。
        某些模型对"文档"与"查询"使用不同的编码方式（如 bge 系列需要加指令前缀），
        子类可覆写此方法。
        """
        vectors = self.embed_documents([text])
        if not vectors:
            raise EmbeddingError("查询向量化失败")
        return vectors[0]

    def describe(self) -> dict:
        """返回后端描述，用于接口返回与前端提示。"""
        return {
            "backend": self.backend_name,
            "available": self.available,
            "dim": self.dim,
        }


# ===========================================================================
# 1. Ollama 本地模型（语义最好）
# ===========================================================================
class OllamaEmbedder(BaseEmbedder):
    """通过 Ollama 的 HTTP 接口调用本地嵌入模型。

    【为什么直接发 HTTP 而不装 ollama 包】
    官方 ollama Python 包只是 REST 接口的薄封装，
    而本项目已踩过"依赖装不上"的坑（见 README 排查表）。
    用 requests 直接调用 /api/embeddings 可减少一个依赖，
    且行为完全透明、易于调试。

    启用方式：
        1) 安装并启动 Ollama：https://ollama.com/download
        2) 拉取嵌入模型：ollama pull bge-m3
        3) .env 设置：EMBEDDING_BACKEND=ollama
    """

    backend_name = "ollama"

    #: Ollama 的嵌入模型通常输出 1024 维（bge-m3）或 768 维（nomic-embed-text）。
    #: 这里设为 None 表示"运行时从首次返回结果推断"，避免写死导致维度不匹配。
    dim = None

    # 单次请求的最大文本数（避免一次发太多导致超时）
    BATCH_SIZE = 16

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        """初始化。

        参数:
            model:    模型名；默认读 settings.EMBEDDING_MODEL
            base_url: Ollama 地址；默认读 settings.OLLAMA_BASE_URL
        """
        from django.conf import settings

        self.base_url = (base_url or getattr(
            settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        )).rstrip("/")
        # bge-small-zh-v1.5 是轻量中文嵌入模型，约 100MB，适合本地
        self.model = model or getattr(settings, "EMBEDDING_MODEL", "bge-m3")

        super().__init__()

    def _check_dependency(self) -> bool:
        """探测 Ollama 服务是否可用，并确认模型已拉取。"""
        import requests

        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]

            if not models:
                logger.warning("Ollama 已运行但没有任何模型，请执行：ollama pull %s", self.model)
                return False

            # 模型名可能带 ":latest" 后缀，做前缀匹配
            matched = any(
                m == self.model or m.startswith(f"{self.model}:") for m in models
            )
            if not matched:
                logger.warning(
                    "Ollama 中未找到模型 %s，可用：%s。请执行：ollama pull %s",
                    self.model, ", ".join(models), self.model,
                )
                return False

            logger.info("Ollama 嵌入后端就绪：%s @ %s", self.model, self.base_url)
            return True
        except Exception as exc:
            logger.debug("Ollama 不可用：%s", exc)
            return False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """调用 Ollama 逐个向量化。

        【为什么逐条而不是批量】
        Ollama 的 /api/embeddings 接口一次只接受一个 prompt。
        新版 /api/embed 支持批量，但版本差异较大，逐条调用更稳。
        索引只在 build_index 时跑一次，逐条的性能损失可接受
        （实测 200 条约 10-20 秒）。
        """
        import requests

        vectors: list[list[float]] = []
        for text in texts:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            resp.raise_for_status()
            vector = resp.json().get("embedding")
            if not vector:
                raise EmbeddingError(f"Ollama 未返回向量：{text[:30]}")

            # 首次调用时记录真实维度
            if self.dim is None:
                self.dim = len(vector)
            vectors.append(vector)

        return vectors


# ===========================================================================
# 2. 通义千问 Embedding（效果好，需 API Key）
# ===========================================================================
class DashScopeEmbedder(BaseEmbedder):
    """通过 DashScope 调用通义千问的文本向量模型。

    启用方式：
        1) 在 https://bailian.console.aliyun.com/ 获取 API Key
        2) .env 设置：
             EMBEDDING_BACKEND=dashscope
             DASHSCOPE_API_KEY=sk-xxxx

    模型说明：
        text-embedding-v3 输出 1024 维，支持中文优化，效果优于词频方案。
    """

    backend_name = "dashscope"
    dim = 1024

    def __init__(self, model: str = "text-embedding-v3"):
        """初始化。"""
        from django.conf import settings

        self.model = model
        self.api_key = getattr(settings, "DASHSCOPE_API_KEY", "")

        super().__init__()

    def _check_dependency(self) -> bool:
        """检查 SDK 与 API Key。"""
        if not self.api_key:
            logger.debug("未配置 DASHSCOPE_API_KEY，DashScope 向量化不可用")
            return False
        try:
            import dashscope  # noqa: F401

            return True
        except ImportError:
            logger.debug("dashscope SDK 未安装")
            return False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """调用 DashScope 批量向量化。

        DashScope 的单次批量上限为 25 条，这里自动分批。
        """
        import dashscope

        vectors: list[list[float]] = []
        batch_size = 25

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )

            if resp.status_code != 200:
                raise EmbeddingError(
                    f"DashScope 返回错误 {resp.status_code}：{resp.message}"
                )

            # 按 index 排序，确保顺序与输入一致
            embeddings = sorted(
                resp.output["embeddings"], key=lambda e: e["text_index"]
            )
            vectors.extend(e["embedding"] for e in embeddings)

        return vectors


# ===========================================================================
# 3. 本地 TF-IDF + SVD（默认，零依赖）
# ===========================================================================
def _fingerprint_texts(texts: list) -> str:
    """计算语料的指纹（用于判断向量化器是否与索引匹配）。

    【为什么需要这个】
        本地向量化器是**用全量语料训练**出来的：TF-IDF 的词表和 IDF、
        SVD 的投影矩阵都依赖当时那批文档。语料一变（比如重建索引时
        文档数从 297 变成 40），训练结果就完全不同。

        而向量化器实例在 Web 进程里是**缓存**的。若重建索引是在
        CLI 或另一个进程里做的，Web 进程内存里还是旧的那一份 ——
        拿旧投影去查新索引，结果就是：

            Collection expecting embedding with dimension of 39, got 256

        表现为"AI 助手检索不到任何内容"，而且因为异常被吞掉，
        界面上只会说"没有找到相关视频"，完全看不出真实原因。

        用指纹就能精确判断"内存里这份是不是当前索引配套的那一份"，
        不匹配就重新从磁盘加载。取前 16 位足够区分，且日志里好读。

    参数:
        texts: 训练语料

    返回:
        16 位十六进制指纹
    """
    import hashlib

    digest = hashlib.md5()
    for text in texts:
        digest.update(str(text).encode("utf-8"))
        # 加分隔符，避免 ["ab","c"] 与 ["a","bc"] 撞成同一个指纹
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


class LocalEmbedder(BaseEmbedder):
    """纯本地向量化：TF-IDF + 截断 SVD 降维。

    【原理】
      1. TF-IDF 把文本转成"词频-逆文档频率"稀疏向量
         —— 罕见词权重高，常见词权重低，能反映文本特征
      2. 截断 SVD 把高维稀疏向量压到固定维度的稠密向量
         —— 这本质上是 LSA（潜在语义分析），能捕捉部分共现关系
      3. L2 归一化后，余弦相似度就是点积，便于 ChromaDB 计算

    【中文处理】
    用字符 n-gram（char_wb, 1-2 元）而非按词切分：
      · 中文没有空格，按词切需要分词器（增加依赖）
      · 字符 bigram 对中文短文本效果尚可（"芯片"会被切成 芯片/芯/片）
      · 天然抗未登录词（新词也能用字符匹配）

    【为什么重要：它是"确定性"的】
    同一个语料库训练出的向量完全可复现，
    因此索引只需构建一次，之后检索无需任何外部服务。
    这保证了答辩现场 AI 模块一定能跑起来。

    【局限（诚实说明）】
    这是词法匹配，不是语义理解：
      · "芯片" 能匹配 "芯片"，但匹配不到 "半导体"
      · 语料库变化后需要重建索引（因为 TF-IDF 的 IDF 变了）
    """

    backend_name = "local"
    dim = EMBEDDING_DIM

    #: 语料库持久化路径（保存 TF-IDF 词表与 SVD 投影矩阵）
    STATE_FILENAME = "local_embedder_state.npz"

    def __init__(self):
        """初始化（不在此时训练，等 build_index 时用全量语料训练）。"""
        self.vectorizer = None
        self.svd = None
        # 记录语料规模，用于接口展示
        self.corpus_size = 0
        # 语料指纹：用于判断"这个向量化器是不是构建当前索引时用的那个"
        self.corpus_fingerprint = ""

        super().__init__()

    def _check_dependency(self) -> bool:
        """检查 scikit-learn 是否可用（它已是项目的既有依赖）。"""
        try:
            import sklearn  # noqa: F401

            return True
        except ImportError:
            logger.error("scikit-learn 未安装，本地向量化不可用")
            return False

    # -----------------------------------------------------------------
    # 训练（把整个语料库拟合到 TF-IDF + SVD）
    # -----------------------------------------------------------------
    def fit(self, texts: list[str]) -> None:
        """用全部语料训练向量化器。

        【为什么必须用全量语料训练】
        TF-IDF 的 IDF 依赖"文档频率"，只有看到全部文档才能算准。
        若逐条 fit，同一条文本在不同批次会得到不同向量，检索就不准了。

        因此 RAG 的正确做法是：
            重建索引时 -> 用全量语料 fit 一次 -> 再逐条 transform 写入向量库

        参数:
            texts: 全部文档文本
        """
        if not texts:
            raise EmbeddingError("语料为空，无法训练向量化器")

        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        logger.info("开始训练本地向量化器，语料 %d 条", len(texts))

        # char_wb：只在词边界内做字符 n-gram，对中文等价于按字切
        # 1-2 元：单字 + 双字组合，兼顾覆盖率与特征量
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(1, 2),
            max_features=20000,   # 限制特征数，避免词表爆炸
            min_df=1,
            sublinear_tf=True,    # 用 1+log(tf) 抑制高频词，效果通常更好
        )
        tfidf_matrix = self.vectorizer.fit_transform(texts)

        # SVD 维度不能超过 min(样本数, 特征数)，否则报错
        n_components = min(self.dim, tfidf_matrix.shape[0] - 1, tfidf_matrix.shape[1] - 1)
        n_components = max(2, n_components)   # 至少 2 维

        self.svd = TruncatedSVD(n_components=n_components, random_state=42)
        self.svd.fit(tfidf_matrix)
        # 实际维度以 SVD 为准（小语料时达不到 256 维）
        self.dim = n_components
        self.corpus_size = len(texts)
        # 语料指纹：检索时据此判断内存里的向量化器是否已过期
        self.corpus_fingerprint = _fingerprint_texts(texts)

        logger.info(
            "本地向量化器训练完成：特征 %d 个 -> 降维 %d 维，解释方差 %.3f，指纹 %s",
            tfidf_matrix.shape[1], self.dim,
            self.svd.explained_variance_ratio_.sum(),
            self.corpus_fingerprint,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把文本转成归一化向量。"""
        if self.vectorizer is None or self.svd is None:
            raise EmbeddingError(
                "本地向量化器尚未训练，请先执行：python manage.py build_index"
            )

        from sklearn.preprocessing import normalize

        tfidf = self.vectorizer.transform(texts)
        dense = self.svd.transform(tfidf)
        # L2 归一化：归一化后余弦相似度 = 点积，ChromaDB 用 cosine 空间即可
        normalized = normalize(dense)
        return normalized.tolist()

    # -----------------------------------------------------------------
    # 持久化
    # -----------------------------------------------------------------
    def save(self, directory) -> str:
        """把训练好的参数保存到磁盘，避免每次重启都重新训练。

        参数:
            directory: 保存目录（Path 对象）

        返回:
            保存的文件路径
        """
        import pickle
        from pathlib import Path

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.STATE_FILENAME

        with open(path, "wb") as f:
            pickle.dump(
                {
                    "vectorizer": self.vectorizer,
                    "svd": self.svd,
                    "dim": self.dim,
                    "corpus_size": self.corpus_size,
                    "corpus_fingerprint": self.corpus_fingerprint,
                },
                f,
            )
        logger.info("本地向量化器已保存：%s", path)
        return str(path)

    def load(self, directory) -> bool:
        """从磁盘加载参数。

        参数:
            directory: 保存目录

        返回:
            是否加载成功
        """
        import pickle
        from pathlib import Path

        path = Path(directory) / self.STATE_FILENAME
        if not path.exists():
            logger.debug("未找到已保存的向量化器：%s", path)
            return False

        try:
            with open(path, "rb") as f:
                state = pickle.load(f)
            self.vectorizer = state["vectorizer"]
            self.svd = state["svd"]
            self.dim = state["dim"]
            self.corpus_size = state.get("corpus_size", 0)
            # 旧版本的状态文件没有这个键，取空串表示"未知"
            self.corpus_fingerprint = state.get("corpus_fingerprint", "")
            logger.info(
                "已加载本地向量化器：%d 维，语料 %d 条，指纹 %s",
                self.dim, self.corpus_size, self.corpus_fingerprint or "(旧版无)",
            )
            return True
        except Exception as exc:
            logger.warning("加载本地向量化器失败：%s", exc)
            return False

    def describe(self) -> dict:
        """附加语料规模信息。"""
        info = super().describe()
        info.update(
            {
                "model": "TF-IDF + SVD (本地词法匹配)",
                "corpus_size": self.corpus_size,
                "fitted": self.vectorizer is not None,
                "note": "词法匹配，非语义理解；如需语义检索请启用 ollama/dashscope",
            }
        )
        return info


# ===========================================================================
# 工厂
# ===========================================================================
# 实例缓存：LocalEmbedder 训练一次即复用，重建索引时通过 refresh 强制刷新
_EMBEDDER_CACHE: dict[str, BaseEmbedder] = {}


def get_embedder(backend: Optional[str] = None, *, refresh: bool = False) -> BaseEmbedder:
    """按配置返回向量化器。

    参数:
        backend: 指定后端（ollama / dashscope / local）；不传则读 settings
        refresh: 为 True 时忽略缓存，重建实例（用于重建索引后刷新状态）

    返回:
        BaseEmbedder 实例

    【降级策略】
    若指定后端不可用，自动降级到 local，并记录警告。
    这样 AI 模块在缺少外部服务时依然可用，只是检索质量下降。
    """
    from django.conf import settings

    name = (
        backend or getattr(settings, "EMBEDDING_BACKEND", "local")
    ).strip().lower()

    if not refresh and name in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[name]

    backend_map = {
        "ollama": OllamaEmbedder,
        "dashscope": DashScopeEmbedder,
        "local": LocalEmbedder,
    }
    embedder_class = backend_map.get(name)

    if embedder_class is None:
        logger.warning("未知的向量化后端 %r，回退到 local", name)
        embedder_class = LocalEmbedder

    embedder = embedder_class()

    # 指定后端不可用时降级（local 是最终兜底，不存在降级）
    if not embedder.available and embedder_class is not LocalEmbedder:
        logger.warning("向量化后端 %s 不可用，降级到 local", name)
        embedder = LocalEmbedder()

    _EMBEDDER_CACHE[name] = embedder
    return embedder


def reset_embedder_cache() -> None:
    """清空实例缓存（重建索引后调用，确保拿到最新的训练状态）。"""
    _EMBEDDER_CACHE.clear()

# -*- coding: utf-8 -*-
"""
ai 应用的测试（阶段五：RAG 与向量检索）。

【测试策略】
RAG 链路的每一环都能独立测试，因此这里分层验证：
  1. 向量化层：LocalEmbedder 的训练、向量维度、相似度是否合理（不依赖网络）
  2. 意图识别：纯字符串逻辑，最容易测也最容易出错
  3. Prompt 组装：验证检索结果是否被正确格式化、编号是否连续
  4. 检索层：用真实 ChromaDB 临时目录，验证写入→检索闭环
  5. 接口层：验证参数校验、统一响应格式、降级行为

【为什么不测试真实大模型调用】
Ollama 未安装、无 DashScope Key 时无法调用真实模型，
因此 LLM 部分只测"降级逻辑是否正确"与"fallback 是否能组织回答"。
真实模型调用属于集成测试，不适合放进单元测试。

运行：
    python manage.py test apps.ai -v 2
"""

import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from apps.ai.embedding import LocalEmbedder, get_embedder, reset_embedder_cache
from apps.ai.llm import RetrievalOnlyLLM, get_llm, reset_llm_cache
from apps.ai.rag import (
    Intent,
    build_context,
    build_prompt,
    detect_intent,
)


def make_temp_chroma_dir() -> str:
    """在【项目目录内】创建一个临时 ChromaDB 目录。

    【为什么不用 tempfile.mkdtemp()】
    实测在本机环境下，ChromaDB 无法在系统临时目录
    （C:\\Users\\...\\AppData\\Local\\Temp\\...）打开其 SQLite 文件，会报：
        InternalError: error returned from database: (code: 14)
                       unable to open database file
    而项目目录内一切正常。这多半与沙箱对临时目录的访问限制有关。

    因此改为在 backend/data/ 下建临时目录，并在 tearDown 中清理。
    """
    path = Path(settings.BASE_DIR) / "data" / f"_test_chroma_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


# ===========================================================================
# 1. 意图识别
# ===========================================================================
class IntentDetectionTests(SimpleTestCase):
    """意图识别测试。

    意图决定检索策略（排行按播放量重排、推荐按相关度加权），
    识别错了会导致"问最火的却返回最相关的"。
    """

    def test_ranking_intent(self):
        """排行类问法应识别为 ranking。"""
        for query in (
            "科技区最火的视频",
            "播放量最高的视频",
            "游戏区排行榜",
            "哪个视频点赞最多",
        ):
            with self.subTest(query=query):
                self.assertEqual(detect_intent(query), Intent.RANKING)

    def test_recommend_intent(self):
        """推荐类问法应识别为 recommend。"""
        for query in (
            "推荐适合下饭的搞笑视频",
            "有什么好看的视频",
            "想看科技类的",
        ):
            with self.subTest(query=query):
                self.assertEqual(detect_intent(query), Intent.RECOMMEND)

    def test_topic_intent(self):
        """选题类问法应识别为 topic。"""
        for query in (
            "给我一些选题建议",
            "做什么内容比较好",
            "什么方向容易火",
        ):
            with self.subTest(query=query):
                self.assertEqual(detect_intent(query), Intent.TOPIC)

    def test_trend_intent(self):
        """趋势类问法应识别为 trend。"""
        for query in ("最近有什么新视频", "这段时间的趋势如何"):
            with self.subTest(query=query):
                self.assertEqual(detect_intent(query), Intent.TREND)

    def test_general_intent_fallback(self):
        """无关键词时应落到 general。"""
        self.assertEqual(detect_intent("你好"), Intent.GENERAL)
        self.assertEqual(detect_intent(""), Intent.GENERAL)

    def test_topic_has_higher_priority_than_ranking(self):
        """同时含"选题"与"最火"时应判定为选题。

        INTENT_KEYWORDS 的顺序即优先级，选题在前。
        这类问法本质是"想知道做什么内容能火"，属于选题而非排行。
        """
        self.assertEqual(detect_intent("选题建议：什么内容最火"), Intent.TOPIC)


# ===========================================================================
# 2. Prompt 组装
# ===========================================================================
class PromptBuildingTests(SimpleTestCase):
    """上下文与 Prompt 组装测试。"""

    SAMPLE_HITS = [
        {
            "bvid": "BV1xx411c7mD",
            "title": "【显卡】深度评测",
            "partition": "科技",
            "up_name": "某UP主",
            "view_count": 123456,
            "like_count": 5678,
            "interaction_rate": 0.085,
            "similarity": 0.71,
        },
        {
            "bvid": "BV2yy522d8nE",
            "title": "【固态硬盘】原理讲解",
            "partition": "科技",
            "up_name": "另一个UP主",
            "view_count": 6543,
            "like_count": 210,
            "interaction_rate": 0.061,
            "similarity": 0.62,
        },
    ]

    def test_build_context_numbers_are_sequential(self):
        """参考资料编号必须从 [1] 开始连续，保证引用可溯源。"""
        context = build_context(self.SAMPLE_HITS)
        self.assertIn("[1]", context)
        self.assertIn("[2]", context)
        # 两条资料都应出现标题
        self.assertIn("【显卡】深度评测", context)
        self.assertIn("【固态硬盘】原理讲解", context)

    def test_build_context_includes_metrics(self):
        """参考资料应包含关键数据，供模型引用具体数字。"""
        context = build_context(self.SAMPLE_HITS)
        self.assertIn("123,456", context)      # 千分位格式化
        self.assertIn("8.50%", context)        # 百分比格式化
        self.assertIn("BV1xx411c7mD", context)

    def test_build_context_empty_hits(self):
        """无检索结果时应给出明确说明，而不是空白。"""
        context = build_context([])
        self.assertIn("没有检索到", context)

    def test_build_prompt_structure(self):
        """Prompt 应包含参考资料与用户问题两部分。"""
        prompt = build_prompt("科技区有什么好视频", self.SAMPLE_HITS)
        self.assertIn("【参考资料】", prompt)
        self.assertIn("【用户问题】", prompt)
        self.assertIn("科技区有什么好视频", prompt)

    def test_build_prompt_with_history(self):
        """带历史时应包含对话历史，且只取最近若干轮。"""
        history = [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "第二个问题"},
        ]
        prompt = build_prompt("追问", self.SAMPLE_HITS, history=history)
        self.assertIn("【对话历史】", prompt)
        self.assertIn("第一个问题", prompt)

    def test_build_prompt_truncates_long_history(self):
        """过长的历史应被裁剪，避免 Prompt 超长。

        传 20 条历史，只应保留最近 6 条（3 轮）。
        """
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"历史{i}"}
            for i in range(20)
        ]
        prompt = build_prompt("现在的问题", self.SAMPLE_HITS, history=history)
        # 最早的历史不应出现
        self.assertNotIn("历史0", prompt)
        # 最近的应出现
        self.assertIn("历史19", prompt)


# ===========================================================================
# 3. 本地向量化
# ===========================================================================
class LocalEmbedderTests(SimpleTestCase):
    """本地 TF-IDF 向量化器测试。"""

    DOCS = [
        "国产芯片深度评测 芯片 科技",
        "国产芯片性能对比 芯片 测评",
        "家常菜做法教程 美食 烹饪",
        "火锅做法详解 美食 火锅",
        "高等数学讲解 知识 数学",
    ]

    def test_fit_and_embed(self):
        """训练后应能产出正确维度的向量。"""
        embedder = LocalEmbedder()
        embedder.fit(self.DOCS)

        self.assertIsNotNone(embedder.vectorizer)
        self.assertIsNotNone(embedder.svd)
        self.assertGreater(embedder.dim, 0)

        vectors = embedder.embed_documents(self.DOCS)
        self.assertEqual(len(vectors), len(self.DOCS))
        for vec in vectors:
            self.assertEqual(len(vec), embedder.dim)

    def test_vectors_are_normalized(self):
        """向量应已 L2 归一化（模长接近 1），否则余弦相似度不准。"""
        embedder = LocalEmbedder()
        embedder.fit(self.DOCS)
        vectors = embedder.embed_documents(self.DOCS)

        for vec in vectors:
            norm = sum(v * v for v in vec) ** 0.5
            self.assertAlmostEqual(norm, 1.0, places=4)

    def test_similar_texts_are_closer(self):
        """语义相近的文本，相似度应高于不相关的文本。

        这是向量化"是否有效"的核心断言：
        两条芯片视频的相似度，必须高于"芯片"与"火锅"的相似度。
        """
        embedder = LocalEmbedder()
        embedder.fit(self.DOCS)
        vectors = embedder.embed_documents(self.DOCS)

        def dot(a, b):
            return sum(x * y for x, y in zip(a, b))

        # 索引 0、1 是芯片；2、3 是美食；4 是数学
        sim_chip_chip = dot(vectors[0], vectors[1])
        sim_chip_food = dot(vectors[0], vectors[2])
        sim_chip_math = dot(vectors[0], vectors[4])

        self.assertGreater(
            sim_chip_chip, sim_chip_food,
            "同类文本（芯片↔芯片）的相似度应高于跨类（芯片↔美食）",
        )
        self.assertGreater(
            sim_chip_chip, sim_chip_math,
            "同类文本的相似度应高于与数学的相似度",
        )

    def test_embed_query_consistency(self):
        """同一文本用 embed_query 与 embed_documents 应得到一致结果。"""
        embedder = LocalEmbedder()
        embedder.fit(self.DOCS)

        vec_doc = embedder.embed_documents([self.DOCS[0]])[0]
        vec_query = embedder.embed_query(self.DOCS[0])

        for a, b in zip(vec_doc, vec_query):
            self.assertAlmostEqual(a, b, places=6)

    def test_embed_before_fit_raises(self):
        """未训练就向量化应抛出明确错误，而不是返回空向量。"""
        from apps.ai.embedding import EmbeddingError

        embedder = LocalEmbedder()
        with self.assertRaises(EmbeddingError):
            embedder.embed_documents(["测试"])

    def test_describe_reports_limitation(self):
        """describe 必须如实说明"词法匹配"的局限。

        这一点很重要：不能让人误以为本地后端有真正的语义理解能力。
        """
        embedder = LocalEmbedder()
        embedder.fit(self.DOCS)
        info = embedder.describe()

        self.assertEqual(info["backend"], "local")
        self.assertIn("note", info)
        self.assertIn("词法匹配", info["note"])


# ===========================================================================
# 4. 向量检索闭环（用真实 ChromaDB 临时目录）
# ===========================================================================
class VectorStoreTests(TestCase):
    """向量库写入与检索的闭环测试。"""

    @classmethod
    def setUpTestData(cls):
        """构造少量视频数据。"""
        from apps.videos.models import Partition, UpUser, Video

        cls.partition = Partition.objects.create(name="科技", bili_tid=188)
        cls.upuser = UpUser.objects.create(mid=9001, name="测试UP主")

        titles = [
            ("BV1test000001", "国产芯片深度评测", "芯片 评测 科技"),
            ("BV1test000002", "固态硬盘原理讲解", "固态硬盘 原理 科技"),
            ("BV1test000003", "家常菜做法教程", "美食 烹饪 教程"),
        ]
        for bvid, title, tags in titles:
            Video.objects.create(
                bvid=bvid,
                title=title,
                tags=tags,
                partition=cls.partition,
                upuser=cls.upuser,
                view_count=1000,
                like_count=100,
                duration=300,
            )

    def setUp(self):
        """为每个测试准备独立的 ChromaDB 临时目录。

        【为什么必须隔离】
        ChromaDB 持久化在磁盘上，多个测试共用一个目录会互相污染
        （上一个测试写入的向量会出现在下一个测试的检索结果里）。
        """
        self.tmpdir = make_temp_chroma_dir()
        self.override = override_settings(CHROMA_PERSIST_DIR=self.tmpdir)
        self.override.enable()

        # 清空缓存，确保拿到指向新目录的实例
        reset_embedder_cache()

    def tearDown(self):
        """清理临时目录与缓存。"""
        self.override.disable()
        reset_embedder_cache()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_index_and_search(self):
        """构建索引后应能检索到相关视频。"""
        from apps.ai.vector_store import build_index, search

        result = build_index(rebuild=True)
        self.assertEqual(result["indexed"], 3)
        self.assertEqual(result["backend"], "local")

        hits = search("国产芯片评测", top_k=3)
        self.assertGreater(len(hits), 0)

        # 第一条应是最相关的"国产芯片深度评测"
        self.assertIn("芯片", hits[0]["title"])
        # 相似度应在合理区间
        self.assertGreater(hits[0]["similarity"], 0.3)

    def test_search_respects_top_k(self):
        """top_k 应生效。"""
        from apps.ai.vector_store import build_index, search

        build_index(rebuild=True)
        hits = search("视频", top_k=2)
        self.assertLessEqual(len(hits), 2)

    def test_search_returns_metadata(self):
        """检索结果应带上前端展示所需的元数据。"""
        from apps.ai.vector_store import build_index, search

        build_index(rebuild=True)
        hits = search("芯片", top_k=1)

        self.assertTrue(hits)
        hit = hits[0]
        for key in ("bvid", "title", "partition", "up_name",
                    "view_count", "similarity"):
            self.assertIn(key, hit, f"检索结果缺少字段 {key}")

    def test_search_partition_filter(self):
        """分区过滤应生效（ChromaDB 的 where 条件）。"""
        from apps.ai.vector_store import build_index, search

        build_index(rebuild=True)

        # 测试数据全在"科技"分区，用不存在的分区筛选应返回空
        hits = search("芯片", top_k=5, partition="不存在的分区")
        self.assertEqual(hits, [])

    def test_search_without_index_returns_empty(self):
        """未构建索引时应返回空列表而不是抛异常。"""
        from apps.ai.vector_store import search

        hits = search("任意查询", top_k=3)
        self.assertEqual(hits, [])

    def test_get_index_stats(self):
        """索引状态应正确反映构建情况。"""
        from apps.ai.vector_store import build_index, get_index_stats

        stats_before = get_index_stats()
        self.assertFalse(stats_before["ready"])

        build_index(rebuild=True)

        stats_after = get_index_stats()
        self.assertTrue(stats_after["ready"])
        self.assertEqual(stats_after["count"], 3)

    def test_rebuild_replaces_old_vectors(self):
        """rebuild 应清空旧集合，条数不累加。"""
        from apps.ai.vector_store import build_index, get_index_stats

        build_index(rebuild=True)
        build_index(rebuild=True)   # 再建一次

        stats = get_index_stats()
        # 若未清空会变成 6
        self.assertEqual(stats["count"], 3)


# ===========================================================================
# 5. LLM 降级逻辑
# ===========================================================================
class StaleEmbedderRecoveryTests(TestCase):
    """向量化器与索引不配套时的自动恢复测试。

    【这个 Bug 的真实经过 —— 界面上只显示"没找到"，看不出任何线索】
        用户反馈 AI 助手检索不到内容，但状态面板明明写着"索引就绪 40 条向量"。
        查服务器日志才看到真相：

            15:48:40 INFO  已加载本地向量化器：256 维，语料 297 条
            16:20:14 ERROR 向量检索失败：Collection expecting embedding with
                           dimension of 39, got 256

        本地向量化器是**用全量语料训练**的，语料一变维度就变
        （297 条 -> 256 维，40 条 -> 39 维）。
        而它在 Web 进程里是缓存的。重建索引若发生在 CLI 或别的进程，
        Web 进程内存里仍是旧的那一份。

        search() 原先只在"完全没训练过"时才去加载磁盘状态：

            if embedder.vectorizer is None: embedder.load(...)

        内存里那份**是训练过的旧版本**，条件为假，于是拿着过期投影去查新索引，
        抛出的维度异常又被 except 吞掉、返回空列表 ——
        最终界面只说"没有找到相关视频"。

        这类"静默降级"最难排查：功能看起来正常，只是永远没结果。
    """

    @classmethod
    def setUpTestData(cls):
        """构造少量视频数据。"""
        from apps.videos.models import Video

        for i, title in enumerate(["国产芯片深度评测", "固态硬盘原理讲解", "美食做法"]):
            Video.objects.create(
                bvid=f"BV1stale0000{i}",
                title=title,
                tags=title,
                view_count=1000 + i,
                like_count=100,
                duration=300,
            )

    def setUp(self):
        """隔离的临时向量库目录 + 清空缓存。"""
        self.tmpdir = make_temp_chroma_dir()
        self.override = override_settings(CHROMA_PERSIST_DIR=self.tmpdir)
        self.override.enable()
        reset_embedder_cache()

    def tearDown(self):
        """清理。"""
        self.override.disable()
        reset_embedder_cache()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_collection_records_embedder_identity(self):
        """建索引时应把向量化器的维度与语料指纹写进集合元数据。

        没有这份"身份信息"，检索时就无从判断内存里的向量化器是否已过期。
        """
        from apps.ai.vector_store import _get_collection, build_index

        build_index(rebuild=True)
        meta = _get_collection(create=False).metadata or {}

        self.assertIn("embedding_dim", meta)
        self.assertIn("corpus_fingerprint", meta)
        self.assertEqual(meta["corpus_size"], 3)
        self.assertTrue(meta["corpus_fingerprint"])

    def test_stale_embedder_is_reloaded_automatically(self):
        """内存里是过期的向量化器时，检索应自动重新加载并正常返回。"""
        from apps.ai import embedding
        from apps.ai.vector_store import _get_collection, build_index, search

        build_index(rebuild=True)

        # ---- 人为制造"过期向量化器"：用另一批语料训练，维度与指纹都不同 ----
        stale = LocalEmbedder()
        stale.fit([f"完全无关的另一批语料 {i}" for i in range(300)])
        self.assertNotEqual(stale.dim, 39)
        embedding._EMBEDDER_CACHE["local"] = stale

        # 用这个过期实例直接查询，会复现维度不匹配（证明场景构造正确）
        collection = _get_collection(create=False)
        with self.assertRaises(Exception) as ctx:
            collection.query(
                query_embeddings=[stale.embed_query("芯片")], n_results=1
            )
        self.assertIn("dimension", str(ctx.exception).lower())

        # ---- 走修复后的 search()，应自动刷新并拿到结果 ----
        hits = search("国产芯片评测", top_k=3)
        self.assertGreater(len(hits), 0, "过期的向量化器应被自动刷新，检索不应为空")

        # 缓存里的实例也应已被替换成正确的那一份
        fixed = embedding._EMBEDDER_CACHE.get("local")
        self.assertIsNotNone(fixed)
        self.assertEqual(fixed.corpus_fingerprint, collection.metadata["corpus_fingerprint"])

    def test_matching_embedder_is_not_reloaded(self):
        """向量化器本来就配套时不应被无谓地重建（避免每次检索都重训）。"""
        from apps.ai import embedding
        from apps.ai.vector_store import build_index, search

        build_index(rebuild=True)
        before = embedding._EMBEDDER_CACHE.get("local")
        self.assertIsNotNone(before)

        search("国产芯片评测", top_k=2)

        self.assertIs(
            embedding._EMBEDDER_CACHE.get("local"),
            before,
            "配套的向量化器不应被替换",
        )


class LlmFallbackTests(SimpleTestCase):
    """大模型降级与兜底回答测试。"""

    def setUp(self):
        reset_llm_cache()

    def tearDown(self):
        reset_llm_cache()

    def test_fallback_provider_always_available(self):
        """fallback 必须永远可用（这是最后的保险）。"""
        llm = RetrievalOnlyLLM()
        self.assertTrue(llm.available)
        self.assertEqual(llm.provider_name, "fallback")

    def test_get_llm_always_returns_instance(self):
        """无论配置什么，get_llm 都不应抛异常或返回 None。

        这是保证对话功能"永不崩溃"的关键。
        """
        for provider in ("ollama", "dashscope", "deepseek", "fallback", "不存在的provider"):
            with self.subTest(provider=provider):
                llm = get_llm(provider, refresh=True)
                self.assertIsNotNone(llm)
                self.assertTrue(hasattr(llm, "generate"))


class DeepSeekProviderTests(SimpleTestCase):
    """DeepSeek Provider 专用测试。

    【为什么单独测这个】
    DeepSeek 官方文档有个容易踩的坑：
        API 模型名是 "deepseek-flash"
        而 "DeepSeek-V4.1-Flash" 是【版本名】，不是模型名
    填错会直接报"模型不存在"。这里用测试把这个约定固化下来，
    避免以后有人"顺手改成版本名"。
    """

    def setUp(self):
        reset_llm_cache()

    def tearDown(self):
        reset_llm_cache()

    def test_default_model_name_is_api_name(self):
        """默认模型名必须是 API 名 deepseek-flash，而非版本名。"""
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(api_key="sk-test")
        self.assertEqual(llm.model, "deepseek-flash")

    def test_version_name_triggers_warning(self):
        """误填版本名时应给出警告（而不是静默失败）。"""
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(model="deepseek-v4.1-flash", api_key="sk-test")

        with self.assertLogs("apps.ai.llm", level="WARNING") as ctx:
            llm._check_dependency()

        self.assertTrue(
            any("deepseek-flash" in msg for msg in ctx.output),
            "应提示正确的模型名",
        )

    def test_unavailable_without_api_key(self):
        """未配置 API Key 时应报告不可用，触发降级。

        【为什么必须用 override_settings】
        真实环境里 .env 已配置了 DEEPSEEK_API_KEY，
        而 os.environ 中的同名变量（若存在）优先级最高，
        会覆盖任何显式传入的参数。因此测试必须显式清空 settings 中的 Key，
        否则这个测试会在"已配置密钥"的机器上误报失败。
        """
        from apps.ai.llm import DeepSeekLLM

        with override_settings(DEEPSEEK_API_KEY=""):
            llm = DeepSeekLLM(api_key="")
            self.assertFalse(llm.available)

    def test_payload_disables_thinking_mode(self):
        """请求体必须显式关闭思考模式。

        该模型默认开启 thinking，会输出思维链，
        对终端用户是噪声（与 deepseek-r1 同类问题）。
        """
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(api_key="sk-test")
        payload = llm._build_payload("问题", "系统提示", 0.7, 512, False)

        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertFalse(payload["stream"])
        # messages 应包含 system + user
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")

    def test_payload_openai_format(self):
        """请求体应符合 OpenAI 兼容格式。"""
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(api_key="sk-test")
        payload = llm._build_payload("问题", "", 0.5, 256, True)

        for key in ("model", "messages", "temperature", "max_tokens", "stream"):
            self.assertIn(key, payload)
        # 无 system 时 messages 只有一条 user
        self.assertEqual(len(payload["messages"]), 1)

    def test_base_url_default(self):
        """默认接口地址应为官方地址。"""
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(api_key="sk-test")
        self.assertEqual(llm.base_url, "https://api.deepseek.com")

    def test_available_with_api_key(self):
        """配置了合法 API Key 时应报告可用（不实际发请求）。"""
        from apps.ai.llm import DeepSeekLLM

        llm = DeepSeekLLM(api_key="sk-abcdef123456")
        self.assertTrue(llm.available)

    def test_fallback_composes_answer_from_hits(self):
        """兜底方案应把检索结果组织成可读回答。"""
        llm = RetrievalOnlyLLM()
        llm.set_context([
            {
                "bvid": "BV1xx411c7mD",
                "title": "【显卡】深度评测",
                "partition": "科技",
                "up_name": "某UP主",
                "view_count": 123456,
                "similarity": 0.71,
            }
        ])

        answer = llm.generate("")

        # 必须明确标注未接入大模型，不能让用户误以为是模型生成的
        self.assertIn("未接入大模型", answer)
        # 应包含真实数据
        self.assertIn("【显卡】深度评测", answer)
        self.assertIn("BV1xx411c7mD", answer)
        self.assertIn("123,456", answer)

    def test_fallback_without_hits_gives_suggestions(self):
        """无检索结果时应给出可操作的排查建议。"""
        llm = RetrievalOnlyLLM()
        llm.set_context([])

        answer = llm.generate("")

        self.assertIn("没有在视频库中找到", answer)
        # 应引导用户构建索引与准备数据（两条命令都要给出）
        self.assertIn("build_index", answer)
        self.assertIn("seed_demo", answer)

    def test_fallback_stream_yields_multiple_chunks(self):
        """兜底方案也应支持流式（分块吐出）。"""
        llm = RetrievalOnlyLLM()
        llm.set_context([
            {
                "bvid": "BV1", "title": "标题一", "partition": "科技",
                "up_name": "UP", "view_count": 100, "similarity": 0.5,
            }
        ])

        chunks = list(llm.generate_stream(""))
        self.assertGreater(len(chunks), 1, "应分多块吐出以实现打字机效果")
        # 拼起来应与非流式结果一致
        self.assertEqual("".join(chunks), llm.generate(""))


# ===========================================================================
# 6. 接口层
# ===========================================================================
class AiApiTests(TestCase):
    """AI 接口的契约测试。"""

    def setUp(self):
        """使用临时向量目录，避免污染真实索引。"""
        self.tmpdir = make_temp_chroma_dir()
        self.override = override_settings(CHROMA_PERSIST_DIR=self.tmpdir)
        self.override.enable()
        reset_embedder_cache()
        reset_llm_cache()

    def tearDown(self):
        self.override.disable()
        reset_embedder_cache()
        reset_llm_cache()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_status_endpoint(self):
        """状态接口应返回索引与 LLM 信息。"""
        response = self.client.get("/api/ai/status/")
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertIn("index", data)
        self.assertIn("llm", data)
        self.assertIn("ready", data)
        self.assertIn("hint", data)

    def test_status_reports_not_ready_without_index(self):
        """未构建索引时应报告未就绪并给出提示。"""
        data = self.client.get("/api/ai/status/").json()["data"]
        self.assertFalse(data["ready"])
        self.assertIn("build_index", data["hint"])

    def test_chat_requires_query(self):
        """缺少 query 应返回 400 统一格式。"""
        response = self.client.post(
            "/api/ai/chat/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], 1001)

    def test_chat_query_too_long(self):
        """超长 query 应被拒绝。"""
        response = self.client.post(
            "/api/ai/chat/",
            data={"query": "测试" * 400},   # 800 字，超过 500 上限
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_json_mode_without_index(self):
        """索引缺失时，非流式对话应仍返回 200 并给出可用回答。

        【为什么这个测试重要】
        这是"AI 模块永不崩溃"的保证：即使索引没建、大模型没接，
        接口也必须返回结构完整的响应，而不是 500。
        """
        response = self.client.post(
            "/api/ai/chat/",
            data={"query": "科技区有什么视频", "stream": False, "save": False},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertIn("answer", data)
        self.assertIn("sources", data)
        self.assertIn("provider", data)
        # 答案不应为空
        self.assertTrue(data["answer"].strip())

    def test_chat_json_mode_with_index(self):
        """有索引时应检索到真实视频。"""
        from apps.videos.models import Video

        Video.objects.create(
            bvid="BV1api0000001",
            title="国产芯片深度评测",
            tags="芯片 科技",
            view_count=5000,
            like_count=400,
            duration=600,
        )

        # 重建索引
        from apps.ai.vector_store import build_index

        build_index(rebuild=True)

        response = self.client.post(
            "/api/ai/chat/",
            data={"query": "国产芯片评测", "stream": False, "save": False, "top_k": 3},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertGreater(len(data["sources"]), 0, "应检索到视频")
        self.assertEqual(data["sources"][0]["bvid"], "BV1api0000001")
        self.assertIn("intent", data)

    def test_chat_saves_history(self):
        """开启 save 时应写入会话与消息记录。"""
        from apps.ai.models import ChatMessage, ChatSession

        response = self.client.post(
            "/api/ai/chat/",
            data={"query": "测试问题", "stream": False, "save": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        session_id = response.json()["data"]["session_id"]
        self.assertIsNotNone(session_id)

        self.assertEqual(ChatSession.objects.count(), 1)
        # 应记录 2 条：用户提问 + 助手回答
        self.assertEqual(ChatMessage.objects.filter(session_id=session_id).count(), 2)

    def test_history_endpoints(self):
        """历史接口应返回会话与消息。"""
        self.client.post(
            "/api/ai/chat/",
            data={"query": "历史测试", "stream": False, "save": True},
            content_type="application/json",
        )

        # 列表
        listing = self.client.get("/api/ai/history/").json()["data"]
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["title"], "历史测试")
        self.assertEqual(listing["items"][0]["message_count"], 2)

        # 详情
        session_id = listing["items"][0]["id"]
        detail = self.client.get(f"/api/ai/history/{session_id}/").json()["data"]
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["role"], "user")
        self.assertEqual(detail["messages"][1]["role"], "assistant")

    def test_history_detail_404(self):
        """会话不存在应返回统一格式的 404。"""
        response = self.client.get("/api/ai/history/99999/")
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["code"], 1004)
        self.assertIn("99999", payload["message"])

    def test_build_index_endpoint(self):
        """重建索引接口应可用。"""
        from apps.videos.models import Video

        Video.objects.create(
            bvid="BV1build00001",
            title="测试视频",
            view_count=100,
            duration=60,
        )

        response = self.client.post(
            "/api/ai/build-index/",
            data={"rebuild": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertEqual(data["indexed"], 1)
        self.assertIn("elapsed", data)

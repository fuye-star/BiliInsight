# -*- coding: utf-8 -*-
"""
videos 与 analytics 接口层的测试。

【测试重点：接口契约，而非统计数值】
统计数值的正确性已在 apps/analytics/tests.py 中验证。
这里关注的是**接口层的行为**：
  · 响应结构是否符合统一约定（code/message/data）
  · 参数校验是否生效（非法值应返回 400 而不是 500）
  · 排序/筛选是否真的生效
  · 404 是否返回统一格式而不是 DRF 默认的 {"detail": ...}

运行：
    python manage.py test apps.videos -v 2
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.videos.models import Danmaku, Partition, UpUser, Video


class ApiContractTestBase(TestCase):
    """构造接口测试所需的最小数据集。"""

    @classmethod
    def setUpTestData(cls):
        """创建 3 个视频、2 个分区、2 个 UP主、4 条弹幕。"""
        now = timezone.now()

        cls.p_tech = Partition.objects.create(name="科技", bili_tid=188, color="#5470C6")
        cls.p_game = Partition.objects.create(name="游戏", bili_tid=4, color="#91CC75")

        cls.up_a = UpUser.objects.create(mid=2001, name="UP甲", follower_count=1000)
        cls.up_b = UpUser.objects.create(mid=2002, name="UP乙", follower_count=2000)

        cls.v1 = Video.objects.create(
            bvid="BV1test000001", aid=1, title="科技视频一",
            description="简介一", tags="科技,测试", partition=cls.p_tech,
            upuser=cls.up_a, view_count=1000, like_count=100,
            interaction_rate=0.1, duration=125, pubdate=now - timedelta(days=1),
        )
        cls.v2 = Video.objects.create(
            bvid="BV1test000002", aid=2, title="科技视频二",
            description="简介二", tags="科技", partition=cls.p_tech,
            upuser=cls.up_b, view_count=2000, like_count=300,
            interaction_rate=0.15, duration=3600, pubdate=now - timedelta(days=2),
        )
        cls.v3 = Video.objects.create(
            bvid="BV1test000003", aid=3, title="游戏视频",
            description="简介三", tags="游戏", partition=cls.p_game,
            upuser=cls.up_a, view_count=500, like_count=10,
            interaction_rate=0.02, duration=65, pubdate=now - timedelta(days=3),
        )

        cls.d1 = Danmaku.objects.create(
            video=cls.v1, dmid=1, content="太强了", video_time=10.0,
            sentiment_score=0.9, sentiment_label="positive", emotion_tags="高燃",
        )
        cls.d2 = Danmaku.objects.create(
            video=cls.v1, dmid=2, content="有点失望", video_time=20.0,
            sentiment_score=0.1, sentiment_label="negative", emotion_tags="失望",
        )
        cls.d3 = Danmaku.objects.create(
            video=cls.v2, dmid=3, content="打卡", video_time=5.0,
            sentiment_score=0.5, sentiment_label="neutral", emotion_tags="打卡",
        )
        cls.d4 = Danmaku.objects.create(
            video=cls.v2, dmid=4, content="哈哈哈", video_time=8.0,
            sentiment_score=0.85, sentiment_label="positive", emotion_tags="搞笑",
        )

    def setUp(self):
        """清空统计缓存，避免跨测试污染。"""
        from apps.analytics.services import clear_analytics_cache

        clear_analytics_cache()


class VideoListApiTests(ApiContractTestBase):
    """视频列表接口测试。"""

    def test_list_returns_paginated_envelope(self):
        """列表应返回统一的分页信封结构。"""
        response = self.client.get("/api/videos/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertIn("data", payload)

        data = payload["data"]
        # 分页元信息必须齐全，前端才能渲染分页控件
        for key in ("total", "page", "page_size", "total_pages",
                    "has_next", "has_previous", "results"):
            self.assertIn(key, data, f"分页响应缺少字段 {key}")

        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["results"]), 3)

    def test_list_item_fields(self):
        """列表项应含卡片展示所需字段，且不含长文本简介。"""
        item = self.client.get("/api/videos/").json()["data"]["results"][0]

        for key in ("bvid", "title", "cover_url", "duration_display",
                    "partition", "up_name", "view_count", "interaction_rate"):
            self.assertIn(key, item, f"列表项缺少字段 {key}")

        # 列表接口刻意不返回 description（可能上千字），避免响应过大
        self.assertNotIn("description", item)

    def test_ordering_by_view_count(self):
        """按播放量倒序应生效。"""
        response = self.client.get("/api/videos/?ordering=-view_count")
        results = response.json()["data"]["results"]
        views = [r["view_count"] for r in results]
        self.assertEqual(views, [2000, 1000, 500])

    def test_ordering_whitelist_blocks_injection(self):
        """非法排序字段应被忽略，不得进入 SQL。"""
        # 若白名单失效，这个请求会触发 SQL 错误导致 500
        response = self.client.get("/api/videos/?ordering=;DROP TABLE videos_video;--")
        self.assertEqual(response.status_code, 200)
        # 表仍然存在
        self.assertEqual(Video.objects.count(), 3)

    def test_filter_by_partition(self):
        """按分区筛选应生效。"""
        response = self.client.get("/api/videos/?partition=科技")
        data = response.json()["data"]
        self.assertEqual(data["total"], 2)
        for item in data["results"]:
            self.assertEqual(item["partition"], "科技")

    def test_search_by_title(self):
        """关键词搜索应覆盖标题。"""
        response = self.client.get("/api/videos/?search=游戏")
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["bvid"], "BV1test000003")

    def test_filter_by_min_view(self):
        """播放量下限筛选应生效。"""
        response = self.client.get("/api/videos/?min_view=900")
        self.assertEqual(response.json()["data"]["total"], 2)

    def test_pagination_page_size(self):
        """page_size 应生效且受上限保护。"""
        data = self.client.get("/api/videos/?page_size=2").json()["data"]
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["total_pages"], 2)

        # 超过上限应被夹到 max_page_size=100
        data2 = self.client.get("/api/videos/?page_size=99999").json()["data"]
        self.assertLessEqual(data2["page_size"], 100)


class VideoDetailApiTests(ApiContractTestBase):
    """视频详情接口测试。"""

    def test_detail_by_bvid(self):
        """应按 bvid 返回完整信息。"""
        response = self.client.get("/api/videos/BV1test000001/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["bvid"], "BV1test000001")
        # 详情包含简介（列表不含）
        self.assertIn("description", data)
        # 时长格式化：125 秒 -> 02:05
        self.assertEqual(data["duration_display"], "02:05")
        # 本地弹幕数
        self.assertEqual(data["local_danmaku_count"], 2)

    def test_detail_404_unified_format(self):
        """不存在的视频应返回统一错误格式，而不是 DRF 默认的 detail 字段。"""
        response = self.client.get("/api/videos/BVnotexist000/")
        self.assertEqual(response.status_code, 404)

        payload = response.json()
        self.assertEqual(payload["code"], 1004)
        # 错误信息应带上 bvid，便于前端定位
        self.assertIn("BVnotexist000", payload["message"])
        self.assertIsNone(payload["data"])
        # 不应出现 DRF 的默认 detail 字段
        self.assertNotIn("detail", payload)


class DanmakuApiTests(ApiContractTestBase):
    """弹幕接口测试。"""

    def test_danmaku_list_for_video(self):
        """应返回该视频的弹幕，并附带视频基本信息。"""
        response = self.client.get("/api/videos/BV1test000001/danmaku/")
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertEqual(data["total"], 2)
        # 附带视频信息，前端无需再发一次请求
        self.assertIn("video", data)
        self.assertEqual(data["video"]["bvid"], "BV1test000001")

    def test_danmaku_ordered_by_time(self):
        """弹幕应按出现时间正序，符合按进度浏览的用法。"""
        results = self.client.get(
            "/api/videos/BV1test000001/danmaku/"
        ).json()["data"]["results"]
        times = [r["video_time"] for r in results]
        self.assertEqual(times, sorted(times))

    def test_danmaku_sentiment_filter(self):
        """按情感筛选应生效。"""
        response = self.client.get("/api/videos/BV1test000001/danmaku/?sentiment=positive")
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["content"], "太强了")

    def test_danmaku_invalid_sentiment(self):
        """非法 sentiment 参数应返回 400 统一格式。"""
        response = self.client.get("/api/videos/BV1test000001/danmaku/?sentiment=xxx")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], 1001)
        self.assertIn("positive", payload["message"])

    def test_danmaku_404_for_missing_video(self):
        """不存在的视频应返回 404 统一格式。"""
        response = self.client.get("/api/videos/BVnope/danmaku/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 1004)

    def test_danmaku_emotion_tag_list(self):
        """情绪标签应被拆成列表。"""
        results = self.client.get(
            "/api/videos/BV1test000001/danmaku/"
        ).json()["data"]["results"]
        positive = [r for r in results if r["sentiment_label"] == "positive"][0]
        self.assertEqual(positive["emotion_tag_list"], ["高燃"])
        self.assertEqual(positive["sentiment_label_display"], "正向")


class PartitionAndUpuserApiTests(ApiContractTestBase):
    """分区与 UP主 列表接口测试。"""

    def test_partition_list_no_pagination(self):
        """分区列表应直接返回数组（数量少，无需分页）。"""
        response = self.client.get("/api/partitions/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["code"], 0)
        # data 是列表而不是分页对象
        self.assertIsInstance(payload["data"], list)
        self.assertEqual(len(payload["data"]), 2)

        # 应带视频数，供前端下拉展示
        tech = [p for p in payload["data"] if p["name"] == "科技"][0]
        self.assertEqual(tech["video_count"], 2)

    def test_upuser_list_default_order(self):
        """UP主 列表默认按粉丝数倒序。"""
        data = self.client.get("/api/upusers/").json()["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["results"][0]["name"], "UP乙")   # 2000 粉

    def test_upuser_search(self):
        """UP主 搜索应生效。"""
        data = self.client.get("/api/upusers/?search=甲").json()["data"]
        self.assertEqual(data["total"], 1)


class AnalyticsApiTests(ApiContractTestBase):
    """分析接口的契约与参数校验测试。"""

    def test_overview_shape(self):
        """总览接口应返回全部核心指标。"""
        data = self.client.get("/api/analytics/overview/").json()["data"]
        for key in ("video_count", "upuser_count", "total_view",
                    "avg_view", "avg_interaction_rate"):
            self.assertIn(key, data)
        self.assertEqual(data["video_count"], 3)

    def test_trend_invalid_days_falls_back(self):
        """非法 days 应回退到默认值而不是报错。"""
        response = self.client.get("/api/analytics/trend/?days=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["days"], 30)

    def test_trend_unknown_partition_404(self):
        """不存在的分区应返回 404，而不是静默返回空数据。"""
        response = self.client.get("/api/analytics/trend/?partition=不存在")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2001)

    def test_wordcloud_invalid_source(self):
        """非法 source 应返回 400。"""
        response = self.client.get("/api/analytics/wordcloud/?source=bogus")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], 1001)

    def test_sentiment_segments_respected(self):
        """segments 参数应生效。"""
        data = self.client.get("/api/analytics/sentiment/?segments=4").json()["data"]
        self.assertEqual(len(data["curve"]), 4)

    def test_top_videos_order_by_interaction(self):
        """按互动率排序应生效。

        互动率：v2=0.15 > v1=0.1 > v3=0.02
        """
        data = self.client.get(
            "/api/analytics/top-videos/?order_by=interaction_rate"
        ).json()["data"]
        rates = [item["interaction_rate"] for item in data["items"]]
        self.assertEqual(rates, sorted(rates, reverse=True))

    def test_interaction_analysis_threshold(self):
        """互动质量分析应只统计播放量 ≥ 1000 的视频。

        测试数据播放量分别为 1000 / 2000 / 500，
        因此只有前两个达标（1000 是闭区间边界，应被包含）。
        """
        data = self.client.get("/api/analytics/interaction/").json()["data"]
        self.assertEqual(len(data["top_interaction"]), 2)

        # 500 播放的视频必须被排除，避免"播放少、点赞相对多"造成虚高互动率
        bvids = {item["bvid"] for item in data["top_interaction"]}
        self.assertNotIn("BV1test000003", bvids)
        # 边界值 1000 应被包含（条件为 view_count__gte=1000）
        self.assertIn("BV1test000001", bvids)


class AiSentimentApiTests(ApiContractTestBase):
    """AI 情感分析接口测试。"""

    def test_analyze_single_text(self):
        """单条分析应返回分值、标签与情绪标签。"""
        response = self.client.post(
            "/api/ai/analyze-sentiment/",
            data={"text": "太强了！"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertIn("score", data)
        self.assertIn("label", data)
        self.assertIn("emotion_tags", data)
        self.assertEqual(data["label"], "positive")

    def test_analyze_batch(self):
        """批量分析应返回等长结果列表。"""
        response = self.client.post(
            "/api/ai/analyze-sentiment/",
            data={"texts": ["太强了", "有点失望", "打卡"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["count"], 3)

    def test_analyze_requires_input(self):
        """既不传 text 也不传 texts 应返回参数错误。"""
        response = self.client.post(
            "/api/ai/analyze-sentiment/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_analyze_batch_size_limited(self):
        """超过批量上限应被拒绝，避免被当作 DoS 通道。"""
        response = self.client.post(
            "/api/ai/analyze-sentiment/",
            data={"texts": ["测试"] * 500},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_sentiment_health(self):
        """健康检查应返回后端名称与可用状态。"""
        data = self.client.get("/api/ai/sentiment-health/").json()["data"]
        self.assertIn("backend", data)
        self.assertIn("available", data)


# ===========================================================================
# 数据来源标记（is_demo）
# ===========================================================================
class DataSourceTests(TestCase):
    """数据来源标记的接口契约测试。

    【为什么需要这些测试】
    模拟数据的 bvid 是虚构的，在B站无法访问。
    若接口不返回来源标记，前端就无法区分真假，
    会给用户展示点不通的链接——这比不展示更糟。
    """

    @classmethod
    def setUpTestData(cls):
        """构造真实与模拟各一条数据。"""
        from apps.videos.models import Video

        cls.real = Video.objects.create(
            bvid="BV1real000001",
            title="真实抓取视频",
            view_count=1000,
            duration=100,
            is_demo=False,
        )
        cls.demo = Video.objects.create(
            bvid="BV1demo000001",
            title="模拟数据视频",
            view_count=2000,
            duration=200,
            is_demo=True,
        )

    def setUp(self):
        """清统计缓存，避免跨测试污染。"""
        from apps.analytics.services import clear_analytics_cache

        clear_analytics_cache()

    def test_list_exposes_source_fields(self):
        """列表接口应返回来源相关字段。"""
        results = self.client.get("/api/videos/").json()["data"]["results"]
        self.assertTrue(results)

        for key in ("is_demo", "data_source", "source_url"):
            self.assertIn(key, results[0], f"列表接口缺少字段 {key}")

    def test_real_video_marked_as_real(self):
        """真实抓取的数据应标记为 real。"""
        detail = self.client.get("/api/videos/BV1real000001/").json()
        self.assertFalse(detail["is_demo"])
        self.assertEqual(detail["data_source"], "real")

    def test_demo_video_marked_as_demo(self):
        """模拟数据应标记为 demo。"""
        detail = self.client.get("/api/videos/BV1demo000001/").json()
        self.assertTrue(detail["is_demo"])
        self.assertEqual(detail["data_source"], "demo")

    def test_source_url_format(self):
        """source_url 应是合法的B站地址。"""
        detail = self.client.get("/api/videos/BV1real000001/").json()
        self.assertEqual(
            detail["source_url"],
            "https://www.bilibili.com/video/BV1real000001",
        )

    def test_analytics_top_videos_exposes_source(self):
        """排行榜接口也应返回来源字段（看板热榜需要）。"""
        items = self.client.get("/api/analytics/top-videos/").json()["data"]["items"]
        self.assertTrue(items)

        for key in ("is_demo", "data_source", "source_url"):
            self.assertIn(key, items[0], f"排行榜缺少字段 {key}")

    def test_interaction_analytics_exposes_source(self):
        """互动质量分析也应返回来源字段。"""
        # 需要播放量 ≥1000 才进榜
        data = self.client.get("/api/analytics/interaction/").json()["data"]
        self.assertTrue(data["top_interaction"])
        self.assertIn("is_demo", data["top_interaction"][0])
        self.assertIn("source_url", data["top_interaction"][0])


class DeterministicBvidTests(TestCase):
    """模拟数据 bvid 的确定性测试。

    【为什么这个测试很重要】
    bvid 若每次重建都变化，前端缓存的旧链接就会 404，
    表现为"点视频详情后弹回列表"——一个很难定位的 bug。
    这里把这个约定固化下来。
    """

    def test_bvid_stable_across_calls(self):
        """同一索引生成的 bvid 必须完全一致。"""
        from apps.spider.management.commands.seed_demo import _deterministic_bvid

        first = _deterministic_bvid(0, set())
        second = _deterministic_bvid(0, set())
        self.assertEqual(first, second, "同一索引应生成相同的 bvid")

    def test_different_index_different_bvid(self):
        """不同索引应生成不同的 bvid。"""
        from apps.spider.management.commands.seed_demo import _deterministic_bvid

        used = set()
        bvids = [_deterministic_bvid(i, used) for i in range(50)]
        self.assertEqual(len(set(bvids)), 50, "50 个索引应产生 50 个不同的 bvid")

    def test_bvid_format_valid(self):
        """bvid 格式应接近真实（BV1 + 9 位字符，不含易混淆字符）。"""
        import re

        from apps.spider.management.commands.seed_demo import _deterministic_bvid

        for i in range(20):
            bvid = _deterministic_bvid(i, set())
            self.assertRegex(bvid, r"^BV1[a-z1-9]{9}$", f"bvid 格式不合规：{bvid}")
            # 不应包含易混淆字符
            for ch in "0OlI":
                self.assertNotIn(ch, bvid, f"bvid 含易混淆字符 {ch}：{bvid}")

    def test_collision_avoids_used(self):
        """bvid 冲突时应自动换一个（用于极端哈希碰撞）。"""
        from apps.spider.management.commands.seed_demo import _deterministic_bvid

        first = _deterministic_bvid(0, set())
        # 把首次结果放进 used，再取一次应得到不同的值
        second = _deterministic_bvid(0, {first})
        self.assertNotEqual(first, second, "冲突时应换用其他 bvid")
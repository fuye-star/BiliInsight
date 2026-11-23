# -*- coding: utf-8 -*-
"""
analytics 应用的服务层测试。

【测试重点】
统计函数的正确性无法靠"看接口有没有报错"来验证——
数字算错了接口一样返回 200。因此这里构造**已知答案的小数据集**，
逐个断言统计结果。

数据设计（便于手算）：
    3 个分区，3 个 UP主，6 个视频，6 条弹幕
    播放量分别为 100 / 200 / 300 / 400 / 500 / 600，总和 2100

运行：
    python manage.py test apps.analytics -v 2
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.videos.models import Danmaku, Partition, UpUser, Video

from . import services


class AnalyticsServiceTestBase(TestCase):
    """构造供各测试复用的确定数据集。"""

    def setUp(self):
        """每个测试方法前清空统计缓存。

        【为什么必须清缓存】
        统计函数会把结果写入 Redis（有效期 5-10 分钟），
        而 Redis 在多个测试方法之间是共享的、不会被 TestCase 自动回滚。
        结果就是：某个测试删除了数据，但后续测试仍读到上一个测试
        缓存的旧结果，造成"删了数据却仍然统计出 6 条视频"的假失败。

        这里在每个测试前清缓存，保证测试彼此隔离。
        """
        services.clear_analytics_cache()

    @classmethod
    def setUpTestData(cls):
        """创建固定的测试数据（整个测试类只执行一次，提升速度）。"""
        now = timezone.now()

        # 三个分区
        cls.p_tech = Partition.objects.create(name="科技", bili_tid=188, color="#5470C6")
        cls.p_game = Partition.objects.create(name="游戏", bili_tid=4, color="#91CC75")
        cls.p_life = Partition.objects.create(name="生活", bili_tid=160, color="#FAC858")

        # 两个 UP主
        cls.up_a = UpUser.objects.create(mid=1001, name="UP甲", follower_count=5000)
        cls.up_b = UpUser.objects.create(mid=1002, name="UP乙", follower_count=100)

        # 六个视频：播放量 100 递增到 600，便于手算总和
        cls.videos = []
        views = [100, 200, 300, 400, 500, 600]
        partitions = [cls.p_tech, cls.p_tech, cls.p_game, cls.p_game, cls.p_life, cls.p_life]
        upusers = [cls.up_a, cls.up_a, cls.up_b, cls.up_b, cls.up_a, cls.up_b]

        for i, (view, part, up) in enumerate(zip(views, partitions, upusers), start=1):
            like = view // 10          # 点赞恒为播放的 1/10
            video = Video.objects.create(
                bvid=f"BVtest{i:06d}",
                aid=1000 + i,
                title=f"测试视频{i}",
                description=f"第{i}个测试视频的简介",
                tags=f"{part.name},测试",
                partition=part,
                upuser=up,
                view_count=view,
                like_count=like,
                coin_count=0,
                favorite_count=0,
                interaction_rate=round(like / view, 6),
                duration=600,
                # 发布时间：i 天前（保证按天分组时落在不同天）
                pubdate=now - timedelta(days=i),
            )
            cls.videos.append(video)

        # 六条弹幕：2 正向、2 中性、2 负向，分布在视频进度 0%~100%
        cls.danmakus = []
        for i, video in enumerate(cls.videos):
            for j in range(2):
                if j == 0:
                    label, score, content = "positive", 0.9, "太强了"
                else:
                    label, score, content = "negative", 0.1, "有点失望"
                cls.danmakus.append(
                    Danmaku.objects.create(
                        video=video,
                        dmid=10000 + i * 10 + j,
                        content=content,
                        video_time=video.duration * (i / 6),   # 铺开进度
                        sentiment_score=score,
                        sentiment_label=label,
                        emotion_tags="高燃" if label == "positive" else "失望",
                    )
                )


class OverviewTests(AnalyticsServiceTestBase):
    """总览统计测试。"""

    def test_overview_counts(self):
        """各类计数应准确。"""
        data = services.get_overview()
        self.assertEqual(data["video_count"], 6)
        self.assertEqual(data["upuser_count"], 2)
        self.assertEqual(data["partition_count"], 3)
        self.assertEqual(data["danmaku_count"], 12)

    def test_overview_sums(self):
        """播放量总和应为 100+200+300+400+500+600 = 2100。"""
        data = services.get_overview()
        self.assertEqual(data["total_view"], 2100)
        # 平均播放 2100/6 = 350
        self.assertAlmostEqual(data["avg_view"], 350.0, places=1)

    def test_overview_empty_database(self):
        """空库时应返回零值而不是报错。"""
        Video.objects.all().delete()
        Danmaku.objects.all().delete()
        UpUser.objects.all().delete()
        Partition.objects.all().delete()

        data = services.get_overview()
        self.assertEqual(data["video_count"], 0)
        self.assertEqual(data["total_view"], 0)
        self.assertIsNone(data["latest_pubdate"])
        # 空库时占比应为 0 而不是除零错误
        self.assertEqual(data["real_videos"], 0)
        self.assertEqual(data["demo_videos"], 0)
        self.assertEqual(data["real_ratio"], 0.0)

    def test_overview_data_source_breakdown(self):
        """总览应给出全库准确的真实/模拟构成。

        【为什么要测这个】
            前端曾用"榜单前 10 条"估算数据来源比例，导致抓回真实数据后
            榜单恰好全是真实的，提示条整个消失，而库里其实还有大量模拟数据。
            改由总览提供全库计数后，这里锁定该契约不被改回去。
        """
        data = services.get_overview()
        # setUpTestData 创建的视频未指定 is_demo，默认 False，即全部真实
        self.assertEqual(data["real_videos"], 6)
        self.assertEqual(data["demo_videos"], 0)
        self.assertEqual(data["real_ratio"], 1.0)

        # 把其中 2 条标记为模拟数据，计数与占比应同步变化
        Video.objects.filter(bvid__in=["BVtest000001", "BVtest000002"]).update(
            is_demo=True
        )
        services.clear_analytics_cache()

        data = services.get_overview()
        self.assertEqual(data["real_videos"], 4)
        self.assertEqual(data["demo_videos"], 2)
        # 4/6 = 0.6667
        self.assertAlmostEqual(data["real_ratio"], 0.6667, places=4)


class TrendTests(AnalyticsServiceTestBase):
    """趋势统计测试。"""

    def test_trend_returns_points(self):
        """应返回按天聚合的数据点。"""
        data = services.get_trend(days=30)
        self.assertGreater(len(data["points"]), 0)
        self.assertEqual(data["days"], 30)

        # 每个点都应包含必要字段
        point = data["points"][0]
        for key in ("date", "video_count", "view_sum", "avg_view"):
            self.assertIn(key, point)

    def test_trend_sum_matches_total(self):
        """趋势各天播放量之和应等于视频播放量总和。"""
        data = services.get_trend(days=30)
        total = sum(p["view_sum"] for p in data["points"])
        self.assertEqual(total, 2100)

    def test_trend_partition_filter(self):
        """按分区筛选后只统计该分区的视频。

        科技区两个视频：100 + 200 = 300
        """
        data = services.get_trend(days=30, partition="科技")
        total = sum(p["view_sum"] for p in data["points"])
        self.assertEqual(total, 300)

    def test_trend_days_clamped(self):
        """days 参数应被夹到合法范围。"""
        self.assertEqual(services.get_trend(days=0)["days"], 1)
        self.assertEqual(services.get_trend(days=9999)["days"], 365)


class PartitionRatioTests(AnalyticsServiceTestBase):
    """分区占比测试。"""

    def test_ratio_totals(self):
        """总视频数应为 6。"""
        data = services.get_partition_ratio()
        self.assertEqual(data["total_videos"], 6)
        self.assertEqual(data["total_views"], 2100)

    def test_ratio_percentages_sum_to_100(self):
        """各分区视频数占比之和应为 100%（浮点误差内）。

        三个分区各 2 个视频，各占 33.33%。
        """
        data = services.get_partition_ratio()
        total_pct = sum(item["video_pct"] for item in data["items"])
        self.assertAlmostEqual(total_pct, 100.0, places=1)

    def test_ratio_sorted_by_views(self):
        """结果应按播放量倒序，便于前端直接渲染。"""
        data = services.get_partition_ratio()
        views = [item["view_sum"] for item in data["items"]]
        self.assertEqual(views, sorted(views, reverse=True))


class TopUpusersTests(AnalyticsServiceTestBase):
    """UP主排行榜测试。"""

    def test_top_upusers_default_order(self):
        """默认按总播放量倒序。

        UP甲 有视频 100+200+500 = 800
        UP乙 有视频 300+400+600 = 1300
        因此 UP乙 应排第一。
        """
        data = services.get_top_upusers(limit=10)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["name"], "UP乙")
        self.assertEqual(data["items"][0]["view_sum"], 1300)
        self.assertEqual(data["items"][1]["view_sum"], 800)

    def test_top_upusers_order_by_follower(self):
        """按粉丝数排序时应以 UP甲（5000 粉）为首。"""
        data = services.get_top_upusers(limit=10, order_by="follower_count")
        self.assertEqual(data["items"][0]["name"], "UP甲")

    def test_invalid_order_by_falls_back(self):
        """非法排序字段应回退到默认值，而不是抛异常或注入 SQL。"""
        data = services.get_top_upusers(order_by="; DROP TABLE videos_video; --")
        self.assertEqual(data["order_by"], "view_sum")

    def test_limit_clamped(self):
        """limit 超范围应被夹取。"""
        data = services.get_top_upusers(limit=99999)
        self.assertLessEqual(len(data["items"]), 100)


class TopVideosTests(AnalyticsServiceTestBase):
    """视频排行榜测试。"""

    def test_top_videos_by_view(self):
        """按播放量倒序，第一名应是 600 播放的视频。"""
        data = services.get_top_videos(limit=3)
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(data["items"][0]["view_count"], 600)
        self.assertEqual(data["items"][1]["view_count"], 500)
        self.assertEqual(data["items"][2]["view_count"], 400)

    def test_top_videos_partition_filter(self):
        """分区筛选后只返回该分区视频。"""
        data = services.get_top_videos(limit=10, partition="游戏")
        self.assertEqual(len(data["items"]), 2)
        for item in data["items"]:
            self.assertEqual(item["partition"], "游戏")

    def test_video_item_has_display_fields(self):
        """返回项应含前端需要的展示字段（时长格式化、UP主名等）。"""
        item = services.get_top_videos(limit=1)["items"][0]
        for key in ("bvid", "title", "duration_display", "partition", "up_name"):
            self.assertIn(key, item)
        # 600 秒应格式化为 10:00
        self.assertEqual(item["duration_display"], "10:00")


class WordCloudTests(AnalyticsServiceTestBase):
    """词云统计测试。"""

    def test_wordcloud_from_danmaku(self):
        """弹幕词云应统计出高频词。

        测试数据里弹幕只有两种内容："太强了" 与 "有点失望"，
        各出现 6 次，因此 "太强" 或 "太强了" 应出现在结果中。
        """
        data = services.get_wordcloud(source="danmaku", limit=50)
        self.assertGreater(data["total_words"], 0)
        self.assertGreater(len(data["items"]), 0)

        names = [item["name"] for item in data["items"]]
        # jieba 可能把"太强了"切成"太强"+"了"，两种都接受
        self.assertTrue(
            any("太强" in n for n in names),
            f"未找到「太强」相关词，实际词表：{names[:10]}",
        )

    def test_wordcloud_weight_normalized(self):
        """最高频词的权重应为 100，其余不超过 100。"""
        data = services.get_wordcloud(source="danmaku", limit=50)
        weights = [item["weight"] for item in data["items"]]
        self.assertAlmostEqual(max(weights), 100.0, places=1)
        self.assertTrue(all(w <= 100.0 for w in weights))

    def test_wordcloud_from_titles(self):
        """标题词云应基于视频标题与标签。"""
        data = services.get_wordcloud(source="title", limit=50)
        self.assertGreater(data["total_words"], 0)

    def test_wordcloud_filters_stopwords(self):
        """停用词不应出现在结果中。"""
        data = services.get_wordcloud(source="danmaku", limit=200)
        names = {item["name"] for item in data["items"]}
        # "的""了"在停用词表中
        self.assertNotIn("的", names)
        self.assertNotIn("了", names)

    def test_wordcloud_empty_source(self):
        """无数据时返回空结果而不是报错。"""
        Danmaku.objects.all().delete()
        data = services.get_wordcloud(source="danmaku")
        self.assertEqual(data["total_words"], 0)
        self.assertEqual(data["items"], [])


class SentimentStatsTests(AnalyticsServiceTestBase):
    """情感统计测试。"""

    def test_sentiment_distribution(self):
        """12 条弹幕中 6 正向 6 负向，各占 50%。"""
        data = services.get_sentiment_stats()
        self.assertEqual(data["total"], 12)
        self.assertEqual(data["analyzed"], 12)

        dist = {item["label"]: item for item in data["distribution"]}
        self.assertEqual(dist["positive"]["count"], 6)
        self.assertEqual(dist["negative"]["count"], 6)
        self.assertAlmostEqual(dist["positive"]["pct"], 50.0, places=1)

    def test_sentiment_curve_segments(self):
        """波动曲线应返回指定段数，且每段都有标签。"""
        data = services.get_sentiment_stats(segment_count=10)
        self.assertEqual(len(data["curve"]), 10)
        self.assertEqual(data["curve"][0]["label"], "0-10%")
        self.assertEqual(data["curve"][-1]["label"], "90-100%")

    def test_sentiment_histogram(self):
        """分值直方图应有 10 个区间，且总数等于已分析条数。"""
        data = services.get_sentiment_stats()
        self.assertEqual(len(data["score_histogram"]), 10)
        total = sum(b["count"] for b in data["score_histogram"])
        self.assertEqual(total, 12)

    def test_sentiment_filter_by_bvid(self):
        """按视频筛选后只统计该视频的弹幕（每个视频 2 条）。"""
        bvid = self.videos[0].bvid
        data = services.get_sentiment_stats(bvid=bvid)
        self.assertEqual(data["total"], 2)

    def test_sentiment_empty(self):
        """无弹幕时应返回零值结构。"""
        Danmaku.objects.all().delete()
        data = services.get_sentiment_stats()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["distribution"], [])


class InteractionAnalysisTests(AnalyticsServiceTestBase):
    """互动质量分析测试。"""

    def test_interaction_analysis_structure(self):
        """应返回互动率榜、分区对比与高互动数。"""
        data = services.get_interaction_analysis(limit=5)
        self.assertIn("top_interaction", data)
        self.assertIn("partition_interaction", data)
        self.assertIn("high_quality_count", data)

    def test_top_interaction_sorted(self):
        """互动率榜应按互动率倒序。

        测试数据里互动率恒为 0.1（点赞=播放/10），因此只验证排序不逆序。
        """
        data = services.get_interaction_analysis(limit=6)
        rates = [item["interaction_rate"] for item in data["top_interaction"]]
        self.assertEqual(rates, sorted(rates, reverse=True))

    def test_low_view_videos_excluded(self):
        """播放量低于 1000 的视频应被排除，避免互动率虚高。

        测试数据播放量都小于 1000，因此榜应为空。
        """
        data = services.get_interaction_analysis(limit=5)
        self.assertEqual(len(data["top_interaction"]), 0)


class CacheTests(AnalyticsServiceTestBase):
    """缓存行为测试。"""

    def test_cache_returns_same_result(self):
        """连续两次调用应返回一致结果（第二次走缓存）。"""
        first = services.get_overview()
        second = services.get_overview()
        self.assertEqual(first, second)

    def test_clear_cache_does_not_raise(self):
        """清理缓存不应抛异常（后端可能不支持 delete_pattern）。"""
        services.get_overview()
        # 只要不抛异常即可
        services.clear_analytics_cache()

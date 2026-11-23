# -*- coding: utf-8 -*-
"""桌面版交付相关能力的测试。

覆盖三块"只在桌面形态下才会走到的代码"：

    ① 抓取接口（POST /api/spider/crawl/）
       —— 桌面版「更新数据」按钮的后端

    ② 缓存清理的 LocMemCache 兜底
       —— 桌面版没有 Redis，原实现会静默返回 0（一个键都没删）

    ③ SPA 托管
       —— 前端构建产物由 Django 直接托管，刷新 /videos 不能 404

【为什么这些必须单独测】
    桌面形态和开发形态用的是**不同的配置**（SQLite vs MySQL、
    LocMemCache vs Redis、同步 vs Celery）。开发环境下测试全绿，
    不代表打包后能跑 —— 这几处正是"换配置就会坏"的地方。
"""

import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.common.response import BusinessCode
from apps.spider.base import CrawlStats, RateLimitedError


class CrawlNowViewTests(TestCase):
    """抓取接口的行为测试（网络请求全部用桩替代）。

    【这个接口后来改过一次默认行为，测试也跟着调整】
        最初它抓"分区排行榜"，结果有两个硬伤：
          · 排行榜每次都是同一批 Top 100 → 再点"新增 0 条"，像坏了
          · 排行榜风控最严 → 点一次就被 -352，之后每次都失败

        现在默认走"全站热门"并维护翻页游标。因此下面同时覆盖
        两种来源（popular / partition），避免以后改动时漏掉一边。
    """

    def setUp(self):
        """清掉翻页游标，避免测试之间互相影响。"""
        from django.core.cache import cache

        cache.delete("spider:popular_cursor")

    def _post(self, payload=None):
        """调用抓取接口。

        【为什么默认带 pages=1】
            后端在"新视频不足 20 条"时会继续读下一页（跳过已收录的页）。
            测试里希望每次调用只读一页，否则桩函数会被多消费几次，
            导致 StopIteration 或读到意料之外的页码。
            多页跳过的行为另有专门测试覆盖。
        """
        from rest_framework.test import APIClient

        body = {"limit": 40, "pages": 1}
        if payload:
            body.update(payload)
        return APIClient().post("/api/spider/crawl/", body, format="json")

    @staticmethod
    def _popular_stats(created=5, updated=3, fetched=50, last_page=3, requests=1):
        """构造一份 popular 抓取的统计结果。"""
        stats = CrawlStats(
            fetched=fetched, created=created, updated=updated, failed=0
        )
        stats.last_page = last_page
        return stats

    # ---- 默认来源：popular ----
    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_default_source_is_popular(self, mock_spider_cls, _mock_index):
        """不传 source 时应走全站热门，而不是分区排行榜。

        这条锁住"默认用哪个接口"这个关键决策：
        用排行榜会既拿不到新数据、又极易被风控。
        """
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_popular.side_effect = [self._popular_stats()]

        response = self._post()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(spider.run_popular.called, "默认应调用热门抓取")
        self.assertFalse(spider.run_partition.called, "默认不应调用分区排行榜")
        self.assertEqual(response.data["data"]["source"], "popular")

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_cursor_advances_between_clicks(self, mock_spider_cls, _mock_index):
        """连续点击时页码游标应往后推进，第二次从下一页开始。

        【为什么重要】
            如果每次都从第 1 页抓，而这些视频早已入库，
            结果永远是"新增 0 条"，使用者会以为按钮失效。
            游标推进才能保证每次点击都拿到新内容。
        """
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        # 第一次读第 5 页（last_page=5），第二次读第 6 页
        spider.run_popular.side_effect = [
            self._popular_stats(created=10, last_page=5),
            self._popular_stats(created=12, last_page=6),
        ]

        first = self._post()
        second = self._post()

        first_start = spider.run_popular.call_args_list[0].kwargs.get("start_page")
        second_start = spider.run_popular.call_args_list[1].kwargs.get("start_page")

        # 初始页是 5（预置数据已覆盖前几页，从第 5 页起步能少读些已收录内容）
        self.assertEqual(first_start, 5, "第一次应从初始页（第 5 页）开始")
        self.assertEqual(second_start, 6, "第二次应从上一次的下一页开始")
        self.assertEqual(first.data["data"]["next_page"], 6)
        self.assertEqual(second.data["data"]["next_page"], 7)

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_no_new_video_message_is_friendly(self, mock_spider_cls, _mock_index):
        """没有新增时应解释"为什么"，并提示可以再点一次。

        不能只说"抓取完成：新增 0 条" —— 使用者会以为功能坏了。
        """
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_popular.side_effect = [self._popular_stats(created=0, updated=50)]

        response = self._post()

        message = response.data["message"]
        self.assertIn("没有新视频", message)
        self.assertIn("再点", message)

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_reports_real_request_count(self, mock_spider_cls, _mock_index):
        """必须报告真实的 HTTP 请求次数（不是局部统计里的 0）。"""
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=3)
        spider.run_popular.side_effect = [
            self._popular_stats(created=25, last_page=2)
        ]

        response = self._post()

        self.assertEqual(response.data["data"]["requests"], 3)
        self.assertEqual(response.data["data"]["pages_read"], 1)

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_skips_pages_without_new_videos(self, mock_spider_cls, _mock_index):
        """某一页没有新视频时应自动读下一页，直到凑够目标条数。

        【这是本次修复的核心逻辑】
            热门榜第 1 页的内容通常早已入库（新增 0 条）。
            如果读一页就返回，使用者会看到"新增 0 条"，又以为按钮坏了。
            因此后端会继续往后翻，直到新增条数达到界面上填的"条数"。

            实测：第 1 页只有 3 条新的，第 6/8/12 页几乎全新。
        """
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=2)
        spider.run_popular.side_effect = [
            self._popular_stats(created=0, updated=50, last_page=1),   # 已收录
            self._popular_stats(created=25, updated=5, last_page=6),   # 有新内容
        ]

        # 目标 20 条，第二页给了 25 条 -> 达标即停，不用读第三页
        response = self._post({"limit": 20, "pages": 6})

        self.assertEqual(
            spider.run_popular.call_count, 2, "第一页没新内容时应继续读第二页"
        )
        data = response.data["data"]
        self.assertEqual(data["pages_read"], 2)
        self.assertEqual(data["created"], 25)
        self.assertEqual(data["next_page"], 7)

    # ---- 显式指定分区 ----
    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_partition_source_uses_ranking(self, mock_spider_cls, _mock_index):
        """显式传 source=partition 时才走排行榜。"""
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_partition.return_value = CrawlStats(fetched=97, created=3, updated=2)

        response = self._post(
            {"source": "partition", "partition": "科技", "limit": 10}
        )

        self.assertTrue(spider.run_partition.called)
        self.assertFalse(spider.run_popular.called)
        self.assertEqual(response.data["data"]["source"], "partition")

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_illegal_partition_falls_back(self, mock_spider_cls, _mock_index):
        """分区名非法时回退到默认分区，而不是抛异常。"""
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_partition.return_value = CrawlStats(fetched=1, created=1)

        response = self._post(
            {"source": "partition", "partition": "不存在的分区", "limit": 5}
        )

        self.assertEqual(response.status_code, 200)
        called_partition = spider.run_partition.call_args.args[0]
        self.assertIn(called_partition, ("科技", "数码", "动画", "游戏", "知识"))

    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_limit_is_clamped(self, mock_spider_cls, _mock_index):
        """limit 超出范围时应被夹取，避免一次请求抓太多。"""
        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_partition.return_value = CrawlStats(fetched=1, created=1)

        self._post({"source": "partition", "partition": "科技", "limit": 9999})

        limit = spider.run_partition.call_args.kwargs.get("limit")
        self.assertEqual(limit, 200, "limit 上限应为 200")

    # ---- 缓存 ----
    @patch("apps.spider.views._rebuild_index_if_needed", return_value=0)
    @patch("apps.spider.views.BiliBiliSpider")
    def test_clears_analytics_cache(self, mock_spider_cls, _mock_index):
        """抓完必须清空分析缓存。

        不清的话：视频列表（无缓存）立刻变新，
        但总览/排行榜还缓存着旧数字，用户会以为"只同步了一半"。
        """
        from django.core.cache import cache

        spider = mock_spider_cls.return_value
        spider.stats = CrawlStats(requests=1)
        spider.run_popular.side_effect = [self._popular_stats(created=5)]

        cache.set("analytics:overview", {"video_count": 999}, 300)

        response = self._post()

        self.assertGreaterEqual(
            response.data["data"]["cleared_cache"], 1, "应当清理掉缓存的统计键"
        )
        self.assertIsNone(cache.get("analytics:overview"), "旧缓存应已被清除")

    # ---- 风控 ----
    @patch("apps.spider.views.BiliBiliSpider")
    def test_rate_limit_returns_business_error(self, mock_spider_cls):
        """被风控时应返回明确的业务错误码，而不是 500。"""
        spider = mock_spider_cls.return_value
        spider.run_popular.side_effect = RateLimitedError("接口返回 -352")

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], BusinessCode.CRAWL_RATE_LIMITED)
        # 提示里要告诉使用者"等一会儿"，而不是让他继续点
        self.assertIn("风控", response.data["message"])


class EnrichGuardTests(TestCase):
    """后台补全任务的自我保护。

    【真实踩到的坑】
        弹幕接口被风控时，`run_danmaku` 内部只记日志、然后**正常返回**
        （这是有意的：单包失败不该让整个视频失败）。但调用方看不出"被拦了"，
        于是继续循环，对剩下的几百个视频各发一次注定失败的请求 ——
        既拿不到数据，又不断延长风控。

        实测：389 个待抓视频，日志里连续几十条限流警告，程序还在往下跑。
        因此加了"连续 3 个视频一条弹幕都没拿到就判定为限流并停止"。
    """

    def setUp(self):
        from apps.spider.views import _ENRICH_STATE

        _ENRICH_STATE.update(
            running=False, message="", stage="", total=0, done=0,
            followers=0, danmaku=0, error="",
        )

    def tearDown(self):
        from apps.spider.views import _ENRICH_STATE

        _ENRICH_STATE.update(running=False, message="", stage="")

    def test_stops_after_consecutive_empty_danmaku(self):
        """连续 3 个视频都拿不到弹幕时应停止，而不是继续磨完所有视频。"""
        from apps.spider.views import _ENRICH_STATE, _run_enrich
        from apps.videos.models import Danmaku, Video

        # 准备 6 个没有弹幕的视频
        Video.objects.all().delete()
        Danmaku.objects.all().delete()
        for i in range(6):
            Video.objects.create(
                bvid=f"BVguard{i:05d}",
                title=f"测试视频{i}",
                view_count=1000,
                like_count=10,
                is_demo=False,
            )

        with patch("apps.spider.views.BiliBiliSpider") as mock_cls, patch(
            "apps.spider.views.clear_analytics_cache", return_value=0
        ), patch("apps.spider.views._rebuild_index_if_needed", return_value=0), patch(
            "apps.spider.views.connection"
        ):
            # 说明：_run_enrich 收尾会 connection.close()（长跑线程要回收连接）。
            # 但 TestCase 把每个用例包在事务里，中途关连接会破坏事务，
            # 抛 TransactionManagementError。这里把它 mock 掉即可。
            spider = mock_cls.return_value
            spider.run_upuser_followers.return_value = CrawlStats()
            # 模拟"每次都被限流"：返回成功但不写库
            spider.run_danmaku.return_value = CrawlStats(fetched=0, created=0)

            _run_enrich(followers_limit=0, danmaku_limit=5)

        self.assertEqual(
            spider.run_danmaku.call_count,
            3,
            "连续 3 个视频空手就应判定为限流并停止",
        )
        self.assertFalse(_ENRICH_STATE["running"], "任务应已结束")
        self.assertIn("风控", _ENRICH_STATE["message"])

    def test_reports_partial_result_honestly(self):
        """被风控提前停止时，文案不能伪装成"全部完成"。"""
        from apps.spider.views import _ENRICH_STATE, _run_enrich
        from apps.videos.models import Danmaku, Video

        Video.objects.all().delete()
        Danmaku.objects.all().delete()
        for i in range(4):
            Video.objects.create(
                bvid=f"BVhonest{i:04d}",
                title=f"视频{i}",
                view_count=100,
                like_count=1,
                is_demo=False,
            )

        with patch("apps.spider.views.BiliBiliSpider") as mock_cls, patch(
            "apps.spider.views.clear_analytics_cache", return_value=0
        ), patch("apps.spider.views._rebuild_index_if_needed", return_value=0), patch(
            "apps.spider.views.connection"
        ):
            spider = mock_cls.return_value
            spider.run_upuser_followers.return_value = CrawlStats()
            spider.run_danmaku.return_value = CrawlStats(fetched=0, created=0)

            _run_enrich(followers_limit=0, danmaku_limit=3)

        self.assertIn("提前停止", _ENRICH_STATE["message"])
        self.assertNotIn("补全完成", _ENRICH_STATE["message"])


class LocMemCacheFallbackTests(SimpleTestCase):
    """内存缓存后端下的按键模式删除。"""

    def test_delete_pattern_works_on_locmem(self):
        """LocMemCache 也应支持按模式删除（桌面版没有 Redis）。"""
        from django.core.cache.backends.locmem import LocMemCache

        from apps.common.cache_utils import delete_pattern

        fake = LocMemCache("test-locmem-fallback", {})

        with patch("apps.common.cache_utils.cache", fake):
            fake.set("analytics:overview", 1)
            fake.set("analytics:top_videos", 2)
            fake.set("sentiment:all:20", 3)
            fake.set("unrelated:key", 4)

            deleted = delete_pattern("analytics:*")

            self.assertEqual(deleted, 2, "应删掉两个 analytics 开头的键")
            self.assertIsNone(fake.get("analytics:overview"))
            self.assertIsNone(fake.get("analytics:top_videos"))
            self.assertIsNotNone(fake.get("sentiment:all:20"), "不匹配的键不能删")
            self.assertIsNotNone(fake.get("unrelated:key"), "不匹配的键不能删")

    def test_delete_pattern_returns_zero_when_no_match(self):
        """没有匹配键时返回 0，不应报错。"""
        from django.core.cache.backends.locmem import LocMemCache

        from apps.common.cache_utils import delete_pattern

        fake = LocMemCache("test-locmem-empty", {})
        with patch("apps.common.cache_utils.cache", fake):
            self.assertEqual(delete_pattern("analytics:*"), 0)


class SpaServingTests(SimpleTestCase):
    """前端产物托管测试。"""

    def setUp(self):
        """在项目内创建临时 dist 目录（不写到系统临时目录）。"""
        base = Path(__file__).resolve().parent.parent.parent / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.dist = base / f"_test_spa_{uuid.uuid4().hex[:8]}"
        (self.dist / "assets").mkdir(parents=True, exist_ok=True)

        (self.dist / "index.html").write_text(
            '<!DOCTYPE html><html><body><div id="app"></div></body></html>',
            encoding="utf-8",
        )
        (self.dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

        self.factory = RequestFactory()

    def tearDown(self):
        """清理临时目录。"""
        shutil.rmtree(self.dist, ignore_errors=True)

    def test_root_returns_index(self):
        """/ 返回 index.html。"""
        from apps.common.spa import serve_spa

        with override_settings(FRONTEND_DIST=str(self.dist)):
            response = serve_spa(self.factory.get("/"), path="")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<div id="app">', b"".join(response.streaming_content))

    def test_asset_returns_real_file(self):
        """/assets/app.js 应返回真实文件而不是 index.html。

        这条很关键：如果把静态资源也回退成 index.html，
        浏览器会把 HTML 当 JS 执行，页面直接白屏。
        """
        from apps.common.spa import serve_spa

        with override_settings(FRONTEND_DIST=str(self.dist)):
            response = serve_spa(self.factory.get("/assets/app.js"), path="assets/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"console.log(1)")

    def test_client_route_falls_back_to_index(self):
        """前端路由（如 /videos）刷新时应回退到 index.html，不能 404。"""
        from apps.common.spa import serve_spa

        with override_settings(FRONTEND_DIST=str(self.dist)):
            response = serve_spa(self.factory.get("/videos"), path="videos")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<div id="app">', b"".join(response.streaming_content))

    def test_missing_dist_raises_404(self):
        """未配置前端产物时应明确报 404，而不是静默返回空页面。"""
        from django.http import Http404

        from apps.common.spa import serve_spa

        with override_settings(FRONTEND_DIST=str(self.dist / "not-exist")):
            with self.assertRaises(Http404):
                serve_spa(self.factory.get("/"), path="")

    def test_path_traversal_is_rejected(self):
        """`../` 之类的路径穿越必须被拦住。"""
        from apps.common.spa import serve_spa

        with override_settings(FRONTEND_DIST=str(self.dist)):
            # safe_join 会抛异常 -> 视图回退到 index.html，绝不能读到外部文件
            response = serve_spa(self.factory.get("/../secret"), path="../secret")

        body = b"".join(response.streaming_content)
        self.assertIn(b'<div id="app">', body, "路径穿越应被拦截并回退到 index.html")

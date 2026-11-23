# -*- coding: utf-8 -*-
"""
BaseSpider 行为的单元测试。

【为什么这些测试不需要联网】
BaseSpider 的所有 HTTP 行为都通过 self.session，因此可以用一个
假的 session 对象替换它，从而精确控制返回内容，
验证限速、重试、风控识别等逻辑——不必真的发请求。

运行：
    python manage.py test apps.spider.tests_base -v 2
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.spider.base import BaseSpider, CrawlStats, RateLimitedError, SpiderError


class DummySpider(BaseSpider):
    """用于测试的最小实现。"""

    name = "dummy"
    base_url = "https://example.com"

    def run(self, *args, **kwargs):
        """满足抽象接口即可，测试中不会调用。"""
        return self.stats


def make_response(json_data=None, status_code=200, content=b""):
    """构造一个假的 requests.Response。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    if json_data is not None:
        resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class RateLimitCodeTests(SimpleTestCase):
    """风控业务码识别测试。

    【为什么必须区分风控码】
    B站的风控（-352/-412/-509/-799）会随请求次数升级封禁。
    如果把风控码当普通错误重试，只会让封禁时间变长。
    因此必须识别为 RateLimitedError 并立即停止。
    """

    def setUp(self):
        self.spider = DummySpider(interval=1.0, max_retries=3)

    def tearDown(self):
        self.spider.close()

    def test_all_rate_limit_codes_detected(self):
        """所有风控码都应抛出 RateLimitedError。"""
        for code in (-352, -412, -509, -799):
            with self.subTest(code=code):
                self.spider.session = MagicMock()
                self.spider.session.get.return_value = make_response(
                    {"code": code, "message": str(code)}
                )
                with self.assertRaises(RateLimitedError):
                    self.spider.request("https://example.com/api")

    def test_rate_limit_does_not_retry(self):
        """风控错误不应触发重试——重试会加重风控。"""
        self.spider.session = MagicMock()
        self.spider.session.get.return_value = make_response(
            {"code": -352, "message": "-352"}
        )
        with self.assertRaises(RateLimitedError):
            self.spider.request("https://example.com/api")

        # 关键断言：只发了 1 次请求，没有重试
        self.assertEqual(
            self.spider.session.get.call_count, 1,
            "风控错误不应重试，但实际重试了",
        )

    def test_http_412_and_429_are_rate_limited(self):
        """HTTP 412 / 429 也应识别为限流。"""
        for status in (412, 429):
            with self.subTest(status=status):
                self.spider.session = MagicMock()
                self.spider.session.get.return_value = make_response(
                    {"code": 0}, status_code=status
                )
                with self.assertRaises(RateLimitedError):
                    self.spider.request("https://example.com/api")

    def test_normal_business_error_is_spider_error(self):
        """普通业务错误应抛 SpiderError（可重试），而不是 RateLimitedError。"""
        self.spider.session = MagicMock()
        self.spider.session.get.return_value = make_response(
            {"code": -400, "message": "请求错误"}
        )
        with self.assertRaises(SpiderError):
            self.spider.request("https://example.com/api")
        # 非风控错误会重试到上限
        self.assertEqual(self.spider.session.get.call_count, 3)

    def test_success_returns_payload(self):
        """code=0 时正常返回 payload。"""
        self.spider.session = MagicMock()
        self.spider.session.get.return_value = make_response(
            {"code": 0, "data": {"list": []}}
        )
        result = self.spider.request("https://example.com/api")
        self.assertEqual(result["code"], 0)


class ThrottleTests(SimpleTestCase):
    """限速行为测试。"""

    def test_interval_floor_enforced(self):
        """即使传入 0.1 秒，也应被强制提升到合规下限 1.0 秒。"""
        spider = DummySpider(interval=0.1)
        try:
            self.assertEqual(spider.interval, 1.0)
        finally:
            spider.close()

    def test_interval_can_be_larger(self):
        """传入大于下限的值应被尊重。"""
        spider = DummySpider(interval=5.0)
        try:
            self.assertEqual(spider.interval, 5.0)
        finally:
            spider.close()

    def test_first_request_does_not_sleep(self):
        """首次请求不应休眠（没有"上一次请求"可参照）。"""
        spider = DummySpider(interval=3.0)
        try:
            with patch("apps.spider.base.time.sleep") as mock_sleep:
                spider._throttle()
                mock_sleep.assert_not_called()
        finally:
            spider.close()

    def test_second_request_sleeps(self):
        """第二次请求前应休眠，且时长受抖动影响在合理范围内。"""
        spider = DummySpider(interval=2.0)
        try:
            # 伪造"刚请求过"，使 elapsed 接近 0
            spider._last_request_at = __import__("time").monotonic()
            with patch("apps.spider.base.time.sleep") as mock_sleep:
                spider._throttle()
                mock_sleep.assert_called_once()
                waited = mock_sleep.call_args[0][0]
                # 抖动范围 0.8~1.2 倍，故等待时间应在 1.4~2.4 秒之间
                self.assertGreater(waited, 1.0)
                self.assertLess(waited, 2.6)
        finally:
            spider.close()


class CrawlStatsTests(SimpleTestCase):
    """统计对象测试。"""

    def test_merge_accumulates(self):
        """merge 应正确累加各字段。"""
        a = CrawlStats(fetched=10, created=8, updated=2, failed=0, requests=3)
        b = CrawlStats(fetched=5, created=5, updated=0, failed=1, requests=2)
        a.merge(b)
        self.assertEqual(a.fetched, 15)
        self.assertEqual(a.created, 13)
        self.assertEqual(a.updated, 2)
        self.assertEqual(a.failed, 1)
        self.assertEqual(a.requests, 5)

    def test_as_dict_matches_model_fields(self):
        """as_dict 的键必须与 CrawlTask 模型字段名一致，可直接写入。"""
        stats = CrawlStats(fetched=1, created=2, updated=3, failed=4)
        d = stats.as_dict()
        self.assertEqual(
            set(d.keys()),
            {"total_fetched", "total_created", "total_updated", "total_failed", "requests"},
        )

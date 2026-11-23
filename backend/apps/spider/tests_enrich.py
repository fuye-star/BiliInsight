# -*- coding: utf-8 -*-
"""UP主 粉丝数与 cid 复用的测试。

【为什么这两件事要专门测】
    · 粉丝数：B站排行榜接口**不返回**粉丝数，必须逐个 UP主 单独请求。
      这意味着"多请求一次"就是实打实的风控成本，
      所以去重、跳过已有值这两个节省逻辑必须被测试锁住 ——
      一旦有人改坏，代价是几十次多余请求（可能直接把 IP 打进风控）。

    · cid：排行榜响应里本来就带 cid，存下来就能让抓弹幕少发一次详情请求。
      这是一条很容易在重构中被悄悄弄丢的优化路径，
      用测试固化"有 cid 就不该再请求详情接口"。
"""

from unittest.mock import patch

from django.test import TestCase

from apps.spider import parsers
from apps.spider.base import RateLimitedError
from apps.spider.bilibili import BiliBiliSpider
from apps.spider.constants import VideoItem
from apps.spider.persistence import upsert_video
from apps.videos.models import UpUser, Video


class ParseUpuserStatTests(TestCase):
    """UP主 关系统计解析测试。"""

    def test_parses_follower(self):
        """标准响应应正确取出粉丝数。"""
        payload = {
            "code": 0,
            "data": {"mid": 946974, "following": 293, "follower": 1086893},
        }
        result = parsers.parse_upuser_stat(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["mid"], 946974)
        self.assertEqual(result["follower_count"], 1086893)
        self.assertEqual(result["following"], 293)

    def test_falls_back_to_fans_field(self):
        """B站历史上用过 fans 字段名，应兼容。"""
        payload = {"code": 0, "data": {"mid": 1, "fans": 12345}}
        result = parsers.parse_upuser_stat(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["follower_count"], 12345)

    def test_returns_none_when_data_missing(self):
        """缺少 data 时应返回 None 而不是抛异常。"""
        self.assertIsNone(parsers.parse_upuser_stat({"code": -404}))
        self.assertIsNone(parsers.parse_upuser_stat({"code": 0, "data": "oops"}))

    def test_returns_none_when_no_follower_field(self):
        """没有粉丝数字段时返回 None，避免把 0 写进库当成真实值。"""
        self.assertIsNone(
            parsers.parse_upuser_stat({"code": 0, "data": {"mid": 1}})
        )


class CidPersistenceTests(TestCase):
    """cid 入库与复用测试。"""

    def _item(self, **kwargs) -> VideoItem:
        """构造一个最小的视频实体。"""
        defaults = {
            "bvid": "BV1testcid1",
            "title": "测试视频",
            "cid": 123456,
        }
        defaults.update(kwargs)
        return VideoItem(**defaults)

    def test_cid_is_saved(self):
        """排行榜返回的 cid 必须被存下来。"""
        video, created = upsert_video(self._item())
        self.assertTrue(created)
        video.refresh_from_db()
        self.assertEqual(video.cid, 123456)

    def test_missing_cid_does_not_overwrite(self):
        """实体没有 cid 时不应把库里已有的 cid 清掉。"""
        upsert_video(self._item(cid=111))
        # 第二次抓取（例如详情接口没返回 cid）不应抹掉已有值
        upsert_video(self._item(cid=None))
        video = Video.objects.get(bvid="BV1testcid1")
        self.assertEqual(video.cid, 111)

    def test_run_danmaku_reuses_stored_cid(self):
        """库里已有 cid 时，抓弹幕不应再请求详情接口。

        这是"1 次排行榜请求换 40 次详情请求"的节省点，必须锁住。
        """
        video = Video.objects.create(
            bvid="BV1testcid2", title="测试", cid=999888
        )
        spider = BiliBiliSpider(interval=1.0)

        with patch.object(spider, "_fetch_cid") as mock_fetch_cid, patch.object(
            spider, "fetch_danmaku_segment", return_value=b""
        ) as mock_segment:
            spider.run_danmaku("BV1testcid2", limit=50, video=video)

        mock_fetch_cid.assert_not_called()
        mock_segment.assert_called_once_with(999888, 1)


class DanmakuErrorPayloadTests(TestCase):
    """弹幕接口返回 JSON 错误体时的处理。

    【这个 Bug 的真实经过】
        抓 40 个视频的弹幕时，后 19 个全部"解析出 0 条"，
        日志里只有一句莫名其妙的 "不支持的 wire_type=3"。

        实际原因是：弹幕接口**被风控时依然返回 HTTP 200**，
        响应体变成一小段 JSON（{"code":-352,...}）。
        而该接口因为是二进制协议，调用时传了 expect_json=False，
        于是这段 JSON 绕过了所有业务码检查，被直接丢给 protobuf 解析器。

        后果：19 个视频被静默判成"没有弹幕"，每个白花一次请求额度，
        而且重跑依然失败 —— 因为根因根本不是数据。
    """

    def test_json_rate_limit_payload_raises(self):
        """JSON 风控响应必须抛出 RateLimitedError，让上层正确退避。"""
        spider = BiliBiliSpider(interval=1.0)
        body = b'{"code":-352,"message":"\xe8\xaf\xb7\xe6\xb1\x82\xe8\xbf\x87\xe4\xba\x8e\xe9\xa2\x91\xe7\xb9\x81"}'

        with self.assertRaises(RateLimitedError):
            spider._guard_danmaku_payload(body)

    def test_json_other_error_raises_spider_error(self):
        """非风控码的 JSON 应抛 SpiderError，而不是当成弹幕数据。"""
        from apps.spider.base import SpiderError

        spider = BiliBiliSpider(interval=1.0)
        with self.assertRaises(SpiderError):
            spider._guard_danmaku_payload(b'{"code":-404,"message":"not found"}')

    def test_binary_payload_passes_through(self):
        """正常的 protobuf 二进制必须原样放行（不能误伤主路径）。"""
        spider = BiliBiliSpider(interval=1.0)
        raw = parsers.build_danmaku_segment(
            [{"id": 1, "progress": 1000, "content": "正常弹幕"}]
        )
        self.assertEqual(spider._guard_danmaku_payload(raw), raw)

    def test_parser_reports_json_clearly(self):
        """解析器直接拿到 JSON 时应返回空列表并给出清楚日志，不抛异常。"""
        items = parsers.parse_danmaku_protobuf(b'{"code":-352,"message":"too fast"}')
        self.assertEqual(items, [])


class UpUserFollowerTests(TestCase):
    """UP主 粉丝数抓取测试。"""

    def setUp(self):
        """准备三位 UP主：两位待补、一位已有粉丝数。"""
        self.up_a = UpUser.objects.create(mid=1001, name="甲", follower_count=0)
        self.up_b = UpUser.objects.create(mid=1002, name="乙", follower_count=0)
        self.up_done = UpUser.objects.create(mid=1003, name="丙", follower_count=555)

    @staticmethod
    def _payload(mid: int, follower: int) -> dict:
        """构造一个统计响应。"""
        return {"code": 0, "data": {"mid": mid, "follower": follower, "following": 1}}

    def test_fills_followers(self):
        """应把粉丝数写回数据库。"""
        spider = BiliBiliSpider(interval=1.0)
        fake = {
            1001: self._payload(1001, 123456),
            1002: self._payload(1002, 789),
        }

        with patch.object(
            spider, "fetch_upuser_stat", side_effect=lambda mid: fake[mid]
        ):
            stats = spider.run_upuser_followers(skip_filled=True)

        self.up_a.refresh_from_db()
        self.up_b.refresh_from_db()
        self.assertEqual(self.up_a.follower_count, 123456)
        self.assertEqual(self.up_b.follower_count, 789)
        self.assertEqual(stats.updated, 2)

    def test_skips_upusers_with_followers(self):
        """已有粉丝数的 UP主 不应被再次请求（省一次风控成本）。"""
        spider = BiliBiliSpider(interval=1.0)

        with patch.object(
            spider,
            "fetch_upuser_stat",
            return_value=self._payload(1001, 1),
        ) as mock_fetch:
            spider.run_upuser_followers(skip_filled=True)

        called_mids = [c.args[0] for c in mock_fetch.call_args_list]
        self.assertNotIn(1003, called_mids, "已有粉丝数的 UP主 不应重复请求")
        self.assertEqual(sorted(called_mids), [1001, 1002])

    def test_deduplicates_mids(self):
        """同一 mid 传入多次只应请求一次。"""
        spider = BiliBiliSpider(interval=1.0)

        with patch.object(
            spider,
            "fetch_upuser_stat",
            return_value=self._payload(1001, 42),
        ) as mock_fetch:
            spider.run_upuser_followers(
                mids=[1001, 1001, 1002, 1001], skip_filled=False
            )

        called_mids = [c.args[0] for c in mock_fetch.call_args_list]
        self.assertEqual(sorted(called_mids), [1001, 1002], "应按 mid 去重")

    def test_rate_limit_stops_gracefully(self):
        """遇风控应停止而不是抛出异常 —— 已抓到的部分必须保留。"""
        spider = BiliBiliSpider(interval=1.0)
        calls = {"n": 0}

        def fake(mid):
            """第一次成功，第二次触发风控。"""
            calls["n"] += 1
            if calls["n"] == 1:
                return self._payload(mid, 999)
            raise RateLimitedError("接口返回 -352")

        with patch.object(spider, "fetch_upuser_stat", side_effect=fake):
            stats = spider.run_upuser_followers(skip_filled=True)

        # 第一条应已写入
        self.assertEqual(stats.updated, 1)
        # 第二位（1002）没被写入，但方法本身没有抛异常
        self.up_b.refresh_from_db()
        self.assertEqual(self.up_b.follower_count, 0)

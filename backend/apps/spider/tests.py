# -*- coding: utf-8 -*-
"""
爬虫解析器的单元测试。

【测试策略：全部离线】
解析是本项目最易出错的环节（接口字段变动、protobuf 编码、中文解码）。
这里不联网、不碰数据库，只用固定样本验证解析逻辑：
  · 视频 JSON 解析 —— 用手写的样本字典
  · 弹幕 protobuf 解析 —— 用 parsers 内置的编码器构造二进制样本
    （自己编码再自己解码，可精确验证 varint / 长度前缀 / UTF-8 中文处理）

运行：
    python manage.py test apps.spider -v 2
"""

import gzip
import zlib

from django.test import SimpleTestCase

from apps.spider import parsers
from apps.spider.constants import (
    DEFAULT_PARTITIONS,
    PARTITIONS,
    partition_tid,
    safe_int,
    ts_to_datetime,
)


class PartitionHelperTests(SimpleTestCase):
    """分区名转换工具的测试。"""

    def test_name_to_tid(self):
        """常见分区名应能转成正确的 tid。"""
        self.assertEqual(partition_tid("科技"), 188)
        self.assertEqual(partition_tid("数码"), 95)
        self.assertEqual(partition_tid("游戏"), 4)

    def test_name_with_suffix(self):
        """带"区"后缀也应能识别。"""
        self.assertEqual(partition_tid("科技区"), 188)

    def test_numeric_passthrough(self):
        """纯数字直接当作 tid 返回。"""
        self.assertEqual(partition_tid("188"), 188)

    def test_unknown_returns_none(self):
        """未知分区返回 None，由调用方决定如何处理。"""
        self.assertIsNone(partition_tid("不存在的分区"))
        self.assertIsNone(partition_tid(""))

    def test_default_partitions_all_valid(self):
        """默认分区列表里的每一项都必须能解析出 tid。"""
        for name in DEFAULT_PARTITIONS:
            with self.subTest(partition=name):
                self.assertIsNotNone(partition_tid(name), f"{name} 不在 PARTITIONS 表中")

        # 反向校验：常量表本身非空
        self.assertGreater(len(PARTITIONS), 0)


class SafeIntTests(SimpleTestCase):
    """数字安全转换的测试。"""

    def test_normal_values(self):
        """常规数字正常转换。"""
        self.assertEqual(safe_int(123), 123)
        self.assertEqual(safe_int("456"), 456)

    def test_invalid_values_fallback(self):
        """接口里出现的异常值应回退到默认值，而不是抛异常。"""
        for bad in (None, "", "--", "abc", [], {}):
            with self.subTest(value=bad):
                self.assertEqual(safe_int(bad), 0)
                self.assertEqual(safe_int(bad, default=-1), -1)


class TimestampTests(SimpleTestCase):
    """时间戳转换的测试。"""

    def test_valid_timestamp(self):
        """正常时间戳应转成带时区的 datetime。"""
        dt = ts_to_datetime(1668856639)
        self.assertIsNotNone(dt)
        # 必须带时区，否则 Django 存库会偏移 8 小时
        self.assertIsNotNone(dt.tzinfo)

    def test_invalid_timestamps(self):
        """0 / None / 非法值统一返回 None。"""
        for bad in (None, 0, -1, "", "abc"):
            with self.subTest(value=bad):
                self.assertIsNone(ts_to_datetime(bad))


class VideoParsingTests(SimpleTestCase):
    """视频列表解析的测试。"""

    # 样本结构参照 B站 ranking/v2 接口的真实响应（已裁剪无关字段）
    SAMPLE = {
        "code": 0,
        "message": "0",
        "data": {
            "note": "根据稿件内容质量、近期的数据综合展示，动态更新",
            "list": [
                {
                    "aid": 517751921,
                    "bvid": "BV1Eg411v7a1",
                    "cid": 896512490,
                    "tid": 188,
                    "tname": "科技",
                    "title": "【深度评测】国产芯片到底行不行",
                    "desc": "本期我们聊聊国产芯片的现状",
                    "pic": "http://i1.hdslb.com/bfs/archive/demo.jpg",
                    "pubdate": 1668856639,
                    "duration": 752,
                    "owner": {
                        "mid": 63231,
                        "name": "泛式",
                        "face": "http://i0.hdslb.com/bfs/face/demo.jpg",
                    },
                    "stat": {
                        "view": 1156543,
                        "danmaku": 14224,
                        "reply": 5601,
                        "favorite": 28753,
                        "coin": 58324,
                        "share": 6548,
                        "like": 136884,
                    },
                }
            ],
        },
    }

    def test_parse_single_video(self):
        """标准样本应被完整解析。"""
        items = parsers.parse_video_list(self.SAMPLE)

        self.assertEqual(len(items), 1)
        item = items[0]

        # 标识
        self.assertEqual(item.bvid, "BV1Eg411v7a1")
        self.assertEqual(item.aid, 517751921)
        self.assertEqual(item.cid, 896512490)

        # 文案
        self.assertIn("国产芯片", item.title)
        self.assertIn("现状", item.description)

        # 分区与 UP主
        self.assertEqual(item.tid, 188)
        self.assertEqual(item.tname, "科技")
        self.assertEqual(item.up_mid, 63231)
        self.assertEqual(item.up_name, "泛式")

        # 互动数据
        self.assertEqual(item.view_count, 1156543)
        self.assertEqual(item.like_count, 136884)
        self.assertEqual(item.coin_count, 58324)
        self.assertEqual(item.favorite_count, 28753)
        self.assertEqual(item.share_count, 6548)
        self.assertEqual(item.danmaku_count, 14224)
        self.assertEqual(item.reply_count, 5601)

        # 时间应已转换且带时区
        self.assertIsNotNone(item.pubdate)
        self.assertIsNotNone(item.pubdate.tzinfo)

    def test_http_cover_upgraded_to_https(self):
        """封面/头像的 http 链接应被升级为 https，避免前端混合内容告警。"""
        items = parsers.parse_video_list(self.SAMPLE)
        self.assertTrue(items[0].cover_url.startswith("https://"))
        self.assertTrue(items[0].up_avatar.startswith("https://"))

    def test_skip_entry_without_bvid(self):
        """缺少 bvid 的条目应被跳过——它是入库的唯一键。"""
        payload = {
            "code": 0,
            "data": {"list": [{"title": "没有 bvid 的脏数据", "aid": 123}]},
        }
        self.assertEqual(parsers.parse_video_list(payload), [])

    def test_malformed_entries_do_not_break_batch(self):
        """单条脏数据不应影响整批解析。"""
        payload = {
            "code": 0,
            "data": {
                "list": [
                    {"bvid": "BV1good000001", "title": "正常视频", "stat": {"view": 100}},
                    {"title": "缺 bvid，应跳过"},
                    {"bvid": "BV1good000002", "title": "另一个正常视频",
                     "stat": {"view": 200}},
                ]
            },
        }
        items = parsers.parse_video_list(payload)
        self.assertEqual(len(items), 2)
        self.assertEqual([i.bvid for i in items],
                         ["BV1good000001", "BV1good000002"])

    def test_empty_and_malformed_payload(self):
        """结构异常时返回空列表，而不是抛异常。"""
        for payload in ({}, {"data": None}, {"data": {}},
                        {"data": {"list": None}}, {"data": {"list": "不是列表"}}):
            with self.subTest(payload=payload):
                self.assertEqual(parsers.parse_video_list(payload), [])

    def test_video_detail_parses_tags(self):
        """视频详情接口的 tags 列表应被拼成逗号分隔字符串。"""
        payload = {
            "code": 0,
            "data": {
                "bvid": "BV1Eg411v7a1",
                "title": "测试视频",
                "tags": [
                    {"tag_name": "编程"},
                    {"tag_name": "Python"},
                    {"tag_name": ""},          # 空标签应被过滤
                ],
            },
        }
        item = parsers.parse_video_detail(payload)
        self.assertIsNotNone(item)
        self.assertEqual(item.tags, "编程,Python")


class DanmakuEncodingTests(SimpleTestCase):
    """protobuf 编码器自身的测试（保证测试工具本身正确）。"""

    def test_varint_roundtrip(self):
        """编码后再解码应还原原值。"""
        for value in (0, 1, 127, 128, 300, 16383, 16384, 2 ** 31, 2 ** 62):
            with self.subTest(value=value):
                encoded = parsers.encode_varint(value)
                decoded, pos = parsers._read_varint(encoded, 0)
                self.assertEqual(decoded, value)
                self.assertEqual(pos, len(encoded))

    def test_varint_truncated_raises(self):
        """数据截断应抛 ValueError，而不是静默返回错误值。"""
        # 0x80 表示"还有后续字节"，但数据到此结束
        with self.assertRaises(ValueError):
            parsers._read_varint(b"\x80", 0)


class DanmakuParsingTests(SimpleTestCase):
    """弹幕 protobuf 解析的测试。"""

    def test_parse_single_danmaku(self):
        """单条弹幕的全部字段应被正确解析。"""
        data = parsers.build_danmaku_segment([
            {
                "id": 711923911,
                "progress": 47880,          # 毫秒
                "mode": 1,
                "color": 10092288,
                "content": "世界第一电击公主殿下",
                "ctime": 1418799826,
                "pool": 0,
            }
        ])

        items = parsers.parse_danmaku_protobuf(data)

        self.assertEqual(len(items), 1)
        dm = items[0]
        self.assertEqual(dm.dmid, 711923911)
        # 毫秒应转成秒
        self.assertAlmostEqual(dm.video_time, 47.88, places=2)
        self.assertEqual(dm.mode, 1)
        self.assertEqual(dm.color, 10092288)
        self.assertEqual(dm.content, "世界第一电击公主殿下")
        self.assertIsNotNone(dm.send_time)

    def test_gzip_encoded_segment_is_decompressed(self):
        """未被 requests 解压的 gzip 响应应能自行解压后解析。

        【为什么必须有这个测试】
            实测抓 40 个视频的弹幕时，后 19 个连续失败并报
            "不支持的 wire_type=3" —— 那是压缩字节被当成 protobuf 解析了。
            同样的 cid 稍后重试就正常，说明是 CDN 偶发漏发
            Content-Encoding 头导致 requests 没有自动解压。

            若不在这里兜住，19 个视频会白花 19 次风控额度，
            而且会被误判成"这些视频没有弹幕"而永久跳过。
        """
        raw = parsers.build_danmaku_segment([
            {"id": 1, "progress": 5000, "content": "压缩包里的弹幕"},
        ])
        items = parsers.parse_danmaku_protobuf(gzip.compress(raw))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content, "压缩包里的弹幕")

    def test_zlib_encoded_segment_is_decompressed(self):
        """zlib 压缩的响应同样应被识别并解压。"""
        raw = parsers.build_danmaku_segment([
            {"id": 2, "progress": 8000, "content": "zlib 压缩的弹幕"},
        ])
        items = parsers.parse_danmaku_protobuf(zlib.compress(raw))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content, "zlib 压缩的弹幕")

    def test_broken_gzip_falls_back_without_crashing(self):
        """gzip 魔数正确但内容损坏时，应原样返回、不抛异常。"""
        broken = b"\x1f\x8b" + b"\x00" * 20
        # 不应抛异常；解析结果为空即可
        items = parsers.parse_danmaku_protobuf(broken)
        self.assertEqual(items, [])

    def test_plain_protobuf_still_parses(self):
        """未压缩的正常响应不受影响（避免兜底逻辑误伤主路径）。"""
        raw = parsers.build_danmaku_segment([
            {"id": 3, "progress": 1000, "content": "普通弹幕"},
        ])
        items = parsers.parse_danmaku_protobuf(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content, "普通弹幕")

    def test_chinese_and_emoji_content(self):
        """中文与 emoji 必须正确解码（弹幕里 emoji 很常见）。"""
        samples = [
            "哈哈哈太强了",
            "泪目了😭",
            "🎉🎉🎉",
            "abc混合123中文",
        ]
        data = parsers.build_danmaku_segment([
            {"id": i + 1, "progress": 1000 * (i + 1), "content": text}
            for i, text in enumerate(samples)
        ])

        items = parsers.parse_danmaku_protobuf(data)

        self.assertEqual(len(items), len(samples))
        self.assertEqual([i.content for i in items], samples)

    def test_multiple_danmaku_preserve_order(self):
        """多条弹幕应按原顺序解析，且 dmid 不串位。"""
        data = parsers.build_danmaku_segment([
            {"id": 1, "progress": 1000, "content": "第一条"},
            {"id": 2, "progress": 2000, "content": "第二条"},
            {"id": 3, "progress": 3000, "content": "第三条"},
        ])

        items = parsers.parse_danmaku_protobuf(data)
        self.assertEqual(len(items), 3)
        self.assertEqual([i.dmid for i in items], [1, 2, 3])
        self.assertEqual([i.content for i in items], ["第一条", "第二条", "第三条"])
        # progress 毫秒 -> 秒
        self.assertAlmostEqual(items[1].video_time, 2.0, places=3)

    def test_empty_content_skipped(self):
        """空内容弹幕应被跳过——没有分析价值。"""
        data = parsers.build_danmaku_segment([
            {"id": 1, "progress": 1000, "content": ""},
            {"id": 2, "progress": 2000, "content": "   "},   # 纯空格
            {"id": 3, "progress": 3000, "content": "有效弹幕"},
        ])
        items = parsers.parse_danmaku_protobuf(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content, "有效弹幕")

    def test_empty_bytes_returns_empty_list(self):
        """空响应（视频没有弹幕）应返回空列表而非报错。"""
        self.assertEqual(parsers.parse_danmaku_protobuf(b""), [])
        self.assertEqual(parsers.parse_danmaku_protobuf(None), [])

    def test_corrupted_data_does_not_raise(self):
        """损坏的二进制不应抛异常——单包失败不该中断整个抓取流程。"""
        corrupted = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x0F, 0x00, 0x01])
        # 只要不抛异常即可（结果为列表，可能为空）
        result = parsers.parse_danmaku_protobuf(corrupted)
        self.assertIsInstance(result, list)

    def test_truncated_data_keeps_valid_prefix(self):
        """数据被截断时，已解析成功的部分应被保留。"""
        full = parsers.build_danmaku_segment([
            {"id": 1, "progress": 1000, "content": "完整弹幕"},
            {"id": 2, "progress": 2000, "content": "这条会被截断"},
        ])
        truncated = full[: len(full) - 8]   # 砍掉尾部若干字节

        items = parsers.parse_danmaku_protobuf(truncated)
        # 至少解析出第一条，且不抛异常
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0].content, "完整弹幕")

    def test_large_dmid_beyond_int32(self):
        """dmid 是 int64，超过 int32 范围的值必须正确处理。

        真实弹幕 ID 已经超过 21 亿，若按 int32 解析会溢出为负数。
        """
        big_id = 9_000_000_000   # > 2**32
        data = parsers.build_danmaku_segment([
            {"id": big_id, "progress": 5000, "content": "大 ID 弹幕"}
        ])
        items = parsers.parse_danmaku_protobuf(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].dmid, big_id)

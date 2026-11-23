# -*- coding: utf-8 -*-
"""全站热门（popular）抓取的测试。

【为什么单独测这个接口】
    它是为了绕开"排行榜接口风控太严"而新增的补充路径：

        ranking/v2  —— 每个分区只能拿约 97 条，且最容易被 -352 拦
        popular     —— 支持翻页，风控更宽松，适合批量灌数据

    实测中排行榜持续被拦、热门却能连续抓 5 页（250 条），
    说明两者确实是**不同的配额**。既然它是批量取数的主力，
    翻页、去重、止停条件都必须可靠，否则会白耗请求额度。
"""

from unittest.mock import patch

from django.test import TestCase

from apps.spider.base import CrawlStats
from apps.spider.bilibili import BiliBiliSpider
from apps.videos.models import Video


def _item(bvid: str, tid: int = 4, tname: str = "游戏", cid: int = 111) -> dict:
    """构造一条热门接口里的视频数据。"""
    return {
        "bvid": bvid,
        "aid": 1000,
        "title": f"测试视频 {bvid}",
        "desc": "简介",
        "pic": "http://i0.hdslb.com/x.jpg",
        "duration": 120,
        "pubdate": 1700000000,
        "cid": cid,
        "tid": tid,
        "tname": tname,
        "owner": {"mid": 9001, "name": "测试UP", "face": "http://i0.hdslb.com/a.jpg"},
        "stat": {
            "view": 1000,
            "like": 100,
            "coin": 10,
            "favorite": 5,
            "share": 1,
            "danmaku": 20,
            "reply": 3,
        },
    }


def _page(items: list, no_more: bool = False) -> dict:
    """构造一页热门响应。"""
    return {"code": 0, "data": {"list": items, "no_more": no_more}}


class RunPopularTests(TestCase):
    """run_popular 的翻页与止停逻辑。"""

    def setUp(self):
        Video.objects.all().delete()

    def test_paginates_until_limit(self):
        """应按页抓取，达到 limit 后停止翻页。"""
        spider = BiliBiliSpider(interval=1.0)
        pages = {
            1: _page([_item("BVpop000001"), _item("BVpop000002")]),
            2: _page([_item("BVpop000003"), _item("BVpop000004")]),
            3: _page([_item("BVpop000005"), _item("BVpop000006")]),
        }

        with patch.object(
            spider, "fetch_popular", side_effect=lambda page, page_size: pages[page]
        ) as mock_fetch:
            stats = spider.run_popular(limit=4, max_pages=5, page_size=2)

        self.assertEqual(stats.created, 4, "limit=4 时应恰好入库 4 条")
        self.assertEqual(mock_fetch.call_count, 2, "抓够 4 条后不应再翻第 3 页")
        self.assertEqual(Video.objects.count(), 4)

    def test_stops_on_no_more(self):
        """接口返回 no_more 时应立即停止，不再请求下一页。"""
        spider = BiliBiliSpider(interval=1.0)
        pages = {
            1: _page([_item("BVpop000011")], no_more=True),
            2: _page([_item("BVpop000012")]),
        }

        with patch.object(
            spider, "fetch_popular", side_effect=lambda page, page_size: pages[page]
        ) as mock_fetch:
            spider.run_popular(limit=100, max_pages=5, page_size=2)

        self.assertEqual(mock_fetch.call_count, 1, "no_more 后不应继续翻页")
        self.assertEqual(Video.objects.count(), 1)

    def test_stops_on_empty_page(self):
        """空页也应终止，避免无意义地继续请求。"""
        spider = BiliBiliSpider(interval=1.0)
        pages = {1: _page([_item("BVpop000021")]), 2: _page([])}

        with patch.object(
            spider, "fetch_popular", side_effect=lambda page, page_size: pages[page]
        ) as mock_fetch:
            spider.run_popular(limit=100, max_pages=5, page_size=2)

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(Video.objects.count(), 1)

    def test_cid_is_saved(self):
        """热门接口同样返回 cid，必须存下来（后续抓弹幕可省一次请求）。"""
        spider = BiliBiliSpider(interval=1.0)
        with patch.object(
            spider, "fetch_popular", return_value=_page([_item("BVpop000031", cid=999888)])
        ):
            spider.run_popular(limit=10, max_pages=1, page_size=2)

        self.assertEqual(Video.objects.get(bvid="BVpop000031").cid, 999888)

    def test_tags_fallback_to_tname(self):
        """热门接口不返回 tags，应回落到细分分区名（词云需要内容）。"""
        spider = BiliBiliSpider(interval=1.0)
        with patch.object(
            spider, "fetch_popular", return_value=_page([_item("BVpop000041", tname="单机游戏")])
        ):
            spider.run_popular(limit=10, max_pages=1, page_size=2)

        self.assertEqual(Video.objects.get(bvid="BVpop000041").tags, "单机游戏")


class PopularCommandTests(TestCase):
    """命令行 --popular 的行为。"""

    def test_popular_does_not_crawl_default_partitions(self):
        """只传 --popular 时，不能顺带跑一遍默认分区。

        【为什么专门测这个】
            `handle()` 里有一段"未指定抓取目标则使用默认分区列表"的逻辑。
            新增 --popular 时忘了把它加进判断条件，结果：

                manage.py crawl --popular

            在抓完热门之后**又去抓了一遍科技分区**，白白消耗了一次
            风控额度（当时正好被 -352 拦住）。

            这类"参数漏加进判断"的 Bug 不会报错，只会悄悄多发请求，
            所以用测试钉住。
        """
        from django.core.management import call_command

        with patch(
            "apps.spider.management.commands.crawl.BiliBiliSpider"
        ) as mock_spider_cls:
            spider = mock_spider_cls.return_value
            spider.stats = CrawlStats(requests=1)
            spider.run_popular.return_value = CrawlStats(fetched=50, created=50)

            call_command(
                "crawl", popular=True, limit=50, pages=1, followers=False, verbosity=0
            )

            self.assertTrue(spider.run_popular.called, "应调用热门抓取")
            self.assertFalse(
                spider.run_partition.called,
                "--popular 不应触发默认分区抓取",
            )

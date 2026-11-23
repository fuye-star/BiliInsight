# -*- coding: utf-8 -*-
"""缓存失效行为的回归测试。

【为什么专门为"清缓存"写测试】
    这是一个**踩过的坑**，而且失败时完全静默：

    抓完 97 条真实数据后，界面上出现了非常奇怪的现象 ——
        · 视频列表页立刻变成新数据  ✅
        · 数据总览 / UP主 排行 / 情感分析仍是旧数字  ❌
    看起来像"数据只同步了一半"，排查后才发现：
    分析接口带 300-600 秒 Redis 缓存，而抓取流程**根本没有清缓存**。

    更麻烦的是 `clear_analytics_cache()` 的文档字符串里
    写着"在 Celery 任务成功结束时触发（见 apps/spider/tasks.py）"，
    但 tasks.py 里其实**从来没有调用过** —— 注释描述了意图而非事实，
    导致这个缺口长期没人发现。

    因此这里用测试把"数据写入后必须清缓存"固化下来：
    以后再有人改动抓取流程却忘了清缓存，测试会立刻失败。
"""

from unittest.mock import patch

from django.test import TestCase

from apps.analytics.services import clear_analytics_cache
from apps.spider.base import CrawlStats
from apps.spider.models import CrawlTask
from apps.spider.tasks import _finish_task


class FinishTaskClearsCacheTests(TestCase):
    """验证 _finish_task 在合适的时机清空分析缓存。"""

    def setUp(self):
        """每个用例前清一次，避免相互干扰。"""
        clear_analytics_cache()

    def _make_task(self, **kwargs) -> CrawlTask:
        """造一条"执行中"的任务记录。"""
        defaults = {
            "source": "partition",
            "target": "分区:科技",
            "status": "running",
        }
        defaults.update(kwargs)
        return CrawlTask.objects.create(**defaults)

    def test_clears_cache_when_data_created(self):
        """有新数据写入时必须清缓存。"""
        task = self._make_task()
        stats = CrawlStats(fetched=97, created=97, updated=0, failed=0)

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            _finish_task(task, stats)
            self.assertTrue(
                mock_clear.called,
                "抓取新增了数据却没有清分析缓存 —— 看板会显示旧数字最长 10 分钟",
            )

    def test_clears_cache_when_data_updated(self):
        """只更新（无新增）时同样要清缓存。"""
        task = self._make_task()
        stats = CrawlStats(fetched=50, created=0, updated=50, failed=0)

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            _finish_task(task, stats)
            self.assertTrue(mock_clear.called, "更新了数据也应清缓存")

    def test_skips_cache_when_nothing_written(self):
        """没有实际写入时不应清缓存（避免无意义地击穿缓存）。"""
        task = self._make_task()
        stats = CrawlStats(fetched=0, created=0, updated=0, failed=0)

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            _finish_task(task, stats)
            self.assertFalse(
                mock_clear.called,
                "没有任何数据变化时不应清缓存",
            )

    def test_skips_cache_when_task_failed(self):
        """任务失败时不应清缓存。"""
        task = self._make_task()

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            _finish_task(task, None, error_message="被目标站点风控限流")
            self.assertFalse(mock_clear.called, "任务失败时不应清缓存")

    def test_cache_failure_does_not_break_task(self):
        """清缓存失败不能影响"抓取成功"这个事实。

        缓存只是加速手段，Redis 抖动不该让一次成功的抓取被标记为失败。
        """
        task = self._make_task()
        stats = CrawlStats(fetched=10, created=10, updated=0, failed=0)

        with patch(
            "apps.analytics.services.clear_analytics_cache",
            side_effect=RuntimeError("Redis 挂了"),
        ):
            result = _finish_task(task, stats)

        result.refresh_from_db()
        self.assertEqual(result.status, "success")
        self.assertEqual(result.total_created, 10)

    def test_task_records_stats(self):
        """顺带验证统计写入没有被破坏。"""
        task = self._make_task()
        stats = CrawlStats(fetched=97, created=90, updated=7, failed=0)

        result = _finish_task(task, stats)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.total_fetched, 97)
        self.assertEqual(result.total_created, 90)
        self.assertEqual(result.total_updated, 7)
        self.assertIsNotNone(result.finished_at)


class CrawlCommandClearsCacheTests(TestCase):
    """验证 `manage.py crawl` 这条同步路径也会清缓存。

    【为什么 Celery 之外还要单独测】
        本项目抓数据有两条路径：
            · 异步：Celery 任务   -> 由 _finish_task 统一清缓存
            · 同步：manage.py crawl -> 必须自己清
        两者代码不共用，只覆盖其中一条会留下缺口 ——
        最初的 Bug 恰恰是"两条路径都没清"。

        用户手动抓数据用的就是同步命令，所以这条路径必须单独锁定。
    """

    def setUp(self):
        """每个用例前清一次。"""
        clear_analytics_cache()

    def _run_crawl(self, stats: CrawlStats):
        """跑一次 crawl 命令，网络请求全部用假的替代。"""
        from django.core.management import call_command

        with patch(
            "apps.spider.management.commands.crawl.BiliBiliSpider"
        ) as mock_spider_cls:
            spider = mock_spider_cls.return_value
            spider.interval = 2.0
            spider.max_retries = 3
            spider.stats = stats
            spider.run_partition.return_value = stats

            call_command("crawl", partition="科技", limit=10, verbosity=0)

    def test_command_clears_cache_after_creating(self):
        """命令新增数据后必须清缓存。"""
        stats = CrawlStats(fetched=97, created=97, updated=0, failed=0, requests=1)

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            self._run_crawl(stats)

        self.assertTrue(
            mock_clear.called,
            "manage.py crawl 新增数据后没有清缓存 —— "
            "界面会表现为「视频列表更新了，但总览和排行榜没变」",
        )

    def test_command_skips_cache_when_nothing_written(self):
        """全部数据都已存在（新增 0 更新 0）时无需清缓存。"""
        stats = CrawlStats(fetched=97, created=0, updated=0, failed=0, requests=1)

        with patch(
            "apps.analytics.services.clear_analytics_cache"
        ) as mock_clear:
            self._run_crawl(stats)

        self.assertFalse(mock_clear.called, "没有数据变化时不应清缓存")


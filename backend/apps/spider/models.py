# -*- coding: utf-8 -*-
"""
spider 应用的数据模型。

【为什么爬虫需要数据模型】
爬取任务耗时长（受 2 秒限速约束），必须异步执行。
但异步任务的结果前端看不到，因此需要一张表记录每次抓取的状态，
前端可以轮询 /api/tasks/{id}/ 查看进度。

【阶段二计划实现的爬虫基类与任务】
    base.py       BaseSpider 抽象基类（限速、重试、UA、日志）
    bilibili.py   BiliBiliSpider 具体实现（视频、弹幕、分区）
    tasks.py      Celery 任务（crawl_partition / crawl_all_partitions）
"""

from django.db import models

from apps.common.models import TimeStampedModel


class CrawlTask(TimeStampedModel):
    """一次爬取任务的执行记录。

    贯穿"触发 -> 执行 -> 完成/失败"的完整生命周期，
    让前端能以进度条的形式展示后台任务状态。
    """

    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("running", "执行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("cancelled", "已取消"),
    ]

    SOURCE_CHOICES = [
        ("partition", "按分区抓取"),
        ("hot", "热门榜单"),
        ("search", "关键词搜索"),
        ("danmaku", "弹幕抓取"),
    ]

    # Celery 的任务 ID，用于与 celery-results 表关联
    task_id = models.CharField(
        "Celery任务ID",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )

    source = models.CharField(
        "任务类型",
        max_length=20,
        choices=SOURCE_CHOICES,
        default="partition",
        db_index=True,
    )

    # 抓取目标描述，如 "科技" 或 "关键词:Python"
    target = models.CharField("抓取目标", max_length=100, blank=True, default="")

    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # ---------------- 执行统计 ----------------
    total_fetched = models.IntegerField("抓取条数", default=0)
    total_created = models.IntegerField("新增条数", default=0)
    total_updated = models.IntegerField("更新条数", default=0)
    total_failed = models.IntegerField("失败条数", default=0)

    # ---------------- 时间与错误 ----------------
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)

    error_message = models.TextField(
        "错误信息",
        blank=True,
        default="",
        help_text="失败时记录异常摘要，便于排查",
    )

    class Meta:
        db_table = "spider_crawltask"
        verbose_name = "爬取任务"
        verbose_name_plural = "爬取任务"
        ordering = ["-created_at"]
        indexes = [
            # 前端按状态筛选"进行中的任务"
            models.Index(fields=["status", "-created_at"], name="idx_crawltask_status"),
        ]

    def __str__(self):
        return f"[{self.status}] {self.get_source_display()} - {self.target}"

    @property
    def duration_seconds(self):
        """任务耗时（秒）。未开始或未结束时返回 None。"""
        if not self.started_at or not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 2)

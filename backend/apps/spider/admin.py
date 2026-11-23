# -*- coding: utf-8 -*-
"""
spider 应用的 Admin 配置。

爬取任务的执行记录在后台可视化，便于：
  - 观察定时爬虫是否正常运行
  - 排查失败任务的具体错误
  - 答辩演示"爬虫实时运行"环节时展示数据
"""

from django.contrib import admin

from .models import CrawlTask


@admin.register(CrawlTask)
class CrawlTaskAdmin(admin.ModelAdmin):
    """爬取任务管理。"""

    list_display = (
        "id",
        "source",
        "target",
        "status",
        "total_fetched",
        "total_created",
        "total_updated",
        "duration_seconds",
        "created_at",
    )
    list_filter = ("status", "source", "created_at")
    search_fields = ("target", "task_id")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    # 执行结果由任务写入，后台不允许手工篡改
    readonly_fields = (
        "task_id",
        "total_fetched",
        "total_created",
        "total_updated",
        "total_failed",
        "started_at",
        "finished_at",
        "error_message",
        "created_at",
        "updated_at",
    )

    @admin.display(description="耗时（秒）")
    def duration_seconds(self, obj):
        """展示任务耗时。"""
        value = obj.duration_seconds
        return value if value is not None else "-"

# -*- coding: utf-8 -*-
"""
videos 应用的 Admin 后台配置。

Admin 是本项目的实用工具：
  - 快速核对爬虫抓到的数据是否正确
  - 手动查看/清理异常数据
  - 答辩演示时可直接展示后台数据管理能力
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Danmaku, Partition, UpUser, Video


@admin.register(Partition)
class PartitionAdmin(admin.ModelAdmin):
    """分区管理。"""

    list_display = ("id", "name", "bili_tid", "video_total", "created_at")
    search_fields = ("name",)
    ordering = ("name",)

    @admin.display(description="视频数")
    def video_total(self, obj):
        """显示该分区已收录的视频数量。"""
        return obj.videos.count()


@admin.register(UpUser)
class UpUserAdmin(admin.ModelAdmin):
    """UP主管理。"""

    list_display = ("mid", "name", "follower_count", "video_count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "mid")
    ordering = ("-follower_count",)
    # mid 由爬虫写入，后台不允许手动改动，防止破坏唯一性
    readonly_fields = ("created_at", "updated_at")


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    """视频管理（最常用的后台页面）。"""

    list_display = (
        "bvid",
        "short_title",
        "partition",
        "upuser",
        "view_count",
        "like_count",
        "interaction_rate",
        "pubdate",
    )
    list_filter = ("partition", "pubdate", "created_at")
    search_fields = ("bvid", "title", "upuser__name")
    ordering = ("-pubdate",)

    # 外键下拉在数据量大时会很慢，改用搜索选择
    autocomplete_fields = ("partition", "upuser")

    # 关系字段用 select_related 预加载，避免列表页 N+1 查询
    list_select_related = ("partition", "upuser")

    date_hierarchy = "pubdate"

    readonly_fields = ("created_at", "updated_at", "interaction_rate")

    fieldsets = (
        ("标识信息", {"fields": ("bvid", "aid", "title", "description")}),
        ("关联关系", {"fields": ("partition", "upuser")}),
        ("元信息", {"fields": ("cover_url", "duration", "pubdate", "tags")}),
        (
            "互动数据",
            {
                "fields": (
                    "view_count",
                    "like_count",
                    "coin_count",
                    "favorite_count",
                    "share_count",
                    "danmaku_count",
                    "reply_count",
                    "interaction_rate",
                )
            },
        ),
        ("时间戳", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="标题")
    def short_title(self, obj):
        """标题过长时截断，避免列表页排版错乱。"""
        return obj.title[:40] + ("..." if len(obj.title) > 40 else "")

    @admin.display(description="封面")
    def cover_preview(self, obj):
        """在详情页展示封面缩略图。"""
        if not obj.cover_url:
            return "无封面"
        return format_html(
            '<img src="{}" style="max-height:200px;border-radius:6px;" />',
            obj.cover_url,
        )


@admin.register(Danmaku)
class DanmakuAdmin(admin.ModelAdmin):
    """弹幕管理。"""

    list_display = ("id", "video", "short_content", "video_time", "sentiment_label", "send_time")
    list_filter = ("sentiment_label", "send_time")
    search_fields = ("content", "video__bvid")
    ordering = ("-created_at",)
    list_select_related = ("video",)
    date_hierarchy = "send_time"

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="内容")
    def short_content(self, obj):
        """弹幕通常很短，截断到 30 字足够辨认。"""
        return obj.content[:30] + ("..." if len(obj.content) > 30 else "")

    # 提供批量操作：手动触发情感分析（阶段三接入真实分析逻辑）
    actions = ["mark_as_pending"]

    @admin.action(description="标记为待分析（清空情感结果）")
    def mark_as_pending(self, request, queryset):
        """把选中的弹幕重置为未分析状态，便于重新跑分析任务。"""
        updated = queryset.update(sentiment_label="", sentiment_score=None, emotion_tags="")
        self.message_user(request, f"已将 {updated} 条弹幕标记为待分析")

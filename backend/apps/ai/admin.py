# -*- coding: utf-8 -*-
"""
ai 应用的 Admin 配置。

会话与消息记录在后台可查，方便：
  - 回看测试期间的问答质量
  - 统计各 Provider 的响应耗时
  - 答辩时演示 AI 模块的运行记录
"""

from django.contrib import admin

from .models import ChatMessage, ChatSession


class ChatMessageInline(admin.TabularInline):
    """在会话详情页内联展示其消息，一眼看清完整对话。"""

    model = ChatMessage
    extra = 0                 # 不显示空白新增行（消息由程序写入）
    can_delete = False        # 禁止在后台删除单条消息，避免破坏对话上下文
    readonly_fields = ("role", "content", "sources", "model_name", "latency_ms", "created_at")

    def has_add_permission(self, request, obj=None):
        """消息由接口写入，后台不提供新增入口。"""
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """AI 会话管理。"""

    list_display = ("id", "title", "user", "provider", "message_total", "created_at")
    list_filter = ("provider", "created_at")
    search_fields = ("title",)
    ordering = ("-updated_at",)
    date_hierarchy = "created_at"
    inlines = [ChatMessageInline]

    @admin.display(description="消息数")
    def message_total(self, obj):
        """统计该会话的消息条数。"""
        return obj.messages.count()


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """AI 消息管理（独立页面，便于全局检索）。"""

    list_display = ("id", "session", "role", "short_content", "model_name", "latency_ms", "created_at")
    list_filter = ("role", "model_name", "created_at")
    search_fields = ("content",)
    ordering = ("-created_at",)
    list_select_related = ("session",)

    @admin.display(description="内容")
    def short_content(self, obj):
        """截断长文本，保持列表可读。"""
        return obj.content[:50] + ("..." if len(obj.content) > 50 else "")

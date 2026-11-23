# -*- coding: utf-8 -*-
"""
ai 应用的路由。

挂载点：/api/ai/（见 config/urls.py）

【接口清单】
    POST /api/ai/chat/                 RAG 对话（SSE 流式 / JSON）
    GET  /api/ai/status/               RAG 链路状态
    POST /api/ai/build-index/          重建向量索引
    GET  /api/ai/history/              历史会话列表
    GET  /api/ai/history/{id}/         会话消息记录
    POST /api/ai/analyze-sentiment/    文本情感分析
    GET  /api/ai/sentiment-health/     情感分析后端自检
"""

from django.urls import path

from . import views

urlpatterns = [
    # ---- 阶段五：RAG 对话 ----（放在前面，避免被通配路由抢先匹配）
    path("chat/", views.ChatView.as_view(), name="ai-chat"),
    path("status/", views.RagStatusView.as_view(), name="ai-status"),
    path("build-index/", views.BuildIndexView.as_view(), name="ai-build-index"),
    path("history/", views.HistoryListView.as_view(), name="ai-history"),
    path(
        "history/<int:session_id>/",
        views.HistoryDetailView.as_view(),
        name="ai-history-detail",
    ),

    # ---- 阶段三：情感分析 ----
    path(
        "analyze-sentiment/",
        views.AnalyzeSentimentView.as_view(),
        name="ai-analyze-sentiment",
    ),
    path(
        "sentiment-health/",
        views.SentimentHealthView.as_view(),
        name="ai-sentiment-health",
    ),

    # ---- 大模型提供商（用户自定义 API）----
    # 放在最后，避免 providers/presets/ 被 providers/<int:pk>/ 抢先匹配
    # （这里 pk 用 int 转换器，presets 是字符串，本不会冲突，但保持顺序清晰）
    path(
        "providers/presets/",
        views.ProviderPresetsView.as_view(),
        name="ai-provider-presets",
    ),
    path(
        "providers/",
        views.ProviderListView.as_view(),
        name="ai-provider-list",
    ),
    path(
        "providers/<int:pk>/",
        views.ProviderDetailView.as_view(),
        name="ai-provider-detail",
    ),
    path(
        "providers/<int:pk>/activate/",
        views.ProviderActivateView.as_view(),
        name="ai-provider-activate",
    ),
    path(
        "providers/<int:pk>/test/",
        views.ProviderTestView.as_view(),
        name="ai-provider-test",
    ),
]

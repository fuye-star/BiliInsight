# -*- coding: utf-8 -*-
"""
analytics 应用的路由。

挂载点：/api/analytics/（见 config/urls.py）

接口列表：
    GET /api/analytics/overview/            总览指标
    GET /api/analytics/trend/               播放量趋势
    GET /api/analytics/partition-ratio/     分区占比
    GET /api/analytics/top-upusers/         UP主排行
    GET /api/analytics/top-videos/          视频排行
    GET /api/analytics/wordcloud/           词云数据
    GET /api/analytics/sentiment/           情感分析
    GET /api/analytics/interaction/         互动质量分析

全部为只读 GET 接口，无需认证（AllowAny），
方便前端在未登录状态下也能展示看板。
"""

from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="analytics-overview"),
    path("trend/", views.TrendView.as_view(), name="analytics-trend"),
    path(
        "partition-ratio/",
        views.PartitionRatioView.as_view(),
        name="analytics-partition-ratio",
    ),
    path("top-upusers/", views.TopUpusersView.as_view(), name="analytics-top-upusers"),
    path("top-videos/", views.TopVideosView.as_view(), name="analytics-top-videos"),
    path("wordcloud/", views.WordCloudView.as_view(), name="analytics-wordcloud"),
    path("sentiment/", views.SentimentView.as_view(), name="analytics-sentiment"),
    path(
        "interaction/",
        views.InteractionAnalysisView.as_view(),
        name="analytics-interaction",
    ),
]

# -*- coding: utf-8 -*-
"""
videos 应用的路由。

挂载点：/api/（见 config/urls.py）

接口列表：
    GET /api/videos/                       视频列表
    GET /api/videos/{bvid}/                视频详情
    GET /api/videos/{bvid}/danmaku/        视频弹幕
    GET /api/upusers/                      UP主列表
    GET /api/partitions/                   分区列表

【为什么不用 DRF Router + ViewSet】
本模块的接口形态差异较大（列表、按 bvid 的详情、嵌套的弹幕列表），
且 URL 需要带 bvid 这种非主键标识。
用显式 path() 声明比 Router 更直观，接口文档中的路径也更清晰。
"""

from django.urls import path

from . import views

urlpatterns = [
    path("videos/", views.VideoListView.as_view(), name="video-list"),
    path("videos/<str:bvid>/", views.VideoDetailView.as_view(), name="video-detail"),
    path(
        "videos/<str:bvid>/danmaku/",
        views.VideoDanmakuView.as_view(),
        name="video-danmaku",
    ),
    path("upusers/", views.UpUserListView.as_view(), name="upuser-list"),
    path("partitions/", views.PartitionListView.as_view(), name="partition-list"),
]

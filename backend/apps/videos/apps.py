# -*- coding: utf-8 -*-
"""videos 应用的 AppConfig。"""

from django.apps import AppConfig


class VideosConfig(AppConfig):
    """核心数据模型：分区、UP主、视频、弹幕。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.videos"
    label = "videos"
    verbose_name = "视频数据"

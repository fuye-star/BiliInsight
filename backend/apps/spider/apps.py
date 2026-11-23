# -*- coding: utf-8 -*-
"""spider 应用的 AppConfig。"""

from django.apps import AppConfig


class SpiderConfig(AppConfig):
    """数据采集：BaseSpider 抽象基类 + B站实现 + Celery 异步任务。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.spider"
    label = "spider"
    verbose_name = "数据采集"

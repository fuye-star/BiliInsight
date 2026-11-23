# -*- coding: utf-8 -*-
"""analytics 应用的 AppConfig。"""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """数据统计：趋势、占比、排行榜、词云、情感分布。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "数据统计"

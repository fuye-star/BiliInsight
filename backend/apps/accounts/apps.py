# -*- coding: utf-8 -*-
"""accounts 应用的 AppConfig。"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """用户与认证：注册、登录、JWT 签发与刷新。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "用户认证"

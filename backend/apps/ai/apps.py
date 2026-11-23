# -*- coding: utf-8 -*-
"""ai 应用的 AppConfig。"""

from django.apps import AppConfig


class AiConfig(AppConfig):
    """AI 模块：LLM 工厂（Ollama/通义千问）+ RAG 检索 + 情感分析。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI 助手"

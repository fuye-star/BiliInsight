# -*- coding: utf-8 -*-
"""
ai 应用的数据模型。

【为什么需要会话表】
AI 助手要支持多轮对话（"那第二个视频呢？"这类追问依赖上文），
因此需要持久化会话与消息记录。

同时这些记录也是答辩材料：可以展示真实的问答历史与 RAG 命中情况。

【阶段三计划的模块结构】
    llm.py             LLM 工厂：按 AI_PROVIDER 返回 Ollama 或通义千问实例
    embedding.py       文本向量化封装
    vector_store.py    ChromaDB 封装（写入 / 相似度检索）
    rag.py             RAG 编排：检索 -> 组装 Prompt -> 调用模型 -> 流式返回
    sentiment.py       SentimentAnalyzer 抽象接口 + SnowNLP/PaddleNLP 实现
"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class ChatSession(TimeStampedModel):
    """一次 AI 对话会话（可包含多轮问答）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        verbose_name="所属用户",
        null=True,
        blank=True,
        help_text="允许为空，便于未登录状态下演示 AI 助手",
    )

    title = models.CharField(
        "会话标题",
        max_length=100,
        blank=True,
        default="",
        help_text="通常取首条提问的前 30 字，便于在历史列表中辨认",
    )

    provider = models.CharField(
        "AI提供方",
        max_length=20,
        blank=True,
        default="",
        help_text="ollama / dashscope，记录本次会话实际使用的模型来源",
    )

    class Meta:
        db_table = "ai_chatsession"
        verbose_name = "AI会话"
        verbose_name_plural = "AI会话"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"会话#{self.pk}"


class ChatMessage(TimeStampedModel):
    """会话中的单条消息（用户提问 或 AI 回答）。"""

    ROLE_CHOICES = [
        ("user", "用户"),
        ("assistant", "AI助手"),
        ("system", "系统"),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="所属会话",
    )

    role = models.CharField("角色", max_length=10, choices=ROLE_CHOICES, db_index=True)

    content = models.TextField("消息内容")

    # ---------------- RAG 溯源 ----------------
    # 保存本次回答检索到的视频 bvid 列表（逗号分隔）
    # 作用：前端可展示"参考了这些视频"，体现 RAG 的可解释性
    sources = models.TextField(
        "引用来源",
        blank=True,
        default="",
        help_text="RAG 命中的视频 bvid，逗号分隔，用于前端展示引用出处",
    )

    # 记录模型信息（名称、耗时、token 数），便于优化提示词与评估成本
    model_name = models.CharField("模型名称", max_length=50, blank=True, default="")
    latency_ms = models.IntegerField("响应耗时（毫秒）", default=0)
    token_count = models.IntegerField("token 数", default=0)

    class Meta:
        db_table = "ai_chatmessage"
        verbose_name = "AI消息"
        verbose_name_plural = "AI消息"
        ordering = ["created_at"]
        indexes = [
            # 按会话拉取消息列表（按时间正序展示）
            models.Index(fields=["session", "created_at"], name="idx_chatmsg_session_time"),
        ]

    def __str__(self):
        return f"[{self.role}] {self.content[:30]}"

    @property
    def source_list(self):
        """把逗号分隔的来源转成列表。"""
        if not self.sources:
            return []
        return [s.strip() for s in self.sources.split(",") if s.strip()]


# ===========================================================================
# 大模型提供商配置（用户自定义 API）
# ===========================================================================
class ModelProvider(TimeStampedModel):
    """用户配置的大模型提供商。

    【为什么需要这张表】
        最初大模型配置只能改 .env（AI_PROVIDER / DEEPSEEK_API_KEY …）。
        这在开发机上是够的，但桌面版分发给别人后完全不成立：

            · 使用者拿不到你的 .env；
            · 就算会改，改完还得重启程序；
            · 而且把 Key 写进 .env 或 config.json 对普通用户门槛太高。

        有了这张表，使用者可以在**界面里**选服务商、填自己的 Key、
        点一下测试连通性，立即生效 —— 这才是"用得上"的产品形态。

    【为什么 Key 要单独加密】
        见 apps/ai/crypto.py 的说明：数据库文件可能被拷贝出去，
        明文存 Key 等于把密钥一起发出去。
        这里的 api_key 字段存的是密文（`enc:v1:` 前缀）。

    【一条记录 = 一个可切换的配置】
        · 支持配多个（比如"公司代理的 DeepSeek"和"自己的通义千问"），
        · 同一时刻只有一条 is_active=True，通过 activate() 保证互斥。
    """

    # ---- 服务商类型 ----
    TYPE_DEEPSEEK = "deepseek"
    TYPE_DASHSCOPE = "dashscope"
    TYPE_OLLAMA = "ollama"
    TYPE_OPENAI = "openai"
    TYPE_CHOICES = [
        (TYPE_DEEPSEEK, "DeepSeek"),
        (TYPE_DASHSCOPE, "通义千问（DashScope）"),
        (TYPE_OLLAMA, "本地 Ollama"),
        (TYPE_OPENAI, "OpenAI 兼容（自定义）"),
    ]

    name = models.CharField(
        "配置名称",
        max_length=100,
        help_text="给这套配置起个名字，例如「我的 DeepSeek」",
    )

    provider_type = models.CharField(
        "服务商类型",
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_DEEPSEEK,
        db_index=True,
        help_text="决定默认接口地址与调用协议",
    )

    base_url = models.CharField(
        "接口地址",
        max_length=500,
        blank=True,
        default="",
        help_text="留空则使用该服务商的官方地址；OpenAI 兼容类型必须填",
    )

    model = models.CharField(
        "模型名称",
        max_length=100,
        blank=True,
        default="",
        help_text="例如 deepseek-flash / qwen-plus / llama3.1",
    )

    api_key = models.TextField(
        "API Key（加密存储）",
        blank=True,
        default="",
        help_text="以 enc:v1: 开头的密文；Ollama 本地模型通常不需要",
    )

    is_active = models.BooleanField(
        "当前启用",
        default=False,
        db_index=True,
        help_text="同一时刻只允许一条为 True",
    )

    # 记录最近一次连通性测试，方便界面显示"上次测试失败"
    last_test_ok = models.BooleanField("上次测试是否成功", null=True, blank=True)
    last_test_at = models.DateTimeField("上次测试时间", null=True, blank=True)
    last_test_message = models.CharField(
        "上次测试结果", max_length=300, blank=True, default=""
    )

    class Meta:
        db_table = "ai_modelprovider"
        verbose_name = "大模型配置"
        verbose_name_plural = "大模型配置"
        ordering = ["-is_active", "provider_type", "id"]
        indexes = [
            models.Index(fields=["is_active"], name="idx_provider_active"),
        ]

    def __str__(self):
        return f"{self.name}({self.provider_type})"

    # -----------------------------------------------------------------
    # 便捷属性
    # -----------------------------------------------------------------
    @property
    def effective_base_url(self) -> str:
        """最终使用的接口地址（自定义优先，否则取预设默认值）。"""
        from .providers import preset_base_url

        return (self.base_url or preset_base_url(self.provider_type)).rstrip("/")

    @property
    def effective_model(self) -> str:
        """最终使用的模型名。"""
        from .providers import preset_model

        return self.model or preset_model(self.provider_type)

    def get_api_key(self) -> str:
        """取出解密后的 API Key（**不要**直接序列化这个值）。"""
        from .crypto import decrypt_key

        return decrypt_key(self.api_key)

    def set_api_key(self, plain: str) -> None:
        """加密写入 API Key。"""
        from .crypto import encrypt_key

        self.api_key = encrypt_key(plain)

    def masked_key(self) -> str:
        """给界面展示用的打码 Key。"""
        from .crypto import mask_key

        return mask_key(self.get_api_key())

    # -----------------------------------------------------------------
    # 互斥启用
    # -----------------------------------------------------------------
    @classmethod
    def get_active(cls):
        """取当前启用的配置；没有则返回 None。"""
        return cls.objects.filter(is_active=True).first()

    def activate(self) -> None:
        """把本配置设为唯一启用项。"""
        from django.db import transaction

        with transaction.atomic():
            ModelProvider.objects.exclude(pk=self.pk).filter(
                is_active=True
            ).update(is_active=False)
            if not self.is_active:
                self.is_active = True
                self.save(update_fields=["is_active", "updated_at"])


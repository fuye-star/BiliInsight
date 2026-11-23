# -*- coding: utf-8 -*-
"""大模型提供商（ModelProvider）的服务层。

【为什么把逻辑集中在这里，而不是写在视图里】
    同一套逻辑有三个调用方：

        · HTTP 接口（界面里的增删改查 / 测试连通性）
        · LLM 工厂（get_llm 取当前启用的配置）
        · 启动引导（首次运行从环境变量/配置文件播种一条默认配置）

    写在视图里的话，后两者就得复制一遍。集中到本模块后，
    视图只负责解析参数与包装响应。

【关于 API Key 的三条铁律】
    1. 数据库里存**密文**（apps/ai/crypto.py）
    2. 序列化给前端时**只给打码值**，绝不返回明文
    3. 更新时如果前端没传 key（或传的还是打码值），**保持原值不变**

    第 3 条很容易漏：界面上显示的是 `sk-8****cdef`，
    用户只改了模型名就提交，如果后端把打码值当成新 Key 存进去，
    Key 就被覆盖成无效串了 —— 表现为"改个模型名结果连不上了"。
"""

import logging
import time
from typing import Optional

from django.conf import settings

from .crypto import KeyCryptoError, encrypt_key, is_encrypted
from .llm import LLMError, build_llm_from_provider, reset_llm_cache

logger = logging.getLogger(__name__)


# ===========================================================================
# 预设：每种服务商的默认地址与模型
# ===========================================================================
PROVIDER_PRESETS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "needs_key": True,
        "hint": "官方 OpenAI 兼容接口。模型名填 deepseek-flash"
                "（DeepSeek-V4.1-Flash 是版本名，填了会报模型不存在）。",
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "dashscope": {
        "label": "通义千问（DashScope）",
        "base_url": "",
        "model": "qwen-plus",
        "needs_key": True,
        "hint": "阿里云百炼平台，使用官方 SDK 调用，无需填接口地址。",
        "key_url": "https://bailian.console.aliyun.com/",
    },
    "ollama": {
        "label": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "deepseek-r1:8b",
        "needs_key": False,
        "hint": "本机运行 Ollama 时使用，无需 API Key。"
                "需先执行 ollama pull <模型名>。",
        "key_url": "https://ollama.com/download",
    },
    "openai": {
        "label": "OpenAI 兼容（自定义）",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "needs_key": True,
        "hint": "任何遵循 OpenAI /chat/completions 协议的服务都可以："
                "硅基流动、月之暗面、One-API 中转、vLLM、LM Studio 等。"
                "接口地址请填到 /v1 这一层。",
        "key_url": "",
    },
}

DEFAULT_TYPE = "deepseek"


def preset_base_url(provider_type: str) -> str:
    """取某类型服务商的默认接口地址。"""
    return PROVIDER_PRESETS.get(provider_type or "", {}).get("base_url", "")


def preset_model(provider_type: str) -> str:
    """取某类型服务商的默认模型名。"""
    return PROVIDER_PRESETS.get(provider_type or "", {}).get("model", "")


def preset_list() -> list:
    """给前端下拉框用的预设清单。"""
    return [
        {
            "provider_type": key,
            "label": value["label"],
            "base_url": value["base_url"],
            "model": value["model"],
            "needs_key": value["needs_key"],
            "hint": value["hint"],
            "key_url": value.get("key_url", ""),
        }
        for key, value in PROVIDER_PRESETS.items()
    ]


# ===========================================================================
# 序列化（对外只暴露打码 Key）
# ===========================================================================
def serialize_provider(cfg) -> dict:
    """把配置序列化成前端可直接用的结构。

    ⚠️ 这里**永远不返回明文 Key**，只返回 `api_key_masked`。
    """
    return {
        "id": cfg.pk,
        "name": cfg.name,
        "provider_type": cfg.provider_type,
        "provider_label": PROVIDER_PRESETS.get(cfg.provider_type, {}).get(
            "label", cfg.provider_type
        ),
        "base_url": cfg.base_url,
        "effective_base_url": cfg.effective_base_url,
        "model": cfg.model,
        "effective_model": cfg.effective_model,
        "api_key_masked": cfg.masked_key(),
        "has_key": bool(cfg.get_api_key()),
        "is_active": cfg.is_active,
        "last_test_ok": cfg.last_test_ok,
        "last_test_at": cfg.last_test_at.isoformat() if cfg.last_test_at else None,
        "last_test_message": cfg.last_test_message,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
    }


# ===========================================================================
# 写入辅助
# ===========================================================================
class ProviderConfigError(Exception):
    """配置不合法（由视图层转成 400 响应）。"""


def save_provider(cfg, data: dict, *, partial: bool = False):
    """把前端提交的数据写入配置对象（**不负责保存到数据库**）。

    参数:
        cfg:    ModelProvider 实例（新建时是未保存的对象）
        data:   前端提交的字段
        partial: 为 True 时只更新传入的字段（PATCH 语义）

    异常:
        ProviderConfigError: 字段不合法
        KeyCryptoError:      加密环境不可用
    """
    from .models import ModelProvider

    def _get(field, default=None):
        if field in data:
            return data.get(field)
        return default if partial else default

    # ---- 名称 ----
    if "name" in data or not partial:
        name = str(_get("name", "") or "").strip()
        if not name:
            raise ProviderConfigError("请填写配置名称")
        cfg.name = name[:100]

    # ---- 类型 ----
    if "provider_type" in data or not partial:
        ptype = str(_get("provider_type", DEFAULT_TYPE) or DEFAULT_TYPE).strip()
        valid = {choice[0] for choice in ModelProvider.TYPE_CHOICES}
        if ptype not in valid:
            raise ProviderConfigError(f"不支持的服务商类型：{ptype}")
        cfg.provider_type = ptype

    # ---- 接口地址 / 模型 ----
    if "base_url" in data or not partial:
        cfg.base_url = str(_get("base_url", "") or "").strip()[:500]

    if "model" in data or not partial:
        cfg.model = str(_get("model", "") or "").strip()[:100]

    # ---- API Key ----
    # 【关键】三种情况要区分清楚：
    #   a) 没传 api_key 字段        -> 保持原值（用户只改了别的字段）
    #   b) 传了空字符串             -> 显式清空（Ollama 之类不需要 Key）
    #   c) 传了打码值（含 ****）     -> 视同没传，保持原值
    #   否则用户"只改模型名"就会把 Key 覆盖成 sk-8****cdef 这种废串
    if "api_key" in data:
        raw_key = str(data.get("api_key") or "").strip()
        if "****" in raw_key:
            # 前端回显的是打码值，忽略
            pass
        elif raw_key == "":
            cfg.api_key = ""
        else:
            cfg.api_key = encrypt_key(raw_key)

    # ---- 启用状态 ----
    if data.get("is_active"):
        cfg.is_active = True

    # ---- 基本可用性校验 ----
    _validate(cfg, partial=partial)

    return cfg


def _validate(cfg, *, partial: bool = False) -> None:
    """保存前的基本校验（不发起网络请求）。"""
    from .models import ModelProvider

    ptype = cfg.provider_type

    if ptype == ModelProvider.TYPE_OPENAI:
        # 自定义服务商没有默认地址，必须自己填
        if not (cfg.base_url or "").strip():
            raise ProviderConfigError(
                "「OpenAI 兼容」类型必须填写接口地址（例如 https://xxx/v1）"
            )
        if not (cfg.model or "").strip():
            raise ProviderConfigError("「OpenAI 兼容」类型必须填写模型名称")

    if ptype == ModelProvider.TYPE_OLLAMA:
        # 本地模型不校验 Key，但地址要点得通才有意义（放到测试连接里做）
        if not (cfg.base_url or "").strip() and not preset_base_url(ptype):
            raise ProviderConfigError("请填写 Ollama 服务地址")

    # 云端服务商需要 Key（允许先保存后补，但给出明确提示由视图层决定）
    needs_key = PROVIDER_PRESETS.get(ptype, {}).get("needs_key", True)
    if needs_key and not cfg.get_api_key() and not getattr(cfg, "pk", None):
        # 新建时没填 Key：允许保存（用户可能稍后填），但不设为启用
        logger.info("新建的 Provider「%s」未填写 API Key", cfg.name)


# ===========================================================================
# 连通性测试
# ===========================================================================
def _describe_unavailable(cfg) -> str:
    """解释为什么这个配置不可用（给用户看的）。"""
    from .models import ModelProvider

    if cfg.provider_type == ModelProvider.TYPE_OLLAMA:
        return (
            "无法连接本地 Ollama：请确认已启动 Ollama 服务"
            f"（{cfg.effective_base_url}），且已执行 ollama pull {cfg.effective_model}"
        )

    if not cfg.get_api_key():
        return "尚未填写 API Key"

    if cfg.provider_type == ModelProvider.TYPE_DASHSCOPE:
        return "通义千问 SDK 不可用，请确认已安装 dashscope"

    return "配置不完整（请检查接口地址与模型名称）"


def test_provider(cfg) -> dict:
    """实际发一次极小请求，验证 Key / 地址 / 模型是否都正确。

    返回:
        {"ok": bool, "message": str, "latency_ms": int}

    【为什么用"真实调用"而不是只做连通性探测】
        常见失败原因有三种，只有真实调用能全都覆盖：

            1. 地址不通 / Key 无效      —— ping 也能发现
            2. Key 有效但余额不足       —— 只有真实调用才返回 402/403
            3. 模型名填错               —— 只有真实调用才返回 model not found

        第 3 种恰恰是最常见的（比如把 deepseek-flash 写成版本名）。
        因此这里发一个 max_tokens=16 的最小请求，成本可以忽略。
    """
    started = time.monotonic()

    try:
        llm = build_llm_from_provider(cfg)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"配置无法解析：{exc}", "latency_ms": 0}

    if llm is None:
        return {"ok": False, "message": "配置无法解析", "latency_ms": 0}

    if not llm.available:
        elapsed = _elapsed_ms(started)
        return {"ok": False, "message": _describe_unavailable(cfg), "latency_ms": elapsed}

    try:
        reply = llm.generate("收到请回复 ok", max_tokens=16, temperature=0.0)
    except LLMError as exc:
        return {
            "ok": False,
            "message": str(exc)[:280],
            "latency_ms": _elapsed_ms(started),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"{type(exc).__name__}: {exc}"[:280],
            "latency_ms": _elapsed_ms(started),
        }

    elapsed = _elapsed_ms(started)
    snippet = (reply or "").strip().replace("\n", " ")[:40]
    return {
        "ok": True,
        "message": f"连接成功（{elapsed} ms）" + (f"，模型回复：{snippet}" if snippet else ""),
        "latency_ms": elapsed,
    }


def _elapsed_ms(started: float) -> int:
    """把 perf_counter 的差值转成毫秒。"""
    return int((time.monotonic() - started) * 1000)


# ===========================================================================
# 首次启动播种
# ===========================================================================
def ensure_default_provider() -> Optional[object]:
    """没有任何配置时，从环境变量 / config.json 播种一条默认配置。

    返回:
        新建的 ModelProvider；无需播种时返回 None

    【为什么需要它】
        升级到"界面配置"之后，老用户（以及开发机）的 Key 还在
        .env 或桌面版的 config.json 里。如果不管，打开界面会看到
        "未配置模型提供商"，而实际上他早就配过了 —— 体验倒退。

        因此首次进入时把已有配置**迁移成一条数据库记录**并设为启用，
        之后以数据库为准。
    """
    from .models import ModelProvider

    try:
        if ModelProvider.objects.exists():
            return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Provider 表不可用，跳过播种：%s", exc)
        return None

    deepseek_key = (getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
    dashscope_key = (getattr(settings, "DASHSCOPE_API_KEY", "") or "").strip()

    cfg = None
    if deepseek_key:
        cfg = ModelProvider(
            name="DeepSeek（来自已有配置）",
            provider_type=ModelProvider.TYPE_DEEPSEEK,
            model=getattr(settings, "DEEPSEEK_MODEL", "deepseek-flash"),
            base_url=getattr(settings, "DEEPSEEK_BASE_URL", "") or "",
        )
        cfg.api_key = _safe_encrypt(deepseek_key)
    elif dashscope_key:
        cfg = ModelProvider(
            name="通义千问（来自已有配置）",
            provider_type=ModelProvider.TYPE_DASHSCOPE,
            model=getattr(settings, "AI_MODEL", "qwen-plus"),
        )
        cfg.api_key = _safe_encrypt(dashscope_key)

    if cfg is None:
        return None

    cfg.is_active = True
    cfg.save()
    logger.info("已从已有配置播种默认大模型配置：%s", cfg.name)
    reset_llm_cache()
    return cfg


def _safe_encrypt(plain: str) -> str:
    """加密 Key；加密不可用时返回空串（宁可没有配置，也不存明文）。"""
    try:
        return encrypt_key(plain)
    except KeyCryptoError as exc:
        logger.error("播种默认配置时加密失败，已跳过：%s", exc)
        return ""


def any_provider_exists() -> bool:
    """是否已存在任何 Provider 配置。"""
    from .models import ModelProvider

    try:
        return ModelProvider.objects.exists()
    except Exception:  # noqa: BLE001
        return False

# -*- coding: utf-8 -*-
"""
LLM 工厂 —— 多 Provider 切换。

【为什么自己封装而不用 LangChain 的封装】
  1. langchain-community 已官方标记 sunset（导入时会打弃用警告），
     不适合作为新项目的核心依赖
  2. 我们只需要"发请求 + 收流式响应"两件事，
     直接调 REST 接口代码更短、行为更透明、出问题好排查
  3. 少一层抽象 = 少一个答辩现场失效的环节

【三个 Provider】
    ┌──────────────────────────────────────────────────────────┐
    │ ollama    本地大模型，免费、可离线，数据不出本机          │  默认
    │ dashscope 通义千问，效果好，需 API Key + 外网             │
    │ fallback  无大模型兜底：直接用检索结果拼装回答             │
    └──────────────────────────────────────────────────────────┘

【为什么必须有 fallback】
本项目反复遇到"外部依赖不可用"（paddlenlp 装不上、Ollama 服务未启动）。
AI 助手是答辩的核心加分项，绝不能因为模型服务没起来就整个功能失效。
fallback 用检索到的真实数据组织成结构化回答——
虽然不如大模型自然，但**数据是真实的、结论是可信的**，
比报错或空白强得多，而且能诚实告诉用户"当前未接入大模型"。

【流式输出】
大模型逐字返回能显著改善体感（首字延迟从数秒降到几百毫秒）。
两个 Provider 都支持 SSE 流式，统一抽象成 generate_stream() 生成器。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """大模型调用失败。"""


# ===========================================================================
# 抽象接口
# ===========================================================================
class BaseLLM(ABC):
    """大模型抽象基类。

    子类需实现 generate()；流式能力由 generate_stream() 提供默认降级实现
    （一次性生成后按句切分逐段吐出），支持流式的子类应覆写以获得更好体验。
    """

    provider_name = "base"

    def __init__(self):
        """探测可用性。"""
        self.available = self._check_dependency()

    @abstractmethod
    def _check_dependency(self) -> bool:
        """检查依赖（服务是否在跑、API Key 是否配置）。"""
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """一次性生成完整回答。

        参数:
            prompt:      用户提示词（含检索到的上下文）
            system:      系统提示词（定义角色与约束）
            temperature: 采样温度，越高越随机
            max_tokens:  最大生成长度

        返回:
            模型生成的文本

        异常:
            LLMError: 调用失败
        """
        raise NotImplementedError

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """流式生成（逐段 yield 文本片段）。

        默认实现：调用一次 generate() 再按标点切分成多段，
        模拟流式效果。支持真流式的子类应覆写。
        """
        text = self.generate(
            prompt, system=system, temperature=temperature, max_tokens=max_tokens
        )
        yield from _split_for_streaming(text)

    def describe(self) -> dict:
        """返回 Provider 描述，用于接口与前端提示。"""
        return {
            "provider": self.provider_name,
            "available": self.available,
        }


def _split_for_streaming(text: str, chunk_size: int = 12) -> Iterator[str]:
    """把整段文本切成小块，用于模拟流式输出。

    切分点优先选标点，让"逐句出现"的观感更自然。
    """
    if not text:
        return

    buffer = ""
    for char in text:
        buffer += char
        # 遇到句末标点，或缓冲区够长，就吐出一次
        if char in "。！？；\n，、" or len(buffer) >= chunk_size:
            yield buffer
            buffer = ""

    if buffer:
        yield buffer


# ===========================================================================
# 1. Ollama 本地大模型
# ===========================================================================
class OllamaLLM(BaseLLM):
    """通过 Ollama 调用本地大模型。

    【本机情况】
    已下载 deepseek-r1:8b（4.87GB），但 Ollama 服务需要单独安装启动。
    参见 README 7.3 的启用步骤。

    启用方式：
        .env 设置：AI_PROVIDER=ollama
    模型选择：OLLAMA_MODEL=deepseek-r1:8b
    """

    provider_name = "ollama"

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        """初始化。"""
        from django.conf import settings

        self.base_url = (
            base_url or getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        ).rstrip("/")
        self.model = model or getattr(settings, "OLLAMA_MODEL", "deepseek-r1:8b")

        super().__init__()

    def _check_dependency(self) -> bool:
        """探测服务与模型。"""
        import requests

        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]

            if not models:
                logger.warning("Ollama 已运行但无模型，请执行：ollama pull %s", self.model)
                return False

            matched = any(
                m == self.model or m.startswith(f"{self.model}:") for m in models
            )
            if not matched:
                logger.warning(
                    "Ollama 中未找到 %s，可用：%s", self.model, ", ".join(models)
                )
                return False

            return True
        except Exception as exc:
            logger.debug("Ollama 不可用：%s", exc)
            return False

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """调用 /api/generate（非流式）。"""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=180
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:
            raise LLMError(f"Ollama 调用失败：{exc}") from exc

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """真流式：Ollama 支持逐块返回 JSON 行。"""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        try:
            with requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                stream=True,
                timeout=180,
            ) as resp:
                resp.raise_for_status()
                # Ollama 流式响应是"每行一个 JSON 对象"
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    piece = chunk.get("response", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except Exception as exc:
            raise LLMError(f"Ollama 流式调用失败：{exc}") from exc


# ===========================================================================
# 2. 通义千问（DashScope）
# ===========================================================================
class DashScopeLLM(BaseLLM):
    """通过 DashScope 调用通义千问。

    启用方式：
        .env 设置：
            AI_PROVIDER=dashscope
            DASHSCOPE_API_KEY=sk-xxxx
            AI_MODEL=qwen-plus
    """

    provider_name = "dashscope"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """初始化。

        参数:
            model:   模型名，默认读 settings.AI_MODEL（qwen-plus）
            api_key: API Key；**留空时回落到 settings**，
                     这样"界面里配置的 Provider"与"环境变量配置"两条路都能走。
        """
        from django.conf import settings

        self.model = model or getattr(settings, "AI_MODEL", "qwen-plus")
        self.api_key = api_key or getattr(settings, "DASHSCOPE_API_KEY", "")

        super().__init__()

    def _check_dependency(self) -> bool:
        """检查 SDK 与 API Key。"""
        if not self.api_key:
            logger.debug("未配置 DASHSCOPE_API_KEY")
            return False
        try:
            import dashscope  # noqa: F401

            return True
        except ImportError:
            logger.debug("dashscope SDK 未安装")
            return False

    def _build_messages(self, prompt: str, system: str) -> list[dict]:
        """组装 DashScope 的 messages 格式。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """调用通义千问（非流式）。"""
        from dashscope import Generation

        try:
            resp = Generation.call(
                model=self.model,
                messages=self._build_messages(prompt, system),
                result_format="message",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=self.api_key,
            )
        except Exception as exc:
            raise LLMError(f"DashScope 调用异常：{exc}") from exc

        if resp.status_code != 200:
            raise LLMError(f"DashScope 返回错误 {resp.status_code}：{resp.message}")

        try:
            return resp.output.choices[0].message.content.strip()
        except (AttributeError, IndexError, KeyError) as exc:
            raise LLMError(f"解析 DashScope 响应失败：{exc}") from exc

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """真流式：DashScope 支持 incremental_output。"""
        from dashscope import Generation

        try:
            responses = Generation.call(
                model=self.model,
                messages=self._build_messages(prompt, system),
                result_format="message",
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=self.api_key,
                stream=True,
                incremental_output=True,
            )

            for resp in responses:
                if resp.status_code != 200:
                    raise LLMError(f"DashScope 流式错误 {resp.status_code}：{resp.message}")
                try:
                    piece = resp.output.choices[0].message.content
                    if piece:
                        yield piece
                except (AttributeError, IndexError, KeyError):
                    continue
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"DashScope 流式调用失败：{exc}") from exc


# ===========================================================================
# 3. DeepSeek 官方 API（OpenAI 兼容格式）
# ===========================================================================
class DeepSeekLLM(BaseLLM):
    """通过 DeepSeek 官方 API 调用大模型。

    【为什么直接用 REST 而不装 openai SDK】
    DeepSeek 的接口是 **OpenAI 兼容格式**，用 requests 发一个 POST
    就能跑通，无需引入 openai 包。这与本项目"减少依赖、降低答辩现场风险"
    的原则一致（requests 已是既有依赖）。

    【⚠️ 模型名的重要提醒】
    官方文档明确：
        Use `deepseek-flash` as the model name.
    而 `DeepSeek-V4.1-Flash` 是**版本名，不是 API 模型名**。
    填错会直接报模型不存在。旧名 `deepseek-v4-flash` 对应的模型已退役，
    仅作兼容转发，不应使用。

    【思考模式】
    该模型默认开启 thinking 模式（会输出思维链）。
    思维链对终端用户是噪声，因此这里显式传
        "thinking": {"type": "disabled"}
    关闭它。注意：老版本接口可能不认这个参数，
    SDK 会忽略未知字段，因此不影响兼容性。

    启用方式：
        .env 设置：
            AI_PROVIDER=deepseek
            DEEPSEEK_API_KEY=sk-xxxx
            DEEPSEEK_MODEL=deepseek-flash
    """

    provider_name = "deepseek"

    #: 报错文案里显示的名字（子类可覆写，避免自定义服务商报错时显示成 DeepSeek）
    display_name = "DeepSeek"

    #: 官方 OpenAI 兼容接口地址
    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """初始化。

        参数:
            model:    模型名，默认 deepseek-flash
            api_key:  API Key，默认读 settings.DEEPSEEK_API_KEY
            base_url: 接口地址，默认官方地址
        """
        from django.conf import settings

        # 注意默认值是 "deepseek-flash" 而不是 "deepseek-v4.1-flash"
        self.model = model or getattr(settings, "DEEPSEEK_MODEL", "deepseek-flash")
        self.api_key = api_key or getattr(settings, "DEEPSEEK_API_KEY", "")
        self.base_url = (
            base_url
            or getattr(settings, "DEEPSEEK_BASE_URL", self.DEFAULT_BASE_URL)
        ).rstrip("/")

        super().__init__()

    def _check_dependency(self) -> bool:
        """检查 API Key 是否配置。"""
        if not self.api_key:
            logger.debug("未配置 DEEPSEEK_API_KEY，DeepSeek Provider 不可用")
            return False

        # 提前校验模型名，避免填了版本名导致调用时才报错
        if self.model in ("deepseek-v4.1-flash", "deepseek-v4-flash"):
            logger.warning(
                "模型名 %r 可能不正确。DeepSeek 官方要求使用 'deepseek-flash'"
                "（DeepSeek-V4.1-Flash 是版本名而非 API 模型名）。"
                "旧名 deepseek-v4-flash 对应的模型已退役。",
                self.model,
            )
        return True

    def _headers(self) -> dict:
        """构造请求头。"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _build_payload(
        self,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        """构造 OpenAI 格式的请求体。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            # 显式关闭思考模式：思维链对终端用户是噪声
            "thinking": {"type": "disabled"},
        }

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """非流式调用。"""
        import requests

        payload = self._build_payload(prompt, system, temperature, max_tokens, False)

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=180,
            )
        except Exception as exc:
            raise LLMError(f"{self.display_name} 请求异常：{exc}") from exc

        if resp.status_code != 200:
            # 把官方返回的错误信息透出来，便于定位（如模型名错误）
            raise LLMError(
                f"{self.display_name} 返回 HTTP {resp.status_code}：{resp.text[:300]}"
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"解析 DeepSeek 响应失败：{exc}") from exc

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """流式调用（SSE 格式，与 OpenAI 一致）。"""
        import requests

        payload = self._build_payload(prompt, system, temperature, max_tokens, True)

        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    raise LLMError(
                        f"{self.display_name} 流式返回 HTTP {resp.status_code}：{resp.text[:300]}"
                    )

                for line in resp.iter_lines():
                    if not line:
                        continue

                    text = line.decode("utf-8").strip()

                    # SSE 以 "data: " 开头，"[DONE]" 表示结束
                    if not text.startswith("data:"):
                        continue

                    data_str = text[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    try:
                        delta = chunk["choices"][0].get("delta", {})
                        piece = delta.get("content")
                        # 推理模型的思维链在 reasoning_content 字段里，这里刻意忽略
                        if piece:
                            yield piece
                    except (KeyError, IndexError):
                        continue
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"{self.display_name} 流式调用失败：{exc}") from exc


# ===========================================================================
# 3.5 OpenAI 兼容 Provider（用户自定义服务商）
# ===========================================================================
class OpenAICompatibleLLM(DeepSeekLLM):
    """任何遵循 OpenAI `/chat/completions` 协议的服务商。

    【为什么单独一个类，而不是复用 DeepSeekLLM】
        DeepSeek 的请求体里带了一个 DeepSeek 专有参数：

            "thinking": {"type": "disabled"}

        它用来关闭思维链（对终端用户是噪声）。DeepSeek 会忽略/接受它，
        但**严格的第三方网关会因为这个未知字段直接返回 400** ——
        用户填了自己的中转地址却一直报错，很难想到是这个原因。

        因此这个类只覆盖 `_build_payload`，去掉该参数，其余逻辑
        （请求、流式解析、错误提示）完全复用父类。

    【适用范围】
        用户可能填写：公司内网网关、硅基流动、月之暗面、One-API/New-API
        中转、vLLM / LM Studio / LocalAI 等本地推理服务的 OpenAI 兼容端点。

    启用方式：界面「模型提供商」里选择「OpenAI 兼容（自定义）」，
    填接口地址（到 /v1 那一层）与模型名即可。
    """

    provider_name = "openai"

    #: 报错时用中性的名字，不要误导用户以为用的是 DeepSeek
    display_name = "模型服务"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """初始化。

        参数:
            model:    必填（不同服务商模型名差异很大，没有合理默认值）
            api_key:  API Key；部分本地服务不校验，允许为空
            base_url: 必填，OpenAI 兼容端点，例如 https://xxx/v1

        【⚠️ 为什么这里不调用 super().__init__()】
            DeepSeekLLM 的构造函数里有这样一行：

                self.api_key = api_key or getattr(settings, "DEEPSEEK_API_KEY", "")

            也就是说：**传入空 Key 时会自动回落到环境变量里的 DeepSeek 密钥**。
            对 DeepSeek 自己这是我们想要的行为；
            但对"OpenAI 兼容"的任意第三方地址，这会造成一个真实的泄密问题：

                用户配置了本地 LM Studio（不需要 Key）
                -> api_key 传空
                -> 回落到 settings.DEEPSEEK_API_KEY
                -> 程序把 DeepSeek 的密钥当作 Bearer token
                   发给了 http://127.0.0.1:1234（或某个陌生中转服务）

            因此这里绕开父类构造函数，**严格只使用传入值**，
            绝不去翻环境变量。这条规则由 tests_provider 里的
            `test_missing_key_is_allowed` 锁定。
        """
        self.model = model or ""
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")

        # 跳过 DeepSeekLLM.__init__，直接调用基类完成可用性检查
        BaseLLM.__init__(self)

    def _check_dependency(self) -> bool:
        """OpenAI 兼容服务的校验比 DeepSeek 宽松。

        · 必须有接口地址（否则不知道往哪发）
        · 有模型名（没有默认值可用）
        · Key 可以为空 —— 本地推理服务（LM Studio、LocalAI）通常不校验
        """
        if not self.base_url:
            logger.debug("OpenAI 兼容 Provider 未配置接口地址")
            return False
        if not self.model:
            logger.debug("OpenAI 兼容 Provider 未配置模型名")
            return False
        if not self.api_key:
            logger.info(
                "OpenAI 兼容 Provider（%s）未配置 API Key，"
                "将不带鉴权头请求（适用于本地推理服务）",
                self.base_url,
            )
        return True

    def _headers(self) -> dict:
        """构造请求头：没有 Key 时不发 Authorization，避免被本地服务拒绝。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(
        self,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        """标准 OpenAI 请求体（**不包含** DeepSeek 专有的 thinking 参数）。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }


# ===========================================================================
# 4. Fallback：无大模型时的检索式回答
# ===========================================================================
class RetrievalOnlyLLM(BaseLLM):
    """无大模型兜底：用检索结果直接组织回答。

    【设计动机】
    外部模型服务不可用时（Ollama 未安装、无 API Key），
    AI 助手不应该报错或返回空白。这个兜底方案把检索到的**真实视频数据**
    组织成结构化回答，并明确标注"当前未接入大模型"。

    这样：
      · 数据是真实的（来自数据库与向量检索）
      · 用户不会被误导（明确说明生成方式）
      · 答辩时即使断网也能演示完整链路
    """

    provider_name = "fallback"

    def __init__(self):
        """兜底方案永远可用。"""
        super().__init__()
        # 由 rag 模块注入的检索结果（避免在类里耦合向量库）
        self._context_hits: list[dict] = []

    def _check_dependency(self) -> bool:
        """永远可用。"""
        return True

    def set_context(self, hits: list[dict]) -> None:
        """注入检索结果，供 generate 组装回答。

        参数:
            hits: vector_store.search() 的返回值
        """
        self._context_hits = hits or []

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """用检索结果拼装回答。"""
        return self._compose()

    def generate_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """分块吐出，模拟流式观感。"""
        yield from _split_for_streaming(self._compose(), chunk_size=20)

    def _compose(self) -> str:
        """把检索命中组织成可读回答。"""
        if not self._context_hits:
            return (
                "抱歉，我没有在视频库中找到相关内容。\n\n"
                "建议：\n"
                "1. 换一个更具体的说法，例如「科技区的芯片评测」\n"
                "2. 确认已构建向量索引：`python manage.py build_index`\n"
                "3. 确认数据库中已有视频数据：`python manage.py seed_demo`"
            )

        lines = [
            "⚠️ 当前未接入大模型，以下是根据检索到的真实数据为你整理的推荐：",
            "",
        ]

        for i, hit in enumerate(self._context_hits, start=1):
            title = hit.get("title", "未知标题")
            partition = hit.get("partition") or "未分类"
            up_name = hit.get("up_name") or "未知UP主"
            view = hit.get("view_count", 0)
            similarity = hit.get("similarity", 0.0)

            lines.append(
                f"{i}. 【{partition}】{title}\n"
                f"   UP主：{up_name}　播放量：{view:,}　相关度：{similarity:.0%}\n"
                f"   BV号：{hit.get('bvid', '')}"
            )

        lines.append("")
        lines.append(
            "💡 接入大模型后可获得自然语言的分析与推荐，"
            "请参考 README 7.2/7.3 配置通义千问或本地 Ollama。"
        )

        return "\n".join(lines)


# ===========================================================================
# 工厂
# ===========================================================================
_LLM_CACHE: dict[str, BaseLLM] = {}


# ===========================================================================
# 按「用户配置的 Provider」构造实例
# ===========================================================================
def build_llm_from_provider(cfg) -> Optional[BaseLLM]:
    """按数据库里的一条 ModelProvider 配置构造 LLM 实例。

    参数:
        cfg: apps.ai.models.ModelProvider 实例

    返回:
        BaseLLM 实例；配置类型异常时返回 None
    """
    from .models import ModelProvider

    api_key = cfg.get_api_key()
    base_url = (cfg.effective_base_url or "").rstrip("/")
    model = cfg.effective_model

    if cfg.provider_type == ModelProvider.TYPE_OLLAMA:
        # 本地模型不需要 Key，地址留空则回落到 settings.OLLAMA_BASE_URL
        return OllamaLLM(model=model, base_url=base_url or None)

    if cfg.provider_type == ModelProvider.TYPE_DASHSCOPE:
        return DashScopeLLM(model=model, api_key=api_key)

    if cfg.provider_type == ModelProvider.TYPE_OPENAI:
        return OpenAICompatibleLLM(model=model, api_key=api_key, base_url=base_url)

    # 默认按 DeepSeek 官方接口处理
    return DeepSeekLLM(model=model, api_key=api_key, base_url=base_url or None)


def _get_llm_from_db(*, refresh: bool = False) -> Optional[BaseLLM]:
    """取「界面里当前启用」的那个 Provider 实例。

    返回:
        BaseLLM 实例；**没有配置时返回 None**，由调用方回落到 settings

    【缓存键为什么带 updated_at】
        使用者可能在界面里改 Key 或换模型。若只按固定键缓存，
        改完必须依赖调用方记得调 reset_llm_cache()，漏一次就会出现
        "改了配置但不生效"的诡异现象。
        把 updated_at 放进缓存键后，**任何一次保存都会自动失效**，
        不依赖调用方的自觉。

    【为什么要吞掉异常】
        这个函数可能在数据库尚未迁移完成时被调用
        （例如桌面版首次启动的引导阶段），
        此时查表会抛 OperationalError。那种情况下返回 None、
        回落到 settings 才是正确行为，而不是让整个 AI 模块崩掉。
    """
    try:
        from .models import ModelProvider

        cfg = ModelProvider.get_active()
    except Exception as exc:  # noqa: BLE001
        logger.debug("读取数据库 Provider 配置失败（可能尚未迁移）：%s", exc)
        return None

    if cfg is None:
        return None

    stamp = cfg.updated_at.timestamp() if cfg.updated_at else 0
    cache_key = f"db:{cfg.pk}:{stamp}"

    if not refresh and cache_key in _LLM_CACHE:
        return _LLM_CACHE[cache_key]

    try:
        llm = build_llm_from_provider(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("按配置 %s 构造大模型失败：%s", cfg.name, exc)
        return None

    if llm is None:
        return None

    logger.info(
        "使用界面配置的大模型：%s（类型=%s，模型=%s，可用=%s）",
        cfg.name, cfg.provider_type, llm.model, llm.available,
    )
    _LLM_CACHE[cache_key] = llm
    return llm


def get_llm(provider: Optional[str] = None, *, refresh: bool = False) -> BaseLLM:
    """按配置返回大模型实例。

    参数:
        provider: 指定类型（ollama / dashscope / deepseek / openai / fallback）；
                  **不传时优先使用界面里配置的 Provider**
        refresh:  忽略缓存重建实例

    返回:
        BaseLLM 实例

    【配置优先级（重要）】
        ① 界面「模型提供商」里启用的那条（数据库，用户自己填的 Key）
        ② 调用方显式指定的 provider
        ③ settings.AI_PROVIDER（.env，开发/部署用）
        ④ 逐级降级 -> fallback（检索式回答）

    这样设计的原因：桌面版分发给别人后，环境变量那条路等于不存在，
    使用者唯一能操作的就是界面。因此界面配置必须**优先级最高**。

    【降级链路】
    ollama 不可用 -> 尝试 dashscope -> 仍不可用 -> fallback
    保证调用方永远能拿到一个可用的实例，不用写一堆 if。
    """
    from django.conf import settings

    # ① 界面配置优先
    if provider is None:
        db_llm = _get_llm_from_db(refresh=refresh)
        if db_llm is not None:
            return db_llm

    # ②③ 回落到显式指定 / settings
    name = (provider or getattr(settings, "AI_PROVIDER", "ollama")).strip().lower()

    if not refresh and name in _LLM_CACHE:
        return _LLM_CACHE[name]

    provider_map = {
        "ollama": OllamaLLM,
        "dashscope": DashScopeLLM,
        "deepseek": DeepSeekLLM,
        "openai": OpenAICompatibleLLM,
        "fallback": RetrievalOnlyLLM,
    }
    llm_class = provider_map.get(name)

    if llm_class is None:
        logger.warning("未知的 AI Provider %r，使用 fallback", name)
        llm_class = RetrievalOnlyLLM

    llm = llm_class()

    # 逐级降级：依次尝试其余云端 Provider，最后退到 fallback
    if not llm.available:
        logger.warning("Provider %s 不可用，尝试降级", name)

        # 按成本与可达性排序尝试
        for alt_name, alt_class in (
            ("deepseek", DeepSeekLLM),
            ("dashscope", DashScopeLLM),
        ):
            if alt_name == name:
                continue
            alt = alt_class()
            if alt.available:
                logger.info("已降级到 %s", alt_name)
                _LLM_CACHE[name] = alt
                return alt

        logger.warning("无可用大模型，降级到 fallback（检索式回答）")
        llm = RetrievalOnlyLLM()

    _LLM_CACHE[name] = llm
    return llm


def reset_llm_cache() -> None:
    """清空实例缓存（切换配置后调用）。"""
    _LLM_CACHE.clear()

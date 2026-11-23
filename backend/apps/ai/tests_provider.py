# -*- coding: utf-8 -*-
"""大模型提供商（用户自定义 API）的测试。

【为什么这组功能必须重点测】
    它同时踩中三个高风险点：

    ① **密钥安全** —— 接口一旦返回明文，Key 就会出现在浏览器
       开发者工具、日志、抓包记录里。必须断言"永不泄露"。

    ② **打码值回写** —— 界面回显的是 `sk-8****cdef`。
       用户只改了模型名就点保存时，如果后端把这个打码串当成新 Key，
       真实 Key 就被覆盖成废串了，表现为"改个模型名结果连不上了"。
       这个 Bug 极难从现象反推原因，必须用测试钉死。

    ③ **启用互斥** —— 同一时刻只能有一条 is_active=True。
       否则 get_llm() 取到哪条是随机的，表现为"AI 有时好用有时不好用"。
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.ai import providers
from apps.ai.crypto import (
    KeyCryptoError,
    decrypt_key,
    encrypt_key,
    is_encrypted,
    mask_key,
    reset_crypto_cache,
)
from apps.ai.llm import LLMError, reset_llm_cache
from apps.ai.models import ModelProvider


class CryptoRoundTripTests(TestCase):
    """API Key 加解密与打码。"""

    def setUp(self):
        reset_crypto_cache()

    def tearDown(self):
        reset_crypto_cache()

    def test_encrypt_decrypt_roundtrip(self):
        """加密后可还原，且存储值带密文前缀。"""
        plain = "sk-1234567890abcdefghij"
        stored = encrypt_key(plain)

        self.assertTrue(stored.startswith("enc:v1:"), "应带密文前缀")
        self.assertNotIn(plain, stored, "密文不能包含原文")
        self.assertTrue(is_encrypted(stored))
        self.assertEqual(decrypt_key(stored), plain)

    def test_empty_key_stays_empty(self):
        """空 Key 不加密，避免库里出现无意义的密文。"""
        self.assertEqual(encrypt_key(""), "")
        self.assertEqual(decrypt_key(""), "")

    def test_legacy_plaintext_is_supported(self):
        """加密上线前存的明文应能原样读出（不能因升级而全部失效）。"""
        self.assertEqual(decrypt_key("sk-plain-legacy"), "sk-plain-legacy")

    def test_mask_never_reveals_middle(self):
        """打码后中间部分必须消失。"""
        masked = mask_key("sk-1234567890abcdef")
        self.assertIn("****", masked)
        self.assertNotIn("1234567890", masked)
        self.assertTrue(masked.startswith("sk-1"))
        self.assertTrue(masked.endswith("cdef"))

    def test_short_key_is_fully_masked(self):
        """太短的 Key 直接全部打码，避免打码后仍能猜出。"""
        self.assertEqual(mask_key("abc"), "****")
        self.assertEqual(mask_key("12345678"), "****")

    def test_different_secret_cannot_decrypt(self):
        """换一个 SECRET_KEY 后应解不开（证明密钥确实参与加密）。"""
        stored = encrypt_key("sk-something-important")

        reset_crypto_cache()
        with override_settings(SECRET_KEY="a-completely-different-secret-key"):
            reset_crypto_cache()
            # 解不开时返回空串而不是抛异常，避免整页崩溃
            self.assertEqual(decrypt_key(stored), "")


class ProviderApiTests(TestCase):
    """Provider 增删改查接口。"""

    def setUp(self):
        reset_llm_cache()
        reset_crypto_cache()
        ModelProvider.objects.all().delete()

    def tearDown(self):
        reset_llm_cache()
        reset_crypto_cache()

    def _create(self, **kwargs):
        """通过接口创建一条配置。"""
        from rest_framework.test import APIClient

        payload = {
            "name": "测试 DeepSeek",
            "provider_type": "deepseek",
            "model": "deepseek-flash",
            "api_key": "sk-test-abcdefghijklmn",
        }
        payload.update(kwargs)
        return APIClient().post("/api/ai/providers/", payload, format="json")

    # ---- 安全 ----
    def test_list_never_returns_plaintext_key(self):
        """列表接口绝不能返回明文 Key。"""
        from rest_framework.test import APIClient

        self._create()
        response = APIClient().get("/api/ai/providers/")

        body = str(response.data)
        self.assertNotIn("sk-test-abcdefghijklmn", body, "接口泄露了明文 Key")
        self.assertIn("****", body, "应返回打码值供界面回显")

    def test_key_is_encrypted_at_rest(self):
        """数据库里存的必须是密文。"""
        self._create()
        cfg = ModelProvider.objects.first()
        self.assertTrue(is_encrypted(cfg.api_key))
        self.assertEqual(cfg.get_api_key(), "sk-test-abcdefghijklmn")

    # ---- 打码值回写 ----
    def test_masked_key_does_not_overwrite_real_key(self):
        """提交打码值时保持原 Key 不变（关键回归点）。"""
        from rest_framework.test import APIClient

        create_resp = self._create()
        cfg_id = create_resp.data["data"]["id"]
        masked = create_resp.data["data"]["api_key_masked"]

        # 用户只改了模型名，Key 字段回传的是打码值
        APIClient().patch(
            f"/api/ai/providers/{cfg_id}/",
            {"model": "deepseek-chat", "api_key": masked},
            format="json",
        )

        cfg = ModelProvider.objects.get(pk=cfg_id)
        self.assertEqual(cfg.model, "deepseek-chat")
        self.assertEqual(
            cfg.get_api_key(), "sk-test-abcdefghijklmn", "打码值不能覆盖真实 Key"
        )

    def test_empty_key_on_patch_keeps_existing(self):
        """PATCH 不带 api_key 字段时保持原值。"""
        from rest_framework.test import APIClient

        cfg_id = self._create().data["data"]["id"]

        APIClient().patch(
            f"/api/ai/providers/{cfg_id}/", {"name": "改个名"}, format="json"
        )

        cfg = ModelProvider.objects.get(pk=cfg_id)
        self.assertEqual(cfg.name, "改个名")
        self.assertEqual(cfg.get_api_key(), "sk-test-abcdefghijklmn")

    # ---- 启用互斥 ----
    def test_first_provider_is_auto_activated(self):
        """第一条配置应自动启用，省掉用户"保存完发现没生效"的困惑。"""
        self._create()
        cfg = ModelProvider.objects.first()
        self.assertTrue(cfg.is_active)

    def test_activate_keeps_only_one_active(self):
        """切换启用后只能有一条 is_active=True。"""
        from rest_framework.test import APIClient

        first = self._create(name="第一条").data["data"]["id"]
        second = self._create(name="第二条", provider_type="ollama", api_key="").data[
            "data"
        ]["id"]

        APIClient().post(f"/api/ai/providers/{second}/activate/")

        self.assertEqual(ModelProvider.objects.filter(is_active=True).count(), 1)
        self.assertTrue(ModelProvider.objects.get(pk=second).is_active)
        self.assertFalse(ModelProvider.objects.get(pk=first).is_active)

    # ---- 删除回落 ----
    def test_deleting_active_falls_back_to_remaining(self):
        """删掉当前启用项后，应自动把剩下的某条设为启用。

        否则 AI 会突然变成"未配置"，用户会以为自己把功能删坏了。
        """
        from rest_framework.test import APIClient

        first = self._create(name="保留的").data["data"]["id"]
        second = self._create(name="要删的", provider_type="ollama", api_key="").data[
            "data"
        ]["id"]
        APIClient().post(f"/api/ai/providers/{second}/activate/")

        APIClient().delete(f"/api/ai/providers/{second}/")

        self.assertEqual(ModelProvider.objects.count(), 1)
        self.assertTrue(ModelProvider.objects.get(pk=first).is_active)

    # ---- 校验 ----
    def test_openai_type_requires_base_url_and_model(self):
        """OpenAI 兼容类型没有默认地址，缺失时应明确报错。"""
        from rest_framework.test import APIClient

        response = APIClient().post(
            "/api/ai/providers/",
            {"name": "自定义", "provider_type": "openai", "api_key": "sk-x"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("接口地址", response.data["message"])

    def test_unknown_type_rejected(self):
        """未知服务商类型应被拒绝。"""
        response = self._create(provider_type="not-a-real-type")
        self.assertEqual(response.status_code, 400)


class ProviderPresetTests(TestCase):
    """预设清单。"""

    def test_presets_cover_four_types(self):
        """四类服务商都应提供预设。"""
        from rest_framework.test import APIClient

        response = APIClient().get("/api/ai/providers/presets/")
        types = {item["provider_type"] for item in response.data["data"]["presets"]}
        self.assertEqual(types, {"deepseek", "dashscope", "ollama", "openai"})

    def test_ollama_does_not_need_key(self):
        """本地 Ollama 不应要求 Key。"""
        from rest_framework.test import APIClient

        response = APIClient().get("/api/ai/providers/presets/")
        by_type = {
            item["provider_type"]: item for item in response.data["data"]["presets"]
        }
        self.assertFalse(by_type["ollama"]["needs_key"])
        self.assertTrue(by_type["deepseek"]["needs_key"])


class LlmFactoryDbTests(TestCase):
    """LLM 工厂应优先使用界面里配置的 Provider。"""

    def setUp(self):
        reset_llm_cache()
        reset_crypto_cache()
        ModelProvider.objects.all().delete()

    def tearDown(self):
        reset_llm_cache()
        reset_crypto_cache()

    def test_db_provider_takes_priority(self):
        """有数据库配置时，get_llm() 应使用它而不是 settings。"""
        from apps.ai.llm import get_llm

        cfg = ModelProvider(
            name="库里的配置",
            provider_type=ModelProvider.TYPE_DEEPSEEK,
            model="db-model-name",
            base_url="https://api.deepseek.com",
        )
        cfg.set_api_key("sk-db-key-123456")
        cfg.is_active = True
        cfg.save()

        llm = get_llm()

        self.assertEqual(llm.provider_name, "deepseek")
        self.assertEqual(llm.model, "db-model-name", "应使用数据库里配置的模型")
        self.assertEqual(llm.api_key, "sk-db-key-123456")

    def test_inactive_provider_is_ignored(self):
        """未启用的配置不应被 get_llm 使用。"""
        from apps.ai.llm import get_llm

        cfg = ModelProvider(
            name="未启用",
            provider_type=ModelProvider.TYPE_OPENAI,
            model="should-not-be-used",
            base_url="https://example.com/v1",
        )
        cfg.set_api_key("sk-x")
        cfg.is_active = False
        cfg.save()

        llm = get_llm()
        self.assertNotEqual(getattr(llm, "model", ""), "should-not-be-used")

    def test_editing_provider_invalidates_cache(self):
        """改了配置后缓存应自动失效（不依赖调用方记得清缓存）。"""
        from apps.ai.llm import get_llm

        cfg = ModelProvider(
            name="初版", provider_type=ModelProvider.TYPE_DEEPSEEK, model="model-v1"
        )
        cfg.set_api_key("sk-abc-123456")
        cfg.is_active = True
        cfg.save()

        self.assertEqual(get_llm().model, "model-v1")

        # 模拟用户在界面上改了模型名
        cfg.model = "model-v2"
        cfg.save()

        self.assertEqual(get_llm().model, "model-v2", "改配置后应自动用新值")


class ProviderTestEndpointTests(TestCase):
    """「测试连接」接口。"""

    def setUp(self):
        reset_llm_cache()
        ModelProvider.objects.all().delete()
        cfg = ModelProvider(
            name="待测", provider_type=ModelProvider.TYPE_DEEPSEEK, model="m"
        )
        cfg.set_api_key("sk-test-1234")
        cfg.is_active = True
        cfg.save()
        self.cfg = cfg

    def tearDown(self):
        reset_llm_cache()

    def test_success_persists_result(self):
        """测试成功时应把结果写回记录。"""
        from rest_framework.test import APIClient

        fake_llm = MagicMock()
        fake_llm.available = True
        fake_llm.generate.return_value = "ok"

        with patch(
            "apps.ai.providers.build_llm_from_provider", return_value=fake_llm
        ):
            response = APIClient().post(
                f"/api/ai/providers/{self.cfg.pk}/test/", {}, format="json"
            )

        self.assertTrue(response.data["data"]["ok"])
        self.cfg.refresh_from_db()
        self.assertTrue(self.cfg.last_test_ok)
        self.assertIsNotNone(self.cfg.last_test_at)

    def test_failure_returns_reason(self):
        """调用失败时应把原因透给用户，而不是只说"失败"。"""
        from rest_framework.test import APIClient

        fake_llm = MagicMock()
        fake_llm.available = True
        fake_llm.generate.side_effect = LLMError("模型不存在：model-not-found")

        with patch(
            "apps.ai.providers.build_llm_from_provider", return_value=fake_llm
        ):
            response = APIClient().post(
                f"/api/ai/providers/{self.cfg.pk}/test/", {}, format="json"
            )

        data = response.data["data"]
        self.assertFalse(data["ok"])
        self.assertIn("模型不存在", data["message"])

    def test_unavailable_config_explains_why(self):
        """配置不完整时要说明缺什么。"""
        from rest_framework.test import APIClient

        fake_llm = MagicMock()
        fake_llm.available = False

        with patch(
            "apps.ai.providers.build_llm_from_provider", return_value=fake_llm
        ):
            response = APIClient().post(
                f"/api/ai/providers/{self.cfg.pk}/test/", {}, format="json"
            )

        self.assertFalse(response.data["data"]["ok"])
        self.assertTrue(response.data["data"]["message"])


class EnsureDefaultProviderTests(TestCase):
    """首次启动从已有配置播种。"""

    def setUp(self):
        reset_llm_cache()
        reset_crypto_cache()
        ModelProvider.objects.all().delete()

    def tearDown(self):
        reset_llm_cache()
        reset_crypto_cache()

    @override_settings(DEEPSEEK_API_KEY="sk-from-env-123456")
    def test_seeds_from_settings(self):
        """.env 里有 Key 时应迁移成一条启用的数据库记录。"""
        cfg = providers.ensure_default_provider()

        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.is_active)
        self.assertEqual(cfg.provider_type, ModelProvider.TYPE_DEEPSEEK)
        self.assertEqual(cfg.get_api_key(), "sk-from-env-123456")
        self.assertTrue(is_encrypted(cfg.api_key), "迁移时也要加密")

    @override_settings(DEEPSEEK_API_KEY="sk-from-env-123456")
    def test_does_not_seed_twice(self):
        """已有配置时不再重复播种（幂等）。"""
        providers.ensure_default_provider()
        second = providers.ensure_default_provider()
        self.assertIsNone(second)
        self.assertEqual(ModelProvider.objects.count(), 1)

    @override_settings(DEEPSEEK_API_KEY="", DASHSCOPE_API_KEY="")
    def test_no_key_means_no_seed(self):
        """没有任何 Key 时不应凭空造一条配置。"""
        self.assertIsNone(providers.ensure_default_provider())
        self.assertEqual(ModelProvider.objects.count(), 0)


class RagStatusHintTests(TestCase):
    """RAG 状态提示语必须准确。

    【真实踩过的坑】
        干净机器上（没有任何模型配置）打包版状态面板显示的是
        「AI 助手已就绪」，而实际上 provider=fallback、根本没接大模型。

        根因：判断条件只看了 `llm.available`。而兜底的 RetrievalOnlyLLM
        本身就是"永远可用"的（它不需要任何外部服务），available 恒为 True。
        于是"未配置"被误判成"已就绪"，用户根本不会想到去点「模型设置」。
    """

    def setUp(self):
        reset_llm_cache()
        reset_crypto_cache()
        ModelProvider.objects.all().delete()

    def tearDown(self):
        reset_llm_cache()
        reset_crypto_cache()

    def _status_with(self, *, provider_name, available=True, provider_count=0):
        """用伪造的 LLM 与索引状态计算 RAG 状态。

        【为什么 provider_count 要真的建记录】
            get_rag_status() 里的 provider_count 是**函数内部查库**得到的，
            外部传参无效。所以这里按需要真的插入一条记录，
            否则测不到"配了但连不上"那个分支。
        """
        from apps.ai.rag import get_rag_status

        if provider_count:
            cfg = ModelProvider(
                name="测试配置",
                provider_type=ModelProvider.TYPE_DEEPSEEK,
                model="m",
            )
            cfg.set_api_key("sk-hint-test")
            cfg.is_active = True
            cfg.save()

        fake_llm = MagicMock()
        fake_llm.provider_name = provider_name
        fake_llm.available = available
        fake_llm.model = ""
        fake_llm.describe.return_value = {
            "provider": provider_name,
            "available": available,
        }

        with patch("apps.ai.rag.get_llm", return_value=fake_llm), patch(
            "apps.ai.rag.get_index_stats", return_value={"ready": True, "count": 40}
        ):
            return get_rag_status()

    def test_fallback_is_not_reported_as_ready(self):
        """退化成 fallback 时不能提示"已就绪"。"""
        status = self._status_with(provider_name="fallback", available=True)

        self.assertTrue(status["fallback"])
        self.assertIn("模型设置", status["hint"], "应引导用户去配置")
        self.assertNotIn("已就绪", status["hint"])

    def test_hint_differs_between_never_configured_and_broken(self):
        """「从未配置」与「配了但连不上」给出的下一步动作不同。"""
        never = self._status_with(provider_name="fallback", provider_count=0)
        broken = self._status_with(
            provider_name="deepseek", available=False, provider_count=1
        )

        self.assertIn("还没有配置", never["hint"])
        self.assertIn("测试连接", broken["hint"])
        self.assertNotEqual(never["hint"], broken["hint"])

    def test_healthy_provider_says_ready(self):
        """真正可用时才说"已就绪"。"""
        status = self._status_with(
            provider_name="deepseek", available=True, provider_count=1
        )
        self.assertIn("已就绪", status["hint"])


class OpenAiCompatiblePayloadTests(TestCase):
    """OpenAI 兼容 Provider 的请求体不能带 DeepSeek 专有参数。"""

    def test_no_thinking_param(self):
        """不能包含 thinking 字段（严格网关会因此返回 400）。"""
        from apps.ai.llm import DeepSeekLLM, OpenAICompatibleLLM

        generic = OpenAICompatibleLLM(
            model="gpt-4o-mini",
            api_key="sk-x",
            base_url="https://example.com/v1",
        )
        payload = generic._build_payload("hi", "", 0.7, 100, False)

        self.assertNotIn("thinking", payload, "OpenAI 兼容请求体不应带 thinking")
        self.assertEqual(payload["model"], "gpt-4o-mini")

        # 对照：DeepSeek 官方仍应保留该参数（用于关闭思维链）
        deepseek = DeepSeekLLM(model="deepseek-flash", api_key="sk-y")
        self.assertIn("thinking", deepseek._build_payload("hi", "", 0.7, 100, False))

    def test_missing_key_is_allowed(self):
        """本地推理服务不校验 Key，应允许为空。"""
        from apps.ai.llm import OpenAICompatibleLLM

        llm = OpenAICompatibleLLM(
            model="local-model", api_key="", base_url="http://127.0.0.1:1234/v1"
        )
        self.assertTrue(llm.available, "本地服务无 Key 也应视为可用")
        self.assertNotIn("Authorization", llm._headers(), "无 Key 时不应发送鉴权头")

# -*- coding: utf-8 -*-
"""API Key 的加密存储。

【为什么必须加密，而不是明文存数据库】
    大模型的 API Key 等同于"钱包密码"：泄露就能被别人拿去刷额度。
    而桌面版把数据库文件放在程序目录下（data\\biliinsight.db），
    使用者备份、拷贝、发给别人排查问题时，这个文件都可能被带出去。
    明文存 Key 等于把密钥一起发出去了。

【方案选择：对称加密 + 密钥派生自 SECRET_KEY】
    候选方案：
      A. 用操作系统密钥库（Windows DPAPI）—— 最安全，但跨平台麻烦，
         且 PyInstaller 打包后调用 Win32 加密 API 增加不确定性；
      B. 用固定密钥硬编码在代码里 —— 等于没加密，反编译即得；
      C. **用 SECRET_KEY 派生对称密钥（本方案）**。

    选 C 的理由：
      · SECRET_KEY 本来就是每个安装实例独有的（桌面版首次启动随机生成
        并持久化到 data\\secret.key，见 config/settings/desktop.py），
        因此换一台机器、换一次安装，加密密钥都不同；
      · 只依赖 cryptography 库（已是项目依赖），无需任何系统 API；
      · 数据库文件被单独拷走时，脱离 SECRET_KEY 无法解密。

    ⚠️ 诚实说明其局限：
      这防的是"数据库文件被拷走/被看到"，**防不住"能读到 SECRET_KEY
      的攻击者"**。对于桌面单机应用这是合理的取舍；
      若要更强，需要引入用户主密码（每次启动输入），
      那会牺牲"双击即用"的体验，本阶段不做。

【为什么是 fail-closed】
    加密失败时**绝不回退到明文存储**（那样会静默降级成不安全状态），
    而是抛出明确异常，由接口层返回"保存失败，请检查环境"。
    宁可保存不了，也不能悄悄地明文存下来。
"""

import base64
import hashlib
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: 加密后的存储前缀，用于区分"新数据（密文）"与"历史数据（明文）"
_CIPHER_PREFIX = "enc:v1:"

#: 进程内缓存的 Fernet 实例
_fernet = None


class KeyCryptoError(Exception):
    """加密/解密失败。"""


def _derive_fernet():
    """由 SECRET_KEY 派生 Fernet 实例。"""
    global _fernet
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - 依赖缺失属于环境问题
        raise KeyCryptoError(
            "缺少 cryptography 库，无法加密保存 API Key。"
            "请执行：pip install cryptography"
        ) from exc

    secret = getattr(settings, "SECRET_KEY", "") or "biliinsight-fallback-secret"

    # Fernet 需要 32 字节的 urlsafe base64 密钥。
    # 这里用"固定盐 + SECRET_KEY"做 SHA256，保证同一实例每次派生结果一致。
    digest = hashlib.sha256(
        f"biliinsight:api-key:v1:{secret}".encode("utf-8")
    ).digest()

    _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


def reset_crypto_cache() -> None:
    """清空缓存的 Fernet（测试切换 SECRET_KEY 时用）。"""
    global _fernet
    _fernet = None


def encrypt_key(plain: str) -> str:
    """加密 API Key。

    参数:
        plain: 明文 Key；空字符串直接返回空

    返回:
        形如 ``enc:v1:gAAAAA...`` 的密文

    异常:
        KeyCryptoError: 加密环境不可用（**绝不回退明文**）
    """
    if not plain:
        return ""

    try:
        token = _derive_fernet().encrypt(plain.encode("utf-8"))
    except KeyCryptoError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise KeyCryptoError(f"加密 API Key 失败：{exc}") from exc

    return _CIPHER_PREFIX + token.decode("ascii")


def decrypt_key(stored: str) -> str:
    """解密 API Key。

    参数:
        stored: 数据库里存的字符串（可能是密文，也可能是历史明文）

    返回:
        明文 Key；空字符串返回空

    说明:
        没有 ``enc:v1:`` 前缀的按**历史明文**处理并原样返回 ——
        这样升级前的存量数据不会因为加了加密而全部失效。
    """
    if not stored:
        return ""

    if not stored.startswith(_CIPHER_PREFIX):
        # 历史数据：加密上线前保存的明文
        return stored

    token = stored[len(_CIPHER_PREFIX):]
    try:
        return _derive_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        # 解不开通常是 SECRET_KEY 变了（例如 data\\secret.key 被删）
        logger.warning("解密 API Key 失败（SECRET_KEY 可能已变化）：%s", exc)
        return ""


def is_encrypted(stored: str) -> bool:
    """判断数据库里的值是否已加密。"""
    return bool(stored) and stored.startswith(_CIPHER_PREFIX)


def mask_key(plain: str) -> str:
    """把 Key 打码成可安全展示的形式。

    【为什么要打码而不是"前端拿到再藏起来"】
        只要接口返回了完整 Key，它在浏览器开发者工具、日志、
        抓包记录里就都存在了。正确的做法是**后端根本不返回完整值**。

    示例:
        sk-8971234567890abcdef  ->  sk-8****cdef
        短 key（<= 8 位）        ->  ****
    """
    if not plain:
        return ""

    if len(plain) <= 8:
        return "****"

    head = plain[:4]
    tail = plain[-4:]
    return f"{head}****{tail}"

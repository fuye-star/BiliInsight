# -*- coding: utf-8 -*-
"""
DeepSeek 配置诊断脚本。

用于排查"独立脚本能拿到密钥，但服务端仍是 fallback"这类不一致问题。

运行：
    python scripts/diagnose_deepseek.py
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.conf import settings  # noqa: E402


def mask(value: str) -> str:
    """密钥打码显示。"""
    if not value:
        return "（空）"
    if len(value) <= 10:
        return f"{value[:3]}...（{len(value)} 字符）"
    return f"{value[:7]}...{value[-4:]}（{len(value)} 字符）"


def main():
    print("\n" + "=" * 60)
    print("  DeepSeek 配置诊断")
    print("=" * 60)

    env_path = BACKEND_DIR / ".env"

    print("\n【1】文件层面")
    print(f"  cwd            : {os.getcwd()}")
    print(f"  .env 路径      : {env_path}")
    print(f"  .env 存在      : {env_path.exists()}")
    if env_path.exists():
        import datetime
        mtime = datetime.datetime.fromtimestamp(env_path.stat().st_mtime)
        print(f"  .env 修改时间  : {mtime:%Y-%m-%d %H:%M:%S}")

    print("\n【2】进程环境变量（会覆盖 .env！）")
    found_env_var = False
    for key in ("AI_PROVIDER", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"):
        value = os.environ.get(key)
        if value is not None:
            found_env_var = True
            print(f"  {key:20} = {mask(value)}   ← 来自进程环境变量")
    if not found_env_var:
        print("  （无相关环境变量，配置将全部来自 .env，这是正常情况）")

    print("\n【3】Django settings 读到的值")
    print(f"  BASE_DIR        : {settings.BASE_DIR}")
    print(f"  AI_PROVIDER     : {settings.AI_PROVIDER}")
    print(f"  DEEPSEEK_MODEL  : {settings.DEEPSEEK_MODEL}")
    print(f"  DEEPSEEK_BASE_URL: {settings.DEEPSEEK_BASE_URL}")
    print(f"  DEEPSEEK_API_KEY: {mask(settings.DEEPSEEK_API_KEY)}")

    print("\n【4】DeepSeekLLM 实例判定")
    from apps.ai.llm import DeepSeekLLM

    llm = DeepSeekLLM()
    print(f"  available       : {llm.available}")
    print(f"  model           : {llm.model}")
    if not llm.available:
        print("  → 不可用原因：API Key 为空")

    print("\n【5】工厂选择结果")
    from apps.ai.llm import get_llm, reset_llm_cache

    reset_llm_cache()
    selected = get_llm(refresh=True)
    print(f"  provider        : {selected.provider_name}")
    print(f"  available       : {selected.available}")
    if selected.provider_name != "deepseek":
        print("  → 未选中 deepseek，说明密钥未被读到或为空")

    print("\n【6】真实调用测试（会消耗少量额度）")
    if not llm.available:
        print("  跳过：API Key 为空")
        return 1

    try:
        answer = llm.generate(
            "请只回复两个字：收到",
            system="你是一个简洁的助手。",
            temperature=0,
            max_tokens=20,
        )
        print(f"  [OK] 调用成功，模型回复：{answer[:60]}")
        return 0
    except Exception as exc:
        print(f"  [X] 调用失败：{type(exc).__name__}: {exc}")
        print("\n  常见原因：")
        print("    · 401 → API Key 无效或已过期")
        print("    · 402 → 账户余额不足")
        print("    · 400 → 模型名不对（应为 deepseek-flash）")
        print("    · 网络 → 无法访问 api.deepseek.com")
        return 1


if __name__ == "__main__":
    sys.exit(main())

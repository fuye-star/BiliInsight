# -*- coding: utf-8 -*-
"""
生产环境配置。

启用方式：设置环境变量 DJANGO_SETTINGS_MODULE=config.settings.prod
（或启动时加 --settings=config.settings.prod）

与 dev 的核心差异：
  1. DEBUG 永久关闭 —— 避免泄露源码路径与配置
  2. 强制要求 SECRET_KEY 来自环境变量 —— 不允许使用默认弱密钥
  3. CORS 收紧为白名单
  4. 启用 HTTPS 相关安全响应头
"""

from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# 调试必须关闭
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
# 安全校验：生产环境不允许使用开发默认密钥
# ---------------------------------------------------------------------------
if SECRET_KEY == "dev-only-insecure-key-change-me":  # noqa: F405
    raise RuntimeError(
        "生产环境必须在 .env 中设置 DJANGO_SECRET_KEY（建议 50 位以上随机字符串）。\n"
        "生成方式：python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

# 生产环境必须显式声明允许的域名
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:  # noqa: F405
    raise RuntimeError(
        "生产环境必须在 .env 中设置 DJANGO_ALLOWED_HOSTS，例如：example.com,www.example.com"
    )


# ---------------------------------------------------------------------------
# CORS 收紧
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
# CORS_ALLOWED_ORIGINS 由 base.py 从环境变量读取，生产环境务必在 .env 中配置


# ---------------------------------------------------------------------------
# HTTPS 与安全响应头
# ---------------------------------------------------------------------------
# 若部署在 Nginx 等反向代理之后，让 Django 正确识别原始请求是 HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 强制 HTTPS 跳转（有证书后开启；纯内网 HTTP 部署可注释掉）
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)  # noqa: F405

# Cookie 安全
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

# 防点击劫持
X_FRAME_OPTIONS = "DENY"

# 内容类型嗅探防护
SECURE_CONTENT_TYPE_NOSNIFF = True

# HSTS：告诉浏览器后续只走 HTTPS（有证书后再开启）
if env_bool("SECURE_HSTS", False):  # noqa: F405
    SECURE_HSTS_SECONDS = 31536000          # 一年
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# ---------------------------------------------------------------------------
# 生产日志：只写文件 + 控制台交给容器收集
# ---------------------------------------------------------------------------
LOGGING["root"]["level"] = "WARNING"          # noqa: F405
LOGGING["loggers"]["django"]["level"] = "WARNING"   # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "INFO"        # noqa: F405

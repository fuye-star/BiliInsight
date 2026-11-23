# -*- coding: utf-8 -*-
"""
BiliInsight 基础配置（base）。

所有环境共用的配置项都放在这里；
dev / prod 通过 `from .base import *` 继承后再覆盖差异部分。

【配置来源优先级】
  1. 系统环境变量（最高，便于 CI/CD 与容器部署）
  2. backend/.env 文件（本地开发，已在 .gitignore 中排除）
  3. 本文件内的默认值（仅用于开发便利，生产必须覆盖）

【为什么不用 django-environ】
本机环境未安装 django-environ，而 python-dotenv 已随主依赖装好，
两者功能等价，少一个依赖就少一分环境风险。
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 路径计算
# ---------------------------------------------------------------------------
# BASE_DIR 指向 backend/ 目录（即 manage.py 所在目录）
#   __file__        -> backend/config/settings/base.py
#   .parent         -> backend/config/settings
#   .parent.parent  -> backend/config
#   .parent.parent.parent -> backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 加载 .env（不存在也不报错，便于纯环境变量部署）
load_dotenv(BASE_DIR / ".env")


def env(key: str, default=None):
    """读取环境变量；未设置时返回 default。"""
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    """读取布尔型环境变量，接受 1/true/yes/on 等写法。"""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int) -> int:
    """读取整型环境变量，非法值回退到 default。"""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key: str, default=None):
    """读取逗号分隔的列表型环境变量。"""
    val = os.environ.get(key)
    if not val:
        return default or []
    return [item.strip() for item in val.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# 安全
# ---------------------------------------------------------------------------
# 生产环境务必在 .env 中设置一个随机长字符串（建议 50 位以上）
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")

# 默认关闭调试；dev.py 会显式打开
DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])


# ---------------------------------------------------------------------------
# 应用注册
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# 第三方应用
THIRD_PARTY_APPS = [
    "rest_framework",            # DRF：RESTful API 框架
    "rest_framework_simplejwt",  # JWT 认证
    "corsheaders",               # 跨域处理（前后端分离必需）
    "django_filters",            # 列表接口的筛选能力
    "drf_spectacular",           # 自动生成 OpenAPI 接口文档
    # Celery 结果与定时任务存储（用数据库保存，便于在 Admin 中查看）
    "django_celery_results",
    "django_celery_beat",
]

# 本项目的业务应用
LOCAL_APPS = [
    "apps.common",     # 公共组件：分页、异常、响应封装、基础模型
    "apps.accounts",   # 用户与 JWT 认证
    "apps.videos",     # 视频 / UP主 / 弹幕 / 分区 数据模型
    "apps.spider",     # 爬虫（BaseSpider 抽象基类 + B站实现 + Celery 任务）
    "apps.analytics",  # 数据聚合统计 API
    "apps.ai",         # LLM 工厂 + RAG 检索 + 弹幕情感分析
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    # CORS 必须尽量靠前，确保预检请求与错误响应也能带上跨域头
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # 项目级模板目录（Admin 之外的公共模板放这里）
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# 数据库：MySQL 8.0
# ---------------------------------------------------------------------------
# 端口说明：
#   3307 -> 本机使用 Docker 部署 MySQL（避免与原生 MySQL 的 3306 冲突）
#   3306 -> 原生安装的 MySQL
# 具体值由 .env 中的 MYSQL_PORT 决定
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("MYSQL_DATABASE", "biliinsight"),
        "USER": env("MYSQL_USER", "bili"),
        "PASSWORD": env("MYSQL_PASSWORD", "bili_pass_2026"),
        "HOST": env("MYSQL_HOST", "127.0.0.1"),
        "PORT": env("MYSQL_PORT", "3307"),
        "OPTIONS": {
            # 弹幕与评论包含大量 emoji，必须使用 utf8mb4
            "charset": "utf8mb4",
            # 严格模式：避免数据静默截断，问题尽早暴露
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        # 连接复用：避免每个请求都重新建立 TCP 连接（性能优化点）
        "CONN_MAX_AGE": env_int("MYSQL_CONN_MAX_AGE", 60),
        "ATOMIC_REQUESTS": False,
    }
}


# ---------------------------------------------------------------------------
# 缓存：Redis
# ---------------------------------------------------------------------------
# Redis 同时承担三个角色：
#   db0 -> 页面/榜单数据缓存
#   db1 -> Celery 任务队列（Broker）
#   db2 -> Celery 任务结果（Result Backend）
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "biliinsight",  # 统一前缀，避免与其他项目键名冲突
        "TIMEOUT": 300,               # 默认 5 分钟过期
    }
}

# 缓存时长（秒），供业务代码统一引用，避免散落魔法数字
CACHE_TTL_HOT_VIDEOS = env_int("CACHE_TTL_HOT_VIDEOS", 300)
CACHE_TTL_RANKING = env_int("CACHE_TTL_RANKING", 600)


# ---------------------------------------------------------------------------
# Celery 异步任务
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_ENABLE_UTC = False

# 任务结果保存到数据库，便于在 Django Admin 中直接查看执行记录
CELERY_RESULT_EXTENDED = True

# 单个任务最多执行 30 分钟，超时强制终止，防止爬虫卡死拖垮 Worker
CELERY_TASK_TIME_LIMIT = 60 * 30

# 每个 Worker 预取 1 个任务，保证长任务不会把队列堵在一个 Worker 上
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# 定时任务调度器使用数据库存储（配合 django_celery_beat）
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


# ---------------------------------------------------------------------------
# 密码校验
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# 国际化
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# 静态与媒体文件
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    # 默认要求 JWT 认证；公开接口在视图上单独放行
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # 全局异常处理：把 DRF 的默认错误格式统一成 {code, message, data}
    # 【这一项极易遗漏】DRF 默认返回 {"detail": "..."}，
    # 与本项目的统一响应约定不一致，前端拦截器就得写两套判断。
    # 早期版本漏配了此项，导致 404 等错误仍以 DRF 默认格式返回，
    # 而 apps/common/exceptions.py 里的处理器其实一次都没被调用。
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    # 全站分页，避免大表查询把内存打满
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    # 筛选与排序
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    # 接口文档（drf-spectacular）
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # 只读接口不做不必要的写操作校验
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "BiliInsight API",
    "DESCRIPTION": "B站热门视频数据分析与智能推荐系统 —— 后端接口文档",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # 中文标签排序，便于按模块查找
    "TAGS": [
        {"name": "health", "description": "健康检查"},
        {"name": "videos", "description": "视频 / UP主 / 弹幕"},
        {"name": "analytics", "description": "数据统计分析"},
        {"name": "ai", "description": "AI 助手与情感分析"},
    ],
}


# ---------------------------------------------------------------------------
# CORS 跨域
# ---------------------------------------------------------------------------
# 前端开发服务器（Vite）默认跑在 8080
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    ["http://localhost:8080", "http://127.0.0.1:8080"],
)
CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)  # 目录不存在时自动创建，避免首次启动报错

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}:{lineno} - {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{asctime}] {levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "biliinsight.log",
            "maxBytes": 10 * 1024 * 1024,  # 单文件 10MB
            "backupCount": 5,              # 最多保留 5 个历史文件
            "encoding": "utf-8",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        # Django 自身日志
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # 项目业务日志：单独一个文件，便于排查
        "apps": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        # 爬虫日志：调试请求细节时用
        "apps.spider": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


# ---------------------------------------------------------------------------
# 业务可调参数（统一收敛在这里，避免散落在各处）
# ---------------------------------------------------------------------------
# 爬虫合规配置 —— 请勿将间隔调到 1.0 秒以下
SPIDER_REQUEST_INTERVAL = float(env("SPIDER_REQUEST_INTERVAL", "2.0"))
SPIDER_MAX_RETRIES = env_int("SPIDER_MAX_RETRIES", 3)
SPIDER_TIMEOUT = env_int("SPIDER_TIMEOUT", 15)
SPIDER_USER_AGENT = env(
    "SPIDER_USER_AGENT",
    "Mozilla/5.0 (compatible; BiliInsight/1.0; Educational-Research)",
)

# AI Provider：ollama | dashscope | deepseek
# ollama   本地免费离线（需启动 Ollama 服务）
# dashscope 通义千问（需 API Key + 外网）
# deepseek  DeepSeek 官方 API（OpenAI 兼容，价格极低）
# 均不可用时自动降级为"检索式回答"
AI_PROVIDER = env("AI_PROVIDER", "ollama")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "deepseek-r1:8b")
DASHSCOPE_API_KEY = env("DASHSCOPE_API_KEY", "")
AI_MODEL = env("AI_MODEL", "qwen-plus")

# DeepSeek 官方 API
# ⚠️ 模型名必须是 "deepseek-flash"（不是 deepseek-v4.1-flash）
#    DeepSeek-V4.1-Flash 是版本名，API 模型名是 deepseek-flash
#    旧名 deepseek-v4-flash 对应的模型已退役
DEEPSEEK_API_KEY = env("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = env("DEEPSEEK_MODEL", "deepseek-flash")
DEEPSEEK_BASE_URL = env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# 向量库
CHROMA_PERSIST_DIR = env("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma"))
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "bge-m3")

# 向量化后端：local（默认，零依赖）| ollama | dashscope
# ⚠️ 切换后端后必须重建索引：python manage.py build_index --rebuild
EMBEDDING_BACKEND = env("EMBEDDING_BACKEND", "local")

# 情感分析后端：snownlp（默认，支持 3.13）| paddlenlp（需 Python 3.11/3.12）
SENTIMENT_BACKEND = env("SENTIMENT_BACKEND", "snownlp")

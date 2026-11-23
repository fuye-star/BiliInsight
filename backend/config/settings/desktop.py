# -*- coding: utf-8 -*-
"""桌面版配置（desktop）—— 绿色免安装的单机运行形态。

【为什么需要单独一套配置】
    开发/部署形态（dev / prod）依赖三个外部服务：

        MySQL 8.0（3307） + Redis（6379） + Celery Worker

    这对"发给老师/同学安装"完全不现实：没人愿意为了看一个数据看板
    先装 Docker、装 MySQL、再开一个命令行窗口跑 Celery。

    因此桌面版把这套依赖全部就地替换，做到**双击即用**：

        外部服务       -> 桌面版方案
        ------------     --------------------------------
        MySQL          -> SQLite（单文件，随程序目录走）
        Redis 缓存      -> Django LocMemCache（进程内）
        Celery Worker  -> 同步执行（单用户不需要任务队列）
        ChromaDB       -> 不变（本来就是嵌入式 PersistentClient）
        Vite 开发服务器  -> Django 直接托管前端构建产物

【关键：数据依然可以更新】
    打包只冻结"代码 + Python 解释器"，不冻结网络和数据库。
    桌面版的数据链路是完整的：

        点「更新数据」 -> 请求 B站 API（需要网络） -> 写入 data/biliinsight.db
                      -> 前端立刻读新数据出图

    所以"打包后还能不能更新数据"的答案是：能，只要联网。
    不联网时也能用 —— 程序自带一份预置数据库，打开就有完整图表可看。

启用方式：
    set DJANGO_SETTINGS_MODULE=config.settings.desktop
    python manage.py check
"""

import json
import os
import secrets
import sys
from pathlib import Path

from .base import *  # noqa: F401,F403  —— 继承全部基础配置


# ===========================================================================
# 一、应用根目录（便携模式：数据放在程序旁边）
# ===========================================================================
def _resolve_app_home() -> Path:
    """确定应用数据根目录。

    【为什么默认放在程序目录，而不是 %APPDATA%】
      1. 本应用以"绿色免安装"分发：老师/同学解压到任意目录即可运行；
      2. 数据与程序同在一处，卸载时删掉文件夹就干净了，不留残余；
      3. 避免向 C 盘用户目录写文件。

      优先级：
        · 环境变量 BILIINSIGHT_HOME（便于放在其他盘）
        · 打包后：exe 所在目录
        · 开发期：项目根目录下的 .desktop（不污染 backend/data）

    ⚠️ 分发时要提醒使用者：**不要解压到 C:\\Program Files**，
       那里没有写权限，抓取数据会失败。
    """
    override = os.environ.get("BILIINSIGHT_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    # PyInstaller 打包后 sys.frozen 为 True
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return (BASE_DIR.parent / ".desktop").resolve()  # noqa: F405


APP_HOME = _resolve_app_home()
DATA_DIR = APP_HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _bundle_dirs() -> list:
    """返回"随包资源"可能所在的目录，按优先级排列。

    【为什么需要多个候选 —— PyInstaller 6.x 的布局变化】
        PyInstaller 6 起，onedir 模式的产物结构变了：

            BiliInsight/
            ├── BiliInsight.exe
            └── _internal/            <- 依赖与数据文件都搬到了这里
                ├── frontend/
                ├── seed/
                └── ...

        而在 5.x 及更早版本里，这些文件是与 exe 平级的。

        如果只按"exe 同级"去找，打出来的应用会找不到前端页面和预置数据，
        表现为"双击后一片空白"。因此这里把几种可能的布局都列出来依次探测，
        这样无论 PyInstaller 版本如何变化都不会踩空。

        优先级：
            ① sys._MEIPASS（PyInstaller 提供的打包资源根目录，最可靠）
            ② exe 同级的 _internal（6.x 的固定名字）
            ③ APP_HOME 本身（开发期 / 5.x 布局 / 用户手动放置）
    """
    dirs = []

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        dirs.append(Path(meipass))

    dirs.append(APP_HOME / "_internal")
    dirs.append(APP_HOME)

    # 去重但保持顺序
    seen = set()
    result = []
    for item in dirs:
        try:
            resolved = item.resolve()
        except Exception:  # noqa: BLE001
            continue
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


# ===========================================================================
# 二、用户配置（API Key 等，放程序目录下，可随时用记事本改）
# ===========================================================================
USER_CONFIG_FILE = APP_HOME / "config.json"


def _load_user_config() -> dict:
    """读取本地用户配置。

    【为什么不把 API Key 写进代码或 exe】
        exe 里的字符串可以被直接提取（strings / 反编译），
        把密钥硬编码进分发包等于公开它。
        因此密钥放外部的 config.json，由使用者自己填写。

    格式示例：
        {
          "deepseek_api_key": "sk-xxxx",
          "ai_provider": "deepseek"
        }
    """
    if not USER_CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        # 配置文件写坏不能导致应用起不来
        return {}


USER_CONFIG = _load_user_config()


# ===========================================================================
# 三、安全
# ===========================================================================
def _resolve_secret_key() -> str:
    """生成并持久化 SECRET_KEY。

    【为什么要持久化而不是每次随机】
        SECRET_KEY 一变，已签发的 session / JWT 签名全部失效，
        使用者每次重启都要重新登录。因此首次启动生成一次并存到 data/ 下。
    """
    env_key = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if env_key:
        return env_key

    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        stored = key_file.read_text(encoding="ascii", errors="ignore").strip()
        if stored:
            return stored

    key = secrets.token_urlsafe(50)
    try:
        key_file.write_text(key, encoding="ascii")
    except Exception:
        pass
    return key


SECRET_KEY = _resolve_secret_key()

# 桌面版是单机运行，不需要调试页暴露内部信息
DEBUG = False

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# ===========================================================================
# 四、数据库 -> SQLite
# ===========================================================================
# 本项目原本用 MySQL，但检查过全部业务代码：
#   · 没有任何 JSONField / ArrayField / 数据库专有字段类型
#   · 没有原生 SQL（唯一的 SELECT VERSION() 在健康检查里，已做方言适配）
# 因此换 SQLite 只需改这一处配置。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DATA_DIR / "biliinsight.db"),
        "OPTIONS": {
            # 抓取线程写库时前端可能正在读接口，给足重试时间避免
            # "database is locked"（SQLite 默认只等 5 秒）
            "timeout": 20,
            # 事务行为与 MySQL 的 STRICT_TRANS_TABLES 接近，尽早暴露问题
            "transaction_mode": "IMMEDIATE",
        },
        "CONN_MAX_AGE": 0,
        "ATOMIC_REQUESTS": False,
    }
}


# ===========================================================================
# 五、缓存 -> 进程内内存缓存
# ===========================================================================
# Redis 在 Windows 上没有原生版本（要装 Memurai 或用 Docker），
# 桌面版单进程完全可以用 LocMemCache 替代，接口代码不需要任何改动
# （业务代码一直是通过 Django cache 抽象访问的）。
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "biliinsight-desktop",
        "KEY_PREFIX": "biliinsight",
        "TIMEOUT": 300,
    }
}


# ===========================================================================
# 六、Celery -> 同步执行
# ===========================================================================
# 本项目原本用 Celery 把抓取放到后台，是为了避免 HTTP 请求超时。
# 桌面版只有一个用户，改成同步执行反而更好：
#   · 少两个进程（worker / beat），打包和退出都简单得多
#   · 前端能拿到真实进度，而不是轮询任务表
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# 即便误配置也不会真的往 Redis 投递任务
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# 桌面版不做定时抓取（避免程序开着就偷偷发请求，也符合合规预期）
CELERY_BEAT_SCHEDULER = "celery.beat.Scheduler"


# ===========================================================================
# 七、静态文件与前端
# ===========================================================================
# WhiteNoise：不需要 Nginx，也不需要跑 collectstatic
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
_WHITENOISE = "whitenoise.middleware.WhiteNoiseMiddleware"
if _WHITENOISE not in MIDDLEWARE:
    try:
        _idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1
    except ValueError:
        _idx = 0
    MIDDLEWARE.insert(_idx, _WHITENOISE)

# 直接从各 app 的 static 目录取文件（Django Admin 的样式依赖它）
WHITENOISE_USE_FINDERS = True
WHITENOISE_MAX_AGE = 0
WHITENOISE_AUTOREFRESH = False

# WhiteNoise 在 finders 模式下其实不需要 STATIC_ROOT，
# 但只要它指向一个不存在的目录，每次启动都会打一条 WARNING：
#     No directory at: .../staticfiles/
# 桌面版要尽量减少日志噪音（使用者会把日志贴给你），因此建好这个目录。
STATIC_ROOT = str(APP_HOME / "staticfiles")
Path(STATIC_ROOT).mkdir(parents=True, exist_ok=True)

# 前端构建产物位置：打包后在程序目录的 frontend/；开发期直接指向 Vite 的 dist
FRONTEND_DIST = ""


def _resolve_frontend_dist() -> str:
    """定位前端构建产物目录。"""
    # 打包后：在随包资源目录里找
    for base in _bundle_dirs():
        candidate = base / "frontend"
        if (candidate / "index.html").exists():
            return str(candidate)

    # 开发期：直接用 Vite 的 dist
    dev_dist = BASE_DIR.parent / "frontend" / "dist"  # noqa: F405
    if (dev_dist / "index.html").exists():
        return str(dev_dist)

    # 都没有：返回打包后的预期位置，让 SPA 视图给出明确的 404 提示
    return str(APP_HOME / "frontend")


FRONTEND_DIST = _resolve_frontend_dist()


def _resolve_seed_dir() -> str:
    """定位预置数据目录（离线演示用的初始数据集）。

    【为什么要有预置数据】
        使用者第一次打开时如果数据库是空的，看到的是一片空图表 ——
        既不知道软件能干什么，答辩现场没网时更是直接没法演示。

        因此发布包里带一份"开箱即用"的真实数据集（40 条视频 + 6720 条弹幕），
        首次启动自动导入；联网后点「更新数据」再增量抓取最新内容。
    """
    for base in _bundle_dirs():
        candidate = base / "seed"
        if (candidate / "preset_videos.json").exists():
            return str(candidate)

    # 开发期：backend/seed
    dev_seed = BASE_DIR / "seed"  # noqa: F405
    if (dev_seed / "preset_videos.json").exists():
        return str(dev_seed)

    return str(APP_HOME / "seed")


SEED_DIR = _resolve_seed_dir()


# ===========================================================================
# 八、AI 配置（从 config.json 读取，覆盖 .env）
# ===========================================================================
DEEPSEEK_API_KEY = (
    str(USER_CONFIG.get("deepseek_api_key") or "").strip()
    or os.environ.get("DEEPSEEK_API_KEY", "").strip()
)
DEEPSEEK_MODEL = str(USER_CONFIG.get("deepseek_model") or "").strip() or env(  # noqa: F405
    "DEEPSEEK_MODEL", "deepseek-flash"
)
DEEPSEEK_BASE_URL = str(USER_CONFIG.get("deepseek_base_url") or "").strip() or env(  # noqa: F405
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)

# 有 Key 就用 DeepSeek；没有 Key 则自动降级为"仅检索"（不会报错，功能仍可用）
AI_PROVIDER = (
    str(USER_CONFIG.get("ai_provider") or "").strip()
    or ("deepseek" if DEEPSEEK_API_KEY else "deepseek")
)

# 向量库放在数据目录（与数据库同处，便于整体备份/迁移）
CHROMA_PERSIST_DIR = str(DATA_DIR / "chroma")

# 本地向量化：零外部依赖，离线也能建索引与检索
EMBEDDING_BACKEND = "local"

# 情感分析：snownlp 纯 Python，打包体积小、无编译依赖
SENTIMENT_BACKEND = "snownlp"


# ===========================================================================
# 九、其他
# ===========================================================================
# 同源部署（前端由 Django 托管），不需要跨域
CORS_ALLOW_ALL_ORIGINS = False

# 论坛/邮件等开发期功能不需要
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# 桌面端日志写到数据目录，便于使用者反馈问题时直接提供日志文件。
# base.py 已经把 console / file 两个 handler 挂到了所有 logger 上，
# 这里只需要把文件路径改到 data/logs，不必重建 handler（重建会导致重复挂载）。
_LOG_DIR = DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING["handlers"]["file"]["filename"] = str(_LOG_DIR / "desktop.log")  # noqa: F405
LOGGING["handlers"]["file"]["maxBytes"] = 2 * 1024 * 1024                # noqa: F405
LOGGING["handlers"]["file"]["backupCount"] = 3                           # noqa: F405

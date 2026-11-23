# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 生成"绿色免安装"的 BiliInsight 桌面版。

【为什么用 onedir（目录）而不是 onefile（单文件）】
    onefile 看起来更"像单个 app"，但代价很实际：

      · 每次启动都要把几百 MB 解压到系统临时目录（%TEMP%），冷启动十几秒；
      · 解压会往 C 盘写大量临时文件；
      · 杀毒软件更容易误报（自解压行为特征明显）。

    onedir 是一个文件夹：解压即用、启动快、不写系统临时目录。
    对"发给老师/同学"这个场景，把文件夹压缩成 zip 分发完全够用。

【为什么要显式声明那么多 hiddenimports】
    Django 的应用是按**字符串**加载的，不是按 import 语句：

        INSTALLED_APPS = ["apps.videos", "apps.ai", ...]
        ROOT_URLCONF  = "config.urls"
        DJANGO_SETTINGS_MODULE = "config.settings.desktop"

    PyInstaller 靠静态分析追 import，看不到这些字符串，
    因此必须手动告诉它"这些模块运行时会用到"，否则打出来的包一启动就
    ModuleNotFoundError。这是 Django 项目打包最常见的坑。

【为什么要排除 onnxruntime / matplotlib】
    · onnxruntime 是 chromadb 的间接依赖（默认嵌入函数用），
      而本项目**始终自己计算向量再传进去**，从不使用默认嵌入函数 ——
      实测 `import chromadb` 与导入项目向量库都不会把它带进来，可安全排除（省约 44MB）。
    · matplotlib 是 wordcloud 的间接依赖。本项目的词云是"后端算词频 +
      前端 ECharts 画图"，不需要 matplotlib 渲染（省约 30MB）。

构建：
    cd backend
    python -m PyInstaller build_desktop.spec --noconfirm --clean

产物：
    backend/dist/BiliInsight/     <- 这就是要分发的文件夹
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
# SPECPATH 是 PyInstaller 注入的全局变量，指向本文件所在目录（backend/）
BACKEND_DIR = Path(SPECPATH).resolve()          # noqa: F821
PROJECT_DIR = BACKEND_DIR.parent

# 让 collect_submodules 在需要时能 import 到项目包
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.desktop")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


# ---------------------------------------------------------------------------
# 随包分发的数据文件
# ---------------------------------------------------------------------------
datas = [
    # 前端构建产物：Django 会从这个目录托管 SPA
    # 打包后在程序目录的 frontend/ 下，settings 的 _resolve_frontend_dist 能找到
    (str(PROJECT_DIR / "frontend" / "dist"), "frontend"),
    # 预置数据集：首次启动自动导入，保证"没网也能看到完整图表"
    (str(BACKEND_DIR / "seed"), "seed"),
    # 使用说明（给老师/同学看的）
    (str(BACKEND_DIR / "使用说明.txt"), "."),
]

# Django 自带的模板、locale（Admin 后台与错误页要用）
datas += collect_data_files("django")
# DRF 的浏览器调试页模板
datas += collect_data_files("rest_framework")
# 接口文档 UI 的静态资源
datas += collect_data_files("drf_spectacular")

# 中文分词的词典（jieba 没有它就不能工作）
datas += collect_data_files("jieba")
# 情感分析模型语料（snownlp 没有它就不能工作）
datas += collect_data_files("snownlp")


# ---------------------------------------------------------------------------
# 运行时才加载、静态分析看不到的模块
# ---------------------------------------------------------------------------
hiddenimports = [
    # Django 配置与路由（通过字符串加载）
    "config.settings.base",
    "config.settings.desktop",
    "config.urls",
    "config.celery",
    # 桌面版入口用到的服务器与窗口
    "waitress",
    "whitenoise.middleware",
    # MySQL 驱动的"伪装"：config/__init__.py 里会 install_as_MySQLdb
    "pymysql",
    # 项目各 app（INSTALLED_APPS 是字符串，必须显式收集）
    "apps",
    "apps.common",
    "apps.videos",
    "apps.analytics",
    "apps.ai",
    "apps.spider",
    "apps.accounts",
    # 后台任务相关（模型要迁移建表，类必须存在）
    "django_celery_beat",
    "django_celery_results",
]

# 递归收集项目 app 下的全部子模块（management commands / migrations 等）
hiddenimports += collect_submodules("apps")
# chromadb 内部按需加载了不少实现模块
hiddenimports += collect_submodules("chromadb")
# pywebview 的平台后端（Windows 走 edgechromium）
hiddenimports += collect_submodules("webview.platforms")

# Celery / kombu：`config/__init__.py` 会 `from .celery import app`，
# 而 Celery 内部大量使用「字符串动态导入」（kombu.utils.imports.symbol_by_name），
# PyInstaller 的静态分析看不到这些路径。
#
# 实测漏掉后的报错就发生在 Django 设置加载阶段：
#     File "config\celery.py", line 31, in <module>
#       app = Celery("biliinsight")
#     ModuleNotFoundError: No module named 'celery.fixups'
#
# 注意：这种错误发生在**创建窗口之前**，无控制台版本会静默退出，
# 表现成"双击没反应"，非常难查。因此这里把整包都收进来。
hiddenimports += collect_submodules("celery", on_error="ignore")
hiddenimports += collect_submodules("kombu", on_error="ignore")
hiddenimports += collect_submodules("billiard", on_error="ignore")


# ---------------------------------------------------------------------------
# 排除用不到的大件
# ---------------------------------------------------------------------------
excludes = [
    # 见文件头说明：本项目不使用 chromadb 的默认嵌入函数
    "onnxruntime",
    # 词云由前端 ECharts 绘制，不需要 Python 出图
    "matplotlib",
    "mpl_toolkits",
    # 桌面窗口用 WebView2，不需要 Tk / Qt
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    # 开发/测试期依赖
    "pytest",
    "locust",
    "IPython",
    "jupyter",
    "notebook",
    "pip",
    "setuptools",
]


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------
a = Analysis(  # noqa: F821
    ["desktop_main.py"],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    # 不优化字节码：保持与开发环境一致的报错信息，便于排查
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BiliInsight",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 会明显增加杀毒误报，且对体积帮助有限
    # 无黑框：双击后只出现应用窗口。
    # 启动失败时由 desktop_main 弹出 Windows 消息框，
    # 并把完整堆栈写进 exe 同级的 startup-error.log。
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BiliInsight",
)

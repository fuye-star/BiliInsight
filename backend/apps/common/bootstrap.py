# -*- coding: utf-8 -*-
"""桌面版启动引导 —— 让"双击即用"真正成立。

【它解决什么问题】
    开发环境下，跑起来要手动执行一堆命令：

        python manage.py migrate
        python manage.py loaddata seed/preset_videos.json
        python manage.py build_index --rebuild

    但桌面版的使用者是老师/同学，不可能去敲这些命令。
    因此启动器在打开窗口之前先跑一遍本模块，把环境准备到位。

【为什么每一步都必须幂等】
    程序会被反复启动，初始化逻辑不能"跑第二次就报错或重复导入数据"：

        migrate        —— Django 自带幂等，已应用的迁移会跳过
        导入预置数据    —— 只在视频表为空时执行
        构建向量索引    —— 只在索引为空或条数不一致时重建
"""

import logging
from pathlib import Path

from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)

#: 预置数据文件名
SEED_FIXTURE_NAME = "preset_videos.json"


def _log(progress, message: str) -> None:
    """同时输出到日志与（可选的）启动画面回调。"""
    logger.info(message)
    if progress is not None:
        try:
            progress(message)
        except Exception:  # noqa: BLE001
            # 启动画面回调失败绝不能影响初始化
            pass


def _run_migrations(progress=None) -> None:
    """执行数据库迁移，把 SQLite 建表/升级到最新结构。"""
    _log(progress, "正在检查数据库结构…")
    # verbosity=0：不刷屏，使用者看不懂那些迁移日志
    call_command("migrate", interactive=False, verbosity=0)


def _video_count() -> int:
    """当前库里的视频条数。"""
    from apps.videos.models import Video

    return Video.objects.count()


def _load_preset_data(progress=None) -> int:
    """导入预置数据（仅当数据库为空时）。

    返回:
        导入的对象条数；未导入返回 0
    """
    if _video_count() > 0:
        return 0

    fixture = Path(getattr(settings, "SEED_DIR", "")) / SEED_FIXTURE_NAME
    if not fixture.is_file():
        _log(progress, "未找到预置数据，将从空库开始（可点「更新数据」抓取）")
        return 0

    _log(progress, "首次启动，正在导入预置数据…")
    try:
        call_command("loaddata", str(fixture), verbosity=0)
    except Exception as exc:  # noqa: BLE001
        # 预置数据导入失败不应阻止应用启动 —— 用户仍可自己抓取
        logger.exception("导入预置数据失败：%s", exc)
        _log(progress, "预置数据导入失败，仍可正常使用并手动抓取")
        return 0

    total = _video_count()
    _log(progress, f"预置数据导入完成：{total} 条视频")
    return total


def _ensure_vector_index(progress=None) -> None:
    """确保向量索引与数据库一致。

    【为什么要校验条数】
        AI 助手依赖向量索引。若索引为空（首次启动）或与视频数不一致
        （刚导入过预置数据、或刚抓取完新视频），检索结果就会缺失。
        本地向量化建 40 条索引只要 1 秒出头，直接重建最省事。
    """
    from apps.ai.vector_store import build_index, get_index_stats

    expected = _video_count()
    if expected == 0:
        return

    stats = get_index_stats()
    if stats.get("ready") and stats.get("count") == expected:
        return

    _log(progress, "正在构建 AI 检索索引…")
    try:
        result = build_index(rebuild=True)
        _log(progress, f"检索索引就绪：{result.get('indexed', 0)} 条")
    except Exception as exc:  # noqa: BLE001
        # 索引失败只影响 AI 检索，其它页面照常可用
        logger.exception("构建向量索引失败：%s", exc)
        _log(progress, "检索索引构建失败（AI 助手将降级为不可用）")


def _ensure_llm_provider(progress=None) -> None:
    """确保大模型配置存在（把 .env / config.json 里的 Key 迁移进数据库）。

    【为什么要做这一步】
        大模型配置从"只认环境变量"改成了"界面里可管理（数据库）"。
        如果不管，老用户打开界面会看到"还没有配置模型提供商"，
        而他明明早就把 Key 写进了 .env 或 config.json —— 体验倒退。

        这里在启动时做一次**一次性迁移**：只要数据库里还没有任何配置，
        就把已有 Key 转成一条记录并设为启用。之后以数据库为准。

    【为什么必须幂等】
        每次启动都会执行。已有配置时直接返回，不会重复写入。
    """
    try:
        from apps.ai.providers import ensure_default_provider

        cfg = ensure_default_provider()
        if cfg is not None:
            _log(progress, f"已导入原有的大模型配置：{cfg.name}")
    except Exception as exc:  # noqa: BLE001
        # 播种失败不该阻止应用启动 —— 用户仍可在界面里手动添加
        logger.warning("导入原有大模型配置失败：%s", exc)


def ensure_ready(progress=None) -> dict:
    """桌面版启动前的一次性准备。

    参数:
        progress: 可选回调，接收一段中文进度文本（用于启动画面）

    返回:
        {"ok": bool, "videos": int, "error": str}
    """
    from django.db import connection

    _log(progress, "正在准备运行环境…")

    # 数据目录（打包后可能是首次创建）
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)

    try:
        # SQLite 开启 WAL：
        #   抓取线程在写库时，前端仍在读接口。
        #   默认的 rollback journal 模式下读会被写阻塞，
        #   容易出现 "database is locked"。WAL 允许读写并发，体验更稳。
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA journal_mode=WAL")

        _run_migrations(progress)
        _load_preset_data(progress)
        _ensure_llm_provider(progress)
        _ensure_vector_index(progress)

        return {"ok": True, "videos": _video_count(), "error": ""}
    except Exception as exc:  # noqa: BLE001
        logger.exception("桌面版初始化失败：%s", exc)
        _log(progress, f"初始化失败：{exc}")
        return {"ok": False, "videos": 0, "error": str(exc)}

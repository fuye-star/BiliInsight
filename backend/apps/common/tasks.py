# -*- coding: utf-8 -*-
"""
common 应用的 Celery 任务。

Celery 会自动发现每个 app 下的 tasks.py（见 config/celery.py 的
autodiscover_tasks），因此任务写在这里即可被 worker 识别。
"""

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)


@shared_task(name="apps.common.tasks.cleanup_expired_cache")
def cleanup_expired_cache():
    """清理业务缓存中的过期键。

    说明：Redis 自身会按 TTL 自动淘汰过期键，本任务主要用于
    清理那些"因异常而残留"的键（例如写入时未设置 TTL 的键）。

    Returns:
        dict: 清理统计，便于在 Celery 结果中查看
    """
    # 本项目的缓存键统一带 biliinsight 前缀（见 settings 的 KEY_PREFIX）
    patterns = [
        "biliinsight:hot_videos:*",
        "biliinsight:ranking:*",
    ]

    deleted = 0
    for pattern in patterns:
        try:
            # django-redis 提供 delete_pattern；官方 RedisCache 没有此方法，
            # 因此这里做兼容处理：不支持时跳过，不影响主流程。
            if hasattr(cache, "delete_pattern"):
                deleted += cache.delete_pattern(pattern)
            else:
                logger.debug("当前缓存后端不支持 delete_pattern，跳过 %s", pattern)
        except Exception as exc:
            logger.warning("清理缓存 %s 失败: %s", pattern, exc)

    logger.info("缓存清理完成，共删除 %d 个键", deleted)
    return {"deleted": deleted, "patterns": patterns}


@shared_task(name="apps.common.tasks.ping")
def ping():
    """连通性测试任务，用于验证 Celery 链路。

    用法：
        python manage.py shell -c "from apps.common.tasks import ping; print(ping.delay().get(timeout=10))"

    期望返回 'pong'，同时 Worker 终端会打印日志。
    """
    logger.info("Celery ping 任务已执行")
    return "pong"

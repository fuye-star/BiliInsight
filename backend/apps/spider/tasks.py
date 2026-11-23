# -*- coding: utf-8 -*-
"""
spider 应用的 Celery 异步任务。

【为什么爬虫必须异步】
受合规限速约束（每次请求间隔 ≥ 1 秒），抓取 5 个分区各 50 条视频
大约需要 1-2 分钟。若放在 HTTP 请求里同步执行，前端会一直转圈甚至超时。
交给 Celery 后接口立即返回 task_id，前端轮询 CrawlTask 表即可展示进度。

【启动 Worker（Windows 必须加 -P solo）】
    celery -A config worker -l info -P solo

【合规要求（务必遵守）】
  · 请求间隔不低于 1.0 秒（由 settings.SPIDER_REQUEST_INTERVAL 控制，默认 2.0）
  · 遵守目标站点 robots.txt，仅抓取公开数据
  · User-Agent 中声明学习研究用途
"""

import logging
from datetime import datetime

from celery import shared_task
from django.utils import timezone

from apps.spider.base import RateLimitedError, SpiderError
from apps.spider.bilibili import BiliBiliSpider
from apps.spider.constants import DEFAULT_PARTITIONS
from apps.spider.models import CrawlTask

logger = logging.getLogger(__name__)


def _start_task(source: str, target: str, task_id: str = "") -> CrawlTask:
    """创建一条"执行中"的任务记录。

    参数:
        source:  任务类型（partition / hot / danmaku）
        target:  抓取目标描述
        task_id: Celery 任务 ID

    返回:
        新建的 CrawlTask 实例
    """
    return CrawlTask.objects.create(
        source=source,
        target=target,
        status="running",
        task_id=task_id,
        started_at=timezone.now(),
    )


def _finish_task(
    task: CrawlTask,
    stats,
    error_message: str = "",
) -> CrawlTask:
    """把任务标记为成功/失败并写入统计。

    参数:
        task:          CrawlTask 实例
        stats:         CrawlStats 统计对象（可为 None）
        error_message: 失败原因；非空即视为失败

    返回:
        更新后的 CrawlTask
    """
    task.finished_at = timezone.now()

    if error_message:
        task.status = "failed"
        task.error_message = error_message[:2000]
    else:
        task.status = "success"
        if stats is not None:
            data = stats.as_dict()
            task.total_fetched = data["total_fetched"]
            task.total_created = data["total_created"]
            task.total_updated = data["total_updated"]
            task.total_failed = data["total_failed"]

    task.save(
        update_fields=[
            "status", "finished_at", "error_message",
            "total_fetched", "total_created", "total_updated", "total_failed",
            "updated_at",
        ]
    )

    # ---- 清空分析类缓存 ----
    # 【为什么必须在这里清】
    #   分析接口（overview / top-upusers / top-videos / sentiment / wordcloud）
    #   都带 300-600 秒的 Redis 缓存。数据写完了却不清缓存，
    #   看板会继续吐旧数字最长 10 分钟。
    #
    #   实测表现：视频列表页（/api/videos/，无缓存）立刻变成新数据，
    #   而数据总览、UP主排行、情感分析仍是旧值 ——
    #   看起来像"部分页面没同步"，实际是缓存没失效。
    #
    #   放在 _finish_task 里，5 个抓取任务自动全部获得该行为，
    #   不需要每个任务各写一遍（避免以后再有人漏掉）。
    #
    #   仅在有实际写入时清理，避免无意义地击穿缓存。
    if task.status == "success" and (task.total_created or task.total_updated):
        try:
            from apps.analytics.services import clear_analytics_cache

            deleted = clear_analytics_cache()
            logger.info("抓取任务完成，已清理分析缓存 %d 个键", deleted)
        except Exception as exc:
            # 清缓存失败绝不能影响"抓取成功"这个事实，降级为警告
            logger.warning("清理分析缓存失败（不影响抓取结果）：%s", exc)

    return task


def _classify_error(exc: Exception) -> str:
    """把异常转成对用户友好的错误描述。

    【为什么要分类】
    "被限流"和"网络超时"对使用者的处理方式完全不同：
    前者要调大请求间隔并等待，后者只需重试。直接抛出原始堆栈没有指导意义。
    """
    if isinstance(exc, RateLimitedError):
        return (
            f"被目标站点风控限流：{exc}。"
            f"处理方式：① 等待 10-30 分钟让风控冷却；"
            f"② 调大 .env 中的 SPIDER_REQUEST_INTERVAL（建议 3.0-5.0 秒）；"
            f"③ 减少单次抓取的 limit。切勿立即重试，否则会延长封禁时间。"
        )
    if isinstance(exc, SpiderError):
        return f"抓取失败：{exc}"
    return f"未预期错误 {type(exc).__name__}：{exc}"


# ===========================================================================
# 任务定义
# ===========================================================================
@shared_task(bind=True, name="apps.spider.tasks.crawl_partition")
def crawl_partition(self, partition_name: str, limit: int = 50):
    """抓取指定分区的排行榜视频。

    参数:
        partition_name: 分区名，如 "科技"
        limit:          最多入库条数

    返回:
        dict，含 task_id 与统计结果（会存入 Celery 结果后端）
    """
    target = f"分区:{partition_name}"
    task = _start_task("partition", target, task_id=self.request.id)
    logger.info("开始抓取 %s（limit=%d，任务 #%d）", target, limit, task.pk)

    spider = BiliBiliSpider()
    try:
        stats = spider.run_partition(partition_name, limit=limit)
        _finish_task(task, stats)
        logger.info("抓取完成 %s：新增 %d 条", target, stats.created)
        return {"task_id": self.request.id, "db_id": task.pk, "status": "success",
                **stats.as_dict()}
    except Exception as exc:
        message = _classify_error(exc)
        _finish_task(task, None, error_message=message)
        logger.error("抓取失败 %s：%s", target, message)
        # 重新抛出，让 Celery 记录为 FAILURE 状态，便于结果后端查询
        raise
    finally:
        spider.close()


@shared_task(name="apps.spider.tasks.crawl_all_partitions")
def crawl_all_partitions(limit: int = 50):
    """抓取全部默认分区的视频（由 Celery Beat 每 6 小时调度）。

    参数:
        limit: 每个分区的入库上限

    返回:
        dict 统计结果
    """
    target = f"批量:{len(DEFAULT_PARTITIONS)}个分区"
    task = _start_task("partition", target)
    logger.info("开始批量抓取分区：%s", DEFAULT_PARTITIONS)

    spider = BiliBiliSpider()
    try:
        stats = spider.run_all_partitions(limit=limit)
        _finish_task(task, stats)
        return {"db_id": task.pk, "status": "success", **stats.as_dict()}
    except Exception as exc:
        message = _classify_error(exc)
        _finish_task(task, None, error_message=message)
        logger.error("批量抓取失败：%s", message)
        raise
    finally:
        spider.close()


@shared_task(bind=True, name="apps.spider.tasks.crawl_hot")
def crawl_hot(self, limit: int = 50):
    """抓取全站热门榜视频。

    参数:
        limit: 入库上限
    """
    target = "全站热门"
    task = _start_task("hot", target, task_id=self.request.id)

    spider = BiliBiliSpider()
    try:
        stats = spider.run_hot(limit=limit)
        _finish_task(task, stats)
        return {"task_id": self.request.id, "db_id": task.pk, "status": "success",
                **stats.as_dict()}
    except Exception as exc:
        message = _classify_error(exc)
        _finish_task(task, None, error_message=message)
        logger.error("热门抓取失败：%s", message)
        raise
    finally:
        spider.close()


@shared_task(bind=True, name="apps.spider.tasks.crawl_danmaku")
def crawl_danmaku(self, bvid: str, limit: int = 3000, max_segments: int = 20):
    """抓取指定视频的弹幕。

    参数:
        bvid:         视频 BV 号
        limit:        弹幕入库上限
        max_segments: 最多读取的弹幕分包数（每包 6 分钟）
    """
    target = f"弹幕:{bvid}"
    task = _start_task("danmaku", target, task_id=self.request.id)
    logger.info("开始抓取弹幕 %s（limit=%d）", bvid, limit)

    spider = BiliBiliSpider()
    try:
        stats = spider.run_danmaku(bvid, limit=limit, max_segments=max_segments)
        _finish_task(task, stats)
        return {"task_id": self.request.id, "db_id": task.pk, "status": "success",
                **stats.as_dict()}
    except Exception as exc:
        message = _classify_error(exc)
        _finish_task(task, None, error_message=message)
        logger.error("弹幕抓取失败 %s：%s", bvid, message)
        raise
    finally:
        spider.close()


@shared_task(name="apps.spider.tasks.batch_crawl_danmaku")
def batch_crawl_danmaku(limit_videos: int = 10, limit_danmaku: int = 2000):
    """为"弹幕数最多"的若干视频批量抓取弹幕。

    这个任务让情感分析有足够的数据可跑，
    也避免人工一个个指定 bvid。

    参数:
        limit_videos:  抓取多少个视频
        limit_danmaku: 每个视频的弹幕上限
    """
    from apps.videos.models import Video

    target = f"批量弹幕:前{limit_videos}个视频"
    task = _start_task("danmaku", target)

    # 选择弹幕数多且尚未抓取弹幕的视频，优先补数据空白
    videos = list(
        Video.objects.filter(danmaku_count__gt=0)
        .order_by("-danmaku_count")[:limit_videos]
    )

    if not videos:
        _finish_task(task, None, error_message="数据库中没有视频，请先抓取视频")
        return {"db_id": task.pk, "status": "failed", "reason": "no videos"}

    spider = BiliBiliSpider()
    try:
        for video in videos:
            try:
                spider.run_danmaku(
                    video.bvid, limit=limit_danmaku, video=video
                )
            except Exception as exc:
                logger.warning("视频 %s 弹幕抓取失败：%s", video.bvid, exc)
                spider.stats.failed += 1

        _finish_task(task, spider.stats)
        return {"db_id": task.pk, "status": "success",
                "videos": len(videos), **spider.stats.as_dict()}
    finally:
        spider.close()

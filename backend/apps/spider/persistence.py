# -*- coding: utf-8 -*-
"""
入库层 —— 把解析后的实体写入数据库。

【为什么单独抽一层】
BaseSpider 负责"取回并解析"，本模块负责"落库"。
分开后有两个好处：
  1. 爬虫可以在不连数据库的情况下做单元测试（注入假的 upsert 函数）；
  2. 数据模型变化时只需改这里，爬虫主体不受影响。

【幂等性设计（关键）】
所有写入都基于唯一键做 update_or_create：
    · Video   以 bvid 为唯一键
    · UpUser  以 mid 为唯一键
    · Danmaku 以 (video, dmid) 为唯一键
因此重复抓取同一批数据不会产生重复记录，只会更新计数与时间，
可以放心地把爬虫挂成每 6 小时跑一次的定时任务。
"""

import logging
from typing import Optional

from django.db import transaction

from apps.videos.models import Danmaku, Partition, UpUser, Video

from .constants import DanmakuItem, VideoItem

logger = logging.getLogger(__name__)


def upsert_partition(name: str, tid: Optional[int] = None) -> Optional[Partition]:
    """按名称写入或更新分区。

    参数:
        name: 分区名，如 "科技"
        tid:  B站分区 ID

    返回:
        Partition 实例；name 为空时返回 None
    """
    name = (name or "").strip()
    if not name:
        return None

    defaults = {}
    if tid:
        defaults["bili_tid"] = tid

    partition, _created = Partition.objects.update_or_create(
        name=name,
        defaults=defaults,
    )
    return partition


def upsert_upuser(item: VideoItem) -> Optional[UpUser]:
    """从视频实体中提取 UP主信息并入库。

    参数:
        item: 视频实体（需含 up_mid / up_name）

    返回:
        UpUser 实例；缺少 mid 时返回 None

    说明：排行榜接口不返回粉丝数，因此 follower_count 保持默认 0，
    不覆盖已有值（避免把之前抓到的粉丝数清零）。
    """
    if not item.up_mid:
        return None

    defaults = {}
    if item.up_name:
        defaults["name"] = item.up_name
    if item.up_avatar:
        defaults["avatar"] = item.up_avatar

    upuser, _created = UpUser.objects.update_or_create(
        mid=item.up_mid,
        defaults=defaults,
    )
    return upuser


def upsert_video(item: VideoItem) -> tuple[Optional[Video], bool]:
    """把视频实体写入数据库（幂等）。

    参数:
        item: 解析后的视频实体

    返回:
        (Video 实例 或 None, 是否新建)

    说明：
      · 关联的 UP主 与 分区 会按需自动创建；
      · interaction_rate 在入库时计算并存储（冗余字段，见模型注释）。
    """
    if not item.bvid:
        return None, False

    partition = upsert_partition(item.tname, item.tid)
    upuser = upsert_upuser(item)

    defaults = {
        "title": item.title[:300],           # 兜底截断，防止超长标题入库报错
        "description": item.description,
        "cover_url": item.cover_url[:500],
        "duration": item.duration,
        "pubdate": item.pubdate,
        "tags": item.tags[:500],
        "view_count": item.view_count,
        "like_count": item.like_count,
        "coin_count": item.coin_count,
        "favorite_count": item.favorite_count,
        "share_count": item.share_count,
        "danmaku_count": item.danmaku_count,
        "reply_count": item.reply_count,
        "partition": partition,
        "upuser": upuser,
    }
    if item.aid:
        defaults["aid"] = item.aid
    # cid 用于抓弹幕（作为 oid 参数）。排行榜接口本身就返回它，
    # 存下来之后抓弹幕就不必再为每个视频单独请求一次详情接口。
    if item.cid:
        defaults["cid"] = item.cid

    # 互动率：(点赞 + 投币 + 收藏) / 播放量
    # 入库时算好并冗余存储，使榜单排序可以走索引而非实时计算
    if item.view_count > 0:
        interactions = item.like_count + item.coin_count + item.favorite_count
        defaults["interaction_rate"] = round(interactions / item.view_count, 6)
    else:
        defaults["interaction_rate"] = 0.0

    video, created = Video.objects.update_or_create(
        bvid=item.bvid,
        defaults=defaults,
    )
    return video, created


def upsert_danmaku(video: Video, items: list[DanmakuItem]) -> tuple[int, int]:
    """批量写入弹幕（幂等）。

    参数:
        video: 所属视频实例
        items: 弹幕实体列表

    返回:
        (新建条数, 已存在被更新条数)

    【性能说明】
    逐条 update_or_create 会产生 2 次查询（SELECT + INSERT/UPDATE），
    万条弹幕下较慢。这里用 ignore_conflicts 做批量插入：
      · 已存在的 (video, dmid) 直接跳过，不报错也不更新
      · 只统计真正新增的条数
    弹幕内容本身不会变化，因此"跳过已存在"是正确且最快的策略。
    """
    if not items:
        return 0, 0

    # 弹幕必须有 dmid 才能去重；没有 dmid 的按内容+时间兜底跳过
    objects = []
    for it in items:
        if it.dmid is None:
            continue
        objects.append(
            Danmaku(
                video=video,
                dmid=it.dmid,
                content=it.content[:500],
                video_time=it.video_time,
                send_time=it.send_time,
            )
        )

    if not objects:
        return 0, 0

    before = Danmaku.objects.filter(video=video).count()

    with transaction.atomic():
        # bulk_create + ignore_conflicts：依赖 uniq_danmaku_video_dmid 唯一约束
        Danmaku.objects.bulk_create(
            objects,
            batch_size=1000,
            ignore_conflicts=True,
        )

    after = Danmaku.objects.filter(video=video).count()
    created = after - before
    skipped = len(objects) - created

    logger.info(
        "弹幕入库完成：视频 %s 新增 %d 条，已存在跳过 %d 条",
        video.bvid, created, skipped,
    )
    return created, skipped

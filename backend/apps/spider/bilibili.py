# -*- coding: utf-8 -*-
"""
BiliBiliSpider —— B站具体实现。

继承 BaseSpider 后，限速、重试、UA、日志、统计全部自动获得，
本文件只关注三件事：
    1. 请求哪些接口、带什么参数      -> fetch_*
    2. 如何把响应变成实体            -> 复用 parsers 模块
    3. 如何编排整个抓取流程          -> run()

【支持的抓取模式】
    run_partition(name, limit)   抓取指定分区的排行榜视频
    run_hot(limit)               抓取全站热门视频
    run_danmaku(bvid, limit)     抓取指定视频的弹幕

【合规提醒】
  · 请求间隔由 BaseSpider 强制不低于 1.0 秒
  · 仅抓取公开数据，不涉及登录态与用户隐私
  · 仅用于学习研究，禁止商业用途
"""

import json
import logging
from typing import Callable, Optional

from .base import BaseSpider, CrawlStats, ParseError, RateLimitedError, SpiderError
from .constants import (
    BiliAPI,
    DEFAULT_PARTITIONS,
    VideoItem,
    partition_tid,
)
from . import parsers, persistence

logger = logging.getLogger(__name__)


def _notify_progress(callback, index: int, total: int, stats) -> None:
    """安全地调用进度回调。

    【为什么单独抽一个函数】
        进度回调只是"界面进度条"这种非关键逻辑，
        它一旦抛异常绝不能中断抓取。统一在这里 try/except，
        调用方就不必到处包 try 了。
    """
    if callback is None:
        return
    try:
        callback(index, total, stats)
    except Exception:  # noqa: BLE001
        pass


class BiliBiliSpider(BaseSpider):
    """B站爬虫。

    用法：
        spider = BiliBiliSpider()
        stats = spider.run_partition("科技", limit=50)
        print(stats.as_dict())
    """

    name = "bilibili"
    base_url = "https://www.bilibili.com"

    def __init__(self, *args, upsert_video_fn: Optional[Callable] = None, **kwargs):
        """初始化。

        参数:
            upsert_video_fn: 可选的入库函数，签名 (VideoItem) -> (Video, created)。
                             默认使用 persistence.upsert_video。
                             单元测试时可注入桩函数，从而不触碰数据库。

        其余参数透传给 BaseSpider（interval / max_retries / user_agent）。
        """
        super().__init__(*args, **kwargs)
        self._upsert_video = upsert_video_fn or persistence.upsert_video

    # =====================================================================
    # 请求层
    # =====================================================================
    def fetch_ranking(self, tid: Optional[int] = None) -> dict:
        """请求分区排行榜。

        参数:
            tid: 分区 ID；不传则请求全站排行榜

        返回:
            接口 JSON（dict）

        异常:
            RateLimitedError: 被限流
        """
        params = {"type": "all"}
        if tid is not None:
            params["rid"] = tid

        logger.info("[%s] 抓取排行榜 tid=%s", self.name, tid if tid else "全站")
        return self.request(BiliAPI.RANKING, params=params)

    def fetch_popular(self, page: int = 1, page_size: int = 50) -> dict:
        """请求"全站热门"列表（支持翻页）。

        参数:
            page:      页码，从 1 开始
            page_size: 每页条数（B站上限约 50）

        返回:
            接口 JSON（dict）

        【为什么除了排行榜还要这个接口】
            实测发现**不同接口的风控额度差别很大**：
            `/x/web-interface/ranking/v2`（分区排行榜）最敏感，
            连续抓几个分区就会被 -352 拦住；而热门列表是另一个端点，
            并且**支持翻页**，一次能稳定取回一批。

            两者互补：排行榜拿不到时可以换热门继续，反之以然 ——
            这在需要批量灌数据的场景（例如给桌面版准备初始数据集）很关键。
        """
        logger.info("[%s] 抓取全站热门 第 %d 页", self.name, page)
        return self.request(
            BiliAPI.POPULAR,
            params={"ps": page_size, "pn": page},
        )

    def fetch_video_detail(self, bvid: str) -> dict:
        """请求视频详情（含 tags 与 cid）。

        参数:
            bvid: 如 BV1xx411c7mD

        返回:
            接口 JSON（dict）
        """
        logger.debug("[%s] 抓取视频详情 bvid=%s", self.name, bvid)
        return self.request(BiliAPI.VIDEO_INFO, params={"bvid": bvid})

    def fetch_upuser_stat(self, mid: int) -> dict:
        """请求 UP主 关系统计（取粉丝数）。

        参数:
            mid: UP主 的 B站用户 ID

        返回:
            接口 JSON（dict）

        【为什么需要单独一次请求】
            排行榜接口的 owner 字段只有 mid / name / face，
            **不包含粉丝数**。所以要让「UP主排行」按粉丝数排序，
            只能对每位 UP主 单独调用本接口。
            代价是 1 位 UP主 = 1 次请求，因此调用方必须先按 mid 去重。
        """
        logger.debug("[%s] 抓取 UP主 统计 mid=%s", self.name, mid)
        return self.request(BiliAPI.RELATION_STAT, params={"vmid": mid})

    def fetch_danmaku_segment(self, cid: int, segment_index: int) -> bytes:
        """请求一包弹幕（protobuf 二进制）。

        参数:
            cid:           视频 cid
            segment_index: 分包序号，从 1 开始，每包覆盖 6 分钟

        返回:
            原始字节（response.content）

        异常:
            RateLimitedError: 被限流（响应体是 JSON 错误信息）
        """
        params = {
            "type": 1,               # 1 = 视频弹幕
            "oid": cid,              # 注意：弹幕接口用的是 cid，不是 avid
            "segment_index": segment_index,
        }
        logger.debug(
            "[%s] 抓取弹幕 cid=%s segment=%d", self.name, cid, segment_index
        )
        # 弹幕是二进制，必须用 expect_json=False 拿原始字节
        raw = self.request(BiliAPI.DANMAKU_SEG, params=params, expect_json=False)
        return self._guard_danmaku_payload(raw)

    def _guard_danmaku_payload(self, raw: bytes) -> bytes:
        """拦截弹幕接口返回的 JSON 错误体，转成明确的异常。

        【为什么必须做这一步 —— 一个很隐蔽的坑】
            弹幕接口**被风控时依然返回 HTTP 200**，只是响应体变成一小段 JSON：

                {"code":-352,"message":"请求过于频繁，请稍后再试"}

            而本接口因为是二进制协议，调用时传了 `expect_json=False`，
            于是这段 JSON **绕过了 BaseSpider 里所有的业务码检查**
            （包括限流识别），被原样交给 protobuf 解析器。

            解析器看到的是一堆它不认识的字节，报出的是：

                不支持的 wire_type=3（已解析 0 条）

            —— 完全看不出真实原因。实测后果很严重：
            抓 40 个视频的弹幕时，有 19 个被静默判成"这个视频没有弹幕"，
            每个还白白消耗了一次请求额度，而且重跑也依然失败。

            这里按特征识别：正常的弹幕数据是二进制，
            而 JSON 错误体**一定以 `{`(0x7B) 开头**。
            识别出来后按业务码抛出正确的异常，让上层节奏控制器能正确退避。

        参数:
            raw: 接口返回的原始字节

        返回:
            校验通过的原始字节

        异常:
            RateLimitedError: 响应是风控码
            SpiderError:      响应是其它非预期内容
        """
        if raw[:1] != b"{":
            # 正常情况：protobuf 二进制，直接放行
            return raw

        # 是 JSON —— 说明接口返回了错误信息而不是弹幕数据
        code = None
        try:
            payload = json.loads(raw.decode("utf-8", errors="ignore"))
            code = payload.get("code")
        except Exception:  # noqa: BLE001
            pass

        preview = raw[:120]
        if code in self.RATE_LIMIT_CODES:
            raise RateLimitedError(
                f"接口返回 {code}（弹幕分段），触发目标站点风控"
            )

        raise SpiderError(
            f"弹幕接口返回了非预期内容（不是 protobuf）："
            f"code={code} body={preview!r}"
        )

    # =====================================================================
    # 编排层：抓取视频
    # =====================================================================
    def run(self, *args, **kwargs) -> CrawlStats:
        """BaseSpider 要求的统一入口，等价于 run_hot()。

        之所以让 run() 指向热门榜，是为了让子类满足抽象接口，
        同时保持"直接实例化后调用 run()"也有合理行为。
        """
        return self.run_hot(*args, **kwargs)

    def run_partition(self, partition_name: str, limit: int = 50) -> CrawlStats:
        """抓取指定分区的排行榜视频并入库。

        参数:
            partition_name: 分区名（如 "科技"）或数字 tid
            limit:          最多入库条数（排行榜单次最多返回约 100 条）

        返回:
            CrawlStats 统计结果
        """
        tid = partition_tid(partition_name)
        if tid is None:
            raise ValueError(
                f"无法识别的分区名：{partition_name}。"
                f"可用分区：{', '.join(DEFAULT_PARTITIONS)} 等（见 constants.PARTITIONS）"
            )

        payload = self.fetch_ranking(tid)
        items = parsers.parse_video_list(payload)

        # 排行榜接口不返回 tags，这里补一个 tags 来源：
        # 用 tname（细分分区名）作为基础标签，保证词云有一定内容
        for item in items:
            if not item.tags and item.tname:
                item.tags = item.tname

        return self._save_videos(items, limit=limit, scope=f"分区:{partition_name}")

    def run_hot(self, limit: int = 50) -> CrawlStats:
        """抓取全站排行榜视频并入库。

        ⚠️ 注意：本方法走的是 `ranking/v2` 接口（只是不带 rid）。
        要抓真正的"热门列表"（支持翻页、风控更宽松），
        请用 run_popular()。

        参数:
            limit: 最多入库条数

        返回:
            CrawlStats 统计结果
        """
        payload = self.fetch_ranking(tid=None)
        items = parsers.parse_video_list(payload)
        return self._save_videos(items, limit=limit, scope="全站排名")

    def run_popular(
        self,
        limit: int = 100,
        max_pages: int = 12,
        page_size: int = 50,
        start_page: int = 1,
    ) -> CrawlStats:
        """按页抓取"全站热门"并入库。

        参数:
            limit:      最多入库条数
            max_pages:  最多翻多少页
            page_size:  每页条数（B站上限约 50）
            start_page: 从第几页开始（用于"每次点击往前翻"的场景）

        返回:
            CrawlStats 统计结果（本次累计）

        【适用场景】
            需要**批量**灌数据时（例如给桌面版准备初始数据集）。
            排行榜接口每个分区只能拿约 97 条且风控最严，
            而热门列表可以翻页，几页就能凑够几百条。

        【start_page 有什么用】
            界面上的「更新数据」按钮如果每次都从第 1 页拉，
            由于这些视频早已入库，结果永远是"新增 0 条、更新 N 条"，
            使用者会觉得"点了没反应"。

            配合调用方维护的页码游标，每次点击都从上次的下一页开始，
            就能**持续拿到新视频**（实测第 8、12 页几乎全是新内容）。
        """
        stats = CrawlStats()
        saved = 0

        start_page = max(1, int(start_page or 1))
        last_page = start_page - 1

        for page in range(start_page, start_page + max_pages):
            if saved >= limit:
                break

            payload = self.fetch_popular(page=page, page_size=page_size)
            data = payload.get("data") or {}
            items = parsers.parse_video_list(payload)
            if not items:
                logger.info("[%s] 热门第 %d 页无数据，结束", self.name, page)
                break

            last_page = page

            # 热门接口同样不返回 tags，用细分分区名兜底
            for item in items:
                if not item.tags and item.tname:
                    item.tags = item.tname

            page_stats = self._save_videos(
                items, limit=limit - saved, scope=f"热门第{page}页"
            )
            stats.merge(page_stats)
            saved += page_stats.created + page_stats.updated
            logger.info(
                "[%s] 热门第 %d 页：解析 %d 条，新增 %d 条，累计入库 %d 条",
                self.name, page, page_stats.fetched, page_stats.created, saved,
            )

            # no_more 为真说明没有下一页了
            if data.get("no_more"):
                logger.info("[%s] 热门列表已到末页（第 %d 页）", self.name, page)
                break

        # 把"下一页"的提示藏在统计里，供调用方维护游标
        stats.last_page = last_page
        return stats

    def _save_videos(self, items: list[VideoItem], limit: int, scope: str) -> CrawlStats:
        """把视频实体批量入库，并累计统计。

        参数:
            items: 解析后的视频实体
            limit: 入库上限
            scope: 日志中显示的范围描述

        返回:
            本次的 CrawlStats（会累加到 self.stats）
        """
        stats = CrawlStats(fetched=len(items))
        saved = 0

        for item in items:
            if saved >= limit:
                break
            try:
                _video, created = self._upsert_video(item)
                if created:
                    stats.created += 1
                else:
                    stats.updated += 1
                saved += 1
            except Exception as exc:
                stats.failed += 1
                logger.warning("[%s] 视频入库失败 bvid=%s：%s", self.name, item.bvid, exc)

        self.stats.merge(stats)
        logger.info(
            "[%s] %s 抓取完成：解析 %d 条，新增 %d，更新 %d，失败 %d",
            self.name, scope, stats.fetched, stats.created, stats.updated, stats.failed,
        )
        return stats

    # =====================================================================
    # 编排层：抓取 UP主 粉丝数
    # =====================================================================
    def run_upuser_followers(
        self,
        mids: Optional[list] = None,
        skip_filled: bool = True,
        limit: int = 0,
        on_progress: Optional[Callable] = None,
    ) -> CrawlStats:
        """为 UP主 抓取粉丝数并回填数据库。

        参数:
            mids:        要处理的 mid 列表；None 表示"全库中粉丝数为 0 的 UP主"
            skip_filled: 是否跳过粉丝数已有值的 UP主（避免白费请求）
            limit:       最多处理多少位；0 表示不限
            on_progress: 可选回调 (已处理数, 总数, 当前统计)，
                         供界面显示进度 —— 几十位 UP主 要跑一两分钟，
                         没有进度会让人以为卡死了

        返回:
            CrawlStats
                fetched = 成功取到粉丝数的位次
                updated = 实际写库更新的行数
                failed  = 单次请求失败的位次

        【请求成本】
            1 位 UP主 = 1 次请求。这是本项目最"贵"的一项抓取
            （40 个视频往往来自 40 位不同的 UP主，就是 40 次请求）。
            因此这里做了三重节省：
              ① 按 mid 去重 —— 同一 UP主 只请求一次
              ② skip_filled —— 已有粉丝数的直接跳过
              ③ 按粉丝数升序处理 —— 先补 0 的（粉丝多的 UP主 通常先被别的路劲填上）

        【风控处理与其它方法不同】
            本方法**不抛出** RateLimitedError，而是记录后**停止后续请求**。
            原因：调用它时视频已经入库成功了，若因为补粉丝数失败就把整条命令
            判为失败，会掩盖"视频抓取其实成功了"这个事实。
            已抓到的部分照常保留，属于"尽力而为"的增强步骤。
        """
        from apps.videos.models import UpUser

        stats = CrawlStats()

        # ---- 1. 确定要处理的 mid 列表 ----
        if mids is None:
            qs = UpUser.objects.all()
            if skip_filled:
                qs = qs.filter(follower_count=0)
            # 升序：粉丝数为 0 的、mid 小的优先，行为可预期
            mids = list(qs.order_by("follower_count", "mid").values_list("mid", flat=True))

        # 去重但保持顺序：同一 UP主 只请求一次
        seen = set()
        unique_mids = []
        for mid in mids:
            if mid and mid not in seen:
                seen.add(mid)
                unique_mids.append(mid)

        if limit and limit > 0:
            unique_mids = unique_mids[:limit]

        if not unique_mids:
            logger.info("[%s] 没有需要补粉丝数的 UP主", self.name)
            return stats

        logger.info(
            "[%s] 开始抓取 %d 位 UP主 的粉丝数（1 位 1 次请求）",
            self.name, len(unique_mids),
        )

        total = len(unique_mids)

        # ---- 2. 逐位请求 ----
        for index, mid in enumerate(unique_mids, start=1):
            stats.fetched += 1
            try:
                payload = self.fetch_upuser_stat(mid)
            except RateLimitedError:
                # 见方法文档：不抛出，停止后续请求，保留已抓到的部分
                stats.fetched -= 1
                logger.warning(
                    "[%s] 抓 UP主 粉丝数时被风控限流，已停止（已成功的部分保留）",
                    self.name,
                )
                break
            except Exception as exc:
                stats.failed += 1
                logger.warning("[%s] UP主 %s 粉丝数抓取失败：%s", self.name, mid, exc)
                _notify_progress(on_progress, index, total, stats)
                continue

            parsed = parsers.parse_upuser_stat(payload)
            if parsed is None:
                stats.failed += 1
                _notify_progress(on_progress, index, total, stats)
                continue

            try:
                updated = UpUser.objects.filter(mid=mid).update(
                    follower_count=parsed["follower_count"]
                )
                stats.updated += updated
            except Exception as exc:
                stats.failed += 1
                logger.warning("[%s] UP主 %s 粉丝数入库失败：%s", self.name, mid, exc)

            _notify_progress(on_progress, index, total, stats)

        self.stats.merge(stats)
        logger.info(
            "[%s] UP主 粉丝数抓取完成：成功 %d 位，更新 %d 行，失败 %d 位",
            self.name, stats.fetched, stats.updated, stats.failed,
        )
        return stats

    # =====================================================================
    # 编排层：批量抓弹幕
    # =====================================================================
    def run_danmaku_for_videos(
        self,
        bvids: list,
        limit: int = 50,
        max_segments: int = 20,
    ) -> CrawlStats:
        """为一批视频依次抓取弹幕。

        参数:
            bvids:        视频 BV 号列表
            limit:        单个视频最多入库弹幕条数（注意：见下方说明）
            max_segments: 单个视频最多读取的弹幕分包数

        返回:
            CrawlStats（累加各视频的结果）

        【limit 的真实语义】
            代码只在"包与包之间"检查 `collected >= limit`，
            而一包（6 分钟）内的弹幕是**整包入库**的。
            因此 limit=50 的实际含义是"只抓一包就停"，
            一包里可能有几千条弹幕，全部都会入库。
            用它把请求数压到最低（每视频 2 次：1 次取 cid + 1 次取弹幕包）。

        【风控处理】
            与 run_upuser_followers 同理：被限流时停止后续视频，
            不抛出异常，保留已抓到的弹幕。
        """
        from apps.videos.models import Video

        for i, bvid in enumerate(bvids, start=1):
            logger.info(
                "[%s] 弹幕进度 %d/%d：%s", self.name, i, len(bvids), bvid
            )
            video = Video.objects.filter(bvid=bvid).first()
            if video is None:
                logger.warning("[%s] 数据库中无 %s，跳过弹幕抓取", self.name, bvid)
                continue

            try:
                self.run_danmaku(
                    bvid, limit=limit, max_segments=max_segments, video=video
                )
            except RateLimitedError:
                logger.warning(
                    "[%s] 抓弹幕时被风控限流，已停止在 %s（已抓到的部分保留）",
                    self.name, bvid,
                )
                break
            except Exception as exc:
                logger.warning("[%s] %s 弹幕抓取失败：%s", self.name, bvid, exc)

        return self.stats

    # =====================================================================
    # 编排层：抓取弹幕
    # =====================================================================
    def run_danmaku(
        self,
        bvid: str,
        limit: int = 3000,
        max_segments: int = 20,
        video=None,
    ) -> CrawlStats:
        """抓取指定视频的弹幕并入库。

        参数:
            bvid:         视频 BV 号
            limit:        最多入库弹幕条数（防止超长视频抓取过久）
            max_segments: 最多读取的弹幕分包数（每包 6 分钟）
            video:        已有 Video 实例；不传则按 bvid 查询数据库

        返回:
            CrawlStats 统计结果

        说明：
          弹幕分两段处理——先确保视频存在（含 cid），
          再按 6 分钟一包逐包拉取，直到达到 limit 或分包耗尽。
        """
        from apps.videos.models import Video

        stats = CrawlStats()

        # ---- 1. 确定 video 与 cid ----
        # cid 是弹幕接口的必填参数。
        # 优先用库里已存的 cid（排行榜接口就会返回它）——这样能省掉一次详情请求。
        # 只有当库里没有时才回落到详情接口。
        if video is None:
            video = Video.objects.filter(bvid=bvid).first()

        cid = video.cid if (video is not None and video.cid) else None
        if cid is None:
            cid = self._fetch_cid(bvid)

        if cid is None:
            logger.warning("[%s] 无法获取 cid，跳过弹幕抓取 bvid=%s", self.name, bvid)
            stats.failed += 1
            self.stats.merge(stats)
            return stats

        # ---- 2. 逐包抓取 ----
        collected = 0
        for segment in range(1, max_segments + 1):
            if collected >= limit:
                break

            try:
                raw = self.fetch_danmaku_segment(cid, segment)
            except RateLimitedError:
                logger.warning("[%s] 弹幕抓取被限流，已停止在 segment=%d", self.name, segment)
                break
            except Exception as exc:
                logger.warning("[%s] 弹幕分包 %d 抓取失败：%s", self.name, segment, exc)
                stats.failed += 1
                break

            items = parsers.parse_danmaku_protobuf(raw)
            if not items:
                # 该包为空说明后面没有更多弹幕了，提前结束
                logger.debug("[%s] segment=%d 无弹幕，结束抓取", self.name, segment)
                break

            stats.fetched += len(items)

            if video is not None:
                try:
                    created, _skipped = persistence.upsert_danmaku(video, items)
                    stats.created += created
                except Exception as exc:
                    stats.failed += 1
                    logger.warning("[%s] 弹幕入库失败 segment=%d：%s", self.name, segment, exc)

            collected += len(items)

        self.stats.merge(stats)
        logger.info(
            "[%s] 弹幕抓取完成 bvid=%s：解析 %d 条，新增 %d 条，失败 %d",
            self.name, bvid, stats.fetched, stats.created, stats.failed,
        )
        return stats

    def _fetch_cid(self, bvid: str) -> Optional[int]:
        """通过视频详情接口取 cid。

        参数:
            bvid: 视频 BV 号

        返回:
            cid 整数；取不到返回 None

        说明：弹幕接口需要 cid 而非 bvid，因此这是抓弹幕的前置步骤。
        """
        try:
            payload = self.fetch_video_detail(bvid)
        except Exception as exc:
            logger.warning("[%s] 获取视频详情失败 bvid=%s：%s", self.name, bvid, exc)
            return None

        item = parsers.parse_video_detail(payload)
        if item is None or not item.cid:
            return None

        # 顺手把 cid 与 tags 回填数据库：
        #   · cid   —— 下次抓这个视频的弹幕就不必再请求详情接口
        #   · tags  —— 排行榜拿不到标签，详情接口才有，词云要用
        try:
            from apps.videos.models import Video

            fields = {"cid": item.cid}
            if item.tags:
                fields["tags"] = item.tags[:500]
            Video.objects.filter(bvid=bvid).update(**fields)
        except Exception:
            # 回填失败不影响本次弹幕抓取
            pass

        return item.cid

    # =====================================================================
    # 批量抓取
    # =====================================================================
    def run_all_partitions(
        self,
        partitions: Optional[list[str]] = None,
        limit: int = 50,
    ) -> CrawlStats:
        """依次抓取多个分区（供 Celery 定时任务调用）。

        参数:
            partitions: 分区名列表；默认使用 constants.DEFAULT_PARTITIONS
            limit:      每个分区入库上限

        返回:
            汇总后的 CrawlStats

        说明：分区之间复用同一个 session，但 BaseSpider 的限速依然生效，
        因此每抓一个分区都会自然间隔，不会形成突发流量。
        """
        names = partitions or DEFAULT_PARTITIONS

        logger.info("[%s] 开始批量抓取 %d 个分区：%s", self.name, len(names), names)

        # 重置累计统计，避免多次调用时重复累加
        self.stats = CrawlStats()

        for name in names:
            try:
                self.run_partition(name, limit=limit)
            except RateLimitedError as exc:
                # 被限流说明请求已经过于频繁，继续抓只会加重风控，直接终止
                logger.error("[%s] 批量抓取被限流，提前终止：%s", self.name, exc)
                break
            except Exception as exc:
                logger.warning("[%s] 分区 %s 抓取失败：%s", self.name, name, exc)
                self.stats.failed += 1
                continue

        logger.info(
            "[%s] 批量抓取结束：新增 %d 条，更新 %d 条，失败 %d 条，共发出 %d 次请求",
            self.name, self.stats.created, self.stats.updated,
            self.stats.failed, self.stats.requests,
        )
        return self.stats

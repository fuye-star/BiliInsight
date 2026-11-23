# -*- coding: utf-8 -*-
"""爬虫相关的 HTTP 接口。

【为什么桌面版需要这些接口】
    原来抓数据只能靠命令行：

        python manage.py crawl --partition 科技 --limit 40

    但桌面版的使用者是老师/同学，不可能去敲命令。
    因此把抓取能力暴露成接口，由界面上的「更新数据」按钮调用 ——
    这样"打包后还能不能更新数据"就有了一个可见、可演示的答案。

【两个接口的分工】

    ① POST /api/spider/crawl/     抓取排行榜（**同步**，约 2-5 秒）
       只发 1 次 HTTP 请求就能拿到约 100 条视频，含封面、播放量、UP主。
       足够让看板"焕然一新"，而且不会让前端等到超时。

    ② POST /api/spider/enrich/    补全细节（**后台线程**，可能几十秒）
       逐位补 UP主 粉丝数、逐视频抓弹幕。
       因为每项都是"1 位/1 个 = 1 次请求"，耗时不可控，
       所以放到后台线程执行，前端轮询 GET /api/spider/enrich/ 看进度。

【为什么同步接口要限制规模】
    浏览器/HTTP 客户端都有超时。排行榜单次请求本身很快（1 秒级），
    但如果一次请求里顺带补 40 位 UP主 的粉丝数（40 次请求 × 2 秒），
    就会超过一分钟 —— 前端会以为请求失败，体验很差。
    因此"快"和"全"拆成两个接口，让调用方自己决定。
"""

import logging
import threading
import time

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.analytics.services import clear_analytics_cache
from apps.common.response import BusinessCode, error, success
from apps.spider.base import CrawlStats, RateLimitedError
from apps.spider.bilibili import BiliBiliSpider
from apps.spider.constants import PARTITIONS, DEFAULT_PARTITIONS

logger = logging.getLogger(__name__)


# ===========================================================================
# 后台补全任务的状态（进程内）
# ===========================================================================
# 【为什么用一个模块级字典而不是数据库表】
#   桌面版只有一个用户、一个进程，任务状态只在"这一次运行"里有用 ——
#   程序重启后任务本来也中止了，持久化没有意义。
#   存内存里最简单，也避免为了一个进度条去建表。
_ENRICH_LOCK = threading.Lock()
_ENRICH_STATE = {
    "running": False,
    "message": "空闲",
    "stage": "",
    "total": 0,
    "done": 0,
    "followers": 0,
    "danmaku": 0,
    "error": "",
}


def _set_state(**kwargs) -> None:
    """线程安全地更新后台任务状态。"""
    with _ENRICH_LOCK:
        _ENRICH_STATE.update(kwargs)


def _get_state() -> dict:
    """取后台任务状态的快照。"""
    with _ENRICH_LOCK:
        return dict(_ENRICH_STATE)


# ===========================================================================
# 工具
# ===========================================================================
def _pick_partition(raw: str) -> str:
    """把前端传来的分区名规范化；不合法时回退到第一个默认分区。"""
    name = (raw or "").strip()
    if not name:
        return DEFAULT_PARTITIONS[0]
    if name in PARTITIONS:
        return name
    return DEFAULT_PARTITIONS[0]


def _clamp_int(value, default: int, low: int, high: int) -> int:
    """把任意输入转成夹在区间内的整数。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(number, high))


def _index_count() -> int:
    """当前向量索引条数（失败返回 0，不影响主流程）。"""
    try:
        from apps.ai.vector_store import get_index_stats

        return int(get_index_stats().get("count") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _rebuild_index_if_needed() -> int:
    """数据变了就重建向量索引，保证 AI 助手检索到的是一致的。

    本地向量化建 40 条约 1 秒，同步做完全可接受；
    不做的话 AI 助手会检索不到刚抓进来的新视频。
    """
    from apps.videos.models import Video

    try:
        from apps.ai.vector_store import build_index

        build_index(rebuild=True)
        return _index_count()
    except Exception as exc:  # noqa: BLE001
        # 索引失败只影响 AI 检索，抓取本身已经成功
        logger.warning("重建向量索引失败：%s", exc)
        return Video.objects.count() and _index_count()


#: 「更新数据」翻页游标：下次从热门榜第几页开始
_POPULAR_CURSOR_KEY = "spider:popular_cursor"

#: 游标初始值（没有游标记录时从第几页开始）
#:
#: 【为什么不是 1】
#:   预置数据集就是从热门榜前若干页抓的，第 1 页的内容几乎全在库里。
#:   从第 1 页开始点，前几次点击会反复读已收录的页，新增很少（实测首次只有 8 条）。
#:   从第 5 页起步可以少浪费几页，第一次点击就能拿到更靠后的新内容。
_POPULAR_INITIAL_PAGE = 5

#: 游标最多推进到第几页（再往后内容质量下降，且没必要一直翻）
_POPULAR_MAX_PAGE = 50

#: 一次点击最多连续读几页（跳过"已收录"的页用）
#:
#: 【为什么是 10 而不是 5、6】
#:   预置数据集覆盖了热门榜前 10 页左右。全新安装后第一次点击时，
#:   游标从第 5 页起步，前 5-6 页几乎都已收录 —— 只给 6 次机会的话，
#:   会出现"填了 5 条却只新增 3 条"的情况。
#:   放宽到 10 页，首次点击也能凑够目标条数（多花几次请求，只发生在首次）。
_POPULAR_MAX_ATTEMPTS = 10


def _get_popular_cursor() -> int:
    """读取热门翻页游标（从第几页开始）。"""
    from django.core.cache import cache

    try:
        value = int(cache.get(_POPULAR_CURSOR_KEY) or _POPULAR_INITIAL_PAGE)
    except Exception:  # noqa: BLE001
        value = _POPULAR_INITIAL_PAGE
    return max(1, min(value, _POPULAR_MAX_PAGE))


def _set_popular_cursor(page: int) -> None:
    """写回热门翻页游标。"""
    from django.core.cache import cache

    page = max(1, min(int(page or 1), _POPULAR_MAX_PAGE))
    try:
        # timeout=None 表示不过期；桌面版重启后 LocMem 会丢，相当于回到第 1 页
        cache.set(_POPULAR_CURSOR_KEY, page, None)
    except Exception:  # noqa: BLE001
        pass


def _crawl_popular(spider, limit: int, max_pages: int) -> dict:
    """从游标位置开始翻热门页，直到拿到 limit 条新视频。

    参数:
        limit:     目标新增条数（界面上的"条数"就是这个含义）
        max_pages: 最多连续读几页（跳过已收录的页用）

    返回:
        {"stats": CrawlStats, "next_page": int, "pages_read": int}

    【limit 的语义】
        它表示"本次希望新增多少条"，而不是"读多少页"。
        逐页读、每页最多存 `limit - 已新增` 条，够了就停 ——
        所以界面上填 5 就是"这次加 5 条"，填 40 就是"这次加 40 条"。

    【为什么要"跳过已收录的页"】
        界面上的「更新数据」如果每次固定从第 1 页拉，而这些视频早已入库，
        结果永远是"新增 0 条" —— 使用者会以为按钮坏了。

        实测热门榜的第 1 页几乎都已收录（只有 3 条新的），
        而第 6/8/12 页几乎全是新内容。因此这里逐页读、逐页判断：
        **只要这一页没有新视频，就继续读下一页**，
        直到凑够 limit 条、或连续读了 max_pages 页为止。
    """
    start_page = _get_popular_cursor()

    total = CrawlStats()
    page = start_page
    pages_read = 0

    for _attempt in range(max(1, max_pages)):
        # 还差多少条才达标；至少请求 1 条，避免剩 0 时白读一页
        remaining = max(1, limit - total.created)

        page_stats = spider.run_popular(
            limit=remaining,
            max_pages=1,
            start_page=page,
        )

        # last_page 为 0 说明这一页没取到数据（到底了）
        if page_stats.last_page == 0:
            # 绕回到初始页，下次重新扫（热门榜每天都在变，绕回后通常又有新内容）
            page = _POPULAR_INITIAL_PAGE
            break

        pages_read += 1
        total.fetched += page_stats.fetched
        total.created += page_stats.created
        total.updated += page_stats.updated
        total.failed += page_stats.failed

        page = page_stats.last_page + 1

        # 已经凑够目标条数，停
        if total.created >= limit:
            break
        if page > _POPULAR_MAX_PAGE:
            page = _POPULAR_INITIAL_PAGE
            break

    _set_popular_cursor(page)
    total.requests = spider.stats.requests
    return {"stats": total, "next_page": page, "pages_read": pages_read}


# ===========================================================================
# ① 抓取（同步）
# ===========================================================================
class CrawlNowView(APIView):
    """立即抓取一批真实数据（同步，秒级返回）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="立即抓取一批真实视频",
        description=(
            "默认走**全站热门**接口并自动翻页 —— 该接口风控宽松、且支持翻页，"
            "每次点击都能拿到新的视频。\n\n"
            "也可指定 `source=partition` 抓某个分区排行榜，"
            "但排行榜接口风控最严（连续点容易被 -352 拦截），不建议频繁使用。\n\n"
            "抓完会自动清理统计缓存、重建 AI 检索索引。"
        ),
        tags=["spider"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["popular", "partition"],
                        "example": "popular",
                    },
                    "partition": {"type": "string", "example": "科技"},
                    "limit": {"type": "integer", "example": 40},
                    "pages": {"type": "integer", "example": 3},
                },
            }
        },
    )
    def post(self, request):
        """POST /api/spider/crawl/"""
        source = str(request.data.get("source") or "popular").strip().lower()
        if source not in ("popular", "partition"):
            source = "popular"

        partition = _pick_partition(request.data.get("partition"))
        limit = _clamp_int(request.data.get("limit"), 40, 1, 200)
        pages = _clamp_int(request.data.get("pages"), _POPULAR_MAX_ATTEMPTS, 1, _POPULAR_MAX_ATTEMPTS)

        spider = BiliBiliSpider(interval=getattr(settings, "SPIDER_REQUEST_INTERVAL", 2.0))
        started = time.monotonic()
        next_page = None
        pages_read = 0

        try:
            if source == "partition":
                stats = spider.run_partition(partition, limit=limit)
            else:
                result = _crawl_popular(spider, limit=limit, max_pages=pages)
                stats = result["stats"]
                next_page = result["next_page"]
                pages_read = result["pages_read"]
        except RateLimitedError as exc:
            logger.warning("抓取被风控限流：%s", exc)
            return error(
                "被 B站 风控限流：请等待 2-10 分钟后重试（不要连续点击）",
                code=BusinessCode.CRAWL_RATE_LIMITED,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("抓取失败：%s", exc)
            return error(
                f"抓取失败：{type(exc).__name__}",
                code=BusinessCode.CRAWL_FAILED,
            )
        finally:
            spider.close()

        elapsed = round(time.monotonic() - started, 2)

        # 数据变了 -> 统计缓存必须失效，否则看板还是旧数字
        cleared = clear_analytics_cache()
        index_count = _rebuild_index_if_needed()

        from apps.videos.models import Video

        # 给一句能直接看懂的话：新增了就报喜，没新增就解释为什么
        if stats.created > 0:
            message = f"抓取完成：新增 {stats.created} 条视频，更新 {stats.updated} 条"
        elif stats.updated > 0:
            message = (
                f"本次没有新视频（热门榜这几页都已收录），已为你翻到第 {next_page} 页，"
                "再点一次即可抓到后面更新的内容"
            )
        else:
            message = "本次没有取到新数据，稍后再试"

        return success(
            {
                "source": source,
                "partition": partition if source == "partition" else "",
                "fetched": stats.fetched,
                "created": stats.created,
                "updated": stats.updated,
                "failed": stats.failed,
                # 请求数累加在 spider.stats 上（run_* 返回的是局部统计）
                "requests": spider.stats.requests,
                "elapsed": elapsed,
                "cleared_cache": cleared,
                "video_total": Video.objects.count(),
                "index_count": index_count,
                "pages_read": pages_read,
                "next_page": next_page,
            },
            message=message,
        )


# ===========================================================================
# ② 补全细节（后台线程）
# ===========================================================================
def _run_enrich(followers_limit: int, danmaku_limit: int) -> None:
    """后台线程主体：补 UP主 粉丝数，再抓弹幕。

    【为什么中途要 close 连接】
        Django 的数据库连接是**按线程**绑定的。线程结束后若不复用连接，
        连接会一直挂到进程退出。这里显式 close，避免长时间运行时连接泄漏。
    """
    from apps.videos.models import Danmaku, UpUser, Video

    spider = BiliBiliSpider(interval=getattr(settings, "SPIDER_REQUEST_INTERVAL", 2.0))
    try:
        # ---- 阶段一：UP主 粉丝数 ----
        pending_followers = UpUser.objects.filter(follower_count=0).count()
        _set_state(
            stage="followers",
            message=f"正在补全 UP主 粉丝数（待补 {pending_followers} 位）…",
            total=pending_followers,
            done=0,
        )

        if pending_followers:
            # 【为什么传进度回调】
            #   补 35 位 UP主 大约要 70 秒，期间若状态一直是"0/35"，
            #   使用者会以为卡死了。回调让进度条能一格一格走。
            def _on_follower_progress(index: int, total: int, stats) -> None:
                _set_state(
                    total=total,
                    done=index,
                    message=f"正在补全 UP主 粉丝数（{index}/{total}）…",
                )

            stats = spider.run_upuser_followers(
                skip_filled=True,
                limit=followers_limit or 0,
                on_progress=_on_follower_progress,
            )
            _set_state(
                followers=stats.updated,
                message=f"UP主 粉丝数完成：更新 {stats.updated} 位",
            )

        # ---- 阶段二：弹幕 ----
        has_danmaku = set(Danmaku.objects.values_list("video_id", flat=True).distinct())
        pending_bvids = list(
            Video.objects.exclude(id__in=has_danmaku)
            .filter(is_demo=False)
            .order_by("-danmaku_count")
            .values_list("bvid", flat=True)
        )
        if danmaku_limit:
            pending_bvids = pending_bvids[:danmaku_limit]

        _set_state(
            stage="danmaku",
            message=f"正在抓取弹幕（待抓 {len(pending_bvids)} 个视频）…",
            total=len(pending_bvids),
            done=0,
        )

        total_new = 0
        empty_streak = 0
        # 记录是否因风控提前停止，收尾时如实告知，而不是报"全部完成"
        stopped_by_limit = False

        for index, bvid in enumerate(pending_bvids, start=1):
            video = Video.objects.filter(bvid=bvid).first()
            if video is None:
                continue

            before = Danmaku.objects.filter(video=video).count()
            try:
                stats = spider.run_danmaku(bvid, limit=50, video=video)
                total_new += stats.created
            except RateLimitedError:
                stopped_by_limit = True
                _set_state(message="弹幕抓取被风控限流，已停止（可稍后再试）")
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 弹幕抓取失败：%s", bvid, exc)

            done_now = Danmaku.objects.filter(video=video).count()

            # 【为什么要有"连续空手"保护】
            #   run_danmaku 内部捕获限流后只记日志、正常返回，
            #   调用方看不出"被拦了"。若照原样继续循环，就会对剩下的
            #   几百个视频各发一次失败请求 —— 既拿不到数据，又不断延长风控。
            #   实测过：389 个视频里连续几十次限流警告，却还在一路往下跑。
            #
            #   这里用"连续 3 个视频一条弹幕都没拿到"作为判定：
            #   正常情况下每个视频至少能拿到几十条，连续空手基本只能是限流。
            if done_now == before:
                empty_streak += 1
                if empty_streak >= 3:
                    stopped_by_limit = True
                    _set_state(
                        done=index,
                        danmaku=total_new,
                        message="弹幕接口被风控，已停止（已抓到的内容已保存，稍后可再点一次）",
                    )
                    break
            else:
                empty_streak = 0

            _set_state(done=index, danmaku=total_new)

        # ---- 收尾 ----
        clear_analytics_cache()
        _rebuild_index_if_needed()

        followers_done = _get_state()["followers"]
        if stopped_by_limit:
            # 被风控提前停止：如实说明，不要伪装成"全部完成"
            _set_state(
                running=False,
                stage="done",
                message=(
                    f"已提前停止：弹幕接口被风控。本次补全粉丝数 {followers_done} 位、"
                    f"新增弹幕 {total_new} 条（已保存），稍后可再点一次继续"
                ),
            )
        else:
            _set_state(
                running=False,
                stage="done",
                message=f"补全完成：粉丝数 {followers_done} 位，新增弹幕 {total_new} 条",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("后台补全任务失败：%s", exc)
        _set_state(running=False, stage="error", error=str(exc), message=f"补全失败：{exc}")
    finally:
        spider.close()
        # 线程自己的数据库连接要主动回收
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass


class EnrichView(APIView):
    """启动 / 查询后台补全任务。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="启动补全任务",
        description="后台线程补全 UP主 粉丝数与弹幕，立即返回；用 GET 查询进度。",
        tags=["spider"],
    )
    def post(self, request):
        """POST /api/spider/enrich/"""
        if _get_state()["running"]:
            return error("补全任务正在进行中，请稍候", code=BusinessCode.BAD_REQUEST)

        followers_limit = _clamp_int(request.data.get("followers_limit"), 40, 0, 200)
        danmaku_limit = _clamp_int(request.data.get("danmaku_limit"), 20, 0, 100)

        _set_state(
            running=True,
            stage="starting",
            message="正在启动补全任务…",
            total=0,
            done=0,
            followers=0,
            danmaku=0,
            error="",
        )

        thread = threading.Thread(
            target=_run_enrich,
            args=(followers_limit, danmaku_limit),
            name="biliinsight-enrich",
            daemon=True,
        )
        thread.start()

        return success({"started": True}, message="补全任务已在后台启动")

    @extend_schema(
        summary="查询补全进度",
        description="返回后台补全任务的当前阶段、进度与累计结果。",
        tags=["spider"],
    )
    def get(self, request):
        """GET /api/spider/enrich/"""
        return success(_get_state())


# ===========================================================================
# ③ 可选项：分区列表（给下拉框用）
# ===========================================================================
class CrawlOptionsView(APIView):
    """返回可用于抓取的分区列表。"""

    permission_classes = [AllowAny]

    @extend_schema(summary="可抓取的分区列表", tags=["spider"])
    def get(self, request):
        """GET /api/spider/options/"""
        return success(
            {
                "partitions": [
                    {"name": name, "tid": tid} for name, tid in PARTITIONS.items()
                ],
                "default_partition": DEFAULT_PARTITIONS[0],
                # 界面「条数」的默认值 = 本次希望新增多少条
                # （热门模式按这个数停手，不是"读多少页"）
                "default_limit": 5,
            }
        )

# -*- coding: utf-8 -*-
"""
analytics 应用 —— 数据统计服务层。

【为什么统计逻辑要独立成 services.py】
  1. **可复用**：视图、管理命令、Celery 任务都能调用同一套统计函数；
  2. **可测试**：绕开 HTTP 层直接测统计结果是否正确；
  3. **便于优化**：缓存、SQL 优化都集中在这里，视图保持简洁。

【缓存策略（对应 README 的性能优化加分项）】
统计接口的数据来自对视频/弹幕表的实时聚合。本项目数据量为万级，
实时聚合可接受，但同一看板会被反复刷新，因此对结果做短时缓存：
    总览 / 趋势 / 占比    -> 5 分钟
    排行榜 / 词云 / 情感  -> 10 分钟

缓存键统一带 biliinsight: 前缀（由 settings 的 KEY_PREFIX 自动添加），
避免与其他项目的键冲突。

【为什么不用汇总表】
课程项目数据量级下，实时聚合 + 缓存足够。引入汇总表会带来
"数据不同步"的维护成本（爬虫更新后要记得刷新汇总表）。
若将来数据涨到百万级，再在 services 层内部改为读汇总表即可，
视图与接口契约完全不用改——这也是分层设计的价值。
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.videos.models import Danmaku, Partition, UpUser, Video

logger = logging.getLogger(__name__)

# ===========================================================================
# 缓存时长（秒）—— 与 settings 中的配置项保持一致
# ===========================================================================
TTL_OVERVIEW = 300    # 总览：5 分钟
TTL_TREND = 300       # 趋势：5 分钟
TTL_RATIO = 300       # 占比：5 分钟
TTL_RANKING = 600     # 排行榜：10 分钟
TTL_WORDCLOUD = 600   # 词云：10 分钟
TTL_SENTIMENT = 600   # 情感：10 分钟


def _cached(key: str, ttl: int, producer):
    """通用的"读缓存 -> 未命中则计算并写回"辅助函数。

    参数:
        key:      缓存键（会自动加 settings.KEY_PREFIX）
        ttl:      过期秒数
        producer: 无参函数，未命中时调用以计算真实值

    返回:
        producer() 的返回值，或缓存中的副本

    【为什么不直接对 dict 做缓存】
    Django 的缓存后端（Redis）内部用 pickle 序列化，dict/list 都能直接存。
    这里无需额外处理，直接返回即可。
    """
    value = cache.get(key)
    if value is not None:
        logger.debug("缓存命中：%s", key)
        return value

    logger.debug("缓存未命中，计算：%s", key)
    value = producer()
    try:
        cache.set(key, value, ttl)
    except Exception as exc:
        # 缓存写入失败不应影响接口可用性（例如 Redis 临时抖动）
        logger.warning("缓存写入失败 %s：%s", key, exc)
    return value


def clear_analytics_cache():
    """清空本应用产生的所有统计缓存。

    【调用时机 —— 数据一变就必须清】
    分析接口的缓存 TTL 是 300-600 秒。如果写完数据不清缓存，
    看板会继续显示旧数字最长 10 分钟。实测表现很具迷惑性：

        视频列表页 /api/videos/     -> 无缓存，立刻变成新数据 ✅
        数据总览 /api/analytics/*   -> 有缓存，仍是旧值       ❌

    于是看起来像"只同步了一半数据"，实际是缓存没有失效。
    这个现象在本项目真实发生过（抓完 97 条真实数据后，
    总览与 UP主 排行仍显示抓取前的 200 条统计）。

    因此以下入口在写完数据后都会调用本函数：

        · apps/spider/tasks.py            -> _finish_task()，覆盖全部 5 个 Celery 任务
        · manage.py crawl                 -> 抓取结束、有新增或更新时
        · manage.py seed_demo             -> 生成演示数据后
        · manage.py mark_data_source      -> 修改 is_demo 标记后
        · apps/ai/views.py                -> 重建向量索引后

    【实现说明】
    Django 内置的 RedisCache 没有 delete_pattern()，
    因此改用 apps.common.cache_utils 中基于 SCAN 的实现。
    早期版本这里写了 `if hasattr(cache, "delete_pattern")` 判断，
    但该判断永远为假 —— 清理静默失效（删了 0 个键）却不报错。
    这个问题是通过"清理后缓存依然命中"的测试发现的。

    返回:
        删除的键数量
    """
    from apps.common.cache_utils import delete_pattern

    patterns = [
        "analytics:*",
        "wordcloud:*",
        "sentiment:*",
    ]
    deleted = 0
    for pattern in patterns:
        deleted += delete_pattern(pattern)

    logger.info("统计缓存已清理，共删除 %d 个键", deleted)
    return deleted


# ===========================================================================
# 1. 总览统计
# ===========================================================================
def get_overview() -> dict:
    """总览卡片数据：视频数、播放总量、UP主数等。

    返回:
        {
          "video_count": 297,
          "real_videos": 97,
          "demo_videos": 200,
          "real_ratio": 0.3266,
          "upuser_count": 137,
          "partition_count": 10,
          "danmaku_count": 3000,
          "total_view": 98667090,
          "total_like": ...,
          "avg_view": 332212.4,
          "avg_interaction_rate": 0.0758,
          "latest_pubdate": "2026-09-27T..."
        }

    【为什么总览要带真实/模拟的准确条数】
        前端原本用"榜单前 10 条"里的 is_demo 比例来估算数据来源，
        这是不准确的：抓完真实数据后，播放量最高的前 10 条往往全是真实的，
        于是看板顶部那条"混合数据"提示会**完全消失**，
        而库里其实仍有 200 条模拟数据 —— 用户会误以为数据已经全部同步。

        总览直接给出全库准确计数，前端据此判断就不会出现这种误导。
    """

    def _compute():
        video_agg = Video.objects.aggregate(
            total_view=Sum("view_count"),
            total_like=Sum("like_count"),
            total_coin=Sum("coin_count"),
            total_favorite=Sum("favorite_count"),
            total_danmaku=Sum("danmaku_count"),
            avg_view=Avg("view_count"),
            avg_interaction=Avg("interaction_rate"),
            latest=Max("pubdate"),
        )

        # 真实 / 模拟计数：两次轻量 count 查询（走 is_demo 索引），
        # 比把全表拉出来在 Python 里统计便宜得多。
        video_count = Video.objects.count()
        demo_videos = Video.objects.filter(is_demo=True).count()
        real_videos = video_count - demo_videos

        return {
            "video_count": video_count,
            # ---- 数据来源构成（供前端准确展示"混合数据"状态）----
            "real_videos": real_videos,
            "demo_videos": demo_videos,
            "real_ratio": (
                round(real_videos / video_count, 4) if video_count else 0.0
            ),
            "upuser_count": UpUser.objects.count(),
            "partition_count": Partition.objects.count(),
            # 已抓取入库的弹幕条数（区别于视频上标记的 danmaku_count 总数）
            "danmaku_count": Danmaku.objects.count(),
            "total_view": video_agg["total_view"] or 0,
            "total_like": video_agg["total_like"] or 0,
            "total_coin": video_agg["total_coin"] or 0,
            "total_favorite": video_agg["total_favorite"] or 0,
            "total_danmaku": video_agg["total_danmaku"] or 0,
            "avg_view": round(video_agg["avg_view"] or 0, 1),
            "avg_interaction_rate": round(video_agg["avg_interaction"] or 0, 4),
            "latest_pubdate": (
                video_agg["latest"].isoformat() if video_agg["latest"] else None
            ),
        }

    return _cached("analytics:overview", TTL_OVERVIEW, _compute)


# ===========================================================================
# 2. 播放量趋势
# ===========================================================================
def get_trend(days: int = 30, partition: str = "") -> dict:
    """按天统计发布视频数与播放量，用于折线图。

    参数:
        days:      统计最近多少天
        partition: 可选，按分区名筛选

    返回:
        {
          "days": 30,
          "partition": "",
          "points": [
            {"date": "2026-08-20", "video_count": 5, "view_sum": 12345, "avg_view": 2469.0},
            ...
          ]
        }

    【实现说明】
    用 TruncDate 按天截断 pubdate，再分组聚合。
    注意：没有数据的日期不会出现在结果里（SQL GROUP BY 的特性），
    前端画折线图时需要自己补零——这一点已在返回中说明，
    前端可用 points 的日期范围生成完整轴。
    """
    days = max(1, min(int(days), 365))   # 限制范围，防止恶意传参

    def _compute():
        since = timezone.now() - timedelta(days=days)

        qs = Video.objects.filter(pubdate__gte=since)
        if partition:
            qs = qs.filter(partition__name=partition)

        rows = (
            qs.annotate(day=TruncDate("pubdate"))
            .values("day")
            .annotate(
                video_count=Count("id"),
                view_sum=Sum("view_count"),
                like_sum=Sum("like_count"),
                avg_view=Avg("view_count"),
            )
            .order_by("day")
        )

        points = [
            {
                "date": row["day"].isoformat() if row["day"] else None,
                "video_count": row["video_count"],
                "view_sum": row["view_sum"] or 0,
                "like_sum": row["like_sum"] or 0,
                "avg_view": round(row["avg_view"] or 0, 1),
            }
            for row in rows
            if row["day"] is not None
        ]

        return {"days": days, "partition": partition, "points": points}

    cache_key = f"analytics:trend:{days}:{partition or 'all'}"
    return _cached(cache_key, TTL_TREND, _compute)


# ===========================================================================
# 3. 分区占比
# ===========================================================================
def get_partition_ratio() -> dict:
    """各分区的视频数、播放量与占比，用于饼图。

    返回:
        {
          "total_videos": 200,
          "total_views": 2592625,
          "items": [
            {"name": "科技", "bili_tid": 188, "color": "#5470C6",
             "video_count": 46, "view_sum": 123456, "video_pct": 23.0, "view_pct": 12.3},
            ...
          ]
        }

    说明：同时给出"视频数占比"与"播放量占比"两个维度——
    按数量看是均衡的，按播放量看往往头部集中，两者对比更能说明问题。
    """

    def _compute():
        rows = (
            Partition.objects.annotate(
                video_count=Count("videos"),
                view_sum=Sum("videos__view_count"),
                like_sum=Sum("videos__like_count"),
                avg_view=Avg("videos__view_count"),
            )
            .filter(video_count__gt=0)
            .order_by("-view_sum")
        )

        total_videos = sum(r.video_count for r in rows) or 1
        total_views = sum(r.view_sum or 0 for r in rows) or 1

        items = [
            {
                "name": r.name,
                "bili_tid": r.bili_tid,
                "color": r.color or "",
                "video_count": r.video_count,
                "view_sum": r.view_sum or 0,
                "like_sum": r.like_sum or 0,
                "avg_view": round(r.avg_view or 0, 1),
                "video_pct": round(r.video_count / total_videos * 100, 2),
                "view_pct": round((r.view_sum or 0) / total_views * 100, 2),
            }
            for r in rows
        ]

        return {
            "total_videos": total_videos,
            "total_views": total_views,
            "items": items,
        }

    return _cached("analytics:partition_ratio", TTL_RATIO, _compute)


# ===========================================================================
# 4. UP主排行榜
# ===========================================================================
def get_top_upusers(limit: int = 10, order_by: str = "view_sum") -> dict:
    """UP主排行榜，用于柱状图。

    参数:
        limit:    返回条数（1-100）
        order_by: 排序依据，可选：
                  view_sum（总播放，默认）
                  video_count（作品数）
                  avg_view（篇均播放）
                  like_sum（总点赞）
                  follower_count（粉丝数）

    返回:
        {"order_by": "view_sum", "items": [...]}
    """
    limit = max(1, min(int(limit), 100))

    # 白名单校验：绝不能让前端传的字符串直接进入 order_by，否则存在注入风险
    allowed = {
        "view_sum", "video_count", "avg_view", "like_sum", "follower_count",
    }
    if order_by not in allowed:
        order_by = "view_sum"

    def _compute():
        rows = (
            UpUser.objects.annotate(
                video_count_db=Count("videos"),
                view_sum=Sum("videos__view_count"),
                like_sum=Sum("videos__like_count"),
                avg_view=Avg("videos__view_count"),
                max_view=Max("videos__view_count"),
            )
            .filter(video_count_db__gt=0)
            .order_by(f"-{order_by if order_by != 'video_count' else 'video_count_db'}")
            .values(
                "mid", "name", "avatar", "follower_count",
                "video_count_db", "view_sum", "like_sum", "avg_view", "max_view",
            )[:limit]
        )

        items = [
            {
                "mid": r["mid"],
                "name": r["name"],
                "avatar": r["avatar"],
                "follower_count": r["follower_count"],
                "video_count": r["video_count_db"],
                "view_sum": r["view_sum"] or 0,
                "like_sum": r["like_sum"] or 0,
                "avg_view": round(r["avg_view"] or 0, 1),
                "max_view": r["max_view"] or 0,
            }
            for r in rows
        ]

        return {"order_by": order_by, "items": items}

    cache_key = f"analytics:top_upusers:{limit}:{order_by}"
    return _cached(cache_key, TTL_RANKING, _compute)


# ===========================================================================
# 5. 视频排行榜
# ===========================================================================
def get_top_videos(limit: int = 10, order_by: str = "view_count",
                   partition: str = "") -> dict:
    """视频排行榜，用于榜单展示。

    参数:
        limit:     返回条数
        order_by:  view_count（播放，默认）/ interaction_rate（互动率）/
                   like_count / coin_count / favorite_count / danmaku_count
        partition: 可选分区筛选

    返回:
        {"order_by": ..., "partition": ..., "items": [...]}
    """
    limit = max(1, min(int(limit), 100))

    allowed = {
        "view_count", "interaction_rate", "like_count",
        "coin_count", "favorite_count", "danmaku_count", "reply_count",
    }
    if order_by not in allowed:
        order_by = "view_count"

    def _compute():
        # select_related 预加载外键，避免列表页 N+1 查询
        # （这是 README"代码优化"章节的落点之一）
        qs = Video.objects.select_related("partition", "upuser")
        if partition:
            qs = qs.filter(partition__name=partition)

        rows = qs.order_by(f"-{order_by}")[:limit]

        items = [
            {
                "bvid": v.bvid,
                "title": v.title,
                "cover_url": v.cover_url,
                "duration": v.duration,
                "duration_display": v.duration_display,
                "pubdate": v.pubdate.isoformat() if v.pubdate else None,
                "partition": v.partition.name if v.partition else None,
                "up_name": v.upuser.name if v.upuser else None,
                "up_mid": v.upuser.mid if v.upuser else None,
                "view_count": v.view_count,
                "like_count": v.like_count,
                "coin_count": v.coin_count,
                "favorite_count": v.favorite_count,
                "danmaku_count": v.danmaku_count,
                "interaction_rate": v.interaction_rate,
                # 数据来源：前端据此打「模拟数据」标签并隐藏跳转入口
                "is_demo": v.is_demo,
                "data_source": "demo" if v.is_demo else "real",
                "source_url": v.source_url,
            }
            for v in rows
        ]

        return {"order_by": order_by, "partition": partition, "items": items}

    cache_key = f"analytics:top_videos:{limit}:{order_by}:{partition or 'all'}"
    return _cached(cache_key, TTL_RANKING, _compute)


# ===========================================================================
# 6. 关键词统计（词云数据源）
# ===========================================================================
# 中文停用词表：这些词在所有视频标题里都高频出现，但对分析没有信息量。
# 不做过滤的话，词云会被"的""了""我"之类占满，看不出内容主题。
STOPWORDS = {
    # 通用虚词
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "那", "什么", "怎么", "为什么",
    "可以", "这个", "那个", "还", "被", "把", "让", "给", "对", "从",
    "但是", "因为", "所以", "如果", "虽然", "然后", "而且", "以及",
    # 单字（信息量低）
    "啊", "吧", "呢", "吗", "呀", "哦", "嗯", "哈",
    # 视频标题中的格式性词
    "期", "第", "集", "篇", "版", "up", "UP", "up主", "视频", "系列",
    # 弹幕常见无意义内容
    "哈哈", "哈哈哈", "哈哈哈哈", "233", "666", "前排", "打卡", "来了",
    "沙发", "第一", "签到", "路过", "看看", "嗯嗯", "原来如此",
}


def get_wordcloud(limit: int = 100, source: str = "danmaku",
                  bvid: str = "", min_length: int = 2) -> dict:
    """词频统计，用于渲染词云。

    参数:
        limit:      返回的高频词数量
        source:     统计来源：danmaku（弹幕，默认）/ title（视频标题）
        bvid:       可选，只统计某个视频的弹幕
        min_length: 词的最小长度，默认 2（过滤单字噪声）

    返回:
        {
          "source": "danmaku",
          "total_words": 12500,       # 参与统计的词总数
          "unique_words": 1800,       # 去重后的词数
          "items": [{"name": "太强了", "value": 42, "weight": 100.0}, ...]
        }

    【为什么用 jieba 而不是按空格切分】
    中文没有词间空格，按字符切会得到大量单字，按整句切又得不到词。
    jieba 是中文分词的事实标准，且纯 Python 无编译依赖。

    【权重 weight 的含义】
    把最高频词的词频归一化为 100，其余按比例缩放。
    前端可直接用 weight 决定字号（ECharts 词云 / 自定义渲染均适用）。
    """
    limit = max(1, min(int(limit), 300))
    min_length = max(1, min(int(min_length), 10))

    if source not in ("danmaku", "title"):
        source = "danmaku"

    def _compute():
        # 延迟导入 jieba：它首次导入会加载词典（约 1-2 秒），
        # 放在函数内可避免拖慢 Django 启动与不相关的接口。
        import jieba

        if source == "title":
            qs = Video.objects
            if bvid:
                qs = qs.filter(bvid=bvid)
            texts = list(qs.values_list("title", flat=True))
            # 标题里还包含标签信息，一并纳入统计
            texts += [t for t in Video.objects.values_list("tags", flat=True) if t]
        else:
            qs = Danmaku.objects
            if bvid:
                qs = qs.filter(video__bvid=bvid)
            texts = list(qs.values_list("content", flat=True))

        if not texts:
            return {
                "source": source, "bvid": bvid,
                "total_words": 0, "unique_words": 0, "items": [],
            }

        counter: dict[str, int] = defaultdict(int)
        total = 0

        for text in texts:
            if not text:
                continue
            # cut 返回生成器；这里用精确模式（默认），比全模式更贴合语义
            for word in jieba.cut(text):
                word = word.strip()
                # 过滤：长度不足、纯符号数字、停用词
                if len(word) < min_length:
                    continue
                if word in STOPWORDS:
                    continue
                if not _has_meaning(word):
                    continue
                counter[word] += 1
                total += 1

        # 取词频最高的 limit 个
        top = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        max_count = top[0][1] if top else 1

        items = [
            {
                "name": word,
                "value": count,
                # 归一化到 0-100，方便前端直接映射字号
                "weight": round(count / max_count * 100, 2),
            }
            for word, count in top
        ]

        return {
            "source": source,
            "bvid": bvid,
            "total_words": total,
            "unique_words": len(counter),
            "items": items,
        }

    cache_key = f"wordcloud:{source}:{bvid or 'all'}:{limit}:{min_length}"
    return _cached(cache_key, TTL_WORDCLOUD, _compute)


def _has_meaning(word: str) -> bool:
    """判断一个词是否"有实义"。

    过滤掉纯标点、纯数字、纯空白。
    例："！！!" "123" "  " 都是噪声，不应进入词云。

    参数:
        word: 待判断的词

    返回:
        True 表示保留，False 表示过滤掉
    """
    if not word:
        return False
    # 至少包含一个中日韩文字或英文字母
    for ch in word:
        if ch.isalpha() or "\u4e00" <= ch <= "\u9fff":
            return True
    return False


# ===========================================================================
# 7. 情感分析统计
# ===========================================================================
def get_sentiment_stats(bvid: str = "", segment_count: int = 20) -> dict:
    """弹幕情感分布与情绪波动序列。

    参数:
        bvid:          可选，指定视频；不传则统计全部
        segment_count: 波动图的时间分段数，默认 20 段

    返回:
        {
          "bvid": "BV...",
          "total": 3000,
          "analyzed": 3000,
          "distribution": [
            {"label": "positive", "name": "正向", "count": 1764, "pct": 58.8},
            ...
          ],
          "emotion_tags": [{"name": "高燃", "value": 320}, ...],
          "curve": [                      # 情绪波动序列（按视频播放进度分段）
            {"segment": 1, "label": "0-5%", "avg_score": 0.72, "count": 150},
            ...
          ],
          "score_histogram": [            # 分值直方图（10 个区间）
            {"range": "0.0-0.1", "count": 30}, ...
          ]
        }
    """

    def _compute():
        qs = Danmaku.objects.all()
        if bvid:
            qs = qs.filter(video__bvid=bvid)

        total = qs.count()
        analyzed_qs = qs.exclude(sentiment_label="")
        analyzed = analyzed_qs.count()

        if total == 0:
            return {
                "bvid": bvid, "total": 0, "analyzed": 0,
                "distribution": [], "emotion_tags": [],
                "curve": [], "score_histogram": [],
            }

        # ---- 情感分布 ----
        label_names = {"positive": "正向", "neutral": "中性", "negative": "负向"}
        dist_rows = (
            analyzed_qs.values("sentiment_label")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        distribution = [
            {
                "label": row["sentiment_label"],
                "name": label_names.get(row["sentiment_label"], row["sentiment_label"]),
                "count": row["n"],
                # 占比以"已分析条数"为分母，避免未分析的弹幕拉低比例
                "pct": round(row["n"] / analyzed * 100, 2) if analyzed else 0.0,
            }
            for row in dist_rows
        ]

        # ---- 情绪标签统计 ----
        # emotion_tags 是逗号分隔的字符串，需要拆开统计
        tag_counter: dict[str, int] = defaultdict(int)
        for tags in analyzed_qs.exclude(emotion_tags="").values_list("emotion_tags", flat=True):
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    tag_counter[tag] += 1
        emotion_tags = [
            {"name": name, "value": count}
            for name, count in sorted(tag_counter.items(), key=lambda kv: kv[1], reverse=True)
        ]

        # ---- 情绪波动曲线 ----
        # 思路：把视频时长按百分比分成若干段，统计每段的平均情感分值。
        # 因为不同视频时长差异很大，用"播放进度百分比"而非绝对秒数，
        # 才能把多个视频的弹幕放在同一张图上比较。
        curve = _build_sentiment_curve(qs, segment_count)

        # ---- 分值直方图 ----
        histogram = _build_score_histogram(analyzed_qs)

        return {
            "bvid": bvid,
            "total": total,
            "analyzed": analyzed,
            "distribution": distribution,
            "emotion_tags": emotion_tags,
            "curve": curve,
            "score_histogram": histogram,
        }

    cache_key = f"sentiment:{bvid or 'all'}:{segment_count}"
    return _cached(cache_key, TTL_SENTIMENT, _compute)


def _build_sentiment_curve(qs, segment_count: int) -> list:
    """构造情绪波动序列。

    参数:
        qs:            已筛选的弹幕 QuerySet
        segment_count: 分段数量

    返回:
        [{"segment": 1, "label": "0-5%", "avg_score": 0.72, "count": 150}, ...]

    【实现说明：为什么在 Python 里算而不是用 SQL】
    需要按"弹幕时间点 / 视频时长"的比例分段，而 video.duration 在关联表里，
    纯 SQL 需要 JOIN + 除法 + 分桶，可读性差且不便跨数据库。
    本项目弹幕量为千级，取回后在 Python 中计算完全可接受，
    代码清晰度更重要。（若数据涨到百万级，再改写成 SQL 聚合。）
    """
    # 只取计算所需字段，减少内存占用
    rows = (
        qs.exclude(sentiment_score__isnull=True)
        .values_list("video_time", "sentiment_score", "video__duration")
    )

    buckets: dict[int, list] = defaultdict(list)
    for video_time, score, duration in rows:
        # 时长为 0 或缺失时无法计算进度比例，跳过
        if not duration or duration <= 0:
            continue
        ratio = min(max(video_time / duration, 0.0), 1.0)   # 夹到 [0,1]
        idx = min(int(ratio * segment_count), segment_count - 1)
        buckets[idx].append(score)

    curve = []
    step = 100.0 / segment_count
    for i in range(segment_count):
        scores = buckets.get(i, [])
        curve.append(
            {
                "segment": i + 1,
                "label": f"{i * step:.0f}-{(i + 1) * step:.0f}%",
                "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
                "count": len(scores),
            }
        )
    return curve


def _build_score_histogram(analyzed_qs) -> list:
    """构造情感分值直方图（10 个等宽区间）。

    参数:
        analyzed_qs: 已分析的弹幕 QuerySet

    返回:
        [{"range": "0.0-0.1", "count": 30}, ...]
    """
    bins = [0] * 10
    for score in analyzed_qs.values_list("sentiment_score", flat=True):
        if score is None:
            continue
        # score 理论范围 [0,1]，做个保护性夹取
        idx = min(int(max(0.0, min(score, 1.0)) * 10), 9)
        bins[idx] += 1

    return [
        {"range": f"{i / 10:.1f}-{(i + 1) / 10:.1f}", "count": bins[i]}
        for i in range(10)
    ]


# ===========================================================================
# 8. 互动质量分析（附加接口）
# ===========================================================================
def get_interaction_analysis(limit: int = 10) -> dict:
    """互动质量分析：找出"高互动率"的优质视频与分区对比。

    【为什么单独做这个接口】
    单看播放量只能反映"流量"，而互动率（点赞+投币+收藏 / 播放）
    更能反映"内容质量"。创作者真正需要的是"什么样的内容互动率高"，
    这也是本项目回答"创作者选题难"痛点的核心数据。

    参数:
        limit: 每个榜单返回条数

    返回:
        {
          "top_interaction": [...],     # 互动率最高的视频
          "partition_interaction": [...],  # 各分区平均互动率
          "high_quality_threshold": 0.1,   # 高互动率阈值
          "high_quality_count": 23,        # 超过阈值的视频数
        }
    """
    limit = max(1, min(int(limit), 50))

    def _compute():
        # 只统计有一定播放量的视频，避免"播放 5 次点赞 1 次"造成虚高互动率
        base = Video.objects.select_related("partition", "upuser").filter(
            view_count__gte=1000
        )

        top = [
            {
                "bvid": v.bvid,
                "title": v.title,
                "partition": v.partition.name if v.partition else None,
                "up_name": v.upuser.name if v.upuser else None,
                "view_count": v.view_count,
                "interaction_rate": v.interaction_rate,
                "like_count": v.like_count,
                "coin_count": v.coin_count,
                "favorite_count": v.favorite_count,
                # 数据来源标记（同上）
                "is_demo": v.is_demo,
                "source_url": v.source_url,
            }
            for v in base.order_by("-interaction_rate")[:limit]
        ]

        partition_rows = (
            Partition.objects.annotate(
                avg_interaction=Avg("videos__interaction_rate"),
                avg_view=Avg("videos__view_count"),
                video_count=Count("videos"),
            )
            .filter(video_count__gt=0)
            .order_by("-avg_interaction")
        )
        partition_interaction = [
            {
                "name": r.name,
                "color": r.color or "",
                "video_count": r.video_count,
                "avg_interaction": round(r.avg_interaction or 0, 4),
                "avg_view": round(r.avg_view or 0, 1),
            }
            for r in partition_rows
        ]

        # 高互动率阈值：取互动率的 90 分位作为"高质量"分界
        threshold = 0.10
        return {
            "top_interaction": top,
            "partition_interaction": partition_interaction,
            "high_quality_threshold": threshold,
            "high_quality_count": base.filter(
                interaction_rate__gte=threshold
            ).count(),
        }

    cache_key = f"analytics:interaction:{limit}"
    return _cached(cache_key, TTL_RANKING, _compute)

# -*- coding: utf-8 -*-
"""
analytics 应用的视图层。

【职责边界】
视图只做三件事：
    1. 校验与解析查询参数
    2. 调用 services 层取数
    3. 用统一格式包装响应

统计逻辑全部在 services.py，视图保持"薄"，
这样同一份统计既能被接口调用，也能被管理命令或定时任务复用。

【为什么用 APIView 而不是 ViewSet】
这些接口都是只读的聚合查询，没有 CRUD 语义，
用 APIView 逐个声明路由比 ViewSet 更直观，
接口文档中的路径也更清晰。
"""

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.response import error, success

from . import services

logger = logging.getLogger(__name__)


def _int_param(request, name: str, default: int, min_value: int, max_value: int) -> int:
    """从查询参数中安全地取一个整数并夹到合法区间。

    参数:
        request:   DRF Request
        name:      参数名
        default:   缺省值
        min_value: 允许的最小值
        max_value: 允许的最大值

    返回:
        夹取后的整数。非法输入（如 ?days=abc）回退到 default，
        而不是抛 500 错误——前端传错参数不应导致服务端异常。
    """
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.debug("参数 %s=%r 非法，使用默认值 %s", name, raw, default)
        return default
    return max(min_value, min(value, max_value))


def _str_param(request, name: str, default: str = "") -> str:
    """取字符串参数并去除首尾空白。"""
    value = request.query_params.get(name)
    if value is None:
        return default
    return value.strip()


# ===========================================================================
# 1. 总览
# ===========================================================================
class OverviewView(APIView):
    """总览统计：视频数、播放总量、UP主数等核心指标。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="数据总览",
        description="返回视频数、UP主数、分区数、播放总量、平均互动率等总览指标。",
        tags=["analytics"],
    )
    def get(self, request):
        """GET /api/analytics/overview/"""
        return success(services.get_overview())


# ===========================================================================
# 2. 趋势
# ===========================================================================
class TrendView(APIView):
    """播放量趋势（按天聚合）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="播放量趋势",
        description="按天统计发布视频数与播放量，用于折线图。"
                    "注意：没有数据的日期不会出现在结果中，前端需自行补零。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("days", int, description="统计最近多少天，1-365，默认 30"),
            OpenApiParameter("partition", str, description="可选，按分区名筛选，如「科技」"),
        ],
    )
    def get(self, request):
        """GET /api/analytics/trend/?days=30&partition=科技"""
        days = _int_param(request, "days", default=30, min_value=1, max_value=365)
        partition = _str_param(request, "partition")

        # 分区名非法时给出明确提示，而不是静默返回空数据
        if partition:
            from apps.videos.models import Partition

            if not Partition.objects.filter(name=partition).exists():
                return error(f"分区不存在：{partition}", code=2001, http_status=404)

        return success(services.get_trend(days=days, partition=partition))


# ===========================================================================
# 3. 分区占比
# ===========================================================================
class PartitionRatioView(APIView):
    """分区占比（饼图数据）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="分区占比",
        description="各分区的视频数与播放量占比。同时给出数量占比与播放占比两个维度。",
        tags=["analytics"],
    )
    def get(self, request):
        """GET /api/analytics/partition-ratio/"""
        return success(services.get_partition_ratio())


# ===========================================================================
# 4. UP主排行
# ===========================================================================
class TopUpusersView(APIView):
    """UP主排行榜。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="UP主排行榜",
        description="按总播放/作品数/篇均播放/粉丝数等维度对 UP主 排名。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("limit", int, description="返回条数，1-100，默认 10"),
            OpenApiParameter(
                "order_by", str,
                description="排序依据：view_sum(默认) / video_count / avg_view / like_sum / follower_count",
            ),
        ],
    )
    def get(self, request):
        """GET /api/analytics/top-upusers/?limit=10&order_by=view_sum"""
        limit = _int_param(request, "limit", default=10, min_value=1, max_value=100)
        order_by = _str_param(request, "order_by", "view_sum")
        return success(services.get_top_upusers(limit=limit, order_by=order_by))


# ===========================================================================
# 5. 视频排行
# ===========================================================================
class TopVideosView(APIView):
    """视频排行榜。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="视频排行榜",
        description="按播放量/互动率/点赞等维度对视频排名，支持按分区筛选。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("limit", int, description="返回条数，1-100，默认 10"),
            OpenApiParameter(
                "order_by", str,
                description="view_count(默认) / interaction_rate / like_count / "
                            "coin_count / favorite_count / danmaku_count",
            ),
            OpenApiParameter("partition", str, description="可选，按分区名筛选"),
        ],
    )
    def get(self, request):
        """GET /api/analytics/top-videos/?limit=10&order_by=view_count"""
        limit = _int_param(request, "limit", default=10, min_value=1, max_value=100)
        order_by = _str_param(request, "order_by", "view_count")
        partition = _str_param(request, "partition")

        if partition:
            from apps.videos.models import Partition

            if not Partition.objects.filter(name=partition).exists():
                return error(f"分区不存在：{partition}", code=2001, http_status=404)

        return success(
            services.get_top_videos(limit=limit, order_by=order_by, partition=partition)
        )


# ===========================================================================
# 6. 词云
# ===========================================================================
class WordCloudView(APIView):
    """弹幕/标题词频统计（词云数据源）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="关键词词频（词云）",
        description="对弹幕内容或视频标题做中文分词与词频统计，"
                    "返回高频词及归一化权重，供前端渲染词云。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("source", str, description="统计来源：danmaku(默认) / title"),
            OpenApiParameter("bvid", str, description="可选，只统计某个视频的弹幕"),
            OpenApiParameter("limit", int, description="返回词数，1-300，默认 100"),
            OpenApiParameter("min_length", int, description="词最小长度，默认 2"),
        ],
    )
    def get(self, request):
        """GET /api/analytics/wordcloud/?source=danmaku&limit=100"""
        source = _str_param(request, "source", "danmaku")
        bvid = _str_param(request, "bvid")
        limit = _int_param(request, "limit", default=100, min_value=1, max_value=300)
        min_length = _int_param(request, "min_length", default=2, min_value=1, max_value=10)

        if source not in ("danmaku", "title"):
            return error("source 参数只能是 danmaku 或 title", code=1001)

        return success(
            services.get_wordcloud(
                limit=limit, source=source, bvid=bvid, min_length=min_length
            )
        )


# ===========================================================================
# 7. 情感分析
# ===========================================================================
class SentimentView(APIView):
    """弹幕情感分布与情绪波动。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="弹幕情感分析",
        description="返回情感分布（正向/中性/负向）、情绪标签统计、"
                    "按播放进度分段的情绪波动曲线，以及分值直方图。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("bvid", str, description="可选，只统计某个视频"),
            OpenApiParameter("segments", int, description="波动曲线分段数，2-100，默认 20"),
        ],
    )
    def get(self, request):
        """GET /api/analytics/sentiment/?bvid=BV...&segments=20"""
        bvid = _str_param(request, "bvid")
        segments = _int_param(request, "segments", default=20, min_value=2, max_value=100)
        return success(services.get_sentiment_stats(bvid=bvid, segment_count=segments))


# ===========================================================================
# 8. 互动质量分析
# ===========================================================================
class InteractionAnalysisView(APIView):
    """互动质量分析：高互动率视频与分区对比。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="互动质量分析",
        description="互动率（点赞+投币+收藏 / 播放）比播放量更能反映内容质量。"
                    "本接口返回互动率最高的视频与各分区的平均互动率。",
        tags=["analytics"],
        parameters=[
            OpenApiParameter("limit", int, description="每个榜单返回条数，1-50，默认 10"),
        ],
    )
    def get(self, request):
        """GET /api/analytics/interaction/?limit=10"""
        limit = _int_param(request, "limit", default=10, min_value=1, max_value=50)
        return success(services.get_interaction_analysis(limit=limit))

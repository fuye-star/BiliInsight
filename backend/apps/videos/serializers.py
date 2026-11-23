# -*- coding: utf-8 -*-
"""
videos 应用的序列化器。

【设计原则】
  1. **列表用轻量序列化器**：列表接口只需卡片展示所需字段，
     不返回长文本（简介、弹幕全文），减少传输体积。
  2. **详情用完整序列化器**：详情页需要全部字段。
  3. **外键扁平化**：把 partition / upuser 展开成 name、mid 等标量字段，
     前端不必再发请求取关联数据（也避免了 N+1 问题）。
"""

from rest_framework import serializers

from .models import Danmaku, Partition, UpUser, Video


class PartitionSerializer(serializers.ModelSerializer):
    """分区序列化器。"""

    video_count = serializers.IntegerField(read_only=True, help_text="该分区已收录视频数")

    class Meta:
        model = Partition
        fields = ["id", "name", "bili_tid", "color", "video_count"]


class UpUserSerializer(serializers.ModelSerializer):
    """UP主序列化器。"""

    class Meta:
        model = UpUser
        fields = [
            "id", "mid", "name", "avatar", "sign",
            "follower_count", "video_count",
        ]


class UpUserBriefSerializer(serializers.ModelSerializer):
    """UP主精简序列化器（嵌入视频列表时使用）。

    只保留卡片展示需要的字段，避免列表响应过大。
    """

    class Meta:
        model = UpUser
        fields = ["mid", "name", "avatar"]


class VideoListSerializer(serializers.ModelSerializer):
    """视频列表序列化器（轻量）。

    不包含 description（简介可能上千字），
    列表页用不到，返回它会显著增大响应体积。
    """

    # 用 source 把外键展开为标量，前端拿到的是扁平结构
    partition = serializers.CharField(source="partition.name", default=None, read_only=True)
    partition_color = serializers.CharField(source="partition.color", default="", read_only=True)
    up_name = serializers.CharField(source="upuser.name", default=None, read_only=True)
    up_mid = serializers.IntegerField(source="upuser.mid", default=None, read_only=True)
    up_avatar = serializers.CharField(source="upuser.avatar", default="", read_only=True)

    # 计算属性：把秒数格式化为 mm:ss
    duration_display = serializers.CharField(read_only=True)
    tag_list = serializers.ListField(child=serializers.CharField(), read_only=True)

    # ---- 数据来源相关 ----
    # 原站地址由后端统一计算，避免前端各处拼 URL 时写法不一致
    source_url = serializers.CharField(read_only=True)
    # 人类可读的来源标识，前端可直接用于展示
    data_source = serializers.SerializerMethodField(
        help_text="real（真实抓取）/ demo（模拟数据）"
    )

    class Meta:
        model = Video
        fields = [
            "id", "bvid", "aid", "title", "cover_url",
            "duration", "duration_display", "pubdate",
            "partition", "partition_color", "up_name", "up_mid", "up_avatar",
            "tags", "tag_list",
            "view_count", "like_count", "coin_count", "favorite_count",
            "share_count", "danmaku_count", "reply_count",
            "interaction_rate",
            # 数据来源（用于区分真实抓取与模拟数据）
            "is_demo", "data_source", "source_url",
        ]

    def get_data_source(self, obj) -> str:
        """返回数据来源标识。

        前端据此决定是否展示"跳转B站"入口——
        模拟数据的 bvid 是虚构的，跳过去只会 404，
        给用户一个点不通的链接比不给更糟。
        """
        return "demo" if obj.is_demo else "real"


class VideoDetailSerializer(VideoListSerializer):
    """视频详情序列化器（完整）。

    相比列表版本增加了 description、cid 相关字段与抓取到的弹幕条数。
    """

    # 该视频已抓取入库的弹幕条数（区别于接口返回的 danmaku_count 总数）
    local_danmaku_count = serializers.SerializerMethodField(help_text="已入库的弹幕条数")

    class Meta(VideoListSerializer.Meta):
        fields = VideoListSerializer.Meta.fields + [
            "description",
            "local_danmaku_count",
            "created_at",
            "updated_at",
        ]

    def get_local_danmaku_count(self, obj) -> int:
        """统计该视频本地已存的弹幕数量。

        说明：优先用 annotate 预加载的值（避免 N+1），
        若视图未 annotate 则退化为一次 COUNT 查询。
        """
        # 视图里用 annotate(local_danmaku_count=Count("danmakus")) 预加载
        precomputed = getattr(obj, "local_danmaku_count", None)
        if precomputed is not None:
            return precomputed
        return obj.danmakus.count()


class DanmakuSerializer(serializers.ModelSerializer):
    """弹幕序列化器。"""

    sentiment_label_display = serializers.CharField(
        source="get_sentiment_label_display", read_only=True
    )
    emotion_tag_list = serializers.SerializerMethodField()

    class Meta:
        model = Danmaku
        fields = [
            "id", "dmid", "content", "video_time", "send_time",
            "sentiment_score", "sentiment_label", "sentiment_label_display",
            "emotion_tags", "emotion_tag_list",
        ]

    def get_emotion_tag_list(self, obj) -> list:
        """把逗号分隔的情绪标签转成列表。"""
        if not obj.emotion_tags:
            return []
        return [t.strip() for t in obj.emotion_tags.split(",") if t.strip()]

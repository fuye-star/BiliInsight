# -*- coding: utf-8 -*-
"""
视频模块数据模型。

【表结构总览】
    videos_partition   分区（科技 / 数码 / 游戏 / 生活 / 知识 ...）
    videos_upuser      UP主（视频作者）
    videos_video       视频主表（核心业务表）
    videos_danmaku     弹幕（一条弹幕一行）

【设计要点】
1. **索引策略**：B站数据的查询模式集中在"按分区筛选 + 按播放量排序"
   和"按发布时间排序"，因此为 partition / pubdate / view_count / 互动数
   建立索引。这是 README 中"数据库优化"加分项的落点。
2. **bvid 唯一约束**：bvid 是 B站视频的唯一标识（如 BV1xx411c7mD），
   爬虫重复抓取时用 update_or_create(bvid=...) 即可实现幂等入库。
3. **计数字段用 BigIntegerField**：热门视频播放量可上亿，
   普通 IntegerField（上限约 21 亿）虽够但仍留足余量。
4. **弹幕情感字段**：预留 sentiment_score / sentiment_label，
   由 apps.ai 的情感分析模块回填，避免二次建表。
"""

from django.db import models

from apps.common.models import TimeStampedModel


class Partition(TimeStampedModel):
    """B站分区（一级分区）。

    例：科技、数码、游戏、生活、知识、影视、动画。
    """

    name = models.CharField(
        "分区名称",
        max_length=50,
        unique=True,
        help_text="如：科技、数码、游戏",
    )

    # B站分区的数字 ID（如科技=188），用于调用官方 API 时传参
    bili_tid = models.IntegerField(
        "B站分区ID",
        null=True,
        blank=True,
        db_index=True,
        help_text="B站官方的 tid 参数，用于接口请求",
    )

    # 用于前端展示的颜色（ECharts 饼图配色）
    color = models.CharField(
        "主题色",
        max_length=16,
        blank=True,
        default="",
        help_text="前端图表配色，如 #5470C6",
    )

    class Meta:
        db_table = "videos_partition"
        verbose_name = "分区"
        verbose_name_plural = "分区"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UpUser(TimeStampedModel):
    """UP主（视频作者）。

    视频与 UP主 是"多对一"关系：
    一个 UP主 可发布多个视频，用外键从 Video 指向本表。
    """

    mid = models.BigIntegerField(
        "B站用户ID",
        unique=True,
        db_index=True,
        help_text="B站的 mid，UP主的唯一标识",
    )

    name = models.CharField("昵称", max_length=100, db_index=True)

    avatar = models.URLField("头像地址", max_length=500, blank=True, default="")

    sign = models.CharField(
        "个性签名",
        max_length=500,
        blank=True,
        default="",
        help_text="UP主简介，可用于文本分析",
    )

    # 粉丝数：用于计算"粉丝播放比"，衡量视频相对热度
    follower_count = models.BigIntegerField("粉丝数", default=0)

    # 该 UP主 在本项目中已入库的视频数量（冗余字段，避免频繁 COUNT 查询）
    video_count = models.IntegerField("已收录视频数", default=0)

    class Meta:
        db_table = "videos_upuser"
        verbose_name = "UP主"
        verbose_name_plural = "UP主"
        ordering = ["-follower_count"]
        indexes = [
            # 排行榜按粉丝数排序时使用
            models.Index(fields=["-follower_count"], name="idx_upuser_follower"),
        ]

    def __str__(self):
        return f"{self.name}({self.mid})"


class Video(TimeStampedModel):
    """视频主表 —— 本系统的核心数据表。

    字段分为四类：
      1. 标识类：bvid / aid / title
      2. 关联类：partition / upuser
      3. 元信息：cover_url / duration / pubdate
      4. 互动数据：view / like / coin / favorite / share / danmaku / reply
    """

    # ---------------- 标识 ----------------
    bvid = models.CharField(
        "BV号",
        max_length=20,
        unique=True,
        db_index=True,
        help_text="B站视频唯一标识，如 BV1xx411c7mD，用于幂等入库",
    )

    aid = models.BigIntegerField(
        "AV号",
        null=True,
        blank=True,
        db_index=True,
        help_text="旧版数字 ID，部分接口仍会返回",
    )

    cid = models.BigIntegerField(
        "弹幕ID(cid)",
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "抓弹幕时作为 oid 参数使用。"
            "**排行榜接口就会返回 cid**，因此存下来可以为每个视频省掉一次"
            "「取视频详情」的请求 —— 抓 40 个视频的弹幕能少发 40 次请求，"
            "在风控严格的场景下这是很可观的节省。"
        ),
    )

    title = models.CharField("标题", max_length=300, db_index=True)

    description = models.TextField(
        "简介",
        blank=True,
        default="",
        help_text="视频简介，用于语义检索与 RAG 向量化",
    )

    # ---------------- 关联 ----------------
    partition = models.ForeignKey(
        Partition,
        on_delete=models.SET_NULL,   # 分区删除时保留视频，避免数据丢失
        null=True,
        blank=True,
        related_name="videos",
        verbose_name="所属分区",
        db_index=True,
    )

    upuser = models.ForeignKey(
        UpUser,
        on_delete=models.CASCADE,     # UP主删除时其视频一并删除（外键必需）
        null=True,
        blank=True,
        related_name="videos",
        verbose_name="UP主",
        db_index=True,
    )

    # ---------------- 元信息 ----------------
    cover_url = models.URLField("封面地址", max_length=500, blank=True, default="")

    duration = models.IntegerField(
        "时长（秒）",
        default=0,
        help_text="用于筛选短视频/长视频",
    )

    pubdate = models.DateTimeField(
        "发布时间",
        null=True,
        blank=True,
        db_index=True,
        help_text="用于趋势分析，按时间聚合",
    )

    # 标签以逗号分隔存储（如 "编程,Python,教程"）
    # 选择理由：标签仅用于分词与检索，无需独立表关联，保持结构简单
    tags = models.CharField(
        "标签",
        max_length=500,
        blank=True,
        default="",
        help_text="逗号分隔，用于关键词分析与向量化",
    )

    # ---------------- 互动数据 ----------------
    view_count = models.BigIntegerField("播放量", default=0, db_index=True)
    like_count = models.BigIntegerField("点赞数", default=0)
    coin_count = models.BigIntegerField("投币数", default=0)
    favorite_count = models.BigIntegerField("收藏数", default=0)
    share_count = models.BigIntegerField("分享数", default=0)
    danmaku_count = models.BigIntegerField("弹幕数", default=0)
    reply_count = models.BigIntegerField("评论数", default=0)

    # 互动率：(点赞+投币+收藏) / 播放量
    # 冗余存储的理由：榜单要按互动率排序，实时计算需要全表扫描，
    # 入库时算好可显著提升查询性能（见 README 优化章节）
    interaction_rate = models.FloatField(
        "互动率",
        default=0.0,
        db_index=True,
        help_text="(点赞+投币+收藏)/播放量，入库时计算，用于质量排序",
    )

    # ---------------- 数据来源标记 ----------------
    # 【为什么必须有这个字段】
    # 开发阶段用 seed_demo 生成的模拟数据，其 bvid 是虚构的，
    # 在B站搜索不到、点开原站会 404。
    # 若不与真实抓取的数据区分，使用者会误以为"爬虫抓的数据是假的"，
    # 从而对系统可信度产生错误判断。
    #
    # 有了这个标记，前端可以：
    #   · 给模拟数据打上「模拟数据」标签
    #   · 不给模拟数据显示"跳转B站"按钮（点了也是 404，反而更困惑）
    is_demo = models.BooleanField(
        "是否模拟数据",
        default=False,
        db_index=True,
        help_text="True 表示由 seed_demo 生成，bvid 为虚构值，B站无法访问",
    )

    class Meta:
        db_table = "videos_video"
        verbose_name = "视频"
        verbose_name_plural = "视频"
        # 默认按发布时间倒序，符合"最新视频"的常见需求
        ordering = ["-pubdate", "-created_at"]
        indexes = [
            # 热榜查询：按分区筛选后按播放量排序
            models.Index(fields=["partition", "-view_count"], name="idx_video_part_view"),
            # 趋势分析：按发布时间范围查询
            models.Index(fields=["-pubdate"], name="idx_video_pubdate"),
            # 质量榜单：按互动率排序
            models.Index(fields=["-interaction_rate"], name="idx_video_interaction"),
            # UP主作品列表
            models.Index(fields=["upuser", "-pubdate"], name="idx_video_up_pub"),
            # 按数据来源筛选（区分真实抓取与模拟数据）
            models.Index(fields=["is_demo", "-pubdate"], name="idx_video_demo_pub"),
        ]

    def __str__(self):
        return f"{self.bvid} {self.title[:30]}"

    # -----------------------------------------------------------------
    # 计算属性
    # -----------------------------------------------------------------
    @property
    def source_url(self):
        """该视频在B站的原站地址。

        ⚠️ 模拟数据的 bvid 是虚构的，此链接会 404。
        前端应结合 is_demo 判断是否展示跳转入口。
        """
        return f"https://www.bilibili.com/video/{self.bvid}"

    @property
    def duration_display(self):
        """把秒数格式化为 mm:ss 或 hh:mm:ss，供前端直接展示。"""
        total = self.duration or 0
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def tag_list(self):
        """把逗号分隔的标签转成列表，便于序列化输出。"""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    def calculate_interaction_rate(self):
        """计算互动率并写回字段（入库前调用，不自动保存）。"""
        if not self.view_count:
            self.interaction_rate = 0.0
            return 0.0
        interactions = (self.like_count or 0) + (self.coin_count or 0) + (self.favorite_count or 0)
        self.interaction_rate = round(interactions / self.view_count, 6)
        return self.interaction_rate


class Danmaku(TimeStampedModel):
    """弹幕。

    【为什么单独建表而不是塞进 Video】
    单个热门视频的弹幕可达数万条，若存在 Video 里会导致主表膨胀、
    查询变慢。独立成表后可按需分页拉取，也便于做情感分析。
    """

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,     # 视频删除时弹幕一并清理
        related_name="danmakus",
        verbose_name="所属视频",
        db_index=True,
    )

    # 弹幕在 B站 中的唯一 ID，用于去重（同一条弹幕不重复入库）
    dmid = models.BigIntegerField(
        "弹幕ID",
        null=True,
        blank=True,
        db_index=True,
        help_text="B站弹幕唯一 ID，用于幂等去重",
    )

    content = models.CharField(
        "弹幕内容",
        max_length=500,
        db_index=True,
        help_text="文本内容，用于分词与情感分析",
    )

    # 弹幕出现在视频第几秒
    video_time = models.FloatField(
        "出现时间点（秒）",
        default=0.0,
        help_text="用于生成情绪波动图（横轴为视频时间）",
    )

    # 弹幕发送时间（B站接口返回的是 Unix 时间戳）
    send_time = models.DateTimeField(
        "发送时间",
        null=True,
        blank=True,
        db_index=True,
        help_text="用于分析观众活跃时段",
    )

    # ---------------- 情感分析结果（由 apps.ai 回填）----------------
    sentiment_score = models.FloatField(
        "情感分值",
        null=True,
        blank=True,
        db_index=True,
        help_text="0~1，越大越正面；null 表示尚未分析",
    )

    SENTIMENT_CHOICES = [
        ("positive", "正向"),
        ("neutral", "中性"),
        ("negative", "负向"),
    ]
    sentiment_label = models.CharField(
        "情感标签",
        max_length=10,
        choices=SENTIMENT_CHOICES,
        blank=True,
        default="",
        db_index=True,
        help_text="由情感分析任务回填，空表示未分析",
    )

    # 情绪分类标签（高燃 / 泪目 / 搞笑 / 吐槽 ...），逗号分隔
    emotion_tags = models.CharField(
        "情绪标签",
        max_length=100,
        blank=True,
        default="",
        help_text="如：高燃,搞笑，用于情绪分布统计",
    )

    class Meta:
        db_table = "videos_danmaku"
        verbose_name = "弹幕"
        verbose_name_plural = "弹幕"
        ordering = ["video_time"]
        indexes = [
            # 情绪波动图：按视频 + 时间点排序
            models.Index(fields=["video", "video_time"], name="idx_danmaku_video_time"),
            # 情感分布统计：按视频 + 情感标签聚合
            models.Index(fields=["video", "sentiment_label"], name="idx_danmaku_video_senti"),
            # 待分析弹幕的筛选（sentiment_label 为空）
            models.Index(fields=["sentiment_label"], name="idx_danmaku_senti"),
        ]
        # 同一视频内，同一条弹幕只存一次
        constraints = [
            models.UniqueConstraint(
                fields=["video", "dmid"],
                name="uniq_danmaku_video_dmid",
            ),
        ]

    def __str__(self):
        return f"[{self.video.bvid}] {self.content[:20]}"

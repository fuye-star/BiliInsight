# -*- coding: utf-8 -*-
"""
生成演示数据命令。

【为什么需要这个命令】
  1. **无网也能开发前端**：前端同学不必等爬虫跑完就能调图表；
  2. **答辩现场零风险**：万一现场网络受限，一条命令即可造出完整数据集；
  3. **测试分页与排序**：可自定义规模，验证前端分页、榜单排序是否正确；
  4. **让情感分析有数据可跑**：直接生成带情感标签的弹幕。

【数据特点】
  · 使用固定随机种子，同样的参数每次生成完全相同的数据（可复现）；
  · 播放量/点赞等按真实分布的形态生成（播放量远大于点赞，点赞大于投币），
    使互动率、榜单排序看起来合理，而不是一堆随机数；
  · 视频发布时间均匀分布在最近 N 天内，让"趋势图"有形状。

用法：
    python manage.py seed_demo                    # 默认 200 条视频 + 3000 条弹幕
    python manage.py seed_demo --videos 500 --danmaku 8000
    python manage.py seed_demo --clear            # 先清空再生成
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.videos.models import Danmaku, Partition, UpUser, Video

# ---------------------------------------------------------------------------
# 素材库：用于拼装看起来真实的中文标题
# ---------------------------------------------------------------------------
# 按分区准备专属词库，使标题与分区语义匹配（科技区不会出现"美食"标题）
TITLE_MATERIALS = {
    "科技": {
        "subjects": ["国产芯片", "大模型", "折叠屏手机", "机械键盘", "固态硬盘",
                     "扫地机器人", "无人机", "智能眼镜", "开源项目", "显卡"],
        "actions": ["深度评测", "上手体验", "拆解全过程", "三个月使用报告",
                    "横向对比", "从零搭建", "避坑指南", "原理讲解"],
    },
    "数码": {
        "subjects": ["旗舰手机", "轻薄本", "平板电脑", "显示器", "耳机",
                     "相机", "充电宝", "路由器", "鼠标", "智能手表"],
        "actions": ["选购指南", "开箱评测", "双十一推荐", "性能实测",
                    "对比分析", "性价比之王", "深度体验"],
    },
    "游戏": {
        "subjects": ["开放世界新作", "独立游戏", "怀旧经典", "竞技网游", "单机大作",
                     "像素游戏", "恐怖游戏", "模拟经营"],
        "actions": ["通关实况", "全成就攻略", "开局教学", "剧情解析",
                    "极限挑战", "彩蛋盘点", "新手入门"],
    },
    "知识": {
        "subjects": ["量子力学", "经济学原理", "中国历史", "心理学效应", "高等数学",
                     "哲学思辨", "天文学", "语言学习"],
        "actions": ["十分钟讲透", "通俗解读", "从零入门", "深度剖析",
                    "常见误区", "系统梳理"],
    },
    "生活": {
        "subjects": ["出租屋改造", "早起作息", "独居生活", "收纳整理", "阳台种菜",
                     "通勤穿搭", "极简主义", "省钱技巧"],
        "actions": ["实录", "经验分享", "一个月变化", "保姆级教程",
                    "真实测评", "踩坑总结"],
    },
    "美食": {
        "subjects": ["家常菜", "深夜食堂", "街头小吃", "烘焙", "火锅",
                     "减脂餐", "地方特色菜", "早餐"],
        "actions": ["零失败做法", "探店实录", "成本核算", "做法详解",
                    "新手友好", "一次成功"],
    },
}

# 弹幕素材：正向 / 中性 / 负向各准备一批，便于情感分析展示效果
DANMAKU_MATERIALS = {
    "positive": [
        "太强了！", "干货满满", "已三连", "up主辛苦了", "这个讲得真清楚",
        "爱了爱了", "收藏了慢慢看", "质量太高了", "终于等到了", "泪目",
        "燃起来了", "笑死我了哈哈哈", "这就是专业", "前排学习", "受益匪浅",
        "看哭了", "太治愈了", "永远支持up", "满分视频", "优秀！",
    ],
    "neutral": [
        "打卡", "来了来了", "沙发", "有人吗", "路过",
        "第一", "签到", "看看", "嗯嗯", "原来如此",
        "记笔记", "第几集了", "更新了", "好久不见", "顺便问下",
    ],
    "negative": [
        "有点失望", "没看懂", "节奏太慢了", "音质有点问题", "标题党",
        "不如上一期", "太长了", "画面有点糊", "讲错了", "广告太多",
    ],
}

# 情绪分类标签，与情感倾向组合使用
EMOTION_TAGS = {
    "positive": ["高燃", "感动", "搞笑", "治愈"],
    "neutral": ["疑问", "打卡"],
    "negative": ["吐槽", "失望"],
}


# ===========================================================================
# bvid 确定性生成
# ===========================================================================
def _deterministic_bvid(index: int, used: set) -> str:
    """根据索引生成确定性的模拟 bvid。

    【为什么必须确定性】
    早期版本用 random 生成，导致每次重跑 seed_demo（内部会先清空重建）
    得到的 bvid 都不同。后果是：前端若缓存了旧 bvid（例如详情页 URL、
    或上一轮渲染的列表），重跑后再点击就会 404，
    表现为"点视频详情后自动弹回列表"——一个很难定位的诡异 bug。

    改为基于索引的哈希后，同一批数据永远得到同样的 bvid，
    重跑不会破坏已有链接，也让演示可复现。

    【为什么用 hashlib 而不是内置 hash()】
    Python 的 hash() 对字符串会加随机盐（PYTHONHASHSEED），
    每次进程启动结果都不同，无法用于确定性生成。
    hashlib 是稳定的。

    参数:
        index: 视频序号
        used:  已占用的 bvid 集合（极端哈希碰撞时递增重试）

    返回:
        形如 BV1xxxxxxxxx 的确定性 bvid
    """
    import hashlib

    salt = 0
    while True:
        digest = hashlib.md5(f"biliinsight-demo-{index}-{salt}".encode()).hexdigest()
        # B站 bvid 的字符集（去掉易混淆的 0/O/l/I）
        charset = "abcdefghijkmnpqrstuvwxyz123456789"
        body = "".join(charset[int(digest[i * 2:i * 2 + 2], 16) % len(charset)] for i in range(9))
        bvid = f"BV1{body}"   # 以 BV1 开头，贴近真实格式
        if bvid not in used:
            return bvid
        salt += 1


class Command(BaseCommand):
    """生成用于开发与演示的模拟数据。"""

    help = "生成演示数据（视频 / UP主 / 弹幕），无需联网"

    def add_arguments(self, parser):
        """定义命令行参数。"""
        parser.add_argument(
            "--videos",
            type=int,
            default=200,
            help="生成的视频条数，默认 200",
        )
        parser.add_argument(
            "--danmaku",
            type=int,
            default=3000,
            help="生成的弹幕总条数，默认 3000",
        )
        parser.add_argument(
            "--upusers",
            type=int,
            default=40,
            help="生成的 UP主 数量，默认 40",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="视频发布时间跨度（天），默认 30，用于趋势图",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="生成前先清空已有的视频/弹幕/UP主数据",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20260918,
            help="随机种子，固定种子可复现同一批数据，默认 20260918",
        )

    def handle(self, *args, **options):
        """命令入口。"""
        random.seed(options["seed"])

        video_count = options["videos"]
        danmaku_count = options["danmaku"]
        upuser_count = options["upusers"]
        days = options["days"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  BiliInsight 演示数据生成"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  视频   : {video_count} 条")
        self.stdout.write(f"  弹幕   : {danmaku_count} 条")
        self.stdout.write(f"  UP主   : {upuser_count} 个")
        self.stdout.write(f"  时间跨度: 最近 {days} 天")
        self.stdout.write(f"  随机种子: {options['seed']}（固定种子保证可复现）")
        self.stdout.write("")

        if options["clear"]:
            self._clear()

        try:
            with transaction.atomic():
                partitions = self._create_partitions()
                upusers = self._create_upusers(upuser_count)
                videos = self._create_videos(
                    video_count, partitions, upusers, days
                )
                self._create_danmaku(danmaku_count, videos)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"生成失败：{exc}"))
            raise

        self._report()

    # -----------------------------------------------------------------
    # 清理
    # -----------------------------------------------------------------
    def _clear(self):
        """清空业务数据（保留分区表，它会被复用）。"""
        self.stdout.write(self.style.WARNING("  正在清空已有数据..."))
        # 注意删除顺序：弹幕依赖视频，视频依赖 UP主
        Danmaku.objects.all().delete()
        Video.objects.all().delete()
        UpUser.objects.all().delete()
        self.stdout.write(self.style.WARNING("  已清空"))

    # -----------------------------------------------------------------
    # 分区
    # -----------------------------------------------------------------
    def _create_partitions(self) -> list[Partition]:
        """确保分区存在并返回。

        使用 get_or_create 保证幂等——重复执行命令不会产生重复分区。
        """
        from apps.spider.constants import PARTITIONS

        # 只使用有素材词库的分区，保证标题语义合理
        names = list(TITLE_MATERIALS.keys())
        created = 0
        partitions = []

        # ECharts 饼图配色，前端可直接取用
        palette = [
            "#5470C6", "#91CC75", "#FAC858", "#EE6666",
            "#73C0DE", "#3BA272", "#FC8452", "#9A60B4",
        ]

        for idx, name in enumerate(names):
            partition, is_new = Partition.objects.get_or_create(
                name=name,
                defaults={
                    "bili_tid": PARTITIONS.get(name),
                    "color": palette[idx % len(palette)],
                },
            )
            partitions.append(partition)
            if is_new:
                created += 1

        self.stdout.write(f"  分区     : 共 {len(partitions)} 个（新建 {created} 个）")
        return partitions

    # -----------------------------------------------------------------
    # UP主
    # -----------------------------------------------------------------
    def _create_upusers(self, count: int) -> list[UpUser]:
        """生成 UP主。

        粉丝数按幂律分布生成：少数头部 UP主 粉丝量级远高于长尾，
        这样"UP主排行榜"才有区分度。
        """
        prefixes = ["爱吃", "专注", "每日", "硬核", "温柔", "沉默", "疯狂", "认真的"]
        cores = ["测评", "科普", "实况", "手作", "笔记", "日常", "研究所", "频道"]
        suffixes = ["的猫", "工作室", "本尊", "同学", "实验室", "君", "酱", ""]

        upusers = []
        used_names = set()

        for i in range(count):
            # 拼接昵称并去重
            for _ in range(20):
                name = f"{random.choice(prefixes)}{random.choice(cores)}{random.choice(suffixes)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            else:
                name = f"UP主{i:03d}"

            # 幂律分布：少数 UP主 粉丝极多
            # random.paretovariate 产生长尾分布，再取整
            follower = int(random.paretovariate(1.3) * 8000)
            follower = min(follower, 8_000_000)

            upuser = UpUser.objects.create(
                mid=random.randint(10_000_000, 699_999_999),
                name=name,
                avatar=f"https://i0.hdslb.com/bfs/face/demo_{i:04d}.jpg",
                sign=f"{random.choice(['分享', '记录', '专注', '热爱'])}"
                     f"{random.choice(['科技', '生活', '游戏', '知识', '美食'])}内容",
                follower_count=follower,
            )
            upusers.append(upuser)

        self.stdout.write(f"  UP主     : 生成 {len(upusers)} 个")
        return upusers

    # -----------------------------------------------------------------
    # 视频
    # -----------------------------------------------------------------
    def _create_videos(
        self,
        count: int,
        partitions: list[Partition],
        upusers: list[UpUser],
        days: int,
    ) -> list[Video]:
        """批量生成视频。

        【互动数据为什么这样生成】
        真实B站数据的量级关系是：
            播放量 >> 点赞 > 收藏 ≈ 投币 > 分享 > 弹幕 > 评论
        因此这里以播放量为基准，按比例派生其他指标，并加入随机抖动。
        这样计算出的 interaction_rate（互动率）会落在合理区间（2%-15%），
        榜单排序才有意义。
        """
        now = timezone.now()
        objects = []
        # 记录已用的 bvid，避免唯一约束冲突
        used_bvids = set()

        for i in range(count):
            partition = random.choice(partitions)
            upuser = random.choice(upusers)
            material = TITLE_MATERIALS[partition.name]

            title = (
                f"【{random.choice(material['subjects'])}】"
                f"{random.choice(material['actions'])}"
                f"｜第{random.randint(1, 99)}期"
            )

            # ---- bvid：确定性生成 ----
            # 【为什么不用 random】
            # 之前用 random 生成，导致每次重跑 seed_demo（它内部会先清空）
            # 得到的 bvid 都不同。若前端缓存了旧的 bvid（如详情页 URL），
            # 重跑后点进去就是 404，表现为"点视频详情后弹回列表"。
            #
            # 改为基于索引的确定性哈希：同一批数据永远得到同样的 bvid，
            # 重跑也不会破坏已有的链接。
            bvid = _deterministic_bvid(i, used_bvids)
            used_bvids.add(bvid)

            # 播放量：同样用长尾分布，少量爆款 + 大量普通视频
            view = int(random.paretovariate(1.6) * 5000)
            view = min(view, 30_000_000)

            # 按真实比例派生互动指标（比例带随机抖动）
            like = int(view * random.uniform(0.02, 0.09))
            coin = int(view * random.uniform(0.004, 0.025))
            favorite = int(view * random.uniform(0.006, 0.03))
            share = int(view * random.uniform(0.001, 0.008))
            danmaku = int(view * random.uniform(0.001, 0.006))
            reply = int(view * random.uniform(0.0005, 0.003))

            interactions = like + coin + favorite
            interaction_rate = round(interactions / view, 6) if view else 0.0

            # 发布时间均匀分布在最近 days 天内，让趋势图有形状
            pubdate = now - timedelta(
                days=random.uniform(0, days),
                hours=random.uniform(0, 24),
            )

            objects.append(
                Video(
                    bvid=bvid,
                    aid=random.randint(100_000_000, 999_999_999),
                    title=title[:300],
                    description=f"这是用于开发与演示的模拟视频数据，分区：{partition.name}。"
                                f"本记录由 seed_demo 命令生成，bvid 为虚构值，"
                                f"在B站无法访问。",
                    cover_url=f"https://i0.hdslb.com/bfs/archive/demo_{i:05d}.jpg",
                    duration=random.randint(45, 2400),
                    pubdate=pubdate,
                    partition=partition,
                    upuser=upuser,
                    tags=f"{partition.name},{random.choice(material['subjects'])}",
                    view_count=view,
                    like_count=like,
                    coin_count=coin,
                    favorite_count=favorite,
                    share_count=share,
                    danmaku_count=danmaku,
                    reply_count=reply,
                    interaction_rate=interaction_rate,
                    # 标记为模拟数据：前端据此打标签、并隐藏"跳转B站"入口
                    # （虚构 bvid 跳过去只会 404，给个点不通的链接更糟）
                    is_demo=True,
                )
            )

        # bulk_create 一次插入，比逐条 save 快得多（数量级差异）
        Video.objects.bulk_create(objects, batch_size=500)

        # 【关键】bulk_create 不会回填主键（Django 已知限制），
        # 因此上面 objects 里的实例 pk 仍为 None。
        # 而弹幕需要 video_id 外键，用未保存的实例会报：
        #   ValueError: bulk_create() prohibited to prevent data loss
        #             due to unsaved related object 'video'
        # 解决办法：按唯一键 bvid 重新查回带主键的实例。
        bvids = [v.bvid for v in objects]
        saved_videos = list(Video.objects.filter(bvid__in=bvids))
        # 建立 bvid -> 实例 映射，保证后续与弹幕的顺序无关
        by_bvid = {v.bvid: v for v in saved_videos}
        saved_videos = [by_bvid[b] for b in bvids if b in by_bvid]

        # 回填每个 UP主 的视频计数（冗余字段，避免列表页频繁 COUNT）
        for upuser in upusers:
            upuser.video_count = Video.objects.filter(upuser=upuser).count()
        UpUser.objects.bulk_update(upusers, ["video_count"], batch_size=200)

        self.stdout.write(f"  视频     : 生成 {len(saved_videos)} 条")
        return saved_videos

    # -----------------------------------------------------------------
    # 弹幕
    # -----------------------------------------------------------------
    def _create_danmaku(self, total: int, videos: list[Video]):
        """为随机视频生成弹幕。

        【情感标签为什么直接生成】
        真实流程是"抓弹幕 → 情感分析模块打标"。但演示数据的目的
        是让前端图表立刻有内容，因此这里按正向/中性/负向比例
        直接写入标签，使情绪分布图与词云立刻可见。
        真实数据仍由 apps.ai 的分析任务处理。
        """
        if not videos or total <= 0:
            return

        # 按 6:3:1 的比例分配三种情感，接近真实弹幕分布
        buckets = (
            ["positive"] * 6 + ["neutral"] * 3 + ["negative"] * 1
        )

        now = timezone.now()
        objects = []
        used_pairs = set()   # (video_id, dmid) 去重，避免唯一约束冲突
        dmid_seq = 1

        for i in range(total):
            video = random.choice(videos)

            # 弹幕出现在视频的前 90% 时长内（结尾通常弹幕较少）
            max_time = max(video.duration * 0.9, 10)
            video_time = round(random.uniform(0, max_time), 2)

            sentiment = random.choice(buckets)
            content = random.choice(DANMAKU_MATERIALS[sentiment])
            # 偶尔加个后缀，避免弹幕完全重复
            if random.random() < 0.3:
                content += random.choice(["~", "！", "哈哈", "233", "awa", "！？"])

            # 保证 (video, dmid) 唯一
            while True:
                dmid = dmid_seq
                dmid_seq += 1
                if (video.pk, dmid) not in used_pairs:
                    used_pairs.add((video.pk, dmid))
                    break

            # 情感分值：正向偏 0.7-0.99，中性 0.4-0.6，负向 0.01-0.3
            if sentiment == "positive":
                score = round(random.uniform(0.70, 0.99), 4)
            elif sentiment == "neutral":
                score = round(random.uniform(0.40, 0.60), 4)
            else:
                score = round(random.uniform(0.01, 0.30), 4)

            emotion = random.choice(EMOTION_TAGS[sentiment])

            objects.append(
                Danmaku(
                    video=video,
                    dmid=dmid,
                    content=content[:500],
                    video_time=video_time,
                    send_time=video.pubdate + timedelta(hours=random.uniform(0, 72))
                    if video.pubdate else now,
                    sentiment_score=score,
                    sentiment_label=sentiment,
                    emotion_tags=emotion,
                )
            )

        Danmaku.objects.bulk_create(objects, batch_size=1000)
        self.stdout.write(f"  弹幕     : 生成 {len(objects)} 条（已带情感标签）")

    # -----------------------------------------------------------------
    # 汇总
    # -----------------------------------------------------------------
    def _report(self):
        """打印最终数据统计与后续操作提示。"""
        video_total = Video.objects.count()
        danmaku_total = Danmaku.objects.count()
        upuser_total = UpUser.objects.count()
        partition_total = Partition.objects.count()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  数据库当前状态"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  分区     : {partition_total}")
        self.stdout.write(f"  UP主     : {upuser_total}")
        self.stdout.write(self.style.SUCCESS(f"  视频     : {video_total}"))
        self.stdout.write(self.style.SUCCESS(f"  弹幕     : {danmaku_total}"))

        # 情感分布，顺便验证数据生成的正确性
        from django.db.models import Count

        dist = (
            Danmaku.objects.exclude(sentiment_label="")
            .values("sentiment_label")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        if dist:
            self.stdout.write("")
            self.stdout.write("  弹幕情感分布：")
            label_map = {"positive": "正向", "neutral": "中性", "negative": "负向"}
            for row in dist:
                label = label_map.get(row["sentiment_label"], row["sentiment_label"])
                pct = row["n"] / danmaku_total * 100 if danmaku_total else 0
                bar = "█" * int(pct / 2)
                self.stdout.write(f"    {label}  {pct:5.1f}%  {bar}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  下一步"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write("  启动服务后访问：")
        self.stdout.write("    http://127.0.0.1:8000/admin/        查看数据（admin）")
        self.stdout.write("    http://127.0.0.1:8000/api/docs/     接口文档")
        self.stdout.write("")

        # ---- 清空分析类缓存 ----
        # 【为什么生成数据后也要清】
        #   与 crawl 同理：分析接口带 300-600 秒缓存。
        #   重新灌数据后若不清，看板会继续显示上一批数据的统计值。
        #   尤其是配合 --clear 重建时，旧缓存会让新老数据同时"存在"于界面上。
        from apps.analytics.services import clear_analytics_cache

        cleared = clear_analytics_cache()
        self.stdout.write(self.style.SUCCESS(f"  已清分析缓存 : {cleared} 个键"))
        self.stdout.write("")

# -*- coding: utf-8 -*-
"""
弹幕情感分析命令。

【为什么需要这个命令】
爬虫只负责抓取原始弹幕，情感标签需要单独分析回填。
拆成独立步骤的好处：
  · 爬虫不被分析拖慢（分析需要加载模型，首次较慢）
  · 可以反复重跑分析而无需重新抓取
  · 更换情感分析后端后，一条命令即可全量重标

用法：
    # 分析全部未标注的弹幕（默认批量 500 条一轮）
    python manage.py analyze_sentiment

    # 指定批量大小与总数上限
    python manage.py analyze_sentiment --batch 1000 --limit 5000

    # 只分析某个视频的弹幕
    python manage.py analyze_sentiment --video BV1xx411c7mD

    # 全量重标（覆盖已有结果）
    python manage.py analyze_sentiment --reset

    # 查看某个视频的情感分布（不写库）
    python manage.py analyze_sentiment --video BV1xx411c7mD --show-dist
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai.sentiment import clean_text, get_analyzer
from apps.videos.models import Danmaku

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """对弹幕做情感分析并回填标签。"""

    help = "对弹幕执行情感分析，回填 sentiment_score / sentiment_label / emotion_tags"

    def add_arguments(self, parser):
        """定义命令行参数。"""
        parser.add_argument(
            "--batch",
            type=int,
            default=500,
            help="每批处理条数，默认 500（批次间会打印进度）",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="最多处理多少条，0 表示不限制",
        )
        parser.add_argument(
            "--video",
            type=str,
            default="",
            help="只处理指定视频的弹幕，值为 BV 号",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="重新分析全部弹幕（含已有标签的），用于更换后端后全量重标",
        )
        parser.add_argument(
            "--show-dist",
            action="store_true",
            help="只展示情感分布统计，不做分析",
        )
        parser.add_argument(
            "--backend",
            type=str,
            default="",
            help="指定情感分析后端：snownlp / paddlenlp，默认读 .env",
        )

    def handle(self, *args, **options):
        """命令入口。"""
        # ---- 仅查看分布 ----
        if options["show_dist"]:
            self._show_distribution(options["video"])
            return

        analyzer = get_analyzer(options["backend"] or None)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  弹幕情感分析"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  分析后端 : {analyzer.backend_name}")
        self.stdout.write(f"  后端可用 : {'是' if analyzer.available else '否（将返回中性值）'}")
        self.stdout.write(f"  批量大小 : {options['batch']}")

        if not analyzer.available:
            self.stdout.write("")
            self.stderr.write(self.style.ERROR(
                "情感分析后端不可用！请检查依赖是否安装：\n"
                "  snownlp   -> pip install snownlp\n"
                "  paddlenlp -> 需 Python 3.11/3.12，见 requirements-paddle.txt"
            ))

        # ---- 构造待处理查询集 ----
        qs = Danmaku.objects.all()
        if options["video"]:
            qs = qs.filter(video__bvid=options["video"])
            if not qs.exists():
                raise CommandError(f"视频不存在或没有弹幕：{options['video']}")

        if not options["reset"]:
            # 默认只处理尚未标注的（sentiment_label 为空）
            qs = qs.filter(sentiment_label="")

        total = qs.count()
        limit = options["limit"]
        if limit and total > limit:
            total = limit

        if total == 0:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                "没有待分析的弹幕。若需全量重标，请加 --reset"
            ))
            return

        self.stdout.write(f"  待处理   : {total} 条")
        self.stdout.write("")

        # ---- 分批处理 ----
        batch_size = max(1, options["batch"])
        processed = 0
        started = time.monotonic()

        # 用主键游标分批，避免 offset 随数据量增大而变慢
        last_id = 0

        while processed < total:
            remaining = total - processed
            current_batch = min(batch_size, remaining)

            batch = list(
                qs.filter(id__gt=last_id).order_by("id")[:current_batch]
            )
            if not batch:
                break

            last_id = batch[-1].id
            
            # 批量分析
            texts = [clean_text(d.content) for d in batch]
            results = analyzer.analyze_batch(texts)

            # 回填结果
            to_update = []
            for danmaku, result in zip(batch, results):
                danmaku.sentiment_score = result["score"]
                danmaku.sentiment_label = result["label"]
                # 情绪标签用逗号分隔存入 CharField
                danmaku.emotion_tags = ",".join(result["emotion_tags"])[:100]
                to_update.append(danmaku)

            # bulk_update 比逐条 save 快一个数量级
            with transaction.atomic():
                Danmaku.objects.bulk_update(
                    to_update,
                    ["sentiment_score", "sentiment_label", "emotion_tags"],
                    batch_size=200,
                )

            processed += len(batch)

            # 进度输出
            elapsed = time.monotonic() - started
            rate = processed / elapsed if elapsed > 0 else 0
            self.stdout.write(
                f"  进度 {processed}/{total} "
                f"({processed / total * 100:.1f}%)  "
                f"{rate:.0f} 条/秒"
            )

        elapsed = time.monotonic() - started
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"分析完成：共处理 {processed} 条，耗时 {elapsed:.1f} 秒"
        ))

        # ---- 展示结果分布 ----
        self._show_distribution(options["video"])

    # -----------------------------------------------------------------
    # 分布统计
    # -----------------------------------------------------------------
    def _show_distribution(self, bvid: str = ""):
        """打印情感分布与高频情绪标签。"""
        from django.db.models import Count

        qs = Danmaku.objects.exclude(sentiment_label="")
        if bvid:
            qs = qs.filter(video__bvid=bvid)

        total = qs.count()
        if total == 0:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("暂无已分析的弹幕数据"))
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"  情感分布{f'（视频 {bvid}）' if bvid else '（全部）'}"
        ))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  已分析弹幕：{total} 条")
        self.stdout.write("")

        label_names = {"positive": "正向", "neutral": "中性", "negative": "负向"}
        rows = (
            qs.values("sentiment_label")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        for row in rows:
            label = label_names.get(row["sentiment_label"], row["sentiment_label"])
            pct = row["n"] / total * 100
            # 用方块字符画条形图，终端里直观可见
            bar = "█" * int(pct / 2)
            self.stdout.write(f"  {label}  {row['n']:>6} 条  {pct:5.1f}%  {bar}")

        # 情绪标签统计（拆分逗号分隔的字段）
        tag_counter: dict = {}
        for tags in qs.exclude(emotion_tags="").values_list("emotion_tags", flat=True):
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    tag_counter[tag] = tag_counter.get(tag, 0) + 1

        if tag_counter:
            self.stdout.write("")
            self.stdout.write("  情绪标签分布（Top 10）：")
            top = sorted(tag_counter.items(), key=lambda kv: kv[1], reverse=True)[:10]
            max_count = top[0][1] if top else 1
            for name, count in top:
                bar = "█" * int(count / max_count * 20)
                self.stdout.write(f"    {name:<6} {count:>6}  {bar}")

        self.stdout.write("")

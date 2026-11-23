# -*- coding: utf-8 -*-
"""
数据来源标记命令。

【为什么需要这个命令】
`is_demo` 字段是后加的（迁移 0002），因此**在它之前生成的演示数据**
都会被默认为 `is_demo=False`（即被当成真实数据）。
若不修正，前端会：
  · 不给这些数据打「模拟数据」标签 → 用户以为 bvid 是真实的
  · 给它们显示"跳转B站"按钮 → 点开是 404，比没有按钮更困惑

本命令用于批量修正历史数据的来源标记。

用法：
    # 查看当前标记情况
    python manage.py mark_data_source --status

    # 把 seed_demo 生成的数据标记为模拟数据（按描述文本识别）
    python manage.py mark_data_source --mark-demo

    # 把所有数据标记为真实抓取（谨慎使用）
    python manage.py mark_data_source --mark-real

    # 指定只处理某个分区
    python manage.py mark_data_source --mark-demo --partition 科技
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.videos.models import Video

logger = logging.getLogger(__name__)

#: 识别演示数据的特征文本。
#: seed_demo 生成的记录描述里必定包含这个片段，
#: 因此可以用它反推历史数据的真实来源。
DEMO_MARKER = "seed_demo"


class Command(BaseCommand):
    """修正视频的数据来源标记（is_demo）。"""

    help = "标记视频是模拟数据还是真实抓取数据"

    def add_arguments(self, parser):
        """定义参数。"""
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--mark-demo",
            action="store_true",
            help="把 seed_demo 生成的数据标记为模拟数据（is_demo=True）",
        )
        group.add_argument(
            "--mark-real",
            action="store_true",
            help="把所有数据标记为真实抓取（is_demo=False，谨慎使用）",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="仅查看当前的标记统计",
        )
        parser.add_argument(
            "--partition",
            type=str,
            default="",
            help="只处理指定分区",
        )

    def handle(self, *args, **options):
        """命令入口。"""
        # ---- 仅查看状态 ----
        if options["status"] or not (options["mark_demo"] or options["mark_real"]):
            self._show_status()
            if not (options["mark_demo"] or options["mark_real"]):
                self.stdout.write("")
                self.stdout.write(self.style.WARNING(
                    "未指定操作。可选：--mark-demo / --mark-real"
                ))
            return

        qs = Video.objects.all()
        if options["partition"]:
            qs = qs.filter(partition__name=options["partition"])
            self.stdout.write(f"  限定分区：{options['partition']}")

        # 累计本次实际改动的行数；为 0 时说明什么也没变，无需清缓存
        changed = 0

        # ---- 标记为模拟数据 ----
        if options["mark_demo"]:
            # 用描述文本识别：只有 seed_demo 生成的记录才含该片段
            demo_qs = qs.filter(description__contains=DEMO_MARKER)
            target_count = demo_qs.count()

            if target_count == 0:
                self.stdout.write(self.style.WARNING(
                    f"  未找到含「{DEMO_MARKER}」标记的记录"
                ))
                return

            updated = demo_qs.update(is_demo=True)
            changed += updated
            self.stdout.write(self.style.SUCCESS(
                f"  已标记 {updated} 条为模拟数据（is_demo=True）"
            ))

            # 同时把描述里缺失的说明补上，让用户在原站/后台也能看出来
            self.stdout.write(
                f"  说明：这些记录的 bvid 是虚构的，在B站无法访问"
            )

        # ---- 标记为真实数据 ----
        if options["mark_real"]:
            current_demo = qs.filter(is_demo=True).count()
            if current_demo == 0:
                self.stdout.write("  没有标记为模拟数据的记录，无需处理")
                return

            self.stdout.write(self.style.WARNING(
                f"  即将把 {current_demo} 条模拟数据改为真实数据标记"
            ))
            updated = qs.filter(is_demo=True).update(is_demo=False)
            changed += updated
            self.stdout.write(self.style.SUCCESS(
                f"  已改回 {updated} 条（is_demo=False）"
            ))
            self.stdout.write(self.style.WARNING(
                "  ⚠️ 请确认这些数据确实是真实抓取的，"
                "否则用户点开B站会看到 404"
            ))

        self.stdout.write("")
        self._show_status()

        # ---- 清空分析类缓存 ----
        # 【为什么标记变更也要清】
        #   is_demo 会随序列化器透出到 analytics 的返回里
        #   （top-videos / interaction 等都带 data_source 字段）。
        #   不清缓存的话，改完标记界面上仍是旧的"模拟/真实"标识。
        if changed:
            from apps.analytics.services import clear_analytics_cache

            cleared = clear_analytics_cache()
            self.stdout.write(self.style.SUCCESS(f"  已清分析缓存 : {cleared} 个键"))
            self.stdout.write("")

    # -----------------------------------------------------------------
    def _show_status(self):
        """打印当前标记统计。"""
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  数据来源标记统计"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))

        total = Video.objects.count()
        demo = Video.objects.filter(is_demo=True).count()
        real = total - demo

        self.stdout.write(f"  视频总数   : {total}")
        self.stdout.write(self.style.SUCCESS(f"  真实抓取   : {real}"))
        self.stdout.write(self.style.WARNING(f"  模拟数据   : {demo}"))

        if total and demo == total:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "  ⚠️ 当前全部是模拟数据。这些 bvid 在B站无法访问，\n"
                "     前端会隐藏「跳转B站」入口并显示「模拟数据」标签。\n"
                "     要获得可验证的真实数据，请执行：\n"
                "       python manage.py crawl --partition 科技 --limit 20 --interval 5"
            ))
        elif demo and real:
            self.stdout.write("")
            self.stdout.write(
                "  当前为混合数据：真实数据可点击跳转B站，模拟数据带标签标识"
            )

        # 按分区细分，便于判断哪些分区还没有真实数据
        if total:
            self.stdout.write("")
            self.stdout.write("  分区明细：")
            rows = (
                Video.objects.values("partition__name")
                .annotate(
                    total=Count("id"),
                    demo=Count("id", filter=models_q_demo()),
                )
                .order_by("-total")
            )
            for row in rows:
                name = row["partition__name"] or "未分区"
                self.stdout.write(
                    f"    {name:<8} 共 {row['total']:>4} 条"
                    f"（真实 {row['total'] - row['demo']:>4} / 模拟 {row['demo']:>4}）"
                )
        self.stdout.write("")


def models_q_demo():
    """构造 is_demo=True 的聚合过滤条件。

    单独抽成函数是为了让上面的 values().annotate() 写法保持整洁——
    Count 的 filter 参数需要 Q 对象，内联在链条里可读性差。
    """
    from django.db.models import Q

    return Q(is_demo=True)

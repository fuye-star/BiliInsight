# -*- coding: utf-8 -*-
"""清空业务数据命令 —— 用于"推倒重来"式重新抓取。

【为什么需要专门的命令（而不是手写 SQL）】
    本项目的数据之间存在级联关系，删除顺序错了会"删一半"：

        UpUser --CASCADE--> Video --CASCADE--> Danmaku

    也就是说，**先删 UP主 会把视频和弹幕一起带走**，
    但如果只删 Video，UP主 会留下来变成"没有任何视频的孤儿记录"，
    这些孤儿会在「UP主排行」里以粉丝数参与排序，干扰结果。

    因此清空必须按 Danmaku -> Video -> UpUser 的顺序显式执行，
    并且顺手把两处"派生数据"也清掉，否则界面会自相矛盾：

        · 分析缓存（Redis）—— 不清的话看板继续显示已删除数据的统计值
        · 向量索引（ChromaDB）—— 不清的话 AI 助手会引用已经不存在的视频

【默认行为】
    不带 --yes 时只**预览**将删除的内容，不实际执行 —— 防止误操作。

用法：
    # 查看将要删除什么（安全，不删）
    python manage.py reset_data

    # 确认清空
    python manage.py reset_data --yes

    # 保留分区表（分区是参考数据，默认保留）
    python manage.py reset_data --yes --keep-partitions

    # 连向量索引一起保留（一般不需要）
    python manage.py reset_data --yes --keep-index
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.videos.models import Danmaku, Partition, UpUser, Video

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """清空视频 / 弹幕 / UP主 数据。"""

    help = "清空视频、弹幕、UP主数据（含分析缓存与向量索引），用于重新抓取"

    def add_arguments(self, parser):
        """定义命令行参数。"""
        parser.add_argument(
            "--yes",
            action="store_true",
            help="确认执行删除；不加此参数时只预览，不做任何修改",
        )
        parser.add_argument(
            "--drop-partitions",
            action="store_true",
            help="连分区表一起清空（默认保留分区；分区是配置性参考数据）",
        )
        parser.add_argument(
            "--keep-index",
            action="store_true",
            help="保留向量索引（默认一并清空，避免 AI 引用已删除的视频）",
        )

    def handle(self, *args, **options):
        """命令入口。"""
        confirmed = options["yes"]
        drop_partitions = options["drop_partitions"]
        keep_index = options["keep_index"]

        # ---- 统计当前数据 ----
        video_total = Video.objects.count()
        real_total = Video.objects.filter(is_demo=False).count()
        demo_total = video_total - real_total
        danmaku_total = Danmaku.objects.count()
        upuser_total = UpUser.objects.count()
        partition_total = Partition.objects.count()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  数据重置"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  视频    : {video_total} 条（真实 {real_total} / 模拟 {demo_total}）")
        self.stdout.write(f"  弹幕    : {danmaku_total} 条")
        self.stdout.write(f"  UP主    : {upuser_total} 位")
        self.stdout.write(
            f"  分区    : {partition_total} 个"
            + ("（将保留）" if not drop_partitions else "（将一并清空）")
        )
        self.stdout.write(
            "  向量索引: " + ("保留" if keep_index else "将清空")
        )
        self.stdout.write("")

        if video_total == 0 and danmaku_total == 0 and upuser_total == 0:
            self.stdout.write(self.style.WARNING("  当前没有任何业务数据，无需清理"))
            self.stdout.write("")
            return

        # ---- 未确认时只预览 ----
        if not confirmed:
            self.stdout.write(self.style.WARNING(
                "  以上数据将被永久删除，且不可恢复。"
            ))
            self.stdout.write(self.style.WARNING(
                "  确认请追加 --yes 参数重新执行："
            ))
            self.stdout.write("      python manage.py reset_data --yes")
            self.stdout.write("")
            return

        # ---- 执行删除 ----
        # 顺序说明：Danmaku -> Video -> UpUser
        # 虽然数据库层面 CASCADE 会兜底，但显式按序删除能让统计数字准确，
        # 也避免依赖"某个外键恰好是 CASCADE"这种隐式约定。
        with transaction.atomic():
            deleted_danmaku = Danmaku.objects.all().delete()[0]
            deleted_video = Video.objects.all().delete()[0]
            deleted_upuser = UpUser.objects.all().delete()[0]
            deleted_partition = 0
            if drop_partitions:
                deleted_partition = Partition.objects.all().delete()[0]

        self.stdout.write(self.style.SUCCESS(
            f"  已删除弹幕 {deleted_danmaku} 条"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"  已删除视频 {deleted_video} 条"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"  已删除 UP主 {deleted_upuser} 位"
        ))
        if drop_partitions:
            self.stdout.write(self.style.SUCCESS(
                f"  已删除分区 {deleted_partition} 个"
            ))

        # ---- 清空分析缓存 ----
        # 【为什么必须清】
        #   分析接口带 300-600 秒缓存。数据删了却不清缓存，
        #   看板会继续显示已经不存在的视频的统计值。
        from apps.analytics.services import clear_analytics_cache

        cleared = clear_analytics_cache()
        self.stdout.write(self.style.SUCCESS(
            f"  已清分析缓存 {cleared} 个键"
        ))

        # ---- 清空向量索引 ----
        # 【为什么必须清】
        #   向量库里存的是视频文本的嵌入，删了视频却留着向量，
        #   AI 助手会检索到"已不存在的视频"并作为答案来源引用。
        if not keep_index:
            try:
                from apps.ai.vector_store import clear_index

                ok = clear_index()
                self.stdout.write(self.style.SUCCESS(
                    f"  向量索引：{'已清空' if ok else '清空失败（可稍后 build_index --rebuild）'}"
                ))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f"  向量索引清空失败：{exc}（可稍后 build_index --rebuild）"
                ))

        # ---- 结果确认 ----
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  清理后状态"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  视频    : {Video.objects.count()} 条")
        self.stdout.write(f"  弹幕    : {Danmaku.objects.count()} 条")
        self.stdout.write(f"  UP主    : {UpUser.objects.count()} 位")
        self.stdout.write(self.style.SUCCESS(f"  分区    : {Partition.objects.count()} 个"))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  下一步"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write("  抓取真实数据（含封面、UP主粉丝数、弹幕）：")
        self.stdout.write(
            "    python manage.py crawl --partition 科技 --limit 40 "
            "--with-danmaku 40 --interval 3"
        )
        self.stdout.write("")
        self.stdout.write("  抓完重建向量索引：")
        self.stdout.write("    python manage.py build_index --rebuild")
        self.stdout.write("")

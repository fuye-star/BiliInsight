# -*- coding: utf-8 -*-
"""
B站数据抓取命令。

【为什么要有这个命令（而不是只用 Celery）】
  · 首次建库、答辩演示时需要"立刻看到结果"，同步执行最直观；
  · 排查接口问题时能直接在终端看到日志，比翻 Celery 日志方便；
  · CI / 脚本中无需启动 Worker 即可灌数据。

用法示例：
    # 抓取单个分区的视频
    python manage.py crawl --partition 科技 --limit 50

    # 抓取多个分区（逗号分隔）
    python manage.py crawl --partition 科技,数码,游戏 --limit 30

    # 抓取全站热门榜
    python manage.py crawl --hot --limit 50

    # 抓取指定视频的弹幕
    python manage.py crawl --danmaku BV1xx411c7mD --limit 2000

    # 为数据库中弹幕最多的 10 个视频批量抓弹幕
    python manage.py crawl --batch-danmaku 10

【合规提醒】
请求间隔默认 2.0 秒且不可低于 1.0 秒，仅用于学习研究。
"""

import argparse
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.spider.base import RateLimitedError
from apps.spider.bilibili import BiliBiliSpider
from apps.spider.constants import DEFAULT_PARTITIONS, PARTITIONS, partition_tid

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """抓取 B站公开数据并入库。"""

    help = "抓取 B站视频 / 弹幕数据并写入数据库（仅用于学习研究）"

    def add_arguments(self, parser):
        """定义命令行参数。"""
        parser.add_argument(
            "--partition", "-p",
            type=str,
            default="",
            help=f"分区名，多个用逗号分隔。可选：{', '.join(list(PARTITIONS)[:8])} 等",
        )
        parser.add_argument(
            "--hot",
            action="store_true",
            help="抓取全站排行榜（走 ranking/v2 接口，不带 rid）",
        )
        parser.add_argument(
            "--popular",
            action="store_true",
            help=(
                "抓取全站热门列表（走 popular 接口，支持翻页）。"
                "与 --hot 不是同一个接口：热门列表风控更宽松，适合批量灌数据"
            ),
        )
        parser.add_argument(
            "--pages",
            type=int,
            default=6,
            metavar="N",
            help="配合 --popular 使用，最多翻多少页（每页约 50 条），默认 6",
        )
        parser.add_argument(
            "--danmaku",
            type=str,
            default="",
            help="抓取指定视频的弹幕，值为 BV 号",
        )
        parser.add_argument(
            "--batch-danmaku",
            type=int,
            default=0,
            metavar="N",
            help="为数据库中弹幕数最多的 N 个视频批量抓取弹幕",
        )
        parser.add_argument(
            "--limit", "-l",
            type=int,
            default=50,
            help="最多入库条数（视频）或弹幕条数，默认 50",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=None,
            help="请求间隔秒数，默认读取 .env 的 SPIDER_REQUEST_INTERVAL（不低于 1.0）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只抓取并解析，不写入数据库（用于验证接口是否可用）",
        )
        parser.add_argument(
            "--followers",
            action=argparse.BooleanOptionalAction,
            default=None,
            help=(
                "抓取涉及的 UP主 粉丝数。"
                "默认行为：本次若抓了视频则开启，只抓弹幕则关闭（避免误发几十次请求）。"
                "可用 --followers / --no-followers 强制指定"
            ),
        )
        parser.add_argument(
            "--followers-limit",
            type=int,
            default=0,
            metavar="N",
            help=(
                "最多为多少位 UP主 补粉丝数（默认 0 = 不限）。"
                "1 位 = 1 次请求，风控敏感时用它压量"
            ),
        )
        parser.add_argument(
            "--with-danmaku",
            type=int,
            default=0,
            metavar="N",
            help=(
                "为弹幕量最多的 N 个（尚无弹幕的）视频抓弹幕，默认 0 = 不抓。"
                "每个视频抓 1 包，约 2 次请求"
            ),
        )

    def handle(self, *args, **options):
        """命令入口。"""
        partition = (options["partition"] or "").strip()
        hot = options["hot"]
        danmaku = (options["danmaku"] or "").strip()
        batch_danmaku = options["batch_danmaku"]
        limit = options["limit"]
        dry_run = options["dry_run"]

        # ---- 参数校验：必须至少指定一种抓取目标 ----
        # ⚠️ 新增抓取方式时别忘了把它加进这个判断，否则会被误判成"未指定目标"，
        #    从而自动跑一遍默认分区 —— 这不只浪费请求，还会把风控额度用掉。
        #    （--popular 就漏加过一次，实测确实多抓了一个分区才被拦。）
        if not any([partition, hot, options["popular"], danmaku, batch_danmaku]):
            self.stdout.write(self.style.WARNING("未指定抓取目标，使用默认分区列表"))
            partition = ",".join(DEFAULT_PARTITIONS)

        spider = BiliBiliSpider(interval=options["interval"])

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  BiliInsight 数据抓取"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(f"  请求间隔 : {spider.interval} 秒（合规下限 1.0 秒）")
        self.stdout.write(f"  最大重试 : {spider.max_retries} 次")
        self.stdout.write(f"  试运行   : {'是（不写库）' if dry_run else '否'}")
        self.stdout.write("")

        if dry_run:
            # 试运行模式：只验证接口连通性与解析结果，不落库
            self._dry_run(spider, partition, hot, danmaku)
            return

        try:
            if batch_danmaku:
                self._run_batch_danmaku(spider, batch_danmaku, limit)

            if danmaku:
                self._run_danmaku(spider, danmaku, limit)

            if hot:
                stats = spider.run_hot(limit=limit)
                self._report("全站排名", stats)

            if options["popular"]:
                pages = max(1, min(int(options["pages"] or 6), 30))
                self.stdout.write(
                    f"  正在抓取全站热门（最多 {pages} 页 × 约 50 条）……"
                )
                stats = spider.run_popular(
                    limit=limit, max_pages=pages, page_size=50
                )
                self._report("全站热门", stats)

            if partition:
                names = [n.strip() for n in partition.split(",") if n.strip()]
                self._run_partitions(spider, names, limit)

            # ---- 补抓 UP主 粉丝数 ----
            # 【为什么放在视频入库之后】
            #   UP主 记录此时已由 upsert_upuser 建好，补粉丝数只需一次 UPDATE。
            # 【默认值为什么是"看情况"】
            #   本次抓了视频（partition/hot）-> 默认开启，因为这是需求的一部分；
            #   只抓弹幕（--danmaku BV...）-> 默认关闭，
            #   否则本想抓一个视频的弹幕，却顺带对全库 UP主 发了上百次请求。
            want_followers = options["followers"]
            if want_followers is None:
                want_followers = bool(partition or hot or options["popular"])

            if want_followers:
                self._run_followers(spider, options["followers_limit"])

            # ---- 抓弹幕 ----
            if options["with_danmaku"]:
                self._run_danmaku_batch(spider, options["with_danmaku"])

        except RateLimitedError as exc:
            # 限流是最常见的失败原因，给出明确的操作指引。
            # 注意：此时【不能】再继续重试，风控会随请求次数升级。
            self.stdout.write("")
            self.stderr.write(self.style.ERROR(f"被目标站点风控限流：{exc}"))
            self.stderr.write("")
            self.stderr.write(self.style.WARNING("处理建议（按顺序尝试）："))
            self.stderr.write("  1. 等待 10-30 分钟，让风控冷却（最重要，切勿立即重试）")
            self.stderr.write("  2. 调大 .env 中的 SPIDER_REQUEST_INTERVAL，例如 3.0 或 5.0")
            self.stderr.write("  3. 减小单次抓取量，例如 --limit 20")
            self.stderr.write("  4. 换一个网络环境（风控通常按 IP 维度统计）")
            self.stderr.write("")
            self.stderr.write(self.style.WARNING(
                "提示：B站风控按请求频率累积，连续重试会延长封禁时间。"
            ))
            raise CommandError("抓取被风控限流，请稍后重试")
        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("已手动中断"))
        finally:
            spider.close()

        # ---- 汇总 ----
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  抓取汇总"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        s = spider.stats
        self.stdout.write(f"  解析条数 : {s.fetched}")
        self.stdout.write(self.style.SUCCESS(f"  新增     : {s.created}"))
        self.stdout.write(f"  更新     : {s.updated}")
        if s.failed:
            self.stdout.write(self.style.WARNING(f"  失败     : {s.failed}"))
        self.stdout.write(f"  HTTP请求 : {s.requests} 次")

        # ---- 清空分析类缓存 ----
        # 【不清会怎样】
        #   分析接口（overview / top-upusers / top-videos / sentiment / wordcloud）
        #   都带 300-600 秒 Redis 缓存。
        #   抓完不清 -> 视频列表（无缓存）立刻更新，但看板总览与各排行榜
        #   继续显示旧数字最长 10 分钟，看起来像"数据只同步了一半"。
        if s.created or s.updated:
            from apps.analytics.services import clear_analytics_cache

            cleared = clear_analytics_cache()
            self.stdout.write(f"  已清分析缓存 : {cleared} 个键")
        self.stdout.write("")

    # -----------------------------------------------------------------
    # 内部方法
    # -----------------------------------------------------------------
    def _run_partitions(self, spider, names: list, limit: int):
        """按分区逐个抓取，并校验分区名是否合法。"""
        for name in names:
            if partition_tid(name) is None:
                self.stderr.write(self.style.WARNING(
                    f"跳过无法识别的分区：{name}（可用分区见 constants.PARTITIONS）"
                ))
                continue
            try:
                stats = spider.run_partition(name, limit=limit)
                self._report(f"分区 {name}", stats)
            except RateLimitedError:
                raise
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"分区 {name} 抓取失败：{exc}"))
                spider.stats.failed += 1

    def _run_danmaku(self, spider, bvid: str, limit: int):
        """抓取单个视频的弹幕。"""
        self.stdout.write(f"  正在抓取弹幕：{bvid}")
        stats = spider.run_danmaku(bvid, limit=limit)
        self._report(f"弹幕 {bvid}", stats)

    def _run_followers(self, spider, limit: int):
        """补抓 UP主 粉丝数。

        参数:
            spider: 爬虫实例
            limit:  最多处理多少位 UP主；0 表示不限
        """
        from apps.videos.models import UpUser

        # 只处理还没有粉丝数的 UP主，已有值的跳过以节省请求
        pending = UpUser.objects.filter(follower_count=0).count()
        if pending == 0:
            self.stdout.write("  UP主 粉丝数：无待补记录，跳过")
            return

        self.stdout.write("")
        self.stdout.write(
            f"  正在补抓 UP主 粉丝数（待补 {pending} 位，"
            f"1 位 1 次请求{'，上限 ' + str(limit) + ' 位' if limit else ''}）……"
        )
        stats = spider.run_upuser_followers(skip_filled=True, limit=limit)
        self.stdout.write(
            f"  UP主 粉丝数：成功 {stats.fetched} 位，"
            f"更新 {stats.updated} 行"
            + (f"，失败 {stats.failed} 位" if stats.failed else "")
        )

    def _run_danmaku_batch(self, spider, count: int):
        """为弹幕量最多的若干（尚无弹幕的）视频抓弹幕。

        参数:
            spider: 爬虫实例
            count:  处理多少个视频

        说明：每个视频只抓 **1 包**（6 分钟），约 2 次请求：
              1 次取 cid + 1 次取弹幕包。
              一包内的弹幕会全部入库（limit 只在包与包之间生效）。
        """
        from apps.videos.models import Danmaku, Video

        # 已有弹幕的视频不再重复抓，把请求留给没抓过的
        has_danmaku = set(
            Danmaku.objects.values_list("video_id", flat=True).distinct()
        )
        bvids = list(
            Video.objects.exclude(id__in=has_danmaku)
            .filter(is_demo=False)          # 模拟数据的视频在B站不存在，抓不到弹幕
            .order_by("-danmaku_count")
            .values_list("bvid", flat=True)[:count]
        )

        if not bvids:
            self.stdout.write("  弹幕：没有需要抓取的视频，跳过")
            return

        self.stdout.write("")
        self.stdout.write(
            f"  正在为 {len(bvids)} 个视频抓弹幕（每视频 1 包，约 2 次请求）……"
        )
        for i, bvid in enumerate(bvids, start=1):
            self.stdout.write(f"    [{i}/{len(bvids)}] {bvid}")

        stats = spider.run_danmaku_for_videos(bvids, limit=50)
        self.stdout.write(
            f"  弹幕：新增 {stats.created} 条，失败 {stats.failed} 个视频"
        )

    def _run_batch_danmaku(self, spider, count: int, limit: int):
        """为弹幕数最多的若干视频批量抓弹幕。"""
        from apps.videos.models import Video

        videos = list(
            Video.objects.filter(danmaku_count__gt=0)
            .order_by("-danmaku_count")[:count]
        )
        if not videos:
            self.stderr.write(self.style.WARNING(
                "数据库中没有视频记录，请先执行：python manage.py crawl --partition 科技"
            ))
            return

        self.stdout.write(f"  批量抓取 {len(videos)} 个视频的弹幕")
        for video in videos:
            try:
                spider.run_danmaku(video.bvid, limit=limit, video=video)
            except RateLimitedError:
                raise
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  {video.bvid} 失败：{exc}"))
                spider.stats.failed += 1

    def _dry_run(self, spider, partition: str, hot: bool, danmaku: str):
        """试运行：抓取并解析，打印结果但不写数据库。

        用途：确认网络能通、接口结构没变、解析器工作正常。
        """
        from apps.spider import parsers

        self.stdout.write(self.style.WARNING("【试运行模式】不会写入数据库"))
        self.stdout.write("")

        if hot or partition:
            if partition:
                tid = partition_tid(partition.split(",")[0].strip())
                label = f"分区 {partition.split(',')[0].strip()}"
            else:
                tid = None
                label = "全站热门"

            try:
                payload = spider.fetch_ranking(tid)
                items = parsers.parse_video_list(payload)
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] {label}：成功解析 {len(items)} 条视频"
                ))
                for item in items[:3]:
                    self.stdout.write(
                        f"       · {item.bvid}  {item.title[:32]}  "
                        f"播放 {item.view_count:,}"
                    )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  [X] {label} 抓取失败：{exc}"))

        if danmaku:
            try:
                cid = spider._fetch_cid(danmaku)
                if cid is None:
                    self.stderr.write(self.style.ERROR(f"  [X] 无法获取 {danmaku} 的 cid"))
                    return
                raw = spider.fetch_danmaku_segment(cid, 1)
                items = parsers.parse_danmaku_protobuf(raw)
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] 弹幕 {danmaku}：第 1 包解析出 {len(items)} 条"
                ))
                for item in items[:3]:
                    self.stdout.write(f"       · [{item.video_time:>8.2f}s] {item.content[:40]}")
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  [X] 弹幕抓取失败：{exc}"))

        self.stdout.write("")

    def _report(self, label: str, stats):
        """打印单次抓取的结果行。"""
        self.stdout.write(
            f"  {label}：解析 {stats.fetched} 条，"
            f"新增 {stats.created} 条，更新 {stats.updated} 条"
            + (f"，失败 {stats.failed} 条" if stats.failed else "")
        )

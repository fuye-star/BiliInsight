# -*- coding: utf-8 -*-
"""耐心抓取器 —— 在严格风控下把数据一点一点补齐。

【为什么需要单独一个脚本，而不是直接用 manage.py crawl】
    实测摸清了本机 IP 的额度规律：

        15:26      排行榜 1 次          -> OK
        15:44-45   弹幕 11 次           -> 全部 OK
        15:53:14   排行榜 1 次          -> OK
        15:53:20   粉丝数 第 1 次        -> -352 风控

    即大约 **每 30 分钟只能发 12 次左右请求**。
    而"40 个视频 + 40 位 UP主 粉丝数 + 40 个视频的弹幕"合计约 121 次请求，
    在单次运行里根本做不完 —— manage.py crawl 会中途被拦而退出。

    本脚本解决的就是这个问题：**把一次性抓取摊开成长期任务**。

【核心设计】
  1. **进度存在数据库里，天然可续跑**
     · 待补粉丝数 = UpUser.follower_count == 0
     · 待抓弹幕   = Video 没有关联 Danmaku
     因此脚本随时可以 Ctrl+C 或被杀掉，下次运行自动从断点继续，
     不需要额外的进度文件。

  2. **遇风控不是失败，而是"等一下再试"**
     manage.py crawl 遇到 -352 会直接退出（对交互式命令是对的）。
     本脚本改为自适应退避：
         命中风控 -> 冷却时间拉长（初始 10 分钟，每次 ×1.5，上限 60 分钟）
         连续成功 -> 冷却时间缓慢回落到基线（每成功 10 次减 60 秒）
     这样既不会硬撞风控，也不会在风控放开后还傻等。

  3. **单请求粒度**
     每次只发一个请求、立刻判断结果，而不是"抓完一整个视频再判断"，
     避免在风控已经触发的情况下把剩余的包也发出去。

【合规声明】
  仍然只访问公开接口、只读、不登录、不绕风控。
  本脚本做的是"降低请求频率"，方向与风控要求一致。

用法：
    # 先补粉丝数（40 位 UP主），再抓弹幕
    python scripts/patient_crawl.py --followers --danmaku

    # 只补粉丝数，最多 20 位
    python scripts/patient_crawl.py --followers --followers-limit 20

    # 自定义节奏：基线间隔 5 秒，风控后首次冷却 20 分钟
    python scripts/patient_crawl.py --followers --interval 5 --cooldown 1200

    # 先看看还有多少活要干（不发任何请求）
    python scripts/patient_crawl.py --status
"""

import argparse
import os
import sys
import time
from pathlib import Path

# ---- 让脚本能独立运行：把 backend 目录加入 sys.path ----
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from django.db import close_old_connections  # noqa: E402

from apps.spider.base import RateLimitedError  # noqa: E402
from apps.spider.bilibili import BiliBiliSpider  # noqa: E402
from apps.spider import parsers  # noqa: E402
from apps.videos.models import Danmaku, UpUser, Video  # noqa: E402

LINE = "=" * 74


def log(message: str) -> None:
    """带时间戳打印。"""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def banner(title: str) -> None:
    """打印分节标题。"""
    print()
    print(LINE)
    print(f"  {title}")
    print(LINE)


class Pacer:
    """请求节奏控制器：负责间隔与风控退避。

    【为什么单独抽一个类】
        节奏策略（基线间隔、退避倍数、上限、成功后的回落）是本脚本的核心逻辑，
        独立出来后可以单独调整与测试，也让主流程读起来只剩"抓什么"。
    """

    def __init__(self, interval: float, cooldown: float, max_cooldown: float):
        """初始化。

        参数:
            interval:     正常情况下的请求间隔（秒）
            cooldown:     首次遇到风控时的冷却时长（秒）
            max_cooldown: 冷却时长上限（秒）
        """
        self.interval = max(1.0, interval)      # 合规下限 1.0 秒，与 BaseSpider 一致
        self.base_cooldown = cooldown
        self.cooldown = cooldown
        self.max_cooldown = max_cooldown
        self.success_streak = 0
        self.last_request_at = 0.0
        self.rate_limit_hits = 0

    def wait_turn(self) -> None:
        """两次请求之间等待基线间隔。"""
        elapsed = time.time() - self.last_request_at
        remaining = self.interval - elapsed
        if self.last_request_at and remaining > 0:
            time.sleep(remaining)

    def mark_request(self) -> None:
        """记录"刚刚发过一次请求"。"""
        self.last_request_at = time.time()

    def on_rate_limited(self) -> None:
        """命中风控：拉长冷却。"""
        self.rate_limit_hits += 1
        self.success_streak = 0
        log(f"  ⚠ 命中风控 -352，冷却 {self.cooldown / 60:.1f} 分钟后重试")
        time.sleep(self.cooldown)
        # 指数退避：下次若再被拦，等更久
        self.cooldown = min(self.cooldown * 1.5, self.max_cooldown)
        # 冷却结束视为一段时间没发请求，重置间隔计时
        self.last_request_at = 0.0

    def on_success(self) -> None:
        """请求成功：每积累 10 次成功，把冷却时间往回收一点。"""
        self.success_streak += 1
        if self.success_streak >= 10:
            self.success_streak = 0
            self.cooldown = max(self.base_cooldown, self.cooldown - 60)
            log(f"  ✓ 已连续成功 10 次，冷却时长回落到 {self.cooldown / 60:.1f} 分钟")


def pending_counts() -> tuple[list[int], list[str]]:
    """返回待处理的 UP主 mid 列表与待抓弹幕的视频 bvid 列表。"""
    mids = list(
        UpUser.objects.filter(follower_count=0)
        .order_by("mid")
        .values_list("mid", flat=True)
    )
    has_danmaku = set(Danmaku.objects.values_list("video_id", flat=True).distinct())
    bvids = list(
        Video.objects.exclude(id__in=has_danmaku)
        .order_by("-danmaku_count")
        .values_list("bvid", flat=True)
    )
    return mids, bvids


def show_status() -> None:
    """打印待办统计（不发请求）。"""
    mids, bvids = pending_counts()
    banner("待办统计")
    print(f"  视频总数            : {Video.objects.count()}")
    print(f"  弹幕总数            : {Danmaku.objects.count()}")
    print(f"  UP主 总数           : {UpUser.objects.count()}")
    print(f"  待补粉丝数的 UP主   : {len(mids)} 位  （约 {len(mids)} 次请求）")
    print(f"  待抓弹幕的视频      : {len(bvids)} 个  （约 {len(bvids) * 2} 次请求）")
    print(f"  合计约需            : {len(mids) + len(bvids) * 2} 次请求")
    print()
    if mids:
        print("  待补粉丝数的 UP主（前 5）：")
        for mid in mids[:5]:
            up = UpUser.objects.filter(mid=mid).first()
            print(f"    {mid}  {up.name if up else ''}")
    print()


def refresh_cids(spider: BiliBiliSpider, pacer: Pacer) -> int:
    """用排行榜接口批量回填 cid。

    返回:
        本次回填成功的视频数

    【为什么要单独做这一步】
        抓弹幕需要 cid。若"每个视频单独请求一次详情"，40 个视频要 40 次请求；
        而"按分区请求排行榜"只要 1 次/分区 —— 排行榜响应里本来就带 cid，
        只是早期版本没有把它存进数据库。

        本次实测涉及 5 个子分区，即 **5 次请求换掉 40 次详情请求**，
        仍然是 8 倍的节省。
    """
    missing = Video.objects.filter(cid__isnull=True).count()
    if missing == 0:
        return 0

    # 【为什么用 bili_tid 而不是分区名】
    #   入库时存的是 B站返回的细分分区名（tname），例如"数码""极客DIY"。
    #   这些子分区名**不在 constants.PARTITIONS 对照表里**，
    #   用名字去查会报"无法识别的分区名"。
    #   而 Partition 表里存了 B站原始 tid，直接拿数字去请求排行榜即可，
    #   run_partition() 本身也接受纯数字字符串。
    #
    # 【为什么从 Video 侧查询】
    #   `Partition.objects.filter(videos__cid__isnull=True)` 实测会带上
    #   一些"一条视频都没有"的分区（JOIN + distinct 的行为不符合直觉），
    #   导致白白多发几次请求。改成从 Video 侧取 distinct 外键，语义明确。
    #
    # 【为什么必须加 .order_by()】
    #   Django 的已知陷阱：模型的 Meta.ordering 字段会被**加进 SELECT**，
    #   于是 `distinct()` 失效 —— 实测这里会返回 40 行（一视频一行）
    #   而不是 5 行（一个分区一行），白白多发 35 次请求。
    #   先 `.order_by()` 清空排序再 distinct 才能得到真正的去重结果。
    tids = list(
        Video.objects.filter(cid__isnull=True, partition__isnull=False)
        .order_by()
        .values_list("partition__bili_tid", "partition__name")
        .distinct()
    )
    if not tids:
        return 0

    banner(f"回填 cid（{missing} 个视频缺 cid，{len(tids)} 个分区各请求 1 次）")

    for i, (tid, pname) in enumerate(tids, start=1):
        pacer.wait_turn()
        pacer.mark_request()
        try:
            stats = spider.run_partition(str(tid), limit=100)
        except RateLimitedError:
            # 【为什么这里不冷却重试，而是直接放弃】
            #   实测发现**不同接口的配额不同**：
            #   /x/relation/stat 连续 40 次全通，
            #   而 /web-interface/ranking/v2 在同一时段持续返回 -352。
            #   排行榜接口明显更敏感，等下去大概率还是被拦。
            #   反正下一步抓弹幕时会回落到详情接口取 cid（那个接口是通的），
            #   所以这里直接放弃、把额度留给真正需要的请求。
            log("  ⚠ 排行榜接口被风控，放弃 cid 回填，改由弹幕步骤逐个取 cid")
            break
        except Exception as exc:  # noqa: BLE001
            log(f"  ✗ [{i}/{len(tids)}] 分区 {pname}(tid={tid}) 回填失败：{exc}")
            continue

        pacer.on_success()
        still = Video.objects.filter(cid__isnull=True).count()
        log(
            f"  ✓ [{i}/{len(tids)}] 分区 {pname}(tid={tid})：解析 {stats.fetched} 条，"
            f"仍缺 cid {still} 个"
        )

    filled = missing - Video.objects.filter(cid__isnull=True).count()
    print()
    log(f"cid 回填完成：{filled}/{missing}")
    return filled


def crawl_followers(spider: BiliBiliSpider, pacer: Pacer, limit: int) -> tuple[int, int]:
    """补抓 UP主 粉丝数。

    返回:
        (成功位数, 失败位数)
    """
    mids = list(
        UpUser.objects.filter(follower_count=0)
        .order_by("mid")
        .values_list("mid", flat=True)
    )
    if limit:
        mids = mids[:limit]

    if not mids:
        banner("UP主 粉丝数：无待补记录")
        return 0, 0

    banner(f"补抓 UP主 粉丝数（{len(mids)} 位，1 位 1 次请求）")
    ok = failed = 0

    for i, mid in enumerate(mids, start=1):
        # 长跑脚本必须每轮回收过期连接：
        # 中途的风控冷却会让数据库连接空闲几分钟，MySQL / 中间设备会把它掐掉，
        # 下一次查询就抛 OperationalError(2013, Lost connection)。
        close_old_connections()
        up = UpUser.objects.filter(mid=mid).first()
        name = up.name if up else str(mid)

        pacer.wait_turn()
        pacer.mark_request()
        try:
            payload = spider.fetch_upuser_stat(mid)
        except RateLimitedError:
            pacer.on_rate_limited()
            # 冷却结束后重试同一位，不推进下标
            try:
                pacer.wait_turn()
                pacer.mark_request()
                payload = spider.fetch_upuser_stat(mid)
            except Exception as exc:  # noqa: BLE001
                log(f"  ✗ [{i}/{len(mids)}] {name} 重试仍失败：{exc}")
                failed += 1
                continue
        except Exception as exc:  # noqa: BLE001
            log(f"  ✗ [{i}/{len(mids)}] {name} 失败：{exc}")
            failed += 1
            continue

        parsed = parsers.parse_upuser_stat(payload)
        if parsed is None:
            log(f"  ✗ [{i}/{len(mids)}] {name} 响应无法解析")
            failed += 1
            continue

        UpUser.objects.filter(mid=mid).update(
            follower_count=parsed["follower_count"]
        )
        ok += 1
        pacer.on_success()
        log(
            f"  ✓ [{i}/{len(mids)}] {name[:16]:<18} "
            f"粉丝 {parsed['follower_count']:>10,}"
        )

    print()
    log(f"UP主 粉丝数完成：成功 {ok} 位，失败 {failed} 位，风控命中 {pacer.rate_limit_hits} 次")
    return ok, failed


def crawl_danmaku(
    spider: BiliBiliSpider, pacer: Pacer, limit: int, max_segments: int
) -> int:
    """抓弹幕。返回新增弹幕总数。"""
    has_danmaku = set(Danmaku.objects.values_list("video_id", flat=True).distinct())
    bvids = list(
        Video.objects.exclude(id__in=has_danmaku)
        .order_by("-danmaku_count")
        .values_list("bvid", flat=True)
    )
    if limit:
        bvids = bvids[:limit]

    if not bvids:
        banner("弹幕：无待抓视频")
        return 0

    banner(f"抓弹幕（{len(bvids)} 个视频，每视频约 2 次请求）")
    collected = 0

    for i, bvid in enumerate(bvids, start=1):
        # 同上：避免长时间抓取（含风控冷却）时 MySQL 断连
        close_old_connections()
        video = Video.objects.filter(bvid=bvid).first()
        if video is None:
            continue

        # ---- 第 1 步：确定 cid ----
        # 优先用库里已存的 cid（排行榜回填过，或上一次运行取到过）。
        # 只有真的没有时才请求详情接口 —— 省下的都是风控额度。
        cid = video.cid
        if not cid:
            pacer.wait_turn()
            pacer.mark_request()
            try:
                detail = spider.fetch_video_detail(bvid)
            except RateLimitedError:
                pacer.on_rate_limited()
                continue
            except Exception as exc:  # noqa: BLE001
                log(f"  ✗ [{i}/{len(bvids)}] {bvid} 取详情失败：{exc}")
                continue

            item = parsers.parse_video_detail(detail)
            if item is None or not item.cid:
                log(f"  ✗ [{i}/{len(bvids)}] {bvid} 未取到 cid")
                continue

            cid = item.cid
            # 立刻落库：即使本次运行随后被中断，
            # 下次也不必再为这个视频重复请求详情接口。
            Video.objects.filter(bvid=bvid).update(cid=cid)

        # ---- 第 2 步：逐包抓弹幕 ----
        added_here = 0
        for segment in range(1, max_segments + 1):
            pacer.wait_turn()
            pacer.mark_request()
            try:
                raw = spider.fetch_danmaku_segment(cid, segment)
            except RateLimitedError:
                pacer.on_rate_limited()
                break
            except Exception as exc:  # noqa: BLE001
                log(f"  ✗ [{i}/{len(bvids)}] {bvid} 第 {segment} 包失败：{exc}")
                break

            items = parsers.parse_danmaku_protobuf(raw)
            if not items:
                # 空包说明后面没有更多弹幕了
                break

            from apps.spider import persistence

            created, _skipped = persistence.upsert_danmaku(video, items)
            added_here += created
            collected += created
            pacer.on_success()

            # 只抓一包：够画出情感曲线即可，把请求留给别的视频
            break

        log(f"  ✓ [{i}/{len(bvids)}] {bvid} 新增 {added_here} 条弹幕")

    print()
    log(f"弹幕完成：新增 {collected} 条，风控命中 {pacer.rate_limit_hits} 次")
    return collected


def main() -> int:
    """脚本入口。"""
    parser = argparse.ArgumentParser(
        description="耐心抓取器：在严格风控下分批补齐 UP主 粉丝数与弹幕",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--followers", action="store_true", help="补抓 UP主 粉丝数")
    parser.add_argument("--danmaku", action="store_true", help="抓取弹幕")
    parser.add_argument("--status", action="store_true", help="只显示待办统计，不发请求")
    parser.add_argument("--followers-limit", type=int, default=0, help="最多补多少位 UP主（0=不限）")
    parser.add_argument("--danmaku-limit", type=int, default=0, help="最多抓多少个视频的弹幕（0=不限）")
    parser.add_argument("--max-segments", type=int, default=1, help="每个视频最多抓几包弹幕（默认 1）")
    parser.add_argument("--interval", type=float, default=3.0, help="正常请求间隔秒数（默认 3.0）")
    parser.add_argument("--cooldown", type=float, default=600, help="首次风控冷却秒数（默认 600 = 10 分钟）")
    parser.add_argument("--max-cooldown", type=float, default=3600, help="冷却上限秒数（默认 3600 = 60 分钟）")
    args = parser.parse_args()

    if args.status or not (args.followers or args.danmaku):
        show_status()
        if not args.status and not (args.followers or args.danmaku):
            print("  未指定任务。可选：--followers / --danmaku / --status")
            print()
        return 0

    banner("BiliInsight 耐心抓取器")
    print(f"  基线间隔   : {args.interval} 秒（合规下限 1.0）")
    print(f"  首次冷却   : {args.cooldown / 60:.1f} 分钟")
    print(f"  冷却上限   : {args.max_cooldown / 60:.1f} 分钟")
    print(f"  任务       : {'粉丝数 ' if args.followers else ''}{'弹幕' if args.danmaku else ''}")
    show_status()

    spider = BiliBiliSpider(interval=1.0)   # 间隔由 Pacer 统一控制
    pacer = Pacer(args.interval, args.cooldown, args.max_cooldown)

    started = time.time()
    try:
        if args.followers:
            crawl_followers(spider, pacer, args.followers_limit)
        if args.danmaku:
            # 先花很少的请求把 cid 补齐，后面的弹幕抓取就能省掉逐个详情请求
            refresh_cids(spider, pacer)
            crawl_danmaku(spider, pacer, args.danmaku_limit, args.max_segments)
    except KeyboardInterrupt:
        log("已手动中断（进度已保存在数据库中，可直接重新运行续跑）")
    finally:
        spider.close()

    elapsed = time.time() - started
    banner("本次运行结束")
    print(f"  耗时        : {elapsed / 60:.1f} 分钟")
    print(f"  风控命中    : {pacer.rate_limit_hits} 次")
    show_status()
    print("  提示：随时可重新运行，会自动从断点继续。")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""把数据集扩充到指定规模（供打包作"初始数据"）。

【为什么需要单独一个脚本】
    做桌面版初始数据时，目标不是"抓一次"，而是"稳稳地抓够 300 条"：

        · 视频    ：1 个分区 = 1 次请求，约 97 条 —— 但排行榜接口风控最严
        · 粉丝数  ：1 位 UP主 = 1 次请求，约 300 次
        · 弹幕    ：1 个视频 = 1 次请求（cid 已存时可复用），约 300 次

    合计六七百次请求，**一次性跑必然中途被限流**。
    manage.py crawl 遇到 -352 会直接退出（对交互式命令是对的），
    所以这里需要一个"被拦了等一会儿再继续、进度存在数据库里"的编排脚本。

【进度存在哪里】
    完全依赖数据库状态，天然可续跑：
        · 待抓视频    = 目标数 - Video.objects.count()
        · 待补粉丝数  = UpUser.follower_count == 0
        · 待抓弹幕    = Video 没有关联 Danmaku

    因此脚本随时可以 Ctrl+C 或被杀掉，下次运行自动从断点继续。

用法：
    # 只抓视频，凑到 300 条
    python scripts/grow_dataset.py --target 300 --partitions 游戏,知识,生活,美食

    # 视频 + 粉丝数 + 每个视频一包弹幕
    python scripts/grow_dataset.py --target 300 --partitions 游戏,知识,生活,美食 \
        --with-followers --with-danmaku

    # 看还差多少（不发请求）
    python scripts/grow_dataset.py --status
"""

import argparse
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
# 复用 patient_crawl 里已经调好的节奏控制器，避免两套退避逻辑各自演化
sys.path.insert(0, str(BASE_DIR / "scripts"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import django  # noqa: E402

django.setup()

from django.db import close_old_connections  # noqa: E402

from apps.spider.base import RateLimitedError  # noqa: E402
from apps.spider.bilibili import BiliBiliSpider  # noqa: E402
from apps.spider.constants import PARTITIONS  # noqa: E402
from apps.videos.models import Danmaku, UpUser, Video  # noqa: E402
from patient_crawl import Pacer, banner, log  # noqa: E402


# ===========================================================================
# 统计
# ===========================================================================
def report(target: int) -> dict:
    """打印并返回当前进度。"""
    total = Video.objects.count()
    no_danmaku = Video.objects.exclude(
        id__in=Danmaku.objects.values("video_id")
    ).count()
    no_follower = UpUser.objects.filter(follower_count=0).count()

    print(f"  视频        : {total} / {target}   （还差 {max(0, target - total)} 条）")
    print(f"  弹幕        : {Danmaku.objects.count()} 条（{no_danmaku} 个视频还没有弹幕）")
    print(f"  UP主        : {UpUser.objects.count()} 位（{no_follower} 位缺粉丝数）")
    print()
    return {
        "videos": total,
        "no_danmaku": no_danmaku,
        "no_follower": no_follower,
    }


# ===========================================================================
# 阶段一：抓视频
# ===========================================================================
def crawl_partitions(
    spider: BiliBiliSpider,
    pacer: Pacer,
    partitions: list,
    target: int,
    limit: int,
) -> int:
    """依次抓分区，直到视频数达到 target。

    返回:
        本次新增的视频数
    """
    added_total = 0

    for name in partitions:
        if Video.objects.count() >= target:
            log(f"已达到目标 {target} 条，停止抓取")
            break

        if name not in PARTITIONS:
            log(f"分区 {name} 不在可抓列表里，跳过")
            continue

        # 同一个分区可能因风控重试多次
        for attempt in range(1, 4):
            pacer.wait_turn()
            pacer.mark_request()
            try:
                stats = spider.run_partition(name, limit=limit)
            except RateLimitedError:
                log(f"  分区 {name} 被风控（第 {attempt} 次），退避后重试")
                pacer.on_rate_limited()
                continue
            except Exception as exc:  # noqa: BLE001
                log(f"  分区 {name} 抓取失败：{exc}")
                break
            else:
                pacer.on_success()
                added_total += stats.created
                log(
                    f"  ✓ 分区 {name}：解析 {stats.fetched} 条，"
                    f"新增 {stats.created} 条（库内共 {Video.objects.count()} 条）"
                )
                break

    return added_total


# ===========================================================================
# 阶段二：补 UP主 粉丝数
# ===========================================================================
def fill_followers(spider: BiliBiliSpider, pacer: Pacer) -> int:
    """逐位补粉丝数（跳过已有值）。"""
    pending = list(
        UpUser.objects.filter(follower_count=0).order_by("mid").values_list("mid", flat=True)
    )
    if not pending:
        log("UP主 粉丝数：无待补记录")
        return 0

    log(f"开始补 {len(pending)} 位 UP主 的粉丝数（1 位 = 1 次请求）")
    from apps.spider import parsers

    done = 0
    for index, mid in enumerate(pending, start=1):
        # 【为什么每轮都要 close_old_connections()】
        #   本脚本会连续跑十几分钟，中途还可能有几分钟的风控冷却。
        #   期间数据库连接长时间空闲，MySQL / 网络中间设备会把它掐掉，
        #   下一次查询就抛：
        #       OperationalError: (2013, 'Lost connection to MySQL server during query')
        #   实测就是在这里崩过一次（跑完 265 位粉丝数、弹幕抓到一半时）。
        #
        #   close_old_connections() 会把已失效的连接标记为不可用并重新建立，
        #   是 Django 官方给长跑脚本的标准做法（Web 请求周期里由框架自动调用）。
        close_old_connections()

        pacer.wait_turn()
        pacer.mark_request()
        try:
            payload = spider.fetch_upuser_stat(mid)
        except RateLimitedError:
            pacer.on_rate_limited()
            # 冷却后重试同一位
            try:
                pacer.wait_turn()
                pacer.mark_request()
                payload = spider.fetch_upuser_stat(mid)
            except Exception as exc:  # noqa: BLE001
                log(f"  ✗ [{index}/{len(pending)}] mid={mid} 重试失败：{exc}")
                continue
        except Exception as exc:  # noqa: BLE001
            log(f"  ✗ [{index}/{len(pending)}] mid={mid} 失败：{exc}")
            continue

        parsed = parsers.parse_upuser_stat(payload)
        if parsed is None:
            continue

        UpUser.objects.filter(mid=mid).update(follower_count=parsed["follower_count"])
        done += 1
        pacer.on_success()

        if index % 20 == 0 or index == len(pending):
            log(f"  [{index}/{len(pending)}] 已补 {done} 位")

    return done


# ===========================================================================
# 阶段三：抓弹幕（每个视频一包）
# ===========================================================================
def fill_danmaku(spider: BiliBiliSpider, pacer: Pacer, limit: int) -> int:
    """为还没有弹幕的视频各抓一包。

    参数:
        limit: 最多处理多少个视频（0 = 不限）
    """
    from apps.spider import parsers, persistence

    has = set(Danmaku.objects.values_list("video_id", flat=True).distinct())
    pending = list(
        Video.objects.exclude(id__in=has).order_by("-danmaku_count").values_list(
            "bvid", flat=True
        )
    )
    if limit:
        pending = pending[:limit]

    if not pending:
        log("弹幕：无待抓视频")
        return 0

    log(f"开始为 {len(pending)} 个视频抓弹幕（每视频约 1 次请求）")
    total_new = 0

    for index, bvid in enumerate(pending, start=1):
        # 每轮回收过期连接，避免长时间抓取时 MySQL 断连（见 fill_followers 的说明）
        close_old_connections()

        video = Video.objects.filter(bvid=bvid).first()
        if video is None:
            continue

        # cid 优先复用（榜单抓取时已存），缺失时才请求详情
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
                log(f"  ✗ [{index}/{len(pending)}] {bvid} 取详情失败：{exc}")
                continue
            item = parsers.parse_video_detail(detail)
            if item is None or not item.cid:
                continue
            cid = item.cid
            Video.objects.filter(bvid=bvid).update(cid=cid)

        pacer.wait_turn()
        pacer.mark_request()
        try:
            raw = spider.fetch_danmaku_segment(cid, 1)
        except RateLimitedError:
            pacer.on_rate_limited()
            continue
        except Exception as exc:  # noqa: BLE001
            log(f"  ✗ [{index}/{len(pending)}] {bvid} 弹幕失败：{exc}")
            continue

        items = parsers.parse_danmaku_protobuf(raw)
        if items:
            created, _skipped = persistence.upsert_danmaku(video, items)
            total_new += created
            pacer.on_success()

        if index % 20 == 0 or index == len(pending):
            log(f"  [{index}/{len(pending)}] 累计新增弹幕 {total_new} 条")

    return total_new


# ===========================================================================
# 入口
# ===========================================================================
def main() -> int:
    """脚本入口。"""
    parser = argparse.ArgumentParser(description="把数据集扩充到目标规模")
    parser.add_argument("--target", type=int, default=300, help="目标视频数（默认 300）")
    parser.add_argument(
        "--partitions",
        type=str,
        default="游戏,知识,生活,美食,动画,音乐,影视,运动",
        help="依次尝试的分区（逗号分隔）",
    )
    parser.add_argument("--limit", type=int, default=100, help="每个分区最多入库条数")
    parser.add_argument("--with-followers", action="store_true", help="补 UP主 粉丝数")
    parser.add_argument("--with-danmaku", action="store_true", help="为无弹幕视频抓弹幕")
    parser.add_argument("--danmaku-limit", type=int, default=0, help="最多为多少个视频抓弹幕（0=不限）")
    parser.add_argument("--interval", type=float, default=3.0, help="请求间隔秒数")
    parser.add_argument("--cooldown", type=float, default=300, help="首次风控冷却秒数")
    parser.add_argument("--max-cooldown", type=float, default=1800, help="冷却上限")
    parser.add_argument("--status", action="store_true", help="只看进度，不发请求")
    args = parser.parse_args()

    banner("数据集扩充")
    print(f"  目标视频数 : {args.target}")
    print(f"  请求间隔   : {args.interval} 秒")
    print(f"  风控冷却   : {args.cooldown / 60:.1f} → {args.max_cooldown / 60:.1f} 分钟")
    print(f"  任务       : 视频"
          + (" + 粉丝数" if args.with_followers else "")
          + (" + 弹幕" if args.with_danmaku else ""))
    print()
    report(args.target)

    if args.status:
        return 0

    spider = BiliBiliSpider(interval=1.0)  # 节奏由 Pacer 控制
    pacer = Pacer(args.interval, args.cooldown, args.max_cooldown)
    started = time.time()

    try:
        partitions = [p.strip() for p in args.partitions.split(",") if p.strip()]

        if Video.objects.count() < args.target:
            banner("阶段一：抓取视频")
            added = crawl_partitions(spider, pacer, partitions, args.target, args.limit)
            log(f"阶段一完成：新增 {added} 条")
        else:
            log("视频数已达标，跳过抓取")

        if args.with_followers:
            banner("阶段二：补 UP主 粉丝数")
            filled = fill_followers(spider, pacer)
            log(f"阶段二完成：补全 {filled} 位")

        if args.with_danmaku:
            banner("阶段三：抓弹幕")
            new_dm = fill_danmaku(spider, pacer, args.danmaku_limit)
            log(f"阶段三完成：新增弹幕 {new_dm} 条")
    except KeyboardInterrupt:
        log("已手动中断（进度已保存，可直接重新运行续跑）")
    finally:
        spider.close()

    # 数据变了：清缓存 + 重建索引
    try:
        from apps.analytics.services import clear_analytics_cache

        log(f"清理分析缓存：{clear_analytics_cache()} 个键")
    except Exception as exc:  # noqa: BLE001
        log(f"清理缓存失败：{exc}")

    try:
        from apps.ai.vector_store import build_index

        result = build_index(rebuild=True)
        log(f"向量索引已重建：{result.get('indexed')} 条")
    except Exception as exc:  # noqa: BLE001
        log(f"重建索引失败：{exc}")

    banner("本次运行结束")
    print(f"  耗时     : {(time.time() - started) / 60:.1f} 分钟")
    print(f"  风控命中 : {pacer.rate_limit_hits} 次")
    print()
    report(args.target)
    print("  提示：随时可重新运行，会自动从断点继续。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

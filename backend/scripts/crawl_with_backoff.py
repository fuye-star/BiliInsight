# -*- coding: utf-8 -*-
"""
带指数退避的真实数据抓取脚本。

【为什么需要这个脚本】
B站风控按"短时间内的请求次数"判定，实测规律是：
    · 冷却后的第 1 次请求通常成功
    · 紧接着的第 2 次就被拦截（返回 code=-352）

因此人工反复重试很容易越试越糟——每一次被拦都会重置冷却计时。
本脚本的做法是：**长时间等待 + 单次尝试 + 失败后指数退避**，
把重试节奏控制在与风控"和解"的范围内。

退避序列（累计约 75 分钟）：
    第 1 次尝试 -> 等 30 分钟
    第 2 次尝试 -> 等 45 分钟
    第 3 次尝试 -> 放弃并报告

用法：
    # 抓科技区 20 条（默认间隔 8 秒）
    python scripts/crawl_with_backoff.py --partition 科技 --limit 20

    # 先等待再尝试（用于风控冷却期内启动）
    python scripts/crawl_with_backoff.py --partition 科技 --limit 20 --initial-wait 1800

    # 多分区（每个分区一次请求，成功后再抓下一个）
    python scripts/crawl_with_backoff.py --partition 科技,数码,游戏 --limit 15
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402

logger = logging.getLogger(__name__)

# 退避序列（秒）：每次失败后等待多久再试
BACKOFF_SEQUENCE = [1800, 2700]

# 命中风控的特征字符串
RATE_LIMIT_MARKERS = ("-352", "风控", "-412", "-509", "-799")


def log(msg: str):
    """带时间戳输出，便于后台任务查看进度。"""
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def is_rate_limited(error_text: str) -> bool:
    """判断错误信息是否为风控限流。"""
    return any(marker in error_text for marker in RATE_LIMIT_MARKERS)


def count_real_videos() -> int:
    """统计当前真实抓取的数据量。"""
    from apps.videos.models import Video

    return Video.objects.filter(is_demo=False).count()


def attempt_crawl(partition: str, limit: int, interval: float) -> tuple[bool, str]:
    """尝试抓取一次。

    返回:
        (是否成功, 错误信息)
    """
    before = count_real_videos()

    try:
        call_command("crawl", partition=partition, limit=limit, interval=interval)
        after = count_real_videos()
        added = after - before

        if added > 0:
            log(f"  ✅ 成功：新增 {added} 条真实数据（累计 {after} 条）")
            return True, ""

        # 命令正常结束但没新增，说明视频已存在（幂等更新）
        log(f"  ✅ 成功：无新增（数据已存在，累计 {after} 条真实数据）")
        return True, ""

    except CommandError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main():
    parser = argparse.ArgumentParser(description="带指数退避的真实数据抓取")
    parser.add_argument(
        "--partition", "-p", default="科技",
        help="分区名，多个用逗号分隔，默认 科技",
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=20,
        help="每个分区抓取条数，默认 20",
    )
    parser.add_argument(
        "--interval", type=float, default=8.0,
        help="请求间隔秒数，默认 8.0（比默认的 2.0 更保守，降低风控概率）",
    )
    parser.add_argument(
        "--initial-wait", type=int, default=0,
        help="开始前先等待多少秒（用于风控冷却期内启动），默认 0",
    )
    parser.add_argument(
        "--max-attempts", type=int, default=3,
        help="最多尝试次数，默认 3",
    )
    args = parser.parse_args()

    partitions = [p.strip() for p in args.partition.split(",") if p.strip()]

    log("=" * 62)
    log("  BiliInsight 真实数据抓取（带指数退避）")
    log("=" * 62)
    log(f"  目标分区 : {', '.join(partitions)}")
    log(f"  每区条数 : {args.limit}")
    log(f"  请求间隔 : {args.interval} 秒")
    log(f"  起始真实 : {count_real_videos()} 条")
    log("")

    # ---- 起始等待 ----
    if args.initial_wait > 0:
        log(f"先等待 {args.initial_wait} 秒（{args.initial_wait / 60:.0f} 分钟）让风控冷却…")
        for remaining in range(args.initial_wait, 0, -60):
            log(f"  剩余约 {remaining // 60} 分钟")
            time.sleep(min(60, remaining))
        log("等待结束，开始尝试")
        log("")

    # ---- 逐分区抓取 ----
    # 【为什么按分区逐个来而不是一次抓多个】
    # 每次请求都可能触发风控；分开做可以在"第一个分区成功"后
    # 立即拿到真实数据，而不是"因为第二个分区失败导致整体回滚"。
    succeeded: list[str] = []
    failed: list[str] = []

    for partition in partitions:
        log(f"--- 抓取分区：{partition} ---")

        ok = False
        for attempt in range(1, args.max_attempts + 1):
            log(f"  第 {attempt}/{args.max_attempts} 次尝试…")

            success, error = attempt_crawl(partition, args.limit, args.interval)

            if success:
                succeeded.append(partition)
                ok = True
                break

            if is_rate_limited(error):
                if attempt <= len(BACKOFF_SEQUENCE):
                    wait = BACKOFF_SEQUENCE[attempt - 1]
                    log(f"  命中风控，等待 {wait // 60} 分钟后重试")
                    log(f"  （风控按请求次数累积，立即重试只会延长封禁）")
                    time.sleep(wait)
                else:
                    log(f"  ❌ 风控未解除，放弃分区 {partition}")
            else:
                log(f"  ❌ 非风控错误，不再重试：{error[:120]}")
                break

        if not ok:
            failed.append(partition)

        # 分区之间留足间隔，避免连续请求触发风控
        if partition != partitions[-1]:
            log("  分区间隔 30 秒…")
            time.sleep(30)

    # ---- 汇总 ----
    log("")
    log("=" * 62)
    log("  抓取汇总")
    log("=" * 62)
    log(f"  成功分区 : {', '.join(succeeded) if succeeded else '无'}")
    if failed:
        log(f"  失败分区 : {', '.join(failed)}")
    log(f"  真实数据 : {count_real_videos()} 条")

    if succeeded:
        log("")
        log("  ✅ 已获得真实数据！接下来请重建向量索引让 AI 助手能检索到新数据：")
        log("     python manage.py build_index --rebuild")
        return 0

    log("")
    log("  ⚠️ 未获取到真实数据。建议：")
    log("     1. 等待 1-2 小时后再试（风控封禁时间会累积）")
    log("     2. 换网络环境（风控按出口 IP 统计，如手机热点）")
    log("     3. 继续使用模拟数据演示——功能完全等价，只是 BV 号不可验证")
    return 1


if __name__ == "__main__":
    sys.exit(main())

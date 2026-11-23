# -*- coding: utf-8 -*-
"""
演示数据质量校验脚本。

【为什么需要单独校验】
seed_demo 生成的是"模拟数据"，如果分布不合理（例如互动率全是 0.0001，
或播放量全挤在同一个数量级），后端的榜单排序、趋势图就失去意义。
本脚本用统计量验证生成的这批数据是否"看起来像真的"。

运行：
    python scripts/verify_demo_data.py
"""

import os
import sys
from pathlib import Path

import django

# 【为什么必须手动加 sys.path】
# 本脚本位于 backend/scripts/ 下，直接执行时 Python 的模块搜索路径
# 只包含 scripts/ 目录，找不到 config 与 apps 包，
# 会报 ModuleNotFoundError: No module named 'config'。
# manage.py 之所以没这个问题，是因为它就在 backend/ 根目录下。
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.db.models import Avg, Count, Max, Min, Sum   # noqa: E402

from apps.videos.models import Danmaku, Partition, UpUser, Video  # noqa: E402


def line(title=""):
    """打印分隔线。"""
    if title:
        print(f"\n{'=' * 62}\n  {title}\n{'=' * 62}")
    else:
        print("=" * 62)


def main():
    line("BiliInsight 演示数据质量校验")

    # -----------------------------------------------------------------
    # 1. 数据总量
    # -----------------------------------------------------------------
    line("1. 数据总量")
    counts = {
        "分区": Partition.objects.count(),
        "UP主": UpUser.objects.count(),
        "视频": Video.objects.count(),
        "弹幕": Danmaku.objects.count(),
    }
    for name, n in counts.items():
        print(f"  {name:<6}: {n}")

    if counts["视频"] == 0:
        print("\n  [X] 没有视频数据，请先运行：python manage.py seed_demo")
        return 1

    # -----------------------------------------------------------------
    # 2. 互动数据分布（验证幂律分布是否生效）
    # -----------------------------------------------------------------
    line("2. 视频互动数据分布")
    agg = Video.objects.aggregate(
        v_min=Min("view_count"), v_max=Max("view_count"), v_avg=Avg("view_count"),
        v_sum=Sum("view_count"),
        r_min=Min("interaction_rate"), r_max=Max("interaction_rate"),
        r_avg=Avg("interaction_rate"),
    )
    print(f"  播放量  最小 {agg['v_min']:>12,}   最大 {agg['v_max']:>12,}")
    print(f"          平均 {agg['v_avg']:>12,.0f}   总计 {agg['v_sum']:>14,}")
    print(f"  互动率  最小 {agg['r_min']:.4f}       最大 {agg['r_max']:.4f}")
    print(f"          平均 {agg['r_avg']:.4f}")

    # 互动率应落在合理区间（真实B站约 2%-15%）
    if 0.01 <= agg["r_avg"] <= 0.20:
        print("  [OK] 平均互动率在合理区间（1%-20%）")
    else:
        print(f"  [!] 平均互动率 {agg['r_avg']:.4f} 偏离常见区间，建议检查派生比例")

    # 播放量应有明显长尾（最大值远大于平均值）
    if agg["v_max"] > agg["v_avg"] * 10:
        print("  [OK] 播放量呈长尾分布（最大值 > 平均值×10）")
    else:
        print("  [!] 播放量分布过于集中，榜单区分度可能不足")

    # -----------------------------------------------------------------
    # 3. 分区分布
    # -----------------------------------------------------------------
    line("3. 分区分布")
    rows = (
        Partition.objects.annotate(n=Count("videos"))
        .order_by("-n")
        .values_list("name", "n", "bili_tid", "color")
    )
    total_videos = counts["视频"] or 1
    for name, n, tid, color in rows:
        pct = n / total_videos * 100
        bar = "█" * int(pct / 2)
        print(f"  {name:<4} tid={tid:<4} {n:>4} 条 {pct:5.1f}%  {bar}")

    # -----------------------------------------------------------------
    # 4. 弹幕情感分布
    # -----------------------------------------------------------------
    line("4. 弹幕情感分布")
    label_map = {"positive": "正向", "neutral": "中性", "negative": "负向"}
    dist = (
        Danmaku.objects.exclude(sentiment_label="")
        .values("sentiment_label")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    total_dm = counts["弹幕"] or 1
    for row in dist:
        label = label_map.get(row["sentiment_label"], row["sentiment_label"])
        pct = row["n"] / total_dm * 100
        bar = "█" * int(pct / 2)
        print(f"  {label}  {row['n']:>5} 条  {pct:5.1f}%  {bar}")

    # -----------------------------------------------------------------
    # 5. 外键关联完整性
    # -----------------------------------------------------------------
    line("5. 关联完整性")
    orphan_danmaku = Danmaku.objects.filter(video__isnull=True).count()
    orphan_video = Video.objects.filter(upuser__isnull=True).count()
    print(f"  无归属的弹幕 : {orphan_danmaku}")
    print(f"  无 UP主 的视频: {orphan_video}")
    if orphan_danmaku == 0 and orphan_video == 0:
        print("  [OK] 外键关联完整")
    else:
        print("  [!] 存在孤儿记录，需检查生成逻辑")

    # -----------------------------------------------------------------
    # 6. 数据抽样（人工核对是否"像真的"）
    # -----------------------------------------------------------------
    line("6. 视频抽样（按播放量 Top 5）")
    for v in Video.objects.select_related("partition", "upuser").order_by("-view_count")[:5]:
        print(f"  {v.bvid}  {v.title[:26]:<28}")
        print(f"      分区={v.partition.name if v.partition else '-':<4} "
              f"UP={v.upuser.name if v.upuser else '-':<12} "
              f"播放={v.view_count:>10,}  互动率={v.interaction_rate:.4f}")

    line("7. 弹幕抽样（各情感一条）")
    for label in ("positive", "neutral", "negative"):
        dm = Danmaku.objects.filter(sentiment_label=label).select_related("video").first()
        if dm:
            print(f"  [{label:<8}] {dm.content[:24]:<26} "
                  f"分值={dm.sentiment_score:.2f}  情绪={dm.emotion_tags}  "
                  f"视频={dm.video.bvid}")

    # -----------------------------------------------------------------
    # 8. 结论
    # -----------------------------------------------------------------
    line("校验结论")
    ok = (
        counts["视频"] > 0
        and counts["弹幕"] > 0
        and orphan_danmaku == 0
        and orphan_video == 0
        and 0.01 <= agg["r_avg"] <= 0.20
    )
    if ok:
        print("  数据可用于前端开发与阶段三接口联调 ✅")
    else:
        print("  存在需要修正的问题，详见上方 [!] 标记 ⚠️")
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

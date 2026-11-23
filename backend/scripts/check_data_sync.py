# -*- coding: utf-8 -*-
"""数据同步诊断脚本。

【为什么需要它】
    抓完真实数据后，看板上的「UP主排行 / 情感分析 / 数据总览」看起来没变化。
    但"看起来没变"有两种完全不同的原因，必须区分开：

        A. 接口有 Bug 或缓存没清 —— 这是缺陷，要修
        B. 新抓的数据里根本不含这些字段 —— 这是数据源能力边界，不是 Bug

    例如：B站排行榜接口【不返回 UP主粉丝数】，
    那么新入库的 UP主 follower_count 就是 0，
    按粉丝数排行自然排不上去 —— 这不是接口没同步，而是没有可排序的值。

    本脚本把"接口返回"和"数据库底表"并排打印，一眼就能判断属于哪种。

用法：
    python scripts/check_data_sync.py
"""

import json
import os
import sys
from pathlib import Path

import django

# ---- 让脚本能独立运行：把 backend 目录加入 sys.path ----
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

import requests  # noqa: E402

from apps.videos.models import Danmaku, UpUser, Video  # noqa: E402

API = "http://127.0.0.1:8000/api"
LINE = "=" * 78


def title(text: str) -> None:
    """打印分节标题。"""
    print()
    print(LINE)
    print(f"  {text}")
    print(LINE)


def call(path: str) -> dict:
    """调用接口，失败时返回带 error 的字典而不抛异常。"""
    try:
        resp = requests.get(f"{API}{path}", timeout=30)
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# =====================================================================
# 1. 底层数据：真实/模拟 各自持有多少"可用于分析"的内容
# =====================================================================
title("1. 底层数据分布（真实 vs 模拟）")

real_ids = list(Video.objects.filter(is_demo=False).values_list("id", flat=True))
demo_ids = list(Video.objects.filter(is_demo=True).values_list("id", flat=True))

print(f"  视频        : 真实 {len(real_ids):>4} 条 | 模拟 {len(demo_ids):>4} 条")
print(f"  UP主        : 总计 {UpUser.objects.count()} 位")
print(f"  弹幕        : 总计 {Danmaku.objects.count()} 条")

# 弹幕归属——情感分析完全依赖这张表
real_dm = Danmaku.objects.filter(video_id__in=real_ids).count()
demo_dm = Danmaku.objects.filter(video_id__in=demo_ids).count()
print(f"    ├ 属于真实视频 : {real_dm:>5} 条")
print(f"    └ 属于模拟视频 : {demo_dm:>5} 条")

# 情感标注覆盖
sent_total = Danmaku.objects.exclude(sentiment_label="").count()
sent_real = Danmaku.objects.filter(video_id__in=real_ids).exclude(sentiment_label="").count()
sent_demo = Danmaku.objects.filter(video_id__in=demo_ids).exclude(sentiment_label="").count()
print(f"  已标注情感的弹幕 : {sent_total} 条")
print(f"    ├ 来自真实视频 : {sent_real:>5} 条")
print(f"    └ 来自模拟视频 : {sent_demo:>5} 条")

# =====================================================================
# 2. UP主：粉丝数是否有值（决定排行榜能否体现新数据）
# =====================================================================
title("2. UP主粉丝数覆盖率（决定「UP主排行」是否有新面孔）")

with_followers = UpUser.objects.filter(follower_count__gt=0).count()
zero_followers = UpUser.objects.filter(follower_count=0).count()
print(f"  粉丝数 > 0 的 UP主 : {with_followers} 位")
print(f"  粉丝数 = 0 的 UP主 : {zero_followers} 位")

# 真实视频的 UP主里，有多少拿到了粉丝数
real_up_ids = set(
    Video.objects.filter(is_demo=False)
    .exclude(upuser__isnull=True)
    .values_list("upuser_id", flat=True)
)
real_up_with = UpUser.objects.filter(id__in=real_up_ids, follower_count__gt=0).count()
print()
print(f"  真实视频涉及 UP主 : {len(real_up_ids)} 位")
print(f"    其中粉丝数 > 0  : {real_up_with} 位")
print(f"    其中粉丝数 = 0  : {len(real_up_ids) - real_up_with} 位")

print()
print("  TOP 5 真实 UP主（按粉丝数）：")
for up in UpUser.objects.filter(id__in=real_up_ids).order_by("-follower_count")[:5]:
    print(f"    {up.name[:18]:<20} 粉丝 {up.follower_count:>10,}  mid={up.mid}")

# =====================================================================
# 3. 接口实测
# =====================================================================
title("3. 接口返回对比")

# --- 3.1 数据总览 ---
ov = call("/analytics/overview/")
d = ov.get("data", {})
print("  【数据总览】/api/analytics/overview/")
if "error" in ov:
    print(f"    ✗ {ov['error']}")
else:
    for key in ("video_count", "upuser_count", "partition_count",
                "danmaku_count", "total_view", "avg_interaction_rate"):
        print(f"    {key:<22} = {d.get(key)}")

# --- 3.2 UP主排行 ---
print()
print("  【UP主排行】/api/analytics/top-upusers/?order_by=follower_count")
tu = call("/analytics/top-upusers/?order_by=follower_count&limit=5")
items = (tu.get("data") or {}).get("items") or []
if not items:
    print(f"    (空) 原始返回：{json.dumps(tu, ensure_ascii=False)[:200]}")
for it in items:
    print(f"    {str(it.get('name'))[:16]:<18} 粉丝 {it.get('follower_count'):>10,}"
          f"  视频 {it.get('video_count')}")

print()
print("  【UP主排行·按视频数】/api/analytics/top-upusers/?order_by=video_count")
tu2 = call("/analytics/top-upusers/?order_by=video_count&limit=5")
for it in ((tu2.get("data") or {}).get("items") or []):
    print(f"    {str(it.get('name'))[:16]:<18} 视频 {it.get('video_count'):>4}"
          f"  粉丝 {it.get('follower_count'):>10,}")

# --- 3.3 情感分析 ---
print()
print("  【情感分析】/api/analytics/sentiment/")
se = call("/analytics/sentiment/")
sd = se.get("data", {})
if "error" in se:
    print(f"    ✗ {se['error']}")
else:
    print(f"    变量名(backends) = {sd.get('backend') or sd.get('engine')}")
    dist = sd.get("distribution") or sd.get("items") or []
    if isinstance(dist, list):
        for row in dist[:6]:
            print(f"    {json.dumps(row, ensure_ascii=False)}")
    else:
        print(f"    {json.dumps(dist, ensure_ascii=False)[:300]}")
    for key in ("total", "total_danmaku", "analyzed", "avg_score"):
        if key in sd:
            print(f"    {key:<16} = {sd.get(key)}")

print()
print(LINE)
print("  结论提示：")
print("    · 若「粉丝数 = 0」的 UP主占比很高 -> UP主排行无新面孔属【数据源能力边界】")
print("    · 若「属于真实视频的弹幕 = 0」   -> 情感分析全部来自模拟数据，属【数据源能力边界】")
print("    · 若接口返回值与底表不一致        -> 才是【缓存或接口 Bug】，需要修")
print(LINE)

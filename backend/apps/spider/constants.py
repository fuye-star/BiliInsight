# -*- coding: utf-8 -*-
"""
爬虫公共常量与数据实体。

【本模块的定位】
把"常量表"与"数据结构"从爬虫逻辑中抽离出来，好处有三：
  1. 分区表、接口地址集中维护，改一处即可全局生效
  2. 数据实体（dataclass）与 HTTP/数据库解耦，便于单元测试
  3. 解析函数只接受 dict/bytes、只返回实体，不碰网络，可离线测试
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ===========================================================================
# B站接口地址
# ===========================================================================
class BiliAPI:
    """B站 Web 接口地址与固定参数。

    【合规提示】
    以下均为公开的 Web 接口，仅在遵守 robots.txt、控制请求频率、
    注明学习研究用途的前提下使用。
    """

    # 站点主域
    BASE_URL = "https://api.bilibili.com"

    # 分区排行榜：返回该分区近期约 100 个稿件（含完整互动数据）
    # 文档：https://github.com/SocialSisterYi/bilibili-API-collect
    RANKING = f"{BASE_URL}/x/web-interface/ranking/v2"

    # 综合热门榜（不传 rid 即为全站热门）
    POPULAR = f"{BASE_URL}/x/web-interface/popular"

    # 视频详细信息（含 cid，抓弹幕前需要）
    VIDEO_INFO = f"{BASE_URL}/x/web-interface/view"

    # UP主 关系统计（含粉丝数）
    # 【为什么必须单独请求】
    #   排行榜接口的 owner 字段只有 mid / name / face，
    #   **不返回粉丝数**。要让「UP主排行」按粉丝数排得动，
    #   就必须对每位 UP主 单独调一次本接口（1 位 1 次请求）。
    #   因此抓取时需要按 mid 去重，避免重复请求同一位 UP主。
    RELATION_STAT = f"{BASE_URL}/x/relation/stat"

    # 弹幕分段接口（protobuf 格式，每包覆盖 6 分钟）
    DANMAKU_SEG = f"{BASE_URL}/x/v2/dm/web/seg.so"

    # 弹幕分段对应的秒数（B站固定以 6 分钟分包）
    DANMAKU_SEGMENT_SECONDS = 360

    # 单包弹幕数量上限（超出需读取下一包）
    DANMAKU_MAX_PER_SEGMENT = 6000


# ===========================================================================
# 分区表
# ===========================================================================
# B站一级分区 tid 对照。仅收录本项目关注的分区，
# 需要扩充时在此追加即可（爬虫与管理命令都从这里读取）。
PARTITIONS: dict[str, int] = {
    "动画": 1,
    "音乐": 3,
    "游戏": 4,
    "知识": 36,
    "科技": 188,
    "运动": 234,
    "影视": 181,
    "生活": 160,
    "美食": 211,
    "动物": 217,
    "鬼畜": 119,
    "时尚": 155,
    "娱乐": 5,
    "舞蹈": 129,
    "数码": 95,
}

# 默认抓取的分区（答辩演示与定时任务用这几个，覆盖不同内容类型）
DEFAULT_PARTITIONS = ["科技", "数码", "游戏", "知识", "生活"]


def partition_tid(name: str) -> Optional[int]:
    """把分区名转换为 tid。

    参数:
        name: 分区名，如 "科技"；也接受纯数字字符串（直接当 tid 用）

    返回:
        tid 整数；无法识别时返回 None
    """
    if not name:
        return None
    name = name.strip()
    # 允许直接传数字 tid
    if name.isdigit():
        return int(name)
    # 允许带"区"后缀，如 "科技区"
    if name.endswith("区"):
        name = name[:-1]
    return PARTITIONS.get(name)


# ===========================================================================
# 数据实体
# ===========================================================================
# 说明：这些 dataclass 是"解析层"与"入库层"之间的契约。
# 解析函数产出实体，入库函数消费实体，双方都不关心对方细节。


@dataclass
class VideoItem:
    """一个视频的结构化数据。"""

    bvid: str
    aid: Optional[int] = None
    title: str = ""
    description: str = ""
    cover_url: str = ""
    duration: int = 0                 # 秒
    pubdate: Optional[datetime] = None

    # 分区
    tid: Optional[int] = None
    tname: str = ""

    # UP主
    up_mid: Optional[int] = None
    up_name: str = ""
    up_avatar: str = ""

    # 互动数据
    view_count: int = 0
    like_count: int = 0
    coin_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    danmaku_count: int = 0
    reply_count: int = 0

    # 标签（B站排行榜接口不返回 tags，需要时单独请求）
    tags: str = ""

    # cid：抓弹幕必需，排行榜接口会返回
    cid: Optional[int] = None

    def to_dict(self) -> dict:
        """转为普通字典，便于日志打印或 JSON 序列化。"""
        return asdict(self)


@dataclass
class DanmakuItem:
    """一条弹幕的结构化数据。"""

    dmid: Optional[int] = None
    content: str = ""
    video_time: float = 0.0           # 出现在视频第几秒
    send_time: Optional[datetime] = None
    mode: int = 1                     # 弹幕类型（1-3 普通，4 底部，5 顶部）
    color: int = 16777215             # 十进制 RGB
    pool: int = 0

    def to_dict(self) -> dict:
        """转为普通字典。"""
        return asdict(self)


# ===========================================================================
# 时间转换工具
# ===========================================================================
def ts_to_datetime(ts) -> Optional[datetime]:
    """把 Unix 时间戳转为 Django 可用的 aware datetime。

    【为什么必须带时区】
    settings 中 USE_TZ=True，Django 要求存入数据库的 datetime 必须
    是 aware（带 tzinfo）的对象，否则会抛 RuntimeWarning 并按 UTC 处理，
    导致时间显示偏移 8 小时（东八区问题）。

    参数:
        ts: Unix 秒级时间戳；None 或非法值返回 None

    返回:
        带 UTC 时区的 datetime，或 None
    """
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return None

    # B站偶发返回 0 表示"无时间"，按 None 处理更符合语义
    if value <= 0:
        return None

    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def safe_int(value, default: int = 0) -> int:
    """把接口返回值安全地转成 int。

    接口中数字字段偶尔会是 "--"、"" 或 null，直接 int() 会抛异常，
    这里统一兜底为 default。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

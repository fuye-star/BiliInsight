# -*- coding: utf-8 -*-
"""
响应解析器 —— 纯函数，不涉及网络与数据库。

【为什么解析逻辑必须独立成模块】
  1. **可离线测试**：解析是本项目最易出错的环节（接口字段变动、编码问题），
     独立后可以用固定样本（fixture）做单元测试，不必真的联网抓数据。
  2. **职责单一**：BiliBiliSpider 只负责"取回原始数据"，本模块只负责
     "把原始数据变成结构化实体"，任何一方出问题都能快速定位。
  3. **便于适配接口变更**：B站接口字段一旦调整，只需改这里，爬虫主体不动。

【弹幕格式的选择说明】
B站弹幕接口返回的是 protobuf 二进制。常见做法有两种：
  A. 引入 .proto 文件并用 protoc 编译成 _pb2.py
  B. 手写 wire-format 解析器（本模块采用）

选择 B 的理由：
  · 无需安装 protoc、无需维护 .proto 文件与编译产物，答辩现场零风险；
  · 我们只关心十来个字段，而 protobuf 的 wire format 本身很简单
    （varint + length-delimited 两种类型即可覆盖弹幕的全部字段）；
  · 纯 Python 实现，可完全离线单元测试；
  · 不依赖 google.protobuf 的版本（当前它只是 chromadb 的间接依赖，
    不希望业务代码直接耦合到这种"偶然存在"的包上）。

若将来需要解析 B站更复杂的嵌套 protobuf，再切换到 A 方案即可，
只需替换 parse_danmaku_protobuf() 一个函数。
"""

import gzip
import logging
import zlib
from typing import Optional

from .constants import DanmakuItem, VideoItem, safe_int, ts_to_datetime

logger = logging.getLogger(__name__)


# ===========================================================================
# 视频列表解析
# ===========================================================================
def parse_video_list(payload: dict) -> list[VideoItem]:
    """解析分区排行榜 / 热门榜接口的响应。

    对应接口：
        GET /x/web-interface/ranking/v2?rid={tid}
        GET /x/web-interface/popular

    响应结构：
        {"code": 0, "data": {"list": [ {...}, {...} ]}}

    参数:
        payload: 接口返回的完整 JSON（dict）

    返回:
        VideoItem 列表。字段缺失的条目会被跳过并计入日志，
        不会因单条异常导致整批失败。
    """
    items: list[VideoItem] = []

    # 防御性取数：任何一层不符合预期都返回空列表，交由上层判定
    data = payload.get("data") or {}
    raw_list = data.get("list") or []

    if not isinstance(raw_list, list):
        logger.warning("解析视频列表失败：data.list 不是列表，实际类型 %s", type(raw_list))
        return items

    for raw in raw_list:
        try:
            item = _parse_single_video(raw)
            if item is not None:
                items.append(item)
        except Exception as exc:
            # 单条解析失败不影响整批，记录后继续
            logger.warning("跳过一条无法解析的视频数据：%s（原始数据键：%s）",
                           exc, list(raw.keys())[:8] if isinstance(raw, dict) else type(raw))
            continue

    logger.info("视频列表解析完成，成功 %d 条 / 原始 %d 条", len(items), len(raw_list))
    return items


def _parse_single_video(raw: dict) -> Optional[VideoItem]:
    """解析单个视频对象。

    参数:
        raw: 接口 list 中的一项

    返回:
        VideoItem；缺少关键字段（bvid）时返回 None
    """
    if not isinstance(raw, dict):
        return None

    bvid = (raw.get("bvid") or "").strip()
    if not bvid:
        # bvid 是入库的唯一键，缺失则该条无意义
        return None

    owner = raw.get("owner") or {}
    stat = raw.get("stat") or {}

    return VideoItem(
        bvid=bvid,
        aid=safe_int(raw.get("aid")) or None,
        title=(raw.get("title") or "").strip(),
        description=(raw.get("desc") or "").strip(),
        # 接口返回的封面是 http，换成 https 避免前端混合内容告警
        cover_url=(raw.get("pic") or "").replace("http://", "https://"),
        duration=safe_int(raw.get("duration")),
        pubdate=ts_to_datetime(raw.get("pubdate")),
        cid=safe_int(raw.get("cid")) or None,
        tid=safe_int(raw.get("tid")) or None,
        tname=(raw.get("tname") or "").strip(),
        up_mid=safe_int(owner.get("mid")) or None,
        up_name=(owner.get("name") or "").strip(),
        up_avatar=(owner.get("face") or "").replace("http://", "https://"),
        # 互动数据全部来自 stat 子对象
        view_count=safe_int(stat.get("view")),
        like_count=safe_int(stat.get("like")),
        coin_count=safe_int(stat.get("coin")),
        favorite_count=safe_int(stat.get("favorite")),
        share_count=safe_int(stat.get("share")),
        danmaku_count=safe_int(stat.get("danmaku")),
        reply_count=safe_int(stat.get("reply")),
    )


def parse_video_detail(payload: dict) -> Optional[VideoItem]:
    """解析视频详情接口的响应。

    对应接口：GET /x/web-interface/view?bvid={bvid}

    与排行榜的区别：详情接口的 data 直接就是视频对象（不是 list），
    且额外返回 tags 字段。

    参数:
        payload: 接口返回的完整 JSON

    返回:
        VideoItem；解析失败返回 None
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("解析视频详情失败：data 不是对象")
        return None

    item = _parse_single_video(data)
    if item is None:
        return None

    # 详情接口的标签是列表，转成逗号分隔字符串存入 CharField
    tags = data.get("tags") or []
    if isinstance(tags, list):
        names = [
            (t.get("tag_name") or "").strip()
            for t in tags
            if isinstance(t, dict)
        ]
        item.tags = ",".join(n for n in names if n)

    return item


# ===========================================================================
# UP主 关系统计解析
# ===========================================================================
def parse_upuser_stat(payload: dict) -> Optional[dict]:
    """解析 UP主 关系统计接口的响应，取出粉丝数。

    对应接口：GET /x/relation/stat?vmid={mid}

    响应结构：
        {
          "code": 0,
          "data": {"mid": 946974, "following": 293, "follower": 1086893}
        }

    【为什么单独做这个解析函数】
        排行榜接口的 owner 只有 mid / name / face，**没有粉丝数**。
        因此"UP主排行"要按粉丝数排序，就必须逐个 UP主 单独请求本接口。
        解析逻辑独立出来，可以用固定样本离线测试字段映射，
        避免线上才发现 B站把 follower 改名（历史上用过 fans / follower 两种）。

    参数:
        payload: 接口返回的完整 JSON

    返回:
        {"mid": int, "follower_count": int, "following": int}；
        解析失败返回 None

    说明：粉丝数兜底兼容 `follower` 与 `fans` 两种字段名 ——
    B站不同接口对同一含义用过不同命名，这里做一次兼容可以少一次线上故障。
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("解析 UP主 统计失败：data 不是对象")
        return None

    follower = data.get("follower")
    if follower is None:
        # 兼容旧版 / 其他接口的字段名
        follower = data.get("fans")

    if follower is None:
        logger.warning("解析 UP主 统计失败：响应中没有 follower / fans 字段")
        return None

    return {
        "mid": safe_int(data.get("mid")) or 0,
        "follower_count": safe_int(follower),
        "following": safe_int(data.get("following")),
    }


# ===========================================================================
# 弹幕 protobuf 解析
# ===========================================================================
# ---------------------------------------------------------------------------
# protobuf wire format 速查（本模块只用得到两种）
# ---------------------------------------------------------------------------
# 每个字段的编码都是：  [tag][payload]
#   tag = (field_number << 3) | wire_type
#
# wire_type 取值：
#   0 = VARINT          —— 用于 int32/int64/uint32/uint64
#   1 = I64              —— 固定 8 字节（double 等）
#   2 = LEN              —— 长度前缀，用于 string / bytes / 嵌套 message
#   5 = I32              —— 固定 4 字节（float 等）
#
# DanmakuElem 的字段编号（来自 B站官方 dm.proto）：
#   1  id(int64)        2  progress(int32)   3  mode(int32)
#   4  fontsize(int32)  5  color(uint32)     6  midHash(string)
#   7  content(string)  8  ctime(int64)      9  weight(int32)
#   10 action(string)   11 pool(int32)       12 idStr(string)
#   13 attr(int32)
# ---------------------------------------------------------------------------

# 弹幕条目（DanmakuElem）中我们关心的字段编号
_DM_FIELD_ID = 1
_DM_FIELD_PROGRESS = 2
_DM_FIELD_MODE = 3
_DM_FIELD_COLOR = 5
_DM_FIELD_CONTENT = 7
_DM_FIELD_CTIME = 8
_DM_FIELD_POOL = 11

# 外层消息（DmSegMobileReply）中 elems 的字段编号
_SEG_FIELD_ELEMS = 1


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """从 buf 的 pos 处读取一个 varint。

    varint 编码：每字节低 7 位是数据，最高位表示"是否还有后续字节"。

    返回:
        (数值, 新位置)

    异常:
        ValueError: 数据截断或 varint 超过 10 字节（非法）
    """
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("varint 数据截断")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
        if shift > 63:
            raise ValueError("varint 长度非法（超过 64 位）")
    return result, pos


def _iter_fields(buf: bytes):
    """按顺序遍历 protobuf 消息中的所有字段。

    逐个产出 (field_number, wire_type, value)：
      · wire_type 0 -> value 为 int
      · wire_type 1 -> value 为 8 字节 bytes
      · wire_type 2 -> value 为 bytes（字符串或嵌套消息）
      · wire_type 5 -> value 为 4 字节 bytes
    其余类型（3/4 已废弃的 group）直接跳过，保证解析不中断。

    本函数是生成器，遇到损坏数据时抛出 ValueError 由调用方处理。
    """
    pos = 0
    length = len(buf)

    while pos < length:
        # 读取 tag
        tag, pos = _read_varint(buf, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:  # VARINT
            value, pos = _read_varint(buf, pos)
            yield field_number, wire_type, value

        elif wire_type == 1:  # I64
            if pos + 8 > length:
                raise ValueError("I64 字段数据截断")
            yield field_number, wire_type, buf[pos:pos + 8]
            pos += 8

        elif wire_type == 2:  # LEN
            size, pos = _read_varint(buf, pos)
            if pos + size > length:
                raise ValueError("LEN 字段长度超出数据范围")
            yield field_number, wire_type, buf[pos:pos + size]
            pos += size

        elif wire_type == 5:  # I32
            if pos + 4 > length:
                raise ValueError("I32 字段数据截断")
            yield field_number, wire_type, buf[pos:pos + 4]
            pos += 4

        else:
            # 未知类型无法推断长度，继续解析必然错位，直接终止
            raise ValueError(f"不支持的 wire_type={wire_type}")


def _decode_text(raw: bytes) -> str:
    """把 bytes 解码为字符串。

    弹幕内容为 UTF-8，但偶有用户发送非法字节序列，
    使用 errors="replace" 保证不抛异常（坏字符替换为 ?）。
    """
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _maybe_decompress(data: bytes) -> bytes:
    """如果响应体是"未被解码的压缩数据"，先自行解压。

    【为什么需要这一步 —— 实测踩过的坑】
        抓 40 个视频的弹幕时，前 21 个正常，后 19 个全部解析失败：

            弹幕 protobuf 解析中断：不支持的 wire_type=3（已解析 0 条）

        wire_type=3 是 protobuf 早已废弃的"分组"类型，正常的弹幕数据
        不可能出现 —— 说明拿到的**根本不是 protobuf**。

        但把同样的 cid 稍后重新请求一次，就完全正常（解析出 112 条）。
        结论：B站 CDN 偶发**漏发 Content-Encoding 响应头**。
        requests 只根据这个头来决定是否自动解压，
        头一旦缺失，我们拿到的就是压缩后的原始字节。

    【为什么要自己解压，而不是简单重试】
        每个视频的弹幕请求都要花 1 次风控额度。
        19 个视频因为一个响应头缺失就白抓（还可能被当成"这个视频没弹幕"
        而永久跳过），代价太高。这里按魔数识别并自行解压，一次都不浪费。

    参数:
        data: 响应的原始字节

    返回:
        解压后的字节；无法识别或解压失败时原样返回（交给上层报错）
    """
    if len(data) < 2:
        return data

    # gzip 魔数：1f 8b
    if data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gzip 解压失败，按原样解析：%s", exc)
            return data

    # zlib 头：78 01 / 78 5e / 78 9c / 78 da
    if data[0] == 0x78 and data[1] in (0x01, 0x5E, 0x9C, 0xDA):
        try:
            return zlib.decompress(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("zlib 解压失败，按原样解析：%s", exc)
            return data

    return data


def parse_danmaku_protobuf(data: bytes) -> list[DanmakuItem]:
    """解析弹幕分段接口返回的 protobuf 二进制。

    对应接口：
        GET /x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index={n}

    参数:
        data: 响应的原始字节（requests 的 response.content）

    返回:
        DanmakuItem 列表。解析失败时返回空列表并记录日志，
        不向上抛异常——单包失败不应中断整个视频的弹幕抓取。
    """
    items: list[DanmakuItem] = []

    if not data:
        logger.warning("弹幕数据为空，跳过解析")
        return items

    # 【防御性检查】弹幕接口被风控时会返回 HTTP 200 + JSON 错误体，
    # 而不是 protobuf 二进制。若不在入口拦住，随便一段 JSON 也会被当成
    # protobuf 去解析，最终报出 "不支持的 wire_type=3" 这种毫无线索的错误。
    # （正常的调用路径已在 BiliBiliSpider._guard_danmaku_payload 拦过一道，
    #   这里再拦一次，保证直接调用解析器时也能得到清楚的提示。）
    if data[:1] == b"{":
        logger.warning(
            "弹幕响应是 JSON 而非 protobuf（接口大概率返回了风控提示）：%s",
            data[:120],
        )
        return items

    # 兜底解压：应对 CDN 偶发漏发 Content-Encoding 头的情况
    data = _maybe_decompress(data)

    try:
        # 外层消息只含一个 repeated 字段 elems(1)
        for field_number, wire_type, value in _iter_fields(data):
            if field_number != _SEG_FIELD_ELEMS or wire_type != 2:
                continue
            item = _parse_danmaku_elem(value)
            if item is not None:
                items.append(item)
    except ValueError as exc:
        logger.warning(
            "弹幕 protobuf 解析中断：%s（已解析 %d 条，原始 %d 字节）",
            exc, len(items), len(data),
        )
    except Exception as exc:
        logger.error("弹幕 protobuf 解析异常：%s", exc, exc_info=True)

    return items


def _parse_danmaku_elem(buf: bytes) -> Optional[DanmakuItem]:
    """解析单条弹幕（DanmakuElem 消息）。

    参数:
        buf: 嵌套消息的字节内容

    返回:
        DanmakuItem；内容为空时返回 None（空弹幕无分析价值）
    """
    dmid = None
    progress_ms = 0
    mode = 1
    color = 16777215  # 白色
    content = ""
    ctime = None
    pool = 0

    try:
        for field_number, wire_type, value in _iter_fields(buf):
            if field_number == _DM_FIELD_ID and wire_type == 0:
                dmid = value
            elif field_number == _DM_FIELD_PROGRESS and wire_type == 0:
                progress_ms = value
            elif field_number == _DM_FIELD_MODE and wire_type == 0:
                mode = value
            elif field_number == _DM_FIELD_COLOR and wire_type == 0:
                color = value
            elif field_number == _DM_FIELD_CONTENT and wire_type == 2:
                content = _decode_text(value)
            elif field_number == _DM_FIELD_CTIME and wire_type == 0:
                ctime = value
            elif field_number == _DM_FIELD_POOL and wire_type == 0:
                pool = value
            # 其余字段（fontsize/midHash/weight/action/idStr/attr）暂不关心
    except ValueError:
        # 单条损坏：若有内容仍保留，否则丢弃
        if not content:
            return None

    content = content.strip()
    if not content:
        return None

    return DanmakuItem(
        dmid=dmid,
        content=content,
        # 接口返回毫秒，模型存秒，便于按视频时间轴绘图
        video_time=round(progress_ms / 1000.0, 3),
        send_time=ts_to_datetime(ctime),
        mode=mode,
        color=color,
        pool=pool,
    )


# ===========================================================================
# 测试辅助：protobuf 编码器
# ===========================================================================
# 说明：本函数不属于生产路径，仅供单元测试构造二进制样本，
# 从而在完全离线的情况下验证解析器的正确性。
def encode_varint(value: int) -> bytes:
    """把一个非负整数编码为 varint 字节串。"""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def encode_field_varint(field_number: int, value: int) -> bytes:
    """编码一个 VARINT 类型字段（wire_type=0）。"""
    tag = (field_number << 3) | 0
    return encode_varint(tag) + encode_varint(value)


def encode_field_bytes(field_number: int, raw: bytes) -> bytes:
    """编码一个 LEN 类型字段（wire_type=2），用于字符串或嵌套消息。"""
    tag = (field_number << 3) | 2
    return encode_varint(tag) + encode_varint(len(raw)) + raw


def build_danmaku_segment(items: list[dict]) -> bytes:
    """根据给定字段构造一个 DmSegMobileReply 二进制样本（测试用）。

    参数:
        items: 每项为 dict，可含
               id / progress / mode / color / content / ctime / pool
               其中 progress 单位为毫秒

    返回:
        protobuf 二进制字节串
    """
    payload = bytearray()
    for item in items:
        elem = bytearray()
        if "id" in item:
            elem += encode_field_varint(_DM_FIELD_ID, item["id"])
        if "progress" in item:
            elem += encode_field_varint(_DM_FIELD_PROGRESS, item["progress"])
        if "mode" in item:
            elem += encode_field_varint(_DM_FIELD_MODE, item["mode"])
        if "color" in item:
            elem += encode_field_varint(_DM_FIELD_COLOR, item["color"])
        if "content" in item:
            elem += encode_field_bytes(_DM_FIELD_CONTENT, item["content"].encode("utf-8"))
        if "ctime" in item:
            elem += encode_field_varint(_DM_FIELD_CTIME, item["ctime"])
        if "pool" in item:
            elem += encode_field_varint(_DM_FIELD_POOL, item["pool"])

        payload += encode_field_bytes(_SEG_FIELD_ELEMS, bytes(elem))

    return bytes(payload)

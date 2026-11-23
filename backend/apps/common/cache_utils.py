# -*- coding: utf-8 -*-
"""
缓存操作工具。

【本模块解决的问题】
Django 4.0+ 内置的 `RedisCache` **没有实现 `delete_pattern()`**。
该方法只存在于第三方包 `django-redis` 中。
因此下面这种常见写法会静默失效（不报错，但一个键都删不掉）：

    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern("biliinsight:analytics:*")   # 永远不执行

本项目没有引入 django-redis（少一个依赖少一分风险），
因此这里基于官方 `redis` 库自行实现"按键模式批量删除"。

【为什么用 SCAN 而不是 KEYS】
`KEYS pattern` 会阻塞 Redis 直到遍历完整个键空间，
在生产环境可能造成数百毫秒的卡顿。
`SCAN` 是增量游标遍历，每次只取一小批，对服务影响小。
官方文档也明确建议用 SCAN 替代 KEYS。
"""

import fnmatch
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# 单次 SCAN 返回的键数量。100-1000 之间通常较优，太小会增加往返次数。
_SCAN_COUNT = 500


def get_raw_redis_client():
    """从 Django 缓存后端中取出底层 redis 客户端。

    【为什么需要这个函数】
    Django 的 RedisCache 不暴露公开的 client 属性，
    底层连接藏在私有的 `_cache`（RedisCacheClient）里，
    需要调用其 `get_client()` 才能拿到真正的 `redis.Redis` 实例。

    实测（Django 5.2.7）：
        cache._cache                -> RedisCacheClient
        cache._cache.get_client()   -> redis.Redis

    【容错设计】
    私有属性可能在未来 Django 版本改名，因此用 getattr 逐层探测，
    任何一步失败都返回 None，由调用方决定如何降级。

    返回:
        redis.Redis 实例，或 None（非 Redis 后端 / 版本不兼容时）
    """
    try:
        # 主路径：Django 5.x 的 RedisCacheClient
        wrapper = getattr(cache, "_cache", None)
        if wrapper is not None and hasattr(wrapper, "get_client"):
            inner = wrapper.get_client()
            if hasattr(inner, "scan_iter"):
                return inner

        # 兜底路径：万一某版本直接把客户端挂在 client 上
        direct = getattr(cache, "client", None)
        if direct is not None and hasattr(direct, "scan_iter"):
            return direct
        if direct is not None and hasattr(direct, "get_client"):
            inner = direct.get_client()
            if hasattr(inner, "scan_iter"):
                return inner
    except Exception as exc:
        logger.debug("获取底层 Redis 客户端失败：%s", exc)
    return None


def _cache_key_prefix() -> str:
    """返回 Django 为缓存键自动添加的完整前缀。

    【为什么不能只用 settings 里的 KEY_PREFIX】
    Django 的缓存键由三部分拼成：

        KEY_PREFIX : 版本号 : 业务键名

    实测（Django 5.2.7 + RedisCache，KEY_PREFIX="biliinsight"，默认 version=1）：
        cache.make_key("analytics:overview")
        -> "biliinsight:1:analytics:overview"
                        ^^^^^ 版本号这一节很容易被忽略

    因此不能简单地把 settings 的 KEY_PREFIX 与模式拼接——那样会漏掉版本号，
    SCAN 匹配不到任何键（这正是本项目踩过的坑：清理缓存静默删除 0 个键）。

    返回:
        形如 "biliinsight:1:" 的前缀；无法获取时返回空串
    """
    try:
        # make_key("") 会返回"前缀 + 版本号 + 空"，正好得到完整前缀
        return cache.make_key("")
    except Exception:
        # 非标准后端可能没有 make_key，退化为只用 settings 的 KEY_PREFIX
        prefix = getattr(settings, "CACHES", {}).get("default", {}).get("KEY_PREFIX", "")
        return f"{prefix}:" if prefix else ""


def make_cache_key(key: str) -> str:
    """把业务键名转换成后端实际存储的完整键。

    用途：调试与测试中需要断言某个键是否存在时使用，
    避免调用方自己拼错前缀（含版本号那一节）。

    参数:
        key: 业务键名，如 "analytics:overview"

    返回:
        后端实际使用的完整键名
    """
    try:
        return cache.make_key(key)
    except Exception:
        return f"{_cache_key_prefix()}{key}"


def _delete_pattern_in_memory(pattern: str) -> int:
    """在没有 SCAN 能力的缓存后端（如 LocMemCache）上按键模式删除。

    【为什么需要这条兜底路径】
        桌面版把缓存从 Redis 换成了进程内的 LocMemCache
        （见 config/settings/desktop.py）。而本模块原先的实现
        **只支持 Redis**：拿不到底层 redis 客户端就直接返回 0。

        后果非常隐蔽：`clear_analytics_cache()` 表面"执行成功"，
        实际一个键都没删 —— 于是抓完数据后看板继续显示旧数字，
        使用者看到的是"点了更新数据，但页面没变"。

        这个失效模式本项目已经踩过一次（早先是 delete_pattern
        方法不存在导致静默失效）。既然换成内存后端会再次触发，
        就必须在这里补上兜底，而不是让调用方各自判断。

    【实现方式】
        LocMemCache 的内部就是一个普通 dict，可以直接遍历匹配。
        删除时用公开的 `cache.delete(业务键)`，由后端自己处理前缀，
        不去碰 _cache / _expire_info 这些私有结构（避免随 Django 版本失效）。

    参数:
        pattern: 业务键模式，如 "analytics:*"

    返回:
        删除的键数量
    """
    store = getattr(cache, "_cache", None)
    if not isinstance(store, dict):
        return 0

    prefix = _cache_key_prefix()
    deleted = 0

    # 复制一份键列表再遍历：删除会改变字典大小，边遍历边删会报错
    for full_key in list(store.keys()):
        if not isinstance(full_key, str) or not full_key.startswith(prefix):
            continue
        business_key = full_key[len(prefix):]
        if not fnmatch.fnmatch(business_key, pattern):
            continue
        try:
            if cache.delete(business_key):
                deleted += 1
        except Exception:  # noqa: BLE001
            continue

    if deleted:
        logger.info("按模式 %s 删除了 %d 个缓存键（内存后端）", pattern, deleted)
    return deleted


def delete_pattern(pattern: str) -> int:
    """按模式批量删除缓存键。

    参数:
        pattern: 键模式，**不需要**自己加 KEY_PREFIX
                 （由本函数自动补全，避免调用方遗漏）

    返回:
        实际删除的键数量。无法执行时返回 0（不抛异常）

    【实现说明】
    用 SCAN 游标分批遍历匹配的键，再分批 DEL。
    相比 KEYS 不会长时间阻塞 Redis。
    """
    client = get_raw_redis_client()
    if client is None:
        # 非 Redis 后端（桌面版的 LocMemCache 走这里）
        return _delete_pattern_in_memory(pattern)

    prefix = _cache_key_prefix()
    # 直接拼接：prefix 已包含末尾的冒号（如 "biliinsight:1:"）
    full_pattern = f"{prefix}{pattern}"

    try:
        # scan_iter 是 redis-py 提供的游标迭代器，内部自动处理 SCAN 循环
        keys = list(client.scan_iter(match=full_pattern, count=_SCAN_COUNT))
        if not keys:
            return 0

        # 分批删除：一次删太多会占用较多内存与网络往返
        deleted = 0
        batch_size = 500
        for i in range(0, len(keys), batch_size):
            batch = keys[i:i + batch_size]
            deleted += client.delete(*batch)

        logger.info("按模式 %s 删除了 %d 个缓存键", full_pattern, deleted)
        return deleted
    except Exception as exc:
        # 缓存清理失败不应影响主业务流程
        logger.warning("按模式删除缓存失败 %s：%s", full_pattern, exc)
        return 0

# -*- coding: utf-8 -*-
"""
公共视图：健康检查。

用途：
  1) 前端启动时探活，判断后端是否就绪
  2) 运维/容器编排的健康探针（Docker healthcheck、Nginx upstream 检查）
  3) 开发时快速确认"数据库连上没有"

设计要点：
  - 不需要认证（AllowAny），否则探活本身就成了麻烦
  - 真实探测 MySQL 与 Redis，而不是简单返回 {"status": "ok"}
    因为"能启动"不等于"依赖可用"，假阳性会掩盖问题
  - 任一依赖不可用时返回 HTTP 503，让编排系统能正确判断
"""

import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .response import success

logger = logging.getLogger(__name__)


def _get_raw_redis_client():
    """从 Django 缓存后端中取出底层 redis 客户端。

    【为什么需要这个函数】
    Django 4.0+ 内置的 RedisCache 并不暴露公开的 client 属性，
    底层连接藏在私有的 _cache（RedisCacheClient）里，
    需要调用其 get_client() 才能拿到真正的 redis.Redis 实例。

    实测（Django 5.2.7）：
        cache._cache       -> RedisCacheClient
        cache._cache.get_client() -> redis.Redis

    【容错设计】
    这个私有属性可能在未来的 Django 版本改名，
    因此用 getattr 逐层探测，任何一步失败都返回 None。
    版本号仅用于健康检查展示，取不到不影响服务可用性判定。

    返回:
        redis.Redis 实例，或 None
    """
    try:
        # 主路径：Django 5.x 的 RedisCacheClient
        wrapper = getattr(cache, "_cache", None)
        if wrapper is not None and hasattr(wrapper, "get_client"):
            inner = wrapper.get_client()
            if hasattr(inner, "info"):
                return inner

        # 兜底路径：万一某版本直接把客户端挂在 client 上
        direct = getattr(cache, "client", None)
        if direct is not None and hasattr(direct, "info"):
            return direct
    except Exception:
        # 探测失败是预期内情况，静默降级
        pass
    return None


class HealthCheckView(APIView):
    """健康检查接口。

    GET /api/health/

    响应示例（全部正常）：
        {
          "code": 0,
          "message": "ok",
          "data": {
            "status": "healthy",
            "services": {
              "database": {"ok": true, "detail": "MySQL 8.0.46", "latency_ms": 3.2},
              "cache":    {"ok": true, "detail": "Redis 7.4.11",  "latency_ms": 1.1}
            },
            "version": "1.0.0"
          }
        }

    任一依赖异常时 HTTP 状态码为 503，data.status 为 "degraded"。
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # 探活不需要解析 token，省掉一次数据库查询

    @extend_schema(
        summary="健康检查",
        description="探测后端、MySQL、Redis 是否可用。任一依赖不可用时返回 503。",
        tags=["health"],
        responses={200: None, 503: None},
    )
    def get(self, request):
        """执行依赖探测并返回结果。"""
        services = {
            "database": self._check_database(),
            "cache": self._check_cache(),
        }

        # 所有依赖都正常才算 healthy
        all_ok = all(item["ok"] for item in services.values())

        return success(
            data={
                "status": "healthy" if all_ok else "degraded",
                "services": services,
                "version": "1.0.0",
            },
            message="ok" if all_ok else "部分依赖不可用",
            http_status=200 if all_ok else 503,
        )

    # -----------------------------------------------------------------
    # 私有探测方法
    # -----------------------------------------------------------------
    @staticmethod
    def _check_database():
        """探测数据库：取版本号并计时。

        返回:
            {"ok": bool, "detail": str, "latency_ms": float}

        【为什么要按方言分支】
            桌面版用 SQLite（见 config/settings/desktop.py），
            而 `SELECT VERSION()` 是 **MySQL 专有函数**，SQLite 执行会报错 ——
            健康检查就会误报"数据库不可用"。
            SQLite 对应的写法是 `SELECT sqlite_version()`。

            用 `connection.vendor` 判断方言，而不是 try/except 兜底，
            这样在日志里能直接看出实际用的是哪种数据库。
        """
        start = time.perf_counter()
        try:
            with connection.cursor() as cursor:
                if connection.vendor == "sqlite":
                    cursor.execute("SELECT sqlite_version()")
                    version = cursor.fetchone()[0]
                    detail = f"SQLite {version}"
                else:
                    cursor.execute("SELECT VERSION()")
                    version = cursor.fetchone()[0]
                    detail = f"MySQL {version}"
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            return {"ok": True, "detail": detail, "latency_ms": elapsed}
        except Exception as exc:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.error("健康检查：数据库不可用 - %s", exc)
            return {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "latency_ms": elapsed,
            }

    @staticmethod
    def _check_cache():
        """探测 Redis：写入再读取一个探针键。

        只 ping() 不够——ping 走的是连接层，
        而读写能验证序列化与命令执行链路是否正常。

        返回:
            {"ok": bool, "detail": str, "latency_ms": float}
        """
        start = time.perf_counter()
        probe_key = "health:probe"
        try:
            cache.set(probe_key, "1", timeout=10)
            value = cache.get(probe_key)
            elapsed = round((time.perf_counter() - start) * 1000, 2)

            if value != "1":
                return {
                    "ok": False,
                    "detail": "写入成功但读取失败，缓存可能异常",
                    "latency_ms": elapsed,
                }

            # 尝试读取 Redis 版本号作为附加信息；
            # 桌面版用的是 LocMemCache（没有底层 redis 客户端），
            # 此时退化为报告实际使用的缓存后端名，避免出现"Redis unknown"这种误导。
            detail = None
            try:
                raw_client = _get_raw_redis_client()
                if raw_client is not None:
                    info = raw_client.info()
                    detail = f"Redis {info.get('redis_version', 'unknown')}"
            except Exception:
                # 版本信息只是锦上添花，取不到不影响健康判定
                pass

            if detail is None:
                # 从 settings 取后端类名。
                # 注意：不能用 type(cache).__name__ —— django.core.cache.cache
                # 是个 ConnectionProxy 代理对象，取到的永远是 "ConnectionProxy"，
                # 对排查"到底用的是 Redis 还是内存缓存"毫无帮助。
                _backend = (
                    getattr(settings, "CACHES", {})
                    .get("default", {})
                    .get("BACKEND", "")
                )
                detail = _backend.rsplit(".", 1)[-1] or "unknown"

            return {"ok": True, "detail": detail, "latency_ms": elapsed}
        except Exception as exc:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.error("健康检查：缓存不可用 - %s", exc)
            return {
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "latency_ms": elapsed,
            }

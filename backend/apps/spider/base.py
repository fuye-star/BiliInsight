# -*- coding: utf-8 -*-
"""
BaseSpider —— 爬虫抽象基类。

【设计目标（对应 rdme.txt 的"复用性"要求）】
> 爬虫模块抽象为 BaseSpider 基类，更换目标网站只需实现新解析方法

因此本基类把所有"与具体站点无关"的通用能力都收敛进来：
    · 强制请求间隔（限速）        —— 合规要求 + 避免被封
    · 自动重试与指数退避          —— 应对网络抖动
    · 统一 User-Agent 与请求头    —— 声明学习研究用途
    · 会话复用（keep-alive）      —— 减少握手开销
    · 结构化日志                  —— 便于排查与答辩演示
    · 统计计数                    —— 供 CrawlTask 记录

子类只需实现：
    fetch_xxx()   如何请求（接口地址与参数）
    parse_xxx()   如何解析（把原始响应转成 dataclass）
    run()         编排流程（可选，基类已给出模板）

【新增一个站点的步骤】
    class MySpider(BaseSpider):
        name = "mysite"
        def fetch_items(self): ...
        def parse_items(self, raw): ...
    # 其余限速、重试、日志能力自动继承

【合规声明】
本基类默认强制限速，且请求间隔下限锁定为 1.0 秒，不允许配置成更激进的值。
仅用于学习研究，请勿用于商业用途或高频抓取。
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    """一次爬取过程的统计结果。

    与 spider.CrawlTask 模型字段一一对应，方便直接写入数据库。
    """

    fetched: int = 0     # 从接口拿到的原始条数
    created: int = 0     # 新入库条数
    updated: int = 0     # 更新已有条数
    failed: int = 0      # 解析或入库失败条数
    requests: int = 0    # 实际发出的 HTTP 请求数（含重试）

    #: 翻页抓取时实际读到的最后一页（仅 popular 抓取会填）。
    #: 调用方用它维护"下次从第几页开始"的游标 —— 这样界面上每次点
    #: 「更新数据」都能拿到新内容，而不是反复抓同一批已入库的视频。
    #: 它属于元信息，不参与 merge 累加，也不写进任务统计表。
    last_page: int = 0

    def merge(self, other: "CrawlStats") -> "CrawlStats":
        """累加另一份统计（多分区抓取时逐次汇总）。"""
        self.fetched += other.fetched
        self.created += other.created
        self.updated += other.updated
        self.failed += other.failed
        self.requests += other.requests
        return self

    def as_dict(self) -> dict:
        """转为字典，便于写入模型或返回给 Celery。"""
        return {
            "total_fetched": self.fetched,
            "total_created": self.created,
            "total_updated": self.updated,
            "total_failed": self.failed,
            "requests": self.requests,
        }


class SpiderError(Exception):
    """爬虫业务异常基类。"""


class RateLimitedError(SpiderError):
    """被目标站点限流（HTTP 412 / 429 或业务码 -412）。"""


class ParseError(SpiderError):
    """响应解析失败。"""


class BaseSpider(ABC):
    """爬虫抽象基类。

    子类必须提供 name 与 base_url，并实现 fetch/parse 方法。
    """

    # ---- 子类必须覆盖 ----
    name: str = "base"                 # 爬虫标识，用于日志与统计
    base_url: str = ""                 # 站点主域

    # ---- 子类可按需覆盖 ----
    # 单次请求的超时（连接超时, 读取超时）
    timeout: tuple = (10, 20)

    # 视为"被限流"的业务码。
    # 【为什么必须区分】
    # 这类错误重试是无效甚至有害的——B站风控会随请求次数升级，
    # 继续重试会让封禁时间变长。识别后立即停止，交由上层决定是否等待。
    #   -352  请求过于频繁（风控）
    #   -412  请求被拦截（风控）
    #   -509  请求过于频繁
    #   -799  请求过于频繁，请稍后再试
    RATE_LIMIT_CODES: tuple = (-352, -412, -509, -799)

    def __init__(
        self,
        interval: Optional[float] = None,
        max_retries: Optional[int] = None,
        user_agent: Optional[str] = None,
    ):
        """初始化爬虫。

        参数:
            interval:    请求间隔（秒）。不传则读 settings.SPIDER_REQUEST_INTERVAL
            max_retries: 最大重试次数。不传则读 settings.SPIDER_MAX_RETRIES
            user_agent:  自定义 UA。不传则读 settings.SPIDER_USER_AGENT

        说明：默认值从 Django settings 读取，便于统一调参；
        settings 不可用（如单元测试环境）时回退到安全默认值。
        """
        from django.conf import settings

        raw_interval = interval if interval is not None else getattr(
            settings, "SPIDER_REQUEST_INTERVAL", 2.0
        )
        # 合规硬约束：间隔不得低于 1 秒，避免误配置导致高频抓取
        self.interval = max(float(raw_interval), 1.0)

        self.max_retries = int(
            max_retries if max_retries is not None else getattr(
                settings, "SPIDER_MAX_RETRIES", 3
            )
        )

        self.user_agent = user_agent or getattr(
            settings,
            "SPIDER_USER_AGENT",
            "Mozilla/5.0 (compatible; BiliInsight/1.0; Educational-Research)",
        )

        # 统计对象，随爬取过程累加
        self.stats = CrawlStats()

        # 记录上一次请求的时刻，用于计算是否需要休眠（限速核心）
        self._last_request_at: float = 0.0

        # 复用 TCP 连接，减少握手开销（同时也是对目标站点更友好的做法）
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                # 声明用途，便于站点识别为学习研究流量
                "Referer": self.base_url or "https://www.bilibili.com/",
            }
        )

    # =====================================================================
    # 限速
    # =====================================================================
    def _throttle(self):
        """确保两次请求之间至少间隔 self.interval 秒。

        【为什么不用固定 sleep(interval)】
        固定休眠会让"请求本身耗时"白白浪费——若一次请求耗时 1.5 秒，
        再 sleep 2 秒，实际间隔变成 3.5 秒，抓取效率无谓降低。
        这里改为"距上次请求不足 interval 才补足差额"，
        既满足限速要求，又不浪费已消耗的时间。

        另外加入 ±20% 随机抖动，避免形成固定周期的机器特征。
        """
        if self._last_request_at <= 0:
            return

        elapsed = time.monotonic() - self._last_request_at
        # 抖动：让请求节奏更接近人类浏览
        target = self.interval * random.uniform(0.8, 1.2)

        wait = target - elapsed
        if wait > 0:
            logger.debug("[%s] 限速休眠 %.2f 秒", self.name, wait)
            time.sleep(wait)

    # =====================================================================
    # HTTP 请求（含重试）
    # =====================================================================
    def request(
        self,
        url: str,
        params: Optional[dict] = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        """发起 GET 请求，自带限速、重试与错误分类。

        参数:
            url:         完整请求地址
            params:      查询参数
            expect_json: True 返回解析后的 dict；False 返回原始 bytes
                         （弹幕接口返回 protobuf 二进制，需要原始字节）

        返回:
            dict 或 bytes

        异常:
            RateLimitedError: 被限流
            SpiderError:      重试耗尽后仍失败
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()

            try:
                logger.debug(
                    "[%s] 请求 %s params=%s (第 %d/%d 次)",
                    self.name, url, params, attempt, self.max_retries,
                )
                response = self.session.get(url, params=params, timeout=self.timeout)
                self._last_request_at = time.monotonic()
                self.stats.requests += 1

                # ---- 限流识别 ----
                # B站风控常以 412 返回；429 是通用限流语义
                if response.status_code in (412, 429):
                    raise RateLimitedError(
                        f"被目标站点限流（HTTP {response.status_code}），"
                        f"建议调大 SPIDER_REQUEST_INTERVAL"
                    )

                response.raise_for_status()

                # ---- 返回内容 ----
                if not expect_json:
                    return response.content

                payload = response.json()

                # ---- 业务码检查 ----
                # B站接口用 code 表达业务结果，0 为成功。
                # 注意：风控相关错误码必须识别出来并【停止重试】，
                # 否则重试只会让风控等级更高。
                code = payload.get("code")
                if code in self.RATE_LIMIT_CODES:
                    raise RateLimitedError(
                        f"接口返回 {code}（{payload.get('message')}），"
                        f"触发目标站点风控"
                    )
                if code != 0:
                    raise SpiderError(
                        f"接口返回业务错误 code={code} message={payload.get('message')}"
                    )

                return payload

            except RateLimitedError:
                # 限流不重试——重试只会加重风控，直接向上抛出由调用方决定
                raise

            except (requests.RequestException, ValueError, SpiderError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break

                # 指数退避：1s / 2s / 4s，再叠加随机抖动
                backoff = (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    "[%s] 第 %d 次请求失败（%s），%.1f 秒后重试",
                    self.name, attempt, type(exc).__name__, backoff,
                )
                time.sleep(backoff)

        raise SpiderError(
            f"[{self.name}] 请求失败，已重试 {self.max_retries} 次：{last_error}"
        ) from last_error

    # =====================================================================
    # 子类需要实现的接口
    # =====================================================================
    @abstractmethod
    def run(self, *args, **kwargs) -> CrawlStats:
        """执行一次完整爬取并返回统计结果。

        子类在此编排"请求 -> 解析 -> 入库"的流程。
        基类不提供默认实现，因为不同站点的流程差异较大。
        """
        raise NotImplementedError

    # =====================================================================
    # 通用工具
    # =====================================================================
    def close(self):
        """释放连接池。建议在 finally 中调用。"""
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self):
        """支持 with 语法，确保异常时也能关闭会话。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出 with 时自动关闭会话。"""
        self.close()
        return False  # 不吞异常

    def __repr__(self):
        """便于日志中辨认实例。"""
        return f"<{self.__class__.__name__} name={self.name} interval={self.interval}s>"

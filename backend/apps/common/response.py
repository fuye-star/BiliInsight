# -*- coding: utf-8 -*-
"""
统一响应封装。

【为什么需要】
前后端约定一个固定的响应结构，前端拦截器就能统一处理成功/失败，
不用为每个接口写不同的判断逻辑。

约定格式：
    {
      "code": 0,               # 0 表示成功，非 0 表示业务错误
      "message": "ok",         # 提示信息，可直接展示给用户
      "data": {...}            # 实际业务数据，失败时为 null
    }

【与 HTTP 状态码的分工】
  HTTP 状态码  -> 表达传输层/协议层结果（200/401/404/500）
  code 字段    -> 表达业务层结果（如"视频不存在"仍返回 HTTP 200 + code=20001）
"""

from rest_framework.response import Response


def success(data=None, message="ok", code=0, http_status=200):
    """构造成功响应。

    参数:
        data:        业务数据，可为 dict / list / 基础类型
        message:     提示文案
        code:        业务成功码，默认 0
        http_status: HTTP 状态码，默认 200

    用法:
        return success({"count": 10})
    """
    return Response(
        {"code": code, "message": message, "data": data},
        status=http_status,
    )


def error(message="请求失败", code=1, data=None, http_status=400):
    """构造失败响应。

    参数:
        message:     错误描述（会直接展示给用户，避免暴露内部细节）
        code:        业务错误码
        data:        附加信息，例如字段级校验错误
        http_status: HTTP 状态码，默认 400

    用法:
        return error("视频不存在", code=20001, http_status=404)
    """
    return Response(
        {"code": code, "message": message, "data": data},
        status=http_status,
    )


class BusinessCode:
    """业务错误码集中定义。

    分段规则（便于快速定位问题来源）：
      0        成功
      1xxx     通用错误（参数、权限、限流）
      2xxx     视频 / UP主 / 弹幕 相关
      3xxx     爬虫与任务相关
      4xxx     AI 模块相关
    """

    SUCCESS = 0

    # --- 通用 ---
    BAD_REQUEST = 1001          # 请求参数有误
    UNAUTHORIZED = 1002         # 未登录或 token 失效
    FORBIDDEN = 1003            # 无权限
    NOT_FOUND = 1004            # 资源不存在
    RATE_LIMITED = 1005         # 请求过于频繁
    SERVER_ERROR = 1500         # 服务器内部错误

    # --- 视频模块 ---
    VIDEO_NOT_FOUND = 2001      # 视频不存在
    DANMAKU_DISABLED = 2002     # 该视频未开启弹幕

    # --- 爬虫模块 ---
    CRAWL_FAILED = 3001         # 抓取失败
    CRAWL_RATE_LIMITED = 3002   # 被目标站点限流

    # --- AI 模块 ---
    AI_PROVIDER_ERROR = 4001    # 大模型服务不可用
    AI_TIMEOUT = 4002           # 推理超时
    EMBEDDING_ERROR = 4003      # 向量化失败

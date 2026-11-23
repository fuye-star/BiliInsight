# -*- coding: utf-8 -*-
"""
全局异常处理。

【为什么需要】
DRF 默认的错误响应格式与我们的统一响应约定不一致，
前端拦截器就得写两套判断逻辑。这里把 DRF 抛出的所有异常
统一转换成 {code, message, data} 结构。

配置位置：settings 的 REST_FRAMEWORK["EXCEPTION_HANDLER"]
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

from .response import BusinessCode

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """把异常转换为统一响应结构。

    参数:
        exc:     捕获到的异常实例
        context: DRF 上下文，含 view / request / args / kwargs

    返回:
        Response 对象，或 None（交给 Django 处理）
    """    # 先交给 DRF 默认处理器，拿到基础响应（它会设置正确的 HTTP 状态码）
    response = drf_exception_handler(exc, context)

    # 记录异常发生位置，便于排查
    view = context.get("view", None)
    view_name = view.__class__.__name__ if view else "unknown"

    if response is not None:
        # ---- DRF 能识别的异常 ----
        code = BusinessCode.BAD_REQUEST
        http_status = response.status_code

        if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            code = BusinessCode.UNAUTHORIZED
            message = "登录状态已失效，请重新登录"
        elif isinstance(exc, PermissionDenied):
            code = BusinessCode.FORBIDDEN
            message = "没有权限执行该操作"
        elif isinstance(exc, Throttled):
            code = BusinessCode.RATE_LIMITED
            message = f"请求过于频繁，请 {exc.wait or 60} 秒后重试"
        elif isinstance(exc, (NotFound, Http404)):
            code = BusinessCode.NOT_FOUND
            # 【为什么要取出 exc.detail】
            # DRF 的 NotFound 允许带自定义说明，例如：
            #     raise NotFound(f"视频不存在：{bvid}")
            # 若这里写死一句"请求的资源不存在"，就丢失了 bvid 这个关键信息，
            # 前端与调试时无法判断到底是哪个资源找不到。
            # 因此优先使用异常自带的说明，没有才回退到通用文案。
            # （NotFound 是 Http404 的子类，故合并处理）
            detail = getattr(exc, "detail", None)
            message = _extract_message(detail) if detail else "请求的资源不存在"
        elif isinstance(exc, ValidationError):
            code = BusinessCode.BAD_REQUEST
            # 提取字段级错误，前端可直接标红对应输入框
            message = _flatten_validation_error(exc.detail)
        else:
            message = _extract_message(exc.detail) if hasattr(exc, "detail") else "请求失败"

        response.data = {"code": code, "message": message, "data": None}

        # 5xx 才记 error 级别，4xx 属于预期内的业务错误，记 warning 即可
        if http_status >= 500:
            logger.error("[%s] %s: %s", view_name, exc.__class__.__name__, message, exc_info=True)
        else:
            logger.warning("[%s] %s: %s", view_name, exc.__class__.__name__, message)

        return response

    # ---- DRF 未处理的异常：数据库 / 对象不存在 / 其他 ----
    if isinstance(exc, ObjectDoesNotExist):
        logger.warning("[%s] 对象不存在: %s", view_name, exc)
        return _build(BusinessCode.NOT_FOUND, "请求的数据不存在", status.HTTP_404_NOT_FOUND)

    if isinstance(exc, DatabaseError):
        logger.error("[%s] 数据库错误: %s", view_name, exc, exc_info=True)
        return _build(
            BusinessCode.SERVER_ERROR,
            "数据库繁忙，请稍后重试",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # 兜底：未预期异常。记录完整堆栈，但对外只返回通用提示，
    # 避免把文件路径、SQL 等敏感信息泄露给前端。
    logger.exception("[%s] 未处理异常: %s", view_name, exc)
    return _build(
        BusinessCode.SERVER_ERROR,
        "服务器内部错误，请联系管理员",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _build(code, message, http_status):
    """构造统一格式的错误响应。"""
    from rest_framework.response import Response

    return Response({"code": code, "message": message, "data": None}, status=http_status)


# ---------------------------------------------------------------------------
# Django 层级的 404 / 500 处理
# ---------------------------------------------------------------------------
# 说明：DRF 的 exception_handler 只处理 DRF 视图内抛出的异常。
# 当请求打到一个"根本没有匹配路由"的 URL 时，异常发生在路由解析阶段，
# 不会进入 DRF 的处理链，而是由 Django 用 handler404 处理。
# 因此必须在这里单独接管，才能保证 404 也返回统一 JSON 结构。


def handler404(request, exception=None):
    """全局 404：路由未匹配时返回统一 JSON。

    返回示例:
        {"code": 1004, "message": "请求的资源不存在", "data": null}
    """
    from django.http import JsonResponse

    return JsonResponse(
        {"code": BusinessCode.NOT_FOUND, "message": "请求的资源不存在", "data": None},
        status=404,
        json_dumps_params={"ensure_ascii": False},  # 中文不转义为 \uXXXX
    )


def handler500(request):
    """全局 500：未捕获的服务端异常返回统一 JSON。

    注意：不透出异常详情，避免泄露文件路径、SQL 等敏感信息。
    """
    from django.http import JsonResponse

    return JsonResponse(
        {"code": BusinessCode.SERVER_ERROR, "message": "服务器内部错误，请联系管理员", "data": None},
        status=500,
        json_dumps_params={"ensure_ascii": False},
    )


def _extract_message(detail):
    """从 DRF 的 detail 中提取可读的错误信息。

    detail 可能是字符串、列表或嵌套字典，这里统一转成字符串。
    """
    if isinstance(detail, str):
        return detail
    if isinstance(detail, (list, tuple)):
        return _extract_message(detail[0]) if detail else "请求失败"
    if isinstance(detail, dict):
        # 形如 {"field": ["错误1", "错误2"]}，取第一条
        for key, value in detail.items():
            msg = _extract_message(value)
            return f"{key}: {msg}" if key != "non_field_errors" else msg
    return str(detail)


def _flatten_validation_error(detail):
    """把校验错误拍平成一句话，便于前端直接展示。"""
    messages = []

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "non_field_errors":
                    _walk(value)
                else:
                    sub = []
                    _collect(value, sub)
                    messages.extend(f"{key}: {m}" for m in sub)
        elif isinstance(node, (list, tuple)):
            _walk(node[0]) if node else None
        else:
            messages.append(str(node))

    def _collect(node, out):
        """递归收集叶子节点的错误文案。"""
        if isinstance(node, dict):
            for value in node.values():
                _collect(value, out)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _collect(item, out)
        else:
            out.append(str(node))

    _walk(detail)
    return "；".join(messages) if messages else "请求参数有误"

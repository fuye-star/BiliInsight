# -*- coding: utf-8 -*-
"""前端单页应用（SPA）托管视图。

【为什么需要它】
    开发阶段前端跑在 Vite 开发服务器（8080）上，靠 proxy 把 /api 转给 Django。
    但桌面版不能要求使用者先开一个 npm 进程 —— 必须"双击就见效"。

    因此桌面版把 Vue 的构建产物（frontend/dist）交给 Django 直接托管：

        GET /                -> dist/index.html
        GET /assets/xxx.js   -> dist/assets/xxx.js
        GET /videos          -> dist/index.html（交给前端路由处理）

【为什么要单独处理"真实文件"和"前端路由"】
    Vue Router 用的是 history 模式（没有 #），所以像 /videos、/sentiment 这些
    地址在服务端并不存在对应文件。服务器必须回退返回 index.html，
    再由前端路由自己渲染，否则刷新页面就会 404。

    但 /assets/index-xxx.js 这类真实文件必须原样返回，
    不能被当成"前端路由"而回 index.html —— 那样页面会白屏。
"""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join
from django.views.decorators.http import require_GET


def _dist_dir() -> Path:
    """返回前端构建产物目录。"""
    configured = getattr(settings, "FRONTEND_DIST", "") or ""
    if not configured:
        raise Http404("未配置 FRONTEND_DIST，当前不是桌面版运行模式")
    return Path(configured).resolve()


def _file_response(file_path: Path) -> FileResponse:
    """构造文件响应，并按扩展名推断 Content-Type。"""
    content_type, _encoding = mimetypes.guess_type(str(file_path))
    return FileResponse(
        open(file_path, "rb"),
        content_type=content_type or "application/octet-stream",
    )


@require_GET
def serve_spa(request, path: str = ""):
    """托管前端产物；未命中真实文件时回退到 index.html。"""
    dist = _dist_dir()
    index_file = dist / "index.html"
    if not index_file.is_file():
        raise Http404(
            "前端构建产物不存在。开发期请先执行：cd frontend && npm run build"
        )

    # ---- 1) 优先命中真实文件（assets/*.js、favicon、css 等）----
    if path:
        try:
            # safe_join 会阻止 ../ 路径穿越；不要自己拼字符串
            candidate = Path(safe_join(str(dist), path))
        except Exception:
            candidate = None

        if candidate is not None and candidate.is_file():
            return _file_response(candidate)

    # ---- 2) 其余一律交给前端路由 ----
    # index.html 不能缓存，否则前端发版后使用者拿到的还是旧壳子
    response = FileResponse(
        open(index_file, "rb"),
        content_type="text/html; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

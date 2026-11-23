# -*- coding: utf-8 -*-
"""
URL 总路由。

【路由分层原则】
  /admin/          -> Django Admin 后台
  /api/health/     -> 健康检查（无需认证，便于运维与前端探活）
  /api/docs/       -> 接口文档（Swagger UI / Redoc）
  /api/auth/       -> 用户认证（注册/登录/刷新 token）
  /api/            -> 各业务 app 的路由（videos / analytics / ai）

各 app 内部维护自己的 urls.py，通过 include() 挂载，
避免所有路由堆在一个文件里。
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.spa import serve_spa
from apps.common.views import HealthCheckView

urlpatterns = [
    # ---------------------------------------------------------------------
    # Django 管理后台
    # ---------------------------------------------------------------------
    path("admin/", admin.site.urls),

    # ---------------------------------------------------------------------
    # 健康检查（无需认证）
    # 前端启动时可用它判断后端是否就绪；运维也可作为探针
    # ---------------------------------------------------------------------
    path("api/health/", HealthCheckView.as_view(), name="health-check"),

    # ---------------------------------------------------------------------
    # 接口文档（drf-spectacular 自动生成，随代码实时更新）
    #   /api/schema/  -> OpenAPI schema（JSON/YAML）
    #   /api/docs/    -> Swagger UI（可直接在页面上调试接口）
    #   /api/redoc/   -> Redoc（更适合阅读）
    #
    # 注意：drf-spectacular 0.28 未提供 urls 模块，
    # 需要直接引用它的视图类。
    # ---------------------------------------------------------------------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path("api/auth/", include("apps.accounts.urls")),

    # ---------------------------------------------------------------------
    # 业务模块路由
    # ---------------------------------------------------------------------
    path("api/", include("apps.videos.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/ai/", include("apps.ai.urls")),

    # 抓取相关（桌面版「更新数据」按钮的后端）
    path("api/spider/", include("apps.spider.urls")),
]

# 开发环境下由 Django 直接托管用户上传的媒体文件
# （生产环境应交给 Nginx，见 README 部署章节）
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# ---------------------------------------------------------------------------
# 桌面版：托管前端构建产物（SPA 兜底路由）
# ---------------------------------------------------------------------------
# 【为什么放在最后】必须是兜底 —— 前面的 /api、/admin 等具体路由先匹配，
# 匹配不到才落到这里返回 index.html，交给前端路由处理。
#
# 【为什么要排除这些前缀】否则 /api/unknown/ 这类不存在的接口
# 会被兜底成 200 + HTML，前端拿到一段 HTML 却当 JSON 解析，报错极其难查。
if getattr(settings, "FRONTEND_DIST", ""):
    urlpatterns += [
        re_path(
            r"^(?!(?:api|admin|static|media)/)(?P<path>.*)$",
            serve_spa,
            name="spa",
        )
    ]


# ---------------------------------------------------------------------------
# 全局 404 / 500 处理
# ---------------------------------------------------------------------------
# 【为什么需要】
# Django 默认的 404 / 500 返回 HTML 页面（DEBUG=True 时是调试页），
# 而前端 Axios 拦截器期望统一的 {code, message, data} JSON 结构。
# 若不接管，前端遇到 404 会解析 JSON 失败，报出无关的错误。
handler404 = "apps.common.exceptions.handler404"
handler500 = "apps.common.exceptions.handler500"

# -*- coding: utf-8 -*-
"""spider 应用的路由。

【接口用途】
    桌面版的「更新数据」按钮，以及 AI 页面的"补全数据"入口都走这里。

    POST /api/spider/crawl/     抓取排行榜（同步，秒级）
    POST /api/spider/enrich/    启动后台补全（粉丝数 + 弹幕）
    GET  /api/spider/enrich/    查询补全进度
    GET  /api/spider/options/   可选分区列表

【为什么不用 Celery 任务接口】
    早期规划过 POST /api/tasks/crawl/ + 轮询任务表（CrawlTask）的方案。
    桌面版把它简化了：
      · 抓排行榜本身很快（1 次请求），同步返回最直观，不需要任务表；
      · 只有"补粉丝数 / 抓弹幕"才需要后台执行，用一个后台线程足够，
        不必为此保留 Redis + worker 的整套基础设施。

    异步任务（Celery）的实现仍然保留在 apps/spider/tasks.py，
    供服务器部署形态使用，两种形态互不影响。
"""

from django.urls import path

from . import views

urlpatterns = [
    path("crawl/", views.CrawlNowView.as_view(), name="spider-crawl"),
    path("enrich/", views.EnrichView.as_view(), name="spider-enrich"),
    path("options/", views.CrawlOptionsView.as_view(), name="spider-options"),
]

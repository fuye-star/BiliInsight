# -*- coding: utf-8 -*-
"""
accounts 应用的路由。

阶段一仅搭建占位结构，阶段二实现以下接口：
    POST /api/auth/register/   注册
    POST /api/auth/login/      登录，返回 access + refresh token
    POST /api/auth/refresh/    刷新 access token
    GET  /api/auth/me/         当前登录用户信息
"""

from django.urls import path

urlpatterns = [
    # 阶段二在此挂载认证相关视图
]

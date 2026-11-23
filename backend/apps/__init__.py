# -*- coding: utf-8 -*-
"""
业务应用集合。

本项目把业务代码按职责拆分为 6 个 app，
而不是全部塞进一个 app —— 便于分工协作与单元测试。

  common     公共组件：分页、响应封装、异常处理、基础模型、健康检查
  accounts   用户与 JWT 认证
  videos     核心数据模型：视频 / UP主 / 弹幕 / 分区
  spider     数据采集：BaseSpider 抽象基类 + B站实现 + Celery 任务
  analytics  数据统计分析 API（趋势、占比、排行榜、词云）
  ai         AI 模块：LLM 工厂 + RAG 检索 + 弹幕情感分析
"""

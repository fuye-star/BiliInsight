# -*- coding: utf-8 -*-
"""
accounts 应用的数据模型。

【阶段一决策：不自定义 User 模型】

Django 官方文档明确建议：**项目开始时就确定是否用自定义 User 模型**，
因为项目中途替换的代价极高（涉及所有外键与迁移）。

本项目选择沿用 Django 内置的 auth.User，理由：
  1. 本项目的核心是"数据分析看板"，用户体系只需满足登录/权限，
     内置 User 的 username / password / email / is_staff 已完全够用；
  2. 无需维护额外的用户表与迁移，降低答辩现场环境风险；
  3. 若将来确实需要扩展（如绑定 B站 UID、头像），
     新增 Profile 模型做一对一扩展即可，不影响现有表结构。

【阶段二计划】
新增 UserProfile 模型（OneToOneField -> User），承载：
  - bili_uid    绑定的 B站 UID
  - avatar      头像地址
  - preference  偏好分区（JSON），供推荐算法使用
"""

# 本 app 阶段一暂无自定义模型，使用 Django 内置 User。
# 保留此文件以便阶段二添加 UserProfile。

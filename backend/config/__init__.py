# -*- coding: utf-8 -*-
"""
BiliInsight 配置包入口。

【为什么需要这个文件】
Django 的 MySQL 后端（django.db.backends.mysql）默认依赖 mysqlclient，
而 mysqlclient 在 Windows 上需要 C 编译环境，安装门槛高。
本项目改用纯 Python 的 PyMySQL 作为驱动。

PyMySQL 提供了一个"伪装"开关 install_as_MySQLdb()，
它会把自己注册成 MySQLdb 模块，从而让 Django 无缝使用。

【关键点：必须在这里调用，不能放到 settings 里】
Django 加载 MySQL 后端的时机早于 settings 模块的执行体，
因此必须在 config 包被导入的最早时刻完成注册。
放在 config/__init__.py 是官方推荐做法。
"""

import pymysql

# 将 PyMySQL 伪装成 MySQLdb，使 Django 的 mysql 后端可以直接使用
pymysql.install_as_MySQLdb()


# 暴露 Celery 应用实例。
# 【为什么必须有这一行】
# 执行 `celery -A config worker` 时，Celery 会导入名为 config 的包，
# 并从包属性中查找 app 实例。这里显式导入后，config.celery_app 才可见，
# Celery 才能定位到 Broker 配置与任务列表。
# 否则会报 "Unable to load celery application"。
from .celery import app as celery_app

__all__ = ("celery_app",)


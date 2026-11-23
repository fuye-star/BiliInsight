# -*- coding: utf-8 -*-
"""common 应用的 AppConfig。"""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """公共组件：分页器、响应封装、异常处理、基础模型、健康检查。"""

    # 默认主键类型，避免每个模型重复声明
    default_auto_field = "django.db.models.BigAutoField"

    # 应用的 Python 导入路径
    name = "apps.common"

    # 数据库中的 app 标识。显式指定为 "common"，
    # 这样表名会是 common_xxx，且 migrations 依赖项引用更简洁。
    label = "common"

    # Admin 后台中显示的中文名
    verbose_name = "公共组件"

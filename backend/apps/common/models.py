# -*- coding: utf-8 -*-
"""
基础抽象模型。

所有业务模型继承 TimeStampedModel，统一获得创建/更新时间字段，
避免在每个模型里重复声明，也便于后续做增量同步（按 updated_at 拉取变更）。
"""

from django.db import models


class TimeStampedModel(models.Model):
    """带创建时间与更新时间的抽象基类。

    使用 abstract = True：不会生成独立数据表，
    而是把这两个字段"复制"到每个子类表中。
    """

    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,   # 首次保存时自动写入，之后不再变动
        db_index=True,       # 常用于按时间排序，建索引加速
        help_text="记录首次入库时间",
    )

    updated_at = models.DateTimeField(
        "更新时间",
        auto_now=True,       # 每次 save() 都刷新
        help_text="记录最后一次修改时间",
    )

    class Meta:
        # 抽象基类，不建表
        abstract = True
        # 默认按创建时间倒序，最新数据排在前面
        ordering = ["-created_at"]

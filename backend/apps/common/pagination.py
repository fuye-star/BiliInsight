# -*- coding: utf-8 -*-
"""
分页器。

DRF 自带 PageNumberPagination，但默认只返回 count/next/previous/results，
前端还需要知道"共几页、当前第几页"才能渲染分页控件。
这里在响应中补齐这些字段。
"""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """标准分页器：默认每页 20 条，允许前端通过 page_size 参数调整。"""

    # 默认每页条数
    page_size = 20

    # 前端可用 ?page_size=50 自定义每页条数
    page_size_query_param = "page_size"

    # 上限保护：防止前端传 page_size=100000 把数据库拖垮
    max_page_size = 100

    # 前端用 ?page=3 指定页码
    page_query_param = "page"

    def get_paginated_response(self, data):
        """返回带分页元信息的标准结构。

        返回示例：
            {
              "code": 0,
              "message": "ok",
              "data": {
                "total": 137,          # 总记录数
                "page": 2,             # 当前页
                "page_size": 20,       # 每页条数
                "total_pages": 7,      # 总页数
                "has_next": true,
                "has_previous": true,
                "results": [...]       # 当前页数据
              }
            }
        """
        return Response(
            OrderedDict(
                [
                    ("code", 0),
                    ("message", "ok"),
                    (
                        "data",
                        OrderedDict(
                            [
                                ("total", self.page.paginator.count),
                                ("page", self.page.number),
                                ("page_size", self.get_page_size(self.request)),
                                ("total_pages", self.page.paginator.num_pages),
                                ("has_next", self.page.has_next()),
                                ("has_previous", self.page.has_previous()),
                                ("results", data),
                            ]
                        ),
                    ),
                ]
            )
        )

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django 命令行管理入口。

常用命令：
    python manage.py runserver 8000         启动开发服务器
    python manage.py makemigrations         生成迁移文件
    python manage.py migrate                执行迁移（建表）
    python manage.py createsuperuser        创建后台管理员
    python manage.py check                  检查配置是否有误（不连数据库）
    python manage.py shell                  进入交互式 shell
    python manage.py test                   运行单元测试

【默认设置模块】
本项目默认使用 config.settings.dev（开发环境，DEBUG=True）。
切换生产环境：
    set DJANGO_SETTINGS_MODULE=config.settings.prod
    python manage.py check --deploy
"""

import os
import sys


def main():
    """执行管理命令。"""
    # 默认指向开发配置；已显式设置时以环境变量为准，
    # 这样部署时无需改代码即可切换。
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入 Django。请确认：\n"
            "  1) 已激活虚拟环境：.\\.venv\\Scripts\\Activate.ps1\n"
            "  2) 已安装依赖：pip install -r requirements.txt"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

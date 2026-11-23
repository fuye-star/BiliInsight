# -*- coding: utf-8 -*-
"""
WSGI 入口（同步部署）。

开发：python manage.py runserver
生产（Windows）：waitress-serve --port=8000 config.wsgi:application
生产（Linux）  ：gunicorn config.wsgi:application -w 4 -b 0.0.0.0:8000

【为什么 Windows 用 waitress 而不是 gunicorn】
gunicorn 依赖 fcntl 等 Unix 专有模块，无法在 Windows 上运行。
waitress 是纯 Python 实现，跨平台且性能足够本项目使用。
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()

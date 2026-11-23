# -*- coding: utf-8 -*-
"""
ASGI 入口（异步部署）。

用途：WebSocket 长连接、SSE 流式响应（AI 助手的打字机效果）、
以及高并发 I/O 场景。

启动：
    uvicorn config.asgi:application --host 0.0.0.0 --port 8000
    # 或
    daphne config.asgi:application

【本项目何时用得上】
AI 助手的流式回答（/api/ai/chat/ 的 SSE 模式）用 ASGI 体验最好；
普通 REST 接口用 WSGI 已足够。开发阶段两者都能跑。
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()

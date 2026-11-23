# -*- coding: utf-8 -*-
"""
Celery 应用入口。

【启动方式】
Windows 下必须使用 solo 池，否则 Worker 会卡死（prefork 与 Windows 不兼容）：

    celery -A config worker -l info -P solo      # 启动 Worker
    celery -A config beat   -l info              # 启动定时调度（可选）

Linux / macOS 可以用默认的 prefork 池：

    celery -A config worker -l info

【为什么 Windows 必须 -P solo】
Celery 默认的 prefork 池依赖 Unix 的 fork 系统调用，Windows 没有这个机制。
不指定 -P solo 时，Worker 进程会启动后无响应或直接挂起。
solo 池是单进程串行执行，功能正常，代价是不能并行——
对本项目（爬虫 + AI 推理都是长任务）完全可以接受。
"""

import os

from celery import Celery
from celery.schedules import crontab

# 让 Celery 能正确找到 Django 的配置
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# 创建 Celery 应用实例
app = Celery("biliinsight")

# 从 Django settings 中读取所有以 CELERY_ 开头的配置项
# namespace 的作用：settings 里写 CELERY_BROKER_URL，
# 这里自动映射为 app.conf.broker_url，省去逐项手动赋值
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现各 app 下的 tasks.py 文件
app.autodiscover_tasks()


# ---------------------------------------------------------------------------
# 定时任务调度
# ---------------------------------------------------------------------------
# 说明：生产环境建议改用 django_celery_beat 的数据库调度器，
# 可以在 Admin 后台动态增删任务。这里保留一份代码内声明作为默认值，
# 便于开发阶段快速验证。
app.conf.beat_schedule = {
    # 每 6 小时抓取一次各分区热门视频
    "crawl-hot-videos": {
        "task": "apps.spider.tasks.crawl_all_partitions",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"expires": 3600},  # 超过 1 小时未执行则丢弃，避免堆积
    },
    # 每天凌晨 3 点清理过期缓存
    "cleanup-expired-cache": {
        "task": "apps.common.tasks.cleanup_expired_cache",
        "schedule": crontab(minute=0, hour=3),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """用于验证 Celery 链路是否通畅的调试任务。

    用法：
        python -c "from config.celery import debug_task; debug_task.delay()"
    或在 Django shell 中执行，然后观察 Worker 终端是否打印本行。
    """
    print(f"Celery 链路正常，请求信息: {self.request!r}")

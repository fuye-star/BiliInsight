# -*- coding: utf-8 -*-
"""
构建向量索引命令。

【为什么需要它】
RAG 检索依赖向量库，而向量库不会自动跟随数据库变化：
   · 爬虫抓到新视频后，索引里没有 → 检索不到
   · 切换向量化后端后，新旧向量不在同一语义空间 → 检索结果混乱
因此需要在数据变更后重建索引。

用法：
    # 增量更新（保留已有向量，只补齐缺失的）
    python manage.py build_index

    # 全量重建（切换后端或数据大幅变动后必须这样做）
    python manage.py build_index --rebuild

    # 查看当前索引状态
    python manage.py build_index --status

    # 清空索引
    python manage.py build_index --clear

    # 指定向量化后端
    python manage.py build_index --rebuild --backend ollama
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.ai.embedding import get_embedder, reset_embedder_cache
from apps.ai.vector_store import (
    VectorStoreError,
    build_index,
    clear_index,
    get_index_stats,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """构建/查看/清空视频向量索引。"""

    help = "为视频构建向量索引，供 AI 助手的 RAG 检索使用"

    def add_arguments(self, parser):
        """定义参数。"""
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="清空集合后全量重建（切换向量后端或语料大幅变化时必须使用）",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="仅清空索引，不重建",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="仅查看索引状态",
        )
        parser.add_argument(
            "--backend",
            type=str,
            default="",
            help="指定向量化后端：local / ollama / dashscope，默认读 .env",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="每批写入条数，默认 100",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="限制处理的视频数（调试用），0 表示全部",
        )

    def handle(self, *args, **options):
        """命令入口。"""
        # ---- 仅查看状态 ----
        if options["status"]:
            self._show_status()
            return

        # ---- 仅清空 ----
        if options["clear"]:
            self.stdout.write("正在清空向量索引……")
            if clear_index():
                self.stdout.write(self.style.SUCCESS("索引已清空"))
            else:
                self.stdout.write(self.style.WARNING("索引不存在或清空失败"))
            return

        # ---- 构建 ----
        backend = (options["backend"] or "").strip() or None

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  BiliInsight 向量索引构建"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))

        # 预览将要使用的后端，让用户在跑之前就知道会发生什么
        try:
            embedder = get_embedder(backend, refresh=True)
        except Exception as exc:
            raise CommandError(f"初始化向量化后端失败：{exc}")

        info = embedder.describe()
        self.stdout.write(f"  向量化后端 : {info.get('backend')}")
        self.stdout.write(f"  是否可用   : {'是' if info.get('available') else '否'}")
        if info.get("model"):
            self.stdout.write(f"  模型       : {info['model']}")
        self.stdout.write(f"  向量维度   : {info.get('dim') or '运行时确定'}")
        self.stdout.write(f"  模式       : {'全量重建' if options['rebuild'] else '增量更新'}")
        if options["limit"]:
            self.stdout.write(f"  条数上限   : {options['limit']}")
        self.stdout.write("")

        # 检查是否有视频可索引
        from apps.videos.models import Video

        total_videos = Video.objects.count()
        if total_videos == 0:
            raise CommandError(
                "数据库中没有视频，无法构建索引。\n"
                "请先导入数据：\n"
                "  python manage.py seed_demo            （离线演示数据）\n"
                "  python manage.py crawl --partition 科技  （真实抓取）"
            )
        self.stdout.write(f"  数据库视频 : {total_videos} 条")

        # 切换后端时提醒必须全量重建
        if not options["rebuild"]:
            current = get_index_stats()
            if current.get("count") and current.get("backend") != info.get("backend"):
                self.stdout.write("")
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  当前索引使用的是 {current.get('backend')} 后端，"
                    f"而本次使用 {info.get('backend')}。\n"
                    f"     不同后端的向量不在同一语义空间，**必须**加 --rebuild 全量重建，"
                    f"否则检索结果会混乱。"
                ))
                raise CommandError("后端不一致，请加 --rebuild 重新构建")

        self.stdout.write("")
        self.stdout.write("  开始构建……")

        try:
            result = build_index(
                batch_size=options["batch_size"],
                rebuild=options["rebuild"],
                limit=options["limit"] or None,
            )
        except VectorStoreError as exc:
            raise CommandError(f"构建失败：{exc}") from exc
        except Exception as exc:
            logger.exception("构建向量索引异常")
            raise CommandError(f"构建异常：{exc}") from exc

        # ---- 结果 ----
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"  ✅ 索引构建完成：{result['indexed']} 条，"
            f"耗时 {result['elapsed']} 秒，维度 {result['dim']}"
        ))

        # ---- 构建完自动做一次检索自检 ----
        # 【为什么要自检】
        # 索引"写入成功"不代表"能检索到"——维度不匹配、后端未加载训练参数
        # 等问题都可能让检索返回空。这里用固定样例验证链路真的通了。
        self._self_check()

        self.stdout.write("")
        self._show_status()

    # -----------------------------------------------------------------
    def _self_check(self):
        """用几个样例查询验证检索链路。"""
        from apps.ai.vector_store import search

        self.stdout.write("")
        self.stdout.write("  检索自检：")

        samples = ["科技区的芯片评测", "美食做饭教程", "游戏攻略"]
        for query in samples:
            try:
                hits = search(query, top_k=2)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    [X] 「{query}」检索异常：{exc}"))
                continue

            if not hits:
                self.stdout.write(self.style.WARNING(f"    [!] 「{query}」无命中"))
                continue

            top = hits[0]
            self.stdout.write(
                f"    [OK] 「{query}」→ {top.get('title', '')[:24]}"
                f"（相似度 {top.get('similarity', 0):.3f}）"
            )

    # -----------------------------------------------------------------
    def _show_status(self):
        """打印索引状态。"""
        from apps.ai.llm import get_llm

        stats = get_index_stats()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))
        self.stdout.write(self.style.MIGRATE_HEADING("  RAG 链路状态"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 62))

        ready_mark = "✅" if stats.get("ready") else "❌"
        self.stdout.write(f"  {ready_mark} 索引就绪   : {stats.get('ready')}")
        self.stdout.write(f"     向量条数   : {stats.get('count', 0)}")
        self.stdout.write(f"     向量化后端 : {stats.get('backend')}")
        self.stdout.write(f"     向量维度   : {stats.get('dim')}")
        if stats.get("corpus_size"):
            self.stdout.write(f"     训练语料   : {stats['corpus_size']} 条")
        if stats.get("note"):
            self.stdout.write(f"     说明       : {stats['note']}")

        # 大模型状态
        llm = get_llm()
        llm_info = llm.describe()
        llm_mark = "✅" if llm_info.get("available") else "⚠️"
        self.stdout.write("")
        self.stdout.write(f"  {llm_mark} 大模型     : {llm_info.get('provider')}")
        if getattr(llm, "model", None):
            self.stdout.write(f"     模型       : {llm.model}")

        if llm.provider_name == "fallback":
            self.stdout.write(self.style.WARNING(
                "     （未接入大模型，将用检索结果直接回答）\n"
                "     启用方式见 README 7.2（通义千问）或 7.3（本地 Ollama）"
            ))

        self.stdout.write("")

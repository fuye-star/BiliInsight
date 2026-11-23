# -*- coding: utf-8 -*-
"""
ai 应用的视图层（阶段五：RAG 对话助手）。

【本模块接口】
    POST /api/ai/chat/            对话（支持 SSE 流式）
    GET  /api/ai/status/          RAG 链路状态（索引 + 大模型）
    POST /api/ai/build-index/     重建向量索引
    GET  /api/ai/history/         历史会话列表
    GET  /api/ai/history/{id}/    某会话的消息记录
    POST /api/ai/analyze-sentiment/   情感分析（阶段三已有）
    GET  /api/ai/sentiment-health/    情感后端自检（阶段三已有）

【为什么对话要支持两种返回方式】
  · SSE 流式：体感好，首字延迟低，适合真实使用
  · 普通 JSON：便于测试、便于 Apifox/Postman 调试、便于写单元测试
前端默认用流式，同时保留 JSON 模式作为降级与调试手段。
"""

import json
import logging
import time

from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.response import BusinessCode, error, success

from . import rag
from .models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# 单次提问长度上限，防止超长文本拖垮 Prompt 与向量化
MAX_QUERY_LENGTH = 500
# 单条消息入库长度上限
MAX_CONTENT_LENGTH = 5000


class ChatRequestSerializer(serializers.Serializer):
    """对话请求体。"""

    query = serializers.CharField(
        max_length=MAX_QUERY_LENGTH,
        help_text="用户问题，最长 500 字",
    )
    session_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="会话 ID；不传则新建会话（用于多轮对话）",
    )
    top_k = serializers.IntegerField(
        required=False, default=5, min_value=1, max_value=20,
        help_text="检索条数，默认 5",
    )
    partition = serializers.CharField(
        required=False, allow_blank=True, default="",
        help_text="限定分区，如「科技」",
    )
    stream = serializers.BooleanField(
        required=False, default=True,
        help_text="是否使用 SSE 流式返回；false 时返回完整 JSON",
    )
    save = serializers.BooleanField(
        required=False, default=True,
        help_text="是否保存对话记录（测试时可关闭）",
    )


class ChatView(APIView):
    """AI 对话助手（RAG）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="AI 对话（RAG 检索增强）",
        description=(
            "基于视频向量库的检索增强问答。\n\n"
            "**工作流程**：问题向量化 → 检索相关视频 → 组装 Prompt → 大模型生成 → 返回答案与引用来源。\n\n"
            "**两种返回模式**：\n"
            "- `stream=true`（默认）：SSE 流式，逐段返回，体感更好\n"
            "- `stream=false`：一次性返回完整 JSON，便于调试\n\n"
            "**降级说明**：若未接入大模型（Ollama 未启动且无 DashScope Key），"
            "会自动使用检索结果组织回答，并在 `fallback` 字段标记为 true。"
        ),
        tags=["ai"],
        request=ChatRequestSerializer,
    )
    def post(self, request):
        """POST /api/ai/chat/"""
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error("参数校验失败", code=1001, data=serializer.errors)

        data = serializer.validated_data
        query = data["query"].strip()
        session_id = data.get("session_id")
        top_k = data.get("top_k", 5)
        partition = (data.get("partition") or "").strip() or None
        use_stream = data.get("stream", True)
        save = data.get("save", True)

        # ---- 准备会话与历史 ----
        session, history = self._prepare_session(session_id, query, save)

        if use_stream:
            return self._stream_response(
                query, history, top_k, partition, session, save
            )

        return self._json_response(
            query, history, top_k, partition, session, save
        )

    # -----------------------------------------------------------------
    # 会话管理
    # -----------------------------------------------------------------
    @staticmethod
    def _prepare_session(session_id, query: str, save: bool):
        """取得或新建会话，并取回历史消息。

        参数:
            session_id: 会话 ID，为空则新建
            query:      本次提问（用于生成会话标题）
            save:       是否落库；False 时返回 (None, [])

        返回:
            (ChatSession 或 None, 历史消息列表)
        """
        if not save:
            return None, []

        session = None
        if session_id:
            session = ChatSession.objects.filter(pk=session_id).first()

        if session is None:
            # 用首条提问的前 30 字作标题，便于在历史列表里辨认
            session = ChatSession.objects.create(
                title=query[:30] or "新会话",
                provider="",
            )

        # 取最近 6 条消息作为多轮上下文（rag 侧还会再截断）
        recent = list(
            session.messages.order_by("-created_at")[:6]
        )[::-1]   # 反转为时间正序

        history = [{"role": m.role, "content": m.content} for m in recent]
        return session, history

    @staticmethod
    def _persist(session, query: str, answer_text: str, meta: dict):
        """把本轮问答写入数据库。

        参数:
            session:    会话实例
            query:      用户提问
            answer_text: AI 回答
            meta:       元信息（provider / sources / latency）
        """
        if session is None:
            return

        try:
            ChatMessage.objects.create(
                session=session,
                role="user",
                content=query[:MAX_CONTENT_LENGTH],
            )

            # 来源只存 bvid 列表（逗号分隔），避免 metadata 冗余
            sources = ",".join(
                s.get("bvid", "") for s in (meta.get("sources") or []) if s.get("bvid")
            )

            ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=answer_text[:MAX_CONTENT_LENGTH],
                sources=sources,
                model_name=meta.get("provider", ""),
                latency_ms=int(meta.get("latency_ms", 0)),
            )

            # 回填会话使用的 Provider（便于统计各 Provider 使用情况）
            if not session.provider:
                session.provider = meta.get("provider", "")
                session.save(update_fields=["provider", "updated_at"])
        except Exception as exc:
            # 落库失败不影响对话本身
            logger.warning("保存对话记录失败：%s", exc)

    # -----------------------------------------------------------------
    # 非流式返回
    # -----------------------------------------------------------------
    def _json_response(self, query, history, top_k, partition, session, save):
        """一次性返回完整回答。"""
        try:
            result = rag.answer(
                query,
                top_k=top_k,
                partition=partition,
                history=history,
            )
        except Exception as exc:
            logger.exception("RAG 问答失败")
            return error(
                f"AI 服务异常：{exc}",
                code=4001,
                http_status=500,
            )

        if save:
            self._persist(
                session,
                query,
                result.answer,
                {
                    "provider": result.provider,
                    "sources": result.sources,
                    "latency_ms": result.latency_ms,
                },
            )

        payload = result.to_dict()
        payload["session_id"] = session.pk if session else None
        return success(payload)

    # -----------------------------------------------------------------
    # SSE 流式返回
    # -----------------------------------------------------------------
    def _stream_response(self, query, history, top_k, partition, session, save):
        """SSE 流式返回。

        【SSE 数据格式】
        每帧形如：
            data: {"type":"chunk","data":"文本"}\n\n
        以空行分隔帧，前端用 EventSource 或 fetch + ReadableStream 解析。

        【为什么用 StreamingHttpResponse 而不是 DRF 的 Response】
        DRF 的 Response 需要完整的 data 才能渲染，
        而流式响应必须边生成边发送，因此直接用 Django 的流式响应。
        """

        def event_stream():
            """生成 SSE 数据帧。"""
            collected_answer = []
            meta: dict = {}

            try:
                for event in rag.answer_stream(
                    query,
                    top_k=top_k,
                    partition=partition,
                    history=history,
                ):
                    event_type = event.get("type")
                    payload = event.get("data")

                    if event_type == "meta":
                        meta = payload or {}
                    elif event_type == "chunk":
                        collected_answer.append(payload or "")
                    elif event_type == "done":
                        # 结束帧里带上完整答案与统计
                        merged = {**(payload or {}), **meta}
                        yield _sse({"type": "done", "data": merged})

                        if save:
                            self._persist(
                                session, query, "".join(collected_answer), merged
                            )
                        continue

                    yield _sse(event)

            except Exception as exc:
                logger.exception("SSE 流式问答异常")
                yield _sse({"type": "error", "data": f"AI 服务异常：{exc}"})

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream; charset=utf-8",
        )
        # 关闭缓冲，确保片段能即时推送
        response["Cache-Control"] = "no-cache"
        # 告诉 Nginx 不要缓冲（生产环境经反向代理时必需）
        response["X-Accel-Buffering"] = "no"
        # ⚠️ 注意：这里【不能】设置 Connection: keep-alive。
        # 它是 HTTP 逐跳头（hop-by-hop header），由服务器自行管理，
        # WSGI 规范明确禁止应用设置，否则 wsgiref 会抛：
        #   AssertionError: Hop-by-hop header, 'Connection: keep-alive', not allowed
        # 导致流式接口直接 500。这个 bug 会让 SSE 完全不可用。
        return response


def _sse(payload: dict) -> str:
    """把字典编码成一个 SSE 数据帧。

    参数:
        payload: 要发送的数据

    返回:
        形如 'data: {...}\\n\\n' 的字符串

    注意 ensure_ascii=False：中文直接输出，前端无需再解码转义序列。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class RagStatusView(APIView):
    """RAG 链路状态检查。

    前端据此提示用户"索引未构建"或"未接入大模型"，
    而不是让用户对着报错信息困惑。
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="RAG 链路状态",
        description="返回向量索引状态、大模型 Provider 状态，以及下一步操作建议。",
        tags=["ai"],
    )
    def get(self, request):
        """GET /api/ai/status/"""
        try:
            return success(rag.get_rag_status())
        except Exception as exc:
            logger.exception("读取 RAG 状态失败")
            return error(f"读取状态失败：{exc}", code=4001, http_status=500)


class BuildIndexView(APIView):
    """重建向量索引。

    【为什么要通过接口暴露】
    爬虫抓完新数据后需要更新索引，否则新视频检索不到。
    除命令行 `manage.py build_index` 外，也提供接口供前端一键触发。
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="重建向量索引",
        description=(
            "用数据库中的全部视频重建向量索引。\n\n"
            "⚠️ **重建是全量操作**（TF-IDF 需要全量语料重新训练），"
            "200 条视频约需数秒，数据量大时请耐心等待。\n\n"
            "重建后建议清理统计缓存，避免前端看到旧数据。"
        ),
        tags=["ai"],
        parameters=[
            OpenApiParameter("rebuild", bool, description="是否清空后重建，默认 true"),
        ],
    )
    def post(self, request):
        """POST /api/ai/build-index/"""
        from .vector_store import VectorStoreError, build_index

        # 默认清空重建：切换向量后端后增量追加会导致语义空间混乱
        rebuild = str(request.data.get("rebuild", "true")).lower() not in ("false", "0", "no")

        try:
            result = build_index(rebuild=rebuild)
        except VectorStoreError as exc:
            return error(f"构建索引失败：{exc}", code=4003, http_status=500)
        except Exception as exc:
            logger.exception("构建向量索引异常")
            return error(f"构建索引异常：{exc}", code=4003, http_status=500)

        # 索引变了，统计缓存里的数据可能过期，一并清理
        try:
            from apps.analytics.services import clear_analytics_cache

            clear_analytics_cache()
        except Exception:
            pass

        return success(result)


class HistoryListView(APIView):
    """历史会话列表。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="历史会话列表",
        description="返回最近的会话记录，供前端在侧边栏展示历史对话。",
        tags=["ai"],
    )
    def get(self, request):
        """GET /api/ai/history/?limit=20"""
        try:
            limit = min(int(request.query_params.get("limit", 20)), 100)
        except (TypeError, ValueError):
            limit = 20

        sessions = ChatSession.objects.order_by("-updated_at")[:limit]

        items = [
            {
                "id": s.pk,
                "title": s.title,
                "provider": s.provider,
                "message_count": s.messages.count(),
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]

        return success({"total": len(items), "items": items})


class HistoryDetailView(APIView):
    """某个会话的完整消息记录。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="会话消息记录",
        description="返回指定会话的全部消息（用户提问与 AI 回答）。",
        tags=["ai"],
    )
    def get(self, request, session_id: int):
        """GET /api/ai/history/{session_id}/"""
        session = ChatSession.objects.filter(pk=session_id).first()
        if session is None:
            return error(f"会话不存在：{session_id}", code=1004, http_status=404)

        messages = [
            {
                "id": m.pk,
                "role": m.role,
                "content": m.content,
                "sources": m.source_list,
                "model_name": m.model_name,
                "latency_ms": m.latency_ms,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages.order_by("created_at")
        ]

        return success(
            {
                "id": session.pk,
                "title": session.title,
                "provider": session.provider,
                "messages": messages,
            }
        )


# ===========================================================================
# 情感分析（阶段三实现）
# ===========================================================================
# 单次请求的文本条数上限。
# 【为什么要限制】批量接口若允许上传十万条文本，会长时间占用 worker，
# 相当于给了个简易 DoS 通道。限制后既够用又安全。
MAX_BATCH_SIZE = 200
# 单条文本长度上限（弹幕本身不会超过 500 字）
MAX_TEXT_LENGTH = 500


class AnalyzeSentimentRequestSerializer(serializers.Serializer):
    """情感分析请求体。

    支持两种传法：
        {"text": "太强了！"}                    分析单条
        {"texts": ["太强了！", "有点失望"]}      批量分析
    """

    text = serializers.CharField(
        required=False, allow_blank=True,
        help_text="单条文本；与 texts 二选一",
    )
    texts = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        help_text=f"文本列表，最多 {MAX_BATCH_SIZE} 条；与 text 二选一",
    )

    def validate(self, attrs):
        """校验：必须提供 text 或 texts 之一，且数量、长度合规。"""
        text = attrs.get("text")
        texts = attrs.get("texts")

        if not text and not texts:
            raise serializers.ValidationError("必须提供 text 或 texts 参数")

        if texts:
            if len(texts) > MAX_BATCH_SIZE:
                raise serializers.ValidationError(
                    f"texts 最多 {MAX_BATCH_SIZE} 条，当前 {len(texts)} 条"
                )
            for i, t in enumerate(texts):
                if len(t) > MAX_TEXT_LENGTH:
                    raise serializers.ValidationError(
                        f"第 {i + 1} 条文本超过 {MAX_TEXT_LENGTH} 字"
                    )

        if text and len(text) > MAX_TEXT_LENGTH:
            raise serializers.ValidationError(f"text 超过 {MAX_TEXT_LENGTH} 字")

        return attrs


class SentimentResultSerializer(serializers.Serializer):
    """情感分析结果（用于接口文档展示结构）。"""

    score = serializers.FloatField(help_text="情感分值 0-1，越大越正面")
    label = serializers.CharField(help_text="positive / neutral / negative")
    label_display = serializers.CharField(help_text="中文标签")
    emotion_tags = serializers.ListField(
        child=serializers.CharField(), help_text="情绪标签，如 高燃/搞笑/泪目"
    )


class AnalyzeSentimentView(APIView):
    """对文本执行情感分析。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="文本情感分析",
        description=(
            "对弹幕或评论文本做情感分析，返回情感分值、倾向标签与情绪标签。\n\n"
            f"支持单条（text）或批量（texts，最多 {MAX_BATCH_SIZE} 条）。\n\n"
            "情绪标签（高燃/搞笑/泪目/治愈等）由关键词表匹配得出，"
            "与情感倾向互补——倾向回答「好不好」，情绪回答「是什么感觉」。"
        ),
        tags=["ai"],
        request=AnalyzeSentimentRequestSerializer,
        responses={200: SentimentResultSerializer},
    )
    def post(self, request):
        """POST /api/ai/analyze-sentiment/"""
        # 延迟导入：避免 sentiment 模块的依赖问题影响对话功能
        from .sentiment import clean_text, get_analyzer

        serializer = AnalyzeSentimentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error(
                "参数校验失败",
                code=1001,
                data=serializer.errors,
            )

        validated = serializer.validated_data
        analyzer = get_analyzer()

        # ---- 批量模式 ----
        if validated.get("texts"):
            texts = [clean_text(t) for t in validated["texts"]]
            results = analyzer.analyze_batch(texts)
            return success(
                {
                    "backend": analyzer.backend_name,
                    "count": len(results),
                    "results": [
                        {"text": raw, **result}
                        for raw, result in zip(validated["texts"], results)
                    ],
                }
            )

        # ---- 单条模式 ----
        raw = validated["text"]
        result = analyzer.analyze(clean_text(raw))
        return success({"backend": analyzer.backend_name, **result, "text": raw})


class SentimentHealthView(APIView):
    """检查情感分析后端是否可用。

    用途：前端可在页面上提示"情感分析不可用，请先安装依赖"，
    而不是让用户对着空图表疑惑。
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="情感分析后端健康检查",
        description="返回当前使用的分析后端名称与可用状态。",
        tags=["ai"],
    )
    def get(self, request):
        """GET /api/ai/sentiment-health/"""
        from .sentiment import extract_emotion_tags, get_analyzer

        analyzer = get_analyzer()

        # 用一个已知正向的短句做自检，确认后端真的能跑通
        probe = analyzer.analyze("太棒了，非常喜欢！")

        return success(
            {
                "backend": analyzer.backend_name,
                "available": analyzer.available,
                "probe": probe,
                "emotion_keyword_count": len(extract_emotion_tags("太强了哈哈哈")),
            }
        )


# ===========================================================================
# 大模型提供商（用户自定义 API）
# ===========================================================================
# 【这组接口解决什么问题】
#   最初大模型只能通过 .env 配置，这在分发给别人后就完全不成立 ——
#   使用者既拿不到你的 .env，也不会改、改完还得重启。
#   有了这组接口，「AI 助手」页面上的「模型设置」按钮就能
#   让使用者自己选服务商、填自己的 Key、点一下测通、立即生效。
#
# 【安全约定】
#   · 任何响应都**不返回明文 Key**，只返回打码值（sk-8****cdef）
#   · 更新时若前端回传的是打码值，视为"未修改"，保持库里原值
#     （否则用户只改模型名就会把 Key 覆盖成废串）
class ProviderPresetsView(APIView):
    """可选的模型服务商预设（给前端的下拉框用）。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="模型服务商预设",
        description="返回内置的服务商类型及其默认接口地址、模型名、是否必需 Key。",
        tags=["ai"],
    )
    def get(self, request):
        """GET /api/ai/providers/presets/"""
        from . import providers

        return success(
            {
                "presets": providers.preset_list(),
                "default_type": providers.DEFAULT_TYPE,
            }
        )


class ProviderListView(APIView):
    """列出 / 新增模型提供商配置。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="模型提供商列表",
        description="返回全部配置（Key 已打码）。",
        tags=["ai"],
    )
    def get(self, request):
        """GET /api/ai/providers/"""
        from . import providers
        from .models import ModelProvider

        items = [
            providers.serialize_provider(cfg) for cfg in ModelProvider.objects.all()
        ]
        return success(
            {
                "total": len(items),
                "items": items,
                "active_id": next(
                    (cfg["id"] for cfg in items if cfg["is_active"]), None
                ),
            }
        )

    @extend_schema(
        summary="新增模型提供商",
        description=(
            "保存一条自己的模型配置。API Key 会被加密存储。\n\n"
            "如果这是第一条配置，会自动设为启用。"
        ),
        tags=["ai"],
    )
    def post(self, request):
        """POST /api/ai/providers/"""
        from . import providers
        from .crypto import KeyCryptoError
        from .llm import reset_llm_cache
        from .models import ModelProvider

        cfg = ModelProvider()
        try:
            providers.save_provider(cfg, request.data, partial=False)
        except providers.ProviderConfigError as exc:
            return error(str(exc), code=BusinessCode.BAD_REQUEST)
        except KeyCryptoError as exc:
            logger.error("加密保存 API Key 失败：%s", exc)
            return error(
                "加密保存失败，请检查运行环境（缺少 cryptography 库）",
                code=BusinessCode.SERVER_ERROR,
                http_status=500,
            )

        # 第一条配置自动启用，省掉用户"保存完发现没生效"的困惑
        if not ModelProvider.objects.filter(is_active=True).exists():
            cfg.is_active = True

        cfg.save()
        reset_llm_cache()
        logger.info("新增模型配置：%s（%s）", cfg.name, cfg.provider_type)
        return success(providers.serialize_provider(cfg), message="已保存")


class ProviderDetailView(APIView):
    """修改 / 删除单条配置。"""

    permission_classes = [AllowAny]

    def _get(self, pk):
        from .models import ModelProvider

        return ModelProvider.objects.filter(pk=pk).first()

    @extend_schema(summary="修改模型提供商", tags=["ai"])
    def patch(self, request, pk: int):
        """PATCH /api/ai/providers/<id>/"""
        from . import providers
        from .crypto import KeyCryptoError
        from .llm import reset_llm_cache

        cfg = self._get(pk)
        if cfg is None:
            return error("配置不存在", code=BusinessCode.NOT_FOUND, http_status=404)

        try:
            providers.save_provider(cfg, request.data, partial=True)
        except providers.ProviderConfigError as exc:
            return error(str(exc), code=BusinessCode.BAD_REQUEST)
        except KeyCryptoError as exc:
            logger.error("加密保存 API Key 失败：%s", exc)
            return error(
                "加密保存失败，请检查运行环境（缺少 cryptography 库）",
                code=BusinessCode.SERVER_ERROR,
                http_status=500,
            )

        cfg.save()
        reset_llm_cache()
        return success(providers.serialize_provider(cfg), message="已更新")

    @extend_schema(summary="删除模型提供商", tags=["ai"])
    def delete(self, request, pk: int):
        """DELETE /api/ai/providers/<id>/"""
        from .llm import reset_llm_cache
        from .models import ModelProvider

        cfg = self._get(pk)
        if cfg is None:
            return error("配置不存在", code=BusinessCode.NOT_FOUND, http_status=404)

        was_active = cfg.is_active
        cfg.delete()

        # 删掉的是当前启用的那条：自动接管给剩下的第一条，
        # 否则 AI 会突然退化成"未经配置"的状态，用户会以为删坏了。
        if was_active:
            replacement = ModelProvider.objects.first()
            if replacement is not None:
                replacement.activate()

        reset_llm_cache()
        return success({"deleted": pk}, message="已删除")


class ProviderActivateView(APIView):
    """把某条配置设为当前启用。"""

    permission_classes = [AllowAny]

    @extend_schema(summary="启用某条模型配置", tags=["ai"])
    def post(self, request, pk: int):
        """POST /api/ai/providers/<id>/activate/"""
        from . import providers
        from .llm import reset_llm_cache
        from .models import ModelProvider

        cfg = ModelProvider.objects.filter(pk=pk).first()
        if cfg is None:
            return error("配置不存在", code=BusinessCode.NOT_FOUND, http_status=404)

        cfg.activate()
        reset_llm_cache()
        logger.info("已切换大模型配置：%s", cfg.name)
        return success(providers.serialize_provider(cfg), message=f"已切换到「{cfg.name}」")


class ProviderTestView(APIView):
    """测试某条配置能否真正调通。"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="测试模型配置连通性",
        description=(
            "发起一次极小的真实调用（max_tokens=16），验证 Key、地址、模型名是否都正确。\n\n"
            "之所以用真实调用而不是 ping：常见失败原因里"
            "「模型名填错」「余额不足」都只有真实调用才能发现。"
        ),
        tags=["ai"],
    )
    def post(self, request, pk: int):
        """POST /api/ai/providers/<id>/test/"""
        from django.utils import timezone

        from . import providers
        from .llm import reset_llm_cache
        from .models import ModelProvider

        cfg = ModelProvider.objects.filter(pk=pk).first()
        if cfg is None:
            return error("配置不存在", code=BusinessCode.NOT_FOUND, http_status=404)

        result = providers.test_provider(cfg)

        # 把测试结果落库，界面上可以显示"上次测试失败"
        cfg.last_test_ok = result["ok"]
        cfg.last_test_at = timezone.now()
        cfg.last_test_message = str(result["message"])[:300]
        cfg.save(update_fields=["last_test_ok", "last_test_at", "last_test_message", "updated_at"])
        reset_llm_cache()

        return success(result, message=result["message"])

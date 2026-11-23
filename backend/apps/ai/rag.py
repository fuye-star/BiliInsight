# -*- coding: utf-8 -*-
"""
RAG（检索增强生成）编排。

【RAG 要解决的核心问题】
大模型不知道我们数据库里有什么视频。若直接问"最近科技区什么视频最火"，
模型只能编造（幻觉）。RAG 的做法是：

    用户提问
      ↓
    ① 向量检索：从视频库里找出语义最相关的 K 条
      ↓
    ② 组装 Prompt：把检索结果作为"参考资料"塞进提示词
      ↓
    ③ 大模型生成：要求模型【仅依据参考资料】回答
      ↓
    ④ 返回答案 + 引用来源（可溯源，降低幻觉）

【本模块的设计要点】
  1. **Prompt 里明确约束"只依据资料回答"**，并允许说"不知道"，
     这比让模型自由发挥可信得多
  2. **强制标注引用来源**（[1] [2]），前端可展示"参考了哪些视频"
  3. **意图识别**：不同问法用不同检索策略
     （"最火"应偏向高播放量，"推荐"应偏向相似度）
  4. **上下文注入**：RetrievalOnlyLLM 兜底方案需要拿到检索结果，
     这里统一注入，避免兜底 Provider 自己去查向量库
"""

import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional

from .llm import BaseLLM, RetrievalOnlyLLM, get_llm
from .vector_store import get_index_stats, search

logger = logging.getLogger(__name__)


# ===========================================================================
# 系统提示词
# ===========================================================================
# 【为什么要写得这么细】
# 提示词是 RAG 效果的关键。这几条约束分别解决一个具体问题：
#   · "仅依据参考资料" -> 抑制幻觉
#   · "允许说不知道"   -> 避免强行编造（模型在被要求必须回答时最容易瞎编）
#   · "标注引用编号"   -> 可溯源，也便于用户核对
#   · "不要输出思考过程" -> deepseek-r1 这类推理模型会把思维链也吐出来，
#                          对终端用户是噪声（本机装的正是 deepseek-r1:8b）
SYSTEM_PROMPT = """你是 BiliInsight 的 AI 数据分析助手，专门帮助用户分析B站视频数据、发现优质内容、辅助创作者选题。

回答要求：
1. **仅依据下面提供的「参考资料」回答**，不要编造资料中不存在的信息。
2. 如果参考资料不足以回答，请明确说明「现有数据无法回答这个问题」，并建议用户可以换个问法或补充数据。
3. 引用具体视频时，用 [1] [2] 这样的编号标注来源，编号对应参考资料的序号。
4. 回答要简洁有条理，可用短段落或列表。涉及数据时给出具体数字（如播放量、互动率）。
5. 直接输出回答内容，不要输出你的思考过程或推导步骤。

你的语气应当专业、友好，像一个熟悉B站生态的数据分析师。"""


# ===========================================================================
# 意图类型
# ===========================================================================
class Intent:
    """查询意图类型常量。"""

    RANKING = "ranking"        # 排行类："最火"、"播放量最高"、"排行"
    RECOMMEND = "recommend"    # 推荐类："推荐"、"适合"、"类似"
    TREND = "trend"            # 趋势类："最近"、"这段时间"、"变化"
    TOPIC = "topic"            # 选题类："做什么"、"选题"、"什么方向"
    GENERAL = "general"        # 其他


#: 意图关键词表（命中即归类，顺序即优先级）
INTENT_KEYWORDS: list[tuple[str, tuple]] = [
    (Intent.TOPIC, ("选题", "做什么", "拍什么", "什么方向", "什么类型", "内容方向")),
    (Intent.RANKING, ("最火", "排行", "排名", "最高", "最热", "最多", "top", "榜")),
    (Intent.TREND, ("最近", "近期", "这段时间", "趋势", "变化", "这两天", "本周")),
    (
        Intent.RECOMMEND,
        (
            "推荐", "适合", "想看", "找点", "有没有", "类似", "下饭",
            # "有什么好看的视频"、"值得看"这类问法同样是在求推荐，
            # 实测发现缺少这两个词会被误判为 general
            "好看", "值得看", "值得一看",
        ),
    ),
]


def detect_intent(query: str) -> str:
    """识别查询意图。

    参数:
        query: 用户问题

    返回:
        意图常量之一

    【为什么需要意图识别】
    不同意图应侧重不同的检索与排序策略：
      · "最火"     -> 检索后按播放量重排，而不是纯按相似度
      · "推荐适合下饭的" -> 侧重语义相似度与互动率
      · "选题建议" -> 需要分区维度的聚合视角
    这里先识别意图，供 retrieve() 调整策略。
    """
    if not query:
        return Intent.GENERAL

    lowered = query.lower()
    for intent, keywords in INTENT_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return intent
    return Intent.GENERAL


# ===========================================================================
# 结果结构
# ===========================================================================
@dataclass
class RagResult:
    """一次 RAG 问答的结果。"""

    answer: str
    sources: list[dict] = field(default_factory=list)
    provider: str = ""
    intent: str = Intent.GENERAL
    retrieved: int = 0
    latency_ms: int = 0
    # 是否走了兜底方案（未接入大模型）
    fallback: bool = False

    def to_dict(self) -> dict:
        """转为可序列化的字典。"""
        return {
            "answer": self.answer,
            "sources": self.sources,
            "provider": self.provider,
            "intent": self.intent,
            "retrieved": self.retrieved,
            "latency_ms": self.latency_ms,
            "fallback": self.fallback,
        }


# ===========================================================================
# ① 检索
# ===========================================================================
def retrieve(
    query: str,
    *,
    top_k: int = 5,
    partition: Optional[str] = None,
) -> list[dict]:
    """按意图调整策略后执行向量检索。

    参数:
        query:     用户问题
        top_k:     召回条数
        partition: 可选分区过滤

    返回:
        vector_store.search() 的结果列表
    """
    intent = detect_intent(query)

    # 排行类问题多召回一些，便于重排后取真正的高播放量视频
    actual_k = top_k * 3 if intent == Intent.RANKING else top_k

    hits = search(query, top_k=actual_k, partition=partition)

    # ---- 排行意图：按播放量重排 ----
    # 【为什么不能纯靠向量相似度排序】
    # 向量相似度衡量"内容相关"，不衡量"火不火"。
    # 用户问"最火的视频"，需要的是相关 + 高播放，因此重排。
    if intent == Intent.RANKING and hits:
        hits = sorted(hits, key=lambda h: h.get("view_count", 0), reverse=True)

    # ---- 推荐意图：相关度与互动率加权 ----
    # 推荐场景既要相关，也希望内容质量好（互动率高）
    if intent == Intent.RECOMMEND and hits:
        hits = sorted(
            hits,
            key=lambda h: h.get("similarity", 0) * 0.7
            + min(h.get("interaction_rate", 0) * 10, 0.3),
            reverse=True,
        )

    return hits[:top_k]


# ===========================================================================
# ② 组装 Prompt
# ===========================================================================
def build_context(hits: list[dict]) -> str:
    """把检索结果格式化成参考资料文本。

    参数:
        hits: 检索命中的视频

    返回:
        供 Prompt 使用的参考资料文本

    【格式设计】
    每条资料都带上关键数据（分区/UP主/播放量/互动率），
    这样模型回答时能引用具体数字，而不是泛泛而谈"很受欢迎"。
    编号 [1] [2] 与 sources 列表顺序严格对应，保证引用可溯源。
    """
    if not hits:
        return "（没有检索到相关视频数据）"

    lines = []
    for i, hit in enumerate(hits, start=1):
        view = hit.get("view_count", 0)
        like = hit.get("like_count", 0)
        rate = hit.get("interaction_rate", 0.0)

        lines.append(
            f"[{i}] {hit.get('title', '无标题')}\n"
            f"    分区：{hit.get('partition') or '未分类'}"
            f"　UP主：{hit.get('up_name') or '未知'}\n"
            f"    播放量：{view:,}　点赞：{like:,}　互动率：{rate:.2%}\n"
            f"    BV号：{hit.get('bvid', '')}"
        )

    return "\n\n".join(lines)


def build_prompt(query: str, hits: list[dict], *, history: Optional[list] = None) -> str:
    """组装完整提示词。

    参数:
        query:   用户问题
        hits:    检索命中
        history: 可选的多轮对话历史 [{"role": "user"/"assistant", "content": "..."}]

    返回:
        完整 Prompt
    """
    sections = []

    # ---- 多轮对话历史（取最近 3 轮，避免 Prompt 过长）----
    if history:
        recent = history[-6:]   # 3 轮 = 3 问 + 3 答
        history_text = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}：{m.get('content', '')[:200]}"
            for m in recent
        )
        sections.append(f"【对话历史】\n{history_text}")

    # ---- 参考资料 ----
    sections.append(f"【参考资料】（按相关度排序）\n{build_context(hits)}")

    # ---- 用户问题 ----
    sections.append(f"【用户问题】\n{query}")

    sections.append("请依据上述参考资料回答用户问题，并标注引用编号。")

    return "\n\n".join(sections)


# ===========================================================================
# ③ 生成
# ===========================================================================
def _prepare(llm: BaseLLM, hits: list[dict]) -> None:
    """给需要上下文的 Provider 注入检索结果。

    RetrievalOnlyLLM（兜底方案）不调用大模型，
    它需要直接拿到检索结果来组织回答，因此在这里注入。
    这样兜底逻辑不会耦合到向量库，保持职责清晰。
    """
    if isinstance(llm, RetrievalOnlyLLM):
        llm.set_context(hits)


def answer(
    query: str,
    *,
    top_k: int = 5,
    partition: Optional[str] = None,
    history: Optional[list] = None,
    provider: Optional[str] = None,
) -> RagResult:
    """执行完整的 RAG 问答（非流式）。

    参数:
        query:     用户问题
        top_k:     检索条数
        partition: 可选分区过滤
        history:   多轮对话历史
        provider:  指定 Provider（默认读配置）

    返回:
        RagResult
    """
    import time

    started = time.monotonic()

    intent = detect_intent(query)

    # ---- ① 检索 ----
    hits = retrieve(query, top_k=top_k, partition=partition)

    # ---- ② 组装 Prompt ----
    prompt = build_prompt(query, hits, history=history)

    # ---- ③ 生成 ----
    llm = get_llm(provider)
    _prepare(llm, hits)

    try:
        text = llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.7, max_tokens=1024)
    except Exception as exc:
        # 大模型调用失败不应让整个对话崩掉，降级为检索结果
        logger.error("大模型生成失败，降级为检索结果：%s", exc)
        fallback = RetrievalOnlyLLM()
        fallback.set_context(hits)
        text = fallback.generate("", system=SYSTEM_PROMPT)
        llm = fallback

    latency = int((time.monotonic() - started) * 1000)

    return RagResult(
        answer=text,
        sources=hits,
        provider=llm.provider_name,
        intent=intent,
        retrieved=len(hits),
        latency_ms=latency,
        fallback=llm.provider_name == "fallback",
    )


def answer_stream(
    query: str,
    *,
    top_k: int = 5,
    partition: Optional[str] = None,
    history: Optional[list] = None,
    provider: Optional[str] = None,
) -> Iterator[dict]:
    """执行流式 RAG 问答。

    逐段 yield 事件字典，便于上层转成 SSE：
        {"type": "meta",    "data": {...}}     元信息（来源、provider）
        {"type": "chunk",   "data": "文本片段"}  正文片段
        {"type": "done",    "data": {...}}     结束与统计
        {"type": "error",   "data": "错误信息"}

    【为什么先发 meta】
    前端需要在正文开始出现前就渲染"参考来源"区域，
    否则用户会先看到文字再看到来源，体验割裂。
    """
    import time

    started = time.monotonic()
    intent = detect_intent(query)

    # ---- 检索 ----
    try:
        hits = retrieve(query, top_k=top_k, partition=partition)
    except Exception as exc:
        logger.error("检索失败：%s", exc)
        hits = []

    # 先推送元信息（来源列表 + 使用的 Provider）
    llm = get_llm(provider)
    yield {
        "type": "meta",
        "data": {
            "intent": intent,
            "provider": llm.provider_name,
            "fallback": llm.provider_name == "fallback",
            "sources": hits,
            "retrieved": len(hits),
        },
    }

    # ---- 组装 + 生成 ----
    prompt = build_prompt(query, hits, history=history)
    _prepare(llm, hits)

    collected: list[str] = []
    try:
        for piece in llm.generate_stream(
            prompt, system=SYSTEM_PROMPT, temperature=0.7, max_tokens=1024
        ):
            collected.append(piece)
            yield {"type": "chunk", "data": piece}
    except Exception as exc:
        logger.error("流式生成失败：%s", exc)
        # 降级：用检索结果兜底，保证用户仍能得到回答
        fallback = RetrievalOnlyLLM()
        fallback.set_context(hits)
        text = fallback.generate("", system=SYSTEM_PROMPT)
        collected = [text]
        yield {"type": "chunk", "data": text}
        llm = fallback

    yield {
        "type": "done",
        "data": {
            "answer": "".join(collected),
            "provider": llm.provider_name,
            "latency_ms": int((time.monotonic() - started) * 1000),
        },
    }


# ===========================================================================
# ④ 索引状态
# ===========================================================================
def get_rag_status() -> dict:
    """返回 RAG 链路的整体状态，供前端提示。

    返回:
        {
          "index": {...},              # 向量索引状态
          "llm": {...},                # 大模型状态
          "ready": bool,               # 是否可以正常问答
          "hint": "..."                # 给用户的下一步建议
        }
    """
    index_stats = get_index_stats()

    llm = get_llm()
    llm_info = llm.describe()

    # 把实际使用的模型名附上，便于用户确认自己配的是哪个模型
    model_name = getattr(llm, "model", "")
    if model_name:
        llm_info["model"] = model_name

    # ---- 补充"这个配置是从哪来的" ----
    # 前端要据此决定提示语：是"还没配置"、"配置了但连不上"，还是"已就绪"。
    # 三种情况给用户的下一步动作完全不同，混在一起提示等于没提示。
    active_provider = None
    provider_count = 0
    try:
        from .models import ModelProvider

        provider_count = ModelProvider.objects.count()
        active_provider = ModelProvider.get_active()
    except Exception:  # noqa: BLE001
        # 表还没迁移（例如首次启动的极早期），按"未配置"处理
        pass

    llm_info["provider_count"] = provider_count
    if active_provider is not None:
        llm_info["source"] = "database"
        llm_info["config_name"] = active_provider.name
        llm_info["config_id"] = active_provider.pk
    elif llm.provider_name == "fallback":
        llm_info["source"] = "none"
    else:
        llm_info["source"] = "settings"

    ready = index_stats.get("ready", False)

    # 组装提示语，明确告诉用户缺什么、怎么补
    #
    # 【注意判断条件】
    #   不能只看 `llm.available`：兜底的 RetrievalOnlyLLM 本身就是"永远可用"的
    #   （它不需要任何外部服务），因此 available 恒为 True。
    #   若只用 available 判断，就配不上大模型时也会显示"已就绪" ——
    #   实测就踩过这个坑：干净机器上 provider=fallback 却提示"AI 助手已就绪"。
    #   所以必须同时看 provider_name 是否退化成了 fallback。
    using_fallback = llm.provider_name == "fallback"

    if not ready:
        hint = "向量索引尚未构建，请执行：python manage.py build_index"
    elif using_fallback or not llm.available:
        if provider_count == 0:
            hint = (
                "还没有配置大模型。点右下角「模型设置」填入你自己的 API Key 即可接入；"
                "不配置也能用，只是回答会退化成检索结果的直接罗列。"
            )
        else:
            hint = (
                "已配置大模型但当前不可用。请到「模型设置」里点「测试连接」查看具体原因"
                "（常见是 Key 无效、余额不足或模型名填错）。"
            )
    else:
        hint = "AI 助手已就绪"

    return {
        "index": index_stats,
        "llm": llm_info,
        "ready": ready,
        "fallback": llm.provider_name == "fallback",
        "hint": hint,
    }

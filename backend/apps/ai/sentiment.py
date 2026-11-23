# -*- coding: utf-8 -*-
"""
情感分析模块 —— 可插拔的后端设计。

【设计目标（对应 rdme.txt 的复用性要求）】
> 若使用 PaddleNLP 做情感分析……AI 助手支持多模型 Provider 切换

情感分析的业务逻辑（阈值判定、情绪分类、批量回填）与具体算法库解耦：
    SentimentAnalyzer      抽象接口，定义 analyze() / analyze_batch()
      ├── SnowNLPAnalyzer  默认实现，纯 Python，支持 Python 3.13
      └── PaddleNLPAnalyzer 进阶实现，需 Python 3.11/3.12（见 readme）

切换方式：改 .env 中的 SENTIMENT_BACKEND 即可，无需改动调用方代码。

【为什么默认用 SnowNLP 而不是 PaddleNLP】
实测 PaddleNLP 2.8.1 依赖的 tool-helpers 在 PyPI 上取不到任何可用版本，
因此在 Python 3.13 上无法安装（这是上游依赖问题，非环境配置错误）。
SnowNLP 是纯 Python 实现，零编译依赖，对弹幕这类短文本效果足够。

【分值约定】
所有实现统一返回 [0, 1] 区间的情感分值：
    越接近 1 越正面，越接近 0 越负面，0.5 附近为中性。
统一约定后，更换后端不会影响已有的阈值逻辑与前端展示。
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 判定阈值
# ---------------------------------------------------------------------------
# 弹幕文本很短（通常 2-10 字），情感信号弱，
# 因此中性区间设得比较宽（0.4-0.6），避免把中性弹幕误判为极端情感。
POSITIVE_THRESHOLD = 0.60
NEGATIVE_THRESHOLD = 0.40


# ---------------------------------------------------------------------------
# 情绪标签关键词表
# ---------------------------------------------------------------------------
# 情感倾向（正向/负向）表示"好不好"，情绪标签表示"是什么感觉"。
# 两者互补：一条弹幕可以是"正向 + 搞笑"，也可以是"正向 + 感动"。
#
# 关键词表可自由扩充，这是纯数据配置，不影响代码逻辑。
EMOTION_KEYWORDS: dict[str, tuple] = {
    "高燃": (
        "燃", "太强", "牛逼", "牛批", "无敌", "封神", "炸裂", "起飞",
        "永远的神", "yyds", "震撼", "热血", "冲", "顶", "绝了",
    ),
    "搞笑": (
        "哈哈", "笑死", "笑喷", "233", "搞笑", "逗", "乐死", "笑不活",
        "绷不住", "太好笑", "哈哈哈哈哈", "笑", "蚌埠",
    ),
    "泪目": (
        "泪目", "哭了", "看哭", "眼泪", "感动", "破防", "泪奔", "哽咽",
        "太感人", "绷不住泪", "泪",
    ),
    "治愈": (
        "治愈", "温暖", "舒服", "放松", "心安", "好温柔", "舒服了",
        "惬意", "美好",
    ),
    "惊叹": (
        "卧槽", "我靠", "天呐", "天啊", "妈呀", "震撼", "厉害", "强啊",
        "跪了", "膜拜", "大神",
    ),
    "吐槽": (
        "吐槽", "无力", "无语", "离谱", "什么鬼", "太草", "草", "有毒",
        "麻了", "裂开",
    ),
    "失望": (
        "失望", "不行", "退步", "不如", "拉胯", "难看", "水", "敷衍",
        "无聊", "没意思",
    ),
    "疑问": (
        "？", "?", "为什么", "怎么", "啥", "求问", "不懂", "没懂",
        "求教", "请教",
    ),
    "打卡": (
        "打卡", "前排", "沙发", "签到", "来了", "路过", "第一", "报道",
    ),
}

# 每条弹幕最多保留几个情绪标签（避免一条弹幕命中太多关键词导致统计失真）
MAX_EMOTION_TAGS = 3


# ---------------------------------------------------------------------------
# 情感关键词表（用于修正模型分值）
# ---------------------------------------------------------------------------
# 【为什么需要修正】
# 实测发现 SnowNLP 会把 B站 的典型正向弹幕判成负向：
#     "太强了！"  ->  模型分值 0.154（负向）  显然是误判
# 原因是 SnowNLP 用中文电商评论语料训练，不认识弹幕里的网络用语
# （"太强""yyds""绷不住"等）。
#
# 解决办法：模型分值 + 关键词加权，两者互补。
#   · 模型      擅长捕捉一般的褒贬语气
#   · 关键词表  擅长捕捉领域特有的梗与网络用语，且完全可解释
#
# 【分级设计】
# 关键词分两档，因为语气强度差异很大：
#   · 强关键词（称赞/差评意图明确，如"太强""垃圾"）—— 调整幅度大
#   · 弱关键词（语气较轻，如"好""差"）—— 调整幅度小
# 若一律用同一个权重，为了让"太强了"翻正就得把权重调得很大，
# 那"好"这类弱词又会被过度放大。

# 强正向：意图明确是称赞
STRONG_POSITIVE_KEYWORDS: tuple = (
    "太强", "牛逼", "牛批", "无敌", "封神", "炸裂", "起飞", "永远的神",
    "yyds", "满分", "绝了", "大神", "牛逼", "强啊",
    "干货", "学到了", "受益匪浅", "涨知识",
    "辛苦", "三连", "已三连", "关注了", "收藏了",
    "太棒", "爱了", "泪目", "笑死", "笑喷", "乐死", "绷不住",
)

# 弱正向：褒义但语气温和，也可能是反讽（需要模型辅助判断）
WEAK_POSITIVE_KEYWORDS: tuple = (
    "厉害", "优秀", "支持", "感谢", "谢谢", "喜欢", "治愈", "温暖",
    "感动", "热血", "燃", "哈哈", "搞笑", "逗", "妙", "赞", "香",
    "学到了", "有用", "清楚", "明白", "专业", "清晰", "好", "棒",
)

# 强负向：意图明确是差评
STRONG_NEGATIVE_KEYWORDS: tuple = (
    "失望", "拉胯", "垃圾", "敷衍", "标题党", "太难听", "翻车",
    "什么鬼", "离谱", "有毒", "裂开", "退钱", "骗",
    # 否定式表达：模型对"没/不 + 动词"结构识别很差，需显式列出
    # （实测 "没看懂，求讲解" 被判成正向 0.795，就是因为模型只看到"讲"）
    "没看懂", "看不懂", "听不懂", "不明白", "没意思", "没讲清楚",
    "不会吧", "不行啊", "太差",
)

# 弱负向：贬义但语气温和
WEAK_NEGATIVE_KEYWORDS: tuple = (
    "不如", "难看", "无聊", "退步", "吐槽", "无语", "麻了",
    "讲错", "糊", "卡", "水", "差", "烂", "菜", "坑", "慢", "吵",
    "太短", "太长", "跳过",
)

# 调整幅度（见 _apply_keyword_adjustment 的说明）
STRONG_KEYWORD_WEIGHT = 0.32
WEAK_KEYWORD_WEIGHT = 0.06
MAX_KEYWORD_ADJUSTMENT = 0.35

# 强关键词的"兜底区间"。
# 【为什么需要这个而不只是加权】
# 实测表明加权无法可靠修正模型的严重误判：
#     "太强了！"  SnowNLP 原始分值仅 0.154，加 0.32 也只到 0.474，
#                 仍落在中性区，判定错误。
# 原因是这类网络用语的语义与电商语料差距太大，模型给的基础分本身就跑偏了。
#
# 因此对"意图明确"的强关键词采用更硬的规则：
#   · 命中强正向且无强负向  ->  分值不低于 0.65（保证判为正向）
#   · 命中强负向且无强正向  ->  分值不高于 0.35（保证判为负向）
# 若正负强关键词同时命中（如"标题党，太失望了"），则不加兜底，
# 交由加权规则处理——这类矛盾表达本就该由模型权衡。
STRONG_POSITIVE_FLOOR = 0.65
STRONG_NEGATIVE_CEILING = 0.35

# 分值上下限：保留"几乎没有绝对的正负"这一语义（弹幕常带反讽与玩笑）
MIN_SCORE = 0.10
MAX_SCORE = 0.90


def _apply_keyword_adjustment(score: float, text: str) -> float:
    """用情感关键词修正模型给出的分值。

    参数:
        score: 模型输出的原始分值 [0,1]
        text:  清洗后的文本

    返回:
        修正后的分值 [MIN_SCORE, MAX_SCORE]

    策略（两步）：
        1. **加权调整**：强关键词 ±0.32，弱关键词 ±0.06，
           总调整量夹在 ±0.35 内。这处理一般情况。
        2. **强关键词兜底**：若意图明确（只命中强正向或只命中强负向），
           直接把分值拉进对应的判定区间。
           这处理模型严重跑偏的情况（如"太强了！"被打了 0.154）。

    【为什么弱关键词权重压得这么低】
    实测发现"好""差"这类弱词噪声很大——"没看懂，求讲解"这类
    明确负向的文本里也可能出现"好"字，权重高了反而把判定带偏。
    因此弱关键词只做轻微调整，不参与兜底。
    """
    lowered = text.lower()

    strong_pos = [kw for kw in STRONG_POSITIVE_KEYWORDS if kw.lower() in lowered]
    weak_pos = [kw for kw in WEAK_POSITIVE_KEYWORDS if kw.lower() in lowered]
    strong_neg = [kw for kw in STRONG_NEGATIVE_KEYWORDS if kw.lower() in lowered]
    weak_neg = [kw for kw in WEAK_NEGATIVE_KEYWORDS if kw.lower() in lowered]

    # ---- 第一步：加权调整 ----
    adjustment = (
        len(strong_pos) * STRONG_KEYWORD_WEIGHT
        + len(weak_pos) * WEAK_KEYWORD_WEIGHT
        - len(strong_neg) * STRONG_KEYWORD_WEIGHT
        - len(weak_neg) * WEAK_KEYWORD_WEIGHT
    )
    adjustment = max(-MAX_KEYWORD_ADJUSTMENT, min(adjustment, MAX_KEYWORD_ADJUSTMENT))
    adjusted = score + adjustment

    # ---- 第二步：强关键词兜底（仅当方向明确时生效）----
    if strong_pos and not strong_neg:
        # 有明确称赞，不可能整体是负向
        adjusted = max(adjusted, STRONG_POSITIVE_FLOOR)
    elif strong_neg and not strong_pos:
        # 有明确差评，不可能整体是正向
        adjusted = min(adjusted, STRONG_NEGATIVE_CEILING)

    return max(MIN_SCORE, min(adjusted, MAX_SCORE))


# ===========================================================================
# 抽象接口
# ===========================================================================
class SentimentAnalyzer(ABC):
    """情感分析器抽象基类。

    子类只需实现 _score()，批量处理、情绪分类、异常兜底由基类统一提供。
    """

    # 子类覆盖：后端标识，用于日志与结果记录
    backend_name = "base"

    def __init__(self):
        """初始化时记录是否可用，避免每次调用都重复判断依赖。"""
        self.available = self._check_dependency()

    @abstractmethod
    def _check_dependency(self) -> bool:
        """检查后端依赖是否已安装。返回 False 时 analyze 会直接返回中性值。"""
        raise NotImplementedError

    @abstractmethod
    def _score(self, text: str) -> Optional[float]:
        """计算单条文本的情感分值。

        参数:
            text: 待分析文本

        返回:
            [0, 1] 的分值；无法计算时返回 None
        """
        raise NotImplementedError

    # -----------------------------------------------------------------
    # 对外接口
    # -----------------------------------------------------------------
    def analyze(self, text: str) -> dict:
        """分析单条文本。

        参数:
            text: 弹幕或评论内容

        返回:
            {
              "score": 0.83,                    # 情感分值 [0,1]
              "label": "positive",              # positive / neutral / negative
              "label_display": "正向",
              "emotion_tags": ["高燃", "感叹"]   # 情绪标签，可能为空列表
            }
        """
        text = (text or "").strip()

        # 空文本直接返回中性，不浪费计算
        if not text:
            return self._neutral_result()

        # 后端不可用时降级为中性，保证主流程不中断
        if not self.available:
            return self._neutral_result()

        try:
            score = self._score(text)
        except Exception as exc:
            # 单条失败不应中断整个批量任务
            logger.warning("情感分析失败（%s）：%s", self.backend_name, exc)
            return self._neutral_result()

        if score is None:
            return self._neutral_result()

        # 夹取到 [0,1]，防止第三方库返回越界值
        score = max(0.0, min(float(score), 1.0))

        # 用关键词修正模型分值（解决 SnowNLP 不认网络用语的问题）
        score = round(_apply_keyword_adjustment(score, text), 4)

        return {
            "score": score,
            "label": self._classify(score),
            "label_display": self._label_display(self._classify(score)),
            "emotion_tags": extract_emotion_tags(text),
        }

    def analyze_batch(self, texts: list) -> list:
        """批量分析。

        参数:
            texts: 文本列表

        返回:
            与输入等长的结果列表（顺序一一对应）

        说明：基类用简单循环实现。若某后端支持批量推理
        （如 PaddleNLP 的批处理），可在子类中覆写以提速。
        """
        return [self.analyze(t) for t in texts]

    # -----------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------
    @staticmethod
    def _classify(score: float) -> str:
        """按阈值把分值转成情感标签。"""
        if score >= POSITIVE_THRESHOLD:
            return "positive"
        if score <= NEGATIVE_THRESHOLD:
            return "negative"
        return "neutral"

    @staticmethod
    def _label_display(label: str) -> str:
        """情感标签的中文名。"""
        return {"positive": "正向", "neutral": "中性", "negative": "负向"}.get(label, "未知")

    @staticmethod
    def _neutral_result() -> dict:
        """中性兜底结果。"""
        return {
            "score": 0.5,
            "label": "neutral",
            "label_display": "中性",
            "emotion_tags": [],
        }


# ===========================================================================
# SnowNLP 实现（默认）
# ===========================================================================
class SnowNLPAnalyzer(SentimentAnalyzer):
    """基于 SnowNLP 的情感分析。

    SnowNLP 用中文电商评论语料训练，对短文本（弹幕、评论）效果尚可，
    且是纯 Python 实现——无需编译、无版本冲突，适合本项目。

    局限：领域为电商评论，对 B站 特有的梗（"yyds""绷不住"）
    识别能力有限，因此额外叠加了关键词情绪标签来补充。
    """

    backend_name = "snownlp"

    def _check_dependency(self) -> bool:
        """检查 snownlp 是否可用。"""
        try:
            import snownlp  # noqa: F401

            return True
        except ImportError:
            logger.error(
                "snownlp 未安装，情感分析将返回中性值。"
                "安装：pip install snownlp"
            )
            return False

    def _score(self, text: str) -> Optional[float]:
        """调用 SnowNLP 计算情感分值。"""
        from snownlp import SnowNLP

        # SnowNLP 的 sentiments 属性返回 [0,1]，越大越正面，与我们的约定一致
        return SnowNLP(text).sentiments


# ===========================================================================
# PaddleNLP 实现（进阶，需 Python 3.11/3.12）
# ===========================================================================
class PaddleNLPAnalyzer(SentimentAnalyzer):
    """基于 PaddleNLP 的情感分析（国产框架）。

    ⚠️ 启用条件：Python 3.11 或 3.12。
    在 Python 3.13 上无法安装（paddlenlp 依赖的 tool-helpers 在 PyPI 缺失）。

    启用方式：
        pip install -r requirements-paddle.txt -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
        # 然后设置 .env:  SENTIMENT_BACKEND=paddlenlp
    """

    backend_name = "paddlenlp"

    # 类级别的模型缓存：Taskflow 初始化需要加载模型（数秒），
    # 必须复用实例，否则每条弹幕都重新加载会导致批量任务慢到不可用。
    _taskflow = None

    def _check_dependency(self) -> bool:
        """检查 paddlenlp 是否可用，并尝试加载模型。"""
        try:
            from paddlenlp import Taskflow  # noqa: F401
        except ImportError:
            logger.error(
                "paddlenlp 未安装或版本不兼容（需 Python 3.11/3.12）。"
                "详见 requirements-paddle.txt"
            )
            return False

        # 提前加载模型，把"首次调用慢"的问题暴露在初始化阶段
        try:
            self._get_taskflow()
            return True
        except Exception as exc:
            logger.error("PaddleNLP 模型加载失败：%s", exc)
            return False

    @classmethod
    def _get_taskflow(cls):
        """懒加载 Taskflow 实例（类级别复用）。"""
        if cls._taskflow is None:
            from paddlenlp import Taskflow

            # 使用轻量级情感分析模型，CPU 即可运行
            cls._taskflow = Taskflow("sentiment_analysis")
        return cls._taskflow

    def _score(self, text: str) -> Optional[float]:
        """调用 PaddleNLP 情感分析。

        PaddleNLP 返回形如 [{"text": "...", "label": "positive", "score": 0.99}]，
        这里把标签与置信度合成为统一的 [0,1] 分值。
        """
        taskflow = self._get_taskflow()
        result = taskflow(text)

        if not result:
            return None

        return self._result_to_score(result[0])

    @staticmethod
    def _result_to_score(item: dict) -> float:
        """把 PaddleNLP 的 (标签, 置信度) 映射到 [0,1]。

        映射规则：
            positive 且置信度高 -> 接近 1
            negative 且置信度高 -> 接近 0
            中性或低置信度      -> 接近 0.5
        """
        label = item.get("label", "neutral")
        confidence = float(item.get("score", 0.5))

        if label == "positive":
            return 0.5 + (confidence / 2.0)
        if label == "negative":
            return 0.5 - (confidence / 2.0)
        return 0.5

    def analyze_batch(self, texts: list) -> list:
        """覆写批量方法：PaddleNLP 支持一次传入列表，比逐条快得多。"""
        if not self.available or not texts:
            return [self.analyze(t) for t in texts]

        try:
            taskflow = self._get_taskflow()
            # 注意：送入模型的应是清洗后的文本
            cleaned = [clean_text(t) for t in texts]
            results = taskflow(cleaned)

            output = []
            for raw, item in zip(cleaned, results):
                score = self._result_to_score(item)
                score = max(0.0, min(score, 1.0))
                # 与 SnowNLP 后端保持一致的修正逻辑
                score = round(_apply_keyword_adjustment(score, raw), 4)
                output.append(
                    {
                        "score": score,
                        "label": self._classify(score),
                        "label_display": self._label_display(self._classify(score)),
                        "emotion_tags": extract_emotion_tags(raw),
                    }
                )
            return output
        except Exception as exc:
            logger.warning("批量情感分析失败，回退逐条处理：%s", exc)
            return [self.analyze(t) for t in texts]


# ===========================================================================
# 情绪标签提取（与后端无关）
# ===========================================================================
def extract_emotion_tags(text: str) -> list:
    """从文本中提取情绪标签。

    参数:
        text: 弹幕内容

    返回:
        情绪标签列表，最多 MAX_EMOTION_TAGS 个；无命中时返回空列表

    【为什么用关键词匹配而不是模型】
    情绪标签（高燃/泪目/搞笑）是 B站 社区特有的语感，
    通用情感模型（电商语料训练）识别不了"yyds""绷不住"这类网络用语。
    关键词表可自由维护，且推理零成本、结果可解释——
    对答辩演示来说，"可解释"比"黑盒准确"更有说服力。
    """
    if not text:
        return []

    tags = []
    lowered = text.lower()

    for tag, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            # 英文/数字关键词用不区分大小写比较，中文不受影响
            if kw.lower() in lowered:
                tags.append(tag)
                break   # 同一标签命中一个关键词即可

    return tags[:MAX_EMOTION_TAGS]


# ===========================================================================
# 工厂函数
# ===========================================================================
# 分析器实例缓存：初始化可能较慢（PaddleNLP 要加载模型），
# 因此每个后端只创建一次，后续复用。
_ANALYZER_CACHE: dict[str, SentimentAnalyzer] = {}


def get_analyzer(backend: Optional[str] = None) -> SentimentAnalyzer:
    """按配置返回情感分析器实例（带缓存）。

    参数:
        backend: 指定后端；不传则读取 settings.SENTIMENT_BACKEND

    返回:
        SentimentAnalyzer 实例

    【容错策略】
    若指定后端不可用（依赖未装），自动降级到 snownlp，
    而不是抛异常——情感分析是加分项模块，不应阻塞整个应用启动。
    """
    from django.conf import settings

    name = (backend or getattr(settings, "SENTIMENT_BACKEND", "snownlp")).strip().lower()

    if name in _ANALYZER_CACHE:
        return _ANALYZER_CACHE[name]

    analyzer_class = {
        "snownlp": SnowNLPAnalyzer,
        "paddlenlp": PaddleNLPAnalyzer,
    }.get(name)

    if analyzer_class is None:
        logger.warning("未知的情感分析后端 %r，回退到 snownlp", name)
        analyzer_class = SnowNLPAnalyzer

    analyzer = analyzer_class()

    # 指定后端不可用时降级，保证服务可用
    if not analyzer.available and analyzer_class is not SnowNLPAnalyzer:
        logger.warning("后端 %s 不可用，降级到 snownlp", name)
        analyzer = SnowNLPAnalyzer()

    _ANALYZER_CACHE[name] = analyzer
    logger.info("情感分析后端已就绪：%s（可用=%s）", analyzer.backend_name, analyzer.available)
    return analyzer


# ===========================================================================
# 文本清洗（分析前的预处理）
# ===========================================================================
# 弹幕中常见的无意义噪声，分析前先剔除，提高信号质量
_NOISE_PATTERNS = [
    (re.compile(r"https?://\S+"), ""),        # URL
    (re.compile(r"[a-zA-Z0-9]{20,}"), ""),    # 超长 token（通常是刷屏或乱码）
]


def clean_text(text: str) -> str:
    """清洗弹幕文本，去除对情感分析无贡献的噪声。

    参数:
        text: 原始弹幕

    返回:
        清洗后的文本

    说明：不做过度清洗——颜文字、重复字符（"哈哈哈哈"）本身就是
    强情感信号，保留它们对判断反而有利。
    """
    if not text:
        return ""

    cleaned = text
    for pattern, replacement in _NOISE_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    # 折叠 3 个以上的重复字符为 2 个（"哈哈哈哈哈" -> "哈哈"），
    # 既保留情感强度又避免超长文本拖慢分析
    cleaned = re.sub(r"(.)\1{2,}", r"\1\1", cleaned)

    return cleaned.strip()

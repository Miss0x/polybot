"""
probability_judger.py — Week 4 Phase 1

把 StatePackage 转换成结构化的概率判断草稿 ProbabilityDraft。

判断逻辑：
- 启发式规则，不依赖 LLM
- 基于 positive_strength_24h / negative_strength_24h / neutral_news_24h 做方向判断
- 优先选 relevance / strength 高的新闻进入 key_news
- 弱信号明确输出 low confidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from polybot.processing.state_package_builder import MatchedNewsEntry, StatePackage


# ---------------------------------------------------------------------------
# Enums (first version — plain strings)
# ---------------------------------------------------------------------------

PROBABILITY_VIEW_HIGHER = "higher"
PROBABILITY_VIEW_LOWER = "lower"
PROBABILITY_VIEW_UNCHANGED = "unchanged"
PROBABILITY_VIEW_UNCERTAIN = "uncertain"

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProbabilityDraft:
    """概率判断草稿。"""

    market_id: str
    question: str
    current_yes_price: float | None
    probability_view: str  # higher / lower / unchanged / uncertain
    confidence: str  # low / medium / high
    signal_summary: str
    reasoning: str
    key_news: list[dict] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "current_yes_price": self.current_yes_price,
            "probability_view": self.probability_view,
            "confidence": self.confidence,
            "signal_summary": self.signal_summary,
            "reasoning": self.reasoning,
            "key_news": self.key_news,
            "risk_notes": self.risk_notes,
        }


# ---------------------------------------------------------------------------
# Judger
# ---------------------------------------------------------------------------

class ProbabilityJudger:
    """
    基于 StatePackage 生成 ProbabilityDraft。

    第一版规则：
    1. positive_strength_24h 明显大于 negative_strength_24h → higher
    2. negative_strength_24h 明显大于 positive_strength_24h → lower
    3. 二者都很低或差距不明显 → unchanged / uncertain
    4. neutral 新闻过多 → 降低 confidence
    5. matched_news 很多但 key_news 很少 → risk note
    6. 优先选 relevance / strength 高的新闻进入 key_news
    """

    # 阈值参数（可调）
    RATIO_THRESHOLD = 2.0  # 强弱比超过此值视为"明显大于"
    ABS_THRESHOLD = 0.3  # 绝对强度低于此值视为"很低"
    MAX_KEY_NEWS = 3  # 最多保留几条关键新闻
    MIN_RELEVANCE_FOR_KEY = 0.60  # 进入 key_news 的最低 relevance

    def __init__(self, ratio_threshold: float = 2.0, abs_threshold: float = 0.3):
        self.ratio_threshold = ratio_threshold
        self.abs_threshold = abs_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def judge(self, pkg: StatePackage) -> ProbabilityDraft:
        """从 StatePackage 生成 ProbabilityDraft。"""
        pos = pkg.positive_strength_24h
        neg = pkg.negative_strength_24h
        neutral = pkg.neutral_news_24h
        total_matched = len(pkg.matched_news)
        direct_count = getattr(pkg, "direct_news_24h", 0)
        context_count = getattr(pkg, "context_news_24h", 0)


        # 1. 方向判断
        probability_view = self._decide_view(pos, neg)

        # 2. 信心等级（先计算 key_news 再传进去，用于保守降级）
        key_news = self._pick_key_news(pkg.matched_news)
        confidence = self._decide_confidence(
            probability_view, pos, neg, neutral, total_matched, key_news, direct_count
        )


        # 3. 信号摘要 + 理由
        signal_summary = self._build_signal_summary(
            probability_view, pos, neg, neutral, key_news, direct_count, context_count
        )
        reasoning = self._build_reasoning(
            probability_view, pos, neg, neutral, key_news, total_matched, direct_count, context_count
        )

        # 5. 风险提示
        risk_notes = self._build_risk_notes(
            total_matched, key_news, neutral, pos, neg, direct_count, context_count
        )


        return ProbabilityDraft(
            market_id=pkg.market_id,
            question=pkg.question,
            current_yes_price=pkg.yes_price,
            probability_view=probability_view,
            confidence=confidence,
            signal_summary=signal_summary,
            reasoning=reasoning,
            key_news=key_news,
            risk_notes=risk_notes,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decide_view(self, pos: float, neg: float) -> str:
        """根据正负强度决定 probability_view。"""
        # 双方都很低 → unchanged
        if pos < self.abs_threshold and neg < self.abs_threshold:
            return PROBABILITY_VIEW_UNCHANGED

        # 一方明显大于另一方
        if pos > 0 and neg > 0:
            if pos / neg >= self.ratio_threshold:
                return PROBABILITY_VIEW_HIGHER
            if neg / pos >= self.ratio_threshold:
                return PROBABILITY_VIEW_LOWER
            # 有信号但方向冲突 → uncertain
            return PROBABILITY_VIEW_UNCERTAIN

        if pos > 0 and neg == 0:
            return PROBABILITY_VIEW_HIGHER
        if neg > 0 and pos == 0:
            return PROBABILITY_VIEW_LOWER

        return PROBABILITY_VIEW_UNCHANGED

    def _decide_confidence(
        self,
        view: str,
        pos: float,
        neg: float,
        neutral: int,
        total_matched: int,
        key_news: list[dict],
        direct_count: int,
    ) -> str:
        """
        决定信心等级（Phase 3 保守化）。

        规则：
        1. 无明确方向 → low
        2. 无 direct evidence → low（context 不能支撑概率方向判断）
        3. 无关键新闻 → low（没有核心证据支撑判断）
        4. neutral 占比过高（>50%）→ medium 封顶
        5. 整体 direct 信号强度不高（max_strength < 1.5）→ medium
        6. 其他有明确方向 + 有 key_news + direct 强度够 → high
        """
        # 无明确方向 → low
        if view in (PROBABILITY_VIEW_UNCHANGED, PROBABILITY_VIEW_UNCERTAIN):
            return CONFIDENCE_LOW

        # 无 direct evidence → low（context 只作为背景风险，不支撑告警方向）
        if direct_count <= 0:
            return CONFIDENCE_LOW

        # 无关键新闻 → low（没有核心证据）
        if not key_news:
            return CONFIDENCE_LOW

        # neutral 新闻占比过高 → 最多 medium
        if total_matched > 0 and neutral / total_matched > 0.5:
            return CONFIDENCE_MEDIUM

        # 有明确方向但 direct 强度不够高 → medium
        max_strength = max(pos, neg)
        if max_strength < 1.5:
            return CONFIDENCE_MEDIUM

        return CONFIDENCE_HIGH


    def _pick_key_news(self, matched_news: list[MatchedNewsEntry]) -> list[dict]:
        """挑选关键新闻（按 relevance 和 strength 排序）。"""
        # 过滤弱相关
        candidates = [
            n for n in matched_news
            if n.relevance >= self.MIN_RELEVANCE_FOR_KEY
            and (n.evidence_type or "direct") == "direct"
        ]

        # 按 relevance 降序，relevance 相同按 strength 降序
        candidates.sort(key=lambda n: (n.relevance, n.strength), reverse=True)

        result: list[dict] = []
        for n in candidates[: self.MAX_KEY_NEWS]:
            result.append(
                {
                    "news_id": n.news_id,
                    "title": n.title,
                    "direction": n.direction,
                    "relevance": round(n.relevance, 3),
                    "strength": round(n.strength, 3),
                    "event_type": n.event_type,
                    "evidence_type": n.evidence_type,
                    "layer": n.layer,
                    "reasoning": n.reasoning,

                }
            )
        return result

    def _build_signal_summary(
        self,
        view: str,
        pos: float,
        neg: float,
        neutral: int,
        key_news: list[dict],
        direct_count: int,
        context_count: int,
    ) -> str:
        """生成一句话信号摘要。"""
        evidence_suffix = f"direct={direct_count}, context={context_count}, neutral={neutral}"
        if view == PROBABILITY_VIEW_HIGHER:
            return (
                f"Direct positive signal dominates (+{pos:.2f} vs -{neg:.2f}). "
                f"{len(key_news)} direct key news item(s) support YES probability rise "
                f"({evidence_suffix})."
            )
        if view == PROBABILITY_VIEW_LOWER:
            return (
                f"Direct negative signal dominates (-{neg:.2f} vs +{pos:.2f}). "
                f"{len(key_news)} direct key news item(s) suggest YES probability decline "
                f"({evidence_suffix})."
            )
        if view == PROBABILITY_VIEW_UNCERTAIN:
            return (
                f"Mixed direct signals detected (+{pos:.2f} / -{neg:.2f}). "
                f"Direction is unclear ({evidence_suffix})."
            )
        # unchanged
        return (
            f"No strong direct directional signal in the current matched news set "
            f"(+{pos:.2f} / -{neg:.2f}; {evidence_suffix})."
        )


    def _build_reasoning(
        self,
        view: str,
        pos: float,
        neg: float,
        neutral: int,
        key_news: list[dict],
        total_matched: int,
        direct_count: int,
        context_count: int,
    ) -> str:
        """生成详细判断理由。"""
        parts: list[str] = []

        parts.append(
            f"Matched {total_matched} news items in the window: "
            f"direct={direct_count}, context={context_count}, neutral={neutral}. "
            f"Only direct evidence contributes to core strength: "
            f"positive {pos:.2f}, negative {neg:.2f}."
        )

        if key_news:
            parts.append(
                f"Top {len(key_news)} direct key news by relevance: "
                + "; ".join(f"\"{n['title'][:50]}\"" for n in key_news)
                + "."
            )
        else:
            parts.append(
                "No direct news reached the key-news relevance threshold. "
                "Context signals may describe the background but are not enough for an alert."
            )

        if view == PROBABILITY_VIEW_UNCERTAIN:
            parts.append(
                "Conflicting or weak direct directional evidence prevents a clear view."
            )
        elif view == PROBABILITY_VIEW_UNCHANGED:
            parts.append(
                "Direct aggregate signal strength is below the actionable threshold."
            )

        return " ".join(parts)


    def _build_risk_notes(
        self,
        total_matched: int,
        key_news: list[dict],
        neutral: int,
        pos: float,
        neg: float,
        direct_count: int,
        context_count: int,
    ) -> list[str]:
        """生成风险提示列表。"""
        notes: list[str] = []

        # 无 direct evidence
        if direct_count == 0 and context_count > 0:
            notes.append(
                "Only context news matched this market; no direct evidence supports a probability move."
            )

        # context 占比高
        if total_matched > 0 and context_count / total_matched > 0.5:
            notes.append(
                "Most matched news is context-level background; avoid treating it as a strong alert signal."
            )

        # 匹配多但关键少
        if total_matched > 5 and len(key_news) < 2:
            notes.append(
                "Matched news volume is high, but direct market-specific evidence is limited."
            )

        # neutral 占比高
        if total_matched > 0 and neutral / total_matched > 0.6:
            notes.append(
                "A large share of matched news is directionally neutral; "
                "signals may be noisy."
            )

        # 双方强度都低
        if pos < self.abs_threshold and neg < self.abs_threshold:
            notes.append(
                "Direct signal strength is very low; current price may not reflect recent news."
            )

        # 方向冲突
        if pos > 0 and neg > 0 and max(pos, neg) / max(min(pos, neg), 0.01) < self.ratio_threshold:
            notes.append(
                "Positive and negative direct signals are both present and roughly balanced."
            )

        return notes


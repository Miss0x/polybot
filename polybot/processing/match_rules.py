"""
match_rules.py — Phase 3

L1 规则匹配引擎：
- A/B/C 三档分档
- alias 匹配
- context guard
- ambiguous terms 处理
- direction / relevance / strength 计算
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from polybot.processing.market_profile_builder import MarketProfile


# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------


class MatchTier:
    STRONG = "C"      # 强匹配
    NORMAL = "A"      # 普通匹配
    AMBIGUOUS = "B"   # 歧义匹配（需 context guard）


# 全局歧义词表（与 market_profile_builder 中的一致，作为兜底）
GLOBAL_AMBIGUOUS_TERMS: frozenset[str] = frozenset({
    "strike", "attack", "deal", "talks", "war", "peace",
    "trump", "biden", "oil", "missile", "sanctions",
    "nuclear", "agreement", "negotiations",
})

# 全局 context guard 词
GLOBAL_CONTEXT_TERMS: frozenset[str] = frozenset({
    "iran", "tehran", "irgc", "hormuz", "nuclear", "iaea",
    "israel", "israeli", "netanyahu", "khamenei",
    "military", "conflict", "missile", "strike", "war",
    "sanctions", "ceasefire", "retaliation", "gaza",
    "hezbollah", "rafah", "beirut", "syria", "iraq",
    "pentagon", " IDF", "idf", "army", "troops",
    "diplomatic", "negotiation", "summit", "warhead",
})


# ---------------------------------------------------------------------------
# MatchDecision dataclass
# ---------------------------------------------------------------------------


@dataclass
class MatchDecision:
    """一次匹配的结果。"""
    matched: bool
    relevance: float          # 0.0 - 1.0
    direction: int            # 1 / -1 / 0
    strength: float           # 0.0 - 1.0（第一版 = relevance）
    reasoning: str
    tier: str                # "A" / "B" / "C"
    matched_terms: list[str] = field(default_factory=list)
    positive_signals_hit: list[str] = field(default_factory=list)
    negative_signals_hit: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "relevance": round(self.relevance, 3),
            "direction": self.direction,
            "strength": round(self.strength, 3),
            "reasoning": self.reasoning,
            "tier": self.tier,
            "matched_terms": self.matched_terms,
            "positive_signals_hit": self.positive_signals_hit,
            "negative_signals_hit": self.negative_signals_hit,
        }


# ---------------------------------------------------------------------------
# Core matching engine
# ---------------------------------------------------------------------------


class MatchEngine:
    """
    对单条新闻与单个 market_profile 做 L1 规则匹配。

    匹配文本来源：title + " " + raw_text（如果 raw_text 为空则只用 title）
    """

    def __init__(self, profile: MarketProfile):
        self.profile = profile

        # 预解析 profile 字段（JSON string → list）
        self._subjects = self._parse_list(profile.subjects)
        self._actions = self._parse_list(profile.actions)
        self._objects = self._parse_list(profile.objects)
        self._aliases = self._parse_list(profile.aliases)
        self._context_terms = self._parse_list(profile.context_terms) or list(GLOBAL_CONTEXT_TERMS)
        self._ambiguous_terms = self._parse_list(profile.ambiguous_terms) or list(GLOBAL_AMBIGUOUS_TERMS)
        self._positive_signals = self._parse_list(profile.positive_signals)
        self._negative_signals = self._parse_list(profile.negative_signals)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, news_title: str, news_raw_text: str | None = None) -> MatchDecision:
        """
        主入口。

        Args:
            news_title: 新闻标题
            news_raw_text: 新闻正文（可选）
        """
        text = self._build_text(news_title, news_raw_text)
        text_lower = text.lower()

        # 先检测 positive / negative signals
        pos_hit = self._find_phrases(text_lower, self._positive_signals)
        neg_hit = self._find_phrases(text_lower, self._negative_signals)

        # 计算 direction
        direction = self._calc_direction(pos_hit, neg_hit)

        # 尝试 C 档匹配
        decision = self._try_tier_c(text_lower, pos_hit, neg_hit, direction)
        if decision is not None:
            return decision

        # 尝试 A 档匹配
        decision = self._try_tier_a(text_lower, pos_hit, neg_hit, direction)
        if decision is not None:
            return decision

        # 尝试 B 档匹配
        decision = self._try_tier_b(text_lower, pos_hit, neg_hit, direction)
        if decision is not None:
            return decision

        # 不匹配
        return MatchDecision(
            matched=False,
            relevance=0.0,
            direction=0,
            strength=0.0,
            reasoning="No tier matched; news does not relate to this market.",
            tier="",
            matched_terms=[],
        )

    # ------------------------------------------------------------------
    # Tier C: Strong match
    # ------------------------------------------------------------------

    def _try_tier_c(
        self,
        text_lower: str,
        pos_hit: list[str],
        neg_hit: list[str],
        direction: int,
    ) -> MatchDecision | None:
        """
        C 档强匹配：满足任一即命中。
        1. 命中 market-specific alias（词边界匹配）
        2. 同时命中 subject + object
        3. 同时命中 subject + action + context
        4. 命中非常明确的专有地名/机构/设施
        """
        all_terms: list[str] = []
        reasons: list[str] = []

        # 1. alias 词边界匹配
        alias_hits = self._find_word_boundary_hits(text_lower, self._aliases)
        all_terms.extend(alias_hits)
        if alias_hits:
            reasons.append(f"alias hit: {alias_hits}")

        # 2. subject + object 同时命中
        sub_hit = self._find_word_boundary_hits(text_lower, self._subjects)
        obj_hit = self._find_word_boundary_hits(text_lower, self._objects)
        if sub_hit and obj_hit:
            all_terms.extend(sub_hit)
            all_terms.extend(obj_hit)
            reasons.append(f"subject+object: {sub_hit}+{obj_hit}")

        # 3. subject + action + context 同时命中
        act_hit = self._find_word_boundary_hits(text_lower, self._actions)
        ctx_hit = self._find_context_hits(text_lower, self._context_terms)
        if sub_hit and act_hit and ctx_hit:
            all_terms.extend(sub_hit)
            all_terms.extend(act_hit)
            reasons.append(f"subject+action+context: {sub_hit}+{act_hit}")

        # 4. 专有实体（subject 本身即专有地名/机构）
        if sub_hit:
            reasons.append(f"dedicated entity: {sub_hit}")

        if not reasons:
            return None

        matched_terms = list(dict.fromkeys(all_terms))
        relevance = self._clamp(0.75 + len(reasons) * 0.05, 0.75, 0.95)
        reasoning = "; ".join(reasons)

        return MatchDecision(
            matched=True,
            relevance=relevance,
            direction=direction,
            strength=relevance,
            reasoning=f"[C] {reasoning}",
            tier=MatchTier.STRONG,
            matched_terms=matched_terms,
            positive_signals_hit=pos_hit,
            negative_signals_hit=neg_hit,
        )

    # ------------------------------------------------------------------
    # Tier A: Normal match
    # ------------------------------------------------------------------

    def _try_tier_a(
        self,
        text_lower: str,
        pos_hit: list[str],
        neg_hit: list[str],
        direction: int,
    ) -> MatchDecision | None:
        """
        A 档普通匹配：
        1. 命中 subject + context_terms
        2. 或命中 action/object 至少一类
        """
        sub_hit = self._find_word_boundary_hits(text_lower, self._subjects)
        ctx_hit = self._find_context_hits(text_lower, self._context_terms)
        act_hit = self._find_word_boundary_hits(text_lower, self._actions)
        obj_hit = self._find_word_boundary_hits(text_lower, self._objects)

        reason = ""
        all_terms: list[str] = []

        # 条件1：subject + context
        if sub_hit and ctx_hit:
            all_terms.extend(sub_hit)
            all_terms.extend(ctx_hit)
            reason = f"subject+context: {sub_hit}"
        # 条件2：action 或 object 至少一个
        elif act_hit or obj_hit:
            if act_hit:
                all_terms.extend(act_hit)
            if obj_hit:
                all_terms.extend(obj_hit)
            reason = f"action/object: {act_hit or []}+{obj_hit or []}"

        if not reason:
            return None

        matched_terms = list(dict.fromkeys(all_terms))
        relevance = self._clamp(0.45 + len(matched_terms) * 0.03, 0.45, 0.75)
        reasoning = f"subject+context" if ctx_hit else "action/object"

        return MatchDecision(
            matched=True,
            relevance=relevance,
            direction=direction,
            strength=relevance,
            reasoning=f"[A] {reasoning}",
            tier=MatchTier.NORMAL,
            matched_terms=matched_terms,
            positive_signals_hit=pos_hit,
            negative_signals_hit=neg_hit,
        )

    # ------------------------------------------------------------------
    # Tier B: Ambiguous match (context guard required)
    # ------------------------------------------------------------------

    def _try_tier_b(
        self,
        text_lower: str,
        pos_hit: list[str],
        neg_hit: list[str],
        direction: int,
    ) -> MatchDecision | None:
        """
        B 档歧义匹配：
        - 命中 ambiguous_terms
        - 必须同时命中 context guard（同一文本中）
        - 低于阈值（< 0.30）不落库
        """
        # 找 ambiguous term 命中
        amb_hit = self._find_word_boundary_hits(text_lower, self._ambiguous_terms)
        if not amb_hit:
            return None

        # context guard：同文本中必须有 context term
        ctx_hit = self._find_context_hits(text_lower, self._context_terms)
        if not ctx_hit:
            return None  # 歧义词命中但无 context guard，不匹配

        # 同时要求至少命中 subject 或 object 之一
        sub_hit = self._find_word_boundary_hits(text_lower, self._subjects)
        obj_hit = self._find_word_boundary_hits(text_lower, self._objects)
        if not sub_hit and not obj_hit:
            return None

        all_terms = list(dict.fromkeys(amb_hit + (sub_hit or []) + (obj_hit or []) + ctx_hit))
        relevance = self._clamp(0.30 + len(ctx_hit) * 0.05, 0.30, 0.55)

        # B 档 relevance 低于 0.30 不落库（已在 match() 返回前过滤）
        return MatchDecision(
            matched=True,
            relevance=relevance,
            direction=direction,
            strength=relevance,
            reasoning=f"[B] ambiguous={amb_hit}, context={ctx_hit}",
            tier=MatchTier.AMBIGUOUS,
            matched_terms=all_terms,
            positive_signals_hit=pos_hit,
            negative_signals_hit=neg_hit,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_text(title: str, raw_text: str | None) -> str:
        if raw_text:
            return f"{title} {raw_text}"
        return title

    @staticmethod
    def _parse_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v).lower().strip() for v in value if v]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v).lower().strip() for v in parsed if v]
            except Exception:
                pass
        return []

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _find_word_boundary_hits(text_lower: str, terms: list[str]) -> list[str]:
        """词边界匹配：term 必须是完整词（非子串）。"""
        found: list[str] = []
        for term in terms:
            t = term.lower().strip()
            if not t:
                continue
            # 词边界：前后是非字母数字或字符串首尾
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(t) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, text_lower):
                found.append(term)
        return found

    @staticmethod
    def _find_phrases(text_lower: str, phrases: list[str]) -> list[str]:
        """短语匹配：全文子串。"""
        return [p for p in phrases if p.lower() in text_lower]

    @staticmethod
    def _find_context_hits(text_lower: str, context_terms: list[str]) -> list[str]:
        """context 命中：词边界匹配。"""
        return MatchEngine._find_word_boundary_hits(text_lower, context_terms)

    @staticmethod
    def _calc_direction(pos_hit: list[str], neg_hit: list[str]) -> int:
        """direction 保守处理：明确命中 positive → 1，明确命中 negative → -1，否则 0。"""
        if pos_hit and not neg_hit:
            return 1
        if neg_hit and not pos_hit:
            return -1
        if pos_hit and neg_hit:
            return 0
        return 0

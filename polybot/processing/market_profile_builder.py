"""
Market Profile Builder — Phase 2

从 MarketORM 或 dict 出发，基于规则生成 MarketProfile dataclass。
第一版不调用 LLM，只用文本模式提取 + 领域词表。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from polybot.collect.polymarket_client import Market
from polybot.storage.models import MarketORM


# ---------------------------------------------------------------------------
# Domain constants for 美伊冲突 MVP
# ---------------------------------------------------------------------------

_AMBIGUOUS_TERMS: frozenset[str] = frozenset({
    "strike", "attack", "deal", "talks", "war", "peace",
    "trump", "biden", "oil", "missile", "sanctions",
    "nuclear", "agreement", "negotiations",
})

_CONTEXT_TERMS: frozenset[str] = frozenset({
    "iran", "tehran", "irgc", "hormuz", "nuclear", "iaea",
    "israel", "israeli", "netanyahu", "khamenei", "khatami",
    "revolutionary guard", "pacific", "persian gulf",
    "middle east", "atomic", "uranium", "centrifuge",
    "sanctions", "oil", "crude", "brent", "opec",
    "ceasefire", "hostage", "retaliation", "revenge",
})

_POSITIVE_SIGNALS: frozenset[str] = frozenset({
    "iran attack", "iran strike", "iran launches", "iranian attack",
    "tehran attack", "irgc strike", "iranian missile", "iran missile",
    "military action", "war begins", "conflict escalates",
    "iran invades", "tehran orders attack", "retaliation strike",
    "direct attack", "first strike",
})

_NEGATIVE_SIGNALS: frozenset[str] = frozenset({
    "peace talks", "diplomacy", "ceasefire", "deal reached",
    "agreement signed", "negotiations resume", "sanctions lifted",
    "truce", "armistice", "peace deal", "diplomatic solution",
    "talks succeed", "iran backs down", "iran concedes",
    "iran complies", "iaea approved", "nuclear deal restored",
})

_ACTION_VERBS: frozenset[str] = frozenset({
    "attack", "strike", "invade", "launch", "bomb", "missile",
    "shoot", "assassinate", "target", "hit", "destroy", "raid",
    "retaliate", "escalate", "respond", "confront", "threaten",
})

_OBJECT_KW: frozenset[str] = frozenset({
    "israel", "tehran", "tel aviv", "oil facility", "nuclear site",
    "military base", "embassy", "tanker", "shipping", "gulf",
    "pipeline", "refinery", "city", "civilian", "military",
})


@dataclass
class MarketProfile:
    """市场模式卡：系统理解市场的结构化表示。"""
    market_id: str
    subjects: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    context_terms: list[str] = field(default_factory=list)
    ambiguous_terms: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)
    deadline_utc: datetime | None = None
    generated_method: str = "rule_v1"
    generated_at: datetime | None = None
    raw_profile_json: str | None = None


class MarketProfileBuilder:
    """
    从 Market 信息提取结构化 profile。

    输入：MarketORM 或 Market dataclass
    输出：MarketProfile dataclass（需外部 json.dumps 序列化 list 字段）
    """

    def __init__(self, board_config: dict | None = None):
        """
        board_config: 可选，从 board YAML 加载的 dict。
                      用于补充 aliases 和 context_terms。
        """
        self._board = board_config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, market: MarketORM | Market | dict) -> MarketProfile:
        """
        统一入口。
        market_id 必须能取到，其他字段从 dict/daclass 属性探查。
        """
        if isinstance(market, dict):
            return self._from_dict(market)
        elif isinstance(market, Market):
            return self._from_dataclass(market)
        elif isinstance(market, MarketORM):
            return self._from_orm(market)
        else:
            raise TypeError(f"Unsupported market type: {type(market)}")

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _from_dict(self, d: dict) -> MarketProfile:
        q = d.get("question", "") or ""
        desc = d.get("description", "") or ""
        raw_q = q.lower()
        raw_desc = desc.lower()

        subjects = self._extract_subjects(q, desc)
        actions = self._extract_actions(q)
        objects = self._extract_objects(q, desc)

        # Aliases: question 本身 + board keywords + inferred
        aliases = self._build_aliases(subjects, q)

        context_terms = list(_CONTEXT_TERMS)
        ambiguous_terms = list(_AMBIGUOUS_TERMS)
        positive_signals = list(_POSITIVE_SIGNALS)
        negative_signals = list(_NEGATIVE_SIGNALS)
        edge_cases = self._extract_edge_cases(q, desc)

        deadline = self._parse_deadline(d)

        profile = MarketProfile(
            market_id=d["id"],
            subjects=subjects,
            actions=actions,
            objects=objects,
            aliases=aliases,
            positive_signals=positive_signals,
            negative_signals=negative_signals,
            context_terms=context_terms,
            ambiguous_terms=ambiguous_terms,
            edge_cases=edge_cases,
            deadline_utc=deadline,
            generated_method="rule_v1",
            generated_at=datetime.utcnow(),
        )
        profile.raw_profile_json = json.dumps(d, ensure_ascii=False)
        return profile

    def _from_dataclass(self, m: Market) -> MarketProfile:
        raw = m.raw or {}
        d = {
            "id": m.id,
            "question": m.question,
            "description": m.description or "",
            "end_date": getattr(m, "end_date", None),
        }
        # raw market JSON 中可能还有额外的 context
        if isinstance(raw, dict):
            d["description"] = d["description"] or raw.get("description", "") or raw.get("subtitle", "")
        return self._from_dict(d)

    def _from_orm(self, m: MarketORM) -> MarketProfile:
        # 先尝试解析 raw_event_json
        raw_dict: dict = {}
        if m.raw_event_json:
            try:
                raw_dict = json.loads(m.raw_event_json)
            except Exception:
                pass

        deadline = m.end_date

        # subjects 优先从 raw_event 反推
        subjects = self._extract_subjects(m.question, m.description or "")
        actions = self._extract_actions(m.question)
        objects = self._extract_objects(m.question, m.description or "")
        aliases = self._build_aliases(subjects, m.question)

        profile = MarketProfile(
            market_id=m.id,
            subjects=subjects,
            actions=actions,
            objects=objects,
            aliases=aliases,
            positive_signals=list(_POSITIVE_SIGNALS),
            negative_signals=list(_NEGATIVE_SIGNALS),
            context_terms=list(_CONTEXT_TERMS),
            ambiguous_terms=list(_AMBIGUOUS_TERMS),
            edge_cases=self._extract_edge_cases(m.question, m.description or ""),
            deadline_utc=deadline,
            generated_method="rule_v1",
            generated_at=datetime.utcnow(),
        )
        profile.raw_profile_json = m.raw_event_json
        return profile

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_subjects(question: str, description: str) -> list[str]:
        """从 question + description 提取主语实体。"""
        text = (question + " " + (description or "")).lower()
        found: list[str] = []

        # 明确的主语词
        for kw in ["iran", "tehran", "irgc", "israel", "israeli", "netanyahu",
                   "khamenei", "revolutionary guard", "islamic republic"]:
            if kw in text:
                found.append(kw.title() if len(kw) > 3 else kw.upper())

        # 如果一个都没找到，从 question 提取前两个名词词块
        if not found:
            words = re.findall(r"[a-zA-Z]{3,}", question)
            seen = set()
            for w in words[:5]:
                w_lower = w.lower()
                if w_lower not in seen and w_lower not in {"will", "the", "that", "this", "iran"}:
                    seen.add(w_lower)
                    found.append(w_lower.title())

        return list(dict.fromkeys(found))  # 去重保序

    @staticmethod
    def _extract_actions(question: str) -> list[str]:
        """从 question 提取动作词。"""
        q = question.lower()
        found = []
        for verb in _ACTION_VERBS:
            if verb in q:
                found.append(verb)
        return found

    @staticmethod
    def _extract_objects(question: str, description: str) -> list[str]:
        """从 question + description 提取宾语。"""
        text = (question + " " + (description or "")).lower()
        found = []
        for kw in _OBJECT_KW:
            if kw in text:
                found.append(kw.title() if len(kw) > 3 else kw.upper())
        return found

    def _build_aliases(self, subjects: list[str], question: str) -> list[str]:
        """基于主语 + question + board keywords 生成 aliases。"""
        aliases: list[str] = []
        q_lower = question.lower()

        # 收录 question 中的每个单词（过滤常见停用词）
        stop = {"will", "the", "a", "an", "by", "in", "on", "at", "to", "if", "does", "is", "that", "this"}
        words = re.findall(r"[a-zA-Z]{3,}", question)
        for w in words:
            wl = w.lower()
            if wl not in stop and len(wl) >= 3:
                aliases.append(wl)

        # 追加 board keywords
        board_keywords = self._board.get("keywords_market", [])
        aliases.extend([k.lower() for k in board_keywords if k.lower() not in stop])

        # 追加 subjects 本身
        aliases.extend([s.lower() for s in subjects])

        # 去重保序
        seen = set()
        result = []
        for a in aliases:
            al = a.lower()
            if al not in seen:
                seen.add(al)
                result.append(a)
        return result

    @staticmethod
    def _extract_edge_cases(question: str, description: str) -> list[str]:
        """从 question / description 提取边缘条件（resolution 相关的特殊情况）。"""
        text = (question + " " + (description or "")).lower()
        edge = []

        # 常见边缘条件指示词
        indicators = [
            "false flag", "proportional", "retaliation", "self-defense",
            "preemptive", "united nations", "us intervention", "direct",
            "indirect", "state-sponsored", "non-state actor",
            "wmd", "biological", "chemical", "nuclear",
        ]
        for ind in indicators:
            if ind in text:
                edge.append(ind)

        # 条件句特征：if / unless / provided that
        condition_patterns = [
            r"if\s+iran", r"unless\s+iran", r"if\s+israel",
            r"provided\s+that", r"contingent\s+on",
        ]
        for pat in condition_patterns:
            if re.search(pat, text):
                edge.append(re.search(pat, text).group())

        return edge

    @staticmethod
    def _parse_deadline(market_dict: dict) -> datetime | None:
        """从 dict 或 MarketORM 提取截止时间。"""
        end_date = market_dict.get("end_date") or market_dict.get("endDate")
        if isinstance(end_date, datetime):
            return end_date
        if isinstance(end_date, str) and end_date:
            try:
                return datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except Exception:
                pass
        return None
"""
news_event_extractor.py — Phase 1 新闻事件抽取器

将新闻文本转换为结构化事件：
news title/raw_text → event_type + actors + certainty + evidence_sentence。

第一版规则：
- 使用 EventOntology.classify_text() 从受控事件本体中选择 event_type
- 同一新闻可抽取多个 event_type，但默认限制 top_k，避免过宽
- 无匹配时写入 unclassified，便于后续分析覆盖缺口
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from polybot.ontology import EventOntology, EventType, load_event_ontology


DEFAULT_ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "config" / "ontology" / "iran_conflict_events.yaml"


@dataclass
class NewsEventDraft:
    """新闻事件抽取草稿，准备落库到 news_events。"""
    news_id: int
    event_type: str
    actors: list[str] = field(default_factory=list)
    certainty: str = "unknown"
    time_ref: str | None = None
    evidence_sentence: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    extraction_method: str = "rule_v1"


@dataclass
class ExtractStats:
    """批量抽取统计。"""
    news_processed: int = 0
    events_created: int = 0
    events_updated: int = 0
    unclassified_count: int = 0
    by_event_type: dict[str, int] = field(default_factory=dict)

    def add_event_type(self, event_type: str) -> None:
        self.by_event_type[event_type] = self.by_event_type.get(event_type, 0) + 1


class NewsEventExtractor:
    """规则版新闻事件抽取器。"""

    def __init__(self, ontology: EventOntology | None = None, ontology_path: str | Path | None = None):
        if ontology is not None:
            self.ontology = ontology
        else:
            self.ontology = load_event_ontology(ontology_path or DEFAULT_ONTOLOGY_PATH)

    def extract(self, news_id: int, title: str, raw_text: str | None = None, top_k: int = 3) -> list[NewsEventDraft]:
        """
        从单条新闻抽取事件。

        Args:
            news_id: 新闻 ID
            title: 新闻标题
            raw_text: 新闻正文，可为空
            top_k: 最多保留几个事件类型
        """
        text = self._build_text(title, raw_text)
        text_lower = text.lower()
        results = self.ontology.classify_text(text_lower)

        if not results:
            return [
                NewsEventDraft(
                    news_id=news_id,
                    event_type="unclassified",
                    actors=[],
                    certainty=self._detect_certainty(text_lower),
                    evidence_sentence=title,
                    matched_keywords=[],
                )
            ]

        drafts: list[NewsEventDraft] = []
        for event_type_id, matched_keywords in results[:top_k]:
            event_type = self.ontology.get(event_type_id)
            drafts.append(
                NewsEventDraft(
                    news_id=news_id,
                    event_type=event_type_id,
                    actors=self._extract_actors(text_lower, event_type),
                    certainty=self._detect_certainty(text_lower),
                    time_ref=self._extract_time_ref(text),
                    evidence_sentence=self._find_evidence_sentence(text, matched_keywords) or title,
                    matched_keywords=matched_keywords,
                    extraction_method="rule_v1",
                )
            )
        return drafts

    @staticmethod
    def _build_text(title: str, raw_text: str | None) -> str:
        if raw_text:
            return f"{title}. {raw_text}"
        return title

    @staticmethod
    def _extract_actors(text_lower: str, event_type: EventType | None) -> list[str]:
        """从文本中抽取参与方。第一版用 ontology actors + 常见别名匹配。"""
        if event_type is None:
            return []

        actor_aliases: dict[str, tuple[str, ...]] = {
            "US": ("u.s.", "united states", "washington", "american", "pentagon"),
            "Iran": ("iran", "iranian", "tehran", "irgc"),
            "Israel": ("israel", "israeli", "netanyahu", "idf"),
            "Hezbollah": ("hezbollah",),
            "Houthis": ("houthi", "houthis"),
            "Iraqi militias": ("iraqi militia", "iraqi militias", "militia"),
            "IAEA": ("iaea", "international atomic energy agency"),
            "EU": ("eu", "european union"),
            "China": ("china", "beijing"),
            "Oman": ("oman", "muscat"),
            "Qatar": ("qatar", "doha"),
            "US Navy": ("us navy", "u.s. navy", "navy"),
            "IRGC Navy": ("irgc navy", "revolutionary guard navy"),
            "OPEC": ("opec",),
        }

        found: list[str] = []
        for actor in event_type.actors:
            aliases = actor_aliases.get(actor, (actor.lower(),))
            if any(NewsEventExtractor._has_actor_alias(text_lower, alias) for alias in aliases):
                found.append(actor)
        return found

    @staticmethod
    def _has_actor_alias(text_lower: str, alias: str) -> bool:
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, text_lower):
            window = text_lower[max(0, match.start() - 24):match.start()]
            if re.search(r"\b(?:not mention|without mentioning|no mention of)\s+$", window):
                continue
            return True
        return False



    @staticmethod
    def _detect_certainty(text_lower: str) -> str:
        """
        粗略判断事件确定性。

        confirmed: 官方宣布/确认
        reported: 媒体报道/据称
        rumored: 传闻/可能
        denied: 否认
        unknown: 其他
        """
        denied_terms = ["denies", "denied", "rejects claim", "false report", "not true"]
        rumored_terms = ["rumor", "rumour", "unconfirmed", "may", "could", "might", "reportedly", "sources say"]
        reported_terms = ["reported", "according to", "officials say", "media reports", "said"]
        confirmed_terms = ["confirmed", "announced", "officially", "signed", "declared", "states"]

        if any(term in text_lower for term in denied_terms):
            return "denied"
        if any(term in text_lower for term in rumored_terms):
            return "rumored"
        if any(term in text_lower for term in confirmed_terms):
            return "confirmed"
        if any(term in text_lower for term in reported_terms):
            return "reported"
        return "unknown"

    @staticmethod
    def _extract_time_ref(text: str) -> str | None:
        """抽取简单时间引用，第一版只抓常见日期/相对时间表达。"""
        patterns = [
            r"\b(?:today|yesterday|tomorrow|tonight)\b",
            r"\b(?:this|next|last)\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
        ]
        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower, flags=re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _find_evidence_sentence(text: str, matched_keywords: list[str]) -> str | None:
        """找出包含命中关键词的句子。"""
        if not matched_keywords:
            return None

        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(keyword.lower() in sentence_lower for keyword in matched_keywords):
                return sentence.strip()[:500]
        return None

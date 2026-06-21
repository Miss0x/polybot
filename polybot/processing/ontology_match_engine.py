"""
ontology_match_engine.py — 映射系统 Phase 2

基于 news_events.event_type × market_condition 的新闻-市场匹配引擎。

核心链路：
    NewsEventORM.event_type + MarketORM.question
    -> MarketConditionRegistry.classify_market()
    -> ImpactMapping.lookup(event_type, market_condition)
    -> OntologyMatchDecision
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from polybot.ontology import ImpactMapping, MarketConditionRegistry, load_impact_mapping, load_market_conditions
from polybot.storage.models import MarketORM, NewsEventORM



DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "config" / "ontology"
DEFAULT_MARKET_CONDITIONS_PATH = DEFAULT_ONTOLOGY_DIR / "iran_conflict_market_conditions.yaml"
DEFAULT_IMPACT_MAPPING_PATH = DEFAULT_ONTOLOGY_DIR / "iran_conflict_mapping.yaml"


@dataclass
class OntologyMatchDecision:
    """一次 ontology 映射匹配结果。"""

    matched: bool
    news_id: int
    market_id: str
    event_type: str
    market_condition: str | None
    relevance: float
    direction: int
    strength: float
    evidence_type: str | None
    reasoning: str
    layer: str = "L2_ONTOLOGY"
    condition_keywords: list[str] | None = None


class OntologyMatchEngine:
    """用事件本体与映射矩阵生成 news-market 匹配。"""

    def __init__(
        self,
        condition_registry: MarketConditionRegistry | None = None,
        impact_mapping: ImpactMapping | None = None,
        market_conditions_path: str | Path | None = None,
        impact_mapping_path: str | Path | None = None,
        min_relevance: float = 0.30,
    ):
        self.condition_registry = condition_registry or load_market_conditions(
            market_conditions_path or DEFAULT_MARKET_CONDITIONS_PATH
        )
        self.impact_mapping = impact_mapping or load_impact_mapping(
            impact_mapping_path or DEFAULT_IMPACT_MAPPING_PATH
        )
        self.min_relevance = min_relevance

    def match(self, news_event: NewsEventORM, market: MarketORM) -> OntologyMatchDecision:
        """对一条新闻事件和一个市场执行映射匹配。"""
        market_text = self._build_market_text(market)
        news_actors = self._parse_news_actors(news_event)
        condition_candidates = self.condition_registry.classify_market(market_text)
        if not condition_candidates:

            return OntologyMatchDecision(
                matched=False,
                news_id=news_event.news_id,
                market_id=market.id,
                event_type=news_event.event_type,
                market_condition=None,
                relevance=0.0,
                direction=0,
                strength=0.0,
                evidence_type=None,
                reasoning="No market_condition matched for market text.",
                condition_keywords=[],
            )

        for condition_id, keywords in condition_candidates:
            entry = self.impact_mapping.lookup(news_event.event_type, condition_id)
            if entry is None:
                continue

            condition = self.condition_registry.get(condition_id)
            if not self._passes_actor_guard(news_actors, condition.actors if condition else ()):  # type: ignore[arg-type]
                continue

            relevance = self._calc_relevance(entry.evidence_type, entry.strength_value, len(keywords))

            if relevance < self.min_relevance:
                continue

            return OntologyMatchDecision(
                matched=True,
                news_id=news_event.news_id,
                market_id=market.id,
                event_type=news_event.event_type,
                market_condition=condition_id,
                relevance=relevance,
                direction=entry.direction,
                strength=entry.strength_value,
                evidence_type=entry.evidence_type,
                reasoning=(
                    f"event_type={news_event.event_type} × market_condition={condition_id}; "
                    f"evidence={entry.evidence_type}; strength={entry.strength}; "
                    f"direction={entry.direction}; condition_keywords={keywords}; note={entry.note}"
                ),
                condition_keywords=keywords,
            )

        best_condition, best_keywords = condition_candidates[0]
        return OntologyMatchDecision(
            matched=False,
            news_id=news_event.news_id,
            market_id=market.id,
            event_type=news_event.event_type,
            market_condition=best_condition,
            relevance=0.0,
            direction=0,
            strength=0.0,
            evidence_type=None,
            reasoning=(
                f"No impact mapping for event_type={news_event.event_type} "
                f"and matched market_condition={best_condition}."
            ),
            condition_keywords=best_keywords,
        )

    @staticmethod
    def _build_market_text(market: MarketORM) -> str:
        parts = [market.question]
        if market.description:
            parts.append(market.description)
        if market.resolution_source:
            parts.append(market.resolution_source)
        return " ".join(p for p in parts if p)

    @staticmethod
    def _parse_news_actors(news_event: NewsEventORM) -> set[str]:
        actors_json = getattr(news_event, "actors_json", None)
        if not actors_json:
            return set()
        try:
            data = json.loads(actors_json)
        except (TypeError, json.JSONDecodeError):
            return set()
        if not isinstance(data, list):
            return set()
        return {str(item) for item in data if item}

    @staticmethod
    def _passes_actor_guard(news_actors: set[str], condition_actors: tuple[str, ...]) -> bool:
        """要求新闻至少覆盖市场核心参与方，避免跨地理/跨冲突误匹配。"""
        core_actors = {actor for actor in condition_actors if actor in {"US", "Iran", "Israel"}}
        if "Iran" in core_actors:
            if condition_actors == ("Iran",):
                return news_actors == {"Iran"}
            return "Iran" in news_actors
        if core_actors:

            return bool(news_actors & core_actors)
        return True

    @staticmethod
    def _calc_relevance(evidence_type: str, strength_value: float, keyword_count: int) -> float:

        """将 direct/context、strength 和市场条件命中数合成为 relevance。"""
        base = 0.72 if evidence_type == "direct" else 0.42
        strength_bonus = strength_value * 0.20
        keyword_bonus = min(keyword_count, 3) * 0.03
        return min(0.95, round(base + strength_bonus + keyword_bonus, 3))

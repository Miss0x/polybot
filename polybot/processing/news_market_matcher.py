"""
news_market_matcher.py — Phase 3

批量新闻-市场匹配引擎。
读取 market_profiles + 近 N 小时新闻，执行 L1 规则匹配，结果 upsert 到 news_market_links 表。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from polybot.processing.match_rules import MatchDecision, MatchEngine, MatchTier
from polybot.processing.market_profile_builder import MarketProfile
from polybot.storage.db import get_session
from polybot.storage.models import MarketORM, MarketProfileORM, NewsItemORM, NewsMarketLinkORM
from polybot.storage.repositories import (
    list_markets,
    list_recent_news_items,
    upsert_news_market_link,
)
from sqlalchemy import select


@dataclass
class MatchStats:
    """单次运行的统计信息。"""
    markets_processed: int = 0
    news_processed: int = 0
    links_created: int = 0
    links_updated: int = 0
    matches_by_tier: dict[str, int] | None = None

    def summary(self) -> str:
        return (
            f"markets={self.markets_processed}, "
            f"news={self.news_processed}, "
            f"created={self.links_created}, "
            f"updated={self.links_updated}"
        )


# 低于此阈值的 match 不落库
_MIN_RELEVANCE_THRESHOLD = 0.30


class NewsMarketMatcher:
    """
    批量新闻-市场匹配器。
    """

    def __init__(self, news_hours: int = 72, min_relevance: float = _MIN_RELEVANCE_THRESHOLD):
        self.news_hours = news_hours
        self.min_relevance = min_relevance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> MatchStats:
        """
        主入口：读取 profiles + news，执行匹配，upsert links。
        返回统计。
        """
        stats = MatchStats()

        with get_session() as session:
            # 1. 读取所有市场
            orm_markets = list_markets(session)
            stats.markets_processed = len(orm_markets)
            if not orm_markets:
                return stats

            # 2. 读取近 N 小时新闻
            news_items = list_recent_news_items(session, hours=self.news_hours)
            stats.news_processed = len(news_items)
            if not news_items:
                return stats

            # 3. 加载所有 profiles（转为 MarketProfile dict）
            profiles = self._load_profiles(session, orm_markets)
            if not profiles:
                pass

            # 4. 逐 market-profile 匹配
            tier_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "": 0}
            links_created = 0
            links_updated = 0

            for market_id, profile in profiles.items():
                engine = MatchEngine(profile)
                for news in news_items:
                    decision = engine.match(news.title, news.raw_text)

                    if not decision.matched or decision.relevance < self.min_relevance:
                        continue

                    # 先查是否存在
                    existing_stmt = select(NewsMarketLinkORM).where(
                        NewsMarketLinkORM.news_id == news.id,
                        NewsMarketLinkORM.market_id == market_id,
                    )
                    existing = session.execute(existing_stmt).scalar_one_or_none()

                    # upsert link
                    upsert_news_market_link(
                        session=session,
                        news_id=news.id,
                        market_id=market_id,
                        relevance=decision.relevance,
                        direction=decision.direction,
                        strength=decision.strength,
                        reasoning=decision.reasoning,
                        layer="L1_RULE",
                    )

                    if existing is None:
                        links_created += 1
                    else:
                        links_updated += 1

                    if decision.tier in tier_counts:
                        tier_counts[decision.tier] += 1

            session.commit()
            stats.links_created = links_created
            stats.links_updated = links_updated
            stats.matches_by_tier = tier_counts

        return stats

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_profiles(
        self,
        session,
        orm_markets: list[MarketORM],
    ) -> dict[str, MarketProfile]:
        """
        从 market_profiles 表加载 profiles，转为 MarketProfile dataclass。
        """
        market_ids = [m.id for m in orm_markets]
        profiles: dict[str, MarketProfile] = {}

        if not market_ids:
            return profiles

        # 批量查询 profiles
        stmt = select(MarketProfileORM).where(MarketProfileORM.market_id.in_(market_ids))
        rows = session.execute(stmt).scalars().all()
        profile_map = {row.market_id: row for row in rows}

        for market in orm_markets:
            orm = profile_map.get(market.id)
            if orm is None:
                continue

            profile = MarketProfile(
                market_id=orm.market_id,
                subjects=self._parse_json_list(orm.subjects_json),
                actions=self._parse_json_list(orm.actions_json),
                objects=self._parse_json_list(orm.objects_json),
                aliases=self._parse_json_list(orm.aliases_json),
                positive_signals=self._parse_json_list(orm.positive_signals_json),
                negative_signals=self._parse_json_list(orm.negative_signals_json),
                context_terms=self._parse_json_list(orm.context_terms_json),
                ambiguous_terms=self._parse_json_list(orm.ambiguous_terms_json),
                edge_cases=self._parse_json_list(orm.edge_cases_json),
                deadline_utc=orm.deadline_utc,
                generated_method=orm.generated_method,
                generated_at=orm.generated_at,
                raw_profile_json=orm.raw_profile_json,
            )
            profiles[orm.market_id] = profile

        return profiles

    @staticmethod
    def _parse_json_list(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return []

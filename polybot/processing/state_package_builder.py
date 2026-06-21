"""
state_package_builder.py — Phase 4

生成市场状态包雏形。
输入：market + latest snapshot + news_market_links + news_items
输出 JSON 到终端（第一版不入库）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from polybot.storage.models import MarketORM, NewsItemORM, SnapshotORM


@dataclass
class MatchedNewsEntry:
    """单条新闻匹配详情。"""
    news_id: int
    title: str
    direction: int
    relevance: float
    strength: float
    reasoning: str
    event_type: str | None = None
    evidence_type: str | None = None
    layer: str | None = None



@dataclass
class StatePackage:
    """市场状态包。"""
    market_id: str
    question: str
    yes_price: float | None
    matched_news: list[MatchedNewsEntry] = field(default_factory=list)
    positive_strength_24h: float = 0.0
    negative_strength_24h: float = 0.0
    context_positive_strength_24h: float = 0.0
    context_negative_strength_24h: float = 0.0
    neutral_news_24h: int = 0
    direct_news_24h: int = 0
    context_news_24h: int = 0


    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "yes_price": self.yes_price,
            "positive_strength_24h": round(self.positive_strength_24h, 4),
            "negative_strength_24h": round(self.negative_strength_24h, 4),
            "context_positive_strength_24h": round(self.context_positive_strength_24h, 4),
            "context_negative_strength_24h": round(self.context_negative_strength_24h, 4),
            "neutral_news_24h": self.neutral_news_24h,
            "direct_news_24h": self.direct_news_24h,
            "context_news_24h": self.context_news_24h,
            "matched_news": [
                {
                    "news_id": e.news_id,
                    "title": e.title,
                    "direction": e.direction,
                    "relevance": round(e.relevance, 3),
                    "strength": round(e.strength, 3),
                    "event_type": e.event_type,
                    "evidence_type": e.evidence_type,
                    "layer": e.layer,
                    "reasoning": e.reasoning,
                }
                for e in self.matched_news
            ],

        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class StatePackageBuilder:
    """
    状态包生成器。
    """

    def __init__(self, hours: int = 24):
        """
        hours: 聚合时间窗口（默认 24h，仅匹配近 N 小时的 link）。
        """
        self.hours = hours

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        market: MarketORM,
        snapshot: SnapshotORM | None,
        links: list[Any],
        news_map: dict[int, NewsItemORM],
    ) -> StatePackage:
        """
        为单个市场生成状态包。
        """
        yes_price = snapshot.yes_price if snapshot else None

        pkg = StatePackage(
            market_id=market.id,
            question=market.question,
            yes_price=yes_price,
        )

        # 仅保留最近 N 小时内的 link
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=self.hours)

        for link in links:
            link_ts = getattr(link, "created_at", None)
            if link_ts and link_ts < since:
                continue

            news = news_map.get(link.news_id)
            if news is None:
                continue

            evidence_type = getattr(link, "evidence_type", None) or "direct"
            event_type = getattr(link, "event_type", None)
            layer = getattr(link, "layer", None)
            entry = MatchedNewsEntry(
                news_id=link.news_id,
                title=news.title,
                direction=link.direction,
                relevance=link.relevance,
                strength=link.strength,
                reasoning=link.reasoning or "",
                event_type=event_type,
                evidence_type=evidence_type,
                layer=layer,
            )
            pkg.matched_news.append(entry)

            # 汇总统计：direct evidence 进入核心方向强度；context 只单独统计，不推动核心概率判断。
            if evidence_type == "context":
                pkg.context_news_24h += 1
                if link.direction == 1:
                    pkg.context_positive_strength_24h += link.strength
                elif link.direction == -1:
                    pkg.context_negative_strength_24h += link.strength
                else:
                    pkg.neutral_news_24h += 1
                continue

            if evidence_type == "direct":
                pkg.direct_news_24h += 1

            if link.direction == 1:
                pkg.positive_strength_24h += link.strength
            elif link.direction == -1:
                pkg.negative_strength_24h += link.strength
            else:
                pkg.neutral_news_24h += 1


        return pkg

    @staticmethod
    def build_all(
        markets: list[MarketORM],
        snapshots: dict[str, SnapshotORM],
        links: list[Any],
        news_map: dict[int, NewsItemORM],
        hours: int = 24,
    ) -> list[StatePackage]:
        """
        批量为所有市场生成状态包。
        """
        builder = StatePackageBuilder(hours=hours)
        # 按 market_id 聚 links
        links_by_market: dict[str, list[Any]] = {}
        for link in links:
            links_by_market.setdefault(link.market_id, []).append(link)

        packages: list[StatePackage] = []
        for market in markets:
            snapshot = snapshots.get(market.id)
            market_links = links_by_market.get(market.id, [])
            pkg = builder.build(market, snapshot, market_links, news_map)
            packages.append(pkg)

        return packages

"""
scripts/run_ontology_match.py

Phase 2：Ontology 新闻-市场匹配。
读取 news_events + markets，使用 event_type × market_condition 映射矩阵生成 news_market_links。

Usage:
    python scripts/run_ontology_match.py [--limit-events 100] [--min-relevance 0.30]
"""

from __future__ import annotations

import argparse
import json
import sys

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.logging import setup_logging
from polybot.processing.news_event_extractor import NewsEventExtractor
from polybot.processing.ontology_match_engine import OntologyMatchEngine

from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import NewsMarketLinkORM
from polybot.storage.repositories import list_markets, list_news_events, list_news_items, upsert_news_market_link

from sqlalchemy import select


@dataclass
class OntologyMatchStats:
    markets_processed: int = 0
    news_events_processed: int = 0
    links_created: int = 0
    links_updated: int = 0
    skipped_unclassified: int = 0
    matches_by_event_type: Counter[str] = field(default_factory=Counter)
    matches_by_condition: Counter[str] = field(default_factory=Counter)
    matches_by_evidence_type: Counter[str] = field(default_factory=Counter)
    matches_by_direction: Counter[int] = field(default_factory=Counter)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 Ontology News-Market Matcher")
    parser.add_argument("--limit-events", type=int, default=None, help="最多处理 N 条 news_events，默认全部")
    parser.add_argument("--min-relevance", type=float, default=0.30, help="低于该 relevance 的匹配不落库，默认 0.30")
    parser.add_argument("--include-unclassified", action="store_true", help="是否处理 unclassified 事件，默认跳过")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    engine = OntologyMatchEngine(min_relevance=args.min_relevance)
    extractor = NewsEventExtractor()
    stats = OntologyMatchStats()

    with get_session() as session:
        markets = list_markets(session)
        news_events = list_news_events(session)
        news_by_id = {news.id: news for news in list_news_items(session)}

        if args.limit_events is not None:
            news_events = news_events[:args.limit_events]

    print("=" * 76)
    print(
        f"Phase 2 Ontology Match | markets={len(markets)} | "
        f"news_events={len(news_events)} | min_relevance={args.min_relevance}"
    )
    print("=" * 76)

    if not markets:
        print("No markets found. Please run scripts/run_scan.py first.")
        return
    if not news_events:
        print("No news_events found. Please run scripts/run_news_event_extract.py first.")
        return

    with get_session() as session:
        for news_event in news_events:
            if news_event.event_type == "unclassified" and not args.include_unclassified:
                stats.skipped_unclassified += 1
                continue

            stats.news_events_processed += 1
            news_item = news_by_id.get(news_event.news_id)
            if news_item is not None:
                for draft in extractor.extract(news_item.id, news_item.title, news_item.raw_text, top_k=5):
                    if draft.event_type == news_event.event_type:
                        news_event.actors_json = json.dumps(draft.actors, ensure_ascii=False)

                        break

            for market in markets:

                stats.markets_processed += 1
                decision = engine.match(news_event, market)
                if not decision.matched:
                    continue

                existing = session.execute(
                    select(NewsMarketLinkORM).where(
                        NewsMarketLinkORM.news_id == decision.news_id,
                        NewsMarketLinkORM.market_id == decision.market_id,
                    )
                ).scalar_one_or_none()

                upsert_news_market_link(
                    session=session,
                    news_id=decision.news_id,
                    market_id=decision.market_id,
                    relevance=decision.relevance,
                    direction=decision.direction,
                    strength=decision.strength,
                    reasoning=decision.reasoning,
                    layer=decision.layer,
                    event_type=decision.event_type,
                    evidence_type=decision.evidence_type,
                )
                # 同一条新闻可能抽取多个 event_type，并命中同一个 market。
                # 这里及时 flush，使后续同 pair 的 upsert 能查到已插入记录，避免 UNIQUE 冲突。
                session.flush()

                if existing is None:

                    stats.links_created += 1
                else:
                    stats.links_updated += 1

                stats.matches_by_event_type.update([decision.event_type])
                if decision.market_condition:
                    stats.matches_by_condition.update([decision.market_condition])
                if decision.evidence_type:
                    stats.matches_by_evidence_type.update([decision.evidence_type])
                stats.matches_by_direction.update([decision.direction])

        session.commit()

    print("\nMatch result:")
    print(f"  news_events processed: {stats.news_events_processed}")
    print(f"  market comparisons:    {stats.markets_processed}")
    print(f"  links created:         {stats.links_created}")
    print(f"  links updated:         {stats.links_updated}")
    print(f"  skipped unclassified:  {stats.skipped_unclassified}")
    print(f"  by evidence_type:      {dict(stats.matches_by_evidence_type)}")
    print(f"  by direction:          {dict(stats.matches_by_direction)}")
    print(f"  by event_type:         {dict(stats.matches_by_event_type.most_common())}")
    print(f"  by market_condition:   {dict(stats.matches_by_condition.most_common())}")

    with get_session() as session:
        links = session.execute(
            select(NewsMarketLinkORM)
            .where(NewsMarketLinkORM.layer == "L2_ONTOLOGY")
            .order_by(NewsMarketLinkORM.id.desc())
            .limit(5)
        ).scalars().all()

        if links:
            print("\nRecent L2_ONTOLOGY samples:")
            for link in links:
                print(
                    f"  news={link.news_id} | market={link.market_id[:16]} | "
                    f"event={link.event_type} | evidence={link.evidence_type} | "
                    f"dir={link.direction} | rel={link.relevance:.2f} | strength={link.strength:.2f}"
                )
                print(f"    reason: {(link.reasoning or '')[:140]}")
        else:
            print("\nNo L2_ONTOLOGY links found.")

    print("\nDone.")


if __name__ == "__main__":
    main()

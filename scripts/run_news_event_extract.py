"""
scripts/run_news_event_extract.py

Phase 1：新闻事件抽取。
读取 news_items → 使用事件本体分类 → upsert news_events。

Usage:
    python scripts/run_news_event_extract.py [--board iran_conflict] [--limit 100] [--top-k 3]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.logging import setup_logging
from polybot.processing.news_event_extractor import ExtractStats, NewsEventExtractor
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import NewsEventORM
from polybot.storage.repositories import list_news_items, upsert_news_event
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 News Event Extractor")
    parser.add_argument("--board", default=None, help="板块 ID，默认读取当前 settings board")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 条新闻，默认全部")
    parser.add_argument("--top-k", type=int, default=3, help="每条新闻最多抽取 N 个事件类型，默认 3")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    board_id = args.board or settings.board.board.id
    extractor = NewsEventExtractor()
    stats = ExtractStats()

    with get_session() as session:
        news_items = list_news_items(session, board_id=board_id, limit=args.limit)

    print("=" * 70)
    print(f"Phase 1 新闻事件抽取 | board={board_id} | news={len(news_items)} | top_k={args.top_k}")
    print("=" * 70)

    if not news_items:
        print("无新闻数据。请先运行 scripts/run_news_collect.py。")
        return

    with get_session() as session:
        for news in news_items:
            stats.news_processed += 1
            drafts = extractor.extract(
                news_id=news.id,
                title=news.title,
                raw_text=news.raw_text,
                top_k=args.top_k,
            )

            print(f"\n[{stats.news_processed:03d}] news_id={news.id} | {news.title[:90]}")
            for draft in drafts:
                existing = session.execute(
                    select(NewsEventORM).where(
                        NewsEventORM.news_id == draft.news_id,
                        NewsEventORM.event_type == draft.event_type,
                    )
                ).scalar_one_or_none()

                upsert_news_event(
                    session=session,
                    news_id=draft.news_id,
                    event_type=draft.event_type,
                    actors_json=json.dumps(draft.actors, ensure_ascii=False),
                    certainty=draft.certainty,
                    time_ref=draft.time_ref,
                    evidence_sentence=draft.evidence_sentence,
                    matched_keywords_json=json.dumps(draft.matched_keywords, ensure_ascii=False),
                    extraction_method=draft.extraction_method,
                )

                if existing is None:
                    stats.events_created += 1
                else:
                    stats.events_updated += 1
                if draft.event_type == "unclassified":
                    stats.unclassified_count += 1
                stats.add_event_type(draft.event_type)

                actor_text = ",".join(draft.actors) if draft.actors else "-"
                keyword_text = ", ".join(draft.matched_keywords[:4]) if draft.matched_keywords else "-"
                print(
                    f"     -> {draft.event_type:28s} | certainty={draft.certainty:9s} | "
                    f"actors={actor_text:20s} | kw={keyword_text}"
                )

        session.commit()

    print("\n" + "=" * 70)
    print("抽取结果:")
    print(f"  news processed:    {stats.news_processed}")
    print(f"  events created:    {stats.events_created}")
    print(f"  events updated:    {stats.events_updated}")
    print(f"  unclassified:      {stats.unclassified_count}")
    print("  by event type:")
    for event_type, count in sorted(stats.by_event_type.items(), key=lambda x: (-x[1], x[0])):
        print(f"    {event_type:28s} {count}")
    print("=" * 70)


if __name__ == "__main__":
    main()

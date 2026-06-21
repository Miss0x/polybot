"""
scripts/run_state_package.py

输出市场状态包雏形。

Usage:
    python scripts/run_state_package.py [--hours 24] [--top 10]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.logging import setup_logging
from polybot.processing.state_package_builder import StatePackageBuilder
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import (
    MarketORM,
    NewsItemORM,
    NewsMarketLinkORM,
    SnapshotORM,
)
from polybot.storage.repositories import list_market_links, list_markets
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description="Market State Package Generator")
    parser.add_argument("--hours", type=int, default=24, help="时间窗口小时数（默认 24）")
    parser.add_argument("--top", type=int, default=0, help="只输出 Top N 市场（0=全部）")
    parser.add_argument("--layer", default="L2_ONTOLOGY", help="读取指定匹配层，默认 L2_ONTOLOGY；传 all 读取全部")

    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    print(f"=== State Package | 窗口={args.hours}h ===\n")

    with get_session() as session:
        # 1. 读取市场
        markets = list_markets(session)
        if not markets:
            print("No markets found.")
            return
        if args.top > 0:
            markets = markets[:args.top]

        # 2. 读取最新 snapshot
        snapshots: dict[str, SnapshotORM] = {}
        for market in markets:
            stmt = (
                select(SnapshotORM)
                .where(SnapshotORM.market_id == market.id)
                .order_by(SnapshotORM.ts.desc())
                .limit(1)
            )
            snap = session.execute(stmt).scalar_one_or_none()
            if snap:
                snapshots[market.id] = snap

        # 3. 读取 links（默认读取 L2_ONTOLOGY，避免旧 L1_RULE 污染 direct/context 验证）
        link_layer = None if args.layer == "all" else args.layer
        links = list_market_links(session, layer=link_layer)

        if not links:
            print("No news-market links found. Run run_news_market_match.py first.")
            return

        # 4. 读取所有新闻（links 引用的）
        news_ids = {link.news_id for link in links}
        news_map: dict[int, NewsItemORM] = {}
        if news_ids:
            stmt = select(NewsItemORM).where(NewsItemORM.id.in_(news_ids))
            for news in session.execute(stmt).scalars().all():
                news_map[news.id] = news

        # 5. 生成状态包
        packages = StatePackageBuilder.build_all(
            markets=markets,
            snapshots=snapshots,
            links=links,
            news_map=news_map,
            hours=args.hours,
        )

        # 6. 输出
        for pkg in packages:
            print(f"{'=' * 60}")
            print(f"Market: {pkg.market_id}")
            print(f"Question: {pkg.question[:80]}")
            print(f"Yes Price: {pkg.yes_price}")
            print(f"+Strength(24h, direct): {pkg.positive_strength_24h:.3f}")
            print(f"-Strength(24h, direct): {pkg.negative_strength_24h:.3f}")
            print(f"Context Strength: +{pkg.context_positive_strength_24h:.3f} / -{pkg.context_negative_strength_24h:.3f}")
            print(f"Direct/Context/Neutral: {pkg.direct_news_24h}/{pkg.context_news_24h}/{pkg.neutral_news_24h}")
            print(f"Matched News Count: {len(pkg.matched_news)}")
            for entry in pkg.matched_news[:3]:
                arrow = "▲" if entry.direction == 1 else "▼" if entry.direction == -1 else "○"
                evidence = entry.evidence_type or "unknown"
                event = entry.event_type or "unknown"
                print(f"  {arrow} [{entry.relevance:.2f}] {evidence}/{event} | {entry.title[:65]}")
                print(f"      → {entry.reasoning[:80]}")

            print()

        # 7. 输出完整 JSON（可选，最后一行输出第一个包的 JSON）
        if packages:
            print("\n--- JSON Sample (first package) ---")
            print(packages[0].to_json(indent=2))

    print(f"\n=== Done: {len(packages)} packages ===")


if __name__ == "__main__":
    main()

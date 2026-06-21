"""
scripts/run_news_market_match.py

执行 L1 新闻-市场匹配。

Usage:
    python scripts/run_news_market_match.py [--hours 72]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.logging import setup_logging
from polybot.processing.news_market_matcher import NewsMarketMatcher
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import MarketProfileORM, NewsItemORM
from polybot.storage.repositories import list_recent_news_items
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description="L1 News-Market Matcher")
    parser.add_argument("--hours", type=int, default=72, help="只匹配近 N 小时的新闻（默认 72）")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    print(f"=== L1 新闻-市场匹配 | 近 {args.hours}h 新闻 ===\n")

    # 预检：profiles
    with get_session() as session:
        profiles = session.execute(select(MarketProfileORM)).scalars().all()
        print(f"market_profiles: {len(profiles)} 条")

        # 预检：news
        news_items = list_recent_news_items(session, hours=args.hours)
        print(f"news_items ({args.hours}h): {len(news_items)} 条")

        if not profiles:
            print("警告: 无 market_profiles，请先运行 run_build_market_profiles.py")
            return
        if not news_items:
            print("警告: 无新闻数据，请先运行新闻采集脚本")
            return

    # 执行匹配
    matcher = NewsMarketMatcher(news_hours=args.hours)
    stats = matcher.run()

    print(f"\n匹配结果:")
    print(f"  markets processed: {stats.markets_processed}")
    print(f"  news processed:   {stats.news_processed}")
    print(f"  links created:    {stats.links_created}")
    print(f"  links updated:    {stats.links_updated}")
    if stats.matches_by_tier:
        print(f"  matches by tier:  {stats.matches_by_tier}")

    # 打印部分命中样例
    with get_session() as session:
        from polybot.storage.models import NewsMarketLinkORM
        from polybot.storage.repositories import list_market_links

        links = list_market_links(session)
        if links:
            print(f"\n--- 最近匹配样例 (前 5 条) ---")
            for link in links[-5:]:
                # 查新闻标题
                news = session.get(NewsItemORM, link.news_id)
                news_title = news.title if news else f"[news_id={link.news_id}]"
                print(
                    f"  tier={link.layer} | relevance={link.relevance:.2f} | "
                    f"direction={link.direction} | market={link.market_id[:16]}"
                )
                print(f"    news: {news_title[:70]}")
                print(f"    reason: {link.reasoning[:80]}")
        else:
            print("\n无匹配结果（可能新闻与市场暂无重叠）")

    print(f"\n=== 完成 ===")


if __name__ == "__main__":
    main()

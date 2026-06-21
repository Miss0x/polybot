"""
scripts/run_news_collect.py
===========================
新闻采集主脚本：拉取 RSS → 关键词过滤 → 去重 → 入库 → 输出摘要。

用法：
    python scripts/run_news_collect.py
    python scripts/run_news_collect.py --board iran_conflict
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from polybot.collect.dedup import NewsDedup, _compute_simhash
from polybot.collect.news_source import NewsItem, RSSSource
from polybot.exceptions import APIRequestError
from polybot.logging import setup_logging
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.repositories import (
    insert_news_item,
    list_existing_news_simhashes,
    list_existing_news_url_hashes,
)


# -------------------------------------------------------------------
# MVP RSS 源配置（可迁移至 boards/*.yaml）
# -------------------------------------------------------------------
DEFAULT_RSS_SOURCES: list[dict[str, str]] = [
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "name": "Al Jazeera"},
    {"url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "name": "BBC Middle East"},
    {"url": "https://www.whitehouse.gov/feed/", "name": "White House"},
    {"url": "https://www.iaea.org/newsfeeds", "name": "IAEA News"},
    {"url": "https://www.defense.gov/News/News-RSS/", "name": "DoD News"},
    {"url": "https://www.state.gov/rss-feed/", "name": "State Dept"},
]


def _build_sources() -> list[RSSSource]:
    return [RSSSource(feed_url=src["url"], name=src["name"]) for src in DEFAULT_RSS_SOURCES]


def _collect_from_source(source: RSSSource) -> tuple[list[NewsItem], list[str]]:
    """从单个 RSS 源拉取新闻，返回 (items, errors)。"""
    try:
        return source.fetch(), []
    except APIRequestError as exc:
        return [], [f"[{source.name}] {exc}"]


def _filter_items_by_keywords(items: list[NewsItem], keywords: list[str]) -> tuple[list[NewsItem], int]:
    """按标题关键词过滤，返回命中条目与未命中数量。"""
    matched = [item for item in items if any(keyword in item.title.lower() for keyword in keywords)]
    filtered_out = len(items) - len(matched)
    return matched, filtered_out


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    board_id = settings.board.board.id
    keywords = [k.lower() for k in settings.board.board.keywords_news]
    sources = _build_sources()

    logger.info("=" * 60)
    logger.info("新闻采集开始 | 板块: {} | 关键词: {}", board_id, keywords)
    logger.info("RSS 源数量: {}", len(sources))

    total_fetched = 0
    total_filtered_by_keyword = 0
    all_errors: list[str] = []
    all_items: list[NewsItem] = []

    # 1. 拉取所有 RSS 源，并立即做关键词过滤
    for source in sources:
        items, errors = _collect_from_source(source)
        fetched = len(items)
        matched_items, filtered = _filter_items_by_keywords(items, keywords)

        total_fetched += fetched
        total_filtered_by_keyword += filtered
        all_errors.extend(errors)
        all_items.extend(matched_items)

        logger.info("[{}] 拉取:{} | 关键词未命中:{} | 命中:{}", source.name, fetched, filtered, len(matched_items))

    logger.info("拉取完成，总条目:{} | 关键词未命中:{} | 待去重:{}", total_fetched, total_filtered_by_keyword, len(all_items))

    if all_errors:
        logger.warning("采集过程出现 {} 个错误:", len(all_errors))
        for error in all_errors:
            logger.warning("  {}", error)

    # 2. URL Hash + SimHash 去重
    with get_session() as session:
        existing_hashes = list_existing_news_url_hashes(session, board_id=board_id)
        existing_simhashes = list_existing_news_simhashes(session, board_id=board_id)

    logger.info("数据库已有 url_hash:{} | simhash:{}", len(existing_hashes), len(existing_simhashes))

    dedup = NewsDedup(existing_url_hashes=existing_hashes, existing_simhashes=existing_simhashes)
    result = dedup.filter(all_items)

    logger.info(
        "去重结果: 新条目:{} | URL重复:{} | SimHash重复:{}",
        len(result.new_items),
        result.dropped_by_url,
        result.dropped_by_simhash,
    )

    if not result.new_items:
        logger.info("没有新条目需要入库，采集结束。")
        return

    # 3. 入库
    inserted = 0
    with get_session() as session:
        for item in result.new_items:
            simhash_hex = hex(_compute_simhash(item.title))
            row = insert_news_item(session, item, title_simhash=simhash_hex, board_tags=board_id)
            if row is not None:
                inserted += 1
        session.commit()

    # 4. 输出摘要
    print("\n" + "=" * 60)
    print(f"采集完成 | 板块: {board_id}")
    print(f"  RSS 源:      {len(sources)} 个")
    print(f"  拉取总数:    {total_fetched}")
    print(f"  关键词未命中: {total_filtered_by_keyword}")
    print(f"  待去重数:    {len(all_items)}")
    print(f"  URL 重复:    {result.dropped_by_url}")
    print(f"  SimHash 重复: {result.dropped_by_simhash}")
    print(f"  成功入库:    {inserted}")
    print("-" * 60)
    if inserted > 0:
        print(f"入库前 {min(5, inserted)} 条预览:")
        for index, item in enumerate(result.new_items[:5], start=1):
            print(f"  {index}. [{item.source_name}] {item.title[:80]}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())


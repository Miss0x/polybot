import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from polybot.collect.market_scanner import MarketScanner
from polybot.collect.polymarket_client import PolymarketClient
from polybot.logging import setup_logging
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.repositories import insert_snapshot, upsert_market


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    client = PolymarketClient(
        gamma_base_url=settings.polymarket.gamma_base_url,
        clob_base_url=settings.polymarket.clob_base_url,
    )
    scanner = MarketScanner(
        client=client,
        board_config=settings.board,
        top_n=settings.app.top_n_markets,
    )

    logger.info("开始扫描市场，板块: {}", settings.board.board.name)
    result = await scanner.scan()
    logger.info("扫描完成，命中市场数: {}", len(result.markets))
    logger.info(
        "扫描统计 | pages_scanned={} | events_scanned={} | excluded_count={} | keyword_hits={}",
        result.pages_scanned,
        result.events_scanned,
        result.excluded_count,
        result.keyword_hits,
    )

    snapshot_ts = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    stored_count = 0

    with get_session() as session:
        for market in result.markets:
            # Phase 1 需要验证增强字段和 raw JSON 是否稳定入库，因此这里显式写入全部新增字段。
            upsert_market(
                session=session,
                market_id=market.id,
                slug=market.slug,
                question=market.question,
                category=result.board_id,
                end_date=market.end_date,
                condition_id=market.condition_id,
                description=market.description,
                subcategory=market.subcategory,
                resolution_source=market.resolution_source,
                outcomes_json=json.dumps(market.outcomes, ensure_ascii=False) if market.outcomes else None,
                clob_token_ids_json=json.dumps(market.clob_token_ids, ensure_ascii=False) if market.clob_token_ids else None,
                raw_event_json=json.dumps(market.raw_event, ensure_ascii=False) if market.raw_event else None,
                raw_market_json=json.dumps(market.raw_market, ensure_ascii=False) if market.raw_market else None,
            )
            insert_snapshot(
                session=session,
                market_id=market.id,
                ts=snapshot_ts,
                yes_price=market.yes_price,
                volume_24h=market.volume_24h,
                liquidity=market.liquidity,
            )
            stored_count += 1
        session.commit()

    logger.info("本次成功写入/更新 markets 数: {}", stored_count)

    print(f"\n监控池 Top {len(result.markets)} | 板块: {result.board_name}")
    print("-" * 120)
    print(
        f"pages_scanned={result.pages_scanned} | events_scanned={result.events_scanned} | "
        f"excluded_count={result.excluded_count} | keyword_hits={result.keyword_hits}"
    )
    for index, market in enumerate(result.markets, start=1):
        print(
            f"{index:02d}. {market.question[:70]} | yes={market.yes_price} | "
            f"vol24h={market.volume_24h} | id={market.id} | condition_id={market.condition_id}"
        )


if __name__ == "__main__":
    asyncio.run(main())



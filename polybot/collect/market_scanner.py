from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger


from polybot.collect.polymarket_client import Market, PolymarketClient
from polybot.settings import BoardConfig


@dataclass
class ScanResult:
    board_id: str
    board_name: str
    markets: list[Market]
    pages_scanned: int = 0
    events_scanned: int = 0
    excluded_count: int = 0
    keyword_hits: int = 0


class MarketScanner:
    def __init__(self, client: PolymarketClient, board_config: BoardConfig, top_n: int = 10):
        self.client = client
        self.board_config = board_config
        self.top_n = top_n
        self.keywords = [keyword.lower() for keyword in board_config.board.keywords_market]

    async def scan(self) -> ScanResult:
        page_size = 100
        max_pages = 5

        matched: list[Market] = []
        unmatched_samples: list[str] = []
        seen_market_ids: set[str] = set()
        pages_scanned = 0
        events_scanned = 0
        excluded_count = 0
        keyword_hits = 0

        tag_slug = self.board_config.board.tag_slug or self.board_config.board.source_slug
        tag_id: str | int | None = None
        if tag_slug:
            tag = await self.client.get_tag_by_slug(tag_slug)
            if tag and tag.get("id"):
                tag_id = tag["id"]
                logger.info("Polymarket tag_slug={} 解析成功，tag_id={}", tag_slug, tag_id)
            else:
                logger.warning("Polymarket tag_slug={} 未解析到 tag，将退回关键词分页扫描", tag_slug)

        for page_index in range(max_pages):
            offset = page_index * page_size
            if tag_slug:
                events = await self.client.list_events(
                    limit=page_size,
                    offset=offset,
                    active=True,
                    closed=False,
                    archived=False,
                    tag_slug=tag_slug,
                    related_tags=False,
                )
            else:
                events = await self.client.list_events(
                    limit=page_size,
                    offset=offset,
                    active=True,
                    closed=False,
                    archived=False,
                )

            if not events:
                logger.info("Polymarket events 在 offset={} 处已无更多数据，提前停止分页扫描", offset)
                break

            pages_scanned += 1
            events_scanned += len(events)
            logger.info("Polymarket events 抓取页 {} | offset={} | 本页数量={}", page_index + 1, offset, len(events))

            for event in events:
                for market_event in self._split_event_markets(event):
                    market = await self.client.build_market(market_event)
                    if market.id in seen_market_ids:
                        continue
                    seen_market_ids.add(market.id)

                    if self._should_exclude_market(market):
                        excluded_count += 1
                        continue

                    if self._match_keywords(market):
                        matched.append(market)
                        keyword_hits += 1
                    elif len(unmatched_samples) < 5:
                        unmatched_samples.append(self._build_debug_sample(market))

        if not matched and tag_id is not None:
            logger.info("events tag_slug={} 未命中，尝试 markets tag_id={} 兜底", tag_slug, tag_id)
            fallback_markets = await self.client.list_markets(
                limit=self.top_n * 5,
                offset=0,
                tag_id=tag_id,
                closed=False,
                include_tag=True,
                related_tags=False,
            )
            pages_scanned += 1
            events_scanned += len(fallback_markets)
            for market_payload in fallback_markets:
                market_event = {**market_payload, "markets": [market_payload]}
                market = await self.client.build_market(market_event)
                if market.id in seen_market_ids:
                    continue
                seen_market_ids.add(market.id)
                if self._should_exclude_market(market):
                    excluded_count += 1
                    continue
                if self._match_keywords(market):
                    matched.append(market)
                    keyword_hits += 1
                elif len(unmatched_samples) < 5:
                    unmatched_samples.append(self._build_debug_sample(market))

        matched.sort(key=lambda item: item.volume_24h or 0.0, reverse=True)

        if not matched and unmatched_samples:
            logger.debug("未命中样本（前 {} 条）: {}", len(unmatched_samples), unmatched_samples)

        return ScanResult(
            board_id=self.board_config.board.id,
            board_name=self.board_config.board.name,
            markets=matched[: self.top_n],
            pages_scanned=pages_scanned,
            events_scanned=events_scanned,
            excluded_count=excluded_count,
            keyword_hits=keyword_hits,
        )

    @staticmethod
    def _split_event_markets(event: dict) -> list[dict]:
        markets = event.get("markets") or []
        if not isinstance(markets, list) or not markets:
            return [event]
        return [{**event, "markets": [market]} for market in markets if isinstance(market, dict)]


    def _match_keywords(self, market: Market) -> bool:
        # Phase 1 只做宽松正向召回：在已经过 iran_conflict 定向排除后的候选池中，
        # 尽量把可用结构化文本都拼进 haystack，避免漏掉真实相关市场。
        parts = [
            market.question or "",
            market.slug or "",
            market.description or "",
            market.subcategory or "",
            market.resolution_source or "",
            *market.tags,
        ]
        haystack = " ".join(parts).lower()
        return any(keyword in haystack for keyword in self.keywords)

    def _should_exclude_market(self, market: Market) -> bool:
        if self._is_closed_or_expired(market):
            return True

        # 这里故意不做全局抽象：当前规则只服务 MVP 板块 iran_conflict。
        # 等美伊冲突主链路跑通后，再决定是否把它升级成多板块通用能力。
        if self.board_config.board.id != "iran_conflict":
            return False
        return self._should_exclude_for_iran_conflict(market)

    @staticmethod
    def _is_closed_or_expired(market: Market) -> bool:
        raw_market = market.raw_market or {}
        raw_event = market.raw_event or {}
        if raw_market.get("closed") is True or raw_event.get("closed") is True:
            return True
        if raw_market.get("archived") is True or raw_event.get("archived") is True:
            return True
        if raw_market.get("active") is False or raw_event.get("active") is False:
            return True
        if market.end_date:
            now = datetime.now(timezone.utc)
            end_date = market.end_date
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            if end_date < now:
                return True
        return False


    @staticmethod
    def _should_exclude_for_iran_conflict(market: Market) -> bool:
        subcategory = (market.subcategory or "").strip().lower()
        text = " ".join(
            [
                market.question or "",
                market.slug or "",
                market.description or "",
                market.subcategory or "",
                *market.tags,
            ]
        ).lower()

        # 1) 体育事件：项目当前不追求这种强时效盘口。
        if subcategory == "sports":
            return True
        sports_terms = [
            "nba", "nfl", "mlb", "ufc", "fight", "playoff", "score", "goal", "match", " vs ",
            "tko", "ko", "round 1", "semifinals", "finals",
        ]
        if any(term in text for term in sports_terms):
            return True

        # 2) 加密事件：当前 MVP 不是做币圈短时定价。
        if subcategory == "crypto":
            return True
        crypto_terms = [
            "bitcoin", "btc", "ethereum", " eth ", "solana", "token", "memecoin", "nft", "airdrop",
        ]
        if any(term in text for term in crypto_terms):
            return True

        # 3) 电竞 / 游戏比分：不属于当前地缘政治垂直方向。
        esports_terms = [
            "esports", "valorant", "dota", "csgo", "cs2", "league of legends", "map 1", "map 2",
        ]
        if any(term in text for term in esports_terms):
            return True

        # 4) 天气类事件：需要专门建模，当前阶段先排除。
        weather_terms = [
            "weather", "hurricane", "storm", "rainfall", "snowfall", "tornado", "temperature",
        ]
        if any(term in text for term in weather_terms):
            return True

        # 5) 已知误命中噪声：例如 Israel Adesanya。
        if "adesanya" in text:
            return True

        return False

    @staticmethod
    def _build_debug_sample(market: Market) -> str:
        description = (market.description or "").replace("\n", " ").strip()
        if len(description) > 80:
            description = f"{description[:77]}..."
        return (
            f"question={market.question!r}, slug={market.slug!r}, "
            f"subcategory={market.subcategory!r}, tags={market.tags!r}, description={description!r}"
        )



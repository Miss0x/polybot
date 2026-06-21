from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from polybot.exceptions import APIRequestError, DataValidationError


@dataclass
class Market:
    id: str
    slug: str
    question: str
    yes_price: float | None
    volume_24h: float | None
    liquidity: float | None
    end_date: datetime | None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    condition_id: str | None = None
    description: str | None = None
    subcategory: str | None = None
    resolution_source: str | None = None
    outcomes: list[str] = field(default_factory=list)
    clob_token_ids: list[str] = field(default_factory=list)
    raw_event: dict[str, Any] = field(default_factory=dict)
    raw_market: dict[str, Any] = field(default_factory=dict)


@dataclass
class PricePoint:
    ts: datetime
    price: float


class PolymarketClient:
    def __init__(self, gamma_base_url: str, clob_base_url: str, timeout: float = 20.0):
        self.gamma_base_url = gamma_base_url.rstrip("/")
        self.clob_base_url = clob_base_url.rstrip("/")
        self.timeout = timeout

    async def list_events(
        self,
        limit: int = 500,
        offset: int = 0,
        active: bool | None = None,
        archived: bool | None = None,
        closed: bool | None = None,
        tag_slug: str | None = None,
        tag_id: int | str | None = None,
        related_tags: bool | None = None,
    ) -> list[dict[str, Any]]:
        # MVP 阶段只补市场发现需要的 Gamma 参数：状态过滤 + tag 定向扫描。
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if active is not None:
            params["active"] = str(active).lower()
        if archived is not None:
            params["archived"] = str(archived).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if tag_slug:
            params["tag_slug"] = tag_slug
        if tag_id is not None:
            params["tag_id"] = tag_id
        if related_tags is not None:
            params["related_tags"] = str(related_tags).lower()
        return await self._get_json(f"{self.gamma_base_url}/events", params=params)

    async def list_markets(
        self,
        limit: int = 500,
        offset: int = 0,
        tag_id: int | str | None = None,
        closed: bool | None = None,
        include_tag: bool | None = None,
        related_tags: bool | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tag_id is not None:
            params["tag_id"] = tag_id
        if closed is not None:
            params["closed"] = str(closed).lower()
        if include_tag is not None:
            params["include_tag"] = str(include_tag).lower()
        if related_tags is not None:
            params["related_tags"] = str(related_tags).lower()
        return await self._get_json(f"{self.gamma_base_url}/markets", params=params)

    async def get_tag_by_slug(self, slug: str) -> dict[str, Any] | None:
        try:
            return await self._get_json(f"{self.gamma_base_url}/tags/slug/{slug}")
        except APIRequestError:
            return None

    async def get_market(self, market_id: str) -> dict[str, Any]:

        return await self._get_json(f"{self.clob_base_url}/markets/{market_id}")

    async def get_price_history(self, market_id: str, interval: str = "15m") -> list[dict[str, Any]]:
        params = {"market": market_id, "interval": interval}
        try:
            return await self._get_json(f"{self.clob_base_url}/prices-history", params=params)
        except APIRequestError:
            return []


    async def build_market(self, event: dict[str, Any]) -> Market:
        # Phase 1 仍以 event 为扫描单元，但结构化字段优先从第一个 market 中提取。
        # 这样可以兼容当前 Gamma API 的 event/market 双层结构，同时不打破现有表主键策略。
        markets_in_event = event.get("markets") or []
        market0 = markets_in_event[0] if isinstance(markets_in_event, list) and markets_in_event else {}

        market_id = str(market0.get("id") or event.get("market_id") or event.get("id") or "")
        if market0:
            event = {**event, "markets": [market0]}

        question = str(
            market0.get("question")
            or market0.get("title")
            or event.get("question")
            or event.get("title")
            or ""
        ).strip()

        if not market_id or not question:
            raise DataValidationError("Polymarket event 缺少 id 或 question")

        slug = str(market0.get("slug") or event.get("slug") or "")

        volume_24h = self._to_float(
            market0.get("volume24hr")
            or market0.get("volume24h")
            or market0.get("volume_24hr")
            or event.get("volume24hr")
            or event.get("volume_24hr")
            or event.get("volume24h")
        )
        liquidity = self._to_float(
            market0.get("liquidity")
            or market0.get("liquidityNum")
            or event.get("liquidity")
            or event.get("liquidityClob")
            or event.get("liquidityAmm")
        )
        end_date = self._parse_datetime(
            market0.get("endDate")
            or market0.get("end_date")
            or event.get("endDate")
            or event.get("end_date")
        )
        tags = self._extract_tags(event)
        yes_price = self._extract_yes_price(event=event, market=market0)

        condition_id = str(
            market0.get("conditionId")
            or market0.get("condition_id")
            or event.get("conditionId")
            or event.get("condition_id")
            or ""
        ) or None
        description = str(
            event.get("description")
            or market0.get("description")
            or event.get("subtitle")
            or ""
        ) or None
        subcategory = str(
            event.get("subcategory")
            or market0.get("subcategory")
            or market0.get("category")
            or event.get("category")
            or ""
        ) or None
        resolution_source = str(
            event.get("resolutionSource")
            or event.get("resolution_source")
            or market0.get("resolutionSource")
            or market0.get("resolution_source")
            or event.get("source")
            or ""
        ) or None

        # outcomes / clobTokenIds 在 market 层更常见，因此优先读取 market0，再回退到 event 层。
        outcomes = self._parse_json_list(
            market0.get("outcomes")
            or event.get("outcomes")
            or event.get("outcomes_list")
        )
        clob_token_ids = self._parse_json_list(
            market0.get("clobTokenIds")
            or market0.get("clob_token_ids")
            or event.get("clobTokenIds")
            or event.get("clob_token_ids")
        )

        raw_event = event
        raw_market = market0 if isinstance(market0, dict) else {}

        return Market(
            id=market_id,
            slug=slug,
            question=question,
            yes_price=yes_price,
            volume_24h=volume_24h,
            liquidity=liquidity,
            end_date=end_date,
            tags=tags,
            raw=event,
            condition_id=condition_id,
            description=description,
            subcategory=subcategory,
            resolution_source=resolution_source,
            outcomes=outcomes,
            clob_token_ids=clob_token_ids,
            raw_event=raw_event,
            raw_market=raw_market,
        )

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise APIRequestError(f"请求 Polymarket API 失败: {url}") from exc

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        value = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _extract_tags(event: dict[str, Any]) -> list[str]:
        raw_tags: list[Any] = []
        event_tags = event.get("tags") or []
        if isinstance(event_tags, list):
            raw_tags.extend(event_tags)
        markets = event.get("markets") or []
        if isinstance(markets, list) and markets:
            market_tags = markets[0].get("tags") or [] if isinstance(markets[0], dict) else []
            if isinstance(market_tags, list):
                raw_tags.extend(market_tags)

        tags: list[str] = []
        for item in raw_tags:
            if isinstance(item, str):
                tags.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("label") or item.get("slug")
                if name:
                    tags.append(str(name))
        return list(dict.fromkeys(tags))


    @staticmethod
    def _extract_yes_price(event: dict[str, Any], market: dict[str, Any] | None = None) -> float | None:
        market = market or {}
        # Polymarket 的 YES 概率字段位置不稳定，这里按“market 层优先、event 层兜底”顺序尝试。
        candidates = [
            market.get("lastTradePrice"),
            market.get("yes_price"),
            market.get("yesPrice"),
            event.get("lastTradePrice"),
            event.get("yes_price"),
            event.get("yesPrice"),
            event.get("probability"),
        ]

        outcome_prices = (
            market.get("outcomePrices")
            or market.get("outcome_prices")
            or event.get("outcomePrices")
            or event.get("outcome_prices")
        )
        if isinstance(outcome_prices, list) and outcome_prices:
            candidates.append(outcome_prices[0])
        elif isinstance(outcome_prices, str):
            parsed = PolymarketClient._parse_json_list(outcome_prices)
            if parsed:
                candidates.append(parsed[0])
            else:
                cleaned = outcome_prices.strip().replace("[", "").replace("]", "")
                if cleaned:
                    candidates.append(cleaned.split(",")[0].strip())

        for candidate in candidates:
            price = PolymarketClient._to_float(candidate)
            if price is not None:
                return price
        return None

    @staticmethod
    def _parse_json_list(value: Any) -> list[str]:
        """安全解析 JSON 列表字段；支持真实 list、JSON 字符串，失败时返回空列表。"""
        if isinstance(value, list):
            return [str(v) for v in value if v is not None]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed if v is not None]
            except Exception:
                # 有些返回值不是标准 JSON，而是逗号拼接字符串；这里做保守降级解析。
                cleaned = stripped.replace("[", "").replace("]", "")
                if cleaned:
                    return [part.strip().strip('"').strip("'") for part in cleaned.split(",") if part.strip()]
        return []


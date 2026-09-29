"""serbia_markets.py — 塞尔维亚选举相关合约价格采样（价格账本）

用 Gamma public-search 拉取 serbia 相关事件（实测含下届总理/议会胜者/投票率等 7+ 个），
逐个 nested market 提取 Yes 价、成交量、流动性，upsert markets + snapshots。

注意：Gamma public-search 返回的 event.markets[].outcomePrices 为字符串化 JSON。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select

from polybot.storage.db import get_session
from polybot.storage.models import MarketORM, SnapshotORM


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SerbiaMarketSampler:
    # 只保留选举相关事件，剔除体育赛事（"X vs Y"）等噪声
    ELECTION_HINTS = [
        "election", "prime minister", "presidential", "president",
        "parliament", "vote share", "turnout", "parliamentary", "izbori",
    ]

    def __init__(self, gamma_base_url: str = "https://gamma-api.polymarket.com",
                 query: str = "serbia", timeout: float = 20.0):
        self.gamma = gamma_base_url.rstrip("/")
        self.query = query
        self.timeout = timeout

    # ------------------------------------------------------------------
    def sample(self) -> dict:
        """采样一次全部相关市场，返回统计。"""
        events = self._search_events()
        stats = {"events": 0, "markets": 0, "snapshots": 0}

        with get_session() as session:
            now = _utc_now()
            for event in events:
                stats["events"] += 1
                for m in event.get("markets") or []:
                    market_id = str(m.get("id") or "")
                    if not market_id:
                        continue
                    stats["markets"] += 1

                    yes_price = self._extract_yes_price(m)
                    volume = _to_float(m.get("volume"))
                    liquidity = _to_float(m.get("liquidity"))

                    # upsert markets
                    existing = session.get(MarketORM, market_id)
                    if existing is None:
                        session.add(
                            MarketORM(
                                id=market_id,
                                slug=m.get("slug"),
                                question=m.get("question") or event.get("title") or market_id,
                                category="elections",
                                subcategory="serbia_2026",
                                end_date=self._parse_dt(m.get("endDate") or event.get("endDate")),
                                updated_at=now,
                                created_at=now,
                            )
                        )
                    else:
                        existing.updated_at = now

                    # 价格快照（账本）
                    if yes_price is not None:
                        session.add(
                            SnapshotORM(
                                market_id=market_id,
                                ts=now,
                                yes_price=yes_price,
                                volume_24h=_to_float(m.get("volume24hr")),
                                liquidity=liquidity,
                            )
                        )
                        stats["snapshots"] += 1

            session.commit()

        logger.info("价格采样完成: {}", stats)
        return stats

    # ------------------------------------------------------------------
    def _search_events(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.gamma}/public-search",
                params={"q": self.query, "limit_per_type": 20},
            )
            resp.raise_for_status()
            events = resp.json().get("events", [])

        filtered: list[dict[str, Any]] = []
        for event in events:
            title = (event.get("title") or "").lower()
            # 体育赛事噪声过滤（Serbia vs Netherlands 之类）
            if " vs " in title or " vs." in title:
                continue
            # 只保留选举相关事件
            if not any(h in title for h in self.ELECTION_HINTS):
                continue
            # 已收盘市场不入账本
            markets = [m for m in (event.get("markets") or []) if not m.get("closed")]
            if not markets:
                continue
            filtered.append({**event, "markets": markets})
        return filtered

    @staticmethod
    def _extract_yes_price(market: dict[str, Any]) -> float | None:
        raw = market.get("outcomePrices")
        if not raw:
            return None
        try:
            prices = raw if isinstance(raw, list) else json_loads(raw)
            if prices:
                return _to_float(prices[0])
        except Exception:
            return None
        return None

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None


def json_loads(text: str) -> list:
    import json

    return json.loads(text)

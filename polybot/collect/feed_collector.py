"""feed_collector.py — Serbia election pipeline 采集器（W1 D1）

设计要点：
- 复用既有 RSSSource（feedparser + httpx，已验证 3 条原生 RSS + 8 条 Google News 适配 feed）
- 复用既有 NewsDedup（URL hash + SimHash 两级去重）
- 元数据入库：feed_id / source_class / tier / lang；塞语标题机翻英文（fail-open，翻译失败不影响入库）
- Google News 标题带 " - 来源名" 后缀，入库前剥离

用法（见 scripts/run_serbia_pipeline.py）：
    collector = FeedCollector(feeds_config)
    stats = collector.collect_all()
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from loguru import logger
from sqlalchemy import select

from polybot.collect.dedup import NewsDedup
from polybot.collect.news_source import NewsItem, RSSSource
from polybot.storage.db import get_session
from polybot.storage.models import NewsItemORM


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class CollectStats:
    """单次采集统计。"""

    feeds_ok: int = 0
    feeds_failed: list[str] = field(default_factory=list)
    fetched: int = 0
    inserted: int = 0
    dropped_url: int = 0
    dropped_simhash: int = 0
    translated: int = 0

    def summary(self) -> str:
        return (
            f"feeds ok={self.feeds_ok}/{self.feeds_ok + len(self.feeds_failed)} "
            f"failed={self.feeds_failed or 'none'} fetched={self.fetched} "
            f"inserted={self.inserted} dedup(url={self.dropped_url}, sim={self.dropped_simhash}) "
            f"translated={self.translated}"
        )


def load_feeds_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_GN_SUFFIX = re.compile(r"\s+-\s+[^-]{2,40}$")  # Google News 标题尾部的 " - 媒体名"


def _clean_google_news_title(title: str) -> tuple[str, str | None]:
    """剥离 Google News 标题尾部的 ' - 媒体名'，返回 (标题, 媒体名或 None)。"""
    m = _GN_SUFFIX.search(title)
    if m:
        return title[: m.start()].strip(), title[m.start() + 3 :].strip()
    return title.strip(), None


def _translate_to_en(text: str) -> str | None:
    """机翻到英文。fail-open：任何异常返回 None，绝不影响入库。"""
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="en").translate(text)
    except Exception as exc:  # 网络波动/限流等一律降级
        logger.debug("翻译失败（降级为仅原文）: {}", exc)
        return None


class FeedCollector:
    """Serbia election pipeline 的 feed 采集与入库。"""

    def __init__(self, feeds_config_path: Path, translate: bool = True,
                 max_items_per_feed: int | None = None, translate_cap: int = 40):
        cfg = load_feeds_config(feeds_config_path)
        self.election_id: str = cfg["election_id"]
        self.feeds: list[dict] = cfg["feeds"]
        self.translate = translate
        # 配置里的全局上限优先，其次参数
        cap_cfg = cfg.get("max_items_per_feed")
        self.max_items_per_feed = max_items_per_feed or cap_cfg or 30
        self.translate_cap = translate_cap

    # ------------------------------------------------------------------
    def collect_all(self) -> CollectStats:
        stats = CollectStats()
        with get_session() as session:
            # 既有去重索引
            existing_hashes = set(
                session.execute(select(NewsItemORM.url_hash)).scalars().all()
            )
            existing_simhashes = [
                h for h in session.execute(
                    select(NewsItemORM.title_simhash).where(NewsItemORM.title_simhash.is_not(None))
                ).scalars().all()
            ]

            for feed in self.feeds:
                try:
                    items = self._fetch_one(feed)
                except Exception as exc:
                    logger.warning("feed 失败 [{}]: {}", feed["id"], exc)
                    stats.feeds_failed.append(feed["id"])
                    continue

                stats.feeds_ok += 1
                stats.fetched += len(items)

                dedup = NewsDedup(existing_hashes, existing_simhashes)
                result = dedup.filter(items)
                stats.dropped_url += result.dropped_by_url
                stats.dropped_simhash += result.dropped_by_simhash

                translated_count = 0
                for item in result.new_items[: self.max_items_per_feed]:
                    title_en = None
                    if self.translate and feed["lang"] != "en" and stats.translated < self.translate_cap:
                        title_en = _translate_to_en(item.title)
                        if title_en:
                            translated_count += 1
                            stats.translated += 1

                    simhash_hex = _simhash_hex(item.title)
                    orm = NewsItemORM(
                        url_hash=item.url_hash,
                        title_simhash=simhash_hex,
                        title=item.title,
                        url=item.url,
                        source_name=item.source_name,
                        published_at=item.published_at,
                        raw_text=item.raw_text,
                        feed_id=feed["id"],
                        source_class=feed["source_class"],
                        tier=feed["tier"],
                        lang=feed["lang"],
                        title_en=title_en,
                    )
                    session.add(orm)
                    existing_hashes.add(item.url_hash)
                    if simhash_hex:
                        existing_simhashes.append(simhash_hex)
                    stats.inserted += 1

                if translated_count:
                    logger.info("feed [{}] 翻译 {} 条", feed["id"], translated_count)

            session.commit()

        logger.info("采集完成: {}", stats.summary())
        return stats

    # ------------------------------------------------------------------
    def _fetch_one(self, feed: dict) -> list[NewsItem]:
        """抓单个 feed，并给 NewsItem 补充 feed 元数据。"""
        if feed.get("type") == "telegram_web":
            items = _fetch_telegram_channel(feed["url"], name=feed["name"])
        else:
            source = RSSSource(feed["url"], name=feed["name"])
            items = source.fetch()

        enriched: list[NewsItem] = []
        for it in items:
            title, gn_source = _clean_google_news_title(it.title)
            # Google News 条目用适配到的真实媒体名（若可剥离），否则用 feed name
            source_name = gn_source or it.source_name
            enriched.append(
                NewsItem(
                    title=title,
                    url=it.url,
                    source_name=source_name,
                    published_at=it.published_at,
                    raw_text=it.raw_text,
                )
            )
        return enriched


def _simhash_hex(title: str) -> str | None:
    from polybot.collect.dedup import _compute_simhash

    try:
        return hex(_compute_simhash(title))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Telegram 公开频道网页版（t.me/s/<channel>）——无需 API，X 账号实时信息的可行采集路径
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _fetch_telegram_channel(channel_url: str, name: str, limit: int = 30,
                            timeout: float = 20.0) -> list[NewsItem]:
    """解析 t.me/s/ 页面。消息块含 data-post="channel/id" 与 tgme_widget_message_text。"""
    with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}, follow_redirects=True) as client:
        resp = client.get(channel_url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items: list[NewsItem] = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        post = msg.get("data-post", "")           # e.g. EuropeElects/23560
        time_el = msg.select_one("time[datetime]")
        text_el = msg.select_one("div.tgme_widget_message_text")
        if not post or not text_el:
            continue
        text = text_el.get_text("\n", strip=True)
        if not text:
            continue
        published = None
        if time_el:
            try:
                published = datetime.fromisoformat(time_el["datetime"]).replace(tzinfo=None)
            except (ValueError, KeyError):
                pass
        first_line = text.splitlines()[0][:180]
        items.append(
            NewsItem(
                title=first_line,
                url=f"https://t.me/{post.replace('/', '/')}",
                source_name=name,
                published_at=published,
                raw_text=text[:2000],
            )
        )
        if len(items) >= limit:
            break
    return items

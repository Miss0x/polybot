"""新闻源抽象与 RSS 实现。"""

from __future__ import annotations

import email.utils
import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import feedparser
import httpx

from polybot.exceptions import APIRequestError


@dataclass
class NewsItem:
    title: str
    url: str
    source_name: str
    published_at: datetime | None = None
    raw_text: str | None = None

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()[:64]


class NewsSource(ABC):
    """新闻源抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """来源名称，如 'BBC' / 'Al Jazeera'。"""
        ...

    @abstractmethod
    def fetch(self) -> list[NewsItem]:
        """拉取新闻列表。子类实现具体协议（RSS/API/爬虫）。"""
        ...


class RSSSource(NewsSource):
    """通用 RSS / Atom 源。"""

    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

    def __init__(self, feed_url: str, name: str | None = None, timeout: float = 15.0,
                 user_agent: str | None = None):
        self.feed_url = feed_url
        self._name = name
        self.timeout = timeout
        # 部分 RSS 站点（如 BIRN/Cloudflare）会拦截无 UA 的客户端
        self.headers = {"User-Agent": user_agent or self.DEFAULT_UA}

    @property
    def name(self) -> str:
        return self._name or self.feed_url

    def fetch(self) -> list[NewsItem]:
        # feedparser.parse 不支持 timeout，先用 httpx 拉取内容
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers,
                              follow_redirects=True) as client:
                response = client.get(self.feed_url)
                response.raise_for_status()
                content = response.content
        except httpx.HTTPError as exc:
            raise APIRequestError(f"RSS 请求失败 [{self.name}]: {self.feed_url}") from exc

        try:
            feed = feedparser.parse(content)
        except Exception as exc:
            raise APIRequestError(f"RSS 解析失败 [{self.name}]: {self.feed_url}") from exc

        if feed.bozo and not feed.entries:
            raise APIRequestError(f"RSS 源返回空或格式异常 [{self.name}]: {self.feed_url}")

        items: list[NewsItem] = []
        for entry in feed.entries:
            link = _get_link(entry)
            title = _strip_tags(entry.get("title", "")).strip()
            if not link or not title:
                continue

            published_at = _parse_date(entry.get("published") or entry.get("updated"))
            raw_text = _strip_tags(entry.get("summary") or entry.get("content_description", "")).strip()

            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source_name=self.name,
                    published_at=published_at,
                    raw_text=raw_text[:2000] if raw_text else None,
                )
            )
        return items


def _get_link(entry: dict[str, Any]) -> str:
    # feedparser 对 link 的处理：优先取 href，再取纯文本
    link = entry.get("link") or ""
    if isinstance(link, list):
        link = next((l.get("href") or l.get("#text") or "") for l in link if l) or ""
    elif isinstance(link, dict):
        link = link.get("href") or link.get("#text") or ""
    return str(link).strip()


def _strip_tags(text: str | None) -> str:
    """移除 HTML 标签，折叠空白字符。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(value: str | None) -> datetime | None:
    """解析 RFC 822 / ISO 格式日期。"""
    if not value:
        return None
    try:
        t = email.utils.parsedate_to_datetime(value)
        return t.replace(tzinfo=None)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00").split("+")[0])
    except Exception:
        pass
    return None


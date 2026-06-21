"""新闻去重：URL Hash 精确去重 + SimHash 近似去重。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    from simhash import Simhash

    _SIMHASH_AVAILABLE = True
except ImportError:
    _SIMHASH_AVAILABLE = False

from polybot.collect.news_source import NewsItem


@dataclass
class DedupResult:
    new_items: list[NewsItem]
    dropped_by_url: int
    dropped_by_simhash: int
    existing_simhashes: list[str]


class NewsDedup:
    """
    两级去重：
    1. URL Hash — 精确去重，已入库 URL 直接跳过
    2. SimHash — 近似去重，标题足够接近的新闻跳过
    """

    # SimHash 汉明距离阈值，小于等于此值认为相似
    SIMHASH_THRESHOLD: int = 3

    def __init__(self, existing_url_hashes: set[str], existing_simhashes: list[str]):
        self.existing_url_hashes = set(existing_url_hashes)
        self.existing_simhashes: list[int] = []
        if _SIMHASH_AVAILABLE and existing_simhashes:
            for h in existing_simhashes:
                try:
                    self.existing_simhashes.append(int(h, 16))
                except (ValueError, TypeError):
                    pass

    def filter(self, items: list[NewsItem]) -> DedupResult:
        """对新闻列表执行两级去重，返回新条目与统计信息。"""
        new_items: list[NewsItem] = []
        dropped_by_url = 0
        dropped_by_simhash = 0

        seen_url_hashes = set(self.existing_url_hashes)
        seen_simhashes = list(self.existing_simhashes)

        for item in items:
            if item.url_hash in seen_url_hashes:
                dropped_by_url += 1
                continue

            item_simhash = _compute_simhash(item.title)
            if seen_simhashes and _is_similar(item_simhash, seen_simhashes, self.SIMHASH_THRESHOLD):
                dropped_by_simhash += 1
                continue

            new_items.append(item)
            seen_url_hashes.add(item.url_hash)
            seen_simhashes.append(item_simhash)

        return DedupResult(
            new_items=new_items,
            dropped_by_url=dropped_by_url,
            dropped_by_simhash=dropped_by_simhash,
            existing_simhashes=[hex(h) for h in seen_simhashes],
        )


def _compute_simhash(text: str) -> int:
    """计算文本的 SimHash 值。"""
    if not _SIMHASH_AVAILABLE:
        return int(hashlib.md5(text.encode()).hexdigest()[:16], 16)
    return Simhash(text).value


def _is_similar(simhash_value: int, existing: list[int], threshold: int) -> bool:
    """检查 simhash_value 是否与已有列表中的任一项足够接近。"""
    for existing_value in existing:
        if simhash_distance(simhash_value, existing_value) <= threshold:
            return True
    return False


def simhash_distance(a: int, b: int) -> int:
    """两个 SimHash 之间的汉明距离。"""
    return bin(a ^ b).count("1")


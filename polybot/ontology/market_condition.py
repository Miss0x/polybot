"""
market_condition.py — 市场条件归一表加载器

从 config/ontology/{board}_market_conditions.yaml 加载市场条件类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MarketCondition:
    """单个市场条件类型。"""
    id: str
    label: str
    resolution_question: str
    resolution_keywords: tuple[str, ...]
    actors: tuple[str, ...]
    resolution_criteria: dict[str, str] = field(default_factory=dict)

    def matches_market_text(self, text_lower: str) -> list[str]:
        """返回在市场文本中命中的 resolution_keywords。"""
        return [kw for kw in self.resolution_keywords if kw.lower() in text_lower]


@dataclass
class MarketConditionRegistry:
    """一个板块的完整市场条件注册表。"""
    board_id: str
    conditions: dict[str, MarketCondition] = field(default_factory=dict)

    def get(self, condition_id: str) -> MarketCondition | None:
        return self.conditions.get(condition_id)

    def all_ids(self) -> list[str]:
        return list(self.conditions.keys())

    def classify_market(self, market_question: str) -> list[tuple[str, list[str]]]:
        """
        将市场问题归一到条件类型（规则版）。

        返回 [(condition_id, matched_keywords), ...] 按命中数降序。
        """
        text_lower = market_question.lower()
        results: list[tuple[str, list[str]]] = []
        for mc in self.conditions.values():
            hits = mc.matches_market_text(text_lower)
            if hits:
                results.append((mc.id, hits))
        results.sort(key=lambda x: len(x[1]), reverse=True)
        return results


def load_market_conditions(yaml_path: str | Path) -> MarketConditionRegistry:
    """从 YAML 文件加载市场条件注册表。"""
    path = Path(yaml_path)
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    board_id = data.get("board_id", "unknown")
    raw_conditions = data.get("market_conditions", [])

    conditions: dict[str, MarketCondition] = {}
    for item in raw_conditions:
        rc = item.get("resolution_criteria", {})
        mc = MarketCondition(
            id=item["id"],
            label=item.get("label", ""),
            resolution_question=item.get("resolution_question", ""),
            resolution_keywords=tuple(item.get("resolution_keywords", [])),
            actors=tuple(item.get("actors", [])),
            resolution_criteria=rc if isinstance(rc, dict) else {},
        )
        conditions[mc.id] = mc

    return MarketConditionRegistry(board_id=board_id, conditions=conditions)

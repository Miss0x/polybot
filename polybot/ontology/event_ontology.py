"""
event_ontology.py — 事件类型本体加载器

从 config/ontology/{board}_events.yaml 加载受控事件类型库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EventType:
    """单个事件类型。"""
    id: str
    label: str
    description: str
    keywords: tuple[str, ...]
    actors: tuple[str, ...]
    examples: tuple[str, ...]

    def matches_text(self, text_lower: str) -> list[str]:
        """返回在 text_lower 中命中的 keywords 列表。"""
        return [kw for kw in self.keywords if kw.lower() in text_lower]


@dataclass
class EventOntology:
    """一个板块的完整事件本体。"""
    board_id: str
    event_types: dict[str, EventType] = field(default_factory=dict)

    def get(self, event_type_id: str) -> EventType | None:
        return self.event_types.get(event_type_id)

    def all_ids(self) -> list[str]:
        return list(self.event_types.keys())

    def classify_text(self, text_lower: str) -> list[tuple[str, list[str]]]:
        """
        对文本做事件类型分类（规则版）。

        返回 [(event_type_id, matched_keywords), ...] 按命中数降序。
        跳过 unclassified。
        """
        results: list[tuple[str, list[str]]] = []
        for et in self.event_types.values():
            if et.id == "unclassified":
                continue
            hits = et.matches_text(text_lower)
            if hits:
                results.append((et.id, hits))
        results.sort(key=lambda x: len(x[1]), reverse=True)
        return results


def load_event_ontology(yaml_path: str | Path) -> EventOntology:
    """从 YAML 文件加载事件本体。"""
    path = Path(yaml_path)
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    board_id = data.get("board_id", "unknown")
    raw_types = data.get("event_types", [])

    event_types: dict[str, EventType] = {}
    for item in raw_types:
        et = EventType(
            id=item["id"],
            label=item.get("label", ""),
            description=item.get("description", "").strip(),
            keywords=tuple(item.get("keywords", [])),
            actors=tuple(item.get("actors", [])),
            examples=tuple(item.get("examples", [])),
        )
        event_types[et.id] = et

    return EventOntology(board_id=board_id, event_types=event_types)

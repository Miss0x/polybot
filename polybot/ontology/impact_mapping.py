"""
impact_mapping.py — 事件×市场条件映射矩阵加载器

核心查表 API：给定 event_type + market_condition，返回 direction/strength/evidence_type。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# strength 文本 → 数值映射
STRENGTH_MAP: dict[str, float] = {
    "strong": 1.0,
    "medium": 0.6,
    "weak": 0.3,
}


@dataclass(frozen=True)
class ImpactMappingEntry:
    """映射矩阵中的一条记录。"""
    event_type: str
    market_condition: str
    direction: int            # +1 / -1 / 0
    strength: str             # strong / medium / weak
    strength_value: float     # 数值化的 strength
    evidence_type: str        # direct / context
    note: str

    @property
    def is_direct(self) -> bool:
        return self.evidence_type == "direct"


@dataclass
class ImpactMapping:
    """
    完整的映射矩阵。

    查表 API：lookup(event_type, market_condition) → ImpactMappingEntry | None
    """
    board_id: str
    _index: dict[tuple[str, str], ImpactMappingEntry] = field(default_factory=dict)
    _by_event: dict[str, list[ImpactMappingEntry]] = field(default_factory=dict)
    _by_condition: dict[str, list[ImpactMappingEntry]] = field(default_factory=dict)

    def lookup(
        self,
        event_type: str,
        market_condition: str,
    ) -> ImpactMappingEntry | None:
        """查表：给定事件类型和市场条件，返回映射条目。未找到返回 None（即 irrelevant）。"""
        return self._index.get((event_type, market_condition))

    def lookup_by_event(self, event_type: str) -> list[ImpactMappingEntry]:
        """查询某个事件类型影响的所有市场条件。"""
        return self._by_event.get(event_type, [])

    def lookup_by_condition(self, market_condition: str) -> list[ImpactMappingEntry]:
        """查询某个市场条件受哪些事件类型影响。"""
        return self._by_condition.get(market_condition, [])

    def all_entries(self) -> list[ImpactMappingEntry]:
        return list(self._index.values())

    def stats(self) -> dict[str, Any]:
        """返回映射矩阵的统计信息。"""
        entries = self.all_entries()
        return {
            "total_mappings": len(entries),
            "event_types_covered": len(self._by_event),
            "conditions_covered": len(self._by_condition),
            "direct_count": sum(1 for e in entries if e.is_direct),
            "context_count": sum(1 for e in entries if not e.is_direct),
            "by_strength": {
                "strong": sum(1 for e in entries if e.strength == "strong"),
                "medium": sum(1 for e in entries if e.strength == "medium"),
                "weak": sum(1 for e in entries if e.strength == "weak"),
            },
        }


def load_impact_mapping(yaml_path: str | Path) -> ImpactMapping:
    """从 YAML 文件加载映射矩阵。"""
    path = Path(yaml_path)
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    board_id = data.get("board_id", "unknown")
    raw_mappings = data.get("mappings", [])

    index: dict[tuple[str, str], ImpactMappingEntry] = {}
    by_event: dict[str, list[ImpactMappingEntry]] = {}
    by_condition: dict[str, list[ImpactMappingEntry]] = {}

    for item in raw_mappings:
        et = item["event_type"]
        mc = item["market_condition"]
        strength_str = item.get("strength", "weak")

        entry = ImpactMappingEntry(
            event_type=et,
            market_condition=mc,
            direction=int(item.get("direction", 0)),
            strength=strength_str,
            strength_value=STRENGTH_MAP.get(strength_str, 0.3),
            evidence_type=item.get("evidence_type", "context"),
            note=item.get("note", ""),
        )

        index[(et, mc)] = entry
        by_event.setdefault(et, []).append(entry)
        by_condition.setdefault(mc, []).append(entry)

    mapping = ImpactMapping(board_id=board_id)
    mapping._index = index
    mapping._by_event = by_event
    mapping._by_condition = by_condition
    return mapping

"""
验证脚本：加载事件本体 + 市场条件 + 映射矩阵，确认数据完整性。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polybot.ontology import (
    load_event_ontology,
    load_market_conditions,
    load_impact_mapping,
)

ONTOLOGY_DIR = ROOT / "config" / "ontology"


def main():
    print("=" * 70)
    print("Phase 0 验证：事件本体 + 市场条件 + 映射矩阵")
    print("=" * 70)

    # ── 1. 加载事件本体 ──────────────────────────────────────
    events_path = ONTOLOGY_DIR / "iran_conflict_events.yaml"
    ontology = load_event_ontology(events_path)
    print(f"\n[事件本体] board={ontology.board_id}, 事件类型数={len(ontology.all_ids())}")
    for eid in ontology.all_ids():
        et = ontology.get(eid)
        print(f"  {eid:30s} | {et.label:12s} | keywords={len(et.keywords)} | actors={list(et.actors)}")

    # ── 2. 加载市场条件 ──────────────────────────────────────
    conditions_path = ONTOLOGY_DIR / "iran_conflict_market_conditions.yaml"
    registry = load_market_conditions(conditions_path)
    print(f"\n[市场条件] board={registry.board_id}, 条件类型数={len(registry.all_ids())}")
    for cid in registry.all_ids():
        mc = registry.get(cid)
        print(f"  {cid:30s} | {mc.label:12s} | keywords={len(mc.resolution_keywords)}")

    # ── 3. 加载映射矩阵 ──────────────────────────────────────
    mapping_path = ONTOLOGY_DIR / "iran_conflict_mapping.yaml"
    mapping = load_impact_mapping(mapping_path)
    stats = mapping.stats()
    print(f"\n[映射矩阵] board={mapping.board_id}")
    print(f"  总映射数: {stats['total_mappings']}")
    print(f"  覆盖事件类型: {stats['event_types_covered']}")
    print(f"  覆盖市场条件: {stats['conditions_covered']}")
    print(f"  direct: {stats['direct_count']}, context: {stats['context_count']}")
    print(f"  强度分布: {stats['by_strength']}")

    # ── 4. 查表测试 ──────────────────────────────────────────
    print("\n[查表测试]")
    test_cases = [
        ("military_strike", "permanent_peace_deal"),
        ("diplomatic_contact", "diplomatic_meeting"),
        ("peace_deal_signed", "permanent_peace_deal"),
        ("ceasefire", "war_declaration"),
        ("nuclear_development", "iran_nuclear_weapon"),
        ("maritime_incident", "hormuz_traffic_restored"),
        ("oil_market_impact", "regime_fall"),  # 应该是 None（irrelevant）
    ]

    for et_id, mc_id in test_cases:
        entry = mapping.lookup(et_id, mc_id)
        if entry:
            dir_sym = {1: "▲YES", -1: "▼NO", 0: "○中性"}[entry.direction]
            print(f"  {et_id:25s} × {mc_id:25s} → {dir_sym:6s} | {entry.strength:6s} | {entry.evidence_type:7s} | {entry.note}")
        else:
            print(f"  {et_id:25s} × {mc_id:25s} → [irrelevant]")

    # ── 5. 新闻分类测试 ──────────────────────────────────────
    print("\n[新闻事件分类测试]")
    test_headlines = [
        "US and Iran envoys meet in Oman for secret talks",
        "Iran launches missile barrage at Israeli military bases",
        "IAEA reports Iran enriching uranium to 90% purity",
        "Ceasefire extended for another 30 days in Lebanon",
        "Oil prices surge 15% on Iran conflict fears",
        "Reformist candidate wins Iranian presidential election",
        "IRGC seizes oil tanker in Strait of Hormuz",
        "Iran formally declares war on Israel",
    ]

    for headline in test_headlines:
        results = ontology.classify_text(headline.lower())
        if results:
            top = results[0]
            print(f"  \"{headline[:60]}...\"")
            print(f"    → {top[0]} (keywords: {top[1][:3]})")
        else:
            print(f"  \"{headline[:60]}...\"")
            print(f"    → [unclassified]")

    # ── 6. 市场归一测试 ──────────────────────────────────────
    print("\n[市场条件归一测试]")
    test_markets = [
        "US x Iran permanent peace deal by April 30, 2026?",
        "Will US and Iran have a diplomatic meeting by June 2026?",
        "Iran regime fall by end of 2026?",
        "Strait of Hormuz shipping traffic restored by May 2026?",
        "Will Iran develop a nuclear weapon by 2027?",
        "Formal war declaration between US and Iran by 2026?",
    ]

    for market_q in test_markets:
        results = registry.classify_market(market_q)
        if results:
            top = results[0]
            print(f"  \"{market_q[:60]}\"")
            print(f"    → {top[0]} (keywords: {top[1][:3]})")
        else:
            print(f"  \"{market_q[:60]}\"")
            print(f"    → [unmatched]")

    # ── 7. 完整性检查 ─────────────────────────────────────────
    print("\n[完整性检查]")
    event_ids = set(ontology.all_ids()) - {"unclassified"}
    condition_ids = set(registry.all_ids())
    mapped_events = set(mapping._by_event.keys())
    mapped_conditions = set(mapping._by_condition.keys())

    unmapped_events = event_ids - mapped_events
    unmapped_conditions = condition_ids - mapped_conditions

    if unmapped_events:
        print(f"  [WARN] unmapped event types: {unmapped_events}")
    else:
        print(f"  [OK] all event types have mappings")

    if unmapped_conditions:
        print(f"  [WARN] unmapped market conditions: {unmapped_conditions}")
    else:
        print(f"  [OK] all market conditions have mappings")

    print("\n" + "=" * 70)
    print("Phase 0 验证完成")
    print("=" * 70)


if __name__ == "__main__":
    main()

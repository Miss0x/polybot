"""
scripts/run_product_experiment.py — Week 4 Phase 3

本地产品实验脚本。

完整流程：
    读取 markets / snapshots / links / news
    -> 构建 StatePackage
    -> 生成 ProbabilityDraft
    -> 生成 AlertDraft
    -> 输出终端结果
    -> 可选保存 Markdown / JSON

Usage:
    python scripts/run_product_experiment.py [--hours 24] [--top 5] [--output-md reports/week4_product_experiment.md] [--output-json reports/week4_product_experiment.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.analysis.alert_draft_builder import AlertDraft, AlertDraftBuilder
from polybot.analysis.probability_judger import ProbabilityDraft, ProbabilityJudger
from polybot.logging import setup_logging
from polybot.processing.state_package_builder import StatePackage, StatePackageBuilder
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import MarketORM, NewsItemORM, NewsMarketLinkORM, SnapshotORM
from polybot.storage.repositories import list_market_links, list_markets
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Market filtering (P0 — active / target market guard)
# ---------------------------------------------------------------------------

def _is_active_market(market: MarketORM, snapshot: SnapshotORM | None) -> bool:
    """
    过滤过期 / 非目标 / 已解析市场。

    规则：
    1. 只保留 category 为 "iran_conflict" 或 "美伊冲突"（MVP 垂直领域，兼容早期数据）
    2. 排除 end_date 已过期的市场
    3. 排除 yes_price 已完全解析（<=1% 或 >=99%）的市场（有 snapshot 时检查）
    """
    # 非目标板块
    if market.category not in ("iran_conflict", "美伊冲突"):
        return False

    # 有快照时，检查是否已完全解析
    if snapshot is not None and snapshot.yes_price is not None:
        if snapshot.yes_price <= 0.01 or snapshot.yes_price >= 0.99:
            return False

    # 已过期
    if market.end_date:
        now = datetime.now(timezone.utc)
        end_date = market.end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        if end_date < now:
            return False

    return True


# ---------------------------------------------------------------------------
# ProductExperimentResult
# ---------------------------------------------------------------------------

@dataclass
class ProductExperimentResult:
    """实验结果汇总。"""

    generated_at: str
    markets_processed: int
    alerts_generated: int
    watch_items: int
    low_confidence_items: int
    drafts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "markets_processed": self.markets_processed,
            "alerts_generated": self.alerts_generated,
            "watch_items": self.watch_items,
            "low_confidence_items": self.low_confidence_items,
            "drafts": self.drafts,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Polybot Week 4 Product Experiment")
    parser.add_argument("--hours", type=int, default=24, help="时间窗口小时数（默认 24）")
    parser.add_argument("--top", type=int, default=0, help="只处理 Top N 市场（0=全部）")
    parser.add_argument("--output-md", type=str, default=None, help="Markdown 报告输出路径")
    parser.add_argument("--output-json", type=str, default=None, help="JSON 报告输出路径")
    parser.add_argument("--layer", default="L2_ONTOLOGY", help="读取指定匹配层，默认 L2_ONTOLOGY；传 all 读取全部")

    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    print(f"=== Polybot Week 4 Product Experiment | 窗口={args.hours}h ===\n")

    with get_session() as session:
        # 1. 读取市场
        all_markets = list_markets(session)
        if not all_markets:
            print("No markets found.")
            return

        # 2. 读取最新 snapshot 并过滤活跃市场（P0）
        snapshots: dict[str, SnapshotORM] = {}
        markets: list[MarketORM] = []
        for market in all_markets:
            stmt = (
                select(SnapshotORM)
                .where(SnapshotORM.market_id == market.id)
                .order_by(SnapshotORM.ts.desc())
                .limit(1)
            )
            snap = session.execute(stmt).scalar_one_or_none()
            if snap:
                snapshots[market.id] = snap
            if _is_active_market(market, snap):
                markets.append(market)

        if not markets:
            print("No active iran_conflict markets found after filtering.")
            return

        if args.top > 0:
            markets = markets[: args.top]

        print(f"Active markets after filtering: {len(markets)} / {len(all_markets)}\n")

        # 3. 读取 links（默认读取 L2_ONTOLOGY，避免旧 L1_RULE 污染 direct/context 判断）
        link_layer = None if args.layer == "all" else args.layer
        links = list_market_links(session, layer=link_layer)

        if not links:
            print("No news-market links found. Run run_news_market_match.py first.")
            return

        # 4. 读取新闻
        news_ids = {link.news_id for link in links}
        news_map: dict[int, NewsItemORM] = {}
        if news_ids:
            stmt = select(NewsItemORM).where(NewsItemORM.id.in_(news_ids))
            for news in session.execute(stmt).scalars().all():
                news_map[news.id] = news

        # 5. 生成 StatePackage
        packages = StatePackageBuilder.build_all(
            markets=markets,
            snapshots=snapshots,
            links=links,
            news_map=news_map,
            hours=args.hours,
        )

        # 6. 生成 ProbabilityDraft + AlertDraft
        judger = ProbabilityJudger()
        alert_builder = AlertDraftBuilder()

        alert_drafts: list[AlertDraft] = []
        watch_count = 0
        low_conf_count = 0

        for pkg in packages:
            prob_draft = judger.judge(pkg)
            alert_draft = alert_builder.build(prob_draft)
            alert_drafts.append(alert_draft)

            if alert_draft.severity == "watch":
                watch_count += 1
            if prob_draft.confidence == "low":
                low_conf_count += 1

            # 终端输出
            _print_terminal(pkg, prob_draft, alert_draft)

        # 7. 汇总
        alerts_generated = sum(1 for d in alert_drafts if d.should_alert)
        result = ProductExperimentResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            markets_processed=len(packages),
            alerts_generated=alerts_generated,
            watch_items=watch_count,
            low_confidence_items=low_conf_count,
            drafts=[d.to_dict() for d in alert_drafts],
        )

        print(f"\n{'=' * 60}")
        print(f"Summary: {result.markets_processed} markets | {result.alerts_generated} alerts | {result.watch_items} watch | {result.low_confidence_items} low-conf")
        print(f"{'=' * 60}")

        # 8. 保存报告
        if args.output_json:
            _save_json(args.output_json, result.to_dict())
        if args.output_md:
            _save_markdown(args.output_md, packages, alert_drafts, result)

    print("\n=== Done ===")


# ---------------------------------------------------------------------------
# Terminal print
# ---------------------------------------------------------------------------

def _print_terminal(pkg: StatePackage, prob: ProbabilityDraft, alert: AlertDraft) -> None:
    """打印单条市场结果到终端。"""
    print(f"{'=' * 60}")
    print(f"Market : {pkg.market_id}")
    print(f"Q      : {pkg.question[:70]}")
    price_str = f"{pkg.yes_price * 100:.0f}%" if pkg.yes_price is not None else "N/A"
    print(f"YES    : {price_str}")
    print(f"View   : {prob.probability_view.upper()} | Confidence: {prob.confidence.upper()}")
    print(f"Alert  : {'YES' if alert.should_alert else 'NO'} | Severity: {alert.severity.upper()}")
    print(f"Signal : {prob.signal_summary}")
    direct_count = getattr(pkg, "direct_news_24h", 0)
    context_count = getattr(pkg, "context_news_24h", 0)
    print(f"Evidence: direct={direct_count} | context={context_count} | neutral={pkg.neutral_news_24h}")
    if prob.key_news:

        print("Key News:")
        for news in prob.key_news:
            arrow = "▲" if news["direction"] == 1 else "▼" if news["direction"] == -1 else "○"
            event = news.get("event_type") or "unknown"
            evidence = news.get("evidence_type") or "direct"
            print(f"  {arrow} [{news['relevance']:.2f}] {evidence}/{event} | {news['title'][:60]}")

    if prob.risk_notes:
        print("Risk:")
        for note in prob.risk_notes:
            print(f"  - {note}")
    print()


# ---------------------------------------------------------------------------
# Report savers
# ---------------------------------------------------------------------------

def _save_json(path: str, data: dict[str, Any]) -> None:
    """保存 JSON 报告。"""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[Saved JSON] {out_path.resolve()}")


def _save_markdown(
    path: str,
    packages: list[StatePackage],
    alert_drafts: list[AlertDraft],
    result: ProductExperimentResult,
) -> None:
    """保存 Markdown 报告。"""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Polybot Week 4 Product Experiment Report")
    lines.append("")
    lines.append(f"**Generated at:** {result.generated_at}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Markets processed: {result.markets_processed}")
    lines.append(f"- Alerts generated: {result.alerts_generated}")
    lines.append(f"- Watch items: {result.watch_items}")
    lines.append(f"- Low confidence items: {result.low_confidence_items}")
    lines.append("")

    for i, (pkg, alert) in enumerate(zip(packages, alert_drafts), 1):
        lines.append(f"## Market {i}: {pkg.market_id}")
        lines.append("")
        lines.append(f"**Question:** {pkg.question}")
        price_str = f"{pkg.yes_price * 100:.0f}%" if pkg.yes_price is not None else "N/A"
        lines.append(f"**Current YES:** {price_str}")
        lines.append("")
        lines.append(f"**View:** {alert.metadata.get('probability_view', 'N/A')}")
        lines.append(f"**Confidence:** {alert.metadata.get('confidence', 'N/A')}")
        lines.append(f"**Should Alert:** {'Yes' if alert.should_alert else 'No'}")
        lines.append(f"**Severity:** {alert.severity}")
        lines.append("")
        lines.append("### Alert Draft")
        lines.append("```text")
        lines.append(alert.body)
        lines.append("```")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Saved Markdown] {out_path.resolve()}")


if __name__ == "__main__":
    main()

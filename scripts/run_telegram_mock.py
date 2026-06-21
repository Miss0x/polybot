"""
scripts/run_telegram_mock.py — Week 4 Phase 5

Telegram Mock 预演脚本。

完整流程：
    读取 markets / snapshots / links / news
    -> 构建 StatePackage
    -> 生成 ProbabilityDraft
    -> 生成 AlertDraft
    -> TelegramMockSender 模拟发送
    -> 输出终端结果 + 保存 JSONL 日志

Usage:
    python scripts/run_telegram_mock.py [--hours 24] [--top 5]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.analysis.alert_draft_builder import AlertDraftBuilder
from polybot.analysis.probability_judger import ProbabilityJudger
from polybot.logging import setup_logging
from polybot.notify.telegram_mock import TelegramMockSender
from polybot.processing.state_package_builder import StatePackageBuilder
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.models import MarketORM, NewsItemORM, SnapshotORM
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
    if market.category not in ("iran_conflict", "美伊冲突"):
        return False

    if snapshot is not None and snapshot.yes_price is not None:
        if snapshot.yes_price <= 0.01 or snapshot.yes_price >= 0.99:
            return False

    if market.end_date:
        now = datetime.now(timezone.utc)
        end_date = market.end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        if end_date < now:
            return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Polybot Telegram Mock Sender")
    parser.add_argument("--hours", type=int, default=24, help="时间窗口小时数（默认 24）")
    parser.add_argument("--top", type=int, default=0, help="只处理 Top N 市场（0=全部）")
    parser.add_argument("--log", type=str, default="logs/telegram_mock.jsonl", help="JSONL 日志路径")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    print(f"=== Polybot Telegram Mock | 窗口={args.hours}h ===\n")

    sender = TelegramMockSender(log_path=args.log)
    judger = ProbabilityJudger()
    alert_builder = AlertDraftBuilder()

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

        # 3. 读取 links（默认优先使用 L2_ONTOLOGY；若为空再回退全部 links）
        links = list_market_links(session, layer="L2_ONTOLOGY")
        if not links:
            links = list_market_links(session)

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

        # 6. 生成 AlertDraft 并 Mock 发送
        sent_count = 0
        skipped_count = 0
        alert_drafts: list = []

        for pkg in packages:
            prob_draft = judger.judge(pkg)
            alert_draft = alert_builder.build(prob_draft)
            alert_drafts.append(alert_draft)

            result = sender.send(alert_draft)

            if result.sent:
                sent_count += 1
                print(f"{'=' * 60}")
                print(f"[SENT] MOCK SENT | {alert_draft.market_id}")
                print(f"Severity : {alert_draft.severity.upper()}")
                safe_title = alert_draft.title.encode('ascii', 'replace').decode('ascii')
                print(f"Title    : {safe_title}")
                print(f"{'-' * 60}")
                print("Telegram Text Preview:")
                safe_text = result.telegram_text.encode('ascii', 'replace').decode('ascii')
                print(safe_text)
                print(f"{'=' * 60}\n")
            else:
                skipped_count += 1
                print(f"[SKIP] SKIPPED | {alert_draft.market_id} -- {result.reason}")

        # 7. 汇总
        print(f"\n{'=' * 60}")
        print(f"Summary: {len(alert_drafts)} drafts | {sent_count} mock-sent | {skipped_count} skipped")
        print(f"Log file: {sender.log_path}")
        print(f"{'=' * 60}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()

"""
scripts/run_build_market_profiles.py

为当前监控池中的每个市场生成 market_profile，存入 market_profiles 表。

Usage:
    python scripts/run_build_market_profiles.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.logging import setup_logging
from polybot.processing.market_profile_builder import MarketProfileBuilder
from polybot.settings import get_settings
from polybot.storage.db import get_session, init_db
from polybot.storage.repositories import list_markets, upsert_market_profile


def _profile_to_db_args(profile) -> dict:
    """将 MarketProfile dataclass 转为 upsert_market_profile 的参数。"""
    return {
        "market_id": profile.market_id,
        "subjects_json": json.dumps(profile.subjects),
        "actions_json": json.dumps(profile.actions),
        "objects_json": json.dumps(profile.objects),
        "aliases_json": json.dumps(profile.aliases),
        "positive_signals_json": json.dumps(profile.positive_signals),
        "negative_signals_json": json.dumps(profile.negative_signals),
        "context_terms_json": json.dumps(profile.context_terms),
        "ambiguous_terms_json": json.dumps(profile.ambiguous_terms),
        "edge_cases_json": json.dumps(profile.edge_cases),
        "deadline_utc": profile.deadline_utc,
        "generated_method": profile.generated_method,
        "raw_profile_json": profile.raw_profile_json,
    }


def main() -> None:
    settings = get_settings()
    setup_logging(settings.app.log_level)
    init_db()

    # 加载 board config 关键词
    board_keywords = settings.board.board.keywords_market
    board_config = {"keywords_market": board_keywords}
    builder = MarketProfileBuilder(board_config=board_config)

    # 读取所有市场
    with get_session() as session:
        markets = list_markets(session)

    if not markets:
        print("No markets found. Run run_scan.py first.")
        return

    generated = 0
    errors = 0

    with get_session() as session:
        for market in markets:
            try:
                profile = builder.build(market)
                args = _profile_to_db_args(profile)
                upsert_market_profile(session, **args)
                generated += 1
                print(f"[{generated:02d}] {profile.market_id[:20]}")
                print(f"       subjects: {profile.subjects}")
                print(f"       actions:  {profile.actions}")
                print(f"       aliases:  {profile.aliases[:8]}")
                print(f"       pos_sig:  {profile.positive_signals[:3]}")
                print(f"       neg_sig:  {profile.negative_signals[:3]}")
            except Exception as e:
                print(f"[ERR] market {market.id}: {e}")
                errors += 1

        session.commit()

    print(f"\n=== Done: {generated} profiles generated, {errors} errors ===")


if __name__ == "__main__":
    main()

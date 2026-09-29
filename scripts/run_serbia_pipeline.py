"""run_serbia_pipeline.py — Serbia election pipeline 一键主入口（W1 D1-D5）

阶段（可单独执行，默认全部）：
  collect : 11 路 feed 抓取 + 两级去重 + 机翻入库
  triage  : 规则分诊（相关性/变量归属/新颖度/是否新事实）
  markets : Polymarket 塞尔维亚合约族价格采样 → 价格账本
  report  : 三账本现算 → web/index.html（信息通道）+ web/l4_price.html（价格通道）+ md 存档

用法：
  python scripts/run_serbia_pipeline.py                 # 全流程
  python scripts/run_serbia_pipeline.py --report        # 只重渲染报告
定时任务注册（Windows 计划任务，每日 06/12/18/24 点）：
  见 scripts/register_serbia_schedule.bat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONFIG = ROOT / "config"
FEEDS_CFG = CONFIG / "serbia_2026_feeds.yaml"
ELECTION_CFG = CONFIG / "serbia_2026_election.yaml"
NARRATIVE_CFG = CONFIG / "serbia_2026_narrative.yaml"


def init_logging() -> None:
    # polybot.logging 无统一入口函数，这里直接配置 stderr 输出
    logger.remove()
    logger.add(sys.stderr, level="INFO", enqueue=False)


def init_db() -> None:
    from polybot.storage.db import init_db

    init_db()
    logger.info("数据库就绪")


def step_collect() -> None:
    from polybot.collect.feed_collector import FeedCollector

    stats = FeedCollector(FEEDS_CFG).collect_all()
    if stats.feeds_failed:
        logger.warning("失败 feeds: {}（已由结构守卫记录，不影响其余源）", stats.feeds_failed)


def step_triage() -> None:
    from polybot.processing.serbia_triage import SerbiaTriage

    SerbiaTriage(ELECTION_CFG).triage_pending()


def step_markets() -> None:
    import asyncio

    from polybot.collect.serbia_markets import SerbiaMarketSampler

    asyncio.run(asyncio.to_thread(SerbiaMarketSampler().sample)) if False else SerbiaMarketSampler().sample()


def step_report() -> None:
    from polybot.report.briefing_generator import generate

    result = generate(ELECTION_CFG, NARRATIVE_CFG)
    logger.info("报告渲染: {}", result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serbia election pipeline")
    parser.add_argument("--collect", action="store_true", help="只跑采集")
    parser.add_argument("--triage", action="store_true", help="只跑分诊")
    parser.add_argument("--markets", action="store_true", help="只跑价格采样")
    parser.add_argument("--report", action="store_true", help="只重渲染报告")
    args = parser.parse_args()

    run_all = not (args.collect or args.triage or args.markets or args.report)

    init_logging()
    init_db()

    if run_all or args.collect:
        step_collect()
    if run_all or args.triage:
        step_triage()
    if run_all or args.markets:
        step_markets()
    if run_all or args.report:
        step_report()

    logger.info("管线执行完毕 ✅ 打开 web/index.html 查看今日简报")


if __name__ == "__main__":
    main()

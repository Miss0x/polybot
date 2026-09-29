"""triage_sample.py — 分诊质量每周抽检（质量六道闸之五）

随机抽 30 条最近分诊条目导出 Markdown，人工核对：
- 相关性判对了吗？
- 变量归属对吗？
- 新颖度合理吗？
错误率 >10% → 调整提示词/规则。

用法：python scripts/triage_sample.py
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polybot.storage.db import get_session  # noqa: E402
from polybot.storage.models import NewsItemORM  # noqa: E402

REPORTS = ROOT / "reports"
SAMPLE_N = 30


def main() -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    with get_session() as session:
        rows = session.query(NewsItemORM).filter(
            NewsItemORM.triaged_at >= cutoff).all()
        sample = random.sample(rows, min(SAMPLE_N, len(rows)))

        out = [
            "# 分诊抽检报告",
            "",
            f"> 抽样时间：{datetime.now():%Y-%m-%d %H:%M} | 范围：近 7 天 {len(rows)} 条，抽样 {len(sample)} 条",
            "",
            "核对方法：逐条回答 判对/判错 + 原因。错误率 >10%（≥3 条错）→ 调整规则/提示词。",
            "",
            "| # | 分诊 | 相关 | 变量 | 新颖度 | 新事实 | 标题 | 核对结果 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(sample, 1):
            title = (r.title_en or r.title)[:80].replace("|", "/")
            vars_ = (r.variable_ids_json or "").replace('"', "")
            out.append(
                f"| {i} | {r.triage_method} | {r.triage_relevant} | {vars_} "
                f"| {r.novelty} | {r.is_new_fact} | {title} | |"
            )

        REPORTS.mkdir(exist_ok=True)
        out_path = REPORTS / f"triage_audit_{datetime.now():%Y-%m-%d}.md"
        out_path.write_text("\n".join(out), encoding="utf-8")
        print(f"抽检报告已生成: {out_path}")


if __name__ == "__main__":
    main()

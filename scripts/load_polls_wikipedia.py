"""load_polls_wikipedia.py — 民调账本历史录入（ADR D15 原料）

从 Wikipedia《Opinion polling for the next Serbian parliamentary election》解析
2025/2026 两张民调表，结构化写入 polls 表（机构立场/口径标注随行）。

用法：python scripts/load_polls_wikipedia.py
幂等：同 (pollster, fieldwork_end, party) 重复会因唯一约束跳过。
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polybot.storage.db import get_session, init_db  # noqa: E402
from polybot.storage.models import PollORM  # noqa: E402

WIKI_URL = ("https://en.wikipedia.org/wiki/"
            "Opinion_polling_for_the_next_Serbian_parliamentary_election")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"

# 机构元数据：立场 + 口径（引用五要素的机器版）
POLLSTER_META = {
    "NSPM": {"bias": "centre_right_academic",
             "note": "Nova srpska politička misao；按已组联盟的选票样式测量（合并口径）"},
    "CRTA": {"bias": "independent",
             "note": "独立观察机构（与 Stanford Democracy Action Lab 合作）；逐党测量（小党单独列出）"},
    "Faktor Plus": {"bias": "pro_govt_accused", "note": "被反对派与独立媒体指亲政府偏差"},
    "Ipsos": {"bias": "pro_govt_accused", "note": "被指亲政府偏差"},
    "Sprint Insight": {"bias": "unknown", "note": ""},
}

# 表头 → 党派 id 归一化
def _party_id(header: str) -> str | None:
    h = header.lower()
    if "sns" in h or "srsns" in h:
        return "SNS"
    if "student" in h or h.strip().startswith("stu"):
        return "STU"
    if "sps" in h or "js" == h.strip().lower():
        return "SPS"
    if "ss" == h.strip().lower() or "ssp" in h:
        return "SSP"
    if "srce" in h:
        return "SRCE"
    if "nps" in h or "nls" in h:
        return "NPS"
    if "zlf" in h:
        return "ZLF"
    if h.strip() == "ds":
        return "DS"
    if "nada" in h:
        return "NADA"
    if "mi" in h and "sn" in h:
        return "MI_SN"
    if h.strip() == "kp":
        return "KP"
    if "ndss" in h or "poks" in h:
        return None  # 2025 表的旧列，跳过
    if "lead" in h or "其他" in h:
        return None
    if "other" in h:
        return "OTHERS"
    return None


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _parse_date(text: str, year: int) -> datetime | None:
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)", text.strip())
    if not m:
        return None
    day, mon = int(m.group(1)), _MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    return datetime(year, mon, day)


def main() -> None:
    init_db()
    resp = httpx.get(WIKI_URL, headers={"User-Agent": UA}, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    inserted, skipped = 0, 0
    with get_session() as session:
        for table in soup.find_all("table", class_="wikitable"):
            # 从表格位置向前找最近的年份标题
            year = None
            for prev in table.find_all_previous(re.compile(r"^h[23]$")):
                if re.search(r"20\d\d", prev.get_text()):
                    m = re.search(r"(20\d\d)", prev.get_text())
                    year = int(m.group(1))
                    break
            if not year:
                continue

            headers = [_party_id(th.get_text(strip=True)) for th in table.find_all("th")]
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                texts = [c.get_text(" ", strip=True) for c in cells]
                pollster_raw = texts[0]
                pollster = next((k for k in POLLSTER_META
                                 if k.lower() in pollster_raw.lower()), None)
                if not pollster:
                    continue  # 小机构/汇总行暂不入库
                date = _parse_date(texts[1], year) if len(texts) > 1 else None
                if not date:
                    continue
                sample_n = None
                m = re.match(r"([\d,]+)", texts[2].replace("\u2212", "")) if len(texts) > 2 else None
                if m:
                    sample_n = int(m.group(1).replace(",", ""))

                meta = POLLSTER_META[pollster]
                # 数值列从第 4 列开始（0=pollster,1=date,2=sample,3=pandas 索引占位/首党）
                party_cells = headers[1:]
                value_cells = texts[3:]
                # 对齐：headers[0] 通常是 'Polling firm'，headers[1]='Date'…
                # 表头实际为 [Polling firm, Date, Sample, party...] 时 value 从 texts[3] 起
                for party_hdr, val in zip(headers[3:] if headers and headers[0] is None else headers[1:],
                                          value_cells):
                    if not party_hdr:
                        continue
                    v = re.match(r"(\d+(?:\.\d+)?)", val.replace(",", "."))
                    if not v:
                        continue
                    pct = float(v.group(1))
                    exists = session.query(PollORM).filter_by(
                        pollster=pollster, fieldwork_end=date, party=party_hdr).first()
                    if exists:
                        skipped += 1
                        continue
                    session.add(PollORM(
                        pollster=pollster, bias=meta["bias"],
                        fieldwork_end=date, published_at=date,
                        sample_n=sample_n, party=party_hdr, pct=pct,
                        method_note=meta["note"],
                        source_url=WIKI_URL,
                    ))
                    inserted += 1
        session.commit()

    logger.info("民调录入完成: 新增 {} 条，跳过（已存在）{} 条", inserted, skipped)


if __name__ == "__main__":
    main()

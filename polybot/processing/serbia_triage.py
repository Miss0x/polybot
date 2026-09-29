"""serbia_triage.py — 规则分诊 v1（W1 D3）

对 news_items 中未分诊的条目打标：
- triage_relevant：与塞尔维亚选举相关？（关键词命中即相关）
- variable_ids_json：命中的关键变量列表
- novelty：1-5 新颖度（源等级 + 时效近似）
- is_new_fact：含新事实（区别于分析/观点，v1 用启发式）

Jev 接口预留（ADR D5）：设置环境变量 TYPESAFE_API_KEY 后可切换 jev_v1 分诊；
v1 用规则版跑通全链路，Jev 接入后每周人工抽检 30 条对比两版命中率。

规则分诊的局限（诚实记录在案）：关键词匹配对塞语变音、转写（Vučić/Vucic）脆弱，
已尽量双写；语义级判断留给 Jev v2。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import select, update

from polybot.storage.db import get_session
from polybot.storage.models import NewsItemORM

TRIAGE_METHOD = "rule_v1"

# 判定"含新事实"的信号词（对标题/摘要做启发式判断）
_FACT_HINTS_EN = [
    "announc", "confirm", "sign", "launch", "submit", "withdraw", "resign",
    "elect", "win", "poll", "court", "bill", "law", "arrest", "register",
]
_FACT_HINTS_SR = [
    "objav", "potvrđ", "potvrd", "povuk", "predao", "ostavk", "izabr",
    "pobed", "pokren", "usvoj", "donet", "registrovan",
]
_OPINION_HINTS = ["opinion", "analys", "editorial", "mislio", "kolumna", "blog"]


class SerbiaTriage:
    def __init__(self, election_config_path: Path):
        with election_config_path.open("r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.election_id: str = self.cfg["election_id"]
        self.variables: list[dict] = self.cfg["key_variables"]

    # ------------------------------------------------------------------
    def triage_pending(self, batch_limit: int = 500) -> dict:
        """对未分诊条目执行规则分诊并入库。"""
        stats = {"pending": 0, "relevant": 0, "irrelevant": 0}

        with get_session() as session:
            rows = session.execute(
                select(NewsItemORM)
                .where(NewsItemORM.triage_relevant.is_(None))
                .order_by(NewsItemORM.id.desc())
                .limit(batch_limit)
            ).scalars().all()

            stats["pending"] = len(rows)
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            for row in rows:
                text = " ".join(
                    x for x in (row.title, row.title_en, row.raw_text or "") if x
                ).lower()

                hit_vars, strength = self._match_variables(text)
                relevant = 1 if (hit_vars or self._mentions_election(text)) else 0
                novelty = self._novelty(row, strength)
                new_fact = self._is_new_fact(text) if relevant else None

                row.triage_relevant = relevant
                row.variable_ids_json = json.dumps(hit_vars, ensure_ascii=False) if hit_vars else None
                row.novelty = novelty
                row.is_new_fact = new_fact
                row.triage_method = TRIAGE_METHOD
                row.triaged_at = now

                if relevant:
                    stats["relevant"] += 1
                else:
                    stats["irrelevant"] += 1

            session.commit()

        logger.info("分诊完成: {}", stats)
        return stats

    # ------------------------------------------------------------------
    def _match_variables(self, text: str) -> tuple[list[str], int]:
        hits: list[str] = []
        strength = 0
        for var in self.variables:
            for kw in var.get("keywords", []):
                if kw.lower() in text:
                    hits.append(var["id"])
                    strength += 1
                    break
        return hits, strength

    @staticmethod
    def _mentions_election(text: str) -> bool:
        anchors = ["serbia", "srbij", "србиј", "beograd", "belgrade", "izbori"]
        election_words = ["izbor", "elect", "anket", "poll", "kampanj", "campaign", "vote"]
        return any(a in text for a in anchors) and any(w in text for w in election_words)

    @staticmethod
    def _novelty(row: NewsItemORM, kw_strength: int) -> int:
        """1-5 新颖度近似：源等级越高、命中变量越多、越新 → 越高。"""
        base = {"A1": 5, "A2": 4, "A3": 3, "A4": 2}.get(row.tier or "", 2)
        if kw_strength >= 3:
            base += 1
        if row.source_class and row.source_class != "core":
            base = min(base, 2)  # 旁证/实时类未验证前压低
        return max(1, min(5, base))

    @staticmethod
    def _is_new_fact(text: str) -> bool:
        if any(h in text for h in _OPINION_HINTS):
            return False
        return any(h in text for h in _FACT_HINTS_EN) or any(h in text for h in _FACT_HINTS_SR)

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
        """对未分诊条目执行分诊并入库。有 LLM key 走语义分诊，否则规则版。"""
        from polybot.llm_client import llm_available, chat_json

        use_llm = llm_available()
        stats = {"pending": 0, "relevant": 0, "irrelevant": 0, "llm": 0, "rule": 0}

        sys_prompt = (
            "You are a strict classifier for a Serbian 2026-10-25 parliamentary "
            "election intelligence pipeline. For each news item, answer four CLOSED "
            "questions only:\n"
            "1) relevant: is it about Serbian politics/elections? true/false\n"
            "2) variables: pick from this fixed list (empty if none): "
            + ",".join(v["id"] for v in self.variables) + "\n"
            "3) novelty: 1-5 (5=decisive new fact, 3=incremental, 1=repetition/noise)\n"
            "4) new_fact: does it contain a NEW factual claim (not opinion/analysis)?\n"
            'Respond with ONLY a JSON array, same order as input, items like '
            '{"i":0,"relevant":true,"variables":["coalition"],"novelty":4,"new_fact":true}. '
            "No prose."
        )

        with get_session() as session:
            rows = session.execute(
                select(NewsItemORM)
                .where(NewsItemORM.triage_relevant.is_(None))
                .order_by(NewsItemORM.id.desc())
                .limit(batch_limit)
            ).scalars().all()

            stats["pending"] = len(rows)

            # 先做 LLM 批量语义分诊（一批 15 条），结果按行 id 存表
            llm_results: dict[int, dict] = {}
            if use_llm:
                for i in range(0, len(rows), 15):
                    chunk = rows[i:i + 15]
                    user_prompt = "\n".join(
                        f'{{"i":{j},"title":{json.dumps((r.title_en or r.title)[:220], ensure_ascii=False)}}}'
                        for j, r in enumerate(chunk)
                    )
                    parsed = chat_json(sys_prompt, user_prompt, max_tokens=1200)
                    if isinstance(parsed, list):
                        for x in parsed:
                            if isinstance(x, dict) and isinstance(x.get("i"), int) and 0 <= x["i"] < len(chunk):
                                llm_results[chunk[x["i"]].id] = x
                    else:
                        logger.warning("LLM 分诊批返回不可解析（{} 条降级规则）", len(chunk))

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for row in rows:
                item = llm_results.get(row.id)
                if item is not None:
                    self._apply(row, item, stats)
                else:
                    self._apply_rules(row, stats)

            session.commit()

        logger.info("分诊完成: {}", stats)
        return stats

    # ------------------------------------------------------------------
    def _apply(self, row: NewsItemORM, item: dict, stats: dict) -> None:
        """应用单条 LLM 分诊结果。"""
        relevant = 1 if item.get("relevant") else 0
        var_ids = [v for v in (item.get("variables") or [])
                   if v in {x["id"] for x in self.variables}]
        try:
            novelty = max(1, min(5, int(item.get("novelty") or 3)))
        except (TypeError, ValueError):
            novelty = 3
        row.triage_relevant = relevant
        row.variable_ids_json = json.dumps(var_ids, ensure_ascii=False) if var_ids else None
        row.novelty = novelty if relevant else None
        row.is_new_fact = 1 if (relevant and item.get("new_fact")) else (0 if relevant else None)
        row.triage_method = "llm_v1"
        row.triaged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        stats["relevant" if relevant else "irrelevant"] += 1
        stats["llm"] += 1

    def _apply_rules(self, row: NewsItemORM, stats: dict) -> None:
        """规则分诊（降级路径 / 无 LLM key 时的默认路径）。"""
        text = " ".join(
            x for x in (row.title, row.title_en, row.raw_text or "") if x
        ).lower()
        hit_vars, _ = self._match_variables(text)
        relevant = 1 if (hit_vars or self._mentions_election(text)) else 0
        row.triage_relevant = relevant
        row.variable_ids_json = json.dumps(hit_vars, ensure_ascii=False) if hit_vars else None
        row.novelty = self._novelty(row, len(hit_vars)) if relevant else None
        row.is_new_fact = (self._is_new_fact(text) if relevant else None)
        row.triage_method = "rule_v1"
        row.triaged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        stats["relevant" if relevant else "irrelevant"] += 1
        stats["rule"] += 1

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

"""judgment_generator.py — 方向判断页生成器（yes/no + 佐证，非概率）

定位（用户 2026-09-30 指示 + §10 边界规则）：
- 对前几个大事件输出方向判断：yes / no / unclear + 置信度 + 佐证 + 反方 + 翻转条件
- 判断只基于账本证据（事实 + 民调数字），LLM 不得引入外部知识
- 不输出概率；市场参考价并列展示供对照（页面标注混合通道，建议决策时读取）

流程：每题组证据包（关联变量的事实 + 各机构最新民调）→ LLM 严格 JSON 判断
→ web/judgment.html + reports 存档。
"""

from __future__ import annotations

import html as html_mod
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import select

from polybot.llm_client import chat_json, llm_available
from polybot.storage.db import get_session
from polybot.storage.models import NewsItemORM, PollORM


def _esc(text: str) -> str:
    return html_mod.escape(str(text or ""))

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"
REPORTS_DIR = ROOT / "reports"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_cfg(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _poll_summary(session) -> str:
    """各机构最新一次民调的 SNS / 学生名单数字（带口径）。"""
    lines = []
    for pollster in ["CRTA", "NSPM", "Faktor Plus", "Ipsos"]:
        latest_date = session.execute(
            select(PollORM.fieldwork_end).where(PollORM.pollster == pollster)
            .order_by(PollORM.fieldwork_end.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_date is None:
            continue
        meta = session.query(PollORM).filter_by(pollster=pollster, fieldwork_end=latest_date).first()
        nums = session.execute(
            select(PollORM.party, PollORM.pct).where(PollORM.pollster == pollster)
            .where(PollORM.fieldwork_end == latest_date)
        ).all()
        nums_s = ", ".join(f"{p}={v:.1f}%" for p, v in nums)
        note = (meta.method_note[:80] if meta and meta.method_note else "")
        lines.append(f"- {pollster} (fieldwork {latest_date:%Y-%m-%d}, n={meta.sample_n if meta else '?'}): {nums_s}. Method: {note}")
    return "\n".join(lines) or "(no polls in ledger)"


def _evidence_pack(session, variables: list[str], market_hint: str, limit: int = 8) -> str:
    """证据包：关联变量下近 14 天新颖度最高的事实。"""
    parts = []
    for var in variables:
        rows = session.execute(
            select(NewsItemORM)
            .where(NewsItemORM.triage_relevant == 1)
            .where(NewsItemORM.variable_ids_json.like(f'%"{var}"%'))
            .where(NewsItemORM.created_at >= _utc_now() - timedelta(days=14))
            .order_by(NewsItemORM.novelty.desc(), NewsItemORM.created_at.desc())
            .limit(4)
        ).scalars().all()
        for r in rows:
            title = (r.title_en or r.title).replace("\n", " ")[:180]
            d = (r.published_at or r.created_at).strftime("%m-%d")
            parts.append(f"[{d}|{r.tier}|var={var}] {title}")
    # 市场线索：当前相关合约的问题与价格（供对照，不作证据）
    return "\n".join(parts[:limit * 2]) or "(no evidence in ledger)"


def _ask_judgment(question: str, evidence: str) -> dict | None:
    sys_prompt = (
        "You are a careful election intelligence analyst. Based ONLY on the evidence "
        "provided (facts with dates, and poll numbers), answer the closed question with "
        "a DIRECTION judgment — NOT a probability.\n"
        'Respond ONLY as JSON: {"judgment":"yes|no|unclear","confidence":"low|medium|high",'
        '"reason":"2-3 sentences citing specific evidence from the pack",'
        '"counter":"the strongest single counter-argument from the evidence",'
        '"change_if":"what new information would flip this judgment"}. '
        "Rules: no probabilities, no numbers invented, if evidence is thin use "
        '"unclear" with low confidence. All content must come from the evidence pack.'
    )
    return chat_json(sys_prompt, f"EVIDENCE PACK:\n{evidence}\n\nQUESTION: {question}", max_tokens=800)


def _market_price_ref(session, market_hint: str) -> str:
    from polybot.storage.models import MarketORM, SnapshotORM
    row = session.execute(
        select(MarketORM).where(MarketORM.question.ilike(f"%{market_hint}%"))
        .order_by(MarketORM.question).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return ""
    snap = session.execute(
        select(SnapshotORM).where(SnapshotORM.market_id == row.id)
        .order_by(SnapshotORM.ts.desc()).limit(1)
    ).scalar_one_or_none()
    if snap is None or snap.yes_price is None:
        return ""
    return f"{snap.yes_price * 100:.1f}"


def generate(election_cfg_path: Path, judgments_cfg_path: Path) -> dict:
    cfg = _load_cfg(judgments_cfg_path)
    if not llm_available():
        logger.warning("无 LLM key，判断页跳过")
        return {"skipped": True}

    results = []
    with get_session() as session:
        poll_summary = _poll_summary(session)
        for q in cfg["questions"]:
            evidence = _evidence_pack(session, q["variables"], q.get("market_hint", ""))
            full_evidence = f"OPINION POLLS:\n{poll_summary}\n\nNEWS FACTS:\n{evidence}"
            item = _ask_judgment(q["question"], full_evidence) or {}
            price_ref = _market_price_ref(session, q.get("market_hint", ""))
            results.append({
                "id": q["id"],
                "question_cn": q["question_cn"],
                "question": q["question"],
                "judgment": item.get("judgment", "unclear"),
                "confidence": item.get("confidence", "low"),
                "reason": item.get("reason", ""),
                "counter": item.get("counter", ""),
                "change_if": item.get("change_if", ""),
                "market_price": price_ref,
            })

    WEB_DIR.mkdir(exist_ok=True)
    (WEB_DIR / "judgment.html").write_text(_render(cfg["election_id"], results), encoding="utf-8")

    # Markdown 存档
    md_dir = REPORTS_DIR / cfg["election_id"]
    md_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# 方向判断（非概率） — {datetime.now():%Y-%m-%d %H:%M}", ""]
    for r in results:
        md += [
            f"## {r['question_cn']}",
            f"- **判断：{r['judgment'].upper()}**（置信度 {r['confidence']}）",
            f"- 市场参考价：{r['market_price'] or '—'} 分",
            f"- 佐证：{r['reason']}",
            f"- 反方最强：{r['counter']}",
            f"- 翻转条件：{r['change_if']}",
            "",
        ]
    (md_dir / f"{datetime.now():%Y-%m-%d}_judgment.md").write_text("\n".join(md), encoding="utf-8")

    logger.info("判断页已生成: {} 题", len(results))
    return {"questions": len(results)}


def _render(election_id: str, results: list[dict]) -> str:
    colors = {"yes": ("#eaf3de", "#3b6d11", "是"), "no": ("#fcebeb", "#a32d2d", "否"),
              "unclear": ("#f1efe8", "#888780", "不确定")}
    cards = []
    for r in results:
        bg, fg, label = colors.get(r["judgment"], colors["unclear"])
        cards.append(f"""
    <section>
      <h2 style="display:flex;justify-content:space-between">
        <span>{_esc(r['question_cn'])}</span>
        <span style="background:{bg};color:{fg};border-radius:8px;padding:2px 14px;font-size:13px">
          {label} · 置信 {r['confidence']}</span>
      </h2>
      <p style="font-size:12px;color:#888780">{_esc(r['question'])}</p>
      <p style="font-size:13px"><strong>佐证：</strong>{_esc(r['reason'])}</p>
      <p style="font-size:13px"><strong>反方最强：</strong>{_esc(r['counter'])}</p>
      <p style="font-size:13px"><strong>翻转条件：</strong>{_esc(r['change_if'])}</p>
      <p class="q">市场参考价：{r['market_price'] or '—'} 分（对照用，非本页结论）</p>
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>方向判断 — yes/no（非概率）</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#f5f4f0; color:#2c2c2a; line-height:1.7; }}
  .wrap {{ max-width:860px; margin:0 auto; padding:32px 24px; }}
  h1 {{ font-size:17px; font-weight:500; }}
  .meta {{ font-size:12px; color:#888780; margin-bottom:18px; }}
  section {{ background:#fff; border-radius:12px; padding:20px 22px; border:0.5px solid #d3d1c7; margin-bottom:18px; }}
  h2 {{ font-size:14px; font-weight:500; margin-bottom:8px; }}
  p {{ font-size:13px; margin-bottom:8px; }}
  .q {{ font-size:12px; color:#888780; }}
  .shield {{ background:#faf3e6; border:0.5px solid #efc789; border-radius:12px; padding:14px 18px; margin-bottom:20px; font-size:12px; color:#633806; }}
  a {{ color:#185fa5; text-decoration:none; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>方向判断页 — Serbia 2026</h1>
  <div class="meta">{datetime.now():%Y-%m-%d %H:%M} · 基于账本证据的 LLM 方向判断 · <a href="index.html">← 信息通道</a> · <a href="/log">→ 决策日志</a></div>
  <div class="shield">
    <strong>本页是"方向判断"，不是概率，更不是投资建议。</strong>
    每个判断基于账本证据生成（标注佐证与反方），市场参考价并列仅供对照。
    使用方式：读判断 → 读反方 → 自己下结论 → 决策日志留痕。
  </div>
  {''.join(cards)}
</div>
</body>
</html>"""

"""briefing_generator.py — 五层简报生成器（W1 D5）

原则（ADR D6/D13 + 质量六道闸）：
- L0/L1 由账本现算（数据库 diff），禁止自由发挥
- L2/L3 叙事来自 config/serbia_2026_narrative.yaml（人工/LLM 维护，事实必须可回溯 L1）
- L4 价格通道独立成页（web/l4_price.html），信息通道零价格（web/index.html）
- Markdown 存档至 reports/<election_id>/

页面结构与 web/*.html v0 样品保持一致（人工校准版），管线每日重渲染。
"""

from __future__ import annotations

import html as html_mod
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import func, select

from polybot.storage.db import get_session
from polybot.storage.models import MarketORM, NewsItemORM, SnapshotORM

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"
REPORTS_DIR = ROOT / "reports"

_TIER_LABEL = {"A1": "T1", "A2": "T2", "A3": "T3", "A4": "T4"}
_CSS = """  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f4f0; color: #2c2c2a; line-height: 1.7; }
  .layout { display: flex; max-width: 1180px; margin: 0 auto; gap: 24px; padding: 24px; }
  aside { width: 230px; flex-shrink: 0; }
  aside .card { background: #fff; border-radius: 12px; padding: 18px; border: 0.5px solid #d3d1c7; }
  aside h3 { font-size: 13px; color: #5f5e5a; font-weight: 500; margin-bottom: 10px; }
  aside ul { list-style: none; }
  aside li { padding: 8px 10px; border-radius: 8px; font-size: 13px; margin-bottom: 2px; }
  aside li.active { background: #eef3fa; color: #185fa5; font-weight: 500; }
  aside .warn { margin-top: 16px; background: #faf3e6; border: 0.5px solid #efc789; border-radius: 10px; padding: 12px; font-size: 12px; color: #633806; }
  aside .warn a { color: #854f0b; font-weight: 500; text-decoration: none; display: inline-block; margin-top: 6px; }
  main { flex: 1; min-width: 0; }
  header.top { background: #fff; border-radius: 12px; padding: 20px 24px; border: 0.5px solid #d3d1c7; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
  h1 { font-size: 17px; font-weight: 500; }
  .meta { font-size: 12px; color: #888780; }
  section { background: #fff; border-radius: 12px; padding: 22px 24px; border: 0.5px solid #d3d1c7; margin-bottom: 18px; }
  h2 { font-size: 14px; font-weight: 500; margin-bottom: 14px; color: #2c2c2a; display: flex; align-items: center; gap: 8px; }
  h2 .tag { font-size: 11px; background: #eef3fa; color: #185fa5; border-radius: 6px; padding: 2px 8px; font-weight: 500; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: #5f5e5a; font-weight: 500; padding: 8px 10px; border-bottom: 1px solid #e5e3da; }
  td { padding: 8px 10px; border-bottom: 0.5px solid #ecebe3; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .up { color: #3b6d11; font-weight: 500; }
  .flat { color: #888780; }
  ol, ul { padding-left: 20px; font-size: 13px; }
  ol li, ul li { margin-bottom: 8px; }
  .src { display: inline-block; font-size: 11px; border-radius: 5px; padding: 1px 6px; margin-right: 4px; }
  .src.t1 { background: #eaf3de; color: #3b6d11; }
  .src.t2 { background: #e6f1fb; color: #185fa5; }
  .src.t3 { background: #eeedfe; color: #534ab7; }
  .src.t5 { background: #fcebeb; color: #a32d2d; }
  .note { font-size: 12px; color: #888780; background: #f7f6f1; border-radius: 8px; padding: 10px 12px; margin-top: 12px; }
  .q { font-size: 12px; color: #b4b2a9; }
  a { color: #185fa5; text-decoration: none; }
  .shield { background: #faf3e6; border: 0.5px solid #efc789; border-radius: 12px; padding: 18px 20px; margin-bottom: 22px; font-size: 13px; color: #633806; }
  .shield strong { font-weight: 500; }
"""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _esc(text: str) -> str:
    return html_mod.escape(text or "")


def _flash_banner(data: BriefingData) -> str:
    flashes = data.stats.get("flash") or []
    if not flashes:
        return ""
    items = "".join(f"<li>{_esc(x)}</li>" for x in flashes)
    return (
        '<div style="background:#faf3e6;border:0.5px solid #efc789;border-radius:12px;'
        'padding:16px 20px;margin-bottom:18px;font-size:13px;color:#633806">'
        '<strong>⚡ Flash 触发（变化检测命中，建议优先读）：</strong>'
        f'<ul style="margin:6px 0 0 20px">{items}</ul></div>'
    )


def _local_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
@dataclass
class BriefingData:
    election_id: str
    vote_date: str
    variables: list[dict] = field(default_factory=list)   # L0 行
    facts: list[dict] = field(default_factory=list)       # L1 行
    l2_impacts: list[dict] = field(default_factory=list)
    l3_watch: list[dict] = field(default_factory=list)
    l3_contra_students: list[str] = field(default_factory=list)
    l3_contra_sns: list[str] = field(default_factory=list)
    l3_break: list[str] = field(default_factory=list)
    markets: list[dict] = field(default_factory=list)     # L4 行
    stats: dict = field(default_factory=dict)


def gather_data(election_cfg_path: Path, narrative_cfg_path: Path,
                facts_window_hours: int = 72, facts_limit: int = 12) -> BriefingData:
    with election_cfg_path.open("r", encoding="utf-8") as f:
        ecfg = yaml.safe_load(f)
    with narrative_cfg_path.open("r", encoding="utf-8") as f:
        ncfg = yaml.safe_load(f)

    data = BriefingData(
        election_id=ecfg["election_id"],
        vote_date=ecfg["vote_date"],
        l2_impacts=ncfg.get("l2_impacts", []),
        l3_watch=ncfg.get("l3_watch", []),
        l3_contra_students=ncfg.get("l3_contra_students", []),
        l3_contra_sns=ncfg.get("l3_contra_sns", []),
        l3_break=ncfg.get("l3_break_triggers", []),
    )

    today = _local_today()
    cutoff = _now_utc() - timedelta(hours=facts_window_hours)

    with get_session() as session:
        # ---- L1: 最近窗口内的相关事实 ----
        rows = session.execute(
            select(NewsItemORM)
            .where(NewsItemORM.triage_relevant == 1)
            .where(NewsItemORM.created_at >= cutoff)
            .order_by(NewsItemORM.novelty.desc(), NewsItemORM.created_at.desc())
            .limit(facts_limit)
        ).scalars().all()

        # 中文标题自愈：展示层缺失 title_zh 的条目批量补译（一次 LLM 调用）
        missing_zh = [r for r in rows if not r.title_zh]
        if missing_zh:
            try:
                from polybot.collect.feed_collector import _translate_batch

                tr = _translate_batch([(r.title_en or r.title) for r in missing_zh])
                for r, t in zip(missing_zh, tr):
                    if t:
                        r.title_zh = t.get("zh") or r.title_zh
                        r.title_en = r.title_en or t.get("en")
                session.commit()
            except Exception as exc:
                logger.debug("中文标题补译失败（不影响出报）: {}", exc)

        for r in rows:
            title = r.title_zh or r.title_en or r.title
            var_ids = json.loads(r.variable_ids_json) if r.variable_ids_json else []
            tier = _TIER_LABEL.get(r.tier or "", r.tier)
            data.facts.append({
                "tier": tier,
                "title": title,
                "url": r.url,
                "source": r.source_name or "",
                "time": (r.published_at or r.created_at).strftime("%m-%d %H:%M"),
                "variables": var_ids,
                "new_fact": bool(r.is_new_fact),
            })

        # ---- L0: 变量仪表盘（今日有相关命中 → up，否则 flat/保持 config 状态）----
        counts = dict(session.execute(
            select(NewsItemORM.variable_ids_json, func.count(NewsItemORM.id))
            .where(NewsItemORM.triage_relevant == 1)
            .where(NewsItemORM.created_at >= cutoff)
            .group_by(NewsItemORM.variable_ids_json)
        ).all())
        hit_today: dict[str, int] = {}
        for var_json, cnt in counts.items():
            if not var_json:
                continue
            try:
                for vid in json.loads(var_json):
                    hit_today[vid] = hit_today.get(vid, 0) + cnt
            except json.JSONDecodeError:
                continue

        for var in ecfg["key_variables"]:
            n = hit_today.get(var["id"], 0)
            # 每个变量的最新证据（账本现算）：近 7 天内该变量下新颖度最高的一条
            latest = session.execute(
                select(NewsItemORM)
                .where(NewsItemORM.triage_relevant == 1)
                .where(NewsItemORM.variable_ids_json.like(f'%"{var["id"]}"%'))
                .where(NewsItemORM.created_at >= _now_utc() - timedelta(days=7))
                .order_by(NewsItemORM.novelty.desc(), NewsItemORM.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            latest_text = ""
            if latest is not None:
                lt = (latest.title_en or latest.title)[:70]
                lt_time = (latest.published_at or latest.created_at).strftime("%m-%d")
                latest_text = f"{lt}（{lt_time}）"

            data.variables.append({
                "id": var["id"],
                "label": var["label"],
                "state": var["state"],
                "latest": latest_text,
                "flag": "up" if n > 0 else "flat",
                "flag_text": f"↑ {n} 条相关" if n > 0 else "无更新",
            })

        # ---- L4: 各市场最新快照 + 24h 前对比 ----
        market_rows = session.execute(
            select(MarketORM).where(MarketORM.subcategory == data.election_id)
        ).scalars().all()

        for m in market_rows:
            latest = session.execute(
                select(SnapshotORM).where(SnapshotORM.market_id == m.id)
                .order_by(SnapshotORM.ts.desc()).limit(1)
            ).scalar_one_or_none()
            if latest is None:
                continue
            old = session.execute(
                select(SnapshotORM).where(SnapshotORM.market_id == m.id)
                .where(SnapshotORM.ts <= latest.ts - timedelta(hours=24))
                .order_by(SnapshotORM.ts.desc()).limit(1)
            ).scalar_one_or_none()

            change = None
            if old is not None and old.yes_price and latest.yes_price:
                change = (latest.yes_price - old.yes_price) * 100
            data.markets.append({
                "question": m.question,
                "price": latest.yes_price,
                "change": change,
                "volume": latest.volume_24h,
                "liquidity": latest.liquidity,
                "end": m.end_date.strftime("%Y-%m-%d") if m.end_date else "",
            })

        data.stats["facts_total"] = len(data.facts)

    # ---- Flash 触发器（ADR：变化靠算不靠人）----
    flashes: list[str] = []
    for m in data.markets:
        if m["change"] is not None and abs(m["change"]) >= 4.0:
            flashes.append(
                f"盘口异动：{m['question']} 24h 变动 {m['change']:+.1f} 分（现价 {m['price'] * 100:.1f}）"
            )
    for f in data.facts:
        if f["tier"] == "T1":
            flashes.append(f"T1 官方信源更新：{f['title']}")
    data.stats["flash"] = flashes[:5]

    data.stats["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return data


# ---------------------------------------------------------------------------
# HTML 渲染
# ---------------------------------------------------------------------------

def render_index(data: BriefingData, reports_history: list[str]) -> str:
    days_left = ""
    try:
        vote = datetime.strptime(data.vote_date, "%Y-%m-%d")
        days_left = f"距投票 {(vote - datetime.now()).days} 天"
    except ValueError:
        pass

    hist = "\n".join(
        f'<li class="active">{_esc(r)}</li>' if i == 0 else f'<li class="q">{_esc(r)}</li>'
        for i, r in enumerate(reports_history[:8])
    ) or '<li class="q">——</li>'

    var_rows = "\n".join(
        f'<tr><td>{i + 1}</td><td>{_esc(v["label"])}</td>'
        f'<td>{_esc(v["state"])}'
        + (f'<br><span class="q">最新：{_esc(v["latest"])}</span>' if v.get("latest") else '')
        + f'</td><td class="{v["flag"]}">{_esc(v["flag_text"])}</td></tr>'
        for i, v in enumerate(data.variables)
    )

    def _tier_cls(tier: str) -> str:
        return {"T1": "t1", "T2": "t2", "T3": "t3", "T4": "t3", "T5": "t5"}.get(tier, "t5")

    fact_items = "\n".join(
        f'<li><span class="src {_tier_cls(f["tier"])}">{_esc(f["tier"])}</span>'
        f'<a href="{_esc(f["url"])}" target="_blank" style="color:inherit">{_esc(f["title"])}</a>'
        f'<span class="q"> — {_esc(f["source"])} {_esc(f["time"])}</span></li>'
        for f in data.facts
    ) or '<li class="q">窗口内无相关新事实</li>'

    l2_html = "\n".join(
        f'<li><strong>{_esc(x["title"])}</strong>：{_esc(x["text"])}</li>'
        for x in data.l2_impacts
    )

    l3u = "\n".join(
        f'<li><strong>{_esc(x["q"])}</strong><br>'
        f'<span class="q">为什么要盯：{_esc(x["why"])}</span></li>'
        for x in data.l3_watch
    )
    l3a = "\n".join(f"<li>{_esc(x)}</li>" for x in data.l3_contra_students)
    l3b = "\n".join(f"<li>{_esc(x)}</li>" for x in data.l3_contra_sns)
    l3t = " / ".join(_esc(x) for x in data.l3_break)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polybot Decision Briefing — Serbia 2026</title>
<style>
{_CSS}</style>
</head>
<body>
<div class="layout">
  <aside>
    <div class="card">
      <h3>报告列表</h3>
      <ul>
{hist}
      </ul>
      <div class="warn">
        价格通道已按设计分离。<br>建议先读完本页全部信息，再自行决定是否打开。
        <a href="judgment.html">→ 方向判断页（yes/no + 佐证，非概率）</a>
        <a href="l4_price.html">→ L4 决策参考（市场盘口）</a>
        <a href="http://127.0.0.1:8787/" style="margin-top:8px">→ 控制面板（手动采集 / 定时开关，需启动本地服务）</a>
      </div>
    </div>
  </aside>
  <main>
    {_flash_banner(data)}
    <header class="top">
      <div>
        <h1>Serbia 2026 议会选举 — Decision Briefing</h1>
        <div class="meta">{_esc(data.stats.get("generated_at", ""))} · 日报（自动生成） · 信息通道</div>
      </div>
      <div class="meta">{_esc(days_left)}</div>
    </header>

    <section>
      <h2>L0 变量仪表盘 <span class="tag">{len(data.variables)} 个关键变量</span></h2>
      <table>
        <tr><th style="width:28px">#</th><th style="width:180px">变量</th><th>当前状态</th><th style="width:120px">变化</th></tr>
{var_rows}
      </table>
    </section>

    <section>
      <h2>L1 新增事实 <span class="tag">近 72h · 现算自账本</span></h2>
      <ol>
{fact_items}
      </ol>
    </section>

    <section>
      <h2>L2 影响分析 <span class="tag">这些变化意味着什么</span></h2>
      <ul>
{l2_html}
      </ul>
    </section>

    <section>
      <h2>L3 下注前的思维体检 <span class="tag">不是作业，是对照卡</span></h2>
      <div class="note" style="margin:0 0 14px">
        <strong>这一层怎么用：</strong>它不需要你去搜集任何材料——线索会由后续每天的简报自动补充。你只需要做两件事：<br>
        ① 下面"系统在盯的事"告诉你哪些关键问题<b>还没有答案</b>——下注前先确认自己接受这种"不知道"；<br>
        ② "自检卡"是反向质检：<b>想买谁，就先读对方的反驳</b>。任何一条你说服不了自己，就先缓一缓，把疑问写进决策日志。
      </div>
      <p style="font-size:13px;font-weight:500;margin-bottom:6px">系统在盯的事（还没定，别当已有答案）：</p>
      <ul>
{l3u}
      </ul>
      <p style="font-size:13px;font-weight:500;margin:12px 0 6px">自检卡 A —— 想买学生名单（反对派）？先过这三关：</p>
      <ol>
{l3a}
      </ol>
      <p style="font-size:13px;font-weight:500;margin:12px 0 6px">自检卡 B —— 想买 SNS（执政方）？先过这两关：</p>
      <ol>
{l3b}
      </ol>
      <p style="font-size:13px;font-weight:500;margin:12px 0 6px">出现这些新闻，之前所有判断推倒重来：</p>
      <p style="font-size:13px">{l3t}</p>
    </section>

    <div class="note">信息通道到此为止（零市场数据）。价格对照在独立页：<a href="l4_price.html">L4 决策参考</a> · 本页由管线每日重新生成</div>
  </main>
</div>
</body>
</html>"""


def render_l4(data: BriefingData) -> str:
    # 主力合约：按流动性取头部 15 个；其余计入族规模提示
    top = sorted(data.markets, key=lambda m: (m["liquidity"] or 0), reverse=True)[:15]
    rest = len(data.markets) - len(top)
    rows = "\n".join(
        f'<tr><td>{_esc(m["question"])}</td>'
        f'<td>{m["price"] * 100:.1f} 分</td>'
        f'<td>{f"{m["change"]:+.1f} 分" if m["change"] is not None else "—"}</td>'
        f'<td>{m["volume"] or 0:,.0f}</td>'
        f'<td>{m["liquidity"] or 0:,.0f}</td>'
        f'<td>{_esc(m["end"])}</td></tr>'
        for m in top
    ) or '<tr><td colspan="6" class="q">暂无快照——先跑价格采样</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>L4 决策参考 — 价格通道</title>
<style>
{_CSS}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 24px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="shield">
    <strong>你正在进入价格通道。</strong> 按设计约定：若尚未在信息通道完成先验判断并写下决策日志第一段，请先回去完成——看价前写的判断，才是衡量锚定效应的样本。
  </div>
  <header class="top">
    <h1>L4 决策参考 — 塞尔维亚选举相关合约盘口</h1>
    <div class="meta">{_esc(data.stats.get("generated_at", ""))} · <a href="index.html">← 返回信息通道</a></div>
  </header>

  <section>
    <h2>活跃合约族（Yes 价 / 24h 变化 / 24h 成交 / 流动性 / 结算）</h2>
    <table>
      <tr><th>合约</th><th>现价</th><th>24h 变动</th><th>24h 成交</th><th>流动性</th><th>结算</th></tr>
{rows}
    </table>
    <p class="note" style="margin-top:12px">合约族全量 {len(data.markets)} 个市场（含全部候选人/政党级别子市场），上表按流动性取前 15 个主力。整体薄盘，仓位测算需预留滑点摩擦成本。决策日志（两段式）在生成器 v2 接入表单。</p>
  </section>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Markdown 存档
# ---------------------------------------------------------------------------

def render_markdown(data: BriefingData) -> str:
    lines = [
        f"# Serbia 2026 Daily Briefing — {_local_today()}",
        "",
        f"> 生成时间：{data.stats.get('generated_at')} | 信息通道（L0-L3）+ L4 见 web/l4_price.html",
        "",
        "## L0 变量仪表盘",
        "",
        "| # | 变量 | 状态 | 变化 |",
        "|---|---|---|---|",
    ]
    for i, v in enumerate(data.variables):
        lines.append(f"| {i + 1} | {v['label']} | {v['state']} | {v['flag_text']} |")
    lines += ["", "## L1 新增事实（近 72h）", ""]
    for f in data.facts:
        lines.append(f"- **[{f['tier']}]** [{f['title']}]({f['url']}) — {f['source']} {f['time']}")
    lines += ["", "## L2 影响分析", ""]
    for x in data.l2_impacts:
        lines.append(f"- **{x['title']}**：{x['text']}")
    lines += ["", "## L3 下注前的思维体检", "", "**系统在盯的事**", ""]
    lines += [f"- **{x['q']}** —— {x['why']}" for x in data.l3_watch]
    lines += ["", "**自检卡 A（想买学生名单先过这三关）**", ""]
    lines += [f"- {x}" for x in data.l3_contra_students]
    lines += ["", "**自检卡 B（想买 SNS 先过这两关）**", ""]
    lines += [f"- {x}" for x in data.l3_contra_sns]
    lines += ["", f"**推翻格局触发**：{' / '.join(data.l3_break)}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def generate(election_cfg_path: Path, narrative_cfg_path: Path) -> dict:
    data = gather_data(election_cfg_path, narrative_cfg_path)

    WEB_DIR.mkdir(exist_ok=True)
    report_md_dir = REPORTS_DIR / data.election_id
    report_md_dir.mkdir(parents=True, exist_ok=True)

    # 报告历史：扫描 reports 目录下的 md
    history = sorted(
        (p.stem for p in report_md_dir.glob("*.md")), reverse=True
    ) or ["（首期）"]

    (WEB_DIR / "index.html").write_text(
        render_index(data, history), encoding="utf-8"
    )
    (WEB_DIR / "l4_price.html").write_text(render_l4(data), encoding="utf-8")
    md_path = report_md_dir / f"{_local_today()}_daily.md"
    md_path.write_text(render_markdown(data), encoding="utf-8")

    logger.info(
        "简报已生成: facts={} markets={} -> {}",
        len(data.facts), len(data.markets), md_path,
    )
    return {"facts": len(data.facts), "markets": len(data.markets), "md": str(md_path)}

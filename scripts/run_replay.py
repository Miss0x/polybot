"""run_replay.py — 盲测回放（训练轮）：罗马尼亚 2025-05-18 总统决选

机制：
  1. 解析 Wikipedia 决选正面对垒民调表 → 民调账本
  2. 拉取 Polymarket 历史日线（gamma market 519068 → CLOB prices-history）
  3. 对每个 checkpoint 截面：只用 ≤ cutoff 的证据（民调/价格/上下文事实）
     → LLM 方向判断（yes/no/unclear + 佐证 + 反方 + 翻转条件）
  4. 生成 web/replay_romania_2025/：盲测走查页（按时间排序）+ 揭晓页

用法：python scripts/run_replay.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polybot.llm_client import chat, chat_json, llm_available  # noqa: E402

CONFIG = ROOT / "config" / "romania_2025_replay.yaml"
OUT_DIR = ROOT / "web" / "replay_romania_2025"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"


def load_cfg() -> dict:
    with CONFIG.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def fetch_polls(wiki_url: str) -> list[dict]:
    """解析决选正面对垒表：Poll | Date | Sample | Dan | Simion | ..."""
    resp = httpx.get(wiki_url, headers={"User-Agent": UA}, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    polls = []
    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        h = [x.lower() for x in headers]
        if not ("dan" in h and "simion" in h and "date" in h):
            continue
        i_date = h.index("date")
        i_sample = h.index("sample") if "sample" in h else None
        i_dan = h.index("dan")
        i_simion = h.index("simion")
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(i_date, i_dan, i_simion):
                continue
            pollster = cells[0]
            date = _parse_date(cells[i_date])
            if not date or not pollster or pollster.lower().startswith("poll"):
                continue
            dan = _pct(cells[i_dan])
            simion = _pct(cells[i_simion])
            if dan is None or simion is None:
                continue
            sample = None
            if i_sample is not None:
                m = re.match(r"([\d,]+)", cells[i_sample])
                if m:
                    sample = int(m.group(1).replace(",", ""))
            polls.append({
                "pollster": pollster, "date": date, "sample": sample,
                "dan": dan, "simion": simion,
            })
    # 去重（同机构同日期保留最后）
    dedup = {(p["pollster"], p["date"]): p for p in polls}
    return sorted(dedup.values(), key=lambda p: p["date"])


def _parse_date(text: str) -> datetime | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-zăâîșț]+)", text)
    months = {m.lower(): i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], 1)}
    if not m:
        return None
    mon = months.get(m.group(2).lower())
    if not mon:
        return None
    return datetime(2025, mon, int(m.group(1)))


def _pct(text: str) -> float | None:
    m = re.match(r"(\d+(?:\.\d+)?)", text.strip().replace(",", "."))
    return float(m.group(1)) if m else None


def fetch_prices(market_id: str) -> list[dict]:
    m = httpx.get(f"https://gamma-api.polymarket.com/markets/{market_id}", timeout=30.0).json()
    toks = m.get("clobTokenIds")
    token = json.loads(toks)[0] if isinstance(toks, str) else toks[0]
    r = httpx.get("https://clob.polymarket.com/prices-history",
                  params={"market": token, "interval": "max", "fidelity": 1440}, timeout=30.0)
    h = r.json().get("history", [])
    return sorted(
        [{"date": datetime.utcfromtimestamp(p["t"]).strftime("%Y-%m-%d"), "price": p["p"]} for p in h],
        key=lambda x: x["date"],
    )


# ---------------------------------------------------------------------------
# 截面判断
# ---------------------------------------------------------------------------

def _judgment_at(question: str, polls: list[dict], prices: list[dict],
                 context: list[str], cutoff: str) -> dict:
    p = [x for x in polls if x["date"].strftime("%Y-%m-%d") <= cutoff]
    pr = [x for x in prices if x["date"] <= cutoff]
    ctx = [c for c in context if c["as_of"] <= cutoff]

    p_s = "\n".join(
        f"- {x['pollster']} ({x['date']:%m-%d}, n={x['sample'] or '?'}): Dan {x['dan']:.1f}% vs Simion {x['simion']:.1f}%"
        for x in p[-8:]
    ) or "(no runoff polls yet)"
    pr_s = pr[-6:] if pr else []
    pr_s = ", ".join(f"{x['date']}={x['price']:.2f}" for x in pr_s) or "(no prices yet)"
    c_s = "\n".join(f"- ({x['as_of']}) {x['text']}" for x in ctx) or "(none)"

    result = chat_json(
        "You are a careful election analyst doing a point-in-time assessment. "
        "Using ONLY the information below (as known on the cutoff date), answer the closed "
        "question with a DIRECTION judgment — not a probability.\n"
        'Respond ONLY as JSON: {"judgment":"yes|no|unclear","confidence":"low|medium|high",'
        '"reason":"2-4 sentences IN SIMPLIFIED CHINESE citing specific polls/prices/facts with dates",'
        '"counter":"strongest counter-argument IN SIMPLIFIED CHINESE",'
        '"change_if":"what would flip this judgment IN SIMPLIFIED CHINESE"}. '
        "Rules: judgment/confidence in English; no invented numbers; evidence thin → "
        '"unclear"+low confidence. Distinguish pollster reliability issues if relevant. '
        "Remember polls have historically struggled with diaspora and turnout effects in Romania.",
        f"CONTEXT FACTS:\n{c_s}\n\nRUNOFF POLLS (Dan vs Simion):\n{p_s}\n\n"
        f"POLYMARKET 'Dan wins' price history (most recent last):\n{pr_s}\n\n"
        f"CUTOFF DATE: {cutoff}\nQUESTION: {question}",
        max_tokens=1000,
    )
    # 中转站偶发超时/过滤 → 重试至多 2 次
    attempts = 0
    while not result and attempts < 2:
        attempts += 1
        import time

        time.sleep(4 * attempts)
        logger.warning("截面 {} 判断失败，重试 {}/2", cutoff, attempts)
        result = chat_json(
            "You are a careful election analyst doing a point-in-time assessment. "
            "Using ONLY the information below (as known on the cutoff date), answer the closed "
            "question with a DIRECTION judgment — not a probability.\n"
            'Respond ONLY as JSON: {"judgment":"yes|no|unclear","confidence":"low|medium|high",'
            '"reason":"2-4 sentences IN SIMPLIFIED CHINESE citing specific polls/prices/facts with dates",'
            '"counter":"strongest counter-argument IN SIMPLIFIED CHINESE",'
            '"change_if":"what would flip this judgment IN SIMPLIFIED CHINESE"}. '
            "Rules: judgment/confidence in English; no invented numbers; evidence thin → "
            '"unclear"+low confidence.',
            f"CONTEXT FACTS:\n{c_s}\n\nRUNOFF POLLS (Dan vs Simion):\n{p_s}\n\n"
            f"POLYMARKET 'Dan wins' price history (most recent last):\n{pr_s}\n\n"
            f"CUTOFF DATE: {cutoff}\nQUESTION: {question}",
            max_tokens=1000,
        )
    return result or {}


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

_CSS = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#f5f4f0; color:#2c2c2a; line-height:1.7; }
  .wrap { max-width:860px; margin:0 auto; padding:32px 24px; }
  h1 { font-size:17px; font-weight:500; } h2 { font-size:14px; font-weight:500; margin-bottom:10px; }
  .meta { font-size:12px; color:#888780; margin-bottom:18px; }
  .card { background:#fff; border-radius:12px; padding:20px 22px; border:0.5px solid #d3d1c7; margin-bottom:18px; }
  .badge { display:inline-block; border-radius:8px; padding:2px 14px; font-size:13px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:#5f5e5a; font-weight:500; padding:8px 10px; border-bottom:1px solid #e5e3da; }
  td { padding:8px 10px; border-bottom:0.5px solid #ecebe3; }
  p { font-size:13px; margin-bottom:8px; }
  .shield { background:#faf3e6; border:0.5px solid #efc789; border-radius:12px; padding:14px 18px; margin-bottom:20px; font-size:12px; color:#633806; }
  a { color:#185fa5; text-decoration:none; }
  .q { font-size:12px; color:#888780; }
"""


def _checkpoint_page(cfg: dict, cp: str, judge: dict, polls: list[dict], prices: list[dict]) -> str:
    bg, fg, label = {
        "yes": ("#eaf3de", "#3b6d11", "是"), "no": ("#fcebeb", "#a32d2d", "否"),
        "unclear": ("#f1efe8", "#888780", "不确定")}.get(judge.get("judgment", "unclear"),
                                                         ("#f1efe8", "#888780", "不确定"))
    polls_since = [x for x in polls if x["date"].strftime("%Y-%m-%d") <= cp][-6:]
    prices_since = [x for x in prices if x["date"] <= cp][-10:]
    poll_rows = "\n".join(
        f"<tr><td>{x['pollster']}</td><td>{x['date']:%m-%d}</td><td>{x['dan']:.1f}%</td>"
        f"<td>{x['simion']:.1f}%</td><td>{x['sample'] or '—'}</td></tr>" for x in polls_since)
    price_rows = " | ".join(f"{x['date'][5:]}: {x['price']:.2f}" for x in prices_since)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>回放截面 {cp}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>回放截面 — {cp}（T-{(datetime(2025, 5, 18) - datetime.strptime(cp, "%Y-%m-%d")).days} 天）</h1>
<div class="meta">罗马尼亚 2025-05-18 总统决选 · 本页只含 {cp} 及之前的信息</div>
<section>
  <h2>方向判断 <span class="badge" style="background:{bg};color:{fg}">{label} · 置信 {judge.get('confidence', '-')}</span></h2>
  <p><strong>佐证：</strong>{judge.get('reason', '本轮判断被过滤或失败')}</p>
  <p><strong>反方最强：</strong>{judge.get('counter', '')}</p>
  <p><strong>翻转条件：</strong>{judge.get('change_if', '')}</p>
  <p class="q">决策提示：把你的下注决定写进决策日志（买/不买/仓位），再翻下一页。</p>
</section>
<section>
  <h2>决选民调（截点前）</h2>
  <table><tr><th>机构</th><th>日期</th><th>Dan</th><th>Simion</th><th>样本</th></tr>
  {poll_rows}</table>
</section>
<section>
  <h2>Polymarket 'Dan 胜选' 价格走势（截点前 10 日）</h2>
  <p style="font-size:13px">{price_rows}</p>
</section>
<div class="q">Romania 2025 replay · 仅用于训练轮盲测</div>
</div></body></html>"""


def _index_page(cfg: dict, checkpoints: list[str]) -> str:
    items = "\n".join(
        f'<li style="margin-bottom:10px"><a href="checkpoint_{cp}.html">截面 {cp}'
        f'（T-{(datetime(2025, 5, 18) - datetime.strptime(cp, "%Y-%m-%d")).days} 天）</a></li>'
        for cp in checkpoints)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>盲测回放 — Romania 2025</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>盲测回放（训练轮）— 罗马尼亚 2025-05-18 总统决选</h1>
<div class="meta">规则：按时间顺序逐页阅读 → 每页把你的下注决策写进决策日志（/log）→ 全部走完再开揭晓页</div>
<div class="shield"><strong>盲测纪律：</strong>不要跳页。你已知历史结局（Dan 翻盘获胜），挑战在于：假装不知道，
只按页面上的信息判断——如果你在每个截面都会跟 Simion 民调走，那 10/25 塞尔维亚你也可能犯同样的错。</div>
<div class="card"><h2>检查点</h2><ol>{items}</ol></div>
<div class="card"><a href="reveal.html"><strong>→ 结算揭晓页（走完全部截面后才能打开）</strong></a></div>
</div></body></html>"""


def _reveal_page(cfg: dict, checkpoints: list[dict]) -> str:
    rows = "\n".join(
        f"<tr><td>{c['cp']}</td><td>{c['judgment'].get('judgment', '—').upper()}</td>"
        f"<td>{c['judgment'].get('confidence', '—')}</td>"
        f"<td>{c['price_at_cutoff']:.2f}</td></tr>"
        for c in checkpoints)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>回放揭晓</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>揭晓 — 罗马尼亚 2025-05-18 决选真值</h1>
<div class="meta">真值：Nicușor Dan 以 53.6% vs 46.4% 击败 George Simion（爆冷翻盘）</div>
<section>
  <h2>各截面系统判断 vs 真值</h2>
  <table><tr><th>截面</th><th>系统判断</th><th>置信</th><th>当时市场价(Dan)</th></tr>
  {rows}</table>
</section>
<section>
  <h2>复盘要点</h2>
  <p>① 真实民调多数显示 Simion 领先——如果判断页跟民调走就会错；判断的反方证据（侨民票、背书潮）是救命的。</p>
  <p>② 市场 5/6 一度把 Dan 压到 0.265，最后 0.48 结算——市场也犯过错，但修正比民调快。</p>
  <p>③ 把你的决策日志与结果对照：你是在哪个截面被"民调共识"带偏的？</p>
</section>
<a href="index.html">← 返回回放目录</a>
</div></body></html>"""


# ---------------------------------------------------------------------------
def main() -> None:
    if not llm_available():
        print("错误：无 LLM key")
        sys.exit(1)
    cfg = load_cfg()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("拉取民调表…")
    polls = fetch_polls(cfg["wiki_polls_url"])
    logger.info("民调 {} 条", len(polls))

    logger.info("拉取历史价格…")
    prices = fetch_prices(cfg["market"]["gamma_market_id"])
    logger.info("价格 {} 点", len(prices))

    snapshot_pages = []
    done = []
    for cp in cfg["checkpoints"]:
        logger.info("截面 {} 判断中…", cp)
        judge = _judgment_at(cfg["questions"][0]["question"], polls, prices,
                             cfg["context_facts"], cp)
        price_at = next((x["price"] for x in prices if x["date"] <= cp), None)
        (OUT_DIR / f"checkpoint_{cp}.html").write_text(
            _checkpoint_page(cfg, cp, judge, polls, prices), encoding="utf-8")
        snapshot_pages.append(f"checkpoint_{cp}.html")
        done.append({"cp": cp, "judgment": judge, "price_at_cutoff": price_at})

    (OUT_DIR / "index.html").write_text(_index_page(cfg, cfg["checkpoints"]), encoding="utf-8")
    (OUT_DIR / "reveal.html").write_text(_reveal_page(cfg, done), encoding="utf-8")
    logger.info("回放已生成: web/replay_romania_2025/index.html ✅")


if __name__ == "__main__":
    main()

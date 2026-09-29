"""webapp/server.py — Polybot 本地控制面板（用户 2026-09-30 指示）

功能：
  GET  /            控制面板页：手动采集按钮 / 定时任务开关 / 状态一览
  GET  /index.html  信息通道简报（web/ 静态）
  GET  /l4_price.html 价格通道
  POST /api/run              后台线程跑管线（collect+triage+markets+report）
  GET  /api/status           管线运行状态 + 账本统计 + 定时任务状态
  POST /api/schedule/toggle  一键开/关 4 个计划任务（schtasks /Change）
  POST /api/schedule/register 管理员权限尝试注册计划任务（失败则提示用 bat）

启动：python -m polybot.webapp.server   → http://127.0.0.1:8787
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"
PYTHON = Path(sys.executable)
PIPELINE = ROOT / "scripts" / "run_serbia_pipeline.py"

TASK_NAMES = ["Polybot_Serbia_0600", "Polybot_Serbia_1200", "Polybot_Serbia_1800", "Polybot_Serbia_2355"]

app = FastAPI(title="Polybot Control Panel")
# 允许从 file:// 直接打开的简报页（web/index.html）跨域调用本服务的 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_run_lock = threading.Lock()
_run_state: dict = {"running": False, "last_started": None, "last_finished": None, "last_log": ""}


# ---------------------------------------------------------------------------
# 管线执行（后台线程，避免网页请求超时）
# ---------------------------------------------------------------------------

def _run_pipeline() -> None:
    if not _run_lock.acquire(blocking=False):
        return
    try:
        _run_state["running"] = True
        _run_state["last_started"] = datetime.now().strftime("%H:%M:%S")
        proc = subprocess.run(
            [str(PYTHON), str(PIPELINE)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900,
        )
        tail = (proc.stdout or "").strip().splitlines()[-6:]
        _run_state["last_log"] = "\n".join(tail) if proc.returncode == 0 else (proc.stderr or "unknown error")[-1500:]
        _run_state["last_ok"] = proc.returncode == 0
    except Exception as exc:
        _run_state["last_ok"] = False
        _run_state["last_log"] = f"{type(exc).__name__}: {exc}"
    finally:
        _run_state["running"] = False
        _run_state["last_finished"] = datetime.now().strftime("%H:%M:%S")
        _run_lock.release()


# ---------------------------------------------------------------------------
# 定时任务控制（schtasks）
# ---------------------------------------------------------------------------

def _task_status() -> list[dict]:
    out = []
    for name in TASK_NAMES:
        try:
            proc = subprocess.run(
                ["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/NH"],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                out.append({"name": name, "registered": False, "enabled": False})
                continue
            lines = [l for l in (proc.stdout or "").splitlines() if l.strip()]
            status_line = lines[-1] if lines else ""
            enabled = "已启用" in status_line or "Ready" in status_line or "正在运行" in status_line
            out.append({"name": name, "registered": True, "enabled": enabled, "raw": status_line.strip()})
        except Exception:
            out.append({"name": name, "registered": False, "enabled": False})
    return out


def _toggle_tasks(enable: bool) -> dict:
    flag = "/ENABLE" if enable else "/DISABLE"
    results = {}
    for name in TASK_NAMES:
        proc = subprocess.run(
            ["schtasks", "/Change", "/TN", name, flag],
            capture_output=True, text=True, timeout=15,
        )
        results[name] = proc.returncode == 0
    return results


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

_CONTROL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polybot 控制面板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f4f0; color: #2c2c2a; line-height: 1.7; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 32px 24px; }
  h1 { font-size: 18px; font-weight: 500; margin-bottom: 4px; }
  .meta { font-size: 12px; color: #888780; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .card { background: #fff; border-radius: 12px; padding: 20px 22px; border: 0.5px solid #d3d1c7; }
  .card h2 { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
  button { border: none; border-radius: 10px; padding: 12px 18px; font-size: 14px; cursor: pointer; font-family: inherit; width: 100%; margin-bottom: 10px; }
  .btn-run { background: #185fa5; color: #fff; }
  .btn-run:disabled { background: #b4b2a9; cursor: wait; }
  .btn-on { background: #eaf3de; color: #3b6d11; border: 0.5px solid #97c459; }
  .btn-off { background: #fcebeb; color: #a32d2d; border: 0.5px solid #f09595; }
  .links a { display: block; padding: 10px 12px; border-radius: 8px; background: #eef3fa; color: #185fa5; text-decoration: none; font-size: 13px; margin-bottom: 8px; }
  .status { font-size: 13px; white-space: pre-wrap; background: #f7f6f1; border-radius: 8px; padding: 12px; min-height: 60px; margin-top: 8px; }
  .pill { display: inline-block; font-size: 12px; border-radius: 6px; padding: 2px 10px; margin: 2px 4px 2px 0; }
  .pill.on { background: #eaf3de; color: #3b6d11; }
  .pill.off { background: #fcebeb; color: #a32d2d; }
  .pill.na { background: #f1efe8; color: #888780; }
  .note { font-size: 12px; color: #888780; margin-top: 14px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Polybot 控制面板 — Serbia 2026</h1>
  <div class="meta">本页面即本地服务（127.0.0.1:8787）。关掉服务，控制功能失效，但简报页仍可直接双击打开。</div>
  <div class="grid">
    <div class="card">
      <h2>采集控制</h2>
      <button id="runBtn" class="btn-run" onclick="runPipeline()">▶ 立即采集一轮（约 4 分钟）</button>
      <div id="runStatus" class="status">状态加载中…</div>
    </div>
    <div class="card">
      <h2>定时任务（每日 06/12/18/24 点）</h2>
      <div id="schedPills" style="margin-bottom:10px"></div>
      <button class="btn-on" onclick="toggleSchedule(true)">☑ 全部开启</button>
      <button class="btn-off" onclick="toggleSchedule(false)">✕ 全部关闭</button>
      <div id="schedStatus" class="status"></div>
    </div>
    <div class="card links" style="grid-column: 1 / -1">
      <h2>简报直达</h2>
      <a href="/index.html">📄 信息通道（L0-L3 · 每日简报）</a>
      <a href="/l4_price.html">💰 价格通道（L4 · 市场盘口，自选时机打开）</a>
    </div>
  </div>
  <div class="note">提示：定时任务第一次使用需以管理员身份运行一次 scripts/register_serbia_schedule.bat 完成注册；之后即可在本页开关。</div>
</div>
<script>
async function refresh() {
  const s = await (await fetch('/api/status')).json();
  const r = s.run;
  document.getElementById('runBtn').disabled = r.running;
  document.getElementById('runBtn').textContent = r.running ? '⏳ 采集中…' : '▶ 立即采集一轮（约 4 分钟）';
  document.getElementById('runStatus').textContent =
    '运行中: ' + (r.running ? '是' : '否') + '\\n最近启动: ' + (r.last_started || '—')
    + '\\n最近完成: ' + (r.last_finished || '—')
    + '\\n结果: ' + (r.last_ok === undefined ? '—' : (r.last_ok ? '成功' : '失败（见服务端日志）'))
    + '\\n' + (r.last_log || '');
  const pills = s.schedule.map(t => {
    if (!t.registered) return `<span class="pill na">${t.name.slice(-4)} 未注册</span>`;
    return `<span class="pill ${t.enabled ? 'on' : 'off'}">${t.name.slice(-4)} ${t.enabled ? '开启' : '已停'}</span>`;
  }).join('');
  document.getElementById('schedPills').innerHTML = pills;
  document.getElementById('schedStatus').textContent = s.schedule_note || '';
}
async function runPipeline() {
  await fetch('/api/run', {method: 'POST'});
  refresh();
}
async function toggleSchedule(enable) {
  const r = await (await fetch('/api/schedule/toggle', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enable})
  })).json();
  document.getElementById('schedStatus').textContent = r.message;
  refresh();
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def control() -> str:
    return _CONTROL_HTML


@app.get("/index.html")
def index_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/l4_price.html")
def l4_page() -> FileResponse:
    return FileResponse(WEB_DIR / "l4_price.html")


# ---------------------------------------------------------------------------
# 决策日志（两段式，ADR D13）
# ---------------------------------------------------------------------------

_LOG_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>决策日志 — 两段式</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#f5f4f0; color:#2c2c2a; line-height:1.7; }
  .wrap { max-width:760px; margin:0 auto; padding:32px 24px; }
  h1 { font-size:17px; font-weight:500; margin-bottom:6px; }
  .meta { font-size:12px; color:#888780; margin-bottom:20px; }
  .card { background:#fff; border-radius:12px; padding:20px 22px; border:0.5px solid #d3d1c7; margin-bottom:18px; }
  h2 { font-size:14px; font-weight:500; margin-bottom:10px; }
  label { display:block; font-size:12px; color:#5f5e5a; margin:10px 0 4px; }
  input, select, textarea { width:100%; padding:9px 12px; border:0.5px solid #d3d1c7; border-radius:8px; font-size:13px; font-family:inherit; }
  textarea { min-height:64px; resize:vertical; }
  button { border:none; border-radius:10px; padding:11px 20px; font-size:14px; cursor:pointer; background:#185fa5; color:#fff; width:100%; margin-top:14px; }
  .ok { background:#eaf3de; color:#3b6d11; border-radius:8px; padding:10px 12px; font-size:13px; margin-top:12px; display:none; }
  .hint { font-size:12px; color:#888780; background:#f7f6f1; border-radius:8px; padding:10px 12px; margin-bottom:6px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>决策日志</h1>
  <div class="meta">两段式（D13）：先在信息通道读完简报 → 填第一段 → 打开价格通道 → 填第二段。两段差异 = 锚定效应的测量样本。</div>
  <div class="card">
    <h2>第一段 · 看价前</h2>
    <div class="hint">此刻你还没看盘口。凭 L0-L3 的信息写。</div>
    <label>合约方向</label>
    <select id="pre_dir">
      <option value="sns">看 SNS / 执政方</option>
      <option value="students">看学生名单 / 反对派</option>
      <option value="other">其他/说不清</option>
    </select>
    <label>意向价位（低于多少分你愿意买，0.01-0.99；没有就留空）</label>
    <input id="pre_price" placeholder="如 0.45">
    <label>依据（简要：哪些事实/变量支撑你）</label>
    <textarea id="pre_evidence"></textarea>
    <label>我可能错在哪（强制：写一条反方观点）</label>
    <textarea id="pre_risk"></textarea>
    <button onclick="submitLog('pre')">保存第一段</button>
    <div id="ok1" class="ok">已保存。现在可以去打开价格通道了。</div>
  </div>
  <div class="card">
    <h2>第二段 · 看价后</h2>
    <label>最终决策</label>
    <textarea id="post_decision" placeholder="如：以 0.52 买入 SNS 合约 $X；或不动作，挂 0.45 等待"></textarea>
    <label>相对第一段的改动与理由（没改就写"一致"）</label>
    <textarea id="post_change"></textarea>
    <button onclick="submitLog('post')">保存第二段</button>
    <div id="ok2" class="ok">已保存。结算后复盘会对比两段。</div>
  </div>
</div>
<script>
async function submitLog(stage) {
  const body = {
    stage: stage,
    direction: document.getElementById('pre_dir').value,
    intent_price: parseFloat(document.getElementById('pre_price').value) || null,
    decision: stage === 'pre'
      ? ('方向:' + document.getElementById('pre_dir').value + ' | 依据:' + document.getElementById('pre_evidence').value + ' | 可能错在:' + document.getElementById('pre_risk').value)
      : document.getElementById('post_decision').value,
    notes: stage === 'pre' ? '' : document.getElementById('post_change').value,
  };
  const r = await (await fetch('/api/judgment', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)})).json();
  document.getElementById(stage === 'pre' ? 'ok1' : 'ok2').style.display = 'block';
}
</script>
</body>
</html>"""


@app.get("/log", response_class=HTMLResponse)
def log_page() -> str:
    return _LOG_HTML


@app.post("/api/judgment")
def api_judgment(payload: dict) -> JSONResponse:
    from polybot.storage.db import get_session
    from polybot.storage.models import JudgmentLogORM
    from polybot.storage.db import init_db

    init_db()
    with get_session() as session:
        session.add(JudgmentLogORM(
            election_id="serbia_2026",
            market_id=payload.get("market_id"),
            stage=payload.get("stage", "pre")[:8],
            direction=payload.get("direction"),
            intent_price=payload.get("intent_price"),
            decision=payload.get("decision"),
            notes=payload.get("notes"),
        ))
        session.commit()
    return JSONResponse({"ok": True})


@app.post("/api/run")
def api_run() -> JSONResponse:
    if _run_state["running"]:
        return JSONResponse({"ok": False, "message": "已有任务在跑"})
    threading.Thread(target=_run_pipeline, daemon=True).start()
    return JSONResponse({"ok": True, "message": "管线已启动，约 4 分钟"})


@app.get("/api/status")
def api_status() -> JSONResponse:
    schedule = _task_status()
    registered = [t for t in schedule if t["registered"]]
    if not registered:
        note = "计划任务尚未注册：请以管理员身份运行一次 scripts/register_serbia_schedule.bat"
    elif all(t.get("enabled") for t in registered):
        note = "定时采集运行中"
    else:
        note = "定时采集处于关闭状态（部分或全部已停用）"
    return JSONResponse({
        "run": {k: _run_state.get(k) for k in ("running", "last_started", "last_finished", "last_log", "last_ok")},
        "schedule": schedule,
        "schedule_note": note,
    })


@app.post("/api/schedule/toggle")
def api_toggle(payload: dict) -> JSONResponse:
    enable = bool(payload.get("enable", True))
    results = _toggle_tasks(enable)
    ok = all(results.values())
    return JSONResponse({
        "ok": ok,
        "message": ("已全部" + ("开启" if enable else "停用")) if ok
        else f"部分失败（需要管理员权限？）：{results}",
        "results": results,
    })


def main() -> None:
    import uvicorn

    # 服务就绪后自动打开浏览器（延迟 1.5s 等端口起来，避免首次加载失败）
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8787/")).start()
    print("Polybot 控制面板: http://127.0.0.1:8787  （Ctrl+C 停止）")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()

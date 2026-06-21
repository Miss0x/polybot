"""
telegram_mock.py — Week 4 Phase 5

Telegram Mock Sender。

职责：
1. 接收 AlertDraft；
2. 根据 should_alert 判断是否进入发送候选；
3. 输出模拟发送结果到终端；
4. 保存本地发送日志（JSONL）；
5. 为后续真实 Telegram sender 保留接口。

当前不接真实 Telegram API。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polybot.analysis.alert_draft_builder import SEVERITY_INFO, SEVERITY_WARNING, AlertDraft


# ---------------------------------------------------------------------------
# Send result
# ---------------------------------------------------------------------------

@dataclass
class MockSendResult:
    """模拟发送结果。"""

    market_id: str
    sent: bool
    reason: str
    telegram_text: str
    timestamp: str
    severity: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "sent": self.sent,
            "reason": self.reason,
            "telegram_text": self.telegram_text,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Mock Sender
# ---------------------------------------------------------------------------

class TelegramMockSender:
    """
    Telegram 告警模拟发送器。

    使用方式：
        sender = TelegramMockSender(log_path="logs/telegram_mock.jsonl")
        for draft in alert_drafts:
            result = sender.send(draft)
            print(result.sent, result.reason)
    """

    def __init__(self, log_path: str | None = "logs/telegram_mock.jsonl"):
        """
        log_path: JSONL 日志保存路径，None 则不保存。
        """
        self.log_path = Path(log_path) if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, draft: AlertDraft) -> MockSendResult:
        """
        模拟发送一条 AlertDraft。

        逻辑：
        - should_alert=False → 跳过，记录 reason
        - should_alert=True  → 格式化 Telegram 文本，模拟发送，记录日志
        """
        now = datetime.now(timezone.utc).isoformat()

        if not draft.should_alert:
            result = MockSendResult(
                market_id=draft.market_id,
                sent=False,
                reason="should_alert=False — below alert threshold",
                telegram_text="",
                timestamp=now,
                severity=draft.severity,
                metadata=draft.metadata,
            )
            self._write_log(result)
            return result

        # 格式化 Telegram 文本
        telegram_text = self._format_telegram_text(draft)

        result = MockSendResult(
            market_id=draft.market_id,
            sent=True,
            reason="Mock sent successfully (no real API call)",
            telegram_text=telegram_text,
            timestamp=now,
            severity=draft.severity,
            metadata=draft.metadata,
        )
        self._write_log(result)
        return result

    def send_batch(self, drafts: list[AlertDraft]) -> list[MockSendResult]:
        """批量模拟发送。"""
        return [self.send(d) for d in drafts]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_telegram_text(self, draft: AlertDraft) -> str:
        """将 AlertDraft 格式化为适合 Telegram 的文本。"""
        lines: list[str] = []

        # Header emoji
        emoji = "🚨" if draft.severity == SEVERITY_WARNING else "👁" if draft.severity == "watch" else "ℹ️"
        lines.append(f"{emoji} <b>{self._escape_html(draft.title)}</b>")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")

        # Market
        lines.append(f"📊 <b>Market:</b> {self._escape_html(draft.metadata.get('probability_view', 'N/A').upper())}")
        lines.append("")

        # Price
        price = draft.metadata.get("current_yes_price")
        price_str = f"{price * 100:.0f}%" if price is not None else "N/A"
        lines.append(f"💰 <b>Current YES:</b> {price_str}")
        lines.append("")

        # Confidence
        lines.append(f"🎯 <b>Confidence:</b> {draft.metadata.get('confidence', 'N/A').capitalize()}")
        lines.append("")

        # Body (already formatted)
        # We include a condensed version of the body
        lines.append(self._condense_body(draft.body))
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("<i>Polybot Market Watch — Mock Mode</i>")

        return "\n".join(lines)

    def _condense_body(self, body: str) -> str:
        """将完整 body 压缩为 Telegram 友好格式。"""
        # Simple extraction: keep first few meaningful lines
        lines = body.splitlines()
        condensed: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip headers that are redundant with our telegram format
            if stripped.startswith("Market:") or stripped.startswith("Current YES:"):
                continue
            if stripped.startswith("Confidence:"):
                continue
            if stripped.startswith("View:"):
                # Keep view line
                condensed.append(f"📈 {self._escape_html(stripped)}")
                continue
            if stripped.startswith("Reason:"):
                # Truncate reasoning
                reason = stripped[7:].strip()
                condensed.append(f"📝 {self._escape_html(reason[:200])}")
                continue
            if stripped.startswith("Key News:"):
                condensed.append("")
                condensed.append("<b>Key News:</b>")
                continue
            if stripped.startswith("Risk Notes:"):
                condensed.append("")
                condensed.append("<b>Risk Notes:</b>")
                continue
            if stripped.startswith(("•", "-", "▲", "▼", "○")):
                condensed.append(self._escape_html(stripped))
                continue
            # Skip other lines
        return "\n".join(condensed)

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符（Telegram 使用 HTML parse_mode）。"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _write_log(self, result: MockSendResult) -> None:
        """将结果追加写入 JSONL 日志。"""
        if self.log_path is None:
            return
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

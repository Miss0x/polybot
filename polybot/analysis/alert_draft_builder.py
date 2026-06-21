"""
alert_draft_builder.py — Week 4 Phase 2

把 ProbabilityDraft 转换成用户可读的告警草稿 AlertDraft。

第一版只做 watch 信息，不做强交易信号。
should_alert 采用保守策略：
- confidence == high 且 probability_view 为 higher/lower → True
- confidence == medium 且存在强 key_news → True
- 其他情况 → False（仍生成草稿，但不告警）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from polybot.analysis.probability_judger import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    ProbabilityDraft,
    PROBABILITY_VIEW_HIGHER,
    PROBABILITY_VIEW_LOWER,
    PROBABILITY_VIEW_UNCHANGED,
    PROBABILITY_VIEW_UNCERTAIN,
)


# ---------------------------------------------------------------------------
# Severity enums
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WATCH = "watch"
SEVERITY_WARNING = "warning"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AlertDraft:
    """告警草稿。"""

    market_id: str
    title: str
    body: str
    severity: str  # info / watch / warning
    should_alert: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "should_alert": self.should_alert,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class AlertDraftBuilder:
    """
    基于 ProbabilityDraft 生成 AlertDraft。

    保守策略：
    1. confidence == high 且 view in {higher, lower} → should_alert = True, severity = warning
    2. confidence == medium 且存在强 key_news → should_alert = True, severity = watch
    3. 其他 → should_alert = False, severity = info
    4. low confidence 不自动告警，只进入实验输出
    """

    def build(self, draft: ProbabilityDraft) -> AlertDraft:
        """生成 AlertDraft。"""
        should_alert = self._should_alert(draft)
        severity = self._decide_severity(draft, should_alert)
        title = self._build_title(draft, severity)
        body = self._build_body(draft)

        metadata = {
            "probability_view": draft.probability_view,
            "confidence": draft.confidence,
            "current_yes_price": draft.current_yes_price,
            "key_news_count": len(draft.key_news),
            "risk_notes_count": len(draft.risk_notes),
        }

        return AlertDraft(
            market_id=draft.market_id,
            title=title,
            body=body,
            severity=severity,
            should_alert=should_alert,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_alert(self, draft: ProbabilityDraft) -> bool:
        """
        判断是否应触发告警（P1 保守化）。

        规则：
        1. 无当前价格 → 不告警（无法判断偏离）
        2. high confidence + 明确方向 + 至少 2 条 key_news → 告警
        3. medium confidence + 至少 2 条 key_news → 告警（watch 级别）
        4. 其他 → 不告警
        """
        # 无当前价格 → 不告警
        if draft.current_yes_price is None:
            return False

        view = draft.probability_view
        conf = draft.confidence
        key_count = len(draft.key_news)

        # high confidence + 明确方向 + 有足够关键新闻
        if conf == CONFIDENCE_HIGH and view in (PROBABILITY_VIEW_HIGHER, PROBABILITY_VIEW_LOWER):
            return key_count >= 2

        # medium confidence + 有足够关键新闻
        if conf == CONFIDENCE_MEDIUM and view in (PROBABILITY_VIEW_HIGHER, PROBABILITY_VIEW_LOWER):
            return key_count >= 2

        return False

    def _decide_severity(self, draft: ProbabilityDraft, should_alert: bool) -> str:
        """决定严重程度。"""
        if not should_alert:
            return SEVERITY_INFO

        if draft.confidence == CONFIDENCE_HIGH:
            return SEVERITY_WARNING

        if draft.confidence == CONFIDENCE_MEDIUM:
            return SEVERITY_WATCH

        return SEVERITY_INFO

    def _build_title(self, draft: ProbabilityDraft, severity: str) -> str:
        """生成标题。"""
        prefix = "[Polybot Market Watch]"
        view_label = {
            PROBABILITY_VIEW_HIGHER: "YES Probability May Rise",
            PROBABILITY_VIEW_LOWER: "YES Probability May Fall",
            PROBABILITY_VIEW_UNCHANGED: "No Clear Change",
            PROBABILITY_VIEW_UNCERTAIN: "Uncertain Signal",
        }.get(draft.probability_view, "Market Update")

        if severity == SEVERITY_WARNING:
            return f"{prefix} ⚠ {view_label} — {draft.question[:60]}"
        if severity == SEVERITY_WATCH:
            return f"{prefix} 👁 {view_label} — {draft.question[:60]}"
        return f"{prefix} {view_label} — {draft.question[:60]}"

    def _build_body(self, draft: ProbabilityDraft) -> str:
        """生成正文。"""
        lines: list[str] = []

        lines.append(f"Market: {draft.question}")
        lines.append("")

        # 当前价格
        price_str = f"{draft.current_yes_price * 100:.0f}%" if draft.current_yes_price is not None else "N/A"
        lines.append(f"Current YES: {price_str}")
        lines.append("")

        # 判断
        view_display = {
            PROBABILITY_VIEW_HIGHER: "YES probability may rise",
            PROBABILITY_VIEW_LOWER: "YES probability may fall",
            PROBABILITY_VIEW_UNCHANGED: "No clear probability change yet",
            PROBABILITY_VIEW_UNCERTAIN: "Signal is mixed / uncertain",
        }.get(draft.probability_view, "Unknown")
        lines.append(f"View: {view_display}")
        lines.append("")

        # 信心
        lines.append(f"Confidence: {draft.confidence.capitalize()}")
        lines.append("")

        # 理由
        lines.append(f"Reason: {draft.reasoning}")
        lines.append("")

        # 关键新闻
        lines.append("Key News:")
        if draft.key_news:
            for i, news in enumerate(draft.key_news, 1):
                arrow = "▲" if news["direction"] == 1 else "▼" if news["direction"] == -1 else "○"
                lines.append(f"  {i}. {arrow} [{news['relevance']:.2f}] {news['title'][:80]}")
                if news.get("reasoning"):
                    lines.append(f"     → {news['reasoning'][:100]}")
        else:
            lines.append("  None strong enough for direct alert.")
        lines.append("")

        # 风险提示
        if draft.risk_notes:
            lines.append("Risk Notes:")
            for note in draft.risk_notes:
                lines.append(f"  - {note}")
        else:
            lines.append("Risk Notes: None")

        return "\n".join(lines)

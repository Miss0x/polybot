"""
scripts/run_match_evaluation.py

Phase 5: evaluate ontology-based news-market matching against a fixed gold sample.

Usage:
    python scripts/run_match_evaluation.py \
        --gold tests/gold_samples/iran_conflict_gold.yaml \
        --output-md reports/phase5_match_evaluation_baseline.md \
        --output-json reports/phase5_match_evaluation_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.processing.news_event_extractor import NewsEventExtractor
from polybot.processing.ontology_match_engine import OntologyMatchDecision, OntologyMatchEngine


@dataclass
class CaseEvaluation:
    id: str
    market_condition: str
    expected_matched: bool
    actual_matched: bool
    expected_event_type: str | None
    actual_event_type: str | None
    expected_evidence_type: str | None
    actual_evidence_type: str | None
    expected_direction: int
    actual_direction: int
    extracted_event_types: list[str]
    passed: bool
    errors: list[str]
    reasoning: str | None


@dataclass
class EvaluationSummary:
    total_cases: int
    passed_cases: int
    failed_cases: int
    event_type_accuracy: float
    evidence_type_accuracy: float
    direction_accuracy: float
    matched_accuracy: float
    false_positive_count: int
    false_negative_count: int


def _load_gold(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"Invalid gold sample format: {path}")
    return data


def _fake_market(case: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"gold-market-{case['id']}",
        question=case["market_question"],
        description=None,
        resolution_source=None,
    )


def _fake_news_event(news_id: int, draft: Any) -> SimpleNamespace:
    return SimpleNamespace(
        news_id=news_id,
        event_type=draft.event_type,
        actors_json=json.dumps(draft.actors, ensure_ascii=False),
    )



def _choose_decision(
    decisions: list[OntologyMatchDecision],
    expected_event_type: str | None,
) -> OntologyMatchDecision | None:
    matched = [d for d in decisions if d.matched]
    if not matched:
        return None
    if expected_event_type:
        for decision in matched:
            if decision.event_type == expected_event_type:
                return decision
    return sorted(matched, key=lambda d: (d.relevance, d.strength), reverse=True)[0]


def _evaluate_case(
    idx: int,
    case: dict[str, Any],
    extractor: NewsEventExtractor,
    matcher: OntologyMatchEngine,
) -> CaseEvaluation:
    expected = case.get("expected", {})
    expected_matched = bool(expected.get("matched"))
    expected_event_type = expected.get("event_type")
    expected_evidence_type = expected.get("evidence_type")
    expected_direction = int(expected.get("direction", 0))

    drafts = extractor.extract(
        news_id=idx,
        title=case["news_title"],
        raw_text=case.get("news_text"),
        top_k=5,
    )
    extracted_event_types = [draft.event_type for draft in drafts]

    market = _fake_market(case)
    decisions: list[OntologyMatchDecision] = []
    for draft in drafts:
        if draft.event_type == "unclassified":
            continue
        decisions.append(matcher.match(_fake_news_event(idx, draft), market))


    chosen = _choose_decision(decisions, expected_event_type)
    actual_matched = chosen is not None and chosen.matched
    actual_event_type = chosen.event_type if chosen else None
    actual_evidence_type = chosen.evidence_type if chosen else None
    actual_direction = chosen.direction if chosen else 0
    reasoning = chosen.reasoning if chosen else None

    errors: list[str] = []
    if actual_matched != expected_matched:
        errors.append(f"matched expected={expected_matched} actual={actual_matched}")

    if expected_matched:
        if actual_event_type != expected_event_type:
            errors.append(f"event_type expected={expected_event_type} actual={actual_event_type}")
        if actual_evidence_type != expected_evidence_type:
            errors.append(f"evidence_type expected={expected_evidence_type} actual={actual_evidence_type}")
        if actual_direction != expected_direction:
            errors.append(f"direction expected={expected_direction} actual={actual_direction}")
    else:
        if actual_matched:
            errors.append(
                f"false positive event_type={actual_event_type} evidence_type={actual_evidence_type} direction={actual_direction}"
            )

    return CaseEvaluation(
        id=case["id"],
        market_condition=case["market_condition"],
        expected_matched=expected_matched,
        actual_matched=actual_matched,
        expected_event_type=expected_event_type,
        actual_event_type=actual_event_type,
        expected_evidence_type=expected_evidence_type,
        actual_evidence_type=actual_evidence_type,
        expected_direction=expected_direction,
        actual_direction=actual_direction,
        extracted_event_types=extracted_event_types,
        passed=not errors,
        errors=errors,
        reasoning=reasoning,
    )


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _summarize(results: list[CaseEvaluation]) -> EvaluationSummary:
    total = len(results)
    expected_matched = [r for r in results if r.expected_matched]
    event_den = len(expected_matched)
    evidence_den = len(expected_matched)
    direction_den = len(expected_matched)

    return EvaluationSummary(
        total_cases=total,
        passed_cases=sum(1 for r in results if r.passed),
        failed_cases=sum(1 for r in results if not r.passed),
        event_type_accuracy=_ratio(sum(1 for r in expected_matched if r.actual_event_type == r.expected_event_type), event_den),
        evidence_type_accuracy=_ratio(
            sum(1 for r in expected_matched if r.actual_evidence_type == r.expected_evidence_type), evidence_den
        ),
        direction_accuracy=_ratio(sum(1 for r in expected_matched if r.actual_direction == r.expected_direction), direction_den),
        matched_accuracy=_ratio(sum(1 for r in results if r.actual_matched == r.expected_matched), total),
        false_positive_count=sum(1 for r in results if not r.expected_matched and r.actual_matched),
        false_negative_count=sum(1 for r in results if r.expected_matched and not r.actual_matched),
    )


def _write_json(path: Path, gold_meta: dict[str, Any], summary: EvaluationSummary, results: list[CaseEvaluation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "gold": {"board_id": gold_meta.get("board_id"), "version": gold_meta.get("version")},
        "summary": asdict(summary),
        "cases": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(path: Path, gold_meta: dict[str, Any], summary: EvaluationSummary, results: list[CaseEvaluation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 5 Match Evaluation Baseline",
        "",
        f"- Board: `{gold_meta.get('board_id')}`",
        f"- Gold version: `{gold_meta.get('version')}`",
        f"- Total cases: **{summary.total_cases}**",
        f"- Passed: **{summary.passed_cases}**",
        f"- Failed: **{summary.failed_cases}**",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Matched accuracy | {summary.matched_accuracy:.2%} |",
        f"| Event type accuracy | {summary.event_type_accuracy:.2%} |",
        f"| Evidence type accuracy | {summary.evidence_type_accuracy:.2%} |",
        f"| Direction accuracy | {summary.direction_accuracy:.2%} |",
        f"| False positives | {summary.false_positive_count} |",
        f"| False negatives | {summary.false_negative_count} |",
        "",
        "## Cases",
        "",
        "| Case | Pass | Expected | Actual | Extracted events | Errors |",
        "|---|---:|---|---|---|---|",
    ]

    for result in results:
        expected = (
            f"matched={result.expected_matched}; event={result.expected_event_type}; "
            f"evidence={result.expected_evidence_type}; dir={result.expected_direction}"
        )
        actual = (
            f"matched={result.actual_matched}; event={result.actual_event_type}; "
            f"evidence={result.actual_evidence_type}; dir={result.actual_direction}"
        )
        errors = "<br>".join(result.errors) if result.errors else "-"
        extracted = ", ".join(result.extracted_event_types) if result.extracted_event_types else "-"
        lines.append(
            f"| `{result.id}` | {'YES' if result.passed else 'NO'} | {expected} | {actual} | {extracted} | {errors} |"
        )

    lines.extend([
        "",
        "## Failed Case Details",
        "",
    ])
    failed = [r for r in results if not r.passed]
    if not failed:
        lines.append("No failed cases.")
    else:
        for result in failed:
            lines.extend([
                f"### {result.id}",
                "",
                f"- Market condition: `{result.market_condition}`",
                f"- Extracted events: `{', '.join(result.extracted_event_types)}`",
                f"- Errors: {'; '.join(result.errors)}",
                f"- Reasoning: {result.reasoning or '-'}",
                "",
            ])

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ontology news-market matching against gold samples.")
    parser.add_argument("--gold", default="tests/gold_samples/iran_conflict_gold.yaml", help="Gold sample YAML path")
    parser.add_argument("--output-md", default="reports/phase5_match_evaluation_baseline.md", help="Markdown report path")
    parser.add_argument("--output-json", default="reports/phase5_match_evaluation_baseline.json", help="JSON report path")
    parser.add_argument("--min-relevance", type=float, default=0.30, help="Matcher min relevance threshold")
    args = parser.parse_args()

    gold_path = (ROOT / args.gold).resolve() if not Path(args.gold).is_absolute() else Path(args.gold)
    output_md = (ROOT / args.output_md).resolve() if not Path(args.output_md).is_absolute() else Path(args.output_md)
    output_json = (ROOT / args.output_json).resolve() if not Path(args.output_json).is_absolute() else Path(args.output_json)

    gold = _load_gold(gold_path)
    extractor = NewsEventExtractor()
    matcher = OntologyMatchEngine(min_relevance=args.min_relevance)

    results = [
        _evaluate_case(idx=i + 1, case=case, extractor=extractor, matcher=matcher)
        for i, case in enumerate(gold["cases"])
    ]
    summary = _summarize(results)

    _write_markdown(output_md, gold, summary, results)
    _write_json(output_json, gold, summary, results)

    print("=" * 72)
    print("Phase 5 Match Evaluation Baseline")
    print("=" * 72)
    print(f"Gold:              {gold_path}")
    print(f"Total cases:       {summary.total_cases}")
    print(f"Passed / Failed:   {summary.passed_cases} / {summary.failed_cases}")
    print(f"Matched accuracy:  {summary.matched_accuracy:.2%}")
    print(f"Event accuracy:    {summary.event_type_accuracy:.2%}")
    print(f"Evidence accuracy: {summary.evidence_type_accuracy:.2%}")
    print(f"Direction accuracy:{summary.direction_accuracy:.2%}")
    print(f"False positives:   {summary.false_positive_count}")
    print(f"False negatives:   {summary.false_negative_count}")
    print(f"Markdown report:   {output_md}")
    print(f"JSON report:       {output_json}")
    if summary.failed_cases:
        print("\nFailed cases:")
        for result in results:
            if not result.passed:
                print(f"  - {result.id}: {'; '.join(result.errors)}")
    print("=" * 72)


if __name__ == "__main__":
    main()

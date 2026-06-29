from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TZ = dt.timezone(dt.timedelta(hours=8))


def _date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except Exception:
        return None


def _current_week_range(today: dt.date | None = None) -> tuple[dt.date, dt.date, str]:
    today = today or dt.datetime.now(TZ).date()
    start = today - dt.timedelta(days=today.weekday())
    end = start + dt.timedelta(days=6)
    year, week, _ = today.isocalendar()
    return start, end, f"{year}-W{week:02d}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "N/A"
    return f"{numerator / denominator:.0%}"


def _in_range(row: dict[str, Any], start: dt.date, end: dt.date) -> bool:
    row_date = _date(str(row.get("date") or row.get("created_at") or ""))
    return bool(row_date and start <= row_date <= end)


def _count_knowledge_items(weekly_log: Path, week: str, section: str) -> int:
    if not weekly_log.exists():
        return 0
    text = weekly_log.read_text(encoding="utf-8")
    marker = f"## {week}"
    start_idx = text.find(marker)
    if start_idx < 0:
        return 0
    tail = text[start_idx + len(marker) :]
    next_week_idx = tail.find("\n## ")
    block = tail[:next_week_idx] if next_week_idx >= 0 else tail
    section_marker = f"### {section}"
    section_idx = block.find(section_marker)
    if section_idx < 0:
        return 0
    section_tail = block[section_idx + len(section_marker) :]
    next_section_idx = section_tail.find("\n### ")
    section_block = section_tail[:next_section_idx] if next_section_idx >= 0 else section_tail
    return sum(1 for line in section_block.splitlines() if line.strip().startswith("- "))


def _top(counter: collections.Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": key, "count": value} for key, value in counter.most_common(limit)]


def _top_stage_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals = {
        "selection_tokens": sum(_safe_int(row.get("selection_tokens")) for row in rows),
        "writing_tokens": sum(_safe_int(row.get("writing_tokens")) for row in rows),
        "rewrite_tokens": sum(_safe_int(row.get("rewrite_tokens")) for row in rows),
        "policy_rerank_tokens": sum(_safe_int(row.get("policy_rerank_tokens")) for row in rows),
        "lite_cta_tokens": sum(_safe_int(row.get("lite_cta_tokens")) for row in rows),
    }
    ranked = sorted(
        ({"name": key, "count": value} for key, value in totals.items() if value > 0),
        key=lambda item: item["count"],
        reverse=True,
    )
    return ranked


def _count_regression_cases(regression_root: Path, start: dt.date, end: dt.date) -> dict[str, int]:
    if not regression_root.exists():
        return {"total": 0, "new_this_week": 0}
    case_files = list(regression_root.glob("*/input.json")) + list(regression_root.glob("*/*/input.json"))
    new_this_week = 0
    for path in case_files:
        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=TZ).date()
        if start <= modified <= end:
            new_this_week += 1
    return {"total": len(case_files), "new_this_week": new_this_week}


def _read_regression_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _promoted_value(row: dict[str, Any]) -> str:
    promoted = str(row.get("promoted_to") or "").strip()
    if promoted:
        return promoted
    status = str(row.get("status") or "").strip()
    if status == "converted_to_rule":
        return "rule"
    if status in {"covered_by_checker", "converted_to_script", "needs_checker"}:
        return "checker"
    if status == "converted_to_example":
        return "example"
    return "archived"


def build_weekly_review(
    *,
    metrics_path: Path,
    knowledge_dir: Path,
    start: dt.date,
    end: dt.date,
    week: str,
) -> dict[str, Any]:
    rows = [row for row in _read_jsonl(metrics_path) if _in_range(row, start, end)]
    nightly = [row for row in rows if row.get("mode") == "nightly_candidate"]
    morning = [row for row in rows if row.get("mode") == "morning_send"]

    p0_total = sum(_safe_int(row.get("p0_count")) for row in rows)
    p1_total = 0
    p2_total = 0
    module_non_ok: collections.Counter[str] = collections.Counter()
    module_fail: collections.Counter[str] = collections.Counter()
    module_review: collections.Counter[str] = collections.Counter()
    module_score_sum: collections.Counter[str] = collections.Counter()
    module_score_count: collections.Counter[str] = collections.Counter()

    for row in rows:
        counts = row.get("issue_counts") if isinstance(row.get("issue_counts"), dict) else {}
        p1_total += _safe_int(counts.get("medium"))
        p2_total += _safe_int(counts.get("low"))
        statuses = row.get("module_statuses") if isinstance(row.get("module_statuses"), dict) else {}
        for module, status in statuses.items():
            status = str(status or "")
            if status and status != "ok":
                module_non_ok[module] += 1
            if status == "fail":
                module_fail[module] += 1
            if status == "review":
                module_review[module] += 1
        scores = row.get("module_scores") if isinstance(row.get("module_scores"), dict) else {}
        for module, score in scores.items():
            try:
                module_score_sum[module] += float(score)
                module_score_count[module] += 1
            except Exception:
                pass

    rewrite_attempts = [row for row in nightly if row.get("rewrite_modules")]
    rewrite_success = [row for row in rewrite_attempts if row.get("quality_gate") == "ok"]
    p0_repair_attempts = [row for row in nightly if row.get("p0_repair_attempted")]
    p0_repair_success = [row for row in p0_repair_attempts if row.get("p0_repair_success")]

    admin_sent = [row for row in nightly if row.get("admin_report_sent")]
    admin_skipped = [row for row in nightly if row.get("admin_report_skip_reason")]
    morning_sent = [row for row in morning if row.get("send_status") == "sent"]
    morning_ok = [row for row in morning if row.get("status") == "ok"]
    morning_blocked = [row for row in morning if row.get("send_status") == "blocked" or row.get("status") == "blocked"]
    morning_skipped = [row for row in morning if row.get("send_status") == "skipped"]

    quality_issues = _read_jsonl(knowledge_dir / "quality_issues.jsonl")
    converted_issues = [row for row in quality_issues if str(row.get("status") or "") in {"converted_to_rule", "converted_to_script", "converted_to_example"}]
    issue_type_counts: collections.Counter[str] = collections.Counter(str(row.get("issue_type") or "unknown") for row in quality_issues)
    module_issue_counts: collections.Counter[str] = collections.Counter(str(row.get("module") or "unknown") for row in quality_issues)
    reflection_rows = [
        row
        for row in quality_issues
        if int(row.get("reflection_schema_version") or 0) == 1 and _in_range(row, start, end)
    ]
    repeated_reflections: collections.Counter[str] = collections.Counter(
        str(row.get("issue_type") or "unknown")
        for row in reflection_rows
        if _safe_int(row.get("recurrence_count")) > 1
    )
    promoted_reflections: collections.Counter[str] = collections.Counter(_promoted_value(row) for row in reflection_rows)
    regression_counts = _count_regression_cases(knowledge_dir / "regression_cases", start, end)
    regression_report = _read_regression_report(metrics_path.parent / "latest_regression_cases.json")

    good_added = _count_knowledge_items(knowledge_dir / "weekly_log.md", week, "Good Examples")
    bad_added = _count_knowledge_items(knowledge_dir / "weekly_log.md", week, "Bad Examples")
    patterns_added = _count_knowledge_items(knowledge_dir / "weekly_log.md", week, "Patterns Updated")
    token_rows = [row for row in nightly if _safe_int(row.get("estimated_total_tokens")) > 0]
    total_tokens = sum(_safe_int(row.get("estimated_total_tokens")) for row in token_rows)
    total_calls = sum(_safe_int(row.get("llm_call_count")) for row in token_rows)
    total_fallbacks = sum(_safe_int(row.get("fallback_count")) for row in token_rows)
    stage_totals = _top_stage_totals(token_rows)
    selection_share = (
        sum(_safe_int(row.get("selection_tokens")) for row in token_rows) / total_tokens
        if total_tokens > 0
        else 0
    )
    multi_candidate_cost_note = (
        "selection cost is noticeable this week; review whether multi-candidate gains justify the added tokens."
        if selection_share >= 0.18
        else "selection cost remains controlled; lightweight multi-candidate did not dominate total token usage."
    )

    avg_scores = {
        module: round(module_score_sum[module] / module_score_count[module], 1)
        for module in module_score_sum
        if module_score_count[module]
    }

    next_week: list[str] = []
    if module_non_ok:
        top_module = module_non_ok.most_common(1)[0][0]
        next_week.append(f"优先降低 `{top_module}` 的 review/fail 次数，补充针对性样例或规则。")
    if rewrite_attempts and len(rewrite_success) < len(rewrite_attempts):
        next_week.append("复盘一次重写失败样本，把失败原因转成更精确的模块重写 Prompt。")
    if p0_repair_attempts and len(p0_repair_success) < len(p0_repair_attempts):
        next_week.append("复盘 P0 二次修复失败样本，判断是否需要拆分修复模块或提高阻断前留档质量。")
    if morning_blocked:
        next_week.append("检查早晨阻断原因，确认候选件保存、日期口径、OSS 读取和门禁状态是否稳定。")
    if bad_added < 2 or good_added < 1:
        next_week.append("补齐知识库每周最低沉淀：至少 2 个反例和 1 个正例。")
    if not next_week:
        next_week.append("建立固定回归样例集，把本周高频问题加入自动验证。")

    return {
        "schema_version": 1,
        "week": week,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "metrics_path": str(metrics_path),
        "run_counts": {"total": len(rows), "nightly_candidate": len(nightly), "morning_send": len(morning)},
        "p_counts": {
            "p0": p0_total,
            "p1_from_medium_issues": p1_total,
            "p2_from_low_issues": p2_total,
            "note": "P0 uses quality_gate.p0_count; P1/P2 use current metrics issue_counts.medium/low approximation.",
        },
        "module_distribution": {
            "non_ok": _top(module_non_ok),
            "fail": _top(module_fail),
            "review": _top(module_review),
            "average_scores": avg_scores,
        },
        "rewrite": {
            "attempts": len(rewrite_attempts),
            "success": len(rewrite_success),
            "success_rate": _pct(len(rewrite_success), len(rewrite_attempts)),
        },
        "p0_repair": {
            "attempts": len(p0_repair_attempts),
            "success": len(p0_repair_success),
            "success_rate": _pct(len(p0_repair_success), len(p0_repair_attempts)),
        },
        "admin_report": {
            "nightly_runs": len(nightly),
            "sent": len(admin_sent),
            "skipped": len(admin_skipped),
            "send_rate": _pct(len(admin_sent), len(nightly)),
        },
        "morning_send": {
            "runs": len(morning),
            "ok": len(morning_ok),
            "sent": len(morning_sent),
            "blocked": len(morning_blocked),
            "skipped": len(morning_skipped),
            "send_rate": _pct(len(morning_sent), len(morning)),
            "ok_rate": _pct(len(morning_ok), len(morning)),
        },
        "knowledge_conversion": {
            "quality_issues_total": len(quality_issues),
            "converted_total": len(converted_issues),
            "top_issue_types": _top(issue_type_counts),
            "top_modules": _top(module_issue_counts),
            "weekly_good_examples": good_added,
            "weekly_bad_examples": bad_added,
            "weekly_patterns_updated": patterns_added,
        },
        "quality_reflections": {
            "new_reflections_total": len(reflection_rows),
            "repeated_issue_types": _top(repeated_reflections),
            "promoted_counts": _top(promoted_reflections),
        },
        "token_review": {
            "nightly_rows_with_tokens": len(token_rows),
            "estimated_total_tokens": total_tokens,
            "average_tokens_per_email": round(total_tokens / len(token_rows), 1) if token_rows else 0,
            "llm_call_count": total_calls,
            "fallback_count": total_fallbacks,
            "stage_totals": stage_totals,
            "most_expensive_stage": stage_totals[0]["name"] if stage_totals else "",
            "multi_candidate_cost_note": multi_candidate_cost_note,
        },
        "regression_cases": {
            "total_cases": regression_counts["total"],
            "new_cases_this_week": regression_counts["new_this_week"],
            "latest_run_passed": _safe_int(regression_report.get("passed")),
            "latest_run_failed": _safe_int(regression_report.get("failed")),
            "latest_run_case_count": _safe_int(regression_report.get("case_count")),
            "latest_run_pass_rate": _pct(
                _safe_int(regression_report.get("passed")),
                _safe_int(regression_report.get("case_count")),
            ),
        },
        "next_week_harness_upgrade": next_week,
    }


def render_markdown(report: dict[str, Any]) -> str:
    p_counts = report["p_counts"]
    lines = [
        f"# Weekly Harness Quality Review {report['week']}",
        "",
        f"Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        "",
        "## Run Counts",
        "",
        f"- Total records: {report['run_counts']['total']}",
        f"- Nightly candidates: {report['run_counts']['nightly_candidate']}",
        f"- Morning sends: {report['run_counts']['morning_send']}",
        "",
        "## P0/P1/P2 Summary",
        "",
        f"- P0: {p_counts['p0']}",
        f"- P1: {p_counts['p1_from_medium_issues']}",
        f"- P2: {p_counts['p2_from_low_issues']}",
        f"- Note: {p_counts['note']}",
        "",
        "## Module Distribution",
        "",
        "- Non-ok modules: " + json.dumps(report["module_distribution"]["non_ok"], ensure_ascii=False),
        "- Fail modules: " + json.dumps(report["module_distribution"]["fail"], ensure_ascii=False),
        "- Review modules: " + json.dumps(report["module_distribution"]["review"], ensure_ascii=False),
        "- Average scores: " + json.dumps(report["module_distribution"]["average_scores"], ensure_ascii=False),
        "",
        "## Rewrite And Repair",
        "",
        f"- Rewrite attempts: {report['rewrite']['attempts']}",
        f"- Rewrite success: {report['rewrite']['success']} ({report['rewrite']['success_rate']})",
        f"- P0 repair attempts: {report['p0_repair']['attempts']}",
        f"- P0 repair success: {report['p0_repair']['success']} ({report['p0_repair']['success_rate']})",
        "",
        "## Delivery Reliability",
        "",
        f"- Admin report sent: {report['admin_report']['sent']} / {report['admin_report']['nightly_runs']} ({report['admin_report']['send_rate']})",
        f"- Admin report skipped: {report['admin_report']['skipped']}",
        f"- Morning sent: {report['morning_send']['sent']} / {report['morning_send']['runs']} ({report['morning_send']['send_rate']})",
        f"- Morning ok: {report['morning_send']['ok']} / {report['morning_send']['runs']} ({report['morning_send']['ok_rate']})",
        f"- Morning blocked: {report['morning_send']['blocked']}",
        f"- Morning skipped: {report['morning_send']['skipped']}",
        "",
        "## Knowledge Conversion",
        "",
        f"- Quality issues total: {report['knowledge_conversion']['quality_issues_total']}",
        f"- Converted to rule/script/example: {report['knowledge_conversion']['converted_total']}",
        f"- Weekly good examples: {report['knowledge_conversion']['weekly_good_examples']}",
        f"- Weekly bad examples: {report['knowledge_conversion']['weekly_bad_examples']}",
        f"- Weekly patterns updated: {report['knowledge_conversion']['weekly_patterns_updated']}",
        "- Top issue types: " + json.dumps(report["knowledge_conversion"]["top_issue_types"], ensure_ascii=False),
        "- Top modules: " + json.dumps(report["knowledge_conversion"]["top_modules"], ensure_ascii=False),
        "",
        "## Quality Reflections",
        "",
        f"- New reflections this week: {report['quality_reflections']['new_reflections_total']}",
        "- Repeated issue types: " + json.dumps(report["quality_reflections"]["repeated_issue_types"], ensure_ascii=False),
        "- Promoted to rule/checker/example: " + json.dumps(report["quality_reflections"]["promoted_counts"], ensure_ascii=False),
        "",
        "## Regression Cases",
        "",
        f"- Total regression cases: {report['regression_cases']['total_cases']}",
        f"- New regression cases this week: {report['regression_cases']['new_cases_this_week']}",
        f"- Latest run: {report['regression_cases']['latest_run_passed']} passed / {report['regression_cases']['latest_run_case_count']} total ({report['regression_cases']['latest_run_pass_rate']})",
        f"- Latest run failed: {report['regression_cases']['latest_run_failed']}",
        "",
        "## Token / Cost Review",
        "",
        f"- Nightly rows with token stats: {report['token_review']['nightly_rows_with_tokens']}",
        f"- Estimated total tokens: {report['token_review']['estimated_total_tokens']}",
        f"- Average tokens per email: {report['token_review']['average_tokens_per_email']}",
        f"- LLM call count: {report['token_review']['llm_call_count']}",
        f"- Fallback count: {report['token_review']['fallback_count']}",
        f"- Most expensive stage: {report['token_review']['most_expensive_stage'] or 'N/A'}",
        "- Stage totals: " + json.dumps(report["token_review"]["stage_totals"], ensure_ascii=False),
        f"- Multi-candidate cost note: {report['token_review']['multi_candidate_cost_note']}",
        "",
        "## Next Week Harness Upgrade",
        "",
    ]
    lines.extend(f"- {item}" for item in report["next_week_harness_upgrade"])
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weekly Harness quality review from harness_metrics.jsonl.")
    parser.add_argument("--metrics", type=Path, help="Path to harness_metrics.jsonl. Defaults to OUTPUT_DIR/harness_metrics.jsonl.")
    parser.add_argument("--knowledge-dir", type=Path, default=ROOT / "knowledge")
    parser.add_argument("--week", help="ISO week label, for example 2026-W19. Defaults to current week.")
    parser.add_argument("--start", type=dt.date.fromisoformat, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", type=dt.date.fromisoformat, help="End date YYYY-MM-DD.")
    parser.add_argument("--output-dir", type=Path, help="Output directory. Defaults to metrics file directory or OUTPUT_DIR.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start and args.end:
        start, end = args.start, args.end
        year, week_no, _ = start.isocalendar()
        week = args.week or f"{year}-W{week_no:02d}"
    else:
        start, end, week = _current_week_range()
        if args.week:
            week = args.week

    if args.metrics:
        metrics_path = args.metrics
    else:
        from config import settings

        metrics_path = settings.harness_metrics_path
    output_dir = args.output_dir or metrics_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    report = build_weekly_review(
        metrics_path=metrics_path,
        knowledge_dir=args.knowledge_dir,
        start=start,
        end=end,
        week=week,
    )
    json_path = output_dir / f"weekly_harness_review_{week}.json"
    md_path = output_dir / f"weekly_harness_review_{week}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "week": week}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

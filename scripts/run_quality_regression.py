from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_risk_quality import evaluate_content_risks
from minor_auto_fixer import apply_minor_auto_fixes


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _stringify(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _issue_codes(review: dict[str, Any]) -> list[str]:
    return [
        str(issue.get("code") or "")
        for issue in review.get("issues") or []
        if isinstance(issue, dict) and issue.get("code")
    ]


def run_case(path: Path) -> dict[str, Any]:
    case = _read_json(path)
    case_id = str(case.get("case_id") or path.stem)
    brief = case.get("brief") if isinstance(case.get("brief"), dict) else {}
    plain_text = str(case.get("plain_text") or "")
    html_body = str(case.get("html_body") or "")

    review = evaluate_content_risks(brief, plain_text, html_body)
    fix_result = apply_minor_auto_fixes(brief, [review])
    codes = _issue_codes(review)
    fixed_text = _stringify(fix_result.get("brief") or brief)

    failures: list[str] = []
    for expected in case.get("expected_issue_codes") or []:
        if str(expected) not in codes:
            failures.append(f"missing expected issue code: {expected}")
    for unexpected in case.get("unexpected_issue_codes") or []:
        if str(unexpected) in codes:
            failures.append(f"unexpected issue code: {unexpected}")

    if "expect_changed" in case and bool(fix_result.get("changed")) != bool(case.get("expect_changed")):
        failures.append(f"expected changed={case.get('expect_changed')} but got {fix_result.get('changed')}")

    for text in case.get("fixed_must_contain") or []:
        if str(text) not in fixed_text:
            failures.append(f"fixed brief missing text: {text}")
    for text in case.get("fixed_must_not_contain") or []:
        if str(text) in fixed_text:
            failures.append(f"fixed brief still contains text: {text}")

    return {
        "case_id": case_id,
        "path": str(path),
        "ok": not failures,
        "failures": failures,
        "issue_codes": codes,
        "changed": bool(fix_result.get("changed")),
        "fix_count": len(fix_result.get("fixes") or []),
        "score": review.get("score"),
        "status": review.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run content-risk quality regression cases.")
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "tests" / "quality_cases")
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON report path.")
    args = parser.parse_args()

    cases_dir = args.cases_dir
    paths = sorted(cases_dir.glob("*.json"))
    if not paths:
        print(f"no regression cases found: {cases_dir}", file=sys.stderr)
        return 2

    results = [run_case(path) for path in paths]
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed

    for item in results:
        marker = "PASS" if item["ok"] else "FAIL"
        print(f"{marker} {item['case_id']} codes={item['issue_codes']} changed={item['changed']} fixes={item['fix_count']}")
        for failure in item["failures"]:
            print(f"  - {failure}")

    report = {
        "schema_version": 1,
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"summary: {passed}/{len(results)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_regression_cases import build_report


def test_run_regression_cases_executes_sample_tree_and_writes_expected_results(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cases_root = repo_root / "knowledge" / "regression_cases"

    report = build_report(cases_root)

    assert report["case_count"] >= 7
    assert report["failed"] == 0
    categories = report["categories"]
    assert "half_sentence" in categories
    assert "weekly_pdf_path_error" in categories
    assert report["pass_rate"] == 1.0

    output_path = tmp_path / "latest_regression_cases.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["passed"] == report["passed"]


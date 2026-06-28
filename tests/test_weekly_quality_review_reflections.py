from __future__ import annotations

from datetime import date
import json

from scripts.weekly_quality_review import build_weekly_review, render_markdown


def test_weekly_quality_review_summarizes_reflections(tmp_path) -> None:
    metrics_path = tmp_path / "harness_metrics.jsonl"
    metrics_path.write_text("", encoding="utf-8")
    (tmp_path / "latest_regression_cases.json").write_text(
        json.dumps(
            {
                "case_count": 3,
                "passed": 2,
                "failed": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    rows = [
        {
            "reflection_schema_version": 1,
            "date": "2026-06-23",
            "issue_type": "half_sentence",
            "module": "content_quality",
            "recurrence_count": 2,
            "promoted_to": "rule",
        },
        {
            "reflection_schema_version": 1,
            "date": "2026-06-24",
            "issue_type": "half_sentence",
            "module": "content_quality",
            "recurrence_count": 3,
            "promoted_to": "checker",
        },
        {
            "reflection_schema_version": 1,
            "date": "2026-06-25",
            "issue_type": "label_leak",
            "module": "expression_quality",
            "recurrence_count": 1,
            "promoted_to": "archived",
        },
    ]
    (knowledge_dir / "quality_issues.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    (knowledge_dir / "weekly_log.md").write_text("", encoding="utf-8")
    (knowledge_dir / "regression_cases" / "half_sentence" / "case-a").mkdir(parents=True)
    (knowledge_dir / "regression_cases" / "half_sentence" / "case-a" / "input.json").write_text("{}", encoding="utf-8")
    (knowledge_dir / "regression_cases" / "label_leak" / "case-b").mkdir(parents=True)
    (knowledge_dir / "regression_cases" / "label_leak" / "case-b" / "input.json").write_text("{}", encoding="utf-8")

    report = build_weekly_review(
        metrics_path=metrics_path,
        knowledge_dir=knowledge_dir,
        start=date.fromisoformat("2026-06-23"),
        end=date.fromisoformat("2026-06-29"),
        week="2026-W26",
    )

    assert report["quality_reflections"]["new_reflections_total"] == 3
    assert report["quality_reflections"]["repeated_issue_types"][0]["name"] == "half_sentence"
    assert report["quality_reflections"]["promoted_counts"][0]["name"] in {"rule", "checker"}
    assert report["regression_cases"]["total_cases"] == 2
    assert report["regression_cases"]["latest_run_passed"] == 2
    assert report["regression_cases"]["latest_run_case_count"] == 3

    markdown = render_markdown(report)
    assert "## Quality Reflections" in markdown
    assert "New reflections this week: 3" in markdown
    assert "## Regression Cases" in markdown

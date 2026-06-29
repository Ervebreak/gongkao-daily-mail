from __future__ import annotations

from datetime import date
import json

from scripts.weekly_quality_review import build_weekly_review, render_markdown


def test_weekly_quality_review_summarizes_reflections(tmp_path) -> None:
    metrics_path = tmp_path / "harness_metrics.jsonl"
    metrics_path.write_text("", encoding="utf-8")

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

    markdown = render_markdown(report)
    assert "## Quality Reflections" in markdown
    assert "New reflections this week: 3" in markdown


def test_weekly_quality_review_includes_token_review(tmp_path) -> None:
    metrics_path = tmp_path / "harness_metrics.jsonl"
    metrics_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": "2026-06-23",
                        "mode": "nightly_candidate",
                        "estimated_total_tokens": 900,
                        "llm_call_count": 5,
                        "selection_tokens": 180,
                        "writing_tokens": 500,
                        "rewrite_tokens": 120,
                        "policy_rerank_tokens": 60,
                        "lite_cta_tokens": 40,
                        "fallback_count": 1,
                    },
                    ensure_ascii=False,
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "quality_issues.jsonl").write_text("", encoding="utf-8")
    (knowledge_dir / "weekly_log.md").write_text("", encoding="utf-8")

    report = build_weekly_review(
        metrics_path=metrics_path,
        knowledge_dir=knowledge_dir,
        start=date.fromisoformat("2026-06-23"),
        end=date.fromisoformat("2026-06-29"),
        week="2026-W26",
    )

    assert report["token_review"]["estimated_total_tokens"] == 900
    assert report["token_review"]["average_tokens_per_email"] == 900.0
    assert report["token_review"]["most_expensive_stage"] == "writing_tokens"

    markdown = render_markdown(report)
    assert "## Token / Cost Review" in markdown
    assert "Estimated total tokens: 900" in markdown

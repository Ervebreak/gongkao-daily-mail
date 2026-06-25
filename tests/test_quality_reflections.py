from __future__ import annotations

import json
from pathlib import Path

from quality_reflections import generate_quality_reflections


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_generate_quality_reflections_writes_latest_payload_and_knowledge(tmp_path) -> None:
    output_dir = tmp_path / "output"
    knowledge_dir = tmp_path / "knowledge"
    output_dir.mkdir()
    knowledge_dir.mkdir()

    candidate = {
        "delivery_date": "2026-06-23",
        "subject": "公考晨读",
    }
    latest_quality = {
        "final": {
            "content_quality": {
                "issues": [
                    {
                        "severity": "high",
                        "code": "text_truncation",
                        "message": "正文疑似半截句",
                        "bad_text": "这些细节是申论对策题拿高",
                    }
                ]
            },
            "policy_coordinate": {
                "issues": [
                    {
                        "severity": "medium",
                        "code": "weak_match",
                        "message": "policy weak match",
                    }
                ]
            },
        }
    }

    payload = generate_quality_reflections(
        output_dir=output_dir,
        knowledge_dir=knowledge_dir,
        candidate=candidate,
        latest_quality=latest_quality,
        latest_quality_card="质量卡摘录",
        rewrite_comparison=[],
    )

    assert payload["reflection_count"] == 2
    assert (output_dir / "latest_quality_reflections.json").exists()

    issue_types = {row["issue_type"] for row in payload["reflections"]}
    assert issue_types == {"half_sentence", "policy_weak_match"}

    rows = _read_jsonl(knowledge_dir / "quality_issues.jsonl")
    assert len(rows) == 2
    assert all(row["source_run"] == "latest_quality:2026-06-23" for row in rows)
    assert all("root_cause" in row for row in rows)
    assert all("detector" in row for row in rows)
    assert all("auto_fix" in row for row in rows)

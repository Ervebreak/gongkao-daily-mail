from __future__ import annotations

from main import build_gate_from_quality_map


def test_content_quality_hard_fail_syncs_into_quality_gate() -> None:
    quality = {
        "daily_question": {"issues": []},
        "framework_map": {"issues": []},
        "today_takeaway": {"issues": []},
        "brief_cleanliness": {"issues": []},
        "quick_reads": {"issues": []},
        "duplication": {"issues": []},
        "expression_quality": {"issues": []},
        "module_redundancy": {"issues": []},
        "content_risk": {"issues": []},
        "selection": {"issues": []},
        "cleanliness": {"issues": []},
        "policy_coordinate": {"issues": []},
        "content_quality": {
            "status": "fail",
            "can_send": False,
            "issues": [
                {
                    "severity": "high",
                    "code": "text_truncation",
                    "message": "文本截断",
                    "bad_text": "这些细节是申论对策题拿高",
                }
            ],
        },
    }

    gate = build_gate_from_quality_map(
        quality,
        plain_text="今天完整版里，这些细节是申论对策题拿高的关键。",
        html_body="<p>今天完整版里，这些细节是申论对策题拿高的关键。</p>",
    )

    assert gate["overall"] == "fail"
    assert gate["p0_count"] >= 1
    assert any(item["code"] == "text_truncation" for item in gate["p0_issues"])


def test_visible_truncation_issue_escalates_only_when_rendered_output_still_contains_bad_text() -> None:
    quality = {
        "daily_question": {"issues": []},
        "framework_map": {"issues": []},
        "today_takeaway": {
            "issues": [
                {
                    "severity": "high",
                    "code": "truncated_takeaway",
                    "message": "可迁移框架疑似截断",
                    "bad_text": "最后用准入、收费、责任、清退四",
                }
            ]
        },
        "brief_cleanliness": {"issues": []},
        "quick_reads": {"issues": []},
        "duplication": {"issues": []},
        "expression_quality": {"issues": []},
        "module_redundancy": {"issues": []},
        "content_risk": {"issues": []},
        "selection": {"issues": []},
        "cleanliness": {"issues": []},
        "policy_coordinate": {"issues": []},
        "content_quality": {"status": "ok", "can_send": True, "issues": []},
    }

    gate_hidden = build_gate_from_quality_map(quality, plain_text="今天可带走：框架已修复。", html_body="<p>框架已修复。</p>")
    gate_visible = build_gate_from_quality_map(
        quality,
        plain_text="今天可带走：最后用准入、收费、责任、清退四",
        html_body="<p>今天可带走：最后用准入、收费、责任、清退四</p>",
    )

    assert gate_hidden["overall"] == "ok"
    assert gate_hidden["p0_count"] == 0
    assert gate_visible["overall"] == "fail"
    assert any(item["code"] == "truncated_takeaway" for item in gate_visible["p0_issues"])


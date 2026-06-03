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
                    "code": "truncation_error",
                    "message": "文本截断",
                }
            ],
        },
    }

    gate = build_gate_from_quality_map(quality)

    assert gate["overall"] == "fail"
    assert gate["p0_count"] >= 1
    assert any(item["code"] == "truncation_error" for item in gate["p0_issues"])


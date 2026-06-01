from __future__ import annotations

from candidate_store import normalize_candidate_quality_state


def test_normalize_candidate_quality_state_syncs_top_level_gate() -> None:
    payload = {
        "delivery_date": "2026-06-01",
        "quality": {"final": {}, "gate": {"overall": "ok", "p0_count": 0, "p0_issues": []}},
    }

    normalized = normalize_candidate_quality_state(payload)

    assert normalized["quality_gate"] == {"overall": "ok", "p0_count": 0, "p0_issues": []}
    assert normalized["quality"]["gate"] == normalized["quality_gate"]
    assert normalized["quality_state_consistency"]["quality_gate_synced"] is True


def test_normalize_candidate_quality_state_prefers_top_level_gate() -> None:
    payload = {
        "delivery_date": "2026-06-01",
        "quality_gate": {"overall": "fail", "p0_count": 1, "p0_issues": [{"code": "x"}]},
        "quality": {"final": {}, "gate": {"overall": "ok", "p0_count": 0, "p0_issues": []}},
    }

    normalized = normalize_candidate_quality_state(payload)

    assert normalized["quality"]["gate"] == normalized["quality_gate"]
    assert normalized["quality_gate"]["overall"] == "fail"
    assert normalized["quality_state_consistency"]["quality_gate_overall"] == "fail"

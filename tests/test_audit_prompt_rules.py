from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_prompt_rules import audit_prompt_rules


def test_audit_prompt_rules_detects_field_limit_conflict_and_archived_runtime_rule(tmp_path: Path) -> None:
    (tmp_path / "content_harness").mkdir()
    (tmp_path / "knowledge").mkdir()

    (tmp_path / "prompt_templates.py").write_text(
        "answer_framework 每条不超过35字\n",
        encoding="utf-8",
    )
    (tmp_path / "llm_client.py").write_text(
        "answer_framework 每条不超过45字\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG_HARNESS.md").write_text("", encoding="utf-8")
    (tmp_path / "content_harness" / "runtime_prompt_rules.md").write_text(
        "# Runtime Rules\n"
        "统一完整句，不要出现对用户可见的半截句和尾部残句。\n"
        "统一完整句，不要出现对用户可见的半截句和尾部残句。\n"
        "old_rule_marker 不能继续保留。\n",
        encoding="utf-8",
    )
    (tmp_path / "content_harness" / "content_rules.md").write_text("", encoding="utf-8")
    (tmp_path / "knowledge" / "quality_issues.jsonl").write_text(
        json.dumps({"id": "QI-1", "status": "archived", "issue_type": "old_rule_marker"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = audit_prompt_rules(tmp_path)

    conflicts = report["field_limit_conflicts"]
    assert conflicts
    assert conflicts[0]["field"] == "daily_question.answer_framework"
    assert set(conflicts[0]["values"]) == {35, 45}
    assert report["duplicate_rules"]
    assert report["archived_runtime_rules"][0]["term"] == "old_rule_marker"


def test_field_impact_map_covers_required_fields() -> None:
    map_path = Path(__file__).resolve().parents[1] / "content_harness" / "field_impact_map.json"
    payload = json.loads(map_path.read_text(encoding="utf-8"))

    required_fields = {
        "daily_question.answer_framework",
        "daily_question.thirty_second_answer",
        "policy_coordinate",
        "golden_sentences",
        "rewritable_expression",
        "lite_paid_cta",
        "lite_paid_highlight",
        "speed_reads",
        "weekly_pdf_url / oss_pdf_path",
        "subscription.end_date / reminder_sent / plan",
        "referral_code / referred_by",
    }

    assert required_fields.issubset(payload.keys())
    for field in required_fields:
        entry = payload[field]
        assert "renders_to" in entry and entry["renders_to"]
        assert "quality_modules" in entry and entry["quality_modules"]
        assert "must_validate" in entry and entry["must_validate"]
        assert entry["risk_level"] in {"P0", "P1", "P2"}

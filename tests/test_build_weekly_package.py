from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.build_weekly_package import (
    EXPECTED_PRACTICE_TYPES,
    build_delivery_report,
    build_shared_data,
    evaluate_content_gate,
    evaluate_input_gate,
    load_enrichment,
    validate_generation_mode,
)


def _practice_question(question_type: str) -> dict:
    return {
        "question_type": question_type,
        "question": f"这是一道{question_type}。",
        "answer_hint": "先分析问题，再提出有针对性的作答思路。",
        "mini_reference_answer": "答题时应从问题、原因和治理路径三个层面展开。",
        "suggested_golden_sentences": ["治理既要解决眼前问题，也要完善长效机制。"],
    }


def _material_card() -> dict:
    return {
        "source_articles": ["治理案例"],
        "material_summary": "这条素材以具体治理场景为基础，能够说明责任分工和闭环反馈的重要性。",
        "usage_examples": [
            {"theme": "群众诉求闭环办理", "example": "示例一。"},
            {"theme": "多主体协同治理", "example": "示例二。"},
        ],
        "use_boundary": "适合公共治理题，不替代专业执法结论。",
    }


def _valid_enrichment() -> dict:
    return {
        "exam_map_cards": [{"title": f"考点{i}"} for i in range(4)],
        "selected_expression_rows": [{"sentence": f"表达{i}。"} for i in range(8)],
        "material_cards": [_material_card()],
        "practice_questions": [_practice_question(item) for item in EXPECTED_PRACTICE_TYPES],
        "warnings": [],
    }


def _valid_data() -> dict:
    return {
        "days": [{"date": "2026-09-07"}],
        **_valid_enrichment(),
    }


def _args(**overrides) -> argparse.Namespace:
    values = {
        "offline": False,
        "enrichment_json": "",
        "api_key": "",
        "model": "",
        "fallback_model": "",
        "base_url": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_content_gate_accepts_complete_weekly_package() -> None:
    assert evaluate_content_gate(_valid_data()) == []


def test_content_gate_blocks_incomplete_enrichment() -> None:
    data = _valid_data()
    data["exam_map_cards"] = data["exam_map_cards"][:3]
    data["selected_expression_rows"] = data["selected_expression_rows"][:7]
    data["practice_questions"] = data["practice_questions"][:2]

    codes = {item["code"] for item in evaluate_content_gate(data)}

    assert "weekly_package_exam_map_count" in codes
    assert "weekly_package_expression_count" in codes
    assert "weekly_package_practice_count" in codes


def test_content_gate_requires_three_distinct_practice_types() -> None:
    data = _valid_data()
    data["practice_questions"][2] = _practice_question("面试综合分析题")

    codes = {item["code"] for item in evaluate_content_gate(data)}

    assert "weekly_package_practice_types" in codes


def test_content_gate_allows_zero_material_cards() -> None:
    data = _valid_data()
    data["material_cards"] = []

    codes = {item["code"] for item in evaluate_content_gate(data)}

    assert not any(code.startswith("weekly_package_material") for code in codes)


def test_content_gate_blocks_incomplete_material_card() -> None:
    data = _valid_data()
    data["material_cards"] = [{"material_summary": "只有简介。", "usage_examples": []}]

    codes = {item["code"] for item in evaluate_content_gate(data)}

    assert "weekly_package_material_incomplete" in codes
    assert "weekly_package_material_examples" in codes


def test_input_gate_blocks_duplicate_delivery_dates() -> None:
    issues = evaluate_input_gate(
        ["2026-09-07", "2026-09-08", "2026-09-08"],
        start_date="2026-09-07",
        end_date="2026-09-12",
    )

    assert any(item["code"] == "weekly_package_duplicate_dates" for item in issues)


def test_offline_requires_enrichment_json() -> None:
    with pytest.raises(ValueError, match="requires --enrichment-json"):
        validate_generation_mode(_args(offline=True))


def test_offline_rejects_online_model_options() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        validate_generation_mode(
            _args(offline=True, enrichment_json="weekly_enrichment.json", api_key="secret")
        )


def test_load_enrichment_accepts_skill_generated_payload(tmp_path: Path) -> None:
    path = tmp_path / "weekly_enrichment.json"
    path.write_text(json.dumps(_valid_enrichment(), ensure_ascii=False), encoding="utf-8")

    loaded = load_enrichment(path)

    assert loaded == _valid_enrichment()


def test_load_enrichment_rejects_missing_required_keys(tmp_path: Path) -> None:
    path = tmp_path / "weekly_enrichment.json"
    path.write_text(json.dumps({"exam_map_cards": []}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required keys"):
        load_enrichment(path)


def test_build_shared_data_injects_enrichment_without_calling_original_model_builder() -> None:
    enrichment = _valid_enrichment()
    calls = {"build_data": 0}

    fake = SimpleNamespace()

    def build_data(_payloads, _start, _end, _misses, *, enrichment_override=None):
        calls["build_data"] += 1
        assert enrichment_override is enrichment
        return {"days": [{"date": "2026-09-07"}], **enrichment_override}

    fake.build_data = build_data

    result = build_shared_data(
        fake,
        [{"date": "2026-09-07"}],
        "2026-09-07",
        "2026-09-12",
        enrichment_override=enrichment,
    )

    assert calls["build_data"] == 1
    assert result["material_cards"] == enrichment["material_cards"]
    assert not hasattr(fake, "build_weekly_enrichment")


def test_delivery_report_records_offline_no_model_contract(tmp_path: Path) -> None:
    report = build_delivery_report(
        start_date="2026-09-07",
        end_date="2026-09-12",
        source_files=[tmp_path / "2026-09-07.json"],
        output_dir=tmp_path,
        shared_data=_valid_data(),
        artifacts={},
        issues=[],
        generation_mode="offline_enrichment",
        enrichment_json=str(tmp_path / "weekly_enrichment.json"),
    )

    assert report["status"] == "pass"
    assert report["model_enrichment_disabled"] is True
    assert report["model_api_call"] is False
    assert report["generation_mode"] == "offline_enrichment"


def test_entrypoint_does_not_import_publish_side_effect_modules() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "build_weekly_package.py").read_text(encoding="utf-8")

    assert "from weekly_report import" not in source
    assert "from email_sender import" not in source
    assert "from candidate_store import" not in source
    assert "put_oss_object" not in source
    assert "send_email(" not in source
    assert "save_candidate(" not in source

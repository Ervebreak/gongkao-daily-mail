from __future__ import annotations

from pathlib import Path

from scripts.build_weekly_package import (
    EXPECTED_PRACTICE_TYPES,
    evaluate_content_gate,
    evaluate_input_gate,
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


def _valid_data() -> dict:
    return {
        "days": [{"date": "2026-09-07"}],
        "exam_map_cards": [{"title": f"考点{i}"} for i in range(4)],
        "selected_expression_rows": [{"sentence": f"表达{i}。"} for i in range(8)],
        "material_cards": [_material_card()],
        "practice_questions": [_practice_question(item) for item in EXPECTED_PRACTICE_TYPES],
    }


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


def test_entrypoint_does_not_import_publish_side_effect_modules() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "build_weekly_package.py").read_text(encoding="utf-8")

    assert "from weekly_report import" not in source
    assert "from email_sender import" not in source
    assert "from candidate_store import" not in source
    assert "put_oss_object" not in source
    assert "send_email(" not in source
    assert "save_candidate(" not in source

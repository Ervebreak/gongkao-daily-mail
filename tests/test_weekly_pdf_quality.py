from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weekly_material_curator import _validate_enrichment
from weekly_typst_export import build_preview_data_from_full_data, render_typst


def _base_payload(card: dict) -> dict:
    return {
        "exam_map_cards": [],
        "selected_expression_rows": [],
        "material_cards": [card],
        "practice_questions": [],
        "warnings": [],
    }


def _valid_material_card() -> dict:
    return {
        "title": "平台投诉治理素材卡",
        "source_article": "平台投诉治理",
        "source_date": "2026-06-10",
        "source_articles": ["平台投诉治理"],
        "source_dates": ["2026-06-10"],
        "source_urls": ["https://example.com/platform"],
        "material_type": "mechanism",
        "usable_themes": ["基层治理要听见一线声音", "公共服务要从平均供给转向精准抵达"],
        "suitable_question_types": ["综合分析题", "对策建议题"],
        "target_topics": ["基层治理要听见一线声音", "公共服务要从平均供给转向精准抵达"],
        "core_topic": "平台责任与协同治理",
        "generalizable_logic": "面对跨主体公共问题，要把统一入口、分类处置和闭环反馈放进同一条治理链条。",
        "factual_anchor": "平台设置投诉入口，相关部门按类别转办并公开处理结果。",
        "material_summary": "这条素材来自平台投诉治理场景：群众诉求先被统一收集，再按问题类型分流到责任部门处理，并向群众反馈结果，体现了公共服务从接诉即办转向闭环办理的治理考点。",
        "usage_examples": [
            {
                "theme": "基层治理要听见一线声音",
                "paragraph": "写基层治理时，可以用这条素材说明治理不能停留在表态回应，而要让群众知道问题由谁接、谁来办、办到什么程度、办完之后如何反馈，真正把一线诉求转化为治理动作，避免群众反复追问和多头等待。",
            },
            {
                "theme": "公共服务要从平均供给转向精准抵达",
                "paragraph": "论证公共服务精准化时，这条素材可以说明同样是诉求也要分类处置，把有限资源投向最需要的环节，并通过结果公开和责任反馈减少群众反复等待、重复反映，让服务从平均供给转向精准抵达。",
            },
        ],
        "exam_paragraph": "治理复杂问题，关键在于把责任链条和反馈链条同时压实。",
        "exam_paragraph_specific": "针对平台投诉，既要压实平台主体责任，也要通过部门转办形成处置闭环。",
        "exam_paragraph_general": "面对涉及多主体的公共问题，应以责任清单厘清边界，以分类处置提高效率，以闭环反馈回应关切。",
        "can_use_for": ["平台投诉闭环处置", "社区停车纠纷协商", "校园食品安全反馈办理"],
        "suggested_question_types": ["综合分析题", "对策建议题"],
        "not_suitable_for": ["纯理论阐释题"],
        "usage_boundary": "适合公共问题治理场景，不适合替代专业执法结论。",
        "use_boundary": "适合公共问题治理场景，不适合替代专业执法结论。",
    }


def test_material_card_structure_is_stable_and_complete() -> None:
    result = _validate_enrichment(_base_payload(_valid_material_card()))

    assert len(result["material_cards"]) == 1
    card = result["material_cards"][0]
    assert card["title"]
    assert card["source_article"] == "平台投诉治理"
    assert card["source_date"] == "2026-06-10"
    assert len(card["usable_themes"]) >= 2
    assert len(card["suitable_question_types"]) >= 1
    assert card["material_summary"]
    assert card["usage_boundary"]
    assert len(card["usage_examples"]) >= 2
    assert all(example["theme"] and example["paragraph"] for example in card["usage_examples"])


def test_material_card_rejects_user_visible_placeholder_copy() -> None:
    broken = _valid_material_card()
    broken["material_summary"] = "暂无可展示素材"

    result = _validate_enrichment(_base_payload(broken))

    assert result["material_cards"] == []
    assert any("placeholder" in warning for warning in result["warnings"])


def test_preview_material_title_comes_from_full_material_cards() -> None:
    card = _valid_material_card()
    preview = build_preview_data_from_full_data(
        {
            "start_date": "2026-06-08",
            "end_date": "2026-06-14",
            "period": "2026.06.08 - 2026.06.14",
            "days": [],
            "stats": {"featured_count": 0, "questions_count": 0, "golden_count": 0, "quick_count": 0},
            "exam_map_cards": [],
            "selected_expression_rows": [],
            "material_cards": [card],
            "practice_questions": [],
        }
    )

    assert preview["material_preview"]["title"] == "作文素材积累·平台投诉治理素材卡（一例多用）"


def test_render_typst_supports_new_material_card_fields() -> None:
    text = render_typst(
        {
            "start_date": "2026-06-08",
            "end_date": "2026-06-14",
            "period": "2026.06.08 - 2026.06.14",
            "days": [],
            "misses": [],
            "warnings": [],
            "stats": {"featured_count": 0, "questions_count": 0, "golden_count": 0, "quick_count": 0},
            "hot_keywords": [],
            "map_cards": [],
            "expression_rows": [],
            "framework_rows": [],
            "exam_map_cards": [],
            "selected_expression_rows": [],
            "material_cards": [_valid_material_card()],
            "practice_questions": [],
        }
    )

    assert "平台投诉治理素材卡" in text
    assert "平台投诉治理" in text
    assert "基层治理要听见一线声音" in text
    assert "综合分析题" in text
    assert "作文示例" in text
    assert "使用边界" in text

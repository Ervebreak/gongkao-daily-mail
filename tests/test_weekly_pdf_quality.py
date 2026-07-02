from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weekly_material_curator import _validate_enrichment
from weekly_typst_export import build_preview_data_from_full_data, render_typst


def _valid_expression_rows() -> list[dict]:
    return [
        {
            "date": "2026-06-10",
            "theme": "基层治理要把群众诉求转化为闭环办理机制",
            "sentence": "治理难题不能停留在表态回应，而要把责任链条和反馈链条同时压实。",
            "scenario": "适合基层治理、公共服务、矛盾协调类题目。",
        },
        {
            "date": "2026-06-11",
            "theme": "公共服务要从平均供给转向精准抵达",
            "sentence": "公共服务不是简单平均发力，而是把有限资源投向群众最急最盼的环节。",
            "scenario": "适合公共服务优化、民生保障、服务精准化类题目。",
        },
    ]


def _valid_material_card() -> dict:
    return {
        "title": "平台投诉治理素材卡",
        "source_article": "平台投诉治理",
        "source_date": "2026-06-10",
        "source_articles": ["平台投诉治理"],
        "source_dates": ["2026-06-10"],
        "source_urls": ["https://example.com/platform"],
        "material_type": "mechanism",
        "usable_themes": [
            "基层治理要把群众诉求转化为闭环办理机制",
            "公共服务要从平均供给转向精准抵达",
        ],
        "suitable_question_types": ["综合分析题", "对策建议题"],
        "target_topics": [
            "基层治理要把群众诉求转化为闭环办理机制",
            "公共服务要从平均供给转向精准抵达",
        ],
        "core_topic": "平台责任与协同治理",
        "generalizable_logic": "面对跨主体公共问题，要把统一入口、分类处置和闭环反馈放进同一条治理链条。",
        "factual_anchor": "平台设置投诉入口，相关部门按类别转办并公开处理结果。",
        "material_summary": "这条素材来自平台投诉治理场景：群众诉求先被统一收集，再按问题类型分流到责任部门处理，并向群众反馈结果，体现了公共服务从接诉即办转向闭环办理的治理考点。",
        "usage_examples": [
            {
                "theme": "基层治理要把群众诉求转化为闭环办理机制",
                "paragraph": "写基层治理时，可以用这条素材说明治理不能停留在表态回应，而要让群众知道问题由谁接、谁来办、办到什么程度、办完之后如何反馈，真正把一线诉求转化为治理动作，避免群众反复追问和多头等待。",
            },
            {
                "theme": "公共服务要从平均供给转向精准抵达",
                "paragraph": "论证公共服务精准化时，这条素材可以说明同样是诉求也要分类处置，把有限资源投向最需要的环节，并通过结果公开和责任反馈减少群众重复等待、重复反映，让服务从平均供给转向精准抵达。",
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


def _valid_training_questions() -> list[dict]:
    return [
        {
            "question_type": "面试综合分析题",
            "question": "某地社区停车矛盾反复反映，居民投诉和商户经营冲突并存。请你谈谈如何看待这一问题，并提出回应思路。",
            "linked_materials": ["平台投诉治理素材卡"],
            "linked_expressions": ["治理难题不能停留在表态回应，而要把责任链条和反馈链条同时压实。"],
            "review_key": "先点出矛盾交织，再说明治理要把接诉、协商、反馈连成闭环。",
            "answer_outline": ["界定矛盾焦点", "厘清责任边界", "建立反馈闭环"],
            "reference_direction": "可借用平台投诉治理素材，把多主体诉求处理转成协商、分流、反馈三步回应路径。",
        },
        {
            "question_type": "对策建议题",
            "question": "某市公共服务窗口反映群众诉求分流不清、重复跑腿问题突出。请你提出改进对策。",
            "linked_materials": ["平台投诉治理素材卡"],
            "linked_expressions": ["公共服务不是简单平均发力，而是把有限资源投向群众最急最盼的环节。"],
            "review_key": "重点写清统一入口、分类处置和结果反馈，不要空喊提升服务。",
            "answer_outline": ["统一受理入口", "分类分级转办", "公开反馈结果"],
            "reference_direction": "这道题可以直接调用素材中的统一入口和分类转办机制，把事实抽象成措施闭环。",
        },
        {
            "question_type": "申论作文分论点展开题",
            "question": "某地推进基层治理现代化时，群众反映问题多头流转、责任模糊、反馈滞后。请围绕“治理要让群众看见回应”写一段分论点展开。",
            "linked_materials": [],
            "linked_expressions": ["治理难题不能停留在表态回应，而要把责任链条和反馈链条同时压实。"],
            "review_key": "把群众是否看见回应作为分论点中心，再展开责任、流程、反馈三个层次。",
            "answer_outline": ["回应不能停留表态", "责任链条必须压实", "反馈结果要让群众可感"],
            "reference_direction": "这道题可用本周金句做分论点起句，再把治理闭环写成论证链条。",
        },
    ]


def _base_payload() -> dict:
    return {
        "exam_map_cards": [],
        "selected_expression_rows": _valid_expression_rows(),
        "material_cards": [_valid_material_card()],
        "training_questions": _valid_training_questions(),
        "warnings": [],
    }


def _base_full_data() -> dict:
    validated = _validate_enrichment(_base_payload())
    return {
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
        "selected_expression_rows": _valid_expression_rows(),
        "material_cards": validated["material_cards"],
        "training_questions": validated["training_questions"],
        "practice_questions": validated["practice_questions"],
    }


def test_material_card_structure_is_stable_and_complete() -> None:
    result = _validate_enrichment(_base_payload())

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
    assert all(example["example"] == example["paragraph"] for example in card["usage_examples"])


def test_material_card_rejects_user_visible_placeholder_copy() -> None:
    payload = _base_payload()
    payload["material_cards"][0]["material_summary"] = "暂无可展示素材"

    result = _validate_enrichment(payload)

    assert result["material_cards"] == []
    assert any("placeholder" in warning for warning in result["warnings"])


def test_training_questions_bind_to_material_cards_and_expressions() -> None:
    result = _validate_enrichment(_base_payload())

    assert len(result["training_questions"]) == 3
    titles = {card["title"] for card in result["material_cards"]}
    linked_material_count = 0
    for row in result["training_questions"]:
        assert row["question"]
        assert row["review_key"]
        assert len(row["answer_outline"]) >= 3
        assert row["linked_materials"] or row["linked_expressions"]
        assert all(title in titles for title in row["linked_materials"])
        assert all(len(item) <= 36 for item in row["answer_outline"])
        if row["linked_materials"]:
            linked_material_count += 1
    assert linked_material_count >= 2


def test_training_question_linked_materials_match_material_card_titles() -> None:
    result = _validate_enrichment(_base_payload())

    titles = {card["title"] for card in result["material_cards"]}
    for row in result["training_questions"]:
        for linked in row["linked_materials"]:
            assert linked in titles


def test_preview_material_title_comes_from_full_material_cards() -> None:
    preview = build_preview_data_from_full_data(_base_full_data())
    assert preview["material_preview"]["title"] == "平台投诉治理素材卡"


def test_render_typst_supports_training_question_binding_and_clean_copy() -> None:
    text = render_typst(_base_full_data())

    assert "平台投诉治理素材卡" in text
    assert "2026-06-10" in text
    assert "基层治理要把群众诉求转化为闭环办理机制" in text
    assert "综合分析题" in text
    assert "素材简介" in text
    assert "作文示例" in text
    assert "使用边界" in text
    assert "可调用素材" in text
    assert "审题关键" in text
    assert "作答提示" in text
    assert "参考迁移方向" in text
    assert "暂无题目" not in text
    assert "待补充" not in text
    assert "材料不足" not in text
    assert "TODO" not in text
    assert "debug" not in text


def test_render_typst_with_new_material_fields_only() -> None:
    payload = _base_payload()
    card = payload["material_cards"][0]
    card.pop("source_articles", None)
    card.pop("source_dates", None)
    card.pop("target_topics", None)
    card.pop("suggested_question_types", None)
    card.pop("use_boundary", None)
    card["usage_examples"] = [
        {
            "theme": "基层治理要把群众诉求转化为闭环办理机制",
            "paragraph": "这条示例强调诉求收集、分类转办和结果反馈要形成闭环，既要让群众知道问题由谁受理，也要让群众看到办理进度、责任部门和最终结果，避免事项在多个环节之间反复空转。",
        },
        {
            "theme": "公共服务要从平均供给转向精准抵达",
            "paragraph": "这条示例强调要把有限资源投向群众最急最盼的环节，通过分类分级办理、过程公开和结果反馈，让服务从平均供给转向精准抵达，也让群众感受到治理温度和服务效率。",
        },
    ]

    validated = _validate_enrichment(payload)
    assert validated["material_cards"][0]["usage_examples"][0]["paragraph"].startswith("这条示例强调诉求收集")
    assert validated["material_cards"][0]["usage_examples"][1]["paragraph"].startswith("这条示例强调要把有限资源")
    text = render_typst(
        {
            **_base_full_data(),
            "material_cards": validated["material_cards"],
            "training_questions": validated["training_questions"],
            "practice_questions": validated["practice_questions"],
        }
    )

    assert "平台投诉治理" in text
    assert "2026-06-10" in text
    assert "基层治理要把群众诉求转化为闭环办理机制" in text
    assert "综合分析题" in text
    assert "作文示例" in text
    assert "适合公共问题治理场景，不适合替代专业执法结论。" in text

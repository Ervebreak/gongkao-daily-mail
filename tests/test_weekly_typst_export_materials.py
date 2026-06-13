from __future__ import annotations

from weekly_typst_export import render_typst


def _base_data() -> dict:
    return {
        "start_date": "2026-06-09",
        "end_date": "2026-06-13",
        "period": "2026.06.09 - 2026.06.13",
        "days": [],
        "misses": [],
        "warnings": [],
        "stats": {
            "featured_count": 0,
            "questions_count": 0,
            "golden_count": 0,
            "quick_count": 0,
        },
        "hot_keywords": [],
        "map_cards": [],
        "expression_rows": [],
        "framework_rows": [],
        "exam_map_cards": [],
        "selected_expression_rows": [],
        "material_cards": [],
        "practice_questions": [],
    }


def test_render_typst_hides_material_section_when_no_cards() -> None:
    text = render_typst(_base_data())

    assert "作文素材积累·一例多用" not in text
    assert "本周考场素材库" not in text


def test_render_typst_shows_material_cards_as_one_case_many_uses() -> None:
    data = _base_data()
    data["material_cards"] = [
        {
            "title": "投诉闭环素材卡",
            "material_type": "机制型",
            "source_dates": ["2026-06-10"],
            "source_articles": ["平台投诉治理"],
            "target_topics": ["基层治理要听见一线声音"],
            "suggested_question_types": ["综合分析题"],
            "factual_anchor": "平台设置投诉入口，部门按类别转办并公开处理结果。",
            "material_summary": "这条素材来自平台投诉治理场景，能说明公共服务既要有入口，也要有责任分派和结果回告，不适合被拔高成脱离事实的万能模板。",
            "usage_examples": [
                {
                    "theme": "基层治理要听见一线声音",
                    "example": "写基层治理时，可以用这条素材说明治理不是简单接诉即办，而是要让群众知道问题由谁接、谁来办、什么时候反馈，真正把群众声音转成治理动作。",
                },
                {
                    "theme": "公共服务要从平均供给转向精准抵达",
                    "example": "论证公共服务精准化时，这条素材可以说明同样是诉求也要分类处置，把资源投到最需要的环节，避免群众反复等待、重复反映。",
                },
            ],
            "use_boundary": "适合公共问题治理，不适合替代专业执法结论。",
            "not_suitable_for": ["纯理论阐释题"],
        }
    ]

    text = render_typst(data)

    assert "作文素材积累·一例多用" in text
    assert "作文素材积累·#title（一例多用）" in text
    assert "素材简介" in text
    assert "作文示例" in text
    assert "使用边界" in text
    assert "本周考场素材库" not in text

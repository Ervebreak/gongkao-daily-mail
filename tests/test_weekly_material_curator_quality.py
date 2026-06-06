from __future__ import annotations

from copy import deepcopy

from weekly_material_curator import _validate_enrichment, select_material_candidate_articles


GOLDEN_SENTENCE = "把问题解决在基层一线。"


def _expression_rows() -> list[dict[str, str]]:
    return [
        {
            "date": f"2026-06-{idx:02d}",
            "theme": "治理实践",
            "sentence": GOLDEN_SENTENCE,
            "scenario": "公共治理作答",
        }
        for idx in range(1, 9)
    ]


def _practice_question(question_type: str, title: str) -> dict[str, object]:
    return {
        "title": title,
        "question_type": question_type,
        "question": f"请围绕{title}谈谈你的理解。",
        "target_topics": ["治理实践"],
        "suggested_golden_sentences": [GOLDEN_SENTENCE],
        "suggested_case_materials": ["投诉闭环素材卡"],
        "suggested_policy_expressions": ["分类处置、闭环反馈。"],
        "answer_hint": f"作答时可用“{GOLDEN_SENTENCE}”引出治理动作。",
        "mini_reference_answer": f"{GOLDEN_SENTENCE}要通过分类处置和闭环反馈回应群众诉求。",
        "use_boundary": "适合讨论治理机制优化，不适合替代专业执法依据。",
    }


def _valid_material_card() -> dict[str, object]:
    return {
        "title": "投诉闭环素材卡",
        "material_type": "机制型",
        "source_dates": ["2026-06-01"],
        "source_articles": ["平台投诉治理"],
        "source_urls": ["https://example.com/platform"],
        "target_topics": ["责任落实"],
        "core_topic": "平台责任与协同治理。",
        "generalizable_logic": "面对跨主体公共问题，应明确责任边界、分类处置诉求、形成反馈闭环。",
        "factual_anchor": "平台设置投诉入口，部门按类别转办并公开处理结果。",
        "exam_paragraph": "治理复杂问题，关键在于把责任链条和反馈链条同时压实。",
        "exam_paragraph_specific": "针对平台投诉，既要压实平台主体责任，也要通过部门转办形成处置闭环。",
        "exam_paragraph_general": "面对涉及多主体的公共问题，应以责任清单厘清边界，以分类处置提高效率，以闭环反馈回应关切。",
        "can_use_for": [
            "基层治理",
            "公共服务",
            "社区老旧小区停车纠纷协商",
            "平台投诉闭环处置",
            "校园食品安全明厨亮灶",
        ],
        "suggested_question_types": ["综合分析题", "对策建议题"],
        "not_suitable_for": ["纯理论阐释题"],
        "memory_sentence": "责任清单加闭环反馈，能把多主体问题变成可治理流程。",
        "use_tip": "先写具体机制，再抽象出责任、分类、反馈三步。",
        "use_boundary": "适合公共问题治理，不适合编造成具体执法结论。",
    }


def test_weekly_enrichment_guards_question_count_and_extra_practice_fields() -> None:
    payload = {
        "exam_map_cards": [],
        "selected_expression_rows": _expression_rows(),
        "material_cards": [_valid_material_card()],
        "practice_questions": [
            _practice_question("面试综合分析题", "综合分析"),
            _practice_question("对策建议题", "对策建议"),
            _practice_question("申论作文分论点展开题", "分论点展开"),
            _practice_question("面试综合分析题", "额外重复题"),
        ],
        "golden_sentence_practice": [{"title": "不应外泄的小练习"}],
    }

    result = _validate_enrichment(payload)

    assert len(result["practice_questions"]) == 3
    assert "golden_sentence_practice" not in result
    assert "金句小练习" not in result


def test_material_cards_require_general_exam_writing_boundary_and_specific_use_cases() -> None:
    valid_card = _valid_material_card()

    missing_general = deepcopy(valid_card)
    missing_general["source_articles"] = ["缺少通用写法"]
    missing_general["exam_paragraph_general"] = ""

    missing_boundary = deepcopy(valid_card)
    missing_boundary["source_articles"] = ["缺少使用边界"]
    missing_boundary["use_boundary"] = ""

    vague_use_cases = deepcopy(valid_card)
    vague_use_cases["source_articles"] = ["空泛适用场景"]
    vague_use_cases["can_use_for"] = ["基层治理", "公共服务", "民生保障", "社会治理"]

    payload = {
        "exam_map_cards": [],
        "selected_expression_rows": _expression_rows(),
        "material_cards": [valid_card, missing_general, missing_boundary, vague_use_cases],
        "practice_questions": [],
    }

    result = _validate_enrichment(payload)

    assert [card["source_articles"][0] for card in result["material_cards"]] == ["平台投诉治理"]
    assert result["material_cards"][0]["can_use_for"] == [
        "社区老旧小区停车纠纷协商",
        "平台投诉闭环处置",
        "校园食品安全明厨亮灶",
    ]
    assert all(3 <= len(card["can_use_for"]) <= 5 for card in result["material_cards"])


def test_quick_reads_compete_by_material_usability_score() -> None:
    days = [
        {
            "date": "2026-06-01",
            "theme": "治理实践",
            "featured": {
                "title": "一地特色宣传活动",
                "source": "本地媒体",
                "url": "https://example.com/featured",
                "one_sentence": "介绍某地特色宣传活动，话题较窄，迁移空间有限。",
                "exam_use": ["可了解背景"],
            },
            "quick_reads": [
                {
                    "title": "平台投诉治理机制",
                    "source": "权威媒体",
                    "url": "https://example.com/quick",
                    "theme": "市场监管",
                    "one_sentence": "围绕群众投诉、平台责任、公共问题、矛盾处置展开。",
                    "exam_value": "可迁移到申论、面试和公共治理场景，形成分类处置、协同联动、闭环反馈框架。",
                }
            ],
        }
    ]

    candidates = select_material_candidate_articles(days, max_candidates=2)

    assert candidates[0]["role"] == "quick_read"
    assert candidates[0]["material_score"] > candidates[1]["material_score"]

from __future__ import annotations

from copy import deepcopy

from weekly_material_curator import _build_prompt, _validate_enrichment, _validate_usage_examples, select_material_candidate_articles


GOLDEN_SENTENCE = "把问题解决在基层一线，关键是让治理动作能被群众真实感知。"


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
        "question": f"请围绕《{title}》谈谈你的理解。",
        "target_topics": ["治理实践"],
        "suggested_golden_sentences": [GOLDEN_SENTENCE],
        "suggested_case_materials": ["投诉闭环素材卡"],
        "suggested_policy_expressions": ["分类处置、闭环反馈。"],
        "answer_hint": f"作答时可用“{GOLDEN_SENTENCE}”引出治理动作。",
        "mini_reference_answer": f"{GOLDEN_SENTENCE}，要通过分类处置和闭环反馈回应群众诉求。",
        "use_boundary": "适合讨论治理机制优化，不适合替代专业执法依据。",
    }


def _valid_material_card() -> dict[str, object]:
    return {
        "title": "投诉闭环素材卡",
        "material_type": "机制型",
        "source_dates": ["2026-06-01"],
        "source_articles": ["平台投诉治理"],
        "source_urls": ["https://example.com/platform"],
        "target_topics": ["责任落实", "公共服务要从平均供给转向精准抵达"],
        "core_topic": "平台责任与协同治理",
        "generalizable_logic": "面对跨主体公共问题，应明确责任边界、分类处置诉求、形成反馈闭环。",
        "factual_anchor": "平台设置投诉入口，部门按类别转办并公开处理结果。",
        "material_summary": "这条素材来自平台投诉治理场景：原文明确写到平台设置统一投诉入口，相关部门按照问题类型分流转办，并向群众公开处理结果。它能说明公共服务不能停留在平均供给，而要把诉求识别、责任分派和反馈闭环落到具体环节，不适合被夸大成所有治理场景的万能模板。",
        "usage_examples": [
            {
                "theme": "基层治理要听见一线声音",
                "example": "写基层治理时，可以把这条素材放进“先听见问题、再形成闭环”的论述中。比如平台把群众投诉集中收入口，部门按问题类型转办并公开反馈，就说明治理不能只看表面响应速度，更要让群众知道问题交给了谁、什么时候能解决、结果如何回告，真正把一线声音转化为治理动作。",
            },
            {
                "theme": "公共服务要从平均供给转向精准抵达",
                "example": "论证公共服务精准化时，这条素材可以用来说明“同样是诉求，处理路径不能一刀切”。平台先识别投诉类型，再分流到对应部门处理，最后形成反馈闭环，体现的不是简单多做服务，而是让有限资源按问题性质精准投放，避免群众多头反映、反复等待。",
            },
        ],
        "exam_paragraph": "治理复杂问题，关键在于把责任链条和反馈链条同时压实。",
        "exam_paragraph_specific": "针对平台投诉，既要压实平台主体责任，也要通过部门转办形成处置闭环。",
        "exam_paragraph_general": "面对涉及多主体的公共问题，应以责任清单厘清边界，以分类处置提高效率，以闭环反馈回应关切。",
        "can_use_for": [
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


def test_weekly_enrichment_keeps_only_three_practice_questions() -> None:
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
    assert all("material_cards" not in warning for warning in result["warnings"])


def test_material_cards_require_summary_examples_and_boundary() -> None:
    valid_card = _valid_material_card()

    missing_summary = deepcopy(valid_card)
    missing_summary["source_articles"] = ["缺少素材简介"]
    missing_summary["material_summary"] = ""

    missing_boundary = deepcopy(valid_card)
    missing_boundary["source_articles"] = ["缺少使用边界"]
    missing_boundary["use_boundary"] = ""

    missing_examples = deepcopy(valid_card)
    missing_examples["source_articles"] = ["缺少示例"]
    missing_examples["usage_examples"] = []

    generic_theme = deepcopy(valid_card)
    generic_theme["source_articles"] = ["主题空泛"]
    generic_theme["usage_examples"] = [
        {"theme": "担当", "example": valid_card["usage_examples"][0]["example"]},
        valid_card["usage_examples"][1],
    ]

    payload = {
        "exam_map_cards": [],
        "selected_expression_rows": _expression_rows(),
        "material_cards": [valid_card, missing_summary, missing_boundary, missing_examples, generic_theme],
        "practice_questions": [],
    }

    result = _validate_enrichment(payload)

    assert [card["source_articles"][0] for card in result["material_cards"]] == ["平台投诉治理"]
    assert len(result["material_cards"][0]["usage_examples"]) == 2
    assert result["material_cards"][0]["material_summary"]
    assert all("fewer than 3 material_cards" not in warning for warning in result["warnings"])


def test_prompt_requires_material_summary_usage_examples_and_no_three_to_six_rule() -> None:
    days = [
        {
            "date": "2026-06-01",
            "theme": "治理实践",
            "featured": {"title": "平台投诉治理", "source": "权威媒体", "url": "https://example.com/a"},
            "question": {"question": "示例题"},
            "takeaway": {},
            "steps": [],
            "tags": [],
            "quick_reads": [],
        }
    ]

    prompt = _build_prompt(days, candidate_evidence=[])

    assert "material_summary" in prompt
    assert "usage_examples" in prompt
    assert '"theme": "具体申论/面试主题"' in prompt
    assert '"example": "120到220字的考场表达示例"' in prompt
    assert "material_cards：3到6条" not in prompt


def test_overlong_usage_example_is_dropped_when_no_complete_sentence_within_limit() -> None:
    warnings: list[str] = []
    long_example = "这是一个很长但一直没有句号的示例" * 30

    result = _validate_usage_examples(
        [{"theme": "基层治理要听见一线声音", "example": long_example}],
        "平台投诉治理",
        warnings,
    )

    assert result == []
    assert any("overlong non-closable usage example" in warning for warning in warnings)


def test_overlong_usage_example_is_trimmed_to_complete_sentence() -> None:
    warnings: list[str] = []
    sentence = "基层治理不能只满足于表态回应，更要把群众诉求分流到具体责任链条中，确保群众知道谁来办、什么时候办、办到什么程度。"
    long_example = sentence * 4 + "这是未完成的半句"

    result = _validate_usage_examples(
        [{"theme": "基层治理要听见一线声音", "example": long_example}],
        "平台投诉治理",
        warnings,
    )

    assert len(result) == 1
    assert result[0]["example"][-1] in "。！？!?"
    assert len(result[0]["example"]) < len(long_example)
    assert "这是未完成的半句" not in result[0]["example"]
    assert warnings == []


def test_quick_reads_compete_by_material_usability_score() -> None:
    days = [
        {
            "date": "2026-06-01",
            "theme": "治理实践",
            "featured": {
                "title": "一场特色宣传活动",
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

from __future__ import annotations

from weekly_typst_export import (
    _balanced_table_chunks,
    _cover_training_mainline,
    _render_table_chunks,
    build_data,
    build_preview_data_from_full_data,
    render_preview_typst,
    render_typst,
)


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


def _sample_day(day_no: int) -> dict:
    return {
        "day_no": day_no,
        "date": f"2026-06-{8 + day_no:02d}",
        "short_date": f"06.{8 + day_no:02d}",
        "weekday": f"周{day_no}",
        "theme": f"主题 {day_no}",
        "focus": f"本日重点 {day_no}",
        "featured": {
            "title": f"精读文章 {day_no}",
            "source": "人民日报",
            "published_at": f"2026-06-{8 + day_no:02d}",
            "url": "https://example.com/article",
            "theme": "公共服务",
            "one_sentence": "以精细治理提升公共服务质效。",
            "rewritable_expression": "",
            "article_type": "评论",
            "main_thread": "发现问题—分析原因—提出对策",
        },
        "question": {
            "question_type": "综合分析题",
            "question": "请谈谈你的理解。",
            "answer_framework": [],
        },
        "takeaway": {"golden_sentences": [], "framework": ""},
        "steps": [
            {"label": "提出问题", "content": "明确治理堵点。"},
            {"label": "分析原因", "content": "梳理问题成因。"},
            {"label": "提出对策", "content": "形成闭环方案。"},
        ],
        "tags": ["基层治理"],
        "quick_reads": [],
    }


def test_render_typst_hides_material_section_when_no_cards() -> None:
    text = render_typst(_base_data())

    assert "作文素材积累·一例多用" not in text
    assert "本周考场素材库" not in text
    assert "margin: (x: 16mm, y: 21mm)" in text
    assert "leading: 0.9em" in text
    assert "spacing: 0.86em" in text
    assert "周日复盘版" not in text


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
    assert "事实锚点" not in text
    assert "不适合用于" not in text
    assert "本周考场素材库" not in text
    assert "复制链接或搜索原文题目打开原文" in text



def test_render_typst_keeps_material_card_opening_with_heading() -> None:
    text = render_typst(_base_data())

    opening = '#block(breakable: false)[\n    #text(size: 12pt, weight: "bold", fill: brand)[作文素材积累·#title（一例多用）]'
    assert opening in text
    assert text.index(opening) < text.index('#if examples != "" [')


def test_render_typst_normalizes_template_owned_material_title_wrappers() -> None:
    data = _base_data()
    data["material_cards"] = [
        {
            "title": "作文素材积累·招聘背调划清信息使用边界（一例多用）",
            "material_summary": "招聘核验需要守住信息使用边界。",
        }
    ]

    text = render_typst(data)

    assert "#material-card[招聘背调划清信息使用边界]" in text
    assert "#material-card[作文素材积累·招聘背调划清信息使用边界（一例多用）]" not in text


def test_render_typst_wraps_table_cells_as_unbreakable_rows() -> None:
    data = _base_data()
    data["days"] = [
        {
            "day_no": 1,
            "date": "2026-06-10",
            "short_date": "06.10",
            "weekday": "周三",
            "theme": "公共空间治理",
            "focus": "把闲置边角空间转化为居民可达、可用、可持续的公共服务场景。",
            "featured": {
                "title": "盘活城市边角空间",
                "source": "人民日报",
                "published_at": "2026-06-10",
                "url": "https://example.com/article",
                "theme": "公共服务",
                "one_sentence": "以精细治理提升空间使用效率。",
                "rewritable_expression": "",
                "article_type": "",
                "main_thread": "",
            },
            "question": {
                "question_type": "综合分析题",
                "question": "",
                "answer_framework": [],
            },
            "takeaway": {"golden_sentences": [], "framework": ""},
            "steps": [],
            "tags": [],
            "quick_reads": [],
        }
    ]

    text = render_typst(data)

    assert "[#block(breakable: false)[06.10\n周三]]" in text
    assert "[#block(breakable: false)[公共空间治理\n把闲置边角空间转化为居民可达、可用、可持续的公共服务场景。]]" in text


def test_balanced_table_chunks_never_leave_a_single_row_tail() -> None:
    chunks = _balanced_table_chunks([str(index) for index in range(7)], max_rows=4)

    assert [len(chunk) for chunk in chunks] == [4, 3]
    assert all(len(chunk) != 1 for chunk in chunks)
    assert [len(chunk) for chunk in _balanced_table_chunks([str(index) for index in range(9)], max_rows=8)] == [5, 4]
    assert [len(chunk) for chunk in _balanced_table_chunks([str(index) for index in range(12)], max_rows=8)] == [6, 6]


def test_render_table_chunks_repeat_headers_and_force_page_boundaries() -> None:
    rows = [f"[row-{index}]," for index in range(7)]

    text = _render_table_chunks(
        rows,
        columns="(1fr,)",
        headers=["日期"],
        max_rows=4,
        continuation_label="测试表",
    )

    assert text.count("#table(columns:") == 2
    assert text.count("[日期]") == 2
    assert text.count("#pagebreak()") == 1
    assert text.count("#block(breakable: false)[\n#table") == 2
    assert "[测试表（续）]" in text


def test_render_typst_starts_long_tables_on_fresh_pages() -> None:
    text = render_typst(_base_data())

    assert "#pagebreak()\n#block-title[本周主题总览]" in text
    assert "#pagebreak()\n#block-title[补充阅读清单]" in text


def test_render_typst_balances_six_day_overview_without_blank_opening_page() -> None:
    data = _base_data()
    data["days"] = [_sample_day(day_no) for day_no in range(1, 7)]

    text = render_typst(data)
    section = text.split("#block-title[本周主题总览]", 1)[1].split(
        "#block-title[02｜本周高频考点地图]", 1
    )[0]

    assert section.count("#table(columns: (0.9fr, 1.7fr, 2.4fr, 2fr)") == 2
    assert "[本周主题总览（续）]" in section
    assert section.count("#pagebreak()") == 2
    assert section.rstrip().endswith("#pagebreak()")
    assert "#pagebreak()\n#text(size: 12pt, weight: \"bold\", fill: brand)[本周主题总览（续）]" in section


def test_daily_framework_can_split_after_atomic_title_and_first_step() -> None:
    data = _base_data()
    data["days"] = [_sample_day(1)]

    text = render_typst(data)

    assert '#let framework-box(body) = block(fill: white, stroke: 0.6pt + line, inset: 13pt, radius: 9pt, width: 100%, breakable: true)' in text
    opening = '#framework-box[\n  #block(breakable: false)[\n    #text(weight: "bold", fill: brand)[文章框架图]'
    assert opening in text
    assert text.index(opening) < text.index('#step-item("01")[提出问题][明确治理堵点。]')
    assert text.index('#step-item("01")[提出问题][明确治理堵点。]') < text.index(
        '#step-item("02")[分析原因][梳理问题成因。]'
    )


def test_weekly_exercises_each_start_on_a_fresh_page() -> None:
    data = _base_data()
    data["practice_questions"] = [
        {"title": f"训练题 {i}", "question": f"题干 {i}", "mini_reference_answer": f"参考答案 {i}"}
        for i in range(1, 4)
    ]
    text = render_typst(data)
    section = text.split("｜本周 3 道考场迁移训练\n", 1)[1].split(
        "｜每日内容压缩回看\n", 1
    )[0]
    assert section.count("#practice-card[") == 3
    assert "[参考答案 1][]\n#pagebreak()\n#practice-card[训练题 2]" in section
    assert "[参考答案 2][]\n#pagebreak()\n#practice-card[训练题 3]" in section
    assert "参考答案 3" in section


def test_daily_review_keeps_one_representative_expression_without_third_card() -> None:
    data = _base_data()
    day = _sample_day(1)
    day["takeaway"]["golden_sentences"] = [
        {"sentence": "第一条代表性表达。", "scenario": "基层治理"},
        {"sentence": "第二条仍保留在完整表达库。", "scenario": "公共服务"},
    ]
    day["featured"]["rewritable_expression"] = "第三条可改写表达。"
    data["days"] = [day]

    text = render_typst(data)

    assert "第一条代表性表达。" in text
    assert "第二条仍保留在完整表达库。" not in text
    assert "第三条可改写表达。" not in text


def test_daily_review_uses_rewritable_expression_when_no_golden_sentence() -> None:
    data = _base_data()
    day = _sample_day(1)
    day["featured"]["rewritable_expression"] = "可改写表达作为回看兜底。"
    data["days"] = [day]

    text = render_typst(data)

    assert "可改写表达作为回看兜底。" in text


def test_build_data_counts_reviewed_weekly_practice_questions_for_cover() -> None:
    payloads = []
    for day in range(21, 27):
        date = f"2026-09-{day:02d}"
        payloads.append(
            {
                "delivery_date": date,
                "brief": {
                    "date": date,
                    "featured_article": {"title": f"精读文章 {day}"},
                    "daily_question": {"question": f"每日题目 {day}"},
                },
            }
        )
    enrichment = {
        "exam_map_cards": [],
        "selected_expression_rows": [],
        "material_cards": [],
        "practice_questions": [
            {"question_type": "面试综合分析题", "question": "题目一"},
            {"question_type": "对策建议题", "question": "题目二"},
            {"question_type": "申论作文分论点展开题", "question": "题目三"},
        ],
        "warnings": [],
    }

    data = build_data(
        payloads,
        "2026-09-21",
        "2026-09-26",
        [],
        enrichment_override=enrichment,
    )

    assert data["stats"]["featured_count"] == 6
    assert data["stats"]["questions_count"] == 3


def test_cover_training_mainline_comes_from_current_week_practice() -> None:
    data = _base_data()
    data["stats"]["questions_count"] = 3
    data["practice_questions"] = [
        {
            "question_type": "面试综合分析题",
            "question": "题目一",
            "target_topics": ["城市治理"],
        },
        {
            "question_type": "对策建议题",
            "question": "题目二",
            "target_topics": ["网络内容治理"],
        },
        {
            "question_type": "申论作文分论点展开题",
            "question": "题目三",
            "target_topics": ["高质量发展"],
        },
    ]

    mainline = _cover_training_mainline(data)
    text = render_typst(data)

    assert mainline == (
        "围绕“城市治理、网络内容治理、高质量发展”等本周主题，共设置 3 道训练，"
        "覆盖面试综合分析题、对策建议题、申论作文分论点展开题，重点练习把材料转化为考场表达。"
    )
    assert mainline in text
    assert "技术治理、执法规范、专业纠纷、生态边界" not in text
    assert "再做本周 3 道考场迁移训练" in text



def test_render_typst_shows_at_most_three_material_cards() -> None:
    data = _base_data()
    data["material_cards"] = []
    for idx in range(4):
        data["material_cards"].append(
            {
                "title": f"素材{idx + 1}",
                "material_type": "机制型",
                "source_dates": ["2026-06-10"],
                "source_articles": [f"文章{idx + 1}"],
                "target_topics": ["基层治理要听见一线声音"],
                "suggested_question_types": ["综合分析题"],
                "factual_anchor": "平台设置投诉入口，部门按类别转办并公开处理结果。",
                "material_summary": "这条素材来自平台投诉治理场景，能说明公共服务既要有入口，也要有责任分派和结果回告，不适合被拔高成脱离事实的万能模板。",
                "usage_examples": [
                    {"theme": "基层治理要听见一线声音", "example": "写基层治理时，可以用这条素材说明治理不能停留在表面回应，而要让群众看到具体办理链条和结果回告。"},
                    {"theme": "公共服务要从平均供给转向精准抵达", "example": "论证公共服务精准化时，这条素材可以说明同样是诉求也要分类处置，把资源投到最需要的环节。"},
                ],
                "use_boundary": "适合公共问题治理，不适合替代专业执法结论。",
                "not_suitable_for": ["纯理论阐释题"],
            }
        )

    text = render_typst(data)

    assert "素材1" in text
    assert "素材2" in text
    assert "素材3" in text
    assert "素材4" not in text


def test_render_typst_cleans_internal_copy_and_updates_extension_note() -> None:
    text = render_typst(_base_data())

    assert "周日复盘版" not in text
    assert "不新增精读文章" not in text
    assert "宁缺毋滥，不为凑数补卡" not in text
    assert "内部测试" not in text
    assert "quality gate" not in text.lower()
    assert "p0" not in text.lower()
    assert "后台字段" not in text
    assert "json" not in text.lower()
    assert "candidate" not in text.lower()
    assert "复制链接或搜索原文题目打开原文" in text


def test_render_preview_typst_keeps_frontend_copy_clean() -> None:
    text = render_preview_typst(
        {
            "period": "2026.06.09 - 2026.06.13",
            "theme_overview": "本周主要围绕基层治理闭环办理和公共服务精准抵达展开。",
            "focus_points": ["基层治理要把群众诉求转化为闭环办理机制"],
            "full_modules": ["本周高频考点地图"],
            "expression_preview": "把群众诉求接住、办实、反馈清楚。",
            "material_preview": {"title": "素材片段", "source": "精读文章", "summary": "只展示一小段真实可用内容。"},
            "practice_preview": {"title": "训练题片段", "question": "请谈谈如何推进闭环办理。", "direction": "先摸清诉求，再公开反馈。"},
            "cta_url": "https://example.com/paid",
        }
    )

    assert "周日复盘版" not in text
    assert "内部测试" not in text
    assert "quality gate" not in text.lower()
    assert "candidate" not in text.lower()
    assert "思考方向" not in text
    assert "先摸清诉求，再公开反馈。" not in text


def test_preview_focus_title_counts_only_nonempty_points() -> None:
    text = render_preview_typst({"focus_points": ["方向甲", "", "  ", "方向乙"]})
    assert "本周 2 个高频考点方向" in text
    assert "本周 3 个高频考点方向" not in text
    assert "方向甲" in text and "方向乙" in text

    empty_text = render_preview_typst({"focus_points": []})
    assert "#section[本周高频考点方向]" in empty_text
    assert "本周 0 个高频考点方向" not in empty_text


def test_preview_practice_whitelist_excludes_answer_fields() -> None:
    data = _base_data()
    data["practice_questions"] = [
        {
            "title": "招聘背调边界题",
            "question": "请谈谈招聘背调应如何划清边界。",
            "target_topics": ["信息核验边界"],
            "answer_hint": "先肯定合理核验价值，再从调查范围、决定说明和异议更正展开。",
            "mini_reference_answer": "这是一份不应出现在 Lite 中的完整答案。",
        }
    ]

    preview = build_preview_data_from_full_data(data)
    text = render_preview_typst(preview)

    assert preview["practice_preview"] == {
        "title": "招聘背调边界题",
        "question": "请谈谈招聘背调应如何划清边界。",
    }
    assert "请谈谈招聘背调应如何划清边界。" in text
    assert "先肯定合理核验价值" not in text
    assert "这是一份不应出现在 Lite 中的完整答案" not in text
    assert "思考方向" not in text


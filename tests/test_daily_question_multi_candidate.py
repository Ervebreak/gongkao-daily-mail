from __future__ import annotations

import json
from types import SimpleNamespace

from email_renderer import render_email_html, render_plain_text
import llm_client
from question_quality import evaluate_daily_question


def _brief() -> dict:
    return {
        "today_theme": "基层治理与群众诉求回应",
        "featured_article": {
            "title": "把群众诉求办成闭环",
            "source": "人民网",
            "url": "https://example.com/a",
            "theme": "基层治理",
            "one_sentence": "把群众诉求接住、办实、反馈清楚，治理工作才更有信任基础。",
            "rewritable_expression": "先把群众最急的现实问题办好，再推动后续协商，更容易形成稳定共识。",
        },
        "today_takeaway": {
            "framework": "统一入口-分类流转-结果反馈",
        },
        "daily_question": {
            "question_type": "综合分析题",
            "question": "请结合文章谈谈如何回应群众诉求。",
            "answer_framework": ["摸清诉求：先找准问题。", "分类处置：明确责任链条。", "闭环反馈：公开回应群众。"],
            "candidate_answer": "先把群众的急难愁盼接住，再形成分类处置和闭环反馈。",
            "thirty_second_answer": "先接诉求，再分流处置，最后闭环反馈。",
        },
        "today_three_things": {},
        "_question_bank": {"question_bank_refs": []},
    }


def test_select_best_daily_question_candidate_prefers_higher_scoring_generated_option(monkeypatch) -> None:
    brief = _brief()
    monkeypatch.setattr(
        llm_client,
        "settings",
        SimpleNamespace(daily_question_multi_candidate_enabled=True),
    )

    def fake_call(prompt, test_mode, stage="writing", contract=True):
        if "申论综合分析/对策题" in prompt:
            return {
                "daily_question": {
                    "question_type": "申论对策题",
                    "question": "围绕基层治理中群众诉求复杂、工作推进受阻的情况，谈谈如何把回应诉求转成闭环办理机制。",
                    "exam_focus": "基层治理中的群众诉求办理",
                    "breaking_hint": "从摸清诉求、公开协商、责任闭环三个层次展开。",
                    "answer_framework": ["摸清诉求：先把顾虑找准。", "公开协商：把分歧摆上桌面。", "闭环反馈：明确责任时限。"],
                    "candidate_answer": "基层治理中的诉求办理，关键不是简单表态，而是把群众顾虑摸清、把协商过程公开、把责任和反馈做成闭环。",
                    "thirty_second_answer": "先摸清诉求，再公开协商，最后闭环反馈。",
                    "output_prompt": "考生版提示",
                    "output_sentence_template": "把群众诉求接稳、办实、反馈清楚。",
                }
            }
        return {
            "daily_question": {
                "question_type": "机关实务题",
                "question": "你是街道工作人员，负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
                "exam_focus": "群众沟通协调",
                "breaking_hint": "从稳情绪、摸诉求、公开协商展开。",
                "answer_framework": ["稳情绪：先把误解压住。", "摸诉求：逐一梳理顾虑。", "公开协商：明确推进安排。"],
                "candidate_answer": "作为街道工作人员，要先稳住群众情绪，再摸清诉求并公开协商。",
                "thirty_second_answer": "先稳情绪，再摸诉求，最后公开协商。",
                "output_prompt": "考生版提示",
                "output_sentence_template": "把协商过程做实，推进阻力才会下降。",
            }
        }

    def fake_evaluate(candidate_brief):
        question = json.dumps(candidate_brief.get("daily_question") or {}, ensure_ascii=False)
        if "闭环办理机制" in question:
            return {"score": 91, "ok": True, "issues": []}
        if "街道工作人员" in question:
            return {"score": 78, "ok": True, "issues": []}
        return {"score": 60, "ok": True, "issues": []}

    monkeypatch.setattr(llm_client, "_call_with_fallback", fake_call)
    monkeypatch.setattr(llm_client, "evaluate_daily_question", fake_evaluate)

    result = llm_client.select_best_daily_question_candidate(brief, [], test_mode=False)

    assert result["selected_source"] == "shenlun_policy"
    assert result["fallback_used"] is False
    assert result["brief"]["daily_question"]["question_type"] == "申论对策题"
    assert result["brief"]["today_three_things"]["daily_question"].startswith("某地围绕基层治理中群众诉求复杂")
    assert len(result["candidates"]) == 3


def test_practical_wording_forces_practical_question_type(monkeypatch) -> None:
    brief = _brief()
    monkeypatch.setattr(
        llm_client,
        "settings",
        SimpleNamespace(daily_question_multi_candidate_enabled=True),
    )

    def fake_call(prompt, test_mode, stage="writing", contract=True):
        return {
            "daily_question": {
                "question_type": "申论对策题",
                "question": "你是某地团委工作人员，领导让你牵头解决青年夜校报名混乱问题，请谈谈工作思路。",
                "exam_focus": "青年夜校报名秩序治理",
                "breaking_hint": "先稳住情绪，再梳理诉求，最后闭环反馈。",
                "answer_framework": ["稳住情绪：先把现场秩序稳住。", "梳理诉求：摸清青年和机构的真实顾虑。", "闭环反馈：把时间节点和责任公开。"],
                "candidate_answer": "作为团委工作人员，既要先把现场情绪稳住，也要把报名系统的问题摸清，再把协调结果和后续安排及时公开，避免同类问题反复出现。",
                "thirty_second_answer": "先稳住情绪，再摸清问题，最后公开安排。",
                "output_prompt": "请写一句开头表态。",
                "output_sentence_template": "我认为，先把秩序稳住，再把问题摸清，才能把青年关切真正回应到位。",
            }
        }

    monkeypatch.setattr(llm_client, "_call_with_fallback", fake_call)
    monkeypatch.setattr(llm_client, "evaluate_daily_question", evaluate_daily_question)

    result = llm_client.select_best_daily_question_candidate(brief, [], test_mode=False)

    assert result["brief"]["daily_question"]["question_type"].startswith("机关实务题")
    assert result["brief"]["daily_question"]["breaking_hint"].startswith("作答时可按")


def test_shenlun_candidate_drops_identity_and_material_dependency(monkeypatch) -> None:
    brief = _brief()
    monkeypatch.setattr(
        llm_client,
        "settings",
        SimpleNamespace(daily_question_multi_candidate_enabled=True),
    )

    def fake_call(prompt, test_mode, stage="writing", contract=True):
        if "申论" in prompt:
            return {
                "daily_question": {
                    "question_type": "申论对策题",
                    "question": "请根据资料，作为街道工作人员，谈谈如何回应群众对公共工程推进的质疑。",
                    "exam_focus": "群众质疑与项目推进",
                    "breaking_hint": "先摸清诉求，再公开协商，最后闭环反馈。",
                    "answer_framework": ["摸清诉求：先找准顾虑。", "公开协商：把规则讲透。", "闭环反馈：明确责任时限。"],
                    "candidate_answer": "我认为，面对公共工程推进中的群众质疑，关键是把群众顾虑摸清、把协商过程公开、把责任和反馈做成闭环，推动项目在回应关切中稳步推进。",
                    "thirty_second_answer": "先摸清顾虑，再公开协商，最后闭环反馈。",
                    "output_prompt": "请写一句开头表态。",
                    "output_sentence_template": "我认为，回应群众质疑，关键是把规则讲明、把责任压实、把反馈做成闭环。",
                }
            }
        return {
            "daily_question": {
                "question_type": "机关实务题",
                "question": "你是街道工作人员，请谈谈如何回应群众对公共工程推进的质疑。",
                "exam_focus": "群众沟通",
                "breaking_hint": "先稳情绪，再摸诉求，最后公开说明。",
                "answer_framework": ["稳情绪：先把误解压住。", "摸诉求：梳理主要分歧。", "公开说明：回应推进安排。"],
                "candidate_answer": "作为街道工作人员，要先把群众情绪稳住，再摸清分歧，最后公开说明推进安排。",
                "thirty_second_answer": "先稳情绪，再摸诉求，最后公开说明。",
                "output_prompt": "请写一句开头表态。",
                "output_sentence_template": "我认为，先把分歧摆上台面，才能推动项目继续往前走。",
            }
        }

    monkeypatch.setattr(llm_client, "_call_with_fallback", fake_call)
    monkeypatch.setattr(llm_client, "evaluate_daily_question", evaluate_daily_question)

    result = llm_client.select_best_daily_question_candidate(brief, [], test_mode=False)
    question = result["brief"]["daily_question"]["question"]

    assert result["brief"]["daily_question"]["question_type"] == "申论对策题"
    assert "你是" not in question
    assert "领导让你" not in question
    assert "根据资料" not in question
    assert "给定资料" not in question


def test_evaluate_daily_question_reports_fix_targets() -> None:
    brief = _brief()
    brief["daily_question"] = {
        "question_type": "申论对策题",
        "question": "给定资料指出，某地公共服务供给存在堵点，请根据资料提出对策。",
        "exam_focus": "公共服务堵点治理",
        "breaking_hint": "先摸清问题，再分类推进，最后闭环反馈。",
        "answer_framework": [
            "摸清问题：先把群众不满意的环节找准。",
            "分类推进：把部门责任和办理时限压实。",
            "闭环反馈：把办理结果公开给群众。",
        ],
        "candidate_answer": "我认为，解决公共服务堵点，关键是先把群众不满意的环节摸清楚，再把部门责任和办理时限压实，最后把办理结果公开给群众，形成闭环反馈。",
        "thirty_second_answer": "先摸清问题，再分类推进，最后闭环反馈。",
        "output_prompt": "请写一句开头表态。",
        "output_sentence_template": "我认为，公共服务治理要把问题找准、责任压实、反馈做透。",
    }

    report = evaluate_daily_question(brief)
    issues = {item["code"]: item for item in report["issues"]}

    assert report["status"] in {"review", "fail"}
    assert issues["daily_question_material_dependency"]["target_field"] == "question"
    assert issues["breaking_hint_too_framework_like"]["target_field"] == "breaking_hint"
    assert issues["answer_framework_duplicates_candidate_answer"]["target_field"] == "answer_framework"


def test_shenlun_question_without_identity_is_not_flagged_missing_identity() -> None:
    brief = _brief()
    brief["daily_question"] = {
        "question_type": "申论对策题",
        "question": "某地在公共服务办理中出现群众反复跑腿、部门协同不顺的问题，请提出对策。",
        "exam_focus": "公共服务堵点治理",
        "breaking_hint": "作答时可按“找准堵点—压实责任—闭环反馈”这条路线展开。",
        "answer_framework": ["找准堵点", "压实责任", "闭环反馈"],
        "candidate_answer": "我认为，解决公共服务堵点，关键是先把群众反复跑腿的原因找准，再把部门责任和协同机制压实，最后把办理结果反馈给群众，形成闭环改进。",
        "thirty_second_answer": "先找准堵点，再压实责任，最后闭环反馈。",
        "output_prompt": "请写一句开头表态。",
        "output_sentence_template": "我认为，公共服务治理要把堵点找准、责任压实、反馈做透。",
    }

    report = evaluate_daily_question(brief)
    codes = {item["code"] for item in report["issues"]}

    assert "missing_identity" not in codes


def test_candidate_answer_renders_as_multiple_paragraphs() -> None:
    brief = _brief()
    brief.update(
        {
            "email_subject": "测试晨读",
            "date": "2026-06-29",
            "today_focus": "测试聚焦",
            "quick_reads": [],
        }
    )
    brief["featured_article"]["article_framework_map"] = {
        "type": "问题分析",
        "main_thread": "发现问题—回应诉求—形成机制",
        "steps": [
            {"label": "发现问题", "content": "先把群众最集中的意见找准。"},
            {"label": "回应诉求", "content": "把公开协商做扎实。"},
            {"label": "形成机制", "content": "把闭环反馈留下来。"},
        ],
    }
    brief["today_takeaway"].update(
        {
            "keywords": ["群众诉求", "闭环反馈"],
            "common_knowledge_points": ["公共服务要从群众感受出发。"],
        }
    )
    brief["daily_question"].update(
        {
            "candidate_answer": "我认为，面对群众对公共工程推进的质疑，第一，要先把群众最关心的影响点摸清楚。第二，要把协商过程公开，把不同诉求摆到台面上。第三，要把责任部门、时间节点和反馈方式说明白，让群众看到事情在往前推进。",
        }
    )

    plain_text = render_plain_text(brief)
    html_body = render_email_html(brief)

    assert "考生版参考答案：" in plain_text
    assert "第一，要先把群众最关心的影响点摸清楚。" in plain_text
    assert "第二，要把协商过程公开" in plain_text
    assert html_body.count("<p style=\"margin:0 0 10px;line-height:1.78;\">") >= 2

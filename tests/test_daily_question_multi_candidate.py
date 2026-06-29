from __future__ import annotations

import json
from types import SimpleNamespace

import llm_client


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
    assert result["brief"]["today_three_things"]["daily_question"].startswith("围绕基层治理中群众诉求复杂")
    assert len(result["candidates"]) == 3

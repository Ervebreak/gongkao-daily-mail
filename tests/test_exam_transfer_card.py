from __future__ import annotations

from email_renderer import render_email_html, render_plain_text
from exam_transfer_card import build_exam_transfer_card


def _sample_brief() -> dict:
    return {
        "date": "2026-06-15",
        "email_subject": "测试晨读",
        "today_theme": "基层治理",
        "today_focus": "把群众诉求转成闭环办理机制。",
        "reading_guide": {},
        "today_three_things": {
            "theme": "基层治理",
            "must_remember_sentence": "不能只解释政策，更要把诉求接住、办实、反馈清楚。",
            "daily_question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
        },
        "featured_article": {
            "title": "把群众的急难愁盼办到底",
            "source": "人民日报",
            "published_at": "2026-06-15",
            "theme": "基层治理",
            "url": "https://example.com/featured",
            "one_sentence": "文章表面讲的是公共工程推进受阻时，如何先回应群众诉求、再推动后续协商。",
            "core_viewpoint": "真正关键不是重复解释，而是把问题接住、办实并形成闭环反馈。",
            "three_useful_points": ["先回应最现实的顾虑", "再把协商条件做实", "最后形成闭环反馈"],
            "exam_use": ["这类文章适合迁移到群众诉求复杂、协同推进受阻的综合分析和基层治理题。"],
            "rewritable_expression": "可用表达：不能只做表态解释，关键是把群众诉求接住、办实、反馈清楚。",
            "article_framework_map": {
                "type": "评论",
                "main_thread": "先回应急难问题，再推动协商落地",
                "steps": [
                    {"label": "识别堵点", "content": "先把群众最在意的现实顾虑摸清。"},
                    {"label": "回应诉求", "content": "优先处理最现实、最紧迫的痛点。"},
                    {"label": "形成闭环", "content": "把公开协商、结果反馈和后续跟进接起来。"},
                ],
            },
        },
        "policy_coordinate": {
            "display_evidence_type": "qiushi",
            "policy_quote": "坚持问题导向，形成闭环办理机制。",
            "policy_source": "某政策原文",
            "policy_match_score": 78,
            "authoritative_quote": "重面子轻里子的问题，本质上是没有把群众评价落到治理闭环里。",
            "authoritative_source": "《求是》2026年第7期《树立和践行正确政绩观》",
            "qiushi_match_score": 84,
            "exam_transfer": "适合迁移到基层治理、公共服务优化和作风建设类题目，可作为分点展开或结尾升华。",
            "answer_angles": [
                "先稳情绪：先把群众最现实的顾虑接住。",
                "摸清诉求：把争议点、责任链和堵点找准。",
                "公开协商：把方案、依据和边界讲清楚。",
                "闭环反馈：让办理结果可跟踪、可复盘。",
            ],
        },
        "daily_question": {
            "question_type": "综合分析",
            "question": "如果你负责推进一项群众争议较大的公共工程，请谈谈工作思路。",
            "exam_focus": "不能只重复政策目标，要回答怎样把诉求接住、怎样形成闭环。",
            "answer_framework": [
                "稳住情绪：先接住群众最现实的顾虑。",
                "摸清症结：把争议点和责任链理顺。",
                "公开协商：把方案和依据讲清楚。",
                "闭环反馈：让办理结果可跟踪。",
            ],
            "candidate_answer": "这是完整参考答案，不应该在考场转化卡里泄露。",
            "output_prompt": "请用一句话写出这道题的开头表态。",
            "output_sentence_template": "我认为，这类问题关键不是简单解释，而是把群众诉求接住、办实、反馈清楚。",
        },
        "today_takeaway": {
            "keywords": ["基层治理", "闭环办理", "群众诉求"],
            "common_knowledge_points": ["基层治理不能只做解释，更要形成闭环办理机制。"],
            "golden_sentences": [
                {"sentence": "把群众诉求接住、办实、反馈清楚，治理才算真正落地。", "scenario": "基层治理"}
            ],
            "extension": "这段拓展联想不应继续在前台展示。",
        },
        "quick_reads": [],
    }


def test_build_exam_transfer_card_prefers_qiushi_by_default() -> None:
    card = build_exam_transfer_card(_sample_brief())

    assert card["surface_issue"]
    assert card["deep_logic"]
    assert card["evidence_type"] == "qiushi"
    assert card["authoritative_quote"]
    assert card["authoritative_source"]
    assert card["policy_quote"] == ""
    assert len(card["transfer_angles"]) >= 3
    assert card["exam_expression"]


def test_build_exam_transfer_card_allows_both_when_distinct_and_strong() -> None:
    brief = _sample_brief()
    brief["policy_coordinate"]["display_evidence_type"] = "both"
    brief["policy_coordinate"]["policy_quote"] = "要把群众诉求转成可跟踪、可反馈的闭环办理机制。"
    brief["policy_coordinate"]["policy_source"] = "国务院有关文件"
    brief["policy_coordinate"]["policy_match_score"] = 80

    card = build_exam_transfer_card(brief)

    assert card["evidence_type"] == "both"
    assert card["policy_quote"]
    assert card["authoritative_quote"]


def test_build_exam_transfer_card_still_outputs_without_evidence() -> None:
    brief = _sample_brief()
    brief["policy_coordinate"] = {}

    card = build_exam_transfer_card(brief)

    assert card["evidence_type"] == "none"
    assert card["surface_issue"]
    assert card["deep_logic"]
    assert len(card["transfer_angles"]) >= 3
    assert card["exam_expression"]


def test_full_render_uses_exam_transfer_card_and_hides_old_sections() -> None:
    brief = _sample_brief()

    html = render_email_html(brief)
    plain = render_plain_text(brief)

    assert "考场转化卡｜这篇文章到底考什么" in html
    assert "表面在讲" in html
    assert "真正考点" in html
    assert "可迁移作答角度" in html
    assert "一句能直接写进答案里" in html
    assert "记住3个点" not in html
    assert "换成考场话" not in html
    assert "可用表达" not in html
    assert "拓展联想" not in html
    assert "考场转化卡｜这篇文章到底考什么" in plain
    assert "作答角度：" in plain
    assert "这是完整参考答案，不应该在考场转化卡里泄露。" in html


def test_exam_transfer_card_avoids_repeating_candidate_answer_route_words() -> None:
    brief = _sample_brief()
    brief["daily_question"]["candidate_answer"] = (
        "我认为，关键是围绕平台准入、平台执法、平台协同和闭环反馈四个环节逐项推进，"
        "把平台规则、执法检查和闭环机制全部接起来。"
    )
    brief["policy_coordinate"]["exam_transfer"] = "适合从平台准入、平台执法、平台协同和闭环反馈四步展开。"
    brief["exam_transfer_card"] = {
        "exam_expression": "答题时就按平台准入、平台执法、平台协同和闭环反馈四步展开。"
    }

    card = build_exam_transfer_card(brief)

    assert "平台准入、平台执法、平台协同和闭环反馈四步展开" not in card["exam_transfer"]
    assert "平台准入、平台执法、平台协同和闭环反馈四步展开" not in card["exam_expression"]

from __future__ import annotations

from copy import deepcopy

from fact_evidence import (
    build_evidence_bundle,
    build_fact_review,
    build_source_evidence,
    candidate_content_hash,
    candidate_fact_hash,
    fact_review_binding_is_current,
    normalize_selection_scores,
    revalue_selection_scores,
    source_bound_candidate_payload,
)
from article_filter import Article
from prompt_templates import build_final_generation_prompt
from quality_gate import build_gate_from_quality_map
from candidate_store import build_candidate_payload
from email_renderer import render_plain_text
from lite_email_renderer import render_lite_email
from brief_schema import ensure_brief_schema


SOURCE_PARAGRAPHS = [
    "专项治理开展以来，当地通过宣传引导、村规民约和公共服务协同推进，农村婚俗治理已经取得阶段性成效，群众对文明婚俗的认同逐步增强。",
    "调查同时表明，部分地方高额彩礼问题仍然突出，成因涉及传统观念、婚恋压力和公共服务不足，需要持续耐心治理，不能依靠一阵风。",
    "文章认为，治理既要明确底线，也要尊重群众意愿，通过基层协商、典型示范和服务保障改变观念，避免简单化处理带来新的矛盾。",
    "有关措施仍处在逐步完善过程中，未来可能根据实际情况调整服务方式，并通过常态化宣传和跟踪反馈巩固已有成效。",
]


def _article() -> Article:
    article = Article(
        title="杜绝农村高额彩礼不靠一阵清",
        url="https://www.news.cn/example/fact-check.html",
        source="新华社",
        column="新华时评",
        body=SOURCE_PARAGRAPHS,
    )
    article.date = __import__("datetime").date(2026, 9, 3)
    article.evidence = build_source_evidence(
        title=article.title,
        listing_title=article.title,
        page_title=article.title,
        source=article.source,
        published_at=article.published_at,
        url=article.url,
        paragraphs=article.body,
    )
    return article


def _brief(summary: str) -> dict:
    article = _article()
    return {
        "featured_article": {
            "title": article.title,
            "url": article.url,
            "one_sentence": summary,
            "core_viewpoint": "治理需要常态化服务和耐心引导。",
            "original_overview": ["治理已有成效，但部分地方问题仍然突出。"],
            "article_framework_map": {
                "main_thread": "文章先肯定阶段性成效，再分析仍存问题并提出常态治理方向。",
                "steps": ["说明治理已有阶段性成效。", "指出部分地方问题仍突出。", "提出常态服务与观念引导。"],
            },
        },
        "quick_reads": [],
        "daily_question": {
            "question": "【模拟情境】假如你是某村工作人员，有群众提出可以私下收改口费，你将如何开展沟通与治理？"
        },
        "_source_evidence": build_evidence_bundle([article]),
    }


def test_source_missing_or_summary_only_cannot_pass_as_full_text():
    evidence = build_source_evidence(
        title="只有摘要",
        source="新华社",
        published_at="2026-09-03",
        url="https://www.news.cn/example/summary.html",
        paragraphs=["这是一段很短的摘要，不能证明网页正文已经完整取得。"],
    )
    assert evidence["verification_status"] == "incomplete"
    assert "body_too_short_or_summary_only" in evidence["limitations"]


def test_faithful_source_summary_passes_fact_contract():
    review = build_fact_review(_brief("治理已见成效，但部分地方高额彩礼问题仍然突出，需要持续推进。"))
    assert review["ok"] is True
    assert review["binding"]["source_set_hash"]


def test_partial_remaining_is_not_allowed_to_become_universal_relapse():
    review = build_fact_review(_brief("专项整治后高额彩礼已经普遍回潮并全面反弹。"))
    assert review["ok"] is False
    issue = next(item for item in review["issues"] if item["code"] == "unsupported_scope_and_recurrence_upgrade")
    assert issue["field"] == "brief.featured_article"
    assert issue["source_locator"].startswith("p")
    assert issue["repair_target"]


def test_new_number_or_unit_is_flagged_for_review():
    review = build_fact_review(_brief("治理后有80%的农户已经完成整改。"))
    assert any(item["code"] == "candidate_number_not_found_in_source" for item in review["issues"])
    assert review["status"] == "review"


def test_possible_is_not_silently_upgraded_to_already():
    review = build_fact_review(_brief("相关服务方式已经实施并已完成调整。"))
    issue = next(item for item in review["issues"] if item["code"] == "certainty_upgrade_needs_semantic_review")
    assert issue["severity"] == "medium"
    assert issue["source_locator"].startswith("p")
    assert "复核" in issue["judgment"]


def test_marked_simulation_does_not_contaminate_source_bound_fields():
    review = build_fact_review(_brief("治理已有成效，但部分地方问题仍然突出。"))
    assert all(item["code"] != "unsupported_scope_and_recurrence_upgrade" for item in review["issues"])
    assert "改口费" not in str(source_bound_candidate_payload(_brief("治理已有成效，但部分地方问题仍然突出。")))


def test_source_or_candidate_change_invalidates_old_review_binding():
    brief = _brief("治理已有成效，但部分地方问题仍然突出。")
    review = build_fact_review(brief)
    assert fact_review_binding_is_current(brief, review)
    changed = deepcopy(brief)
    changed["featured_article"]["one_sentence"] = "改写后的候选摘要。"
    assert not fact_review_binding_is_current(changed, review)
    changed_source = deepcopy(brief)
    changed_source["_source_evidence"]["source_set_hash"] = "different"
    assert not fact_review_binding_is_current(changed_source, review)
    changed_simulation = deepcopy(brief)
    changed_simulation["daily_question"]["question"] = "【模拟情境】候选题正文也发生了变化。"
    assert candidate_fact_hash(changed_simulation) == candidate_fact_hash(brief)
    assert candidate_content_hash(changed_simulation) != candidate_content_hash(brief)
    assert not fact_review_binding_is_current(changed_simulation, review)


def test_selection_score_uses_detail_sum_and_keeps_history():
    selection = {
        "featured": {
            "title": "文章",
            "url": "https://www.news.cn/a.html",
            "total_score": 88,
            "score_detail": {
                "exam_conversion": 15,
                "problem_awareness": 10,
                "scenario_specificity": 8,
                "contradiction_tension": 7,
                "material_value": 5,
                "authority_timeliness": 4,
            },
            "risk_note": "原文机制信息有限",
        }
    }
    normalized = normalize_selection_scores(selection)
    featured = normalized["featured"]
    assert featured["total_score"] == 49
    assert featured["score_history"][0]["supplied_total"] == 88
    assert featured["score_history"][0]["effective_total"] == 49
    assert featured["score_source"] == "_llm_two_stage.selection.featured"


def test_revaluation_requires_new_source_evidence_and_keeps_old_version():
    first = normalize_selection_scores(
        {
            "featured": {
                "total_score": 49,
                "score_detail": {"exam_conversion": 15, "problem_awareness": 10, "scenario_specificity": 8, "contradiction_tension": 7, "material_value": 5, "authority_timeliness": 4},
            }
        },
        evidence_fingerprint="old-source",
    )
    try:
        revalue_selection_scores(
            first,
            score_detail={"exam_conversion": 20, "problem_awareness": 15, "scenario_specificity": 10, "contradiction_tension": 10, "material_value": 7, "authority_timeliness": 8},
            reason="same source",
            evidence_fingerprint="old-source",
        )
        assert False, "same evidence must not permit revaluation"
    except ValueError:
        pass
    revised = revalue_selection_scores(
        first,
        score_detail={"exam_conversion": 20, "problem_awareness": 15, "scenario_specificity": 10, "contradiction_tension": 10, "material_value": 7, "authority_timeliness": 8},
        reason="previous fetch omitted two source paragraphs",
        evidence_fingerprint="new-source",
    )
    assert revised["featured"]["total_score"] == 70
    assert len(revised["featured"]["score_history"]) == 2
    assert revised["featured"]["score_history"][0]["effective_total"] == 49


def test_fact_failure_is_a_real_gate_p0():
    fact = build_fact_review(_brief("专项整治后高额彩礼已经普遍回潮并全面反弹。"))
    gate = build_gate_from_quality_map({"fact_consistency": fact})
    assert gate["overall"] == "fail"
    assert any(item["code"] == "unsupported_scope_and_recurrence_upgrade" for item in gate["p0_issues"])


def test_generation_prompt_contains_traceable_source_but_no_extra_call_contract():
    article = _article()
    prompt = build_final_generation_prompt([article], "2026-09-05", {"featured": {"url": article.url}})
    assert "source_evidence" in prompt
    assert "content_fingerprint" in prompt
    assert "问题仍存在”改成“治理后复发/回潮" in prompt
    assert "内部 source_evidence" in prompt


def test_candidate_persists_evidence_and_internal_fields_do_not_render():
    brief = _brief("治理已有成效，但部分地方问题仍然突出。")
    brief["email_subject"] = "【公考晨读】事实核验测试"
    brief["today_theme"] = "基层治理"
    brief["today_three_things"] = {}
    brief["today_takeaway"] = {}
    brief, _ = ensure_brief_schema(brief, "2026-09-06")
    plain = render_plain_text(brief)
    lite = render_lite_email({"brief": brief, "subject": brief["email_subject"]})
    # Renderers may normalize reader-facing fields; bind only after that final form exists.
    brief["_fact_review"] = build_fact_review(brief)
    assert "source_set_hash" not in plain
    assert "content_fingerprint" not in plain
    assert "source_set_hash" not in lite["plain_text"]
    assert "content_fingerprint" not in lite["html_body"]
    payload = build_candidate_payload(
        delivery_date="2026-09-06",
        subject=brief["email_subject"],
        brief=brief,
        plain_text=plain,
        html_body="<html></html>",
        quality={"final": {"fact_consistency": brief["_fact_review"]}},
        quality_gate={"overall": "ok", "p0_count": 0, "p0_issues": []},
        article_stats={},
        final_selection={},
    )
    assert payload["source_evidence"]["source_set_hash"] == brief["_source_evidence"]["source_set_hash"]
    assert payload["fact_review"]["binding"]["candidate_fact_hash"] == candidate_fact_hash(brief)
    assert payload["fact_review"]["binding"]["candidate_content_hash"] == candidate_content_hash(brief)

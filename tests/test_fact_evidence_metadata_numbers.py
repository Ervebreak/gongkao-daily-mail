from __future__ import annotations

from fact_evidence import build_fact_review


def _brief(*, url: str, one_sentence: str) -> dict:
    evidence = {
        "schema_version": 1,
        "verification_status": "verified",
        "title": "测试文章",
        "listing_title": "测试文章",
        "page_title": "测试文章",
        "source": "人民日报",
        "published_at": "2026-09-14",
        "url": url,
        "fetched_at": "2026-09-14T14:00:00+00:00",
        "fetch_attempts": 1,
        "content_fingerprint": "source-fingerprint",
        "paragraph_count": 3,
        "body_chars": 240,
        "paragraphs": [
            {"id": "p001", "text": "文章说明治理工作需要围绕真实问题推进，不能脱离岗位需求扩大信息采集范围。"},
            {"id": "p002", "text": "相关主体应当核验信息来源和事实依据，并为当事人保留异议、更正和投诉渠道。"},
            {"id": "p003", "text": "治理重点是明确边界、规范流程并完善救济机制，使风险识别保持必要、真实和可核验。"},
        ],
        "identity_checks": {
            "title_matches_page": True,
            "source_matches_url": True,
            "url_valid": True,
            "published_date_present": True,
        },
        "completeness_checks": {
            "enough_paragraphs": True,
            "enough_chars": True,
            "ending_confirmed": True,
            "boilerplate_not_dominant": True,
            "http_success_is_not_completeness_proof": True,
        },
        "limitations": [],
    }
    bundle = {
        "schema_version": 1,
        "items": {url: evidence},
        "source_set_hash": "source-set-hash",
        "all_verified": True,
    }
    return {
        "featured_article": {
            "title": "测试文章",
            "url": url,
            "one_sentence": one_sentence,
            "core_viewpoint": "治理应保持必要、真实和可核验。",
            "original_overview": ["文章讨论信息核验边界和异议救济。"],
            "article_framework": ["明确边界。", "规范流程。", "完善救济。"],
            "article_framework_map": {
                "main_thread": "从信息核验边界切入，再讨论流程和救济。",
                "steps": ["明确边界。", "规范流程。", "完善救济。"],
            },
        },
        "quick_reads": [],
        "_source_evidence": bundle,
    }


def test_url_date_and_article_id_numbers_do_not_trigger_fact_number_review() -> None:
    brief = _brief(
        url="https://paper.people.com.cn/rmrb/pc/content/202609/14/content_30180864.html",
        one_sentence="文章讨论信息核验边界、流程规范和异议救济。",
    )

    review = build_fact_review(brief)

    assert review["status"] == "ok"
    assert review["issues"] == []


def test_reader_facing_number_not_in_source_is_still_flagged() -> None:
    brief = _brief(
        url="https://paper.people.com.cn/rmrb/pc/content/202609/14/content_30180864.html",
        one_sentence="文章称80%的相关主体已经完成整改。",
    )

    review = build_fact_review(brief)

    assert review["status"] == "review"
    assert any(
        issue.get("code") == "candidate_number_not_found_in_source" and "80%" in issue.get("message", "")
        for issue in review["issues"]
    )

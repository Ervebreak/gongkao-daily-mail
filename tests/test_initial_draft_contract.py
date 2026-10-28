from __future__ import annotations

from article_filter import Article
import llm_client


def test_two_stage_initial_draft_defers_submodule_contract_to_refinement(monkeypatch) -> None:
    """A flawed intermediate takeaway must reach targeted regeneration."""
    article = Article(
        title="测试文章",
        url="https://example.com/article",
        source="人民日报",
        column="要闻",
        body=["测试正文。"],
    )
    calls: list[dict] = []
    draft = {
        "featured_article": {"title": article.title, "url": article.url},
        "today_takeaway": {
            "golden_sentences": [
                {"sentence": "完整金句。", "scenario": "用于申论结尾。"},
                {"sentence": "带省略号的初稿……", "scenario": "等待定点重写。"},
            ],
            "framework": "初稿框架……",
        },
    }

    def fake_call(prompt, test_mode, stage="writing", *, contract=True):
        calls.append({"stage": stage, "contract": contract})
        return {} if stage == "selection" else draft

    refinement_seen: list[dict] = []

    def fake_refine(brief, articles, test_mode=False, max_attempts=2):
        refinement_seen.append(brief)
        return brief

    monkeypatch.setattr(llm_client, "_call_with_fallback", fake_call)
    monkeypatch.setattr(llm_client, "normalize_selection_scores", lambda *args, **kwargs: {})
    monkeypatch.setattr(llm_client, "_resolve_selected_articles", lambda *args, **kwargs: [article])
    monkeypatch.setattr(llm_client, "_question_bank_context_for_article", lambda *args, **kwargs: ([], {}, {}))
    monkeypatch.setattr(llm_client, "build_selection_prompt", lambda *args, **kwargs: "selection")
    monkeypatch.setattr(llm_client, "build_final_generation_prompt", lambda *args, **kwargs: "draft")
    monkeypatch.setattr(llm_client, "build_evidence_bundle", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        llm_client,
        "select_best_daily_question_candidate",
        lambda brief, *args, **kwargs: {"brief": brief, "candidates": [], "fallback_used": False},
    )
    monkeypatch.setattr(llm_client, "refine_high_risk_modules", fake_refine)

    result = llm_client.generate_brief_two_stage([article], "2026-10-29")

    assert calls[1] == {"stage": "writing", "contract": False}
    assert refinement_seen and refinement_seen[0]["today_takeaway"]["framework"] == "初稿框架……"
    assert result["today_takeaway"]["framework"] == "初稿框架……"

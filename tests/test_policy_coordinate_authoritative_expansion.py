import policy_coordinate_matcher as matcher


def test_matcher_expands_authoritative_candidates_from_matched_article_context(monkeypatch):
    monkeypatch.setattr(matcher, "load_policy_core", lambda: [])
    monkeypatch.setattr(matcher, "load_policy_all", lambda: [])
    monkeypatch.setattr(
        matcher,
        "load_qiushi_article_index",
        lambda: [
            {
                "article_id": "article-1",
                "title": "树立和践行正确政绩观",
                "main_theme": "政绩观",
                "sub_themes": ["面子工程", "群众监督"],
                "status": "active",
                "display_priority": 8,
            }
        ],
    )
    monkeypatch.setattr(
        matcher,
        "load_qiushi_chunks",
        lambda: [
            {
                "chunk_id": "chunk-1",
                "article_id": "article-1",
                "title": "树立和践行正确政绩观",
                "section_title": "纠治偏差",
                "chunk_text": "整改不能停留在遮丑和应付检查，必须纠治面子工程，接受群众监督。",
                "theme_tags": ["政绩观", "面子工程"],
                "display_ready": True,
            }
        ],
    )
    monkeypatch.setattr(
        matcher,
        "load_topic_frameworks",
        lambda: [
            {
                "framework_id": "framework-1",
                "article_id": "article-1",
                "framework_name": "纠治面子工程",
                "framework_items": ["纠治面子工程", "接受群众监督"],
                "answer_pattern": "从政绩观偏差切入",
                "theme": "政绩观",
                "display_ready": True,
            }
        ],
    )

    strong_quotes = []
    for index in range(10):
        strong_quotes.append(
            {
                "quote_id": f"quote-{index}",
                "article_id": f"other-{index}",
                "quote_text": f"面子工程 整改 群众监督 {index}",
                "short_quote": f"面子工程 整改 群众监督 {index}",
                "source_title": f"Other Source {index}",
                "theme_level_1": "政绩观",
                "display_ready": True,
                "theme_confidence": "high",
                "usage_tier": "display",
                "display_priority": 2,
            }
        )
    target_quote = {
        "quote_id": "quote-target",
        "article_id": "article-1",
        "quote_text": "重面子轻里子，不能把整改做成表面文章。",
        "short_quote": "重面子轻里子。",
        "source_title": "树立和践行正确政绩观",
        "theme_level_1": "政绩观",
        "display_ready": True,
        "theme_confidence": "high",
        "usage_tier": "display",
        "display_priority": 0,
    }
    monkeypatch.setattr(matcher, "load_qiushi_quotes_core", lambda: strong_quotes + [target_quote])
    monkeypatch.setattr(matcher, "load_qiushi_quotes_candidates", lambda: [])

    result = matcher.match_policy_coordinate_candidates(
        article_title="“遮丑”何以变“揭丑”",
        article_summary="文章批评遮丑式整改、应付检查和面子工程，强调接受群众监督。",
        article_text="遮丑、应付检查、面子工程、群众监督、正确政绩观。",
        main_theme="政绩观",
        sub_themes=["面子工程", "群众监督"],
        keywords=["遮丑", "应付检查", "面子工程", "群众监督"],
        exam_scenarios=["综合分析"],
    )["matched_policy_coordinate_candidates"]

    debug_scores = result["debug_scores"]
    authoritative_candidates = debug_scores["authoritative_candidates_top10"]
    target_rows = [row for row in authoritative_candidates if row.get("quote_id") == "quote-target"]

    assert debug_scores["expanded_authoritative_article_ids"] == ["article-1"]
    assert debug_scores["expanded_authoritative_quote_count"] >= 1
    assert "quote-target" in debug_scores["expanded_authoritative_quote_ids"]
    assert target_rows
    assert target_rows[0]["_match_reasons"]["expanded_from_article_id"] == "article-1"

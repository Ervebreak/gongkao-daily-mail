import policy_coordinate_matcher as matcher


def test_multi_query_merges_specific_authoritative_quote_into_candidates(monkeypatch):
    generic_result = {
        "matched_policy_coordinate_candidates": {
            "best_policy": {"policy_id": "policy-generic", "_match_score": 61.0},
            "best_qiushi_quote": {"quote_id": "quote-generic", "_match_score": 66.0},
            "matched_chunks": [],
            "best_framework": {},
            "debug_scores": {
                "authoritative_candidates_top10": [
                    {"quote_id": "quote-generic", "_match_score": 66.0, "_match_source": "qiushi_quotes_core"}
                ],
                "policy_statement_candidates_top10": [
                    {"policy_id": "policy-generic", "_match_score": 61.0, "_match_source": "policy_core"}
                ],
                "best_article_index": [],
                "chunk_top": [],
                "framework_top": [],
                "final_source_priority_decision": "authoritative_quote_selected",
            },
        }
    }
    specific_result = {
        "matched_policy_coordinate_candidates": {
            "best_policy": {"policy_id": "policy-specific", "_match_score": 62.0},
            "best_qiushi_quote": {
                "quote_id": "quote-specific",
                "_match_score": 64.5,
                "_match_source": "qiushi_quotes_core",
                "quote_text": "重面子轻里子，不能把整改做成表面文章。",
            },
            "matched_chunks": [],
            "best_framework": {},
            "debug_scores": {
                "authoritative_candidates_top10": [
                    {
                        "quote_id": "quote-specific",
                        "_match_score": 64.5,
                        "_match_source": "qiushi_quotes_core",
                        "quote_text": "重面子轻里子，不能把整改做成表面文章。",
                    }
                ],
                "policy_statement_candidates_top10": [
                    {"policy_id": "policy-specific", "_match_score": 62.0, "_match_source": "policy_core"}
                ],
                "best_article_index": [{"article_id": "article-1", "_match_score": 70.0}],
                "chunk_top": [{"chunk_id": "chunk-1", "_match_score": 69.0, "article_id": "article-1"}],
                "framework_top": [{"framework_id": "framework-1", "_match_score": 68.0, "article_id": "article-1"}],
                "final_source_priority_decision": "authoritative_quote_selected",
            },
        }
    }

    calls = []

    def fake_match_policy_coordinate_candidates(**kwargs):
        calls.append(kwargs)
        if kwargs.get("article_summary") == "正确政绩观 面子工程":
            return specific_result
        return generic_result

    monkeypatch.setattr(matcher, "match_policy_coordinate_candidates", fake_match_policy_coordinate_candidates)

    merged = matcher.match_policy_coordinate_candidates_multi_query(
        article_title="“遮丑”何以变“揭丑”",
        article_summary="围绕整改与群众监督展开",
        article_text="原文正文",
        main_theme="政绩观",
        sub_themes=["群众监督"],
        keywords=["基层治理"],
        exam_scenarios=["综合分析"],
        retrieval_queries=["基层治理", "正确政绩观 面子工程"],
    )["matched_policy_coordinate_candidates"]

    debug_scores = merged["debug_scores"]
    assert len(calls) == 3
    specific_call = next(call for call in calls if call.get("article_summary") == "正确政绩观 面子工程")
    assert "正确政绩观" in specific_call["keywords"]
    assert "面子工程" in specific_call["keywords"]
    assert "正确政绩观 面子工程" in specific_call["keywords"]
    assert debug_scores["multi_query_enabled"] is True
    assert debug_scores["retrieval_query_count"] == 2
    assert debug_scores["retrieval_queries_used"] == ["基层治理", "正确政绩观 面子工程"]
    assert "quote-specific" in {
        item["quote_id"] for item in debug_scores["authoritative_candidates_top10"] if item.get("quote_id")
    }
    assert debug_scores["merged_authoritative_count"] >= 2
    assert debug_scores["per_query_authoritative_top_ids"][1]["quote_ids"] == ["quote-specific"]


def test_multi_query_falls_back_to_single_match_when_queries_missing(monkeypatch):
    sentinel = {
        "matched_policy_coordinate_candidates": {
            "best_policy": {},
            "best_qiushi_quote": {},
            "matched_chunks": [],
            "best_framework": {},
            "debug_scores": {
                "authoritative_candidates_top10": [],
                "policy_statement_candidates_top10": [],
            },
        }
    }
    calls = []

    def fake_match_policy_coordinate_candidates(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(matcher, "match_policy_coordinate_candidates", fake_match_policy_coordinate_candidates)

    result = matcher.match_policy_coordinate_candidates_multi_query(
        article_title="test",
        retrieval_queries=[],
    )

    debug_scores = result["matched_policy_coordinate_candidates"]["debug_scores"]
    assert len(calls) == 1
    assert debug_scores["multi_query_enabled"] is False
    assert debug_scores["retrieval_query_count"] == 0


def test_query_keywords_split_compound_query():
    keywords = matcher._query_keywords("正确政绩观 面子工程")

    assert "正确政绩观 面子工程" in keywords
    assert "正确政绩观" in keywords
    assert "面子工程" in keywords

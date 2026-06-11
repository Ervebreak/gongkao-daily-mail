from main import _policy_coordinate_debug_payload


def test_policy_coordinate_debug_payload_contains_required_fields():
    payload = _policy_coordinate_debug_payload(
        featured={"title": "示例文章", "source": "人民日报"},
        article_text="A" * 620,
        topic_query_text="平台治理 闭环落实",
        topic_anchors={"primary_theme": "平台治理", "fine_grained_tags": ["闭环落实"]},
        debug_scores={
            "query": {"main_theme": "平台治理"},
            "policy_core_top": [
                {
                    "policy_id": "policy-1",
                    "_match_source": "policy_core",
                    "_match_score": 72.4,
                    "theme_level_1": "平台治理",
                    "source_title": "条例一",
                    "short_quote": "强化平台责任。",
                }
            ],
            "policy_all_top": [],
            "qiushi_quotes_core_top": [],
            "qiushi_quotes_candidates_top": [],
            "chunk_top": [],
            "framework_top": [],
        },
        result={
            "display_evidence_type": "policy",
            "matched_qiushi_quote_id": "",
            "matched_policy_id": "policy-1",
            "policy_match_score": 72.4,
            "qiushi_match_score": 0,
            "evidence_selection_reason": "policy stronger",
        },
        backend_status="ok",
        semantic_fit={"status": "ok"},
        disabled_reason="",
    )

    assert payload["article_title"] == "示例文章"
    assert payload["article_source"] == "人民日报"
    assert payload["article_text_length"] == 620
    assert payload["article_text_preview"].endswith("...")
    assert payload["selected_evidence_type"] == "policy"
    assert payload["selected_policy_id"] == "policy-1"
    assert payload["policy_score"] == 72.4
    assert "policy_core_top5" in payload
    assert payload["policy_core_top5"][0]["policy_id"] == "policy-1"

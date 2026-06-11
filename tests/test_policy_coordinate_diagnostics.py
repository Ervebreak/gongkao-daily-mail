from main import (
    _policy_coordinate_backend_status,
    _policy_coordinate_debug_payload,
    _policy_coordinate_display_fields,
)


def test_policy_coordinate_debug_payload_contains_required_fields():
    payload = _policy_coordinate_debug_payload(
        featured={"title": "Sample Article", "source": "People Daily"},
        article_text="A" * 620,
        topic_query_text="platform governance closed-loop delivery",
        topic_anchors={"primary_theme": "platform governance", "fine_grained_tags": ["closed-loop delivery"]},
        debug_scores={
            "query": {"main_theme": "platform governance"},
            "policy_core_top": [
                {
                    "policy_id": "policy-1",
                    "_match_source": "policy_core",
                    "_match_score": 72.4,
                    "theme_level_1": "platform governance",
                    "source_title": "Policy One",
                    "short_quote": "Strengthen platform accountability.",
                }
            ],
            "policy_all_top": [],
            "qiushi_quotes_core_top": [],
            "qiushi_quotes_candidates_top": [],
            "authoritative_candidates_top10": [
                {
                    "quote_id": "quote-1",
                    "_match_source": "qiushi_quotes_core",
                    "_match_score": 75.0,
                    "source_title": "Qiushi",
                    "short_quote": "Persist in problem-oriented governance.",
                }
            ],
            "policy_statement_candidates_top10": [
                {
                    "policy_id": "policy-1",
                    "_match_source": "policy_core",
                    "_match_score": 72.4,
                    "source_title": "Policy One",
                    "short_quote": "Strengthen platform accountability.",
                }
            ],
            "final_source_priority_decision": "authoritative_quote_selected_over_policy_fallback",
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

    assert payload["article_title"] == "Sample Article"
    assert payload["article_source"] == "People Daily"
    assert payload["article_text_length"] == 620
    assert payload["article_text_preview"].endswith("...")
    assert payload["selected_evidence_type"] == "policy"
    assert payload["selected_policy_id"] == "policy-1"
    assert payload["policy_score"] == 72.4
    assert payload["policy_core_top5"][0]["policy_id"] == "policy-1"
    assert payload["authoritative_candidates_top10"][0]["quote_id"] == "quote-1"
    assert payload["policy_statement_candidates_top10"][0]["policy_id"] == "policy-1"
    assert payload["final_source_priority_decision"] == "authoritative_quote_selected_over_policy_fallback"


def test_policy_coordinate_display_prefers_authoritative_quote():
    display = _policy_coordinate_display_fields(
        policy_quote="Policy fallback",
        policy_source="Policy source",
        authoritative_quote="Authoritative quote",
        authoritative_source="Qiushi",
        policy_score=83.0,
        qiushi_score=84.0,
    )

    assert display["display_evidence_type"] == "qiushi"


def test_policy_coordinate_display_falls_back_to_policy_statement():
    display = _policy_coordinate_display_fields(
        policy_quote="Policy fallback",
        policy_source="Policy source",
        authoritative_quote="Authoritative quote",
        authoritative_source="Qiushi",
        policy_score=68.0,
        qiushi_score=58.0,
    )

    assert display["display_evidence_type"] == "policy"


def test_policy_coordinate_backend_status_respects_authoritative_threshold():
    status, reason = _policy_coordinate_backend_status(
        {
            "display_evidence_type": "qiushi",
            "source_type": "qiushi_only",
            "policy_match_score": 70.0,
            "qiushi_match_score": 59.0,
        }
    )

    assert status == "skipped"
    assert "qiushi_only" in reason

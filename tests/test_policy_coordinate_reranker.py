import policy_coordinate_reranker as reranker
from email_renderer import should_render_policy_coordinate


def test_reranker_hides_generic_authoritative_match(monkeypatch):
    def fake_chat_completion(*args, **kwargs):
        return {
            "selected_id": "quote-1",
            "fit_score": 81,
            "reason": "Related to grassroots governance.",
            "article_connection": "It generally relates to grassroots governance and service mechanisms.",
            "exam_transfer": "Use for governance topics.",
            "display_level": "A",
        }

    monkeypatch.setattr(reranker, "chat_completion", fake_chat_completion)
    result = reranker.rerank_policy_coordinate_candidates(
        article_title="Why cover-up turns into expose-up",
        policy_profile={
            "core_problem": "cover-up, face projects, inspection-oriented response",
            "governance_logic": "public supervision and systematic rectification",
            "value_orientation": "people-centered accountability",
            "negative_behaviors": ["cover-up", "face project"],
            "positive_behaviors": ["public supervision"],
            "fine_anchors": ["cover-up", "face project"],
        },
        article_summary="The article criticizes cover-up logic, face projects, and inspection-oriented response.",
        candidate_quotes=[
            {
                "quote_id": "quote-1",
                "quote_text": "Persist in improving grassroots governance mechanisms.",
                "source_title": "Qiushi",
                "_match_score": 88,
            }
        ],
        candidate_family="authoritative_quote",
    )

    assert result["display_level"] == "hidden"
    assert result["hidden_reason"].startswith("article_connection_")


def test_should_render_policy_coordinate_uses_stage4_thresholds():
    assert (
        should_render_policy_coordinate(
            {
                "policy_coordinate": {
                    "display_evidence_type": "qiushi",
                    "source_type": "qiushi_only",
                    "display_level": "a",
                    "qiushi_match_score": 69,
                    "answer_angles": [],
                }
            }
        )
        is False
    )
    assert (
        should_render_policy_coordinate(
            {
                "policy_coordinate": {
                    "display_evidence_type": "policy",
                    "source_type": "policy_only",
                    "display_level": "b",
                    "policy_match_score": 75,
                    "answer_angles": [],
                }
            }
        )
        is True
    )

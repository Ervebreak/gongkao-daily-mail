from __future__ import annotations

from main import summarize_llm_trace
from token_economics import estimate_text_tokens, summarize_token_usage


def test_estimate_text_tokens_handles_chinese_and_ascii() -> None:
    assert estimate_text_tokens("基层治理") > 0
    assert estimate_text_tokens("public service") > 0
    assert estimate_text_tokens("") == 0


def test_summarize_token_usage_and_llm_trace() -> None:
    events = [
        {"event": "llm_request_start", "stage": "selection", "model": "qwen-a"},
        {"event": "llm_stage_attempt_succeeded", "stage": "selection", "model": "qwen-a"},
        {
            "event": "llm_token_usage",
            "stage": "selection",
            "model": "qwen-a",
            "estimated_prompt_tokens": 120,
            "estimated_response_tokens": 30,
            "fallback_used": False,
        },
        {
            "event": "llm_token_usage",
            "stage": "policy_coordinate_rerank",
            "model": "qwen-b",
            "estimated_prompt_tokens": 80,
            "estimated_response_tokens": 20,
            "fallback_used": True,
        },
    ]

    token_summary = summarize_token_usage(events)
    assert token_summary["llm_call_count"] == 2
    assert token_summary["estimated_total_tokens"] == 250
    assert token_summary["selection_tokens"] == 150
    assert token_summary["policy_rerank_tokens"] == 100
    assert token_summary["fallback_count"] == 1

    llm_summary = summarize_llm_trace(events)
    assert llm_summary["selection"]["llm_call_count"] == 1
    assert llm_summary["selection"]["estimated_total_tokens"] == 150
    assert llm_summary["_token_economics"]["estimated_total_tokens"] == 250

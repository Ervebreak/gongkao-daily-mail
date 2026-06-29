from __future__ import annotations

import math
import re
from typing import Any


_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]")


def estimate_text_tokens(text: Any) -> int:
    value = str(text or "")
    if not value:
        return 0
    chinese_chars = len(_CHINESE_RE.findall(value))
    ascii_chars = len(_ASCII_WORD_RE.findall(value))
    other_chars = max(len(value) - chinese_chars - ascii_chars, 0)
    estimated = (chinese_chars / 1.5) + (ascii_chars / 4.0) + (other_chars / 3.0)
    return max(0, int(math.ceil(estimated)))


def classify_stage_bucket(stage: Any) -> str:
    name = str(stage or "").strip().lower()
    if not name:
        return "other"
    if "policy_coordinate_rerank" in name or "policy_rerank" in name:
        return "policy_rerank_tokens"
    if "lite_paid_cta" in name:
        return "lite_cta_tokens"
    if "rewrite" in name:
        return "rewrite_tokens"
    if name == "selection" or "candidate_selection" in name or "question_candidate" in name:
        return "selection_tokens"
    if "weekly_material_curator" in name or name == "writing":
        return "writing_tokens"
    return "other"


def summarize_token_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "llm_call_count": 0,
        "estimated_total_tokens": 0,
        "selection_tokens": 0,
        "writing_tokens": 0,
        "rewrite_tokens": 0,
        "policy_rerank_tokens": 0,
        "lite_cta_tokens": 0,
        "fallback_count": 0,
    }
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "llm_token_usage":
            continue
        prompt_tokens = int(event.get("estimated_prompt_tokens") or 0)
        response_tokens = int(event.get("estimated_response_tokens") or 0)
        total = prompt_tokens + response_tokens
        summary["llm_call_count"] += 1
        summary["estimated_total_tokens"] += total
        if event.get("fallback_used"):
            summary["fallback_count"] += 1
        bucket = classify_stage_bucket(event.get("stage"))
        if bucket in summary:
            summary[bucket] += total
    return summary

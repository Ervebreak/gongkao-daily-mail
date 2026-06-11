from __future__ import annotations

from typing import Any


ARTICLE_FINE_TERMS = [
    "基层减负",
    "形式主义",
    "留痕",
    "过度留痕",
    "层层加码",
    "问责",
    "考核",
    "考核纠偏",
    "容错",
    "抓落实",
]

EVIDENCE_FIT_TERMS = [
    "形式主义",
    "基层减负",
    "作风建设",
    "过度留痕",
    "留痕",
    "层层加码",
    "考核",
    "问责",
    "容错",
    "抓落实",
]

GENERIC_OVERLAP_TERMS = ["基层", "治理", "服务", "机制", "落实"]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if _text(item)).strip()
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value if _text(item)).strip()
    return " ".join(str(value).split()).strip()


def _compact(value: Any) -> str:
    return _text(value).replace(" ", "")


def _hits(text: str, terms: list[str]) -> list[str]:
    compact_text = _compact(text)
    return [term for term in terms if term and term in compact_text]


def _anchor_specific_terms(article_anchors: Any) -> list[str]:
    values: list[str] = []
    if isinstance(article_anchors, dict):
        fine_grained = article_anchors.get("fine_grained_tags")
        if isinstance(fine_grained, (list, tuple, set)):
            values.extend(_text(item) for item in fine_grained)
        values.extend(
            _text(article_anchors.get(key))
            for key in ("query_text", "primary_theme", "policy_profile_query")
        )
    else:
        values.append(_text(article_anchors))
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        candidate = value.strip()
        compact_candidate = _compact(candidate)
        if len(compact_candidate) < 4 or compact_candidate in seen or candidate in GENERIC_OVERLAP_TERMS:
            continue
        seen.add(compact_candidate)
        terms.append(candidate)
    return terms


def _evidence_text(policy_coordinate: dict[str, Any]) -> str:
    return _text(
        [
            policy_coordinate.get("policy_quote"),
            policy_coordinate.get("authoritative_quote"),
            policy_coordinate.get("display_evidence_quote"),
            policy_coordinate.get("policy_translation"),
            policy_coordinate.get("article_connection"),
            policy_coordinate.get("exam_transfer"),
            policy_coordinate.get("theme"),
        ]
    )


def policy_match_semantic_fit(article_anchors: Any, policy_coordinate: dict[str, Any]) -> dict[str, Any]:
    anchor_text = _text(article_anchors)
    evidence_text = _evidence_text(policy_coordinate)
    anchor_hits = _hits(anchor_text, ARTICLE_FINE_TERMS)
    evidence_hits = _hits(evidence_text, EVIDENCE_FIT_TERMS)
    generic_hits = _hits(evidence_text, GENERIC_OVERLAP_TERMS)
    specific_anchor_hits = _hits(evidence_text, _anchor_specific_terms(article_anchors))
    source_type = _text(policy_coordinate.get("source_type")).lower()

    if not anchor_hits:
        return {
            "display": True,
            "status": "ok",
            "reason": "",
            "anchor_hits": [],
            "evidence_hits": evidence_hits,
            "generic_hits": generic_hits,
            "specific_anchor_hits": specific_anchor_hits,
        }

    if evidence_hits or specific_anchor_hits:
        return {
            "display": True,
            "status": "ok",
            "reason": "",
            "anchor_hits": anchor_hits,
            "evidence_hits": evidence_hits or specific_anchor_hits,
            "generic_hits": generic_hits,
            "specific_anchor_hits": specific_anchor_hits,
        }

    if source_type == "policy_only" or generic_hits:
        return {
            "display": False,
            "status": "weak_match",
            "reason": (
                "weak_match: policy coordinate only overlaps generic terms "
                f"({', '.join(generic_hits) or 'none'}) without fine-grained anchors "
                f"({', '.join(anchor_hits)})."
            ),
            "anchor_hits": anchor_hits,
            "evidence_hits": [],
            "generic_hits": generic_hits,
            "specific_anchor_hits": specific_anchor_hits,
        }

    return {
        "display": True,
        "status": "ok",
        "reason": "",
        "anchor_hits": anchor_hits,
        "evidence_hits": [],
        "generic_hits": generic_hits,
        "specific_anchor_hits": specific_anchor_hits,
    }


def should_display_policy_match(article_anchors: Any, policy_coordinate: dict[str, Any]) -> bool:
    return bool(policy_match_semantic_fit(article_anchors, policy_coordinate).get("display"))

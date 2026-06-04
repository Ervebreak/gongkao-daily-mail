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
    source_type = _text(policy_coordinate.get("source_type")).lower()

    if not anchor_hits:
        return {
            "display": True,
            "status": "ok",
            "reason": "",
            "anchor_hits": [],
            "evidence_hits": evidence_hits,
            "generic_hits": generic_hits,
        }

    if evidence_hits:
        return {
            "display": True,
            "status": "ok",
            "reason": "",
            "anchor_hits": anchor_hits,
            "evidence_hits": evidence_hits,
            "generic_hits": generic_hits,
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
        }

    return {
        "display": True,
        "status": "ok",
        "reason": "",
        "anchor_hits": anchor_hits,
        "evidence_hits": [],
        "generic_hits": generic_hits,
    }


def should_display_policy_match(article_anchors: Any, policy_coordinate: dict[str, Any]) -> bool:
    return bool(policy_match_semantic_fit(article_anchors, policy_coordinate).get("display"))

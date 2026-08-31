#!/usr/bin/env python3
"""Validate deterministic contract rules for a generated morning-reading candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"(?i)\b(?:none|null|not[_ -]?found|tbd)\b|待补充|第X条")
MATERIAL_DEPENDENCY_RE = re.compile(r"根据(?:上述)?材料|根据给定资料|结合(?:上述)?材料|结合给定资料|给定资料|材料[一二三四五]")
SENTENCE_END_RE = re.compile(r"[。！？.!?）】]$")
SCENARIO_TYPES = ("情景", "实务", "事务处理", "组织管理", "现场模拟")


def get_path(data: dict[str, Any], *paths: tuple[str, ...]) -> tuple[Any, str]:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current not in (None, "", [], {}):
            return current, ".".join(path)
    return None, ".".join(paths[0])


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value in (None, "") else [value]


def text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def add(report: dict[str, Any], level: str, code: str, field: str, message: str) -> None:
    report[level].append({"code": code, "field": field, "message": message})


def inspect_text(report: dict[str, Any], field: str, value: Any) -> None:
    value = text(value).strip()
    if value and PLACEHOLDER_RE.search(value):
        add(report, "errors", "placeholder_visible", field, "contains a visible placeholder.")
    if value and len(value) >= 8 and not SENTENCE_END_RE.search(value):
        add(report, "warnings", "possibly_truncated", field, "does not end with terminal punctuation; review for truncation.")


def validate(data: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = {"errors": [], "warnings": []}
    featured, featured_field = get_path(data, ("featured_article",), ("featured",))
    if not isinstance(featured, dict):
        add(report, "errors", "featured_article_missing", featured_field, "featured article object is required.")
        featured = {}

    for label, paths in {
        "title": (("subject",), ("title",)),
        "featured title": (("featured_article", "title"), ("featured", "title")),
        "featured source": (("featured_article", "source"), ("featured", "source")),
        "featured url": (("featured_article", "url"), ("featured", "url")),
        "featured content": (("featured_article", "content"), ("featured_article", "summary"), ("featured", "content"), ("featured", "summary")),
    }.items():
        value, field = get_path(data, *paths)
        if not text(value).strip():
            add(report, "errors", "required_text_missing", field, f"{label} is required.")
        else:
            inspect_text(report, field, value)

    question, question_field = get_path(data, ("daily_question",))
    if not isinstance(question, dict):
        add(report, "errors", "daily_question_missing", question_field, "daily question object is required.")
        question = {}

    required_question = {
        "question": ("daily_question", "question"),
        "exam focus": ("daily_question", "exam_focus"),
        "answer framework": ("daily_question", "answer_framework"),
        "candidate answer": ("daily_question", "candidate_answer"),
    }
    for label, path in required_question.items():
        value, field = get_path(data, path)
        if value in (None, "", []):
            add(report, "errors", "required_question_field_missing", field, f"{label} is required.")
        elif isinstance(value, str):
            inspect_text(report, field, value)

    question_text, question_text_field = get_path(data, ("daily_question", "question"))
    if text(question_text) and MATERIAL_DEPENDENCY_RE.search(text(question_text)):
        add(report, "errors", "material_dependency", question_text_field, "question depends on materials that are not supplied.")

    framework, framework_field = get_path(data, ("daily_question", "answer_framework"), ("daily_question", "answer_frame"))
    points = [text(item).strip() for item in as_list(framework) if text(item).strip()]
    if points and len(points) not in (3, 4):
        add(report, "warnings", "framework_point_count", framework_field, "answer framework should normally have 3 or 4 points.")
    for index, point in enumerate(points, 1):
        if len(point) > 45:
            add(report, "errors", "framework_point_too_long", f"{framework_field}[{index}]", "framework point exceeds 45 characters.")
        inspect_text(report, f"{framework_field}[{index}]", point)

    qtype, qtype_field = get_path(data, ("daily_question", "question_type"), ("daily_question", "type"))
    if text(qtype) and any(marker in text(qtype) for marker in SCENARIO_TYPES):
        if not re.search(r"你是|作为|现为|担任|某单位", text(question_text)):
            add(report, "warnings", "scenario_identity_unconfirmed", question_text_field, f"{qtype_field} indicates a scenario/practical question but no identity signal was found.")

    takeaway, takeaway_field = get_path(data, ("today_takeaway",), ("takeaway",))
    if not isinstance(takeaway, dict):
        add(report, "errors", "takeaway_missing", takeaway_field, "today takeaway object is required.")
        takeaway = {}

    keywords, keywords_field = get_path(data, ("today_takeaway", "keywords"), ("takeaway", "keywords"))
    keyword_list = [text(item).strip() for item in as_list(keywords) if text(item).strip()]
    if len(keyword_list) not in (2, 3):
        add(report, "warnings", "keyword_count", keywords_field, "takeaway should contain 2 or 3 keywords.")
    for index, item in enumerate(keyword_list, 1):
        if len(item) > 10:
            add(report, "warnings", "keyword_too_long", f"{keywords_field}[{index}]", "keyword exceeds 10 characters.")

    expressions, expressions_field = get_path(data, ("today_takeaway", "golden_sentences"), ("takeaway", "golden_sentences"))
    expression_list = [text(item).strip() for item in as_list(expressions) if text(item).strip()]
    if len(expression_list) != 2:
        add(report, "warnings", "expression_count", expressions_field, "takeaway should contain exactly two expressions.")
    for index, item in enumerate(expression_list, 1):
        if len(item) > 60:
            add(report, "warnings", "expression_too_long", f"{expressions_field}[{index}]", "expression exceeds 60 characters.")
        inspect_text(report, f"{expressions_field}[{index}]", item)

    for field, paths, limit in (
        ("original reading focus", (("featured_article", "original_reading_focus"),), 80),
        ("method framework", (("today_takeaway", "framework"), ("takeaway", "framework")), 50),
    ):
        value, resolved = get_path(data, *paths)
        if text(value):
            if len(text(value)) > limit:
                add(report, "warnings", "text_too_long", resolved, f"{field} exceeds {limit} characters.")
            inspect_text(report, resolved, value)

    quick_reads, quick_reads_field = get_path(data, ("quick_reads",), ("speed_reads",))
    if quick_reads not in (None, "") and len(as_list(quick_reads)) > 2:
        add(report, "warnings", "quick_reads_too_many", quick_reads_field, "at most two quick reads are allowed.")

    report["ok"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--strict", action="store_true", help="return non-zero for warnings too")
    args = parser.parse_args()

    try:
        data = json.loads(args.candidate.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read candidate: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("candidate root must be a JSON object", file=sys.stderr)
        return 2

    report = validate(data)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if report["errors"] or (args.strict and report["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

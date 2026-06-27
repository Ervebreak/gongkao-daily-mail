from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

RUNTIME_PROMPT_RULES_MAX_CHARS = 12000
RUNTIME_PROMPT_RULES_MAX_NONEMPTY_LINES = 220

FIELD_LIMIT_PATTERNS: dict[str, list[dict[str, Any]]] = {
    "daily_question.answer_framework": [
        {
            "label": "max_chars_per_item",
            "regex": re.compile(
                r"answer_framework(?:\s*/\s*answer_frame)?[\s\S]{0,120}?不超过\s*(\d+)\s*字",
                re.IGNORECASE,
            ),
        }
    ],
    "daily_question.thirty_second_answer": [
        {
            "label": "char_range",
            "regex": re.compile(
                r"thirty_second_answer(?:[\"'`\s:：])[\s\S]{0,60}?(\d+)\s*-\s*(\d+)\s*字",
                re.IGNORECASE,
            ),
        }
    ],
    "golden_sentences.sentence": [
        {
            "label": "max_chars_per_item",
            "regex": re.compile(
                r"golden_sentences[\s\S]{0,220}?sentence[\s\S]{0,80}?不超过\s*(\d+)\s*字",
                re.IGNORECASE,
            ),
        }
    ],
    "speed_reads.one_sentence": [
        {
            "label": "max_chars",
            "regex": re.compile(
                r"(?:quick_reads|speed_reads)[\s\S]{0,220}?one_sentence[\s\S]{0,80}?不超过\s*(\d+)\s*字",
                re.IGNORECASE,
            ),
        }
    ],
    "speed_reads.exam_value": [
        {
            "label": "max_chars",
            "regex": re.compile(
                r"(?:quick_reads|speed_reads)[\s\S]{0,220}?exam_value[\s\S]{0,80}?不超过\s*(\d+)\s*字",
                re.IGNORECASE,
            ),
        }
    ],
}


def _repo_root(default_root: Path | None = None) -> Path:
    if default_root is not None:
        return default_root
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def _normalize_rule_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _excerpt(text: str, start: int, end: int, window: int = 110) -> str:
    snippet = text[start : min(len(text), end + window)]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:200]


def _rule_sources(root: Path) -> list[Path]:
    sources = [
        root / "prompt_templates.py",
        root / "llm_client.py",
        root / "CHANGELOG_HARNESS.md",
    ]
    sources.extend(sorted((root / "content_harness").glob("*.md")))
    return [path for path in sources if path.exists()]


def _collect_field_limit_hits(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hits: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for source in _rule_sources(root):
        text = _read_text(source)
        for field, specs in FIELD_LIMIT_PATTERNS.items():
            for spec in specs:
                for match in spec["regex"].finditer(text):
                    groups = match.groups()
                    value: int | tuple[int, int]
                    if len(groups) == 1:
                        value = int(groups[0])
                    else:
                        value = tuple(int(group) for group in groups)
                    hits.append(
                        {
                            "field": field,
                            "rule_label": spec["label"],
                            "value": value,
                            "source": source.relative_to(root).as_posix(),
                            "excerpt": _excerpt(text, match.start(), match.end()),
                        }
                    )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        grouped[(hit["field"], hit["rule_label"])].append(hit)

    for (field, rule_label), field_hits in grouped.items():
        unique_values: list[Any] = []
        for hit in field_hits:
            if hit["value"] not in unique_values:
                unique_values.append(hit["value"])
        if len(unique_values) > 1:
            conflicts.append(
                {
                    "field": field,
                    "rule_label": rule_label,
                    "values": unique_values,
                    "sources": [hit["source"] for hit in field_hits],
                    "hits": field_hits,
                }
            )

    return hits, conflicts


def _duplicate_runtime_rules(root: Path) -> list[dict[str, Any]]:
    runtime_path = root / "content_harness" / "runtime_prompt_rules.md"
    if not runtime_path.exists():
        return []

    counts: dict[str, list[int]] = defaultdict(list)
    for index, line in enumerate(_read_text(runtime_path).splitlines(), start=1):
        normalized = _normalize_rule_line(line)
        if not normalized or normalized.startswith("#"):
            continue
        if len(normalized) < 18:
            continue
        counts[normalized].append(index)

    return [
        {"text": text, "line_numbers": line_numbers}
        for text, line_numbers in counts.items()
        if len(line_numbers) > 1
    ]


def _runtime_length_report(root: Path) -> dict[str, Any]:
    runtime_path = root / "content_harness" / "runtime_prompt_rules.md"
    if not runtime_path.exists():
        return {
            "path": "content_harness/runtime_prompt_rules.md",
            "char_count": 0,
            "nonempty_line_count": 0,
            "max_chars": RUNTIME_PROMPT_RULES_MAX_CHARS,
            "max_nonempty_lines": RUNTIME_PROMPT_RULES_MAX_NONEMPTY_LINES,
            "too_long": False,
        }

    text = _read_text(runtime_path)
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    return {
        "path": runtime_path.relative_to(root).as_posix(),
        "char_count": len(text),
        "nonempty_line_count": len(nonempty_lines),
        "max_chars": RUNTIME_PROMPT_RULES_MAX_CHARS,
        "max_nonempty_lines": RUNTIME_PROMPT_RULES_MAX_NONEMPTY_LINES,
        "too_long": len(text) > RUNTIME_PROMPT_RULES_MAX_CHARS
        or len(nonempty_lines) > RUNTIME_PROMPT_RULES_MAX_NONEMPTY_LINES,
    }


def _archived_rules_still_in_runtime(root: Path) -> list[dict[str, Any]]:
    runtime_path = root / "content_harness" / "runtime_prompt_rules.md"
    knowledge_path = root / "knowledge" / "quality_issues.jsonl"
    if not runtime_path.exists() or not knowledge_path.exists():
        return []

    runtime_text = _read_text(runtime_path)
    findings: list[dict[str, Any]] = []
    for raw_line in _read_text(knowledge_path).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(row.get("status") or row.get("promoted_to") or "")
        if status != "archived":
            continue
        for term_key in ("issue_type", "detector"):
            term = str(row.get(term_key) or "").strip()
            if term and term in runtime_text:
                findings.append(
                    {
                        "term": term,
                        "term_key": term_key,
                        "issue_id": row.get("id"),
                    }
                )
    return findings


def audit_prompt_rules(root: Path | None = None) -> dict[str, Any]:
    repo_root = _repo_root(root)
    field_limit_hits, field_limit_conflicts = _collect_field_limit_hits(repo_root)
    duplicate_rules = _duplicate_runtime_rules(repo_root)
    runtime_length = _runtime_length_report(repo_root)
    archived_runtime_rules = _archived_rules_still_in_runtime(repo_root)
    return {
        "field_limit_hits": field_limit_hits,
        "field_limit_conflicts": field_limit_conflicts,
        "duplicate_rules": duplicate_rules,
        "runtime_prompt_rules_length": runtime_length,
        "archived_runtime_rules": archived_runtime_rules,
        "summary": {
            "field_limit_conflict_count": len(field_limit_conflicts),
            "duplicate_rule_count": len(duplicate_rules),
            "archived_runtime_rule_count": len(archived_runtime_rules),
            "runtime_prompt_rules_too_long": runtime_length["too_long"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit prompt rule drift and field limits.")
    parser.add_argument("--root", type=Path, default=None, help="Repository root path")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    report = audit_prompt_rules(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"field_limit_conflicts={report['summary']['field_limit_conflict_count']}")
        print(f"duplicate_rules={report['summary']['duplicate_rule_count']}")
        print(f"runtime_prompt_rules_too_long={report['summary']['runtime_prompt_rules_too_long']}")
        print(f"archived_runtime_rules={report['summary']['archived_runtime_rule_count']}")
        for conflict in report["field_limit_conflicts"]:
            values = ", ".join(str(value) for value in conflict["values"])
            print(f"- conflict: {conflict['field']} [{conflict['rule_label']}] => {values}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

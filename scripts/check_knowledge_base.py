from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"


def current_week() -> str:
    year, week, _ = dt.date.today().isocalendar()
    return f"{year}-W{week:02d}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def count_section_items(text: str, week: str, section: str) -> int:
    week_match = re.search(rf"^##\s+{re.escape(week)}\s*$", text, flags=re.MULTILINE)
    if not week_match:
        return 0
    tail = text[week_match.end() :]
    next_week = re.search(r"^##\s+", tail, flags=re.MULTILINE)
    block = tail[: next_week.start()] if next_week else tail
    section_match = re.search(rf"^###\s+{re.escape(section)}\s*$", block, flags=re.MULTILINE)
    if not section_match:
        return 0
    section_tail = block[section_match.end() :]
    next_section = re.search(r"^###\s+", section_tail, flags=re.MULTILINE)
    section_block = section_tail[: next_section.start()] if next_section else section_tail
    return len(re.findall(r"^\s*-\s+", section_block, flags=re.MULTILINE))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check weekly knowledge-base sample requirements.")
    parser.add_argument("--week", default=current_week(), help="ISO week label, for example 2026-W19.")
    parser.add_argument("--min-good", type=int, default=1)
    parser.add_argument("--min-bad", type=int, default=2)
    args = parser.parse_args()

    required_paths = [
        KNOWLEDGE_DIR / "README.md",
        KNOWLEDGE_DIR / "weekly_log.md",
        KNOWLEDGE_DIR / "good_examples",
        KNOWLEDGE_DIR / "bad_examples",
        KNOWLEDGE_DIR / "exam_patterns",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.exists()]
    if missing:
        print("missing knowledge paths: " + ", ".join(missing), file=sys.stderr)
        return 2

    weekly_text = read_text(KNOWLEDGE_DIR / "weekly_log.md")
    good_count = count_section_items(weekly_text, args.week, "Good Examples")
    bad_count = count_section_items(weekly_text, args.week, "Bad Examples")
    pattern_count = count_section_items(weekly_text, args.week, "Patterns Updated")

    print(f"week={args.week} good_examples={good_count} bad_examples={bad_count} patterns_updated={pattern_count}")
    if good_count < args.min_good or bad_count < args.min_bad:
        print(
            f"knowledge base requirement failed: need >= {args.min_good} good and >= {args.min_bad} bad examples.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

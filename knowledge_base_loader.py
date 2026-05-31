from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import settings


logger = logging.getLogger(__name__)

_JSONL_CACHE: dict[Path, list[dict[str, Any]]] = {}


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file as dictionaries, skipping bad lines without failing."""
    resolved_path = Path(path).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = Path(__file__).resolve().parent / resolved_path
    resolved_path = resolved_path.resolve()

    if resolved_path in _JSONL_CACHE:
        return _JSONL_CACHE[resolved_path]

    if not resolved_path.exists():
        logger.warning("Knowledge JSONL file not found: %s", resolved_path)
        _JSONL_CACHE[resolved_path] = []
        return []

    rows: list[dict[str, Any]] = []
    try:
        with resolved_path.open("r", encoding="utf-8-sig") as file:
            for line_number, raw_line in enumerate(file, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.error(
                        "Skip invalid JSONL line: file=%s line=%s error=%s",
                        resolved_path,
                        line_number,
                        exc,
                    )
                    continue
                if not isinstance(item, dict):
                    logger.error(
                        "Skip non-object JSONL line: file=%s line=%s type=%s",
                        resolved_path,
                        line_number,
                        type(item).__name__,
                    )
                    continue
                rows.append(item)
    except OSError as exc:
        logger.error("Failed to read Knowledge JSONL file: %s error=%s", resolved_path, exc)
        rows = []

    _JSONL_CACHE[resolved_path] = rows
    return rows


def clear_knowledge_cache() -> None:
    _JSONL_CACHE.clear()


def load_policy_core() -> list[dict[str, Any]]:
    return load_jsonl(settings.policy_corpus_path / "policy_statements_core.jsonl")


def load_policy_all() -> list[dict[str, Any]]:
    return load_jsonl(settings.policy_corpus_path / "policy_statements.jsonl")


def load_qiushi_article_index() -> list[dict[str, Any]]:
    return load_jsonl(settings.topic_knowledge_path / "article_index.jsonl")


def load_qiushi_chunks() -> list[dict[str, Any]]:
    return load_jsonl(settings.topic_knowledge_path / "article_chunks.jsonl")


def load_qiushi_quotes_core() -> list[dict[str, Any]]:
    return load_jsonl(settings.topic_knowledge_path / "authoritative_quotes_core.jsonl")


def load_qiushi_quotes_candidates() -> list[dict[str, Any]]:
    return load_jsonl(settings.topic_knowledge_path / "authoritative_quotes_candidates.jsonl")


def load_topic_frameworks() -> list[dict[str, Any]]:
    return load_jsonl(settings.topic_knowledge_path / "topic_frameworks.jsonl")

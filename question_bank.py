from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import requests

from article_filter import Article
from config import settings
from history import oss_config, oss_headers, oss_ready, oss_url


FORBIDDEN_MATERIAL_TERMS = [
    "根据材料",
    "根据给定资料",
    "结合材料",
    "材料一",
    "材料二",
    "材料三",
    "材料四",
    "材料五",
    "给定资料",
    "资料中",
    "文中提到",
    "阅读材料",
]

PREFERRED_QUESTION_TYPES = {
    "对策措施": 6,
    "解释评价/启示分析": 5,
    "概括要点": 4,
    "应用文/事务文书": 4,
    "待细分": 2,
    "大作文/议论文": -3,
}

_QUESTION_BANK_CACHE: list[dict[str, Any]] | None = None
_QUESTION_BANK_META: dict[str, Any] | None = None


def has_material_dependency(text: str) -> bool:
    return any(term in (text or "") for term in FORBIDDEN_MATERIAL_TERMS)


def sanitize_question_for_prompt(question_text: str) -> str:
    text = str(question_text or "").strip()
    replacements = {
        "请根据全部给定材料": "请结合实际",
        "根据给定资料": "结合实际",
        "根据材料": "结合实际",
        "结合材料": "结合实际",
        "给定资料": "相关情况",
        "资料中": "案例中",
        "文中提到": "案例中提到",
        "阅读材料": "阅读案例",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"材料[一二三四五六七八九十\d]+", "相关案例", text)
    return re.sub(r"\s+", " ", text).strip()


def _local_question_bank_path() -> Path:
    path = Path(settings.question_bank_local_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def _download_question_bank_from_oss(warnings: list[str]) -> Path | None:
    if not oss_ready():
        warnings.append("QUESTION_BANK_SOURCE=oss but OSS config is incomplete.")
        return None
    cfg = oss_config()
    cfg["object_key"] = settings.question_bank_oss_key
    target = Path("/tmp") / "shenlun_question_bank_v3_a.csv"
    try:
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=15)
        response.raise_for_status()
        target.write_bytes(response.content)
        return target
    except Exception as exc:
        warnings.append(f"question bank OSS read failed: {exc}")
        return None


def _resolve_question_bank_file(warnings: list[str]) -> Path | None:
    if settings.question_bank_source == "oss":
        path = _download_question_bank_from_oss(warnings)
        if path and path.exists():
            return path
    path = _local_question_bank_path()
    if path.exists():
        return path
    warnings.append(f"question bank local file not found: {path}")
    return None


def read_question_bank_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            question = str(row.get("题干_V3可用版") or "").strip()
            if not question:
                continue
            rows.append(row)
    return rows


def load_shenlun_question_bank() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _QUESTION_BANK_CACHE, _QUESTION_BANK_META
    if not settings.question_bank_enabled:
        return [], {"question_bank_used": False, "question_bank_enabled": False, "question_bank_warnings": []}
    if _QUESTION_BANK_CACHE is not None and _QUESTION_BANK_META is not None:
        return _QUESTION_BANK_CACHE, dict(_QUESTION_BANK_META)

    warnings: list[str] = []
    path = _resolve_question_bank_file(warnings)
    if not path:
        meta = {
            "question_bank_used": False,
            "question_bank_enabled": True,
            "question_bank_source": settings.question_bank_source,
            "question_bank_warnings": warnings,
        }
        _QUESTION_BANK_CACHE = []
        _QUESTION_BANK_META = meta
        return [], meta
    try:
        rows = read_question_bank_csv(path)
    except Exception as exc:
        warnings.append(f"question bank CSV read failed: {exc}")
        rows = []
    meta = {
        "question_bank_used": bool(rows),
        "question_bank_enabled": True,
        "question_bank_source": settings.question_bank_source,
        "question_bank_path": str(path),
        "question_bank_count": len(rows),
        "question_bank_warnings": warnings,
    }
    _QUESTION_BANK_CACHE = rows
    _QUESTION_BANK_META = meta
    return rows, meta


def _tokens_from_text(text: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}", text or ""):
        if token in {"人民", "日报", "评论", "文章", "主题", "问题", "治理", "发展"}:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:40]


def _article_match_tokens(article: Article) -> list[str]:
    text = " ".join([
        article.title or "",
        " ".join(article.themes or []),
        " ".join(article.tags or []),
        " ".join((article.body or [])[:3]),
    ])
    return _tokens_from_text(text)


def _score_row(row: dict[str, Any], tokens: list[str]) -> int:
    question = str(row.get("题干_V3可用版") or "")
    tags = str(row.get("主题标签") or "")
    q2 = str(row.get("题型二级") or "")
    year_raw = str(row.get("年份") or "")
    score = 0
    for token in tokens:
        if token and token in tags:
            score += 3
        if token and token in question:
            score += 2
    score += PREFERRED_QUESTION_TYPES.get(q2, 0)
    try:
        year = int(year_raw)
        if year >= 2020:
            score += 1
    except Exception:
        pass
    if has_material_dependency(question):
        score -= 2
    return score


def match_question_examples(article: Article, limit: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, meta = load_shenlun_question_bank()
    if not rows:
        return [], meta
    tokens = _article_match_tokens(article)
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        score = _score_row(row, tokens)
        if score <= 0 and str(row.get("题型二级") or "") == "大作文/议论文":
            continue
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    result: list[dict[str, Any]] = []
    for score, row in scored[: max(1, limit or settings.question_bank_match_limit)]:
        question = str(row.get("题干_V3可用版") or "").strip()
        result.append({
            "id": row.get("申论题ID"),
            "year": row.get("年份"),
            "exam_type": row.get("考试类型"),
            "region": row.get("地区/系统"),
            "paper": row.get("卷别/类别"),
            "question_type": row.get("题型二级") or row.get("题型一级"),
            "topic_tags": row.get("主题标签"),
            "question_preview": sanitize_question_for_prompt(question)[:180],
            "material_dependency": has_material_dependency(question),
            "match_score": score,
        })
    meta = dict(meta)
    meta["question_bank_refs"] = result
    meta["question_bank_match_tokens"] = tokens[:12]
    return result, meta


def build_question_bank_context(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return ""
    lines = [
        "【真题问法参考】",
        "以下是真实申论/公考题目的问法参考，只用于学习题型、场景、矛盾设置和问法。",
        "不得照搬原题，不得输出“根据材料X”“结合给定资料”等材料依赖表达。",
        "今日一题必须脱离原始申论材料也能独立作答。",
    ]
    for idx, item in enumerate(examples, start=1):
        lines.extend([
            f"参考题{idx}：",
            f"年份：{item.get('year') or ''}",
            f"地区：{item.get('region') or ''}",
            f"题型：{item.get('question_type') or ''}",
            f"主题：{item.get('topic_tags') or ''}",
            f"题干参考：{item.get('question_preview') or ''}",
        ])
    return "\n".join(lines)

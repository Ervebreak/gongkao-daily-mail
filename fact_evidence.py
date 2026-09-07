from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse


EVIDENCE_SCHEMA_VERSION = 1
FACT_REVIEW_SCHEMA_VERSION = 2
SOURCE_BOUND_PATHS = (
    "featured_article.one_sentence",
    "featured_article.core_viewpoint",
    "featured_article.original_overview",
    "featured_article.article_framework",
    "featured_article.article_framework_map.main_thread",
    "featured_article.article_framework_map.steps",
    "quick_reads",
)
SIMULATION_MARKERS = ("模拟情境", "假设你", "假如你", "某地", "某村", "某社区", "拟开展")
STRONG_SCOPE_TERMS = ("普遍", "全面", "全部", "一律", "均已", "大范围")
RECURRENCE_TERMS = ("回潮", "反弹", "死灰复燃", "治理后复发", "整治后复发")
SOURCE_PERSISTENCE_TERMS = ("部分", "一些", "仍", "依然", "尚", "问题突出", "问题仍然突出")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _title_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", _clean(value)).lower()


def _title_matches(listing_title: str, page_title: str) -> bool:
    left, right = _title_key(listing_title), _title_key(page_title)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _source_matches_url(source: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    source = _clean(source)
    mappings = {
        "人民日报图文数据库": ("people.com.cn",),
        "人民网观点": ("people.com.cn",),
        "人民网评": ("people.com.cn",),
        "新华社": ("news.cn", "xinhuanet.com"),
        "半月谈": ("banyuetan.org",),
        "浙江宣传": ("zjol.com.cn",),
        "学习强国": ("xuexi.cn",),
        "光明网": ("gmw.cn",),
        "求是网": ("qstheory.cn",),
        "中国青年报": ("cyol.com",),
    }
    expected = mappings.get(source)
    return bool(host and (not expected or any(host == suffix or host.endswith("." + suffix) for suffix in expected)))


def build_source_evidence(
    *,
    title: str,
    source: str,
    published_at: str,
    url: str,
    paragraphs: Iterable[str],
    listing_title: str | None = None,
    page_title: str | None = None,
    fetched_at: str | None = None,
    fetch_attempts: int = 1,
) -> dict[str, Any]:
    cleaned = [_clean(item) for item in paragraphs if _clean(item)]
    joined = "\n".join(cleaned)
    paragraph_rows = [
        {"id": f"p{index:03d}", "sha256": _sha256_text(text), "text": text}
        for index, text in enumerate(cleaned, start=1)
    ]
    listing = _clean(listing_title or title)
    page = _clean(page_title or title)
    title_ok = _title_matches(listing, page)
    source_ok = _source_matches_url(source, url)
    url_ok = urlparse(url).scheme in {"http", "https"} and bool(urlparse(url).hostname)
    date_ok = bool(_clean(published_at) and _clean(published_at).lower() != "unknown")
    enough_paragraphs = len(cleaned) >= 3
    enough_chars = len(joined) >= 200
    ending_ok = bool(cleaned and re.search(r"[。！？.!?）)]$", cleaned[-1]))
    boilerplate_hits = sum(1 for item in cleaned if re.search(r"责任编辑|版权声明|返回首页|打开客户端", item))
    boilerplate_ok = not cleaned or boilerplate_hits / max(1, len(cleaned)) < 0.25
    completeness_ok = enough_paragraphs and enough_chars and ending_ok and boilerplate_ok
    identity_ok = title_ok and source_ok and url_ok and date_ok
    limitations: list[str] = []
    if not title_ok:
        limitations.append("listing_title_page_title_mismatch")
    if not source_ok:
        limitations.append("source_url_mismatch")
    if not url_ok:
        limitations.append("invalid_url")
    if not date_ok:
        limitations.append("published_date_missing")
    if not enough_paragraphs:
        limitations.append("too_few_paragraphs")
    if not enough_chars:
        limitations.append("body_too_short_or_summary_only")
    if not ending_ok:
        limitations.append("body_ending_not_confirmed")
    if not boilerplate_ok:
        limitations.append("boilerplate_dominates_body")
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "verification_status": "verified" if identity_ok and completeness_ok else "incomplete",
        "title": _clean(title),
        "listing_title": listing,
        "page_title": page,
        "source": _clean(source),
        "published_at": _clean(published_at),
        "url": _clean(url),
        "fetched_at": fetched_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "fetch_attempts": max(1, int(fetch_attempts or 1)),
        "content_fingerprint": _sha256_text(joined),
        "paragraph_count": len(cleaned),
        "body_chars": len(joined),
        "paragraphs": paragraph_rows,
        "identity_checks": {
            "title_matches_page": title_ok,
            "source_matches_url": source_ok,
            "url_valid": url_ok,
            "published_date_present": date_ok,
        },
        "completeness_checks": {
            "enough_paragraphs": enough_paragraphs,
            "enough_chars": enough_chars,
            "ending_confirmed": ending_ok,
            "boilerplate_not_dominant": boilerplate_ok,
            "http_success_is_not_completeness_proof": True,
        },
        "limitations": limitations,
    }


def article_evidence(article: Any) -> dict[str, Any]:
    current = getattr(article, "evidence", None)
    if isinstance(current, dict) and current.get("content_fingerprint"):
        return current
    return build_source_evidence(
        title=getattr(article, "title", ""),
        source=getattr(article, "source", ""),
        published_at=getattr(article, "published_at", "unknown"),
        url=getattr(article, "url", ""),
        paragraphs=getattr(article, "body", []) or [],
    )


def build_evidence_bundle(articles: Iterable[Any]) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    for article in articles:
        evidence = article_evidence(article)
        key = _clean(evidence.get("url")) or _clean(evidence.get("title"))
        if key:
            items[key] = evidence
    source_hashes = sorted(str(item.get("content_fingerprint") or "") for item in items.values())
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "items": items,
        "source_set_hash": _sha256_text("\n".join(source_hashes)),
        "all_verified": bool(items) and all(item.get("verification_status") == "verified" for item in items.values()),
    }


def evidence_prompt_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in (bundle.get("items") or {}).values():
        rows.append({
            "title": item.get("title"),
            "source": item.get("source"),
            "published_at": item.get("published_at"),
            "url": item.get("url"),
            "verification_status": item.get("verification_status"),
            "content_fingerprint": item.get("content_fingerprint"),
            "limitations": item.get("limitations") or [],
            "paragraphs": [{"id": p.get("id"), "text": p.get("text")} for p in item.get("paragraphs") or []],
        })
    return {"source_set_hash": bundle.get("source_set_hash"), "all_verified": bundle.get("all_verified"), "articles": rows}


def normalize_selection_scores(
    selection: dict[str, Any],
    *,
    reason: str = "initial_selection",
    evidence_fingerprint: str = "",
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(selection, ensure_ascii=False)) if isinstance(selection, dict) else {}
    featured = normalized.get("featured") if isinstance(normalized.get("featured"), dict) else {}
    detail = featured.get("score_detail") if isinstance(featured.get("score_detail"), dict) else {}
    expected = {
        "exam_conversion": 30,
        "problem_awareness": 20,
        "scenario_specificity": 15,
        "contradiction_tension": 15,
        "material_value": 10,
        "authority_timeliness": 10,
    }
    clean_detail: dict[str, int] = {}
    for key, limit in expected.items():
        try:
            value = int(detail.get(key, 0))
        except Exception:
            value = 0
        clean_detail[key] = max(0, min(limit, value))
    supplied_total = featured.get("total_score")
    computed_total = sum(clean_detail.values())
    featured["score_detail"] = clean_detail
    featured["total_score"] = computed_total
    history = featured.get("score_history") if isinstance(featured.get("score_history"), list) else []
    history.append({
        "version": len(history) + 1,
        "reason": reason,
        "supplied_total": supplied_total,
        "effective_total": computed_total,
        "score_detail": clean_detail,
        "evidence_basis": "source_article_only",
        "evidence_fingerprint": evidence_fingerprint,
        "limitations": featured.get("risk_note") or "",
    })
    featured["score_history"] = history
    featured["score_source"] = "_llm_two_stage.selection.featured"
    normalized["featured"] = featured
    return normalized


def revalue_selection_scores(
    selection: dict[str, Any],
    *,
    score_detail: dict[str, Any],
    reason: str,
    evidence_fingerprint: str,
) -> dict[str, Any]:
    """Explicit revaluation allowed only when the source evidence version changed."""
    current = json.loads(json.dumps(selection, ensure_ascii=False)) if isinstance(selection, dict) else {}
    featured = current.get("featured") if isinstance(current.get("featured"), dict) else {}
    history = featured.get("score_history") if isinstance(featured.get("score_history"), list) else []
    previous_fingerprint = str(history[-1].get("evidence_fingerprint") or "") if history and isinstance(history[-1], dict) else ""
    if not _clean(reason):
        raise ValueError("revaluation reason is required")
    if not evidence_fingerprint or evidence_fingerprint == previous_fingerprint:
        raise ValueError("selection score may change only with new source evidence")
    featured["score_detail"] = score_detail
    featured["total_score"] = sum(int(value or 0) for value in score_detail.values())
    featured["score_history"] = history
    current["featured"] = featured
    return normalize_selection_scores(current, reason=reason, evidence_fingerprint=evidence_fingerprint)


def source_bound_candidate_payload(brief: dict[str, Any]) -> dict[str, Any]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    framework = featured.get("article_framework_map") if isinstance(featured.get("article_framework_map"), dict) else {}
    quick_reads = []
    for index, item in enumerate(brief.get("quick_reads") or []):
        if isinstance(item, dict):
            quick_reads.append({"index": index, "title": item.get("title"), "url": item.get("url"), "one_sentence": item.get("one_sentence")})
    return {
        "featured_article": {
            "title": featured.get("title"),
            "url": featured.get("url"),
            "one_sentence": featured.get("one_sentence"),
            "core_viewpoint": featured.get("core_viewpoint"),
            "original_overview": featured.get("original_overview"),
            "article_framework": featured.get("article_framework"),
            "article_framework_map": {"main_thread": framework.get("main_thread"), "steps": framework.get("steps")},
        },
        "quick_reads": quick_reads,
    }


def candidate_fact_hash(brief: dict[str, Any]) -> str:
    return _sha256_text(_canonical_json(source_bound_candidate_payload(brief)))


def _public_candidate_payload(value: Any) -> Any:
    """Return reader-facing candidate data, excluding internal review/debug state."""
    if isinstance(value, dict):
        return {
            str(key): _public_candidate_payload(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_public_candidate_payload(item) for item in value]
    return value


def candidate_content_hash(brief: dict[str, Any]) -> str:
    """Bind a review to the complete public candidate, including simulations/analysis."""
    return _sha256_text(_canonical_json(_public_candidate_payload(brief)))


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return _clean(value)


def deterministic_fact_issues(brief: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    items = bundle.get("items") if isinstance(bundle.get("items"), dict) else {}
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    featured_key = _clean(featured.get("url")) or _clean(featured.get("title"))
    evidence = items.get(featured_key) if isinstance(items.get(featured_key), dict) else {}
    source_text = " ".join(_clean(p.get("text")) for p in evidence.get("paragraphs") or [] if isinstance(p, dict))
    candidate_payload = source_bound_candidate_payload(brief)
    candidate_text = _flatten_text(candidate_payload.get("featured_article"))
    if source_text and any(term in source_text for term in SOURCE_PERSISTENCE_TERMS):
        if any(term in candidate_text for term in RECURRENCE_TERMS) and any(term in candidate_text for term in STRONG_SCOPE_TERMS):
            issues.append({
                "severity": "high",
                "code": "unsupported_scope_and_recurrence_upgrade",
                "field": "brief.featured_article",
                "candidate_claim": next((term for term in RECURRENCE_TERMS if term in candidate_text), "治理后复发"),
                "source_locator": next((p.get("id") for p in evidence.get("paragraphs") or [] if isinstance(p, dict) and any(term in _clean(p.get("text")) for term in SOURCE_PERSISTENCE_TERMS)), "source_paragraphs"),
                "judgment": "原文仅表述部分问题仍存在，候选升级为普遍性治理后复发。",
                "repair_target": "恢复原文的范围和时间关系，不得新增回潮、反弹或普遍化判断。",
                "message": "原文的‘部分/仍存在’被改写成‘普遍/治理后回潮’。",
            })
    certainty_upgrades = ("已经实施", "已实施", "已经发生", "已发生", "已经形成", "已形成", "已经完成", "已完成", "必然会")
    if any(term in source_text for term in ("可能", "或将", "有望", "尚待", "拟")):
        upgrade = next((term for term in certainty_upgrades if term in candidate_text and term not in source_text), "")
        if upgrade:
            issues.append({
                "severity": "medium",
                "code": "certainty_upgrade_needs_semantic_review",
                "field": "brief.featured_article",
                "candidate_claim": upgrade,
                "source_locator": next((p.get("id") for p in evidence.get("paragraphs") or [] if isinstance(p, dict) and any(term in _clean(p.get("text")) for term in ("可能", "或将", "有望", "尚待", "拟"))), "source_paragraphs"),
                "judgment": "原文包含不确定或未来语气，候选出现完成/确定语气，需结合上下文语义复核。",
                "repair_target": "保留原文确定性；无法确认时改回可能、拟或尚待。",
                "message": "候选可能把原文的不确定状态升级为已经发生。",
            })
    number_pattern = r"\d+(?:\.\d+)?(?:%|％|万|亿|元|人|户|项|次|年|月|日)?"
    numeric_pairs: list[tuple[str, str, dict[str, Any]]] = [("brief.featured_article", candidate_text, evidence)]
    for row in candidate_payload.get("quick_reads") or []:
        if not isinstance(row, dict):
            continue
        key = _clean(row.get("url")) or _clean(row.get("title"))
        item_evidence = items.get(key) if isinstance(items.get(key), dict) else {}
        numeric_pairs.append((f"brief.quick_reads[{int(row.get('index') or 0)}].one_sentence", _clean(row.get("one_sentence")), item_evidence))
    for field, field_text, item_evidence in numeric_pairs:
        item_source_text = " ".join(_clean(p.get("text")) for p in item_evidence.get("paragraphs") or [] if isinstance(p, dict))
        source_numbers = set(re.findall(number_pattern, item_source_text))
        for match in re.finditer(number_pattern, field_text):
            token = match.group(0)
            if len(re.sub(r"\D", "", token)) < 2 and not re.search(r"%|％|万|亿|元|人|户|项|次|年|月|日", token):
                continue
            if token not in source_numbers:
                issues.append({
                    "severity": "medium",
                    "code": "candidate_number_not_found_in_source",
                    "field": field,
                    "candidate_claim": field_text[max(0, match.start() - 18): match.end() + 18],
                    "source_locator": "not_found_in_verified_source",
                    "judgment": "候选中的数字或单位未在对应原文快照中找到。",
                    "repair_target": "核对数字对象和单位；不能确认则删除或明确为分析假设。",
                    "message": f"候选数字/单位未在原文中找到：{token}",
                })
    return issues[:8]


def build_fact_review(brief: dict[str, Any], *, semantic_review: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle = brief.get("_source_evidence") if isinstance(brief.get("_source_evidence"), dict) else {}
    items = bundle.get("items") if isinstance(bundle.get("items"), dict) else {}
    issues: list[dict[str, Any]] = []
    if not items:
        issues.append({"severity": "high", "code": "source_evidence_missing", "field": "brief._source_evidence", "source_locator": "missing", "judgment": "旧候选或当前候选没有可追溯原文证据。", "repair_target": "补抓并核验原文后重新审稿；不得沿用旧 ok。", "message": "缺少原文证据，事实核验未完成。"})
    else:
        for key, item in items.items():
            if not isinstance(item, dict) or item.get("verification_status") != "verified":
                issues.append({"severity": "high", "code": "source_evidence_incomplete", "field": f"brief._source_evidence.items.{key}", "source_locator": str(item.get("url") if isinstance(item, dict) else key), "judgment": "正文完整性或标题/来源/日期对应关系尚未核验完成。", "repair_target": "有限重抓或重选；不得以标题、摘要或 HTTP 200 冒充全文。", "message": "原文证据未达到 verified。"})
    issues.extend(deterministic_fact_issues(brief, bundle))
    semantic = semantic_review if isinstance(semantic_review, dict) else {}
    for issue in semantic.get("issues") or []:
        if isinstance(issue, dict) and str(issue.get("code") or "") in {"unsupported_claims", "wrong_article_understanding", "low_source_alignment"}:
            issues.append({**issue, "severity": "high"})
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (str(issue.get("code") or ""), str(issue.get("message") or ""))
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    high_count = sum(1 for issue in deduped if str(issue.get("severity") or "").lower() == "high")
    return {
        "schema_version": FACT_REVIEW_SCHEMA_VERSION,
        "ok": high_count == 0,
        "status": "fail" if high_count else ("review" if deduped else "ok"),
        "score": 0 if high_count else (82 if deduped else 100),
        "issues": deduped[:8],
        "binding": {
            "source_set_hash": bundle.get("source_set_hash"),
            "candidate_fact_hash": candidate_fact_hash(brief),
            "candidate_content_hash": candidate_content_hash(brief),
        },
        "checks": {
            "source_evidence_count": len(items),
            "all_sources_verified": bool(items) and all(isinstance(item, dict) and item.get("verification_status") == "verified" for item in items.values()),
            "deterministic_checks_are_contract_guards_not_semantic_proof": True,
            "semantic_review_supplied": bool(semantic_review),
        },
    }


def fact_review_binding_is_current(brief: dict[str, Any], review: dict[str, Any]) -> bool:
    bundle = brief.get("_source_evidence") if isinstance(brief.get("_source_evidence"), dict) else {}
    binding = review.get("binding") if isinstance(review.get("binding"), dict) else {}
    return bool(
        binding.get("source_set_hash")
        and binding.get("source_set_hash") == bundle.get("source_set_hash")
        and binding.get("candidate_fact_hash") == candidate_fact_hash(brief)
        and binding.get("candidate_content_hash") == candidate_content_hash(brief)
    )

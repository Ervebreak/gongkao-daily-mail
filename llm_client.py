from __future__ import annotations

import json
import re
import time
import warnings
from typing import Any, Callable

warnings.filterwarnings(
    "ignore",
    message="Unable to find acceptable character detection dependency.*",
)
import requests

from article_filter import Article
from config import settings
from lite_paid_cta import build_lite_paid_cta_prompt, fallback_lite_paid_cta_payload, finalize_lite_paid_cta_payload
from quick_reads_quality import evaluate_quick_reads
from fact_evidence import article_evidence, build_evidence_bundle, normalize_selection_scores
from question_quality import (
    compress_daily_question_breaking_hint,
    detect_daily_question_type_mode,
    detect_daily_question_wording_mode,
    evaluate_daily_question,
    material_dependency_hits,
    skeletonize_daily_question_framework,
    strip_daily_question_material_dependency,
)
from takeaway_quality import evaluate_takeaway
from question_bank import build_question_bank_context, match_question_examples
from prompt_templates import (
    SYSTEM_PROMPT,
    FRAMEWORK_MAP_RULES_V1,
    DAILY_QUESTION_RULES_V1,
    TAKEAWAY_RULES_V1,
    GLOBAL_RULES_V1,
    STRUCTURED_FIELD_RULES_V1,
    build_final_generation_prompt,
    build_selection_prompt,
    build_user_prompt,
    full_article_for_generation,
)
from token_economics import estimate_text_tokens


LlmTraceHook = Callable[[dict[str, Any]], None]
_LLM_TRACE_HOOK: LlmTraceHook | None = None


def set_llm_trace_hook(hook: LlmTraceHook | None) -> None:
    global _LLM_TRACE_HOOK
    _LLM_TRACE_HOOK = hook


def clear_llm_trace_hook() -> None:
    set_llm_trace_hook(None)


def _emit_llm_trace(event: str, **payload: Any) -> None:
    if _LLM_TRACE_HOOK is None:
        return
    try:
        _LLM_TRACE_HOOK({"event": event, **payload})
    except Exception:
        pass


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("LLM response does not contain JSON object.")
    return json.loads(match.group(0))


def chat_completion(
    model: str,
    user_prompt: str,
    timeout: int | None = None,
    trace: dict[str, Any] | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required in prod mode.")
    url = f"{settings.dashscope_base_url}/chat/completions"
    effective_timeout = timeout or settings.llm_timeout
    effective_system_prompt = system_prompt or SYSTEM_PROMPT
    payload = {
        "model": model,
        "temperature": settings.llm_temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": effective_system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    prompt_chars = len((effective_system_prompt or "") + (user_prompt or ""))
    estimated_prompt_tokens = estimate_text_tokens((effective_system_prompt or "") + "\n" + (user_prompt or ""))
    trace_payload = dict(trace or {})
    trace_payload.update(
        {
            "model": model,
            "timeout_seconds": effective_timeout,
            "prompt_chars": prompt_chars,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "base_url": settings.dashscope_base_url,
            "custom_system_prompt": bool(system_prompt),
        }
    )
    _emit_llm_trace("llm_request_start", **trace_payload)
    started_at = time.perf_counter()
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=effective_timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = extract_json_object(content)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        response_chars = len(content or "")
        estimated_response_tokens = estimate_text_tokens(content or "")
        _emit_llm_trace(
            "llm_token_usage",
            **trace_payload,
            elapsed_ms=elapsed_ms,
            response_chars=response_chars,
            estimated_response_tokens=estimated_response_tokens,
        )
        _emit_llm_trace(
            "llm_request_success",
            **trace_payload,
            elapsed_ms=elapsed_ms,
            response_chars=response_chars,
        )
        return parsed
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _emit_llm_trace(
            "llm_token_usage",
            **trace_payload,
            elapsed_ms=elapsed_ms,
            response_chars=0,
            estimated_response_tokens=0,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _emit_llm_trace(
            "llm_request_error",
            **trace_payload,
            elapsed_ms=elapsed_ms,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise




def _stage_timeout(stage: str) -> int:
    stage = (stage or "writing").strip().lower()
    if stage == "selection":
        return settings.llm_selection_timeout
    if stage in {"writing", "rewrite"}:
        return settings.llm_writing_timeout
    return settings.llm_timeout

def mock_brief(articles: list[Article], today: str) -> dict[str, Any]:
    featured = articles[0]
    quick = articles[1:4]
    themes = " / ".join(featured.themes[:3]) if featured.themes else "基层治理"
    brief = {
        "email_subject": f"公考晨读 {today}",
        "date": today,
        "today_theme": themes,
        "today_focus": f"围绕“{featured.title}”，积累申论立意、面试表达和常识背景。",
        "today_three_things": {
            "theme": themes,
            "must_remember_sentence": "把具体问题放到治理能力、公共服务和长效机制中理解。",
            "daily_question": "结合今日文章，谈谈如何把政策要求转化为基层治理实效。",
        },
        "featured_article": {
            "title": featured.title,
            "source": featured.source,
            "published_at": featured.published_at,
            "url": featured.url,
            "theme": themes,
            "original_overview": featured.body[:3] or [featured.title],
            "one_sentence": featured.body[0] if featured.body else featured.title,
            "why_worth_reading": "主题贴近申论和结构化面试高频考点，适合积累规范表达。",
            "core_viewpoint": featured.body[1] if len(featured.body) > 1 else featured.title,
            "article_framework": ["从具体事件切入治理短板", "分析执行链条中的责任断点", "提出协同治理和过程反馈", "迁移到面试综合分析表达"],
            "article_framework_map": {
                "title": "文章框架图",
                "steps": ["从具体事件切入治理短板", "分析执行链条中的责任断点", "提出协同治理和过程反馈", "迁移到面试综合分析表达"],
            },
            "structure_breakdown": ["从具体事件切入治理短板", "分析执行链条中的责任断点", "提出协同治理和过程反馈", "迁移到面试综合分析表达"],
            "usable_for_exam": ["申论综合分析", "面试社会现象题", "行测常识背景"],
            "copyable_expression": featured.body[:3] or [featured.title],
        },
        "quick_reads": [
            {
                "title": item.title,
                "source": item.source,
                "published_at": item.published_at,
                "url": item.url,
                "theme": " / ".join(item.themes[:2]) if item.themes else "其他",
                "exam_value": "可作为热点背景和规范表述积累。",
                "one_sentence": item.body[0] if item.body else item.title,
            }
            for item in quick
        ],
        "daily_common_knowledge": {
            "knowledge_point": themes,
            "field": "政治理论",
            "why_frequent": "常出现在政策理解、社会治理和综合分析题中。",
            "memory_sentence": "常识积累要同时记住概念、政策背景和现实应用场景。",
        },
        "daily_question": {
            "question": "【模拟情境】假如你是街道工作人员，辖区推进基层治理整改时出现群众质疑和人手不足问题。领导让你参与推进，请说明你将如何做好沟通、协调和落实工作？",
            "question_type": "申论对策题",
            "exam_focus": "这道题表面问工作推进，本质考察群众沟通、资源统筹和政策落实能力。",
            "breaking_direction": "先回应群众疑虑和基层压力，再从解释沟通、责任分工、过程反馈和长效机制展开。",
            "answer_frame": ["先摸清群众疑虑和基层困难，形成问题清单", "用通俗语言解释政策目标，争取群众理解", "协调部门和社区力量，明确任务节点", "建立反馈复盘机制，避免整改流于形式"],
            "candidate_answer": "我认为，推进这类基层治理工作，关键不在于喊口号，而在于把群众疑虑、基层压力和制度执行真正衔接起来。第一，要先把情况摸清楚，分清群众为什么不认可、基层为什么推进难。第二，要用群众听得懂的话把政策目标和实际影响讲清楚，争取理解支持。第三，要把相关部门和社区力量协调起来，明确责任和时间节点，避免工作空转。最后，还要建立反馈复盘机制，让群众看到变化、让干部看到办法，推动工作真正落地。",
            "thirty_second_answer": "我认为，推进基层治理整改，关键不在于一次性完成任务，而在于把群众感受、基层能力和制度执行真正衔接起来。",
            "output_prompt": "请用一句话写出这道题的开头表态。",
            "output_sentence_template": "我认为，推进基层治理整改，关键不在于一次性完成任务，而在于把群众感受、基层能力和制度执行真正衔接起来。",
            "takeaway_sentence": "",
        },
        "today_accumulation_card": {
            "title": themes,
            "sentences": featured.body[:3] or [featured.title],
        },
        "today_takeaway": {
            "keywords": (featured.themes[:3] if featured.themes else [themes]),
            "common_knowledge_points": [themes],
            "golden_sentences": [
                {"sentence": "治理成效不只看有没有部署，更要看群众有没有感受到变化。", "scenario": "基层治理、政策落实、群众工作"},
                {"sentence": "把问题解决在一线，关键是让责任、资源和反馈形成闭环。", "scenario": "综合分析、组织管理、作风建设"},
            ],
            "copyable_expressions": featured.body[:3] or [featured.title],
            "framework": "看问题先找群众感受，再看基层资源和部门协同，最后落到长效机制。",
            "extension": "同类主题也可迁移到社区治理、公共服务、基层减负等题目。",
            "use_scenarios": ["申论", "面试", "公基", "行测常识"],
        },
    }
    brief["_source_evidence"] = build_evidence_bundle([featured, *quick])
    return brief


def _article_key(article: Article) -> str:
    return (article.url or article.title or "").strip()


def _find_article_by_selection(articles: list[Article], selected: dict[str, Any]) -> Article | None:
    url = str(selected.get("url") or "").strip()
    title = str(selected.get("title") or "").strip()
    if url:
        for article in articles:
            if article.url == url:
                return article
    if title:
        normalized = re.sub(r"\s+", "", title)
        for article in articles:
            if re.sub(r"\s+", "", article.title) == normalized:
                return article
        for article in articles:
            if normalized and (normalized in re.sub(r"\s+", "", article.title) or re.sub(r"\s+", "", article.title) in normalized):
                return article
    return None


def _resolve_selected_articles(articles: list[Article], selection: dict[str, Any]) -> list[Article]:
    selected: list[Article] = []
    featured = selection.get("featured") if isinstance(selection, dict) else None
    if isinstance(featured, dict):
        article = _find_article_by_selection(articles, featured)
        if article:
            selected.append(article)
    if not selected and articles:
        selected.append(articles[0])

    quick_items = selection.get("quick_reads") if isinstance(selection, dict) else None
    if isinstance(quick_items, list):
        for item in quick_items[:2]:
            if not isinstance(item, dict):
                continue
            article = _find_article_by_selection(articles, item)
            if article and _article_key(article) not in {_article_key(x) for x in selected}:
                selected.append(article)
            if len(selected) >= 3:
                break
    for article in articles:
        if len(selected) >= 3:
            break
        if _article_key(article) not in {_article_key(x) for x in selected}:
            selected.append(article)
    return selected


def _dedupe_models(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in candidates:
        model = (model or "").strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def _stage_model_candidates(stage: str, test_mode: bool) -> list[str]:
    stage = (stage or "writing").strip().lower()
    if stage not in {"selection", "writing"}:
        stage = "writing"

    if stage == "selection":
        prod_primary = settings.selection_llm_model or settings.llm_model
        prod_fallback = settings.selection_llm_fallback_model or settings.llm_fallback_model
        test_primary = settings.test_selection_llm_model or settings.test_llm_model or prod_primary
        test_fallback = (
            settings.test_selection_llm_fallback_model
            or settings.test_llm_fallback_model
            or settings.selection_llm_fallback_model
            or settings.llm_fallback_model
        )
    else:
        prod_primary = settings.writing_llm_model or settings.llm_model
        prod_fallback = settings.writing_llm_fallback_model or settings.llm_fallback_model
        test_primary = settings.test_writing_llm_model or settings.test_llm_model or prod_primary
        test_fallback = (
            settings.test_writing_llm_fallback_model
            or settings.test_llm_fallback_model
            or settings.writing_llm_fallback_model
            or settings.llm_fallback_model
        )

    if test_mode:
        return _dedupe_models([test_primary, test_fallback, prod_primary, prod_fallback])
    return _dedupe_models([prod_primary, prod_fallback])


def get_stage_model_plan(test_mode: bool = False) -> dict[str, list[str]]:
    return {
        "selection": _stage_model_candidates("selection", test_mode),
        "writing": _stage_model_candidates("writing", test_mode),
    }


def _question_bank_context_for_article(article: Article | None) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "question_bank_enabled": settings.question_bank_enabled,
        "question_bank_source": settings.question_bank_source,
        "question_bank_warnings": [],
    }
    if article is not None:
        try:
            refs, meta = match_question_examples(article)
        except Exception as exc:
            if not settings.question_bank_fail_open:
                raise
            meta = {
                "question_bank_enabled": settings.question_bank_enabled,
                "question_bank_used": False,
                "question_bank_source": settings.question_bank_source,
                "question_bank_warnings": [f"question bank fallback: {type(exc).__name__}: {exc}"],
            }
    context = {
        "enabled": bool(meta.get("question_bank_enabled")),
        "used": bool(refs),
        "refs": refs,
        "instructions": build_question_bank_context(refs),
        "warnings": meta.get("question_bank_warnings") or [],
    }
    return refs, meta, context


def _call_with_fallback(prompt: str, test_mode: bool, stage: str = "writing", *, contract: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    candidates = _stage_model_candidates(stage, test_mode)
    for attempt, model in enumerate(candidates, start=1):
        trace = {
            "stage": stage,
            "attempt": attempt,
            "candidate_count": len(candidates),
            "fallback_used": attempt > 1,
            "test_mode": test_mode,
            "contract": contract,
        }
        try:
            response = chat_completion(model, prompt, timeout=_stage_timeout(stage), trace=trace)
            if contract:
                _raise_for_generation_contract(response, stage=stage)
            _emit_llm_trace("llm_stage_attempt_succeeded", **trace, model=model)
            return response
        except Exception as exc:
            errors.append(f"{model}: {exc}")
            _emit_llm_trace(
                "llm_stage_attempt_failed",
                **trace,
                model=model,
                error_type=type(exc).__name__,
                error=str(exc),
                fallback_remaining=attempt < len(candidates),
            )
    raise RuntimeError(f"LLM call failed for stage={stage}. " + " | ".join(errors))


def generate_lite_paid_cta(brief: dict[str, Any], test_mode: bool = False) -> dict[str, Any]:
    fallback = fallback_lite_paid_cta_payload(brief)
    model_candidates = _stage_model_candidates("writing", test_mode)
    if test_mode and any((model or "").lower() == "mock" for model in model_candidates):
        return fallback
    if not settings.dashscope_api_key and (settings.run_mode == "test" or test_mode):
        return fallback

    prompt = build_lite_paid_cta_prompt(brief)
    errors: list[str] = []
    for attempt, model in enumerate(model_candidates, start=1):
        trace = {
            "stage": "lite_paid_cta",
            "attempt": attempt,
            "candidate_count": len(model_candidates),
            "fallback_used": attempt > 1,
            "test_mode": test_mode,
        }
        try:
            response = chat_completion(model, prompt, timeout=settings.llm_writing_timeout, trace=trace)
            payload = finalize_lite_paid_cta_payload(response, brief)
            payload["fallback_used"] = bool(payload.get("fallback_used"))
            payload["llm_model"] = model
            return payload
        except Exception as exc:
            errors.append(f"{model}: {exc}")
            _emit_llm_trace(
                "llm_stage_attempt_failed",
                **trace,
                model=model,
                error_type=type(exc).__name__,
                error=str(exc),
                fallback_remaining=attempt < len(model_candidates),
            )

    result = dict(fallback)
    if errors:
        result["error"] = " | ".join(errors)
    return result


def _raise_for_generation_contract(payload: dict[str, Any], stage: str = "writing") -> None:
    """Reject incomplete high-risk fields before they enter the normal pipeline."""
    if stage == "selection" or not isinstance(payload, dict):
        return

    errors: list[str] = []
    if isinstance(payload.get("today_takeaway"), dict):
        takeaway_report = evaluate_takeaway(payload)
    elif "golden_sentences" in payload:
        takeaway_report = evaluate_takeaway({"today_takeaway": payload})
    else:
        takeaway_report = {}
    for issue in takeaway_report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") == "high" and issue.get("code") in {"truncated_takeaway", "empty_golden_sentence"}:
            errors.append(str(issue.get("message") or issue.get("code")))

    if isinstance(payload.get("quick_reads"), list):
        quick_report = evaluate_quick_reads(payload)
        for issue in quick_report.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            if issue.get("severity") == "high" and issue.get("code") in {
                "missing_quick_read_one_sentence",
                "empty_quick_read",
                "truncated_quick_read_one_sentence",
                "truncated_quick_read_exam_value",
            }:
                errors.append(str(issue.get("message") or issue.get("code")))

    if isinstance(payload.get("daily_question"), dict):
        question_report = evaluate_daily_question(payload)
        for issue in question_report.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            if issue.get("severity") == "high" and issue.get("code") in {
                "truncated_answer",
                "missing_candidate_answer",
                "missing_question",
            }:
                errors.append(str(issue.get("message") or issue.get("code")))

    if errors:
        raise ValueError("generation contract failed: " + "；".join(errors[:6]))


def _find_featured_article_for_rewrite(articles: list[Article], brief: dict[str, Any]) -> Article | None:
    featured = brief.get("featured_article") or {}
    if not isinstance(featured, dict):
        return None
    article = _find_article_by_selection(articles, {"title": featured.get("title"), "url": featured.get("url")})
    if article:
        return article
    title = str(featured.get("title") or "").strip()
    for candidate in articles:
        if candidate.title == title:
            return candidate
    return articles[0] if articles else None


def _rewrite_context_payload(article: Article | None, brief: dict[str, Any]) -> dict[str, Any]:
    featured = brief.get("featured_article") or {}
    article_payload = {}
    if article is not None:
        article_payload = full_article_for_generation(article, role="featured_candidate")
    if not article_payload:
        article_payload = {
            "title": featured.get("title"),
            "source": featured.get("source"),
            "url": featured.get("url"),
            "theme": featured.get("theme"),
            "body": [featured.get("one_sentence") or "", featured.get("core_viewpoint") or ""],
        }
    return {
        "today_theme": brief.get("today_theme"),
        "today_focus": brief.get("today_focus"),
        "featured_article": article_payload,
        "current_framework_map": (featured.get("article_framework_map") or {}) if isinstance(featured, dict) else {},
        "current_daily_question": brief.get("daily_question") or {},
        "current_today_takeaway": brief.get("today_takeaway") or {},
    }


def _infer_practical_question_type(question: str, current_type: str) -> str:
    if any(keyword in question for keyword in ("解释", "说明", "回应", "沟通", "答复", "协调")):
        return "机关实务题｜沟通协调类"
    if any(keyword in question for keyword in ("牵头", "推进", "落实", "整改", "统筹")):
        return "机关实务题｜推进落实类"
    if current_type and "机关实务题" in current_type:
        return current_type
    return "机关实务题｜处置应对类"


def _normalize_shenlun_question_text(question: str) -> str:
    text = strip_daily_question_material_dependency(question)
    text = re.sub(r"^(你是|假如你是|作为)[^，。；]{0,24}[，，、]", "", text).strip()
    text = re.sub(r"^领导让你[^，。；]{0,24}[，，、]", "", text).strip()
    text = re.sub(r"^(工作人员|负责人)[^，。；]{0,18}[，，、]", "", text).strip()
    text = re.sub(r"你会(怎么做|如何做|如何处理|怎么处理)[。？]?$", "请提出对策。", text)
    text = re.sub(r"请(谈谈|说明)(你的)?工作思路[。？]?$", "请提出对策。", text)
    text = re.sub(r"请(结合实际)?谈谈(你的)?对策[。？]?$", "请提出对策。", text)
    if "请" not in text:
        text = f"{text}请提出对策。"
    if not text.startswith(("某地", "当地", "某市", "某县", "某社区")):
        text = f"某地{text}"
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"\s+", "", text)
    return text.rstrip("，；") if text.endswith(("。", "？")) else f"{text.rstrip('，；')}。"


def _normalize_daily_question_module(module: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(module or {}, ensure_ascii=False))
    question = str(updated.get("question") or "").strip()
    question_type = str(updated.get("question_type") or updated.get("type") or "").strip()
    candidate_answer = str(updated.get("candidate_answer") or "").strip()
    answer_framework = updated.get("answer_framework") or updated.get("answer_frame") or []
    framework_items = skeletonize_daily_question_framework(answer_framework, candidate_answer)
    if framework_items:
        updated["answer_framework"] = framework_items
    if material_dependency_hits(question):
        question = strip_daily_question_material_dependency(question)

    type_mode = detect_daily_question_type_mode(question_type)
    wording_mode = detect_daily_question_wording_mode(question)
    if wording_mode == "practical":
        updated["question_type"] = _infer_practical_question_type(question, question_type)
    elif type_mode == "shenlun":
        updated["question_type"] = question_type or "申论对策题"
        question = _normalize_shenlun_question_text(question)

    if detect_daily_question_type_mode(updated.get("question_type")) == "shenlun":
        question = _normalize_shenlun_question_text(question)
    updated["question"] = question

    breaking_hint = str(updated.get("breaking_hint") or updated.get("breaking_direction") or "").strip()
    if breaking_hint:
        route_terms = ["先", "再", "最后", "首先", "其次", "再次", "第一", "第二", "第三", "一是", "二是", "三是"]
        if len(breaking_hint) > 80 or breaking_hint.count("；") + breaking_hint.count(";") >= 2 or sum(term in breaking_hint for term in route_terms) >= 2:
            breaking_hint = compress_daily_question_breaking_hint(breaking_hint, updated.get("answer_framework") or framework_items)
    if breaking_hint:
        updated["breaking_hint"] = breaking_hint

    return updated


def _daily_question_candidate_styles() -> list[dict[str, str]]:
    return [
        {
            "name": "shenlun_policy",
            "label": "申论综合分析/对策题",
            "rules": "优先生成更像申论综合分析题或对策题的题干，可以不强制设置身份，但要有明确场景、矛盾和任务，便于展开具体作答。",
        },
        {
            "name": "practical_scene",
            "label": "机关实务/面试场景题",
            "rules": "优先生成更像机关实务或面试场景题的题干，必须有明确身份、场景、矛盾和任务，能自然引出工作思路或沟通协调作答。",
        },
    ]


def build_daily_question_candidate_prompt(brief: dict[str, Any], article: Article | None, style: dict[str, str]) -> str:
    payload = _rewrite_context_payload(article, brief)
    payload["candidate_style"] = style.get("label")
    payload["style_rules"] = style.get("rules")
    question_bank_meta = brief.get("_question_bank") if isinstance(brief.get("_question_bank"), dict) else {}
    payload["question_bank_refs"] = question_bank_meta.get("question_bank_refs") or []
    return f"""
请只生成一个 daily_question 候选，不要改写其他字段。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{DAILY_QUESTION_RULES_V1}

{STRUCTURED_FIELD_RULES_V1}

候选方向：{style.get("label")}
风格要求：{style.get("rules")}

请基于下方文章与当前 brief，输出一个更适合作为今天题目的 daily_question。
输出字段必须包含：question_type、question、exam_focus、breaking_hint、answer_framework、candidate_answer、thirty_second_answer、output_prompt、output_sentence_template。
要求：
1. 只做 1 个候选。
2. 题目必须贴合 featured_article，不得另起炉灶。
3. 题目要像真题，不能空泛，也不能只是复述文章标题。
4. answer_framework 要能和 candidate_answer 配套，但不能逐句照抄。
5. 不得和 today_takeaway、featured_article.rewritable_expression、考场转化内容重复堆叠同一组套话。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _daily_question_overlap_penalty(brief: dict[str, Any], module: dict[str, Any]) -> int:
    target_text = " ".join(
        str(part or "")
        for part in [
            module.get("question"),
            " ".join(str(item or "") for item in (module.get("answer_framework") or [])),
            module.get("candidate_answer"),
            module.get("thirty_second_answer"),
        ]
    )
    support_texts = [
        ((brief.get("today_takeaway") if isinstance(brief.get("today_takeaway"), dict) else {}) or {}).get("framework"),
        ((brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}) or {}).get("rewritable_expression"),
        ((brief.get("exam_transfer_card") if isinstance(brief.get("exam_transfer_card"), dict) else {}) or {}).get("exam_transfer"),
        ((brief.get("exam_transfer_card") if isinstance(brief.get("exam_transfer_card"), dict) else {}) or {}).get("exam_expression"),
    ]
    penalty = 0
    compact_target = re.sub(r"\s+", "", target_text)
    for source in support_texts:
        compact_source = re.sub(r"\s+", "", str(source or ""))
        if len(compact_source) < 8 or len(compact_target) < 12:
            continue
        if compact_source in compact_target or compact_target in compact_source:
            penalty += 8
        elif len(set(re.findall(r"[\u4e00-\u9fff]{2,6}", compact_source)) & set(re.findall(r"[\u4e00-\u9fff]{2,6}", compact_target))) >= 3:
            penalty += 4
    return penalty


def _daily_question_style_bonus(module: dict[str, Any], style_name: str) -> int:
    question_type = str(module.get("question_type") or "")
    question_text = str(module.get("question") or "")
    if style_name == "shenlun_policy":
        bonus = 0
        if any(keyword in question_type for keyword in ("申论", "对策", "综合")):
            bonus += 4
        if "你是" not in question_text and "作为" not in question_text:
            bonus += 2
        return bonus
    if style_name == "practical_scene":
        bonus = 0
        if any(keyword in question_type for keyword in ("面试", "实务", "机关")):
            bonus += 4
        if "你是" in question_text or "作为" in question_text:
            bonus += 2
        return bonus
    return 0


def _daily_question_consistency_bonus(module: dict[str, Any]) -> int:
    question_type = str(module.get("question_type") or "")
    question_text = str(module.get("question") or "")
    type_mode = detect_daily_question_type_mode(question_type)
    wording_mode = detect_daily_question_wording_mode(question_text)
    if type_mode == "unknown" or wording_mode == "unknown":
        return 0
    if type_mode == "practical" and wording_mode == "practical":
        return 4
    if type_mode == "shenlun" and wording_mode != "practical":
        return 4
    if type_mode == "practical" and wording_mode != "practical":
        return -8
    if type_mode == "shenlun" and wording_mode == "practical":
        return -8
    return 0


def _daily_question_candidate_score(brief: dict[str, Any], module: dict[str, Any], style_name: str) -> dict[str, Any]:
    candidate_brief = json.loads(json.dumps(brief, ensure_ascii=False))
    candidate_brief["daily_question"] = module
    question_report = evaluate_daily_question(candidate_brief)
    base_score = int(question_report.get("score") or 0)
    overlap_penalty = _daily_question_overlap_penalty(candidate_brief, module)
    style_bonus = _daily_question_style_bonus(module, style_name)
    consistency_bonus = _daily_question_consistency_bonus(module)
    final_score = base_score + style_bonus + consistency_bonus - overlap_penalty
    return {
        "final_score": final_score,
        "base_score": base_score,
        "style_bonus": style_bonus,
        "consistency_bonus": consistency_bonus,
        "overlap_penalty": overlap_penalty,
        "quality": question_report,
    }


def select_best_daily_question_candidate(brief: dict[str, Any], articles: list[Article], test_mode: bool = False) -> dict[str, Any]:
    if not settings.daily_question_multi_candidate_enabled:
        return {"brief": brief, "selected_source": "disabled", "candidates": [], "fallback_used": True}
    if test_mode and any((model or "").lower() == "mock" for model in _stage_model_candidates("writing", test_mode)):
        return {"brief": brief, "selected_source": "mock_skip", "candidates": [], "fallback_used": True}

    article = _find_featured_article_for_rewrite(articles, brief)
    current_module = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    candidates: list[dict[str, Any]] = []
    if current_module:
        normalized_current = _normalize_daily_question_module(current_module)
        candidates.append(
            {
                "source": "original",
                "style": "original",
                "module": normalized_current,
                **_daily_question_candidate_score(brief, normalized_current, "original"),
            }
        )

    errors: list[str] = []
    for style in _daily_question_candidate_styles():
        prompt = build_daily_question_candidate_prompt(brief, article, style)
        try:
            response = _call_with_fallback(prompt, test_mode, stage="question_candidate_selection", contract=False)
            module = response.get("daily_question") if isinstance(response.get("daily_question"), dict) else response
            if not isinstance(module, dict) or not module.get("question"):
                raise ValueError("daily question candidate payload missing question")
            if style["name"] == "shenlun_policy":
                module = {
                    **module,
                    "question_type": "申论对策题",
                    "question": _normalize_shenlun_question_text(str(module.get("question") or "")),
                }
            module = _normalize_daily_question_module(module)
            candidates.append(
                {
                    "source": "generated",
                    "style": style["name"],
                    "module": module,
                    **_daily_question_candidate_score(brief, module, style["name"]),
                }
            )
        except Exception as exc:
            errors.append(f"{style.get('name')}: {type(exc).__name__}: {exc}")

    if not candidates:
        return {
            "brief": brief,
            "selected_source": "fallback_original",
            "candidates": [],
            "errors": errors,
            "fallback_used": True,
        }

    ranked = sorted(
        candidates,
        key=lambda item: (
            int(item.get("final_score") or 0),
            int((item.get("quality") or {}).get("score") or 0),
            1 if item.get("source") == "generated" else 0,
        ),
        reverse=True,
    )
    winner = ranked[0]
    updated = json.loads(json.dumps(brief, ensure_ascii=False))
    updated["daily_question"] = json.loads(json.dumps(winner["module"], ensure_ascii=False))
    three = updated.setdefault("today_three_things", {})
    if isinstance(three, dict):
        three["daily_question"] = str(winner["module"].get("question") or three.get("daily_question") or "")
    updated["_daily_question_candidates"] = [
        {
            "source": item["source"],
            "style": item["style"],
            "final_score": item["final_score"],
            "base_score": item["base_score"],
            "style_bonus": item["style_bonus"],
            "consistency_bonus": item["consistency_bonus"],
            "overlap_penalty": item["overlap_penalty"],
            "quality_score": int((item.get("quality") or {}).get("score") or 0),
            "type_consistent": bool(((item.get("quality") or {}).get("checks") or {}).get("type_consistent")),
        }
        for item in ranked
    ]
    return {
        "brief": updated,
        "selected_source": str(winner.get("style") or winner.get("source") or ""),
        "candidates": updated["_daily_question_candidates"],
        "errors": errors,
        "fallback_used": winner.get("source") == "original",
    }


def _issue_messages(report: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for item in (report.get("issues") or []):
        if isinstance(item, dict):
            msg = str(item.get("message") or item.get("code") or "").strip()
            sev = str(item.get("severity") or "").strip()
            if msg:
                messages.append(f"[{sev}] {msg}" if sev else msg)
    return messages[:8]


def build_framework_rewrite_prompt(brief: dict[str, Any], article: Article | None, report: dict[str, Any]) -> str:
    payload = _rewrite_context_payload(article, brief)
    payload["quality_issues"] = _issue_messages(report)
    payload["task"] = "只重写 featured_article.article_framework_map 模块"
    return f"""
请只重写 featured_article.article_framework_map 模块。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{FRAMEWORK_MAP_RULES_V1}

你刚刚生成的文章框架图存在这些问题：
{json.dumps(payload['quality_issues'], ensure_ascii=False)}

请基于以下文章与当前内容，重写 article_framework_map。
输出字段必须包含：article_type、main_thread、steps、exam_tags。
其中 steps 必须是 3-5 个对象数组，每个对象只包含 label 和 content。
label 目标 10-18 个字，写不短就改写，不得依赖渲染截断；content 必须是完整短句，不得出现孤立数字或半句话。
steps 只展示文章真实展开结构，严禁加入“考场迁移”“这类题怎么用”等备考迁移节点。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_daily_question_rewrite_prompt(brief: dict[str, Any], article: Article | None, report: dict[str, Any]) -> str:
    payload = _rewrite_context_payload(article, brief)
    payload["quality_issues"] = _issue_messages(report)
    payload["task"] = "只重写 daily_question 模块"
    return f"""
请只重写 daily_question 模块。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{DAILY_QUESTION_RULES_V1}

{STRUCTURED_FIELD_RULES_V1}

你刚刚生成的今日一题存在这些问题：
{json.dumps(payload['quality_issues'], ensure_ascii=False)}

请基于以下文章与当前内容，只重写 daily_question。
输出字段必须包含：question_type、question、exam_focus、breaking_hint、answer_framework、candidate_answer、thirty_second_answer、output_prompt、output_sentence_template。
question 控制在80-180字；answer_framework 应为 3-4 条关键词式骨架，每点不超过45字，格式为“动词短语：简短解释。”；candidate_answer 应是 280-450 字、自然稳重、可复述的考生版参考答案，负责完整展开；answer_framework 不得与 candidate_answer 逐句重复，不得连续12字以上照搬答案表达；thirty_second_answer 控制在40-100字；output_sentence_template 控制在60-120字。
不得另起炉灶，必须与 featured_article 直接相关。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_takeaway_rewrite_prompt(brief: dict[str, Any], article: Article | None, report: dict[str, Any]) -> str:
    payload = _rewrite_context_payload(article, brief)
    payload["quality_issues"] = _issue_messages(report)
    payload["task"] = "只重写 today_takeaway 模块"
    return f"""
请只重写 today_takeaway 模块。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{TAKEAWAY_RULES_V1}

{STRUCTURED_FIELD_RULES_V1}

你刚刚生成的今日可带走存在这些问题：
{json.dumps(payload['quality_issues'], ensure_ascii=False)}

请基于以下文章与当前内容，只重写 today_takeaway。
输出字段必须包含：keywords、common_knowledge_points、golden_sentences、framework、use_scenarios。
keywords 输出2-3个，每个不超过10字；common_knowledge_points 最多1条，不超过100字；framework 不超过50字。
golden_sentences 必须有2条，每条为对象：sentence + scenario；sentence 目标28-48字、不超过60字；scenario 目标25-50字、不超过60字，要完整说明适用题型、位置或用法，不能只写“申论/面试”，也不能停在半句话。
60字只是防截断安全上限，不代表要写满；必备金句要短、准、顺口、好背。
不得出现省略号、半句话、空泛标签或与其他模块大段重复。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_takeaway_module_prompt(brief: dict[str, Any], article: Article | None, report: dict[str, Any] | None = None) -> str:
    payload = _rewrite_context_payload(article, brief)
    payload["quality_issues"] = _issue_messages(report or {})
    payload["task"] = "独立生成并验收 today_takeaway 模块"
    return f"""
请只生成 today_takeaway 模块。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{TAKEAWAY_RULES_V1}

{STRUCTURED_FIELD_RULES_V1}

模块目标：
1. today_takeaway 是最终记忆卡，只输出关键词、1条安全常识、2条必备金句和1个可迁移框架。
2. 如果原文没有明确出现具体文件名、部门名、数字、制度名称，不得编造具体政策事实；可以输出通用考点表述，但不得虚构“某部门联合出台某文件”。
3. keywords 输出2-3个，每个不超过10字；common_knowledge_points 最多1条，不超过100字；framework 不超过50字。
4. golden_sentences 必须有2条，每条为对象：sentence + scenario。
5. 每条 sentence 必须是完整短句，目标28-48字、不超过60字，不得出现省略号、半句话、未完成判断或停在动词后。
6. 每条 scenario 目标25-50字、不超过60字，必须是完整场景说明，不能停在“用于强调……配套监”这类半截表达。
7. 如果句子写长了，必须改短，而不是截断。
8. 60字只是防截断安全上限，不代表要写满；必备金句要短、准、顺口、好背。

上一轮问题：
{json.dumps(payload['quality_issues'], ensure_ascii=False)}

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_quick_reads_module_prompt(brief: dict[str, Any], articles: list[Article], report: dict[str, Any] | None = None) -> str:
    selection = brief.get("_llm_two_stage") if isinstance(brief.get("_llm_two_stage"), dict) else {}
    selected_urls = set(selection.get("selected_urls") or [])
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    featured_url = str(featured.get("url") or "")
    current_quick_reads = brief.get("quick_reads") if isinstance(brief.get("quick_reads"), list) else []
    quick_urls = {str(item.get("url") or "") for item in current_quick_reads if isinstance(item, dict)}
    quick_articles = [
        full_article_for_generation(article, role="quick_read_candidate")
        for article in articles
        if article.url and article.url != featured_url and (article.url in quick_urls or article.url in selected_urls)
    ][:2]
    payload = {
        "today_theme": brief.get("today_theme"),
        "featured_article": {
            "title": featured.get("title"),
            "source": featured.get("source"),
            "url": featured.get("url"),
            "theme": featured.get("theme"),
        },
        "current_quick_reads": current_quick_reads,
        "quick_read_articles": quick_articles,
        "quality_issues": _issue_messages(report or {}),
    }
    return f"""
请只生成 quick_reads 模块。
只输出合法 JSON，不要输出解释。

{GLOBAL_RULES_V1}

{STRUCTURED_FIELD_RULES_V1}

模块目标：
1. quick_reads 最多2篇，必须来自输入 quick_read_articles 或 current_quick_reads，不得虚构标题、来源、日期、链接。
2. 每篇必须包含 title、source、published_at、url、theme、one_sentence、exam_value。
3. one_sentence 是文章核心内容的一句话概括，目标40-55字、不超过60字，不能为空，必须是完整句。
4. exam_value 是考试素材价值说明，目标45-70字、不超过80字，必须说明可用于哪类考点、案例或表达。
5. 不要写长分析，不要抢 featured_article 的主线；上限只是安全余量，不要写满。

上一轮问题：
{json.dumps(payload['quality_issues'], ensure_ascii=False)}

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _merge_quick_reads_metadata(current: list[Any], regenerated: list[Any]) -> list[dict[str, Any]]:
    current_by_url = {
        str(item.get("url") or ""): item
        for item in current
        if isinstance(item, dict) and str(item.get("url") or "")
    }
    merged: list[dict[str, Any]] = []
    for item in regenerated[:2]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        base = dict(current_by_url.get(url) or {})
        base.update({key: value for key, value in item.items() if value not in (None, "")})
        merged.append(base)
    return merged


def refine_high_risk_modules(brief: dict[str, Any], articles: list[Article], test_mode: bool = False, max_attempts: int = 2) -> dict[str, Any]:
    """Generate high-risk modules separately and validate each before accepting it."""
    if test_mode and any((model or "").lower() == "mock" for model in _stage_model_candidates("writing", test_mode)):
        return brief

    article = _find_featured_article_for_rewrite(articles, brief)
    updated = json.loads(json.dumps(brief, ensure_ascii=False))

    takeaway_report = evaluate_takeaway(updated)
    for _ in range(max(1, max_attempts)):
        prompt = build_takeaway_module_prompt(updated, article, takeaway_report)
        response = _call_with_fallback(prompt, test_mode, stage="writing", contract=True)
        module = response.get("today_takeaway") if isinstance(response.get("today_takeaway"), dict) else response
        if isinstance(module, dict):
            candidate = json.loads(json.dumps(updated, ensure_ascii=False))
            candidate["today_takeaway"] = module
            takeaway_report = evaluate_takeaway(candidate)
            if takeaway_report.get("ok"):
                updated = candidate
                break
    if not evaluate_takeaway(updated).get("ok"):
        raise ValueError("today_takeaway module generation failed quality checks: " + json.dumps(takeaway_report.get("issues") or [], ensure_ascii=False))

    quick_report = evaluate_quick_reads(updated)
    for _ in range(max(1, max_attempts)):
        prompt = build_quick_reads_module_prompt(updated, articles, quick_report)
        response = _call_with_fallback(prompt, test_mode, stage="writing", contract=True)
        quick_reads = response.get("quick_reads") if isinstance(response.get("quick_reads"), list) else response
        if isinstance(quick_reads, list):
            candidate = json.loads(json.dumps(updated, ensure_ascii=False))
            candidate["quick_reads"] = _merge_quick_reads_metadata(candidate.get("quick_reads") or [], quick_reads)
            quick_report = evaluate_quick_reads(candidate)
            if quick_report.get("ok"):
                updated = candidate
                break
    if not evaluate_quick_reads(updated).get("ok"):
        raise ValueError("quick_reads module generation failed quality checks: " + json.dumps(quick_report.get("issues") or [], ensure_ascii=False))

    return updated


def rewrite_failed_modules_once(
    brief: dict[str, Any],
    articles: list[Article],
    question_quality: dict[str, Any],
    framework_quality: dict[str, Any],
    takeaway_quality: dict[str, Any] | None = None,
    quick_reads_quality: dict[str, Any] | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    if test_mode and any((model or "").lower() == "mock" for model in _stage_model_candidates("writing", test_mode)):
        return {
            "brief": brief,
            "rewritten_modules": [],
            "details": {"rewrite_skipped": "TEST_LLM_MODEL=mock，跳过定点重写以保持离线 dry run 稳定。"},
        }

    article = _find_featured_article_for_rewrite(articles, brief)
    updated = json.loads(json.dumps(brief, ensure_ascii=False))
    rewritten_modules: list[str] = []
    details: dict[str, Any] = {}

    if not framework_quality.get("ok"):
        prompt = build_framework_rewrite_prompt(updated, article, framework_quality)
        response = _call_with_fallback(prompt, test_mode, stage="writing")
        module = response.get("article_framework_map") if isinstance(response.get("article_framework_map"), dict) else response
        if isinstance(module, dict):
            featured = updated.setdefault("featured_article", {})
            if isinstance(featured, dict):
                featured["article_framework_map"] = module
                rewritten_modules.append("article_framework_map")
                details["article_framework_map"] = {"issues": _issue_messages(framework_quality)}

    if not question_quality.get("ok"):
        prompt = build_daily_question_rewrite_prompt(updated, article, question_quality)
        response = _call_with_fallback(prompt, test_mode, stage="writing")
        module = response.get("daily_question") if isinstance(response.get("daily_question"), dict) else response
        if isinstance(module, dict):
            updated["daily_question"] = _normalize_daily_question_module(module)
            three = updated.setdefault("today_three_things", {})
            if isinstance(three, dict):
                three["daily_question"] = str(updated["daily_question"].get("question") or three.get("daily_question") or "")
            rewritten_modules.append("daily_question")
            details["daily_question"] = {"issues": _issue_messages(question_quality)}

    if takeaway_quality and not takeaway_quality.get("ok"):
        prompt = build_takeaway_rewrite_prompt(updated, article, takeaway_quality)
        response = _call_with_fallback(prompt, test_mode, stage="writing")
        module = response.get("today_takeaway") if isinstance(response.get("today_takeaway"), dict) else response
        if isinstance(module, dict):
            updated["today_takeaway"] = module
            rewritten_modules.append("today_takeaway")
            details["today_takeaway"] = {"issues": _issue_messages(takeaway_quality)}

    if quick_reads_quality and not quick_reads_quality.get("ok"):
        prompt = build_quick_reads_module_prompt(updated, articles, quick_reads_quality)
        response = _call_with_fallback(prompt, test_mode, stage="writing")
        module = response.get("quick_reads") if isinstance(response.get("quick_reads"), list) else response
        if isinstance(module, list):
            updated["quick_reads"] = _merge_quick_reads_metadata(updated.get("quick_reads") or [], module)
            rewritten_modules.append("quick_reads")
            details["quick_reads"] = {"issues": _issue_messages(quick_reads_quality)}

    return {"brief": updated, "rewritten_modules": rewritten_modules, "details": details}


def generate_brief_two_stage(articles: list[Article], today: str, test_mode: bool = False, selection_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Two-stage generation: select articles first, then generate with fuller featured article text."""
    selection_prompt = build_selection_prompt(articles, today, selection_context=selection_context)
    raw_selection = _call_with_fallback(selection_prompt, test_mode, stage="selection")
    raw_featured = raw_selection.get("featured") if isinstance(raw_selection.get("featured"), dict) else {}
    score_article = _find_article_by_selection(articles, raw_featured)
    selection = normalize_selection_scores(
        raw_selection,
        reason="initial_selection_from_verified_source",
        evidence_fingerprint=str(article_evidence(score_article).get("content_fingerprint") or "") if score_article else "",
    )
    selected_articles = _resolve_selected_articles(articles, selection)
    featured_article = selected_articles[0] if selected_articles else None
    question_bank_refs, question_bank_meta, question_bank_context = _question_bank_context_for_article(featured_article)
    final_prompt = build_final_generation_prompt(selected_articles, today, selection, question_bank_context=question_bank_context)
    brief = _call_with_fallback(final_prompt, test_mode, stage="writing", contract=True)
    brief["_source_evidence"] = build_evidence_bundle(selected_articles)
    # Preserve selection diagnostics for logging/debug; ensure_brief_schema will ignore unknown fields if needed.
    brief.setdefault("_llm_two_stage", {})
    if isinstance(brief.get("_llm_two_stage"), dict):
        brief["_llm_two_stage"] = {
            "enabled": True,
            "selection": selection,
            "selected_titles": [a.title for a in selected_articles],
            "selected_urls": [a.url for a in selected_articles],
        }
    brief["_question_bank"] = {
        **question_bank_meta,
        "question_bank_refs": question_bank_refs,
    }
    if isinstance(brief.get("daily_question"), dict):
        brief["daily_question"] = _normalize_daily_question_module(brief["daily_question"])
    question_selection_result = select_best_daily_question_candidate(brief, selected_articles, test_mode=test_mode)
    brief = question_selection_result.get("brief") if isinstance(question_selection_result.get("brief"), dict) else brief
    brief["_daily_question_selection"] = {
        "selected_source": question_selection_result.get("selected_source"),
        "candidate_count": len(question_selection_result.get("candidates") or []),
        "fallback_used": bool(question_selection_result.get("fallback_used")),
        "errors": question_selection_result.get("errors") or [],
    }
    return refine_high_risk_modules(brief, selected_articles, test_mode=test_mode)


def generate_brief(articles: list[Article], today: str, test_mode: bool = False, selection_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate the daily brief.

    When test_mode=True, TEST_LLM_MODEL takes precedence so manual FC tests can use
    a cheaper model without changing the production scheduled model. Set
    TEST_LLM_MODEL=mock to avoid calling the LLM API entirely.

    Default production path is two-stage:
    1) LLM selects featured/quick-read articles from compact candidates;
    2) LLM generates the final email from the selected featured article with fuller text.
    """
    model_plan = get_stage_model_plan(test_mode)
    if test_mode and any((model or "").lower() == "mock" for model in model_plan.get("selection", []) + model_plan.get("writing", [])):
        return mock_brief(articles, today)
    if not settings.dashscope_api_key and (settings.run_mode == "test" or test_mode):
        return mock_brief(articles, today)

    if settings.llm_two_stage_enabled:
        return generate_brief_two_stage(articles, today, test_mode=test_mode, selection_context=selection_context)

    # Legacy one-stage fallback.
    featured_article = articles[0] if articles else None
    question_bank_refs, question_bank_meta, question_bank_context = _question_bank_context_for_article(featured_article)
    prompt = build_user_prompt(
        articles,
        today,
        question_bank_context=question_bank_context,
    )
    brief = _call_with_fallback(prompt, test_mode, stage="writing")
    brief["_source_evidence"] = build_evidence_bundle(articles[:3])
    brief["_question_bank"] = {
        **question_bank_meta,
        "question_bank_refs": question_bank_refs,
    }
    if isinstance(brief.get("daily_question"), dict):
        brief["daily_question"] = _normalize_daily_question_module(brief["daily_question"])
    question_selection_result = select_best_daily_question_candidate(brief, articles, test_mode=test_mode)
    brief = question_selection_result.get("brief") if isinstance(question_selection_result.get("brief"), dict) else brief
    brief["_daily_question_selection"] = {
        "selected_source": question_selection_result.get("selected_source"),
        "candidate_count": len(question_selection_result.get("candidates") or []),
        "fallback_used": bool(question_selection_result.get("fallback_used")),
        "errors": question_selection_result.get("errors") or [],
    }
    return brief

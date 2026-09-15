"""受控工具层：把项目现有成熟能力包装成 Agent 可调用的工具。

原则：不重写任何内部算法。每个工具内部延迟 import 现有模块，
只做「输入输出明确化 + 校验 + 工作区落盘」。模型只负责决策
（选哪些文章、是否 PASS / 需要修复哪个模块），确定性步骤全部
由这些工具执行，保证质量门禁、渲染、发布链路与生产一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable, Optional

from config import settings
from agent.state import RunState, load_run, save_run

# ---------------------------------------------------------------------------
# 工作区：每次运行的中间产物（与 run.json 同目录，便于断点续跑）
# ---------------------------------------------------------------------------


def work_dir(delivery_date: str) -> Path:
    from agent.state import run_dir

    return run_dir(delivery_date)


def work_path(delivery_date: str, name: str) -> Path:
    return work_dir(delivery_date) / f"{name}.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_workspace(delivery_date: str, name: str, payload: Any) -> dict[str, Any]:
    path = work_path(delivery_date, name)
    _write_json(path, payload)
    return {"workspace_file": str(path)}


def load_workspace(delivery_date: str, name: str) -> Optional[Any]:
    return _read_json(work_path(delivery_date, name))


def _state_for(delivery_date: str) -> RunState:
    state = load_run(delivery_date)
    if state is None:
        raise RuntimeError(f"No run state for {delivery_date}; orchestrator must create it first.")
    return state


# ---------------------------------------------------------------------------
# Article 对象重建（fetch_articles 返回的 Article 是 dataclass）
# ---------------------------------------------------------------------------


def rebuild_articles(items: list[dict[str, Any]]) -> list[Any]:
    from article_filter import Article

    articles: list[Any] = []
    for item in items or []:
        raw_date = item.get("date")
        parsed_date: Optional[_date] = None
        if isinstance(raw_date, str) and raw_date:
            try:
                parsed_date = _date.fromisoformat(raw_date)
            except ValueError:
                parsed_date = None
        articles.append(
            Article(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                source=str(item.get("source") or ""),
                column=str(item.get("column") or ""),
                date=parsed_date,
                body=list(item.get("body") or []),
                tags=list(item.get("tags") or []),
                themes=list(item.get("themes") or []),
                score=int(item.get("score") or 0),
                evidence=dict(item.get("evidence") or {}),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


def tool_search_articles(delivery_date: str, test_mode: bool = False) -> dict[str, Any]:
    """抓取当天候选文章池，返回文章摘要列表供模型决策选文。"""
    from fetch_articles import get_candidate_articles_with_stats

    articles, article_stats = get_candidate_articles_with_stats()
    items: list[dict[str, Any]] = []
    for idx, article in enumerate(articles):
        body = list(article.body or [])
        items.append(
            {
                "id": idx,
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "column": article.column,
                "date": article.date.isoformat() if article.date else None,
                "published_at": article.published_at,
                "themes": list(article.themes or []),
                "tags": list(article.tags or []),
                "score": int(article.score or 0),
                "body": body,
                "snippet": " ".join(body)[:300],
            }
        )
    save_workspace(delivery_date, "articles", {"items": items, "stats": article_stats})
    compact = [
        {
            "id": item["id"],
            "title": item["title"],
            "source": item["source"],
            "column": item["column"],
            "published_at": item["published_at"],
            "themes": item["themes"],
            "score": item["score"],
            "snippet": item["snippet"],
        }
        for item in items
    ]
    return {
        "tool": "search_articles",
        "delivery_date": delivery_date,
        "count": len(compact),
        "articles": compact,
        "stats_note": "完整抓取诊断见 workspace articles.json",
    }


def tool_select_articles(article_ids: list[Any], delivery_date: str) -> dict[str, Any]:
    """校验模型选中的文章 id 是否合法，返回选中文章（含正文）供生成使用。"""
    data = load_workspace(delivery_date, "articles")
    if not data:
        raise RuntimeError("articles workspace missing; run search_articles first.")
    items = data.get("items") or []
    valid_ids = {int(item["id"]) for item in items}
    ids: list[int] = []
    for raw in article_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value in valid_ids and value not in ids:
            ids.append(value)
    if not ids:
        raise RuntimeError(f"select_articles: no valid article ids in {article_ids!r}")
    selected = [item for item in items if int(item["id"]) in ids]
    state = _state_for(delivery_date)
    state.selected_article_ids = ids
    state.log_event("articles_selected", ids=ids, count=len(selected))
    save_run(state)
    return {
        "tool": "select_articles",
        "selected_ids": ids,
        "count": len(selected),
        "selected": [
            {
                "id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "column": item["column"],
                "published_at": item["published_at"],
                "themes": item["themes"],
                "score": item["score"],
                "body": item.get("body") or [],
            }
            for item in selected
        ],
    }


def tool_generate_brief(delivery_date: str, test_mode: bool = False) -> dict[str, Any]:
    """用已选文章生成晨读 brief（复用 llm_client.generate_brief + brief_schema 校验）。"""
    from brief_schema import ensure_brief_schema
    from llm_client import generate_brief

    data = load_workspace(delivery_date, "articles")
    if not data:
        raise RuntimeError("articles workspace missing; run search_articles first.")
    state = _state_for(delivery_date)
    selected_ids = state.selected_article_ids or []
    items = [item for item in (data.get("items") or []) if int(item.get("id")) in selected_ids]
    if not items:
        raise RuntimeError("No selected articles; run select_articles first.")
    articles = rebuild_articles(items)
    raw_brief = generate_brief(articles, delivery_date, test_mode=test_mode)
    brief, warnings = ensure_brief_schema(raw_brief, delivery_date)
    save_workspace(delivery_date, "brief", brief)
    save_workspace(delivery_date, "brief_warnings", {"warnings": warnings})
    state.log_event("brief_generated", warnings=warnings)
    save_run(state)
    return {
        "tool": "generate_brief",
        "delivery_date": delivery_date,
        "warnings": warnings,
        "brief_summary": _brief_summary(brief),
    }


def _brief_summary(brief: dict[str, Any]) -> dict[str, Any]:
    featured = brief.get("featured_article") if isinstance(brief.get("featured_article"), dict) else {}
    return {
        "email_subject": brief.get("email_subject") or "",
        "featured_title": featured.get("title") or "",
        "featured_theme": featured.get("theme") or featured.get("theme_label") or "",
        "module_keys": sorted(
            k for k in brief.keys() if not k.startswith("_") and isinstance(brief.get(k), (dict, list))
        ),
    }


def tool_render_candidate(delivery_date: str) -> dict[str, Any]:
    """渲染邮件（subject / plain / html），落盘供质检与预览复用。"""
    brief = load_workspace(delivery_date, "brief")
    if not brief:
        raise RuntimeError("brief workspace missing; run generate_brief first.")
    subject = str(brief.get("email_subject") or f"公考晨读 {delivery_date}")
    if not subject.startswith(settings.subject_prefix):
        subject = f"{settings.subject_prefix}{subject}"
    from email_renderer import render_email_html, render_plain_text

    plain_text = render_plain_text(brief)
    html_body = render_email_html(brief)
    save_workspace(
        delivery_date,
        "rendered",
        {"subject": subject, "plain_text": plain_text, "html_body": html_body},
    )
    return {
        "tool": "render_candidate",
        "subject": subject,
        "plain_text_chars": len(plain_text),
        "html_chars": len(html_body),
    }


def tool_audit_candidate(delivery_date: str, test_mode: bool = False) -> dict[str, Any]:
    """跑完整质检（复用 quality_gate.evaluate_all_quality），返回门禁与问题清单。"""
    from quality_gate import build_gate_from_quality_map, evaluate_all_quality

    brief = load_workspace(delivery_date, "brief")
    rendered = load_workspace(delivery_date, "rendered")
    if not brief or not rendered:
        raise RuntimeError("brief/rendered workspace missing; run generate_brief and render_candidate first.")
    plain_text = str(rendered.get("plain_text") or "")
    html_body = str(rendered.get("html_body") or "")
    quality = evaluate_all_quality(brief, plain_text, html_body, test_invocation=test_mode)
    gate = build_gate_from_quality_map(quality, plain_text=plain_text, html_body=html_body)
    save_workspace(delivery_date, "quality", {"quality": quality, "gate": gate})
    issues = _collect_issues(quality, gate)
    p0_modules = {item.get("module") for item in (gate.get("p0_issues") or [])}
    for issue in issues:
        if issue["module"] in p0_modules:
            issue["severity"] = "P0"
    state = _state_for(delivery_date)
    state.log_event(
        "quality_audited",
        overall=gate.get("overall"),
        p0_count=gate.get("p0_count"),
        p1_count=len([i for i in issues if i["severity"] == "P1"]),
    )
    save_run(state)
    return {
        "tool": "audit_candidate",
        "overall": gate.get("overall"),
        "p0_count": gate.get("p0_count", 0),
        "p1_count": len([i for i in issues if i["severity"] == "P1"]),
        "issues": issues,
    }


def _collect_issues(quality: dict[str, Any], gate: dict[str, Any]) -> list[dict[str, str]]:
    from quality_gate import MODULE_LABELS

    issues: list[dict[str, str]] = []
    for key, label in MODULE_LABELS.items():
        module_quality = quality.get(key)
        if not isinstance(module_quality, dict):
            continue
        ok = module_quality.get("ok")
        if ok is False:
            messages = module_quality.get("messages") or module_quality.get("issues") or []
            reason = ""
            if isinstance(messages, list) and messages:
                reason = " | ".join(str(m) for m in messages[:3])
            elif isinstance(messages, str):
                reason = messages
            issues.append(
                {
                    "module": key,
                    "module_label": label,
                    "severity": "P1",
                    "reason": reason[:1000],
                }
            )
    return issues


def tool_repair_candidate(delivery_date: str, test_mode: bool = False) -> dict[str, Any]:
    """对质检失败模块执行定点修复（复用 llm_client.rewrite_failed_modules_once）。"""
    from llm_client import rewrite_failed_modules_once

    brief = load_workspace(delivery_date, "brief")
    data = load_workspace(delivery_date, "articles")
    quality_data = load_workspace(delivery_date, "quality")
    if not brief or not quality_data:
        raise RuntimeError("brief/quality workspace missing; run audit first.")
    state = _state_for(delivery_date)
    selected_ids = state.selected_article_ids or []
    items = [item for item in (data.get("items") or []) if int(item.get("id")) in selected_ids]
    articles = rebuild_articles(items)
    quality = quality_data.get("quality") or {}
    result = rewrite_failed_modules_once(
        brief,
        articles,
        question_quality=quality.get("daily_question") or {},
        framework_quality=quality.get("framework_map") or {},
        takeaway_quality=quality.get("today_takeaway") or None,
        quick_reads_quality=quality.get("quick_reads") or None,
        test_mode=test_mode,
    )
    updated_brief = result.get("brief") or brief
    save_workspace(delivery_date, "brief", updated_brief)
    state.repair_round += 1
    state.log_event(
        "repaired",
        round=state.repair_round,
        rewritten_modules=result.get("rewritten_modules") or [],
        details=result.get("details") or {},
    )
    save_run(state)
    return {
        "tool": "repair_candidate",
        "repair_round": state.repair_round,
        "rewritten_modules": result.get("rewritten_modules") or [],
        "details": result.get("details") or {},
    }


def tool_save_candidate(delivery_date: str, test_mode: bool = False) -> dict[str, Any]:
    """把通过门禁的候选保存为正式候选件（复用 candidate_store）。"""
    from candidate_store import build_candidate_payload, save_candidate

    brief = load_workspace(delivery_date, "brief")
    rendered = load_workspace(delivery_date, "rendered")
    quality_data = load_workspace(delivery_date, "quality")
    articles_data = load_workspace(delivery_date, "articles")
    if not brief or not rendered or not quality_data:
        raise RuntimeError("brief/rendered/quality workspace missing.")
    quality = quality_data.get("quality") or {}
    gate = quality_data.get("gate") or {}
    state = _state_for(delivery_date)
    if gate.get("overall") != "ok":
        raise RuntimeError("quality gate not ok; cannot save candidate.")
    from main import summarize_final_selection

    payload = build_candidate_payload(
        delivery_date=delivery_date,
        subject=str(rendered.get("subject") or ""),
        brief=brief,
        plain_text=str(rendered.get("plain_text") or ""),
        html_body=str(rendered.get("html_body") or ""),
        quality=quality,
        quality_gate=gate,
        article_stats=(articles_data or {}).get("stats") or {},
        final_selection=summarize_final_selection(brief),
    )
    meta = save_candidate(payload)
    save_workspace(delivery_date, "candidate", payload)
    state.candidate_saved = True
    state.log_event("candidate_saved", meta=meta)
    save_run(state)
    return {"tool": "save_candidate", "candidate_saved": True, "meta": meta}


def tool_get_run_status(delivery_date: str) -> dict[str, Any]:
    """只读：返回当前运行状态与断点信息。"""
    state = load_run(delivery_date)
    if state is None:
        return {"tool": "get_run_status", "run_exists": False, "delivery_date": delivery_date}
    return {
        "tool": "get_run_status",
        "run_exists": True,
        "state": state.state,
        "repair_round": state.repair_round,
        "model_calls": state.model_calls,
        "tool_calls": state.tool_calls,
        "selected_article_ids": state.selected_article_ids,
        "candidate_saved": state.candidate_saved,
        "preview_sent": state.preview_sent,
        "published": state.published,
        "sent": state.sent,
        "last_error": state.last_error,
    }


# ---------------------------------------------------------------------------
# 工具注册表（只注册模型可安全调用的工具；发布/发送不在其中）
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    # 是否需要 test_mode 参数（自动注入）
    needs_test_mode: bool = field(default=False)


TOOL_REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict[str, Any], needs_test_mode: bool = False) -> Callable:
    def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOL_REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            fn=fn,
            needs_test_mode=needs_test_mode,
        )
        return fn

    return wrapper


register(
    "search_articles",
    "抓取目标日期候选文章池，返回文章摘要列表（id/title/source/column/themes/snippet）。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
)(tool_search_articles)

register(
    "select_articles",
    "根据 search_articles 返回的文章列表，选择用于生成晨读的文章 id 列表。",
    {
        "article_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "选中的文章 id 列表（来自 search_articles）",
        },
        "delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"},
    },
)(tool_select_articles)

register(
    "generate_brief",
    "用已选文章生成晨读 brief（含今日一题/框架图/速读/金句等模块），返回模块摘要。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
    needs_test_mode=True,
)(tool_generate_brief)

register(
    "render_candidate",
    "渲染邮件（subject/plain/html），供质检与预览使用。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
)(tool_render_candidate)

register(
    "audit_candidate",
    "对候选执行完整质检（质量门禁），返回 overall / p0_count / issues（含失败模块与原因）。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
    needs_test_mode=True,
)(tool_audit_candidate)

register(
    "repair_candidate",
    "对质检失败模块执行定点修复（一次最多修复框架图/今日一题/金句/速读），返回修复模块列表。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
    needs_test_mode=True,
)(tool_repair_candidate)

register(
    "save_candidate",
    "把通过门禁的候选保存为正式候选件（写本地/OSS）。仅在 audit_candidate 返回 overall=ok 时调用。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
    needs_test_mode=True,
)(tool_save_candidate)

register(
    "get_run_status",
    "只读查询当前运行状态（状态机进度/修复轮次/是否已保存）。",
    {"delivery_date": {"type": "string", "description": "目标投递日期 YYYY-MM-DD"}},
)(tool_get_run_status)


def execute_tool(name: str, arguments: dict[str, Any], *, delivery_date: str, test_mode: bool) -> dict[str, Any]:
    """执行工具：统一注入 delivery_date / test_mode，未注册工具直接拒绝。"""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        raise RuntimeError(f"Unknown tool: {name!r}. Allowed: {sorted(TOOL_REGISTRY)}")
    kwargs: dict[str, Any] = dict(arguments or {})
    kwargs["delivery_date"] = delivery_date
    if tool.needs_test_mode:
        kwargs["test_mode"] = test_mode
    result = tool.fn(**kwargs)
    state = load_run(delivery_date)
    if state is not None:
        state.tool_calls += 1
        state.log_event("tool_called", tool=name)
        save_run(state)
    return result


def tool_descriptions() -> str:
    """给模型的工具清单（JSON）。"""
    lines = []
    for name in sorted(TOOL_REGISTRY):
        tool = TOOL_REGISTRY[name]
        lines.append(
            json.dumps(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)

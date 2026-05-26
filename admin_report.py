from __future__ import annotations

import html
import json
from typing import Any

from config import settings
from email_sender import normalize_recipients, send_email_to_recipients
from quality_issue_schema import issue_counts


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _json_text(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) > limit:
        return text[:limit] + "\n... [truncated in report]"
    return text


def _module_rows(quality: dict[str, Any]) -> str:
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    labels = {
        "daily_question": "今日一题",
        "framework_map": "框架图",
        "today_takeaway": "今日可带走",
        "brief_cleanliness": "整封邮件清洁度",
        "content_quality": "内容质量审稿",
    }
    rows: list[str] = []
    for key, label in labels.items():
        item = final.get(key) if isinstance(final.get(key), dict) else {}
        issues = item.get("issues") or []
        issue_text = "无"
        if issues:
            issue_text = "<br>".join(
                f"{_e(issue.get('severity'))} / {_e(issue.get('code'))}: {_e(issue.get('message'))}"
                for issue in issues[:6]
                if isinstance(issue, dict)
            )
        rows.append(
            "<tr>"
            f"<td>{_e(label)}</td>"
            f"<td>{_e(item.get('status') or ('ok' if item.get('ok') else 'review'))}</td>"
            f"<td>{_e(item.get('score', ''))}</td>"
            f"<td>{issue_text}</td>"
            "</tr>"
        )
    return "".join(rows)


def _p0_list(quality_gate: dict[str, Any]) -> str:
    issues = quality_gate.get("p0_issues") or []
    if not issues:
        return "<li>无 P0 阻断项</li>"
    return "".join(
        f"<li>{_e(issue.get('module'))} / {_e(issue.get('code'))}: {_e(issue.get('message'))}</li>"
        for issue in issues
        if isinstance(issue, dict)
    )


def _rewrite_text(quality: dict[str, Any]) -> str:
    rewrite = quality.get("rewrite")
    if not rewrite:
        return "未触发"
    modules = rewrite.get("rewritten_modules") if isinstance(rewrite, dict) else []
    if modules:
        return "已重写：" + "、".join(str(item) for item in modules)
    if isinstance(rewrite, dict) and rewrite.get("error"):
        return "重写失败：" + str(rewrite.get("error"))
    if isinstance(rewrite, dict) and rewrite.get("details", {}).get("rewrite_skipped"):
        return str(rewrite.get("details", {}).get("rewrite_skipped"))
    return "未重写"


def _rewrite_comparison_html(candidate: dict[str, Any]) -> str:
    rows = candidate.get("rewrite_comparison") or []
    if not rows:
        return "<p>未触发模块重写。</p>"
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        quality_after = row.get("quality_after") if isinstance(row.get("quality_after"), dict) else {}
        issues_before = row.get("issues_before") if isinstance(row.get("issues_before"), list) else []
        issue_text = "无"
        if issues_before:
            issue_text = "<br>".join(
                f"{_e(item.get('severity'))} / {_e(item.get('code'))}: {_e(item.get('message'))}"
                for item in issues_before[:5]
                if isinstance(item, dict)
            )
        parts.append(
            "<div style='border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:10px 0;'>"
            f"<p style='margin:0 0 8px;'><strong>{_e(row.get('module'))}</strong>，changed={_e(row.get('changed'))}，重写后状态={_e(quality_after.get('status'))}，分数={_e(quality_after.get('score'))}</p>"
            f"<p style='margin:0 0 8px;'>重写前问题：<br>{issue_text}</p>"
            "<table style='width:100%;border-collapse:collapse;font-size:13px;'><tr>"
            "<th align='left' style='width:50%;border-top:1px solid #e5e7eb;padding-top:8px;'>重写前</th>"
            "<th align='left' style='width:50%;border-top:1px solid #e5e7eb;padding-top:8px;'>重写后</th>"
            "</tr><tr>"
            f"<td style='vertical-align:top;white-space:pre-wrap;padding-right:10px;'>{_e(_json_text(row.get('before')))}</td>"
            f"<td style='vertical-align:top;white-space:pre-wrap;padding-left:10px;'>{_e(_json_text(row.get('after')))}</td>"
            "</tr></table></div>"
        )
    return "".join(parts) if parts else "<p>未触发模块重写。</p>"


def _rewrite_comparison_plain(candidate: dict[str, Any]) -> list[str]:
    rows = candidate.get("rewrite_comparison") or []
    if not rows:
        return ["自动修复记录：未触发模块重写"]
    lines = ["自动修复记录："]
    for row in rows:
        if not isinstance(row, dict):
            continue
        quality_after = row.get("quality_after") if isinstance(row.get("quality_after"), dict) else {}
        lines.extend(
            [
                f"- 模块：{row.get('module')}，changed={row.get('changed')}，重写后状态={quality_after.get('status')}，分数={quality_after.get('score')}",
                f"  重写前：{_json_text(row.get('before'), 500)}",
                f"  重写后：{_json_text(row.get('after'), 500)}",
            ]
        )
    return lines


def _module_rows(quality: dict[str, Any]) -> str:
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    labels = {
        "daily_question": "今日一题",
        "framework_map": "框架图",
        "today_takeaway": "今日可带走",
        "brief_cleanliness": "整封邮件清洁度",
        "quick_reads": "速读",
        "duplication": "跨模块重复",
        "expression_quality": "表达质量",
        "content_risk": "内容风险小修",
        "content_quality": "内容质量审稿",
    }
    rows: list[str] = []
    for key, label in labels.items():
        item = final.get(key) if isinstance(final.get(key), dict) else {}
        issues = item.get("issues") or []
        issue_text = "无"
        if issues:
            issue_text = "<br>".join(
                f"{_e(issue.get('level') or issue.get('severity'))} / {_e(issue.get('code'))}: {_e(issue.get('message'))}"
                for issue in issues[:6]
                if isinstance(issue, dict)
            )
        rows.append(
            "<tr>"
            f"<td>{_e(label)}</td>"
            f"<td>{_e(item.get('status') or ('ok' if item.get('ok') else 'review'))}</td>"
            f"<td>{_e(item.get('score', ''))}</td>"
            f"<td>{issue_text}</td>"
            "</tr>"
        )
    return "".join(rows)


def _collect_remaining_issues(quality: dict[str, Any], limit: int = 8) -> list[str]:
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    rows: list[str] = []
    for module, result in final.items():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            rows.append(f"- {module} / {issue.get('level') or issue.get('severity')} / {issue.get('code')}: {issue.get('message')}")
            if len(rows) >= limit:
                return rows
    return rows


def _minor_fix_lines(quality: dict[str, Any]) -> list[str]:
    minor = quality.get("minor_auto_fix") if isinstance(quality.get("minor_auto_fix"), dict) else {}
    fixes = minor.get("fixes") if isinstance(minor.get("fixes"), list) else []
    if not fixes:
        return ["- 未触发字段级小修。"]
    lines: list[str] = []
    for fix in fixes[:12]:
        if not isinstance(fix, dict):
            continue
        lines.append(f"- {fix.get('field')}: {fix.get('bad_text')} -> {fix.get('replacement')} ({fix.get('code')})")
    return lines or ["- 未触发字段级小修。"]


DIMENSION_LABELS = {
    "topic_fit": ("选题价值", 20),
    "user_safety": ("用户安全感", 15),
    "exam_value": ("考场转化", 20),
    "source_alignment": ("文章理解", 15),
    "information_gain": ("用户获得感", 10),
    "naturalness": ("表达自然度", 10),
    "module_coherence": ("模块协同", 5),
    "cleanliness": ("移动端友好", 5),
}


def _clip_inline(value: Any, limit: int = 120) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _content_score_lines(content_quality: dict[str, Any]) -> list[str]:
    scores = content_quality.get("scores") if isinstance(content_quality.get("scores"), dict) else {}
    if not scores:
        return ["- 暂无内容审稿八维评分。"]
    lines: list[str] = []
    for key, (label, max_score) in DIMENSION_LABELS.items():
        value = scores.get(key, "")
        lines.append(f"- {label}：{value}/{max_score}")
    return lines


def _walk_values(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _auto_fix_summary_lines(candidate: dict[str, Any], quality: dict[str, Any], limit: int = 10) -> list[str]:
    rows: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    minor = quality.get("minor_auto_fix") if isinstance(quality.get("minor_auto_fix"), dict) else {}
    for fix in minor.get("fixes") or []:
        if not isinstance(fix, dict):
            continue
        key = (
            str(fix.get("field") or fix.get("module") or ""),
            str(fix.get("code") or ""),
            _clip_inline(fix.get("bad_text"), 160),
            _clip_inline(fix.get("replacement"), 160),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            f"{len(rows) + 1}. {fix.get('field') or fix.get('module')}\n"
            f"   - 问题：{fix.get('code')}\n"
            f"   - 修复：{_clip_inline(fix.get('bad_text'))} -> {_clip_inline(fix.get('replacement'))}"
        )
        if len(rows) >= limit:
            return rows

    rewrite = quality.get("rewrite") if isinstance(quality.get("rewrite"), dict) else {}
    if not rewrite.get("rolled_back"):
        for node in _walk_values(rewrite):
            if not isinstance(node, dict) or node.get("rolled_back"):
                continue
            for item in node.get("content_issue_rewrites") or node.get("rewrites") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("field") or item.get("module") or ""),
                    str(item.get("issue_code") or item.get("reason") or ""),
                    _clip_inline(item.get("before"), 160),
                    _clip_inline(item.get("after"), 160),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    f"{len(rows) + 1}. {item.get('field') or item.get('module')}\n"
                    f"   - 问题：{item.get('issue_code') or item.get('reason')}\n"
                    f"   - 修复：{_clip_inline(item.get('before'))} -> {_clip_inline(item.get('after'))}"
                )
                if len(rows) >= limit:
                    return rows

    for row in candidate.get("rewrite_comparison") or quality.get("rewrite_comparison") or []:
        if not isinstance(row, dict) or not row.get("changed"):
            continue
        key = (
            str(row.get("module") or ""),
            "module_rewrite",
            _clip_inline(row.get("before"), 160),
            _clip_inline(row.get("after"), 160),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            f"{len(rows) + 1}. {row.get('module')}\n"
            f"   - 问题：模块级重写\n"
            f"   - 修复：{_clip_inline(row.get('before'))} -> {_clip_inline(row.get('after'))}"
        )
        if len(rows) >= limit:
            return rows

    return rows or ["- 未触发自动修复。"]


def _remaining_issue_items(quality: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    rows: list[dict[str, Any]] = []
    for module, result in final.items():
        if not isinstance(result, dict):
            continue
        for issue in result.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            rows.append(
                {
                    "module": module,
                    "level": issue.get("level") or issue.get("severity") or "",
                    "severity": issue.get("severity") or "",
                    "code": issue.get("code") or "",
                    "message": issue.get("message") or "",
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def _remaining_risk_lines(quality: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    rows = _remaining_issue_items(quality)
    if not rows:
        return ["- 暂无剩余结构化风险。"]
    blocking_codes = {str(item.get("code") or "") for item in gate.get("p0_issues") or [] if isinstance(item, dict)}
    lines = []
    for item in rows:
        impact = "影响发送" if item["code"] in blocking_codes or str(item["level"]).lower() in {"high", "p0"} else "不影响发送，建议关注"
        lines.append(f"- {item['module']} / {item['level']} / {item['code']}：{item['message']}（{impact}）")
    return lines


def _modules_to_review(quality: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    modules: list[str] = []
    for issue in gate.get("p0_issues") or []:
        if isinstance(issue, dict) and issue.get("module") and issue.get("module") not in modules:
            modules.append(str(issue.get("module")))
    for item in _remaining_issue_items(quality):
        level = str(item.get("level") or item.get("severity") or "").lower()
        if level in {"p1", "medium", "high", "p0"} and item.get("module") not in modules:
            modules.append(str(item.get("module")))
    return modules


def _manual_review_decision(quality: dict[str, Any], gate: dict[str, Any], content_quality: dict[str, Any]) -> tuple[str, str]:
    status = str(gate.get("overall") or "unknown")
    modules = _modules_to_review(quality, gate)
    if status != "ok":
        return "是", "质量门禁未通过，至少检查 " + ("、".join(modules[:4]) if modules else "P0 明细")
    if content_quality.get("needs_manual_full_review"):
        return "是", "内容审稿低于阈值且未定位到可自动修复字段，建议通读全文。"
    if modules:
        return "否", "、".join(modules[:4])
    return "否", "无"


def _send_conclusion(gate: dict[str, Any], quality: dict[str, Any], content_quality: dict[str, Any]) -> str:
    status = str(gate.get("overall") or "unknown")
    if status != "ok":
        return "阻断发送"
    modules = _modules_to_review(quality, gate)
    if content_quality.get("needs_manual_full_review") or modules:
        return "建议人工看一眼"
    return "可直接发送"


def _build_quality_card_markdown_legacy(candidate: dict[str, Any]) -> str:
    delivery_date = str(candidate.get("delivery_date") or "")
    subject = str(candidate.get("subject") or "")
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    counts = issue_counts(quality)
    status = str(gate.get("overall") or "unknown")
    send_decision = "可发" if status == "ok" else "阻断"
    content_quality = final.get("content_quality") if isinstance(final.get("content_quality"), dict) else {}
    content_risk = final.get("content_risk") if isinstance(final.get("content_risk"), dict) else {}
    remaining = _collect_remaining_issues(quality) or ["- 暂无剩余结构化风险。"]
    lines = [
        "# 发送前质量卡",
        "",
        f"- 日期：{delivery_date}",
        f"- 标题：{subject}",
        f"- 最终结论：{send_decision}",
        f"- quality_gate：{status}",
        f"- P0/P1/P2：{counts['P0']} / {counts['P1']} / {counts['P2']}",
        "",
        "## 一、门禁结果",
        "",
        f"- P0 数量：{gate.get('p0_count', 0)}",
        f"- 内容风险状态：{content_risk.get('status') or 'unknown'}，分数：{content_risk.get('score', '')}",
        f"- 内容审稿状态：{content_quality.get('status') or 'unknown'}，分数：{content_quality.get('score', '')}",
        "",
        "## 二、字段级自动小修",
        "",
        *_minor_fix_lines(quality),
        "",
        "## 三、剩余风险",
        "",
        *remaining,
        "",
        "## 四、一句话判断",
        "",
        str(content_quality.get("one_sentence_judgment") or ("质量门禁通过，可以进入早晨发送链路。" if status == "ok" else "质量门禁未通过，暂不应发送。")),
        "",
    ]
    return "\n".join(lines)


def build_quality_card_markdown(candidate: dict[str, Any]) -> str:
    delivery_date = str(candidate.get("delivery_date") or "")
    subject = str(candidate.get("subject") or "")
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    final = quality.get("final") if isinstance(quality.get("final"), dict) else {}
    counts = issue_counts(quality)
    status = str(gate.get("overall") or "unknown")
    content_quality = final.get("content_quality") if isinstance(final.get("content_quality"), dict) else {}
    content_risk = final.get("content_risk") if isinstance(final.get("content_risk"), dict) else {}
    manual_review, review_scope = _manual_review_decision(quality, gate, content_quality)
    send_conclusion = _send_conclusion(gate, quality, content_quality)

    lines = [
        f"# 发送前质量卡结论：{send_conclusion}",
        "",
        f"- 日期：{delivery_date}",
        f"- 标题：{subject}",
        f"- quality_gate：{status}",
        f"- P0/P1/P2：{counts['P0']} / {counts['P1']} / {counts['P2']}",
        f"- 是否需要人工通读全文：{manual_review}",
        f"- 只需关注：{review_scope}",
        "",
        "## 内容质量八维评分",
        "",
        *_content_score_lines(content_quality),
        "",
        "## 门禁与发送判断",
        "",
        f"- P0 数量：{gate.get('p0_count', 0)}",
        f"- 内容风险状态：{content_risk.get('status') or 'unknown'}，分数：{content_risk.get('score', '')}",
        f"- 内容审稿状态：{content_quality.get('status') or 'unknown'}，分数：{content_quality.get('score', '')}",
        f"- 发送结论：{send_conclusion}",
        "",
        "## 自动修复摘要",
        "",
        *_auto_fix_summary_lines(candidate, quality),
        "",
        "## 剩余风险",
        "",
        *_remaining_risk_lines(quality, gate),
        "",
        "## 人工检查建议",
        "",
        f"- 是否需要通读全文：{manual_review}",
        f"- 检查范围：{review_scope}",
        "",
        "## 一句话判断",
        "",
        str(content_quality.get("one_sentence_judgment") or ("质量门禁通过，可以进入发送链路。" if status == "ok" else "质量门禁未通过，暂不应发送。")),
        "",
    ]
    return "\n".join(lines)


def build_admin_quality_report(candidate: dict[str, Any], candidate_save_result: dict[str, Any] | None = None) -> tuple[str, str, str]:
    candidate_save_result = candidate_save_result or {}
    delivery_date = str(candidate.get("delivery_date") or "")
    subject = str(candidate.get("subject") or "")
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    quality_gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    final_selection = candidate.get("final_selection") if isinstance(candidate.get("final_selection"), dict) else {}
    featured = final_selection.get("featured") if isinstance(final_selection.get("featured"), dict) else {}
    quick_reads = final_selection.get("quick_reads") if isinstance(final_selection.get("quick_reads"), list) else []
    blocked_archive = candidate.get("blocked_archive") if isinstance(candidate.get("blocked_archive"), dict) else {}
    status = str(quality_gate.get("overall") or "unknown")
    p0_count = int(quality_gate.get("p0_count") or 0)
    candidate_path = candidate_save_result.get("candidate_oss_path") or candidate_save_result.get("candidate_local_path") or ""
    latest_path = candidate_save_result.get("candidate_latest_local_path") or ""
    blocked_archive_path = blocked_archive.get("blocked_archive_path") or ""
    admin_subject = f"【质检报告】{delivery_date} 公考晨读候选：{status.upper()} / P0={p0_count}"
    plain_lines = [
        f"交付日期：{delivery_date}",
        f"候选状态：{status}",
        f"P0 数量：{p0_count}",
        f"邮件标题：{subject}",
        f"候选文件：{candidate_path}",
        f"latest：{latest_path}",
        f"失败留档：{blocked_archive_path or '无'}",
        f"重写情况：{_rewrite_text(quality)}",
        "",
        "P0 明细：",
    ]
    p0_issues = quality_gate.get("p0_issues") or []
    if p0_issues:
        plain_lines.extend(
            f"- {item.get('module')} / {item.get('code')}: {item.get('message')}"
            for item in p0_issues
            if isinstance(item, dict)
        )
    else:
        plain_lines.append("- 无")
    plain_lines.extend(["", *_rewrite_comparison_plain(candidate), "", f"精读：{featured.get('title') or ''}"])
    for idx, item in enumerate(quick_reads[:3], start=1):
        if isinstance(item, dict):
            plain_lines.append(f"速读{idx}：{item.get('title') or ''}")

    quality_card = candidate.get("quality_card_markdown") or build_quality_card_markdown(candidate)
    plain_lines.extend(["", "发送前质量卡：", quality_card])

    html_body = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{_e(admin_subject)}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,Arial,sans-serif;line-height:1.6;color:#111827;background:#f8fafc;margin:0;padding:20px;">
  <div style="max-width:920px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:20px;">
    <h2 style="margin:0 0 12px;font-size:20px;">{_e(delivery_date)} 候选邮件质检报告</h2>
    <p style="margin:0 0 12px;">门禁状态：<strong>{_e(status.upper())}</strong>，P0：<strong>{p0_count}</strong></p>
    <p style="margin:0 0 12px;">邮件标题：{_e(subject)}</p>
    <p style="margin:0 0 12px;">重写情况：{_e(_rewrite_text(quality))}</p>
    <p style="margin:0 0 16px;">候选文件：{_e(candidate_path)}<br>latest：{_e(latest_path)}<br>失败留档：{_e(blocked_archive_path or '无')}</p>
    <h3 style="font-size:16px;margin:18px 0 8px;">P0 明细</h3>
    <ul>{_p0_list(quality_gate)}</ul>
    <h3 style="font-size:16px;margin:18px 0 8px;">模块质检</h3>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <thead><tr><th align="left">模块</th><th align="left">状态</th><th align="left">分数</th><th align="left">问题</th></tr></thead>
      <tbody>{_module_rows(quality)}</tbody>
    </table>
    <h3 style="font-size:16px;margin:18px 0 8px;">自动修复前后对比</h3>
    {_rewrite_comparison_html(candidate)}
    <h3 style="font-size:16px;margin:18px 0 8px;">选题</h3>
    <p>精读：{_e(featured.get('title'))}</p>
    <ul>{"".join(f"<li>{_e(item.get('title'))}</li>" for item in quick_reads[:3] if isinstance(item, dict))}</ul>
  </div>
</body>
</html>"""
    html_body = html_body.replace(
        "</div>\n</body>",
        f"<h3 style=\"font-size:16px;margin:18px 0 8px;\">发送前质量卡</h3><pre style=\"white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;\">{_e(quality_card)}</pre></div>\n</body>",
    )
    return admin_subject, "\n".join(plain_lines), html_body


def send_admin_quality_report(candidate: dict[str, Any], candidate_save_result: dict[str, Any] | None = None) -> dict[str, Any]:
    recipients = normalize_recipients(settings.admin_report_emails)
    if not settings.admin_report_enabled:
        return {"admin_report_sent": False, "admin_report_skip_reason": "ADMIN_REPORT_ENABLED=false"}
    if not settings.admin_report_send_email:
        return {"admin_report_sent": False, "admin_report_skip_reason": "ADMIN_REPORT_SEND_EMAIL=false", "admin_report_recipient_count": len(recipients)}
    if not recipients:
        return {"admin_report_sent": False, "admin_report_skip_reason": "ADMIN_REPORT_EMAILS_EMPTY", "admin_report_recipient_count": 0}
    subject, plain_text, html_body = build_admin_quality_report(candidate, candidate_save_result)
    candidate_html = str(candidate.get("html_body") or "")
    candidate_plain = str(candidate.get("plain_text") or "")
    delivery_date = str(candidate.get("delivery_date") or "candidate")
    result = send_email_to_recipients(
        subject,
        plain_text,
        html_body,
        recipients,
        recipient_source="ADMIN_REPORT_EMAILS",
        attachments=[
            {
                "filename": "latest_quality.json",
                "content": json.dumps(candidate.get("quality") or {}, ensure_ascii=False, indent=2),
                "content_type": "application/json",
            },
            {
                "filename": "latest_content_quality.json",
                "content": json.dumps((candidate.get("quality") or {}).get("final", {}).get("content_quality") or {}, ensure_ascii=False, indent=2),
                "content_type": "application/json",
            },
            {
                "filename": "rewrite_comparison.json",
                "content": json.dumps(candidate.get("rewrite_comparison") or [], ensure_ascii=False, indent=2),
                "content_type": "application/json",
            },
            {
                "filename": "latest_quality_card.md",
                "content": candidate.get("quality_card_markdown") or build_quality_card_markdown(candidate),
                "content_type": "text/markdown; charset=utf-8",
            },
            {
                "filename": f"candidate_email_{delivery_date}.html",
                "content": candidate_html,
                "content_type": "text/html; charset=utf-8",
            },
            {
                "filename": f"candidate_email_{delivery_date}.txt",
                "content": candidate_plain,
                "content_type": "text/plain; charset=utf-8",
            },
        ],
    )
    return {
        "admin_report_sent": int(result.get("success_count", 0)) > 0,
        "admin_report_recipient_count": len(recipients),
        **result,
    }

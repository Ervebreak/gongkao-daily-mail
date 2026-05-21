from __future__ import annotations

"""今日一题质量检查（只检查 + 打日志，不改写内容）。

目标：在大模型生成 brief 后、邮件渲染前，对 daily_question 做轻量规则质检，
把结果写入日志，便于后续观察题目是否过宏观、是否缺身份/场景/矛盾/任务。

本文件不调用大模型，不改变 brief 内容，因此不会增加额度消耗，也不会影响发送结果。
"""

import re
from typing import Any


IDENTITY_KEYWORDS = [
    "你是", "假如你是", "作为", "被派驻", "被安排", "领导安排", "调研组", "工作组",
    "工作人员", "干部", "负责人", "窗口", "专班", "驻村", "社区", "街道", "乡镇", "县级部门",
    "执法人员", "网格员", "选调生", "村干部", "部门负责人", "分管", "成员",
]

SCENE_KEYWORDS = [
    "社区", "街道", "乡镇", "村", "县", "市", "区", "基层", "窗口", "部门", "单位", "企业",
    "学校", "高校", "园区", "小区", "群众", "农户", "项目", "现场", "辖区", "政务服务",
    "基层治理", "执法", "调研", "整改", "推进", "落实", "服务站", "中心",
]

CONFLICT_KEYWORDS = [
    "质疑", "反映", "抱怨", "投诉", "争议", "矛盾", "分歧", "不满", "担心", "不愿",
    "不敢", "不会", "不足", "缺乏", "短板", "困难", "问题", "风险", "压力", "堵点",
    "推进缓慢", "不配合", "不到位", "不理解", "失灵", "偏差", "亏损", "乱象", "整改",
]

TASK_KEYWORDS = [
    "怎么办", "怎么做", "如何", "请提出", "提出", "谈谈", "说明", "回应", "协调", "开展",
    "推进", "处理", "解决", "破解", "落实", "建议", "举措", "路径", "工作思路", "你的理解",
]

BROAD_PATTERNS = [
    r"^你怎么看[^，。？?]{0,20}[？?]?$",
    r"^谈谈你对[^，。？?]{0,24}的理解[。？?]?$",
    r"^请谈谈你对[^，。？?]{0,24}的看法[。？?]?$",
    r"^如何理解[^，。？?]{0,24}[。？?]?$",
]

GENERIC_BIG_WORDS = [
    "高质量发展", "基层治理现代化", "新质生产力", "中国式现代化", "乡村振兴", "生态文明",
    "文化自信", "共同富裕", "营商环境", "治理现代化",
]

INSTRUCTION_STYLE_PATTERNS = [
    "复述本题", "口头复述", "核心对策框架", "重点练习", "逻辑串联",
    "训练你的表达", "请用30秒口头复述", "练习评估", "练习供给", "练习监管",
]

INTERVIEW_STYLE_MARKERS = [
    "你是", "作为", "领导让你", "请你牵头", "你会怎么做", "你会如何",
    "工作人员", "负责人", "接到通知", "安排你",
]

POLICY_REPORT_PHRASES = [
    "持续完善", "切实提升", "不断夯实", "形成合力", "强化保障", "推动形成",
    "建立健全", "扎实推进", "全面提升", "系统推进", "长效机制",
]

TRUNCATION_MARKERS = ["……", "...", "…", "..", "标…", "同步培育…", "最后还要在机制"]
DANGLING_ENDINGS = (
    "通过",
    "由于",
    "为了",
    "围绕",
    "依靠",
    "立足",
    "推动",
    "促进",
    "实现",
    "提升",
    "强化",
    "完善",
    "构建",
    "形成",
    "建立",
    "转向",
    "转为",
    "赋能",
    "配套",
    "让",
    "把",
    "与",
    "和",
    "及",
    "并",
    "但",
    "而",
    "在",
    "为",
    "的",
    "监",
)


MATERIAL_DEPENDENCY_TERMS = [
    "\u6839\u636e\u6750\u6599",
    "\u6839\u636e\u7ed9\u5b9a\u8d44\u6599",
    "\u7ed3\u5408\u6750\u6599",
    "\u7ed3\u5408\u7ed9\u5b9a\u8d44\u6599",
    "\u7ed9\u5b9a\u8d44\u6599",
    "\u6750\u6599\u4e00",
    "\u6750\u6599\u4e8c",
    "\u6750\u6599\u4e09",
    "\u6750\u6599\u56db",
    "\u6750\u6599\u4e94",
]

ANSWER_ROUTE_TERMS = [
    "首先", "其次", "再次", "最后", "先", "再", "一是", "二是", "三是", "第一", "第二", "第三",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " / ".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return " / ".join(_text(item) for item in value.values() if _text(item))
    return str(value).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _keyword_hits(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text][:limit]


def _last_clause(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[，,；;。！？]", text) if part.strip()]
    return parts[-1] if parts else text.strip()


def _looks_incomplete(text: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if any(marker in value for marker in TRUNCATION_MARKERS):
        return True
    if value.endswith(DANGLING_ENDINGS):
        return True
    clause = _last_clause(value)
    if clause.startswith(("让", "把")) and len(clause) <= 10:
        return True
    if clause.startswith(("通过", "依靠", "围绕", "立足")) and len(clause) <= 14:
        return True
    if value.endswith(("，", "、", "：", "；", ",", ":", ";")):
        return True
    return False


def _is_too_broad(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    if len(compact) < 42 and any(word in compact for word in GENERIC_BIG_WORDS):
        return True
    return any(re.search(pattern, compact) for pattern in BROAD_PATTERNS)


def _extract_relevance_tokens(brief: dict[str, Any]) -> list[str]:
    featured = brief.get("featured_article") or {}
    candidates = [
        brief.get("today_theme"),
        featured.get("title"),
        featured.get("theme"),
        featured.get("article_type"),
        featured.get("source"),
    ]
    # 兼容一些字段名
    if isinstance(featured, dict):
        candidates.extend([
            featured.get("summary"),
            featured.get("one_sentence"),
            featured.get("core_viewpoint"),
        ])
    text = " ".join(_text(item) for item in candidates if _text(item))
    # 抽取 2-6 字中文词片段，尽量只保留有辨识度的主题词
    tokens: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}", text):
        if token in {"人民日报", "新华社", "光明网", "浙江宣传", "人民网", "来源", "主题", "文章"}:
            continue
        if len(token) < 2:
            continue
        if token not in tokens:
            tokens.append(token)
        if len(tokens) >= 24:
            break
    return tokens


def _compact_for_overlap(text: str) -> str:
    return re.sub(r"\s+", "", _text(text))


def _has_long_overlap(source: str, target: str, min_chars: int = 12) -> bool:
    source = _compact_for_overlap(source)
    target = _compact_for_overlap(target)
    if len(source) < min_chars or len(target) < min_chars:
        return False
    for start in range(0, len(source) - min_chars + 1):
        piece = source[start:start + min_chars]
        if piece and piece in target:
            return True
    return False


def evaluate_daily_question(brief: dict[str, Any]) -> dict[str, Any]:
    """返回 today_question 的质检结果；不修改 brief。"""
    question_obj = brief.get("daily_question") or {}
    if not isinstance(question_obj, dict):
        question_obj = {}

    question = _text(question_obj.get("question") or brief.get("today_question") or "")
    question_type = _text(question_obj.get("question_type") or question_obj.get("type"))
    answer_framework = question_obj.get("answer_framework") or question_obj.get("answer_frame") or []
    exam_focus = _text(question_obj.get("exam_focus"))
    breaking_hint = _text(question_obj.get("breaking_hint") or question_obj.get("breaking_direction"))
    candidate_answer = _text(question_obj.get("candidate_answer"))
    output_prompt = _text(question_obj.get("output_prompt"))
    output_sentence_template = _text(question_obj.get("output_sentence_template"))
    thirty_second_answer = _text(question_obj.get("thirty_second_answer") or output_sentence_template)

    issues: list[dict[str, str]] = []
    hints: list[str] = []

    if not question:
        issues.append({"severity": "high", "code": "missing_question", "message": "今日一题为空"})
        return {
            "ok": False,
            "status": "fail",
            "score": 0,
            "question": "",
            "question_type": question_type,
            "issues": issues,
            "hints": ["需要让模型基于精读文章重新生成今日一题。"],
        }

    length = len(question)
    has_identity = _contains_any(question, IDENTITY_KEYWORDS)
    has_scene = _contains_any(question, SCENE_KEYWORDS)
    has_conflict = _contains_any(question, CONFLICT_KEYWORDS)
    has_task = _contains_any(question, TASK_KEYWORDS)
    too_broad = _is_too_broad(question)
    material_dependency_hits = _keyword_hits(question, MATERIAL_DEPENDENCY_TERMS, limit=8)

    if length < 45:
        issues.append({"severity": "medium", "code": "too_short", "message": "题干偏短，可能不够具体"})
    if length > 260:
        issues.append({"severity": "low", "code": "too_long", "message": "题干偏长，手机阅读和考场复述成本较高"})
    if not has_identity:
        issues.append({"severity": "medium", "code": "missing_identity", "message": "缺少明确身份，如街道工作人员、调研组成员、窗口负责人等"})
    if not has_scene:
        issues.append({"severity": "medium", "code": "missing_scene", "message": "缺少具体场景，如社区、县域、窗口、项目推进、群众工作等"})
    if not has_conflict:
        issues.append({"severity": "medium", "code": "missing_conflict", "message": "缺少现实矛盾，如群众质疑、推进困难、部门协同不顺、资源不足等"})
    if not has_task:
        issues.append({"severity": "high", "code": "missing_task", "message": "缺少明确作答任务，如如何回应、如何推进、提出举措等"})
    if too_broad:
        issues.append({"severity": "high", "code": "too_broad", "message": "题目可能过于宏观，像讨论题而不像公考题"})

    if material_dependency_hits:
        issues.append({"severity": "medium", "code": "daily_question_material_dependency", "message": "今日一题含材料依赖表达，最终题干应脱离原始申论材料也能独立作答"})

    if not isinstance(answer_framework, list) or len([x for x in answer_framework if _text(x)]) < 2:
        issues.append({"severity": "medium", "code": "weak_answer_framework", "message": "作答框架少于2条，可能不够可操作"})
    framework_items = [_text(x) for x in answer_framework if _text(x)] if isinstance(answer_framework, list) else []
    if any(len(item) > 45 for item in framework_items):
        issues.append({"severity": "medium", "code": "answer_framework_too_long", "message": "作答框架应为关键词式骨架，每点不超过45字，完整展开应放在考生版参考答案中"})
    if candidate_answer and any(_has_long_overlap(item, candidate_answer, min_chars=12) for item in framework_items):
        issues.append({"severity": "medium", "code": "answer_framework_duplicates_candidate_answer", "message": "作答框架与考生版参考答案存在较长重复，应压缩成骨架，避免逐句复述"})
    if not exam_focus:
        issues.append({"severity": "low", "code": "missing_exam_focus", "message": "缺少审题关键"})
    elif len(_keyword_hits(exam_focus, ANSWER_ROUTE_TERMS, limit=12)) >= 2:
        issues.append({"severity": "medium", "code": "exam_focus_too_answer_like", "message": "审题关键写成了作答路线，应只拆题，不提前展开对策"})
    if not breaking_hint:
        issues.append({"severity": "low", "code": "missing_breaking_hint", "message": "缺少作答主线：需要用一句话说明本题切入逻辑"})
    else:
        if any(_has_long_overlap(breaking_hint, item, min_chars=8) for item in framework_items):
            issues.append({"severity": "medium", "code": "breaking_hint_duplicates_framework", "message": "作答主线与作答框架重复，应压缩为一句总路线"})
        breaking_route_hits = _keyword_hits(breaking_hint, ANSWER_ROUTE_TERMS, limit=12)
        semicolon_count = breaking_hint.count("；") + breaking_hint.count(";")
        if semicolon_count >= 2 or len([hit for hit in ["一是", "二是", "三是"] if hit in breaking_hint]) >= 2 or (len(breaking_hint) > 80 and (semicolon_count >= 1 or len(breaking_route_hits) >= 2)):
            issues.append({"severity": "medium", "code": "breaking_hint_too_framework_like", "message": "作答主线过长，容易变成第二套作答框架"})
    if not candidate_answer:
        issues.append({"severity": "high", "code": "missing_candidate_answer", "message": "缺少考生版参考答案"})
    elif len(candidate_answer) < 180:
        issues.append({"severity": "medium", "code": "candidate_answer_too_short", "message": "考生版参考答案偏短，可能不够可模仿"})
    if not thirty_second_answer and not output_sentence_template:
        issues.append({"severity": "medium", "code": "missing_thirty_second_answer", "message": "缺少30秒输出参考句式"})

    output_joined = " ".join([output_prompt, output_sentence_template, thirty_second_answer])
    instruction_hits = _keyword_hits(output_joined, INSTRUCTION_STYLE_PATTERNS, limit=6)
    if instruction_hits:
        issues.append({
            "severity": "medium",
            "code": "thirty_second_output_too_instructional",
            "message": "30秒输出偏教研指令，建议改成考生可模仿的开头表态句",
        })

    shenlun_like_type = any(word in question_type for word in ["申论", "对策", "综合分析", "贯彻执行"])
    interview_hits = _keyword_hits(question, INTERVIEW_STYLE_MARKERS, limit=8)
    if shenlun_like_type and len(interview_hits) >= 2:
        issues.append({
            "severity": "low",
            "code": "question_too_interview_like",
            "message": "题型偏申论，但题干有较明显的面试/机关实务口吻，可考虑改成“某地出现……请提出对策”的材料题形式",
        })

    policy_hits = _keyword_hits(candidate_answer, POLICY_REPORT_PHRASES, limit=8)
    if len(policy_hits) >= 4:
        issues.append({
            "severity": "low",
            "code": "candidate_answer_policy_tone",
            "message": "考生版答案可能偏政策材料腔，建议改得更自然、可复述",
        })

    relevance_tokens = _extract_relevance_tokens(brief)
    relevance_hits = [token for token in relevance_tokens if token and token in question][:8]
    # 如果完全不命中，只给中等问题；有些好题会换成真实场景，不必强判失败。
    if relevance_tokens and not relevance_hits:
        issues.append({"severity": "medium", "code": "weak_article_relevance", "message": "题干与精读文章标题/主题关键词命中较少，需要人工关注是否跑题"})

    truncation_scope = [question, exam_focus, breaking_hint, candidate_answer, output_prompt, output_sentence_template, thirty_second_answer]
    if isinstance(answer_framework, list):
        truncation_scope.extend(_text(item) for item in answer_framework if _text(item))
    truncation_hit = any(_looks_incomplete(item) for item in truncation_scope)
    if truncation_hit:
        issues.append({"severity": "high", "code": "truncated_answer", "message": "答案可能存在截断或半句话"})

    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "high":
            score -= 24
        elif severity == "medium":
            score -= 14
        else:
            score -= 6
    score = max(0, min(100, score))

    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    ok = score >= 72 and high_count == 0 and medium_count <= 2
    status = "ok" if ok else ("review" if score >= 55 else "fail")

    if not ok:
        hints.append("后续可开启自动重写：只重写 daily_question 模块，不必重写整封邮件。")
    if not has_identity or not has_scene or not has_conflict or not has_task:
        hints.append("理想题干应同时具备：身份、场景、矛盾、任务。")
    if too_broad:
        hints.append("避免直接问“你怎么看XX”，建议改成基层/部门具体处置场景。")

    return {
        "ok": ok,
        "status": status,
        "score": score,
        "question": question,
        "question_type": question_type,
        "length": length,
        "candidate_answer": candidate_answer,
        "breaking_hint": breaking_hint,
        "thirty_second_answer": thirty_second_answer,
        "checks": {
            "has_identity": has_identity,
            "has_scene": has_scene,
            "has_conflict": has_conflict,
            "has_task": has_task,
            "too_broad": too_broad,
            "material_dependency_hits": material_dependency_hits,
            "answer_framework_count": len([x for x in answer_framework if _text(x)]) if isinstance(answer_framework, list) else 0,
            "candidate_answer_length": len(candidate_answer),
            "output_prompt_length": len(output_prompt),
            "output_sentence_template_length": len(output_sentence_template),
            "thirty_second_answer_length": len(thirty_second_answer),
            "instruction_style_hits": instruction_hits,
            "interview_style_hits": interview_hits,
            "policy_tone_hits": policy_hits,
            "relevance_hits": relevance_hits,
        },
        "keyword_hits": {
            "identity": _keyword_hits(question, IDENTITY_KEYWORDS),
            "scene": _keyword_hits(question, SCENE_KEYWORDS),
            "conflict": _keyword_hits(question, CONFLICT_KEYWORDS),
            "task": _keyword_hits(question, TASK_KEYWORDS),
        },
        "issues": issues,
        "hints": hints,
    }

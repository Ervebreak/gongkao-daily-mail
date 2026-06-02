from __future__ import annotations

import re
from typing import Any


ARTICLE_TYPES = [
    "政策解读类",
    "数字治理类",
    "政策评论类",
    "现象分析类",
    "案例经验类",
    "精神价值类",
    "产业发展类",
    "生态治理类",
    "基层治理类",
    "公共服务类",
    "其他",
]


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return default


def compact_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)


def clip_text(value: Any, limit: int) -> str:
    """Clip user-facing text without adding ellipsis.

    Formal outputs must remain complete-looking. If text is too long, prefer
    cutting at a sentence boundary; otherwise return a shorter clean fragment
    without appending “...” or “……”.
    """
    text = clean_text(value).replace("……", "").replace("...", "").replace("…", "")
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit].rstrip("，、：:；; ")
    cut = max(head.rfind(mark) for mark in "。；;！!？?")
    if cut >= max(12, int(limit * 0.55)):
        return head[: cut + 1].strip()
    return head.rstrip("，、：:；;和与及并但由于通过")

def extract_bracket_terms(text: Any, limit: int = 6) -> list[str]:
    value = clean_text(text)
    terms: list[str] = []
    for term in re.findall(r"【([^】]{2,16})】", value):
        term = clean_text(term)
        if term and term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms




def clean_empty_highlight_tags(value: Any) -> str:
    """Remove empty prompt-style labels like 【重点词】 while preserving real highlighted terms."""
    text = clean_text(value)
    banned = {"重点词", "易考词", "关键词", "重点", "易错点", "易考点"}
    for term in banned:
        text = text.replace(f"【{term}】", "")
    return clean_text(text)


def infer_article_type(text: str) -> str:
    text = text or ""
    rules = [
        ("精神价值类", ["西迁精神", "劳模精神", "科学家精神", "青年", "奋斗", "使命", "担当", "家国"]),
        ("数字治理类", ["网络法治", "算法", "数据", "数字鸿沟", "数字治理", "平台经济", "人工智能治理"]),
        ("产业发展类", ["新质生产力", "未来产业", "人工智能", "低空经济", "产业升级", "科技创新", "数字化", "制造业"]),
        ("生态治理类", ["生态", "绿色", "污染", "环保", "两山", "碳", "环境治理", "生态产品"]),
        ("基层治理类", ["基层", "社区", "乡村治理", "群众工作", "网格", "矛盾化解", "治理"]),
        ("公共服务类", ["教育", "医疗", "养老", "就业", "住房", "公共服务", "社保"]),
        ("案例经验类", ["做法", "经验", "案例", "试点", "样板", "示范", "实践"]),
        ("现象分析类", ["现象", "争议", "乱象", "问题", "热议", "调查", "通报"]),
        ("政策解读类", ["报告", "白皮书", "发展报告", "意见", "规划", "方案", "解读"]),
        ("政策评论类", ["政策", "部署", "文件", "会议", "评论", "时评", "推进"]),
    ]
    for article_type, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return article_type
    return "其他"


EXAM_TOPIC_RULES = [
    (
        "产业创新与新质生产力",
        ["新质生产力", "科技创新", "未来产业", "人工智能", "低空经济", "产业升级", "数字化", "制造业"],
        ["因地制宜", "场景牵引", "避免一哄而上", "科技创新转化"],
    ),
    (
        "开放发展与风险治理",
        ["开放", "外资", "营商", "市场预期", "风险", "安全审查", "贸易"],
        ["统筹发展和安全", "优化营商环境", "精准监管", "稳定市场预期"],
    ),
    (
        "法治建设与制度执行",
        ["法治", "执法", "制度", "监管", "问责", "责任", "违规", "审批", "整改"],
        ["依法行政", "权责清单", "监督问责", "制度执行力"],
    ),
    (
        "生态文明与绿色发展",
        ["生态", "绿色", "污染", "耕地", "农业面源", "两山", "环境", "环保"],
        ["绿色发展", "两山转化", "乡村振兴", "生态价值实现"],
    ),
    (
        "基层治理与公共服务",
        ["基层", "群众", "社区", "公共服务", "治理", "民生", "就业", "养老", "医疗"],
        ["群众获得感", "政策落实", "基层减负", "协同治理"],
    ),
    (
        "精神价值与青年担当",
        ["精神", "青年", "担当", "奋斗", "使命", "西迁", "劳模", "家国"],
        ["理想信念", "使命担当", "青年奋斗", "知行合一"],
    ),
]


def infer_exam_topic(text: str) -> tuple[str, list[str]]:
    text = text or ""
    for category, keywords, points in EXAM_TOPIC_RULES:
        if any(keyword in text for keyword in keywords):
            return category, points
    return "基层治理与公共服务", ["群众获得感", "政策落实", "基层减负", "协同治理"]


def question_tokens(item: dict[str, Any]) -> list[str]:
    raw = " ".join(
        clean_text(item.get(key))
        for key in [
            "title",
            "theme",
            "source",
            "one_sentence",
            "core_viewpoint",
            "main_thread",
            "exam_value",
        ]
    )
    raw = re.sub(r"[《》“”‘’、，。；：！？（）()\[\]【】\-—_]", " ", raw)
    stop = {"人民日报", "新华社", "人民网", "新华网", "今日", "文章", "评论", "标题", "来源"}
    tokens: list[str] = []
    for token in raw.split():
        token = token.strip()
        if len(token) >= 2 and token not in stop and token not in tokens:
            tokens.append(token)
    return tokens[:14]


def question_text(question: dict[str, Any]) -> str:
    values = [
        question.get("question"),
        question.get("exam_focus"),
        question.get("breaking_direction"),
        question.get("question_source_title"),
        " ".join(clean_text(item) for item in as_list(question.get("conflicts"))),
        " ".join(clean_text(item) for item in as_list(question.get("answer_frame"))),
    ]
    return " ".join(clean_text(item) for item in values)


def is_question_related(question: dict[str, Any], featured: dict[str, Any], quick_reads: list[dict[str, Any]]) -> bool:
    text = question_text(question)
    if not text:
        return False
    if any(token and token in text for token in question_tokens(featured)):
        return True
    for item in quick_reads:
        if any(token and token in text for token in question_tokens(item)):
            return True
    return False


def question_identity(theme: str, article_type: str) -> str:
    text = f"{theme} {article_type}"
    if any(word in text for word in ["乡村", "三农", "农业", "农村", "农田", "县域"]):
        return "县农业农村局工作人员"
    if any(word in text for word in ["科技", "产业", "创新", "企业", "营商"]):
        return "县发改部门工作人员"
    if any(word in text for word in ["文化", "教育", "就业", "民生", "公共服务"]):
        return "基层公共服务工作人员"
    if any(word in text for word in ["社区", "基层", "群众"]):
        return "街道工作人员"
    if any(word in text for word in ["执法", "监管", "整改", "违规", "审批"]):
        return "基层综合执法工作人员"
    return "县直部门工作人员"

def question_type_for(article_type: str) -> str:
    if article_type in {"生态治理类", "基层治理类", "公共服务类"}:
        return "申论对策题"
    if article_type == "案例经验类":
        return "事业单位综合应用题"
    if article_type == "精神价值类":
        return "大作文立意题"
    if article_type in {"政策评论类", "现象分析类"}:
        return "申论综合分析题"
    return "申论综合分析题"


def article_related_question(source_item: dict[str, Any], today_theme: str) -> dict[str, Any]:
    theme = first_text(source_item.get("theme"), today_theme, default="基层治理")
    title = first_text(source_item.get("title"), default="今日精读文章")
    article_type = first_text(source_item.get("article_type"), source_item.get("type"), default=infer_article_type(f"{title} {theme}"))
    category, upper_points = infer_exam_topic(f"{title} {theme} {article_type} {source_item.get('one_sentence', '')}")
    q_type = "机关实务题" if article_type in {"政策评论类", "现象分析类", "案例经验类", "基层治理类", "公共服务类", "生态治理类"} else question_type_for(article_type)
    identity = question_identity(theme, article_type)
    if category == "产业创新与新质生产力":
        question = "你是县发改部门工作人员。近期本地想发展新产业，但基层反映产业基础薄弱、应用场景不足，企业也担心盲目上项目造成资源浪费。领导安排你参与调研，请提出推进建议。"
        framework = ["先摸清本地产业基础、企业需求和资源条件，避免只凭热点确定发展方向。", "围绕具体应用场景开展小切口试点，用实际效果检验项目可行性。", "加强部门、企业、院校和平台协同，补齐人才、技术和服务短板。", "建立评估机制，对效果不佳的项目及时调整，防止一哄而上和重复建设。"]
        output = "发展新产业不能只追风口，关键是看本地有没有基础、场景和承接能力。先小范围试点，再根据效果推广，才更稳妥。"
    elif category == "生态文明与绿色发展":
        question = "你是乡镇工作人员。当地生态资源较好，但群众觉得保护带来的收益不明显，基层也反映项目转化难、资金和人才不足。领导安排你参与调研，请提出工作思路。"
        framework = ["先摸清生态资源、群众诉求和现有产业基础，找准能够落地的转化方向。", "因地制宜发展农文旅、绿色农产品等项目，把生态优势转成具体收入来源。", "争取资金、人才和平台支持，帮助基层补齐运营、品牌和销售短板。", "用群众增收和环境改善检验成效，避免只做景观、不见收益。"]
        output = "生态优势要真正变成发展优势，不能只停留在保护口号上，而要找到产业载体、群众收益和长效运营之间的连接点。"
    elif category == "法治建设与制度执行":
        question = "你是基层综合执法工作人员，在专项排查中发现某项目存在审批把关不严、日常监管跟不上、整改长期不到位等问题，群众反映强烈。领导安排你参与后续整改，请提出你的工作思路。"
        framework = ["先核实情况，摸清项目审批、建设现状、整改进度和群众反映，形成问题清单。", "再压实责任，把审批、监管、整改等环节逐项对上责任单位和具体责任人。", "分类推进整改，对能立即改的限期销号，对长期问题明确阶段目标和跟踪安排。", "做好公开反馈，及时说明整改进展和处理结果，用结果回应群众关切。"]
        output = "处理监管失灵问题，不能只说加强监管，而要把情况查清、责任压实、整改闭环，让每个环节都有人管、能追踪、见结果。"
    elif category == "精神价值与青年担当":
        question = "你是单位青年干部。单位准备开展先进精神学习活动，但有人觉得离岗位较远，也有人担心活动停留在写心得、喊口号。领导安排你参与策划，请提出你的工作思路。"
        framework = ["先把精神内核转成岗位语言，讲清它和日常工作、服务群众之间的关系。", "设计案例学习、岗位实践和交流分享，让学习不只停留在文件和心得里。", "鼓励青年干部结合本职任务认领具体行动，用小切口体现担当。", "用工作改进和群众反馈检验学习效果，防止活动结束后没有变化。"]
        output = "学习先进精神，关键不是多写几篇心得，而是把精神要求落到岗位行动中，让学习最终体现为工作变化和服务成效。"
    elif category == "开放发展与风险治理":
        question = "你是政务服务窗口工作人员。某地在吸引企业投资时，既要优化服务、提高效率，也要防范重点领域风险。领导安排你参与梳理服务流程，请提出工作建议。"
        framework = ["先梳理企业办事流程和高频堵点，找出影响效率和预期的关键环节。", "公开办理标准和风险提示，让企业知道能办什么、怎么办、多久办。", "对重点领域实行分类监管，既避免一放了之，也防止层层加码。", "建立沟通反馈渠道，及时回应企业诉求，提升政策透明度和服务稳定性。"]
        output = "优化营商环境不是不要监管，而是让服务更高效、规则更清楚、监管更精准，使企业有稳定预期。"
    else:
        question = f"你是{identity}。围绕{theme}工作，推进中遇到群众理解不足、部门协同不顺、基层资源有限等情况。领导安排你参与落实，请提出你的工作思路。"
        framework = ["先了解实际情况和群众诉求，分清问题是宣传不到位、资源不足还是流程不顺。", "用群众听得懂的话做好解释，把政策目标、办理流程和实际影响讲清楚。", "主动对接相关部门，明确责任分工和时间安排，避免问题在部门之间空转。", "建立跟踪反馈机制，及时复盘推进效果，把好做法固化下来。"]
        output = f"推进{theme}，不能只靠口号和文件，关键是把群众诉求、部门责任和落地步骤接起来，让工作真正见到效果。"
    return {
        "question": clip_text(question, 180),
        "question_type": q_type,
        "question_source": "featured",
        "question_source_title": title,
        "topic_category": category,
        "upper_exam_points": upper_points,
        "exam_focus": clip_text(f"这道题重点不是泛泛表态，而是围绕具体矛盾，提出普通工作人员能落实的办法。", 100),
        "breaking_hint": clip_text(f"本题核心考察把文章主线转化为基层执行办法，可按“摸清情况→分类施策→跟踪问效”的逻辑展开。", 120),
        "breaking_direction": "先核实情况，再找准原因，最后提出可执行、可反馈的措施。",
        "conflicts": [],
        "answer_framework": [clip_text(item, 90) for item in framework],
        "candidate_answer": clip_text(
            f"我认为，这类问题不能只停留在表态上，而要把群众诉求、现实矛盾和执行办法结合起来。具体来看，第一，要先把情况摸清楚，弄清问题到底卡在哪个环节，是群众不理解、流程不顺，还是资源保障不足。第二，要结合题干中的主要矛盾分类施策，对群众关心的问题及时回应，把政策目标、办理流程和实际影响讲清楚。第三，要推动相关部门形成协同，明确责任分工和时间节点，避免问题在不同环节之间来回空转。最后，还要建立跟踪反馈机制，用实际效果检验工作推进情况，防止一阵风、走过场。", 360),
        "thirty_second_answer": clip_text(output, 100),
        "output_prompt": "请用一句话写出这道题的开头表态。",
        "output_sentence_template": clip_text(output, 120),
        "takeaway_sentence": "",
    }

def normalize_golden_sentences(value: Any, fallback: list[Any] | None = None, limit: int = 2) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in as_list(value):
        if isinstance(item, dict):
            sentence = first_text(item.get("sentence"), item.get("text"), item.get("content"))
            scenario = first_text(item.get("scenario"), item.get("scene"), item.get("适用场景"))
        else:
            text = clean_text(item)
            if "适用场景" in text:
                parts = text.split("适用场景", 1)
                sentence = parts[0].strip(" ：:；;")
                scenario = parts[1].strip(" ：:；;")
            else:
                sentence = text
                scenario = ""
        if sentence:
            rows.append({"sentence": clip_text(sentence, 60), "scenario": clip_text(scenario or "申论分析 / 面试表达", 60)})
    if not rows and fallback:
        for item in fallback:
            text = clean_text(item)
            if text:
                rows.append({"sentence": clip_text(text, 60), "scenario": "申论 / 面试 / 公基热点表达"})
    return rows[:limit]


def merge_golden_sentences(*groups: Any, limit: int = 2) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for item in normalize_golden_sentences(group):
            sentence = item["sentence"].strip()
            key = compact_key(sentence)[:70]
            if not sentence or key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def strip_exam_use_prefix(value: Any) -> str:
    text = clean_text(value)
    for prefix in ["换成考场话：", "换成考场话:", "考场话：", "考场话:"]:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def is_rewritable_expression_item(value: Any) -> bool:
    text = clean_text(value)
    return text.startswith(("可用表达", "可复用表达", "万能表达", "表达积累"))


def normalize_framework_step(item: Any, index: int) -> dict[str, str]:
    if isinstance(item, dict):
        label = first_text(item.get("label"), item.get("title"), item.get("name"), default=f"节点{index}")
        content = first_text(item.get("content"), item.get("text"), item.get("desc"), item.get("summary"))
    else:
        text = clean_text(item)
        if "：" in text:
            label, content = text.split("：", 1)
        elif ":" in text:
            label, content = text.split(":", 1)
        else:
            label, content = f"节点{index}", text
    label = clean_text(label) or f"节点{index}"
    content = clean_text(content) or label
    return {
        "label": clip_text(label, 0),
        "content": clip_text(content, 90),
    }


def is_framework_migration_step(step: dict[str, str]) -> bool:
    label = clean_text(step.get("label"))
    content = clean_text(step.get("content"))
    merged = f"{label} {content}".strip()
    return label.startswith("考场迁移") or "这类题怎么用" in label or "考场迁移" in merged


def fallback_framework(featured: dict[str, Any]) -> list[dict[str, str]]:
    article_type = first_text(featured.get("article_type"), default="政策评论类")
    title = first_text(featured.get("title"), default="主线文章")
    theme = first_text(featured.get("theme"), default="今日主题")
    main_thread = first_text(featured.get("main_thread"), featured.get("one_sentence"), featured.get("core_viewpoint"), default=f"围绕{theme}展开分析")
    theme_short = clip_text(theme or title, 18)
    if article_type in {"政策解读类", "数字治理类"}:
        return [
            {"label": f"为什么要讲{theme_short}", "content": f"文章从{theme_short}切入，说明新情况带来的规则边界、服务公平或风险治理问题。"},
            {"label": "第一层：划清规则边界", "content": "围绕新技术、新业态或新场景，说明法治和制度要先明确可为与不可为。"},
            {"label": "第二层：维护公平秩序", "content": "把市场竞争、公共服务或平台运行纳入规范轨道，避免效率追求挤压公平。"},
            {"label": "第三层：兼顾创新温度", "content": "把发展安全、效率公平和创新温度放在同一套治理规则中统筹。"},
        ]
    if article_type == "生态治理类":
        return [
            {"label": f"从{theme_short}切入", "content": f"文章围绕{theme_short}中的现实治理问题展开。"},
            {"label": "拆解转化难点", "content": "保护要求、群众收益和基层执行之间需要打通。"},
            {"label": "提出制度路径", "content": "用责任链条和跟踪反馈推动问题真正落地解决。"},
            {"label": "回到治理闭环", "content": "把生态保护、基层执行和群众获得感连成可持续的治理闭环。"},
        ]
    if article_type == "精神价值类":
        return [
            {"label": "提炼精神内核", "content": main_thread},
            {"label": "说明现实价值", "content": "精神资源不能停留在口号，要转化为具体行动。"},
            {"label": "落到实践场景", "content": "可落到岗位选择、科研攻关、基层服务等具体场景。"},
            {"label": "形成行动落点", "content": "把精神价值落实到岗位选择、科研攻关和基层服务等具体行动中。"},
        ]
    return [
        {"label": f"从{theme_short}切入", "content": main_thread or f"文章围绕{theme_short}展开，提炼现实问题和治理方向。"},
        {"label": "拆解现实堵点", "content": f"结合原文内容，分析{theme_short}中的短板、争议或执行难点。"},
        {"label": "提炼改进路径", "content": "从规则约束、服务兜底和反馈优化等方面形成作答思路。"},
        {"label": "回到文章落点", "content": "把文章中的问题、原因和做法收束成清晰的治理判断。"},
    ]


def normalize_framework_map(featured: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        clean_text(featured.get(key))
        for key in ["title", "theme", "one_sentence", "core_viewpoint", "main_thread"]
    )
    article_type = first_text(featured.get("article_type"), default=infer_article_type(text))
    if article_type not in ARTICLE_TYPES:
        article_type = infer_article_type(text)
    featured["article_type"] = article_type

    framework_map = ensure_dict(featured.get("article_framework_map"))
    article_type = first_text(framework_map.get("type"), framework_map.get("article_type"), featured.get("article_type"), default=article_type)
    if article_type not in ARTICLE_TYPES:
        article_type = infer_article_type(text)
    featured["article_type"] = article_type
    main_thread = first_text(
        framework_map.get("main_thread"),
        featured.get("main_thread"),
        featured.get("one_sentence"),
        featured.get("core_viewpoint"),
        default=f"围绕{featured.get('theme', '今日主题')}展开，提炼可迁移的考试表达",
    )
    raw_steps = as_list(framework_map.get("steps")) or as_list(featured.get("article_framework")) or as_list(featured.get("structure_breakdown"))
    steps = [normalize_framework_step(item, idx) for idx, item in enumerate(raw_steps, start=1)]
    steps = [
        step
        for step in steps
        if step["content"] and step["content"] not in {"背景", "问题", "原因", "对策", "启示"} and not is_framework_migration_step(step)
    ]
    if len(steps) < 3:
        steps = fallback_framework({**featured, "article_type": article_type, "main_thread": main_thread})
    steps = steps[:5]
    style = first_text(
        framework_map.get("framework_style"),
        default=" → ".join(step["label"] for step in steps[:5]),
    )
    step_exam_values: list[str] = []
    for raw in as_list(framework_map.get("steps")):
        if isinstance(raw, dict):
            value = first_text(raw.get("exam_value"), raw.get("exam"), raw.get("use"), raw.get("适用题型"))
            if value and value not in step_exam_values:
                step_exam_values.append(value)
    _category, inferred_tags = infer_exam_topic(f"{featured.get('title', '')} {featured.get('theme', '')} {main_thread} {article_type}")
    exam_tags = []
    for tag in (as_list(framework_map.get("exam_tags")) or inferred_tags):
        tag_text = clip_text(tag, 12)
        if tag_text and tag_text not in exam_tags:
            exam_tags.append(tag_text)
    exam_tags = exam_tags[:4]
    overall_exam_value = " / ".join(exam_tags)
    return {
        "type": article_type,
        "article_type": article_type,
        "main_thread": clip_text(main_thread, 90),
        "framework_style": style,
        "steps": steps,
        "exam_tags": exam_tags,
        "overall_exam_value": overall_exam_value,
        "self_check": first_text(
            framework_map.get("self_check"),
            default="已检查：框架节点只保留具体内容，考试价值已统一收束。",
        ),
    }


def ensure_brief_schema(data: dict[str, Any], today: str) -> tuple[dict[str, Any], list[str]]:
    from subject_line import normalize_email_subject

    warnings: list[str] = []
    brief = dict(data or {})

    defaults: dict[str, Any] = {
        "email_subject": f"公考晨读 {today}",
        "date": today,
        "today_theme": "今日热点",
        "today_focus": "围绕权威文章积累申论、面试和常识素材。",
    }
    for key, value in defaults.items():
        if not brief.get(key):
            brief[key] = value
            warnings.append(f"missing {key}")

    three = ensure_dict(brief.get("today_three_things"))
    three.setdefault("theme", brief["today_theme"])
    three.setdefault("must_remember_sentence", brief["today_focus"])
    brief["today_three_things"] = three

    featured = ensure_dict(brief.get("featured_article"))
    for key, value in {
        "title": "主线文章",
        "source": "权威媒体",
        "published_at": "",
        "theme": brief["today_theme"],
        "url": "",
    }.items():
        if not featured.get(key):
            featured[key] = value
            warnings.append(f"missing featured_article.{key}")
    featured["original_overview"] = [clip_text(item, 70) for item in as_list(featured.get("original_overview"))[:2]] or [
        first_text(featured.get("one_sentence"), featured.get("summary"), default="本文围绕今日主题展开，适合做晨读素材。")
    ]
    featured["one_sentence"] = clip_text(first_text(featured.get("one_sentence"), featured.get("core_viewpoint"), default=featured["original_overview"][0]), 80)
    featured["core_viewpoint"] = clip_text(first_text(featured.get("core_viewpoint"), featured.get("one_sentence")), 90)
    featured["main_thread"] = clip_text(first_text(featured.get("main_thread"), featured.get("one_sentence"), featured.get("core_viewpoint")), 80)
    framework_map = normalize_framework_map(featured)
    featured["article_framework_map"] = framework_map
    featured["article_framework"] = [f"{step['label']}：{step['content']}" for step in framework_map["steps"]]
    featured["structure_breakdown"] = featured["article_framework"]
    featured["three_useful_points"] = [clip_text(item, 90) for item in as_list(featured.get("three_useful_points"))[:3]] or [
        f"表面是{featured.get('theme')}里的具体问题。",
        "背后是责任、资源和执行之间没有完全接上。",
        "考试里可迁移为问题分析和治理建议。",
    ]
    exam_use_source = as_list(featured.get("exam_use")) or as_list(featured.get("usable_for_exam"))
    exam_use_source = [item for item in exam_use_source if not is_rewritable_expression_item(item)]
    featured["exam_use"] = [clip_text(strip_exam_use_prefix(item), 120) for item in exam_use_source[:2]] or [
        "面试中可用来说明：看问题不能停在表面，要追到执行环节。",
        "申论中可转成“发现问题—分析原因—提出办法”的短表达。",
    ]
    featured["rewritable_expression"] = clip_text(first_text(
        featured.get("rewritable_expression"),
        *(as_list(featured.get("copyable_expression"))[:1]),
        default="作答时可以从现实问题、治理路径和长效机制三个层面展开，避免停留在口号式表态。",
    ), 80)
    featured["original_reading_focus"] = clip_text(first_text(
        featured.get("original_reading_focus"),
        default="点开原文时，重点看作者如何从具体事实推导出治理判断，以及哪些表述可以改写进申论或面试。",
    ), 70)
    featured["usable_for_exam"] = [clip_text(strip_exam_use_prefix(item), 120) for item in as_list(featured.get("usable_for_exam"))[:2] if not is_rewritable_expression_item(item)] or featured["exam_use"][:2]
    featured["exam_conversion"] = [clip_text(strip_exam_use_prefix(item), 120) for item in as_list(featured.get("exam_conversion"))[:2] if not is_rewritable_expression_item(item)] or featured["exam_use"][:2]
    featured_gold = normalize_golden_sentences(featured.get("golden_sentences"), as_list(featured.get("copyable_expression")), limit=3)
    featured["golden_sentences"] = featured_gold
    brief["featured_article"] = featured

    quick_reads = []
    for item in as_list(brief.get("quick_reads"))[:2]:
        row = ensure_dict(item)
        quick_one_sentence = first_text(
            row.get("one_sentence"),
            row.get("summary"),
            row.get("reason"),
            row.get("exam_value"),
            default="本文可作为申论热点素材补充。",
        )
        quick_reads.append(
            {
                "title": first_text(row.get("title"), default="速读素材"),
                "source": first_text(row.get("source"), default="权威媒体"),
                "published_at": first_text(row.get("published_at"), row.get("date")),
                "url": first_text(row.get("url")),
                "theme": first_text(row.get("theme")),
                "exam_value": clip_text(first_text(row.get("exam_value"), quick_one_sentence, default="可作为申论热点素材补充。"), 80),
                "one_sentence": clip_text(quick_one_sentence, 60),
                "url_status": row.get("url_status"),
                "url_status_reason": row.get("url_status_reason"),
            }
        )
    brief["quick_reads"] = quick_reads

    common = ensure_dict(brief.get("daily_common_knowledge"))
    common.setdefault("knowledge_point", "")
    common.setdefault("field", "时政常识")
    common.setdefault("why_frequent", "可用于常识判断和面试热点积累。")
    common.setdefault("memory_sentence", common.get("knowledge_point", ""))
    brief["daily_common_knowledge"] = common

    question = ensure_dict(brief.get("daily_question"))
    question.setdefault("question_source", "featured")
    question.setdefault("question_source_title", featured.get("title", ""))
    if not clean_text(question.get("question")) or not is_question_related(question, featured, quick_reads):
        question = article_related_question(featured, brief["today_theme"])
        warnings.append("daily_question missing or unrelated to featured article; replaced with featured-linked fallback")
    question.setdefault("question_type", question_type_for(featured.get("article_type", "政策评论类")))
    question.setdefault("question_source", "featured")
    question.setdefault("question_source_title", featured.get("title", ""))
    question["question"] = clip_text(first_text(question.get("question"), default="请结合今日文章，谈谈如何把具体问题转化为有效治理。"), 180)
    question["exam_focus"] = clip_text(first_text(question.get("exam_focus"), default="这道题考察能否把文章主线转化为具体考场表达。"), 110)
    question["breaking_hint"] = clip_text(first_text(question.get("breaking_hint"), question.get("breaking_direction"), default="本题核心考察把文章主线转化为具体作答路径，可按“发现问题→分析原因→提出措施→跟踪落实”的逻辑展开。"), 140)
    question["breaking_direction"] = clip_text(first_text(question.get("breaking_direction"), default="先识别题干矛盾，再逐一对应提出分析或对策。"), 60)
    question["conflicts"] = [clip_text(item, 60) for item in as_list(question.get("conflicts"))[:3]] or [
        "政策目标与群众理解之间存在落差",
        "基层执行资源和协同条件不足",
        "短期推进与长效治理之间需要衔接",
    ]
    answer_framework = as_list(question.get("answer_framework")) or as_list(question.get("answer_frame"))
    question["answer_framework"] = [clip_text(item, 90) for item in answer_framework[:4]] or [
        "先点明题干里的现实矛盾，说明不能只停留在表态层面。",
        "对应题干问题逐项作答，不写脱离场景的宏观口号。",
        "提出可执行的沟通、协同、反馈和长效机制。",
        "回到群众获得感或治理实效作总结提升。",
    ]
    question["answer_frame"] = question["answer_framework"]
    question["candidate_answer"] = clip_text(first_text(
        question.get("candidate_answer"),
        default="我认为，这类问题不能只停留在原则表态上，而要把文章中的判断转化成具体场景里的执行办法。第一，要先把情况摸清楚，弄清问题到底卡在哪个环节，是群众不理解、流程不顺，还是资源保障不足。第二，要围绕题干中的主要矛盾分类施策，用群众听得懂的话把政策目标、办理流程和实际影响讲清楚，同时把基层执行中存在的堵点梳理出来。第三，要主动推动相关部门协同配合，明确责任分工和推进节奏，避免问题长期悬着不解决。最后，还要建立跟踪反馈机制，用实际效果检验工作有没有真正落地，让群众看到变化、感到方便。"), 450)
    question["thirty_second_answer"] = clip_text(first_text(question.get("thirty_second_answer"), question.get("output_sentence_template"), default="我认为，解决这类问题，关键是先摸清情况、再分类施策、再推动协同、最后跟踪问效。"), 100)
    question["output_prompt"] = clip_text(first_text(question.get("output_prompt"), default="请用一句话写出这道题的开头表态。"), 90)
    question["output_sentence_template"] = clip_text(first_text(question.get("output_sentence_template"), question.get("thirty_second_answer"), default="我认为，解决这类问题，不能只停留在表态上，关键是把问题找准、把措施做实、把结果跟踪到位。"), 120)
    question["takeaway_sentence"] = ""
    question_gold: list[dict[str, str]] = []
    question["golden_sentences"] = question_gold
    brief["daily_question"] = question
    brief["today_three_things"]["daily_question"] = question.get("question")

    card = ensure_dict(brief.get("today_accumulation_card"))
    card.setdefault("title", brief["today_theme"])
    card["sentences"] = as_list(card.get("sentences"))[:5]
    brief["today_accumulation_card"] = card

    takeaway = ensure_dict(brief.get("today_takeaway"))
    takeaway["keywords"] = [clip_text(item, 10) for item in as_list(takeaway.get("keywords"))[:3]] or [brief["today_theme"], featured.get("theme")]
    takeaway["common_knowledge_points"] = [clip_text(clean_empty_highlight_tags(item), 100) for item in as_list(takeaway.get("common_knowledge_points"))[:1]]
    if not takeaway["common_knowledge_points"] and clean_text(common.get("knowledge_point")):
        takeaway["common_knowledge_points"] = [clip_text(clean_empty_highlight_tags(common.get("knowledge_point")), 100)]
    takeaway["copyable_expressions"] = [clip_text(item, 70) for item in (as_list(takeaway.get("copyable_expressions"))[:2] or card.get("sentences", [])[:2])]
    takeaway["golden_sentences"] = merge_golden_sentences(
        takeaway.get("golden_sentences"),
        featured_gold,
        takeaway.get("copyable_expressions"),
        limit=2,
    )
    if not takeaway["golden_sentences"]:
        takeaway["common_knowledge_highlights"] = extract_bracket_terms("；".join(takeaway.get("common_knowledge_points", [])))

    if len(takeaway["golden_sentences"]) < 2 and clean_text(featured.get("rewritable_expression")):
        takeaway["golden_sentences"].append(
            {"sentence": featured["rewritable_expression"], "scenario": "申论综合分析 / 面试综合分析"}
        )
    takeaway["golden_sentences"] = takeaway["golden_sentences"][:2]
    takeaway["framework"] = clip_text(first_text(
        takeaway.get("framework"),
        takeaway.get("可迁移框架"),
        default="现实问题 → 原因分析 → 因地制宜 → 长效反馈",
    ), 50)
    takeaway["extension"] = clip_text(first_text(takeaway.get("extension"), takeaway.get("拓展联想")), 80)
    takeaway["use_scenarios"] = as_list(takeaway.get("use_scenarios"))[:4] or ["申论", "面试", "公基", "事业单位综合应用"]
    brief["today_takeaway"] = takeaway
    brief, subject_warnings = normalize_email_subject(brief)
    warnings.extend(subject_warnings)
    return brief, warnings

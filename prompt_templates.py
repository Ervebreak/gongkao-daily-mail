from __future__ import annotations

import json
from pathlib import Path

from article_filter import Article
from config import settings
from stage3_structured_constraints import STRUCTURED_FIELD_RULES_V1


SYSTEM_PROMPT = """
你是一名公考/事业单位申论与面试晨读教研编辑。
你的任务是把当天候选文章加工成一封适合手机端 3-5 分钟阅读的晨读邮件。
当前阶段默认申论优先：今日一题中，申论题占比应明显高于面试题；只有文章天然更适合人物态度、现场沟通、应急处置等面试情境时，才生成面试题。

必须遵守：
1. 只输出合法 JSON，不要输出 Markdown、HTML 或解释文字。
2. 一封邮件只围绕一篇主线文章展开，其他文章只做速读补充。
3. 内容要像考生晨读笔记，不要像教研讲义、政策研究报告或完整标准答案。
4. 用户不点原文，也应能理解主线文章的核心收获；点原文只是进一步深读。
5. 今日精读、文章框架图、今日一题、今日可带走必须分工清楚，不能互相重复。
6. 禁止虚构真题年份、地区、题号，禁止冒充权威原文或领导人讲话。
7. 减少空话套话，避免“具有重要意义、推动高质量发展、形成合力”等空泛表述；如必须使用，要说明具体机制。
8. 少用过硬术语，如“权力异化、责任悬空、穿透式督查、终身追溯、系统性重构”等；如必须使用，要改写成普通考生能理解的话。
9. 凡是“换成考场话、可用表达、考生版参考答案、30秒输出、金句用法”等教考生表达的内容，都必须像普通优秀考生能写出来、说出来的话。
10. 时政常识点如需强调重点，只能用【具体关键词】高亮，不得写【重点词】【易考词】这类空标签。
11. 所有正式输出严禁使用省略号（...、……、…）；如果内容过长，必须改写成更短的完整句，不得截断。
"""

GLOBAL_RULES_V1 = """
【全局运行规则】
1. 所有内容必须服务于“考场可用”，不要做纯新闻摘要。
2. 重点信息前置，支持用户选择性阅读；每个模块都应能独立提供价值。
3. 不得出现开发态痕迹：待补充、第X条、None、Python列表、技术字段、重复字段名。
4. 不得在多个模块中机械重复同一观点、金句或判断。
5. 输出必须适合手机阅读：短段落、层级清晰、重点明确。
6. 不得使用省略号（...、……、…）；宁可减少字数，也必须保证所有句子完整收束。
7. 生产硬约束：如果任何字段写到一半、无法自然收尾、缺少宾语或停在“防止局部合理”“用主动服务化”这类半截表达上，必须删掉重写成更短的完整句；不得把半截句输出到 JSON。
8. 字数上限只是防止机械截断的安全余量，不代表要写满；金句、可用表达、30秒输出、速读价值等记忆型内容应优先短、准、完整。
9. 能用一句说清楚的，不写两句；能用普通考生能背下来的短句表达的，不展开成长段分析。
"""

FRAMEWORK_MAP_RULES_V1 = """
【文章框架图运行规则】
1. 框架图必须优先贴合原文真实结构，优先参考原文小标题、段落顺序和论证逻辑。
2. 必须先判断文章类型，再选择结构，不得所有文章都套同一模板。
3. 禁止套用“文章主线 → 现实矛盾 → 具体路径 → 总结落点”作为固定四段式。
4. 节点控制在3-5个；每个节点必须是完整短句，不得只写概念词或半句话。
5. 每个节点都必须包含本篇文章独有信息，不能输出任何换到其他文章也成立的万能句。
6. 禁止使用“从问题识别、责任分工和长效反馈三个层面推进”“把文章判断转化为可复述、可作答的治理表达”等模板句。
7. 数字必须带对象、单位和含义，不得出现孤立数字。
8. 框架图只展示文章真实展开结构，不得加入“考场迁移”“这类题怎么用”等备考迁移节点；迁移价值放到三点、今日一题或今日可带走中表达。
"""

DAILY_QUESTION_RULES_V1 = """
【作答框架精简规则】
1. 今日一题的 answer_framework / answer_frame 只写关键词式骨架，不写完整答案段落。
2. 每点必须控制在35字以内，格式为“动词短语：简短解释。”，例如“摸清底数：掌握问题点位、利益主体和资源条件。”
3. answer_framework 负责给用户看答题骨架，candidate_answer 负责完整展开；两者不得逐句重复、不得只是把框架扩写一遍。
4. answer_framework 禁止写成长句、排比段或答案原句，禁止出现与 candidate_answer 连续12字以上完全相同的表达。
【今日一题运行规则】
1. 今日一题必须从当日精读文章直接生长出来，不得另起炉灶。
2. 题目不得停留在宏观概念讨论。
3. 原则上包含身份、场景、矛盾、任务四要素。
4. 必须明确题型，且默认申论优先。
5. 必须输出：题目、审题关键、破题提示、作答框架、考生版参考答案、30秒输出任务。
6. 考生版答案必须自然、稳重、可复述，不得写成政策报告或领导讲话。
7. 不得出现截断、半句话或省略号结尾。
"""

TAKEAWAY_RULES_V1 = """
【今日可带走运行规则】
1. 今日可带走不是摘抄区，而是考场可用表达沉淀区。
2. 金句不得只罗列句子，必须说明适用题型、位置和用法。
3. 可用表达优先采用“原来的空话 → 更好的说法 → 适用场景”。
4. 关键词必须是考点词，不得使用过泛词。
5. 常识点必须准确、具体、可复述。
6. 不得与今日精读、框架图、今日一题大段重复。
7. golden_sentences 是生产端强校验字段：每条 sentence 必须是完整短句，不得停在动词、形容词、抽象名词或未完成判断上；如果写不完，必须改成更短的完整句。
8. common_knowledge_points 是生产端事实安全字段：如果原文没有明确出现具体文件名、部门名、数字或制度名称，不得编造具体政策事实；可以输出通用考点表述，但不得虚构“某部门联合出台某文件”。
9. 金句 sentence 目标 28-48 字，scenario 目标 25-50 字；60 字只是安全上限，不要写满。
"""


def _load_runtime_prompt_rules() -> str:
    """Load short runtime prompt rules from content_harness/runtime_prompt_rules.md.

    The long SPEC/Rule/Skill files are source documents for humans.  Runtime
    generation only reads this short file to avoid prompt bloat and conflicts.
    """
    path = Path(__file__).resolve().parent / "content_harness" / "runtime_prompt_rules.md"
    try:
        rules = path.read_text(encoding="utf-8").strip()
    except Exception:
        rules = ""
    if not rules:
        rules = "\n".join([GLOBAL_RULES_V1, FRAMEWORK_MAP_RULES_V1, DAILY_QUESTION_RULES_V1, TAKEAWAY_RULES_V1]).strip()
    return rules[:8000]


RUNTIME_PROMPT_RULES = _load_runtime_prompt_rules()


def _load_article_selection_rules() -> str:
    """Load fixed article-selection prompt rules.

    These rules are intentionally separate from runtime generation rules:
    selection evaluates whether an article can be transformed into exam
    material, while generation writes the actual email.
    """
    path = Path(__file__).resolve().parent / "content_harness" / "article_selection_prompt.md"
    try:
        rules = path.read_text(encoding="utf-8").strip()
    except Exception:
        rules = ""
    if not rules:
        rules = """
【固定选文规则】
你是“公考/考编每日晨读邮件”的选文审核器。你的任务不是选择普通新闻热点，而是从候选文章中选择最适合作为今日精读主文章的文章。

请按以下维度为每篇候选文章评分，总分100分：
1. 考题转化度：30分。判断文章是否能自然转化为一道具体的申论题或结构化面试题。
2. 问题意识：20分。判断文章是否包含现实难点、治理堵点、群众痛点或政策落地问题。
3. 场景具体度：15分。判断文章是否落在基层、社区、窗口、养老、就业、执法、应急、平台治理、城市治理等具体场景中。
4. 矛盾张力：15分。判断文章是否包含效率与公平、创新与规范、放权与监管、服务与成本、群众诉求与基层压力、政策弹性与制度边界等两难关系。
5. 素材提炼价值：10分。判断文章是否能提炼出考场可用的原因分析句、对策句、金句、案例素材。
6. 来源权威与时效：10分。判断文章来源是否权威、发布时间是否较新、主题是否有现实关注度。

总分低于75分，不得作为今日精读主文章，只能进入今日速读。连续两天同主题或同来源，应适当降权。
""".strip()
    return rules[:8000]


ARTICLE_SELECTION_RULES = _load_article_selection_rules()


JSON_SCHEMA_HINT = {
    "email_subject": "【公考晨读】不超过18字的主题",
    "date": "YYYY-MM-DD",
    "today_theme": "聚焦一个主线主题，不要双主线硬拼",
    "today_focus": "一句话说明今天为什么读这篇",
    "today_three_things": {
        "theme": "今日主题",
        "must_remember_sentence": "今天最该记住的一句话",
        "daily_question": "今日一题的简短题干或训练方向",
    },
    "featured_article": {
        "title": "主线文章标题",
        "source": "来源",
        "published_at": "YYYY-MM-DD 或 unknown",
        "url": "原文链接",
        "theme": "主题",
        "one_sentence": "一句话看懂，具体直白",
        "three_useful_points": [
            "表面问题是什么",
            "背后原因是什么",
            "考试里能迁移成什么",
        ],
        "exam_use": ["换成考场话：本文核心观点如何转成考场分析语言，1-2条"],
        "rewritable_expression": "可用表达：以后同类题也能复用的考生表达，1句",
        "original_reading_focus": "紧跟原文链接展示：如果点原文，重点看什么",
        "article_framework_map": {
            "article_type": "政策解读类/数字治理类/政策评论类/现象分析类/案例经验类/精神价值类/产业发展类/生态治理类/基层治理类/公共服务类/其他",
            "main_thread": "一句话说明文章主线",
            "steps": [
                {"label": "具体结构名称，不得写文章主线/现实矛盾/具体路径/总结落点", "content": "该层具体内容，必须包含文章独有信息，不写万能句"}
            ],
            "exam_tags": ["可迁移考点1", "可迁移考点2", "可迁移考点3"],
        },
    },
    "daily_question": {
        "topic_category": "题材类别",
        "upper_exam_points": ["上位考点1", "上位考点2"],
        "question_type": "申论对策题/申论综合分析题/申论贯彻执行题/机关实务题/面试综合分析题/事业单位综合应用题/大作文立意题",
        "question": "80-180字，具体场景化题干",
        "exam_focus": "1句话审题关键：只拆题，说明题目任务、对象、核心矛盾和不能漏的角度；不得写作答路线或具体对策",
        "breaking_hint": "1句话作答主线：只给切入顺序，如“先释疑、再溯源、后建制”；不得列完整分点，不得和作答框架重复",
        "answer_framework": ["3-4条正式作答骨架，每条不超过45字，格式为“动词短语：简短解释。”；不得逐句复述作答主线"],
        "candidate_answer": "280-450字考生版参考答案，自然、稳重、可复述",
        "thirty_second_answer": "40-100字，内部30秒压缩表达，必须像考生能直接说出口",
        "output_prompt": "给用户的30秒输出任务，优先固定为：请用一句话写出这道题的开头表态。不得写成复述框架/重点练习等教研指令",
        "output_sentence_template": "60-120字参考句式，必须是一句考生可直接模仿的开头表态或核心判断",
    },
    "today_takeaway": {
        "keywords": ["关键词1", "关键词2", "关键词3"],
        "common_knowledge_points": ["1条时政常识；如需高亮，只能把具体关键词放进【】中；原文没有明确出现具体文件名、部门名、数字或制度名称时，不得编造具体政策事实，可以输出通用考点表述；没有合适常识点可留空"],
        "golden_sentences": [
            {"sentence": "必备金句1", "scenario": "适用场景"},
            {"sentence": "必备金句2", "scenario": "适用场景"},
        ],
        "framework": "1个可迁移框架",
    },
    "quick_reads": [
        {
            "title": "文章标题",
            "source": "来源",
            "published_at": "YYYY-MM-DD",
            "url": "链接",
            "theme": "主题",
            "one_sentence": "一句话概括文章核心内容，必须完整，不超过60字",
            "exam_value": "一句话申论素材价值，不超过80字",
        }
    ],
}


EXAM_TOPIC_RULES = """
生成今日一题前，必须先做上位考点转换：
具体文章题材 -> 题材类别 -> 上位考点 -> 今日一题。

小型高频考点映射：
1. 产业创新与新质生产力：因地制宜、场景牵引、避免一哄而上、科技创新转化。
2. 开放发展与风险治理：统筹发展和安全、优化营商环境、精准监管、稳定市场预期。
3. 生态文明与绿色发展：绿色发展、两山转化、乡村振兴、生态价值实现。
4. 基层治理与公共服务：群众获得感、政策落实、基层减负、协同治理。
5. 精神价值与青年担当：理想信念、使命担当、青年奋斗、知行合一。
6. 法治建设与制度执行：依法行政、权责清单、监督问责、制度执行力。

如果文章题材较专业，不要直接考专业细节，要转化到上位考点。
例如外资审查不要写成“完善外资安全审查制度”，应转为“扩大开放与防范风险如何统筹”。
例如违规用地不要只问“如何治理墓地”，应转为“项目审批监管长期失灵如何治理”。
"""


def _clip_text(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    # 给模型的候选正文做硬截断，不加省略号，避免污染最终邮件展示。
    return _clip_to_sentence_boundary(text, max_chars)


_SENTENCE_BOUNDARIES = "。！？；.!?;"
_WEAK_TRAILING_CHARS = "，、：；,、:;([{<\"'“‘`+-/\\"
_WEAK_TRAILING_WORDS = (
    "以及",
    "并且",
    "或者",
    "但是",
    "如果",
    "为了",
    "通过",
    "根据",
    "对于",
    "围绕",
    "和",
    "与",
    "及",
    "或",
    "并",
    "且",
    "但",
    "而",
    "把",
    "将",
    "向",
    "在",
    "为",
    "就",
    "来",
)


def _is_ascii_word_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def _trim_incomplete_tail(text: str, next_char: str = "") -> str:
    clipped = text.rstrip()
    while clipped and clipped[-1] in _WEAK_TRAILING_CHARS:
        clipped = clipped[:-1].rstrip()
    while clipped and any(clipped.endswith(word) for word in _WEAK_TRAILING_WORDS):
        matched = next(word for word in _WEAK_TRAILING_WORDS if clipped.endswith(word))
        clipped = clipped[: -len(matched)].rstrip()
    if clipped and next_char and _is_ascii_word_char(clipped[-1]) and _is_ascii_word_char(next_char):
        while clipped and _is_ascii_word_char(clipped[-1]):
            clipped = clipped[:-1]
        clipped = clipped.rstrip()
    return clipped


def _clip_to_sentence_boundary(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    candidate = text[:max_chars].rstrip()
    sentence_end = max((candidate.rfind(boundary) for boundary in _SENTENCE_BOUNDARIES), default=-1)
    if sentence_end >= 0:
        clipped = candidate[: sentence_end + 1].rstrip()
        if clipped:
            return clipped
    next_char = text[max_chars] if max_chars < len(text) else ""
    clipped = _trim_incomplete_tail(candidate, next_char)
    return clipped or candidate


def compact_article(article: Article) -> dict[str, object]:
    """Candidate-stage article payload: broad but token-controlled."""
    body_limit = max(1, settings.llm_article_body_paragraphs)
    paragraph_chars = max(80, settings.llm_article_paragraph_chars)
    return {
        "title": article.title,
        "source": article.source,
        "column": article.column,
        "url": article.url,
        "published_at": article.published_at,
        "tags": article.tags,
        "themes": article.themes,
        "score": article.score,
        "body": [_clip_text(p, paragraph_chars) for p in article.body[:body_limit]],
    }


def _clip_paragraphs_by_total_chars(paragraphs: list[str], max_chars: int) -> list[str]:
    cleaned: list[str] = []
    used = 0
    for para in paragraphs:
        para = (para or "").strip()
        if not para:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(para) > remaining:
            clipped = _clip_to_sentence_boundary(para, remaining)
            if clipped:
                cleaned.append(clipped)
                used += len(clipped)
            break
        cleaned.append(para)
        used += len(para)
    return cleaned


def full_article_for_generation(article: Article, role: str = "candidate") -> dict[str, object]:
    max_chars = settings.featured_article_max_chars if role == "featured_candidate" else settings.quick_read_article_max_chars
    return {
        "role": role,
        "title": article.title,
        "source": article.source,
        "column": article.column,
        "url": article.url,
        "published_at": article.published_at,
        "tags": article.tags,
        "themes": article.themes,
        "score": article.score,
        "body": _clip_paragraphs_by_total_chars(article.body, max_chars),
    }


def _selection_context_payload(selection_context: dict[str, object] | None) -> dict[str, object]:
    """Build dynamic context for article selection.

    The fixed scoring rules live in ARTICLE_SELECTION_RULES.  This payload is
    dynamic and may change every run: recent featured articles, source/theme
    repetition, and candidate-pool diagnostics.
    """
    context = selection_context or {}
    return {
        "recent_selected_articles_7d": context.get("history_recent_featured_items_7d", []),
        "recent_featured_themes_3d": context.get("history_recent_featured_themes_3d", []),
        "recent_featured_sources_3d": context.get("history_recent_featured_sources_3d", []),
        "yesterday_featured_titles": context.get("history_yesterday_featured_titles", []),
        "source_candidate_counts": context.get("source_candidate_counts", {}),
        "preselected_sources": context.get("selected_sources", []),
        "preselected_themes": context.get("selected_themes", []),
        "candidate_pool_note": {
            "raw_candidate_count": context.get("raw_candidate_count"),
            "candidate_count_after_filter": context.get("candidate_count"),
            "recent_48h_count": context.get("recent_48h_count"),
            "recent_7d_count": context.get("recent_7d_count"),
            "uses_over_3_days": context.get("uses_over_3_days"),
            "over_3_days_reason": context.get("over_3_days_reason", ""),
        },
    }


def build_selection_prompt(articles: list[Article], today: str, selection_context: dict[str, object] | None = None) -> str:
    payload = {
        "today": today,
        "task": "从候选文章中选择今日主线文章和速读文章，不生成邮件正文。",
        "fixed_selection_rules": ARTICLE_SELECTION_RULES,
        "dynamic_context": _selection_context_payload(selection_context),
        "output_schema": {
            "featured": {
                "title": "主线文章标题，必须来自输入文章",
                "url": "主线文章URL，必须来自输入文章",
                "source": "主线文章来源",
                "total_score": "0-100整数；低于75原则上不得作为精读",
                "score_detail": {
                    "exam_conversion": "考题转化度，0-30",
                    "problem_awareness": "问题意识，0-20",
                    "scenario_specificity": "场景具体度，0-15",
                    "contradiction_tension": "矛盾张力，0-15",
                    "material_value": "素材提炼价值，0-10",
                    "authority_timeliness": "来源权威与时效，0-10"
                },
                "suitable_exam_types": ["申论对策题/申论综合分析题/机关实务题/结构化面试等"],
                "possible_question": "根据主线文章可自然生成的一道具体、场景化考题",
                "reason": "为什么适合做今日精读，80字以内",
                "risk_note": "是否存在主题/来源重复、地方性过窄、正文不足等风险；没有则写无"
            },
            "quick_reads": [
                {
                    "title": "速读文章标题，必须来自输入文章",
                    "url": "URL，必须来自输入文章",
                    "source": "来源",
                    "reason": "为什么适合做速读，60字以内"
                }
            ],
            "selection_notes": "整体选择说明，100字以内"
        },
        "selection_rules_for_execution": [
            "主线文章优先选择能转化为申论/结构化面试训练材料的文章，不只看热点或来源级别。",
            "考题转化度不是与真实题库的相似度；当前尚未接入真题库时，它表示文章是否具备真题常见的出题特征。",
            "主线文章必须能生成具体场景化今日一题，不能只是一条资讯、会议通稿或纯成就宣传。",
            "总分低于75分的文章原则上不得作为 featured；若候选池整体较弱必须选择，应在 risk_note 中说明。",
            "如果最近3天主题或来源重复，应降权；除非单篇考题转化价值明显更高，并在 selection_notes 中说明。",
            "quick_reads 最多选择2篇，尽量与主线来源或主题有所区分。",
            "只允许从输入文章中选择，不得虚构标题、URL或来源。"
        ],
        "articles": [compact_article(article) for article in articles],
    }
    return f"""
请只完成文章选择，不要生成晨读邮件正文。
输出必须是合法 JSON，且只能包含 featured、quick_reads、selection_notes 三个一级字段。

固定规则说明：fixed_selection_rules 是长期固定选文标准；dynamic_context 是每天变化的上下文，用于判断主题/来源去重和候选池强弱。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_final_generation_prompt(
    selected_articles: list[Article],
    today: str,
    selection_result: dict[str, object] | None = None,
    question_bank_context: dict[str, object] | None = None,
) -> str:
    featured_url = ((selection_result or {}).get("featured") or {}).get("url") if isinstance((selection_result or {}).get("featured"), dict) else ""
    articles_payload = []
    for idx, article in enumerate(selected_articles):
        role = "featured_candidate" if idx == 0 or (featured_url and article.url == featured_url) else "quick_read_candidate"
        articles_payload.append(full_article_for_generation(article, role=role))
    payload = {
        "today": today,
        "schema": JSON_SCHEMA_HINT,
        "selection_result": selection_result or {},
        "question_bank_context": question_bank_context or {},
        "articles": articles_payload,
    }
    return f"""
请基于已选文章生成一封“公考/考编每日晨读邮件”的 JSON。

重要约束：
1. role=featured_candidate 的文章已经由第一阶段选定，必须作为 featured_article，不要重新换主线。
2. role=quick_read_candidate 的文章只可作为 quick_reads，不要抢主线。
3. featured_article 的今日精读、文章框架图、今日一题、今日可带走，必须基于更完整正文生成，不要只根据开头脑补。
4. quick_reads 最多 2 篇，只做素材价值提示。
5. 输出必须是合法 JSON，必须符合 schema 中主要字段。

整体目标：
- 内容要实，关键模块可以适当充实；但要删重复、保重点、支持手机端快速扫读。
- 邮件不是新闻摘要，也不是教研讲义，而是早上手机端能快速读、能记住、考试能用的晨读卡片。
- 核心价值是把官方文章转成申论/面试能用的框架、表达和题目。
- 今日精读、文章框架图、今日一题、今日可带走必须分工清楚，不能原句重复。

{RUNTIME_PROMPT_RULES}

{STRUCTURED_FIELD_RULES_V1}

文章框架图要求：
1. 先判断文章类型：政策解读类、数字治理类、政策评论类、现象分析类、案例经验类、精神价值类、产业发展类、生态治理类、基层治理类、公共服务类、其他。
2. 先按文章类型选择结构，不要所有文章都套“文章主线 → 现实矛盾 → 具体路径 → 总结落点”。
3. article_framework_map.main_thread 用一句话说明文章主线，必须包含文章主题和文章独有对象。
4. article_framework_map.steps 控制在 3-5 层。每层只包含 label + content；label 必须是原文展开逻辑的具体短语，目标 10-18 个字，写不短就改写，不得依赖渲染截断；不得使用“文章主线、现实矛盾、具体路径、总结落点、背景、问题、原因、对策、启示”等万能标签。
5. content 必须来自文章具体内容，包含文章独有信息；禁止输出“从问题识别、责任分工和长效反馈三个层面推进”“把文章判断转化为可复述、可作答的治理表达”等万能句。
6. 严禁在 steps 中增加“考场迁移”“这类题怎么用”等备考迁移节点；文章框架图只负责完整展示文章怎么展开。
7. 政策解读类/报告解读类可优先使用“为什么要讲X → 第一层：讲清问题 → 第二层：说明机制 → 第三层：落到执行”的结构；案例经验类可用“问题入口 → 具体做法 → 机制支撑 → 效果启示”。
8. 如果使用数字、人数、金额、时间，必须写完整对象、单位和含义，不得出现孤立数字。
9. article_framework_map.exam_tags 只作为内部考点标签保留，不在邮件里的框架图底部单独展开，也不得改写成 steps 中的“考场迁移”节点。

今日一题要求：
1. 必须和主线文章相关，但不要考冷门专业细节。
2. 默认申论优先：当前阶段申论题占比应明显高于面试题；只有文章天然更适合人物态度、现场沟通、应急处置时才使用面试题。
3. 必须包含普通工作人员身份、具体工作场景、现实矛盾、明确执行任务。
4. 默认身份不得设置为县长、副县长、局长、副局长、分管领导、主要负责人。
5. 优先使用执行型问法：工作思路、整改建议、推进落实办法、调研方案、具体措施、群众解释沟通方案。
6. 如果 question_bank_context 中提供了真题问法参考，只能学习题型、场景和问法，不得照搬原题，不得在邮件正文展示题库来源。
7. 今日一题不得出现“根据材料”“根据给定资料”“结合材料”“材料一/二/三”“给定资料”等材料依赖表达，必须脱离原始申论材料也能独立作答。
{EXAM_TOPIC_RULES}

今日可带走要求：
1. 结构为：关键词 + 时政常识 + 2句必备金句 + 1个可迁移框架。
2. 必备金句必须自然、好记、能直接写进申论或面试；不要和其他模块原句重复。

自检要求：
输出前检查：文章框架图每一层都必须是完整短句，不能出现省略号、未完成句和抽象名词堆叠；是否把专业词转成普通考生能理解的话。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_user_prompt(articles: list[Article], today: str, question_bank_context: dict[str, object] | None = None) -> str:
    payload = {
        "today": today,
        "schema": JSON_SCHEMA_HINT,
        "question_bank_context": question_bank_context or {},
        "articles": [compact_article(article) for article in articles],
    }
    return f"""
请基于输入候选文章生成一封“公考/考编每日晨读邮件”的 JSON。

整体目标：
- 内容要实，关键模块可以适当充实；但要删重复、保重点、支持手机端快速扫读。
- 邮件不是新闻摘要，也不是教研讲义，而是早上手机端能快速读、能记住、考试能用的晨读卡片。
- 核心价值是把官方文章转成申论/面试能用的框架、表达和题目。
- 今日精读、文章框架图、今日一题、今日可带走必须分工清楚，不能原句重复。

{RUNTIME_PROMPT_RULES}

考生表达质感总要求：
1. 凡是 candidate_answer、rewritable_expression、exam_use、thirty_second_answer、output_sentence_template、golden_sentences 等教考生表达的字段，都必须像高水平普通考生能写出来、说出来、背下来的话。
2. 表达要稳重、有层次，但不能像机关公文、政策报告、领导讲话或评论员文章。
3. 表达要自然、清楚、顺口，但不能像日常聊天、吐槽或低水平学生随口说的话。
4. 优先写成“观点判断 + 具体解释 + 考场落点”，让用户知道这句话能怎么用。
5. 少用“持续完善、不断夯实、全面赋能、系统推进、形成合力、长效机制”等套话；如果必须用政策词，后面要接具体解释。
6. 禁止堆砌“路径纠偏、机制重塑、责任异化、深层治理逻辑”等晦涩抽象词。

主线选择：
1. 选择一篇最适合公考/考编转化的文章作为 featured_article。
2. 主线文章优先满足：有明确问题、原因、路径或表达价值；适合生成今日一题；发布时间较新。
3. 如果多篇文章主题差异大，只选一篇做主线，其他放 quick_reads，不要双主线硬拼。
4. quick_reads 最多 2 篇，只做申论素材补充。

今日精读要求：
1. 今日精读负责“看懂文章 + 转成考试素材”，不要写成完整答题答案。
2. featured_article.one_sentence：一句话看懂，50-80字，具体直白，不空泛。
3. featured_article.three_useful_points：严格 3 条，分别回答“表面问题是什么、背后原因是什么、考试里能迁移成什么”；每条可以适当充实，但不要长篇大论。
4. featured_article.exam_use：1-2 条，名称对应“换成考场话”，定位是“本文核心观点在考场上怎么分析”；目标70-95字，120字只是安全上限，不要写满；必须像高水平普通考生能表达出来，不要像政策报告；不是今日一题答案；不要和今日一题的30秒输出参考句式重复；不要输出“可用表达：”或可复用金句，这类内容只放到 rewritable_expression。
5. featured_article.rewritable_expression：只给 1 句自然好背的可用表达；目标25-55字，必须短而完整；定位是“以后同类题也能复用的话”，必须像高水平考生能写出来、说出来、背下来，不要写成教研点评、公文套话或大白话。
6. featured_article.original_reading_focus：如果点原文，提醒重点看什么；这个字段将在原文链接下方前置展示，必须具体指出看开头/案例/结尾/治理落点中的哪几处。
7. 今日精读允许比极简版更充实，但必须避免重复、抽象堆叠和空话。

文章框架图要求：
1. 先判断文章类型：政策解读类、数字治理类、政策评论类、现象分析类、案例经验类、精神价值类、产业发展类、生态治理类、基层治理类、公共服务类、其他。
2. 先按文章类型选择结构，不要所有文章都套“文章主线 → 现实矛盾 → 具体路径 → 总结落点”。
3. article_framework_map.main_thread 用一句话说明文章主线，必须包含文章主题和文章独有对象。
4. article_framework_map.steps 控制在 3-5 层。每层只包含 label + content；label 必须是原文展开逻辑的具体短语，目标 10-18 个字，写不短就改写，不得依赖渲染截断；不得使用“文章主线、现实矛盾、具体路径、总结落点、背景、问题、原因、对策、启示”等万能标签。
5. content 必须来自文章具体内容，包含文章独有信息；禁止输出“从问题识别、责任分工和长效反馈三个层面推进”“把文章判断转化为可复述、可作答的治理表达”等万能句。
6. 严禁在 steps 中增加“考场迁移”“这类题怎么用”等备考迁移节点；文章框架图只负责完整展示文章怎么展开。
7. 政策解读类/报告解读类可优先使用“为什么要讲X → 第一层：讲清问题 → 第二层：说明机制 → 第三层：落到执行”的结构；案例经验类可用“问题入口 → 具体做法 → 机制支撑 → 效果启示”。
8. 如果使用数字、人数、金额、时间，必须写完整对象、单位和含义，不得出现孤立数字。
9. article_framework_map.exam_tags 只作为内部考点标签保留，不在邮件里的框架图底部单独展开，也不得改写成 steps 中的“考场迁移”节点。

今日一题要求：
1. 今日一题必须和主线文章相关，但不要考冷门专业细节。
2. 必须先做上位考点转换，再生成题目。
{EXAM_TOPIC_RULES}
3. 默认申论优先：当前阶段申论题占比应明显高于面试题；只有文章天然更适合人物态度、现场沟通、应急处置时才使用面试题。
4. 题干必须包含：普通工作人员身份、具体工作场景、现实矛盾、明确执行任务。
5. 默认身份不得设置为县长、副县长、局长、副局长、分管领导、主要负责人、党委政府负责人。
6. 优先使用身份：县直部门工作人员、乡镇/街道工作人员、社区工作人员、驻村干部、工作专班成员、调研组成员、新入职机关干部、政务服务窗口工作人员、基层综合执法工作人员。
7. 题目不要总是问“你怎么看、如何回应、请谈谈理解”。优先使用“请提出工作思路、整改建议、推进落实办法、调研方案、具体措施、群众解释沟通方案”等执行型问法。
8. question 控制在 80-180 字，具体、有场景、有现实矛盾、有明确任务。
9. question_type 先判断题型，再选择对应作答结构，不要所有题目都固定使用同一种四点框架；在可行情况下优先生成申论对策题、申论综合分析题、申论贯彻执行题或机关实务题。

今日一题题型与框架匹配：
1. 综合分析题 / 怎么看类：表明态度 -> 分析意义或问题 -> 分析原因 -> 提出建议。
2. 对策建议题 / 怎么做类：摸清情况 -> 找准问题 -> 分类施策 -> 跟踪落实。
3. 调研整改题：明确目的 -> 设计对象 -> 收集信息 -> 形成建议。
4. 群众沟通题 / 应急应变题：稳定情绪 -> 核实情况 -> 解释处理 -> 后续反馈。
5. 组织协调题：明确任务 -> 分工协同 -> 推进执行 -> 总结反馈。
6. 机关实务题：领会要求 -> 结合实际 -> 推动落实 -> 复盘改进。

今日一题答案要求：
1. daily_question 总量控制在500-800字，必要时可略低，但不要低于420字，不要超过900字。
2. answer_framework 一般为3-4条；不强制必须4点，如果3点更清楚，可以写3点。
3. answer_framework 每条不超过35字，只写关键词式骨架，格式为“动词短语：简短解释。”，不要写成长句或完整答案段落。
4. 必须额外输出 candidate_answer：280-450字的考生版参考答案，能让普通考生直接模仿。
5. 必须额外输出 thirty_second_answer：40-100字的内部30秒压缩表达，必须像高水平考生能直接说出口。
6. 答案必须像高水平普通考生在申论/面试中能写出来、说出来、记住的话；不要像政策报告、理论文章、评论员文章、领导讲话或教研讲义，也不要太口语化。
7. 每条作答框架要短、准、可复述，只承担骨架提示；完整论述放到 candidate_answer 中展开。
8. 禁止出现省略号“...”“……”或未完成句；宁可减少字数和答题点，也要保证每一点完整。
9. 禁止堆叠抽象名词，连续4个以上抽象名词必须改写。
10. 少用或禁用：路径纠偏、前置评估制、系统性重构、穿透式督查、终身追溯、组织处理与纪律审查、三重动态核查、责任异化、深层治理逻辑、资本驱动、人为割裂、创新生态、转化链条、迭代能力。
11. 优先使用：先核实情况、摸清问题底数、分析问题原因、补齐短板、分类整改、试点推进、公开回应、群众解释、跟踪问效、形成长效机制。

专业术语通用转译规则：
遇到任何专业术语、政策概念、抽象表达，都必须转成考生能理解、能复述的话。不要只保留原词。
1. 把抽象概念转成具体主体：如“创新生态”不要直接堆概念，要说清楚是人才、企业、资金、场景、政策等要素协同。
2. 把理论判断转成现实问题：如“治理闭环不足”要转成“发现问题后整改不及时、后续跟踪不到位”。
3. 把宏观口号转成具体做法：如“推动高质量发展”要转成“补齐产业、服务、人才、治理等短板”。
4. 把专业表达转成考生能写的短句：如“打通转化链条”可写成“让技术能变成产品、产业和就业”。
5. 抽象题材如新质生产力、AI、科技创新、产业链、出海、营商环境、基层治理、生态治理等，都必须先转译，再作答。

今日一题输出字段要求：
1. exam_focus：1句话审题关键，指出真正考什么。
2. breaking_hint：1-2句破题提示，说明本题核心考察什么、按什么逻辑切入；例如“本题核心考察基层应急处置+群众工作能力，答题可按「事前防范→事中处置→事后长效」展开。”；不要写成第二套答题框架。
3. answer_framework：3-4条关键词式骨架，每条不超过35字，匹配题型结构。
4. candidate_answer：280-450字，考生版参考答案。
5. thirty_second_answer：40-100字，内部30秒压缩表达，用于质检和兜底。
6. output_prompt：给用户的30秒输出任务，可简短，优先要求“用一句话写开头表态/核心判断/一条具体对策”。
7. output_sentence_template：60-120字，作为参考句式展示给用户；必须像高水平考生能直接说出口的一句话；适合作为申论开头表态或核心判断；稳妥、顺口、有记忆点，不要口号化、机关化或聊天化。
8. 不要生成“一句话带走”，后面已有 today_takeaway 模块。

今日可带走要求：
1. today_takeaway 是全封邮件的最终记忆卡，不是新增长篇内容。
2. 结构为：关键词 + 时政常识 + 2句必备金句 + 1个可迁移框架。
3. 金句不得只罗列句子，必须附适用场景；尽量能替换空话。
4. 可用表达要有高水平考生质感：稳重、清楚、好背，不要只有政策腔，也不要大白话。
5. keywords 输出2-3个，每个不超过10字。
6. common_knowledge_points 只输出1条；必须来自文章中明确涉及的政策概念、时政术语、制度名词或高频考点；不超过100字；如有重点，优先把制度名称、政策关键词、易考概念和必要数字放进【】中，例如【长期护理保险】【社保第六险】【0.3%】【单位和个人同比例分担】；如果原文没有明确出现具体文件名、部门名、数字或制度名称，不得编造具体政策事实；可以输出通用考点表述，但不得虚构“某部门联合出台某文件”；不得只高亮数字；不要额外新增过长“重点词/易考题型”模块；如果没有合适常识点可留空，禁止输出“待补充”。
7. golden_sentences 保留“必备金句”的定位，输出2条，每条 sentence 目标28-48字、不超过60字，每条必须有 scenario；scenario 目标25-50字、不超过60字，必须是完整场景说明，不能停在“用于强调……配套监”这类半截表达。
8. 必备金句必须自然、好记、能直接写进申论或面试；高水平普通考生能说出来；不要只追求华丽，不要晦涩或过度官方，不要为了凑字数展开解释。
9. 必备金句不要和今日精读的“换成考场话”、今日一题的“30秒输出参考句式”原句重复。
10. framework 输出1个箭头结构，不超过50字，不展开解释。

今日速读要求：
1. quick_reads 最多 2 篇。
2. 每篇只保留标题、来源、日期、主题、链接、一句话概括 one_sentence 和一句话 exam_value。
3. one_sentence 目标40-55字、不超过60字，必须概括文章核心内容，不能留空。
4. exam_value 目标45-70字、不超过80字，不做长分析。

模块去重规则：
1. 框架图只讲文章结构，不展示“考场迁移”节点，也不额外展示“可迁移考点”底部标签。
2. 今日精读讲文章理解和“换成考场话”。
3. 今日一题讲具体题目和作答。
4. 今日可带走只做最终记忆卡。
5. 如果某句话在多个模块重复，优先保留在最合适的模块。
6. 不要让“换成考场话”“30秒输出参考句式”“必备金句”三者原句重复。

输出限制：
1. 只输出合法 JSON。
2. 必须包含 schema 中的主要字段。
3. 不要输出 HTML、Markdown、注释或解释。
4. 不要虚构真题来源、年份、地区、题号。
5. 不要伪造政策原文或领导人讲话。
6. 不要输出“待补充”。

自检要求：
输出前自行检查：
1. 今日一题是否先判断题型并匹配框架；
2. 今日一题身份是否是普通工作人员；
3. 今日一题是否更像“怎么做/工作思路/整改建议”；
4. 答案是否像普通考生能写、能说、能记住；
5. 是否把专业词转成普通话；
6. 是否没有省略号、未完成句和抽象名词堆叠；
7. 今日可带走是否为关键词、时政常识、2句必备金句、1个框架；
8. 各模块是否减少重复。
如果不符合，请自动重写。

输入数据：
{json.dumps(payload, ensure_ascii=False)}
""".strip()

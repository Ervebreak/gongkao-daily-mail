from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import re

from history import normalize_title


TAG_KEYWORDS = {
    "申论素材": ["治理", "民生", "基层", "改革", "发展", "服务", "问题", "对策", "制度"],
    "面试素材": ["群众", "干部", "担当", "作风", "落实", "责任", "服务", "调研", "协同"],
    "行测常识": ["法律", "科技", "经济", "文化", "生态", "历史", "政策", "会议", "数据"],
}

THEME_KEYWORDS = {
    "高质量发展": ["高质量发展", "新质生产力", "产业", "实体经济", "扩大内需", "区域协调"],
    "科技创新 / 新质生产力": ["科技", "创新", "人工智能", "数字化", "研发", "成果转化", "专利", "技术突破", "科研"],
    "基层治理": ["基层", "治理", "社区", "网格", "群众", "公共服务", "矛盾"],
    "民生保障": ["就业", "教育", "医疗", "养老", "住房", "民生", "保障"],
    "乡村振兴 / 三农": ["乡村", "农村", "农业", "农民", "农田", "农资", "粮食", "县域", "共同富裕"],
    "生态文明 / 环境治理": ["生态", "绿色", "低碳", "污染", "面源污染", "废弃物", "环保", "环境治理", "牛皮癣"],
    "文化建设": ["文化", "文明", "传统", "非遗", "文旅"],
    "法治治理": ["法治", "执法", "监管", "法律", "依法"],
    "作风建设": ["作风", "形式主义", "减负", "担当", "调查研究"],
}


@dataclass
class Article:
    title: str
    url: str
    source: str
    column: str
    date: dt.date | None = None
    body: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    score: int = 0
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return f"{self.title}\n" + "\n".join(self.body)

    @property
    def published_at(self) -> str:
        return self.date.isoformat() if self.date else "unknown"

    def to_log_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "column": self.column,
            "published_at": self.published_at,
            "tags": self.tags,
            "themes": self.themes,
            "score": self.score,
            "source_evidence": self.evidence,
        }


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def assign_tags(article: Article) -> list[str]:
    text = article.text
    tags = [tag for tag, words in TAG_KEYWORDS.items() if any(word in text for word in words)]
    return tags or ["申论素材"]


def assign_themes(article: Article) -> list[str]:
    text = article.text
    agriculture_env = ["农业面源污染", "农资废弃物", "农田治理", "农田", "牛皮癣", "秸秆", "地膜", "农药包装"]
    tech_core = ["人工智能", "数字化", "专利", "技术突破", "科研", "芯片", "算法", "成果转化", "实验室"]
    if any(word in text for word in agriculture_env):
        themes = ["生态文明 / 环境治理", "乡村振兴 / 三农", "基层治理"]
        if any(word in text for word in tech_core):
            themes.append("科技创新 / 新质生产力")
        return themes[:3]
    themes = [theme for theme, words in THEME_KEYWORDS.items() if any(word in text for word in words)]
    return themes[:3] or ["其他"]


def primary_theme(article: Article) -> str:
    if not article.themes:
        article.themes = assign_themes(article)
    return article.themes[0] if article.themes else "其他"


def score_article(article: Article) -> int:
    text = article.text
    score = 0
    score += min(len(article.body), 8)
    if article.source in {"人民日报图文数据库", "人民网观点", "人民网评", "半月谈", "求是网"}:
        score += 9
    elif article.source in {"浙江宣传", "新华社", "中国青年报"}:
        score += 6
    else:
        score += 4
    high_value_columns = ["人民日报图文数据库", "人民时评", "仲音", "评论员观察", "人民网评", "人民锐评", "今日谈", "时政讲解", "评论", "基层治理", "浙江宣传", "时评", "理论", "党建", "地方网评", "求是网评", "青平", "中青在线"]
    score += 7 if any(key in article.column for key in high_value_columns) else 2
    if any(word in article.title for word in ["评论", "锐评", "网评", "时评", "观察", "解读"]):
        score += 8
    for words in THEME_KEYWORDS.values():
        score += min(sum(text.count(word) for word in words), 4)
    if 600 <= len(text) <= 5000:
        score += 5
    if is_noise_article(article):
        score -= 20
    return score


def is_authoritative_unknown_date(article: Article) -> bool:
    text = article.text
    return any(word in text for word in ["评论", "解读", "观察", "时评", "政策", "治理", "民生", "基层"])


def is_noise_article(article: Article) -> bool:
    text = article.text
    url = (article.url or "").lower()
    title = article.title or ""
    bad_titles = {
        "\u5149\u660e\u7f51\u8bc4\u8bba\u5458",  # 光明网评论员
        "\u5168\u90e8\u5bfc\u822a",  # 全部导航
    }
    if title in bad_titles or (title.endswith("\u8bc4\u8bba\u5458") and len(title) <= 8):
        return True
    if "gmw.cn/" in url and re.search(r"/node_\d+\.htm", url):
        return True
    if any(part in url for part in ["special", "specials", "/zt", "zt/", "photo", "pic", "images"]):
        return True
    noise_words = ["天气", "任免", "快讯", "组图", "图集", "直播", "预警", "开奖"]
    if any(word in title for word in noise_words):
        return True
    if any(word in text[:120] for word in ["天气", "任免", "快讯"]):
        return True
    return False


def candidate_filter_reason(article: Article) -> str | None:
    days = age_days(article)
    if article.date is None and not is_authoritative_unknown_date(article):
        return "发布时间 unknown，且不是明显权威解读/评论文章"
    if days is not None and days > 7:
        return "发布时间超过7天"
    if is_noise_article(article):
        return "疑似专题页/图片新闻/天气任免快讯等低转化内容"
    return None


def age_days(article: Article, today: dt.date | None = None) -> int | None:
    if not article.date:
        return None
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    return (today - article.date).days


def article_sort_key(article: Article, recent_featured_themes: list[str] | None = None) -> tuple[int, int, int, int, str]:
    date_ord = article.date.toordinal() if article.date else 0
    recent_featured_themes = recent_featured_themes or []
    theme_penalty = 1 if primary_theme(article) in recent_featured_themes else 0
    # Within the valid fallback window, prefer stronger exam-conversion signals
    # first; date is the tie breaker so expansion actually improves quality.
    return (theme_penalty, -article.score, -date_ord, 0 if article.date else 1, article.title)


def diversify_articles(pool: list[Article], limit: int, recent_featured_themes: list[str] | None = None) -> list[Article]:
    ordered = sorted(pool, key=lambda item: article_sort_key(item, recent_featured_themes))
    selected: list[Article] = []
    used_sources: set[str] = set()
    used_themes: set[str] = set()
    for article in ordered:
        theme = primary_theme(article)
        if article.source not in used_sources and theme not in used_themes:
            selected.append(article)
            used_sources.add(article.source)
            used_themes.add(theme)
        if len(selected) >= limit:
            return selected
    for article in ordered:
        if article not in selected:
            selected.append(article)
        if len(selected) >= limit:
            return selected
    return selected


def high_quality_count(pool: list[Article], threshold: int) -> int:
    return sum(1 for item in pool if item.score >= threshold)


def enrich_and_filter_with_stats(
    articles: list[Article],
    limit: int,
    history_index: dict[str, object] | None = None,
) -> tuple[list[Article], dict[str, object]]:
    history_index = history_index or {}
    seen: set[str] = set()
    cleaned: list[Article] = []
    excluded: list[dict[str, str]] = []
    for article in articles:
        key = article.url or article.title
        if not key or key in seen:
            continue
        seen.add(key)
        article.tags = assign_tags(article)
        article.themes = assign_themes(article)
        filter_reason = candidate_filter_reason(article)
        article.score = score_article(article)
        if filter_reason:
            excluded.append({"title": article.title, "reason": filter_reason})
            continue
        if article.body and article.score >= 10:
            cleaned.append(article)

    source_details: dict[str, list[dict[str, str]]] = {}
    for article in cleaned:
        source_details.setdefault(article.source, []).append(
            {
                "title": article.title,
                "published_at": article.published_at,
                "url": article.url,
                "theme": primary_theme(article),
            }
        )

    featured_urls = set(history_index.get("featured_7_urls", set()))
    featured_titles = set(history_index.get("featured_7_titles", set()))
    quick_urls = set(history_index.get("quick_3_urls", set()))
    quick_titles = set(history_index.get("quick_3_titles", set()))
    manual_block_titles = set(history_index.get("manual_block_titles", set()))
    manual_block_urls = set(history_index.get("manual_block_urls", set()))

    hard_filtered: list[Article] = []
    soft_duplicates: list[Article] = []
    for article in cleaned:
        title_key = normalize_title(article.title)
        if (article.url and article.url in manual_block_urls) or title_key in manual_block_titles:
            excluded.append({"title": article.title, "reason": "命中手动屏蔽列表 BLOCK_TITLES/BLOCK_URLS"})
            continue
        if (article.url and article.url in featured_urls) or title_key in featured_titles:
            excluded.append({"title": article.title, "reason": "最近7天已作为featured发送"})
            continue
        if (article.url and article.url in quick_urls) or title_key in quick_titles:
            soft_duplicates.append(article)
            continue
        hard_filtered.append(article)

    if len(hard_filtered) >= limit:
        cleaned = hard_filtered
        for article in soft_duplicates:
            excluded.append({"title": article.title, "reason": "最近3天已作为quick_read发送"})
        quick_repeat_relaxed = False
    else:
        cleaned = hard_filtered + soft_duplicates
        quick_repeat_relaxed = bool(soft_duplicates)

    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    recent48 = [item for item in cleaned if (age_days(item, today) is not None and age_days(item, today) <= 2)]
    recent3 = [item for item in cleaned if (age_days(item, today) is not None and age_days(item, today) <= 3)]
    recent7 = [item for item in cleaned if (age_days(item, today) is not None and age_days(item, today) <= 7)]
    older = [item for item in cleaned if (age_days(item, today) is not None and age_days(item, today) > 7)]
    unknown = [item for item in cleaned if age_days(item, today) is None]

    recent_themes = list(history_index.get("recent_featured_themes_3d", []))
    min_candidate_pool = min(limit, 6)
    quality_threshold = 30
    high_quality_min = min(3, min_candidate_pool)
    recent48_high_quality_count = high_quality_count(recent48, quality_threshold)
    recent3_high_quality_count = high_quality_count(recent3, quality_threshold)
    recent7_high_quality_count = high_quality_count(recent7, quality_threshold)
    if len(recent48) >= min_candidate_pool and recent48_high_quality_count >= high_quality_min:
        selected_window = "48h"
        eligible = recent48
        selected_window_reason = "48小时内高质量候选充足"
    elif len(recent3) >= min_candidate_pool and recent3_high_quality_count >= high_quality_min:
        selected_window = "3d"
        eligible = recent3
        selected_window_reason = "48小时内候选数量或高质量候选不足，扩展到3天内"
    elif recent7:
        selected_window = "7d"
        eligible = recent7
        selected_window_reason = "3天内候选数量或高质量候选不足，扩展到7天内"
    else:
        selected_window = "unknown_date"
        eligible = unknown
        selected_window_reason = "7天内无可用日期候选，使用未知日期权威候选"

    selected = diversify_articles(eligible, limit, recent_themes)

    selected = selected[:limit]
    uses_over_3_days = any((age_days(item, today) or 0) > 3 for item in selected if item.date)
    old_reason = ""
    if uses_over_3_days:
        old_reason = "近48小时内候选文章不足；该旧文章具有较高申论/面试转化价值。"

    stats: dict[str, object] = {
        "candidate_count": len(cleaned),
        "raw_candidate_count": len(articles),
        "recent_48h_count": len(recent48),
        "recent_3d_count": len(recent3),
        "recent_7d_count": len(recent7),
        "selected_time_window": selected_window,
        "selected_time_window_min_candidate_pool": min_candidate_pool,
        "selected_time_window_reason": selected_window_reason,
        "quality_window_score_threshold": quality_threshold,
        "quality_window_min_high_quality_count": high_quality_min,
        "recent_48h_high_quality_count": recent48_high_quality_count,
        "recent_3d_high_quality_count": recent3_high_quality_count,
        "recent_7d_high_quality_count": recent7_high_quality_count,
        "unknown_date_count": len(unknown),
        "older_than_7d_count": len(older),
        "source_candidate_counts": {source: len(items) for source, items in source_details.items()},
        "source_candidate_details": source_details,
        "history_excluded_count": len(excluded),
        "history_excluded": excluded,
        "quick_read_history_relaxed": quick_repeat_relaxed,
        "recent_featured_themes_3d": recent_themes,
        "selected_titles": [item.title for item in selected],
        "selected_published_at": [item.published_at for item in selected],
        "selected_sources": [item.source for item in selected],
        "selected_themes": [primary_theme(item) for item in selected],
        "selected_source_diverse": len({item.source for item in selected}) > 1 if len(selected) > 1 else True,
        "selected_theme_diverse": len({primary_theme(item) for item in selected}) > 1 if len(selected) > 1 else True,
        "uses_over_3_days": uses_over_3_days,
        "over_3_days_reason": old_reason,
    }
    return selected, stats


def enrich_and_filter(articles: list[Article], limit: int) -> list[Article]:
    selected, _ = enrich_and_filter_with_stats(articles, limit)
    return selected

from __future__ import annotations

import datetime as dt
import json
import re
import time
import warnings
from pathlib import Path
from urllib.parse import urljoin

warnings.filterwarnings(
    "ignore",
    message="Unable to find acceptable character detection dependency.*",
)
import requests
from bs4 import BeautifulSoup

from article_filter import Article, clean_text, enrich_and_filter_with_stats
from config import settings
from history import build_history_index, load_history
from history import normalize_title
from fact_evidence import build_source_evidence


TZ = dt.timezone(dt.timedelta(hours=8))
REQUEST_TIMEOUT = int(getattr(settings, "request_timeout", 20)) if hasattr(settings, "request_timeout") else 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_FETCH_LOOKBACK_DAYS = max(7, int(getattr(settings, "lookback_days", 3)))

PEOPLE_SOURCES = {
    "人民网/观点首页": [
        "https://opinion.people.com.cn/",
        "https://opinion.people.com.cn/GB/223228/index.html",
    ],
    "人民时评": [
        "https://opinion.people.com.cn/GB/8213/49160/49219/index.html",
        "https://opinion.people.com.cn/GB/8213/49160/49219/index1.html",
    ],
    "仲音": [
        "https://opinion.people.com.cn/GB/8213/49160/457596/index.html",
        "https://opinion.people.com.cn/GB/8213/49160/457596/index1.html",
    ],
    "评论员观察": [
        "https://opinion.people.com.cn/GB/8213/49160/457597/index.html",
        "https://opinion.people.com.cn/GB/8213/49160/457597/index1.html",
    ],
}

XINHUA_SOURCES = {
    "新华时评/要闻": [
        "https://www.news.cn/politics/",
        "https://www.news.cn/comments/",
    ]
}

BANYUETAN_SOURCES = {
    # 半月谈按高考公转化栏目抓取；把首页放到后面，避免首页候选过多挤占重点栏目。
    "半月谈/今日谈": ["http://www.banyuetan.org/byt/jinritan/index.html"],
    "半月谈/时政讲解": ["http://www.banyuetan.org/byt/shizhengjiangjie/index.html"],
    "半月谈/评论": ["http://www.banyuetan.org/byt/banyuetanpinglun/index.html"],
    "半月谈/基层治理": ["http://www.banyuetan.org/byt/jicengzhili/index.html"],
    "半月谈/首页": ["http://www.banyuetan.org/"],
    # 考试服务站点偏题库/测评，不一定是普通文章列表；先作为可选入口纳入诊断。
    "半月谈/考试服务": ["http://stk.banyuetan.org/"],
}

ZHEJIANG_SOURCES = {
    "浙江宣传": [
        "https://zjnews.zjol.com.cn/ztjj/zjxc/",
        "https://zjnews.zjol.com.cn/",
    ]
}

PEOPLE_COMMENT_SOURCES = {
    "人民网评/人民锐评": [
        "https://opinion.people.com.cn/",
        "https://opinion.people.com.cn/GB/223228/index.html",
        "https://opinion.people.com.cn/GB/436867/index.html",
    ]
}


def people_daily_database_sources(days: int = MAX_FETCH_LOOKBACK_DAYS) -> dict[str, list[str]]:
    today = dt.datetime.now(TZ).date()
    urls = []
    for offset in range(max(0, days) + 1):
        day = today - dt.timedelta(days=offset)
        urls.append(f"https://data.people.com.cn/rmrb/{day:%Y%m%d}/1?code=2")
    return {"人民日报图文数据库/最近7天": urls}

XUEXI_SOURCES = {
    "学习强国/时政综合": [
        "https://www.xuexi.cn/",
        "https://www.xuexi.cn/lgpage/",
    ],
}

GUANGMING_SOURCES = {
    # 光明网只抓更适合公考拆解的精选栏目，避免全站候选过大、主题过散。
    "光明网/时评": ["https://guancha.gmw.cn/"],
    "光明网/理论": ["https://theory.gmw.cn/"],
    "光明网/党建": ["https://dangjian.gmw.cn/"],
    "光明网/地方网评": ["https://topics.gmw.cn/node_139476.htm"],
    "光明网/教育": ["https://edu.gmw.cn/"],
    "光明网/文化": ["https://culture.gmw.cn/"],
}

QIUSHI_SOURCES = {
    "求是网/首页": ["https://www.qstheory.cn/"],
    "求是网/求是网评": ["https://www.qstheory.cn/"],
}

CHINA_YOUTH_SOURCES = {
    "中国青年报/青平": [
        "https://m.cyol.com/gb/channels/qp/index.html",
        "https://news.cyol.com/gb/channels/gDanapkX/index.html",
    ],
    "中国青年报/中青在线首页": ["https://www.cyol.com/"],
}

SOURCE_POOL_LIMIT_OVERRIDES = {
    # 低价值或不稳定来源可单独压低；高价值来源默认走 SOURCE_POOL_MAX。
    "学习强国": min(80, settings.source_pool_max),
    "浙江宣传": min(160, settings.source_pool_max),
}


def source_pool_limit(source: str) -> int:
    return SOURCE_POOL_LIMIT_OVERRIDES.get(source, settings.source_pool_max)


def column_candidate_limit(source: str, column: str) -> int:
    # 半月谈、光明网采用“每栏目上限”，避免总量过低导致栏目轮不到。
    # 首页和考试服务/教育/文化略降，优先保证今日谈、评论、基层治理、时评、理论、党建等高转化栏目。
    base = settings.column_max_candidates
    if source == "半月谈" and any(key in column for key in ["首页", "考试服务"]):
        return max(30, base // 2)
    if source == "光明网" and any(key in column for key in ["教育", "文化"]):
        return max(30, base // 2)
    return base

ARTICLE_SOURCES = [
    "people_daily_database",
    "people_opinion",
    "xinhua",
    "banyuetan",
    "people_comment",
    "zhejiang_xuanchuan",
    "xuexi_qiangguo",
    "guangming",
    "qiushi",
    "china_youth_daily",
]


BAD_LISTING_TITLES = {
    "\u5149\u660e\u7f51\u8bc4\u8bba\u5458",  # 光明网评论员
    "\u5168\u90e8\u5bfc\u822a",  # 全部导航
}


def is_bad_listing_title(title: str) -> bool:
    normalized = clean_text(title)
    if not normalized:
        return True
    if normalized in BAD_LISTING_TITLES:
        return True
    if normalized.endswith("\u8bc4\u8bba\u5458") and len(normalized) <= 8:
        return True
    if normalized in {"\u66f4\u591a", "\u8be6\u60c5", "\u9996\u9875", "\u4e0b\u4e00\u9875"}:
        return True
    return False


def is_probably_article_url(url: str) -> bool:
    lower = (url or "").lower().strip()
    normalized = lower.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "data.people.com.cn/rmrb/" in normalized and re.search(r"/rmrb/20\d{6}/[^/]+/[0-9a-f]{16,}$", normalized):
        return True
    if not re.search(r"\.(html|htm|shtml)$|/c\.html$", normalized):
        return False
    if any(part in normalized for part in ["/video/", "/photo/", "/pic/", "specials", "/zt/"]):
        return False
    # Guangming node pages are channel/list pages. Real articles usually use
    # date paths plus content_*.htm/shtml.
    if "gmw.cn/" in normalized and re.search(r"/node_\d+\.htm", normalized):
        return False
    return True


def fetch_html(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        verify=False,
    )
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = "utf-8"
    return response.text


def parse_date(text: str) -> dt.date | None:
    match = re.search(r"(20\d{2})\s*[-年./]\s*(\d{1,2})\s*[-月./]\s*(\d{1,2})", text)
    if not match:
        return None
    try:
        return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def page_date(soup: BeautifulSoup) -> dt.date | None:
    text = soup.get_text(" ", strip=True)
    return parse_date(text)


def extract_paragraphs(soup: BeautifulSoup) -> list[str]:
    containers = soup.select(".rm_txt_con, .artDet, .main, .content, article")
    root = containers[0] if containers else soup
    paragraphs: list[str] = []
    for p in root.find_all("p"):
        text = clean_text(p.get_text(" ", strip=True))
        if len(text) >= 20 and not re.search(r"责任编辑|版权|新华社客户端", text):
            paragraphs.append(text)
    if paragraphs:
        return paragraphs[:30]
    text = clean_text(root.get_text(" ", strip=True))
    chunks = re.split(r"(?<=[。！？])", text)
    return [clean_text(chunk) for chunk in chunks if len(clean_text(chunk)) >= 30][:20]


def parse_links(html: str, page_url: str, source: str, column: str) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    articles: list[Article] = []
    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))
        if len(title) < 6:
            title = clean_text(link.get("title") or link.get("aria-label") or "")
        if len(title) < 6:
            img = link.find("img")
            if img:
                title = clean_text(img.get("alt") or img.get("title") or "")
        href = link["href"].strip()
        if len(title) < 6 or is_bad_listing_title(title):
            continue
        url = urljoin(page_url, href)
        if not re.search(r"(people|news|data\.people|banyuetan|zjol|xuexi|gmw|qstheory|cyol)\.(cn|org|com)", url):
            continue
        if not is_probably_article_url(url):
            continue
        nearby = clean_text(link.parent.get_text(" ", strip=True) if link.parent else "")
        articles.append(
            Article(
                title=title,
                url=url,
                source=source,
                column=column,
                date=parse_date(nearby),
            )
        )
    return articles


def _decode_js_string(value: str) -> str:
    text = value.replace("\\/", "/")
    if "\\u" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            pass
    return clean_text(text)


def parse_embedded_links(html: str, page_url: str, source: str, column: str) -> list[Article]:
    """Some sites render article lists from inline JSON instead of plain anchors."""
    articles: list[Article] = []
    patterns = [
        re.compile(r'"title"\s*:\s*"([^"]{6,160})".{0,500}?"url"\s*:\s*"([^"]+?\.(?:html|htm|shtml))"', re.S),
        re.compile(r'"url"\s*:\s*"([^"]+?\.(?:html|htm|shtml))".{0,500}?"title"\s*:\s*"([^"]{6,160})"', re.S),
    ]
    for idx, pattern in enumerate(patterns):
        for match in pattern.finditer(html):
            if idx == 0:
                raw_title, raw_url = match.group(1), match.group(2)
            else:
                raw_url, raw_title = match.group(1), match.group(2)
            title = _decode_js_string(raw_title)
            url = urljoin(page_url, _decode_js_string(raw_url))
            if len(title) < 6 or is_bad_listing_title(title):
                continue
            if not re.search(r"(people|news|data\.people|banyuetan|zjol|xuexi|gmw|qstheory|cyol)\.(cn|org|com)", url):
                continue
            if not is_probably_article_url(url):
                continue
            articles.append(
                Article(
                    title=title,
                    url=url,
                    source=source,
                    column=column,
                    date=parse_date(match.group(0)),
                )
            )
    return articles


def parse_people_daily_database_links(html: str, page_url: str, source: str, column: str) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    articles: list[Article] = []
    page_match = re.search(r"/rmrb/(20\d{6})/", page_url)
    article_date = None
    if page_match:
        try:
            article_date = dt.datetime.strptime(page_match.group(1), "%Y%m%d").date()
        except ValueError:
            article_date = None
    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))
        href = link["href"].strip()
        url = urljoin(page_url, href)
        if len(title) < 6 or is_bad_listing_title(title):
            continue
        if not re.search(r"data\.people\.com\.cn/rmrb/20\d{6}/[^/]+/[0-9a-f]{16,}", url):
            continue
        articles.append(
            Article(
                title=title,
                url=url,
                source=source,
                column=column,
                date=article_date,
            )
        )
    return articles


def extract_people_daily_database_paragraphs(soup: BeautifulSoup) -> list[str]:
    root = soup.select_one(".detail_con") or soup.select_one(".div_detail")
    if not root:
        return []
    paragraphs: list[str] = []
    for p in root.find_all("p"):
        text = clean_text(p.get_text(" ", strip=True))
        if len(text) >= 20:
            paragraphs.append(text)
    if paragraphs:
        return paragraphs[:30]
    text = clean_text(root.get_text(" ", strip=True))
    text = re.sub(r"【人民日报\s+20\d{2}-\d{1,2}-\d{1,2}.*?】", " ", text)
    text = re.sub(r"【字号：.*?】", " ", text)
    chunks = re.split(r"(?<=[。！？])", text)
    return [clean_text(chunk) for chunk in chunks if len(clean_text(chunk)) >= 30][:30]


def fetch_article(article: Article) -> Article | None:
    listing_title = article.title
    last_article: Article | None = None
    for attempt in range(1, 3):
        try:
            html = fetch_html(article.url)
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.select_one(".div_detail .title") if "data.people.com.cn/rmrb/" in article.url else None
        heading = heading or soup.find(["h1", "h2"])
        page_title = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        if page_title and not is_bad_listing_title(page_title):
            article.title = page_title
        if is_bad_listing_title(article.title):
            return None
        if "data.people.com.cn/rmrb/" in article.url:
            article.body = extract_people_daily_database_paragraphs(soup)
        else:
            article.body = extract_paragraphs(soup)
        article.date = article.date or page_date(soup)
        article.evidence = build_source_evidence(
            title=article.title,
            source=article.source,
            published_at=article.published_at,
            url=article.url,
            paragraphs=article.body,
            listing_title=listing_title,
            page_title=page_title or article.title,
            fetch_attempts=attempt,
        )
        last_article = article
        if article.evidence.get("verification_status") == "verified":
            return article
    # An incomplete response is retained only for diagnostics. It must not enter
    # the selection pool as if a title/summary or HTTP 200 proved full text.
    return None if last_article is None or last_article.evidence.get("verification_status") != "verified" else last_article


def is_recent(article: Article, lookback_days: int) -> bool:
    if not article.date:
        return True
    today = dt.datetime.now(TZ).date()
    delta = (today - article.date).days
    return 0 <= delta <= lookback_days


def load_mock_articles() -> list[Article]:
    path = Path(__file__).with_name("mock_articles.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    articles: list[Article] = []
    mock_date = dt.datetime.now(TZ).date() if settings.run_mode == "test" else None
    for item in data:
        article_date = mock_date or parse_date(item.get("date", ""))
        articles.append(
            Article(
                title=item["title"],
                url=item.get("url", ""),
                source=item.get("source", "样例来源"),
                column=item.get("column", "样例栏目"),
                date=article_date,
                body=item.get("body", []),
            )
        )
    return articles


def fetch_prod_articles() -> tuple[list[Article], dict[str, object]]:
    articles: list[Article] = []
    fetch_status: dict[str, object] = {}
    source_pages = [
        ("人民日报图文数据库", people_daily_database_sources()),
        ("人民网观点", PEOPLE_SOURCES),
        ("人民网评", PEOPLE_COMMENT_SOURCES),
        ("新华社", XINHUA_SOURCES),
        ("半月谈", BANYUETAN_SOURCES),
        ("浙江宣传", ZHEJIANG_SOURCES),
        ("学习强国", XUEXI_SOURCES),
        ("光明网", GUANGMING_SOURCES),
        ("求是网", QIUSHI_SOURCES),
        ("中国青年报", CHINA_YOUTH_SOURCES),
    ]
    for source, pages in source_pages:
        source_found = 0
        source_errors: list[str] = []
        source_called = False
        page_debug: list[dict[str, object]] = []
        source_limit = source_pool_limit(source)
        source_stats: dict[str, int] = {
            "pages_configured": sum(len(urls) for urls in pages.values()),
            "pages_fetched": 0,
            "anchor_count": 0,
            "parsed_anchor_candidates": 0,
            "parsed_embedded_candidates": 0,
            "unique_candidates": 0,
            "recent_candidates": 0,
            "article_fetch_ok": 0,
            "article_fetch_failed": 0,
            "not_recent_filtered": 0,
            "source_max_candidates": source_limit,
            "column_max_candidates_default": settings.column_max_candidates,
            "source_limit_hit": 0,
        }
        for column, urls in pages.items():
            page_limit = column_candidate_limit(source, column)
            for page_url in urls:
                source_called = True
                page_started = time.time()
                page_row: dict[str, object] = {"column": column, "url": page_url, "page_limit": page_limit}
                try:
                    html = fetch_html(page_url)
                except Exception as exc:
                    source_errors.append(f"{page_url}: {exc}")
                    page_row.update({"status": "error", "error": str(exc)[:180], "elapsed_sec": round(time.time() - page_started, 2)})
                    page_debug.append(page_row)
                    continue

                soup = BeautifulSoup(html, "html.parser")
                anchor_count = len(soup.find_all("a", href=True))
                if source == "人民日报图文数据库":
                    anchor_candidates = parse_people_daily_database_links(html, page_url, source, column)
                    embedded_candidates = []
                else:
                    anchor_candidates = parse_links(html, page_url, source, column)
                    embedded_candidates = parse_embedded_links(html, page_url, source, column)
                page_candidates = anchor_candidates + embedded_candidates
                seen_page_urls: set[str] = set()
                unique_candidates: list[Article] = []
                for candidate in page_candidates:
                    if candidate.url in seen_page_urls:
                        continue
                    seen_page_urls.add(candidate.url)
                    unique_candidates.append(candidate)

                recent_candidates: list[Article] = []
                not_recent_count = 0
                for candidate in unique_candidates:
                    if not is_recent(candidate, MAX_FETCH_LOOKBACK_DAYS):
                        not_recent_count += 1
                        continue
                    recent_candidates.append(candidate)

                article_fetch_ok = 0
                article_fetch_failed = 0
                for candidate in recent_candidates:
                    if source_found >= source_limit:
                        source_stats["source_limit_hit"] = 1
                        break
                    if article_fetch_ok >= page_limit:
                        break
                    full = fetch_article(candidate)
                    if full:
                        articles.append(full)
                        source_found += 1
                        article_fetch_ok += 1
                    else:
                        article_fetch_failed += 1

                source_stats["pages_fetched"] += 1
                source_stats["anchor_count"] += anchor_count
                source_stats["parsed_anchor_candidates"] += len(anchor_candidates)
                source_stats["parsed_embedded_candidates"] += len(embedded_candidates)
                source_stats["unique_candidates"] += len(unique_candidates)
                source_stats["recent_candidates"] += len(recent_candidates)
                source_stats["article_fetch_ok"] += article_fetch_ok
                source_stats["article_fetch_failed"] += article_fetch_failed
                source_stats["not_recent_filtered"] += not_recent_count

                page_row.update(
                    {
                        "status": "ok",
                        "html_chars": len(html),
                        "anchors": anchor_count,
                        "parsed_anchor_candidates": len(anchor_candidates),
                        "parsed_embedded_candidates": len(embedded_candidates),
                        "unique_candidates": len(unique_candidates),
                        "recent_candidates": len(recent_candidates),
                        "not_recent_filtered": not_recent_count,
                        "article_fetch_ok": article_fetch_ok,
                        "article_fetch_failed": article_fetch_failed,
                        "sample_titles": [item.title for item in unique_candidates[:5]],
                        "elapsed_sec": round(time.time() - page_started, 2),
                    }
                )
                page_debug.append(page_row)
        if source_found:
            status = "ok"
        elif source_called and source_errors and source_stats.get("pages_fetched", 0) == 0:
            status = "all_pages_error"
        elif source_called:
            status = "called_but_zero"
        else:
            status = "not_implemented"
        fetch_status[source] = {
            "called": source_called,
            "found": source_found,
            "errors": source_errors[:5],
            "status": status,
            "diagnostics": source_stats,
            "page_debug": page_debug[:8],
        }
    fetch_status["reserved_sources"] = {}
    return articles, fetch_status

def get_candidate_articles_with_stats() -> tuple[list[Article], dict[str, object]]:
    history, history_meta = load_history(settings.history_path)
    history_index = build_history_index(history)
    history_index["manual_block_titles"] = {normalize_title(title) for title in settings.blocked_titles}
    history_index["manual_block_urls"] = set(settings.blocked_urls)
    if settings.run_mode == "test":
        raw = load_mock_articles()
        for article in raw:
            article.evidence = build_source_evidence(
                title=article.title,
                source=article.source,
                published_at=article.published_at,
                url=article.url,
                paragraphs=article.body,
            )
        fetch_status = {"mock": {"called": True, "found": len(raw), "status": "ok"}}
    else:
        raw, fetch_status = fetch_prod_articles()
        if not raw:
            fetch_status["fallback"] = {
                "called": False,
                "found": 0,
                "status": "blocked_no_verified_full_text",
                "reason": "生产候选不得用样例标题/摘要替代未核验全文。",
            }
    articles, stats = enrich_and_filter_with_stats(raw, settings.llm_selection_pool_max, history_index)
    stats.update(history_meta)
    stats["output_max_articles"] = settings.max_articles
    stats["llm_selection_pool_max"] = settings.llm_selection_pool_max
    stats["column_max_candidates"] = settings.column_max_candidates
    stats["source_pool_max"] = settings.source_pool_max
    stats["history_recent_featured_themes_3d"] = history_index.get("recent_featured_themes_3d", [])
    stats["history_recent_featured_sources_3d"] = history_index.get("recent_featured_sources_3d", [])
    stats["history_recent_featured_items_7d"] = history_index.get("recent_featured_items_7d", [])
    stats["history_yesterday_featured_titles"] = history_index.get("yesterday_featured_titles", [])
    stats["manual_block_titles"] = settings.blocked_titles
    stats["manual_block_urls_count"] = len(settings.blocked_urls)
    source_counts = dict(stats.get("source_candidate_counts", {}))
    stats["configured_article_sources"] = ARTICLE_SOURCES
    stats["source_fetch_status"] = fetch_status
    stats["source_zero_warnings"] = [
        source for source in ["人民日报图文数据库", "人民网观点", "新华社"]
        if source_counts.get(source, 0) == 0
    ]
    zero_reasons: dict[str, str] = {}
    for source in stats["source_zero_warnings"]:
        status = fetch_status.get(source, {})
        if not status:
            zero_reasons[source] = "未实现抓取"
        elif status.get("status") == "called_but_zero":
            zero_reasons[source] = "抓取函数已调用，但未解析到可用候选；可能是页面结构变化、网络/证书问题或候选被过滤"
        else:
            zero_reasons[source] = str(status.get("status", "unknown"))
    for source in ["半月谈", "人民网评", "浙江宣传", "学习强国", "光明网", "求是网", "中国青年报"]:
        if source not in source_counts:
            status = fetch_status.get(source, {})
            diagnostics = status.get("diagnostics", {}) if isinstance(status, dict) else {}
            if source == "人民网评" and source_counts.get("人民网观点", 0) > 0:
                zero_reasons[source] = "当前人民网评入口与人民网观点入口高度重合，候选可能已按URL去重并计入‘人民网观点’；请看 source fetch diagnostics 判断是否确实解析到候选。"
            elif status.get("called"):
                if diagnostics.get("pages_fetched", 0) == 0:
                    zero_reasons[source] = "入口页未成功抓取，优先检查网络、证书、反爬或入口URL。"
                elif diagnostics.get("unique_candidates", 0) == 0:
                    zero_reasons[source] = "入口页可访问，但未解析出文章候选，优先检查链接解析规则或页面是否JS动态渲染。"
                elif diagnostics.get("recent_candidates", 0) == 0:
                    zero_reasons[source] = "已解析出候选，但全部被日期窗口过滤，优先检查日期解析或LOOKBACK_DAYS。"
                elif diagnostics.get("article_fetch_ok", 0) == 0:
                    zero_reasons[source] = "已有近期候选，但文章正文抓取失败，优先检查正文解析规则或文章页访问限制。"
                else:
                    zero_reasons[source] = "抓取端已有候选，但后续去重/考试价值筛选后未进入最终候选池。"
            else:
                zero_reasons[source] = "未实现抓取"
    stats["source_zero_reasons"] = zero_reasons
    if stats["source_zero_warnings"]:
        stats["source_balance_note"] = "其他来源候选为0时，quick_read 仍可能来自新华社；本次不声称已实现来源均衡。"
    stats["reserved_sources_note"] = "人民日报图文数据库、半月谈、人民网评/人民锐评、浙江宣传、学习强国、光明网、求是网、中国青年报已纳入抓取配置；若为0会在 source_fetch_status 中记录原因。"
    return articles, stats


def get_candidate_articles() -> list[Article]:
    articles, _ = get_candidate_articles_with_stats()
    return articles

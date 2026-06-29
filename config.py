import os
from dataclasses import dataclass
from pathlib import Path


def get_env(name: str, default: str = "", required: bool = False) -> str:
    value = os.environ.get(name, default).strip()
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    run_mode: str = get_env("RUN_MODE", "prod").lower()
    timezone: str = get_env("TIMEZONE", "Asia/Shanghai")
    max_articles: int = int(get_env("MAX_ARTICLES", "6"))
    lookback_days: int = int(get_env("LOOKBACK_DAYS", "3"))
    # 抓取与筛选池控制：
    # COLUMN_MAX_CANDIDATES：每个栏目最多抓取并解析的文章数。
    # SOURCE_POOL_MAX：每个来源最多进入程序筛选池的文章数。
    # LLM_SELECTION_POOL_MAX：最终送给大模型做主线/速读选择的候选数。
    column_max_candidates: int = int(get_env("COLUMN_MAX_CANDIDATES", "80"))
    source_pool_max: int = int(get_env("SOURCE_POOL_MAX", "240"))
    llm_selection_pool_max: int = int(get_env("LLM_SELECTION_POOL_MAX", "300"))
    llm_article_body_paragraphs: int = int(get_env("LLM_ARTICLE_BODY_PARAGRAPHS", "3"))
    llm_article_paragraph_chars: int = int(get_env("LLM_ARTICLE_PARAGRAPH_CHARS", "160"))
    # 两阶段大模型：第一阶段只选文章；第二阶段用更完整的主线正文生成邮件。
    llm_two_stage_enabled: bool = get_bool("LLM_TWO_STAGE_ENABLED", True)
    featured_article_max_chars: int = int(get_env("FEATURED_ARTICLE_MAX_CHARS", "8000"))
    quick_read_article_max_chars: int = int(get_env("QUICK_READ_ARTICLE_MAX_CHARS", "1800"))
    output_dir: Path = Path(get_env("OUTPUT_DIR", "/tmp/gongkao-morning-mailer"))
    send_email: bool = get_bool("SEND_EMAIL", True)
    attach_daily_pdf: bool = get_bool("ATTACH_DAILY_PDF", False)
    enable_weekly_pdf: bool = get_bool("ENABLE_WEEKLY_PDF", False)
    weekly_pdf_days: int = int(get_env("WEEKLY_PDF_DAYS", "7"))
    weekly_pdf_prefix: str = get_env("WEEKLY_PDF_PREFIX", "gongkao-morning-mailer/weekly").strip().strip("/")
    weekly_pdf_send_email: bool = get_bool("WEEKLY_PDF_SEND_EMAIL", True)
    weekly_pdf_attach: bool = get_bool("WEEKLY_PDF_ATTACH", True)
    # 周末晨读自动附加周 PDF：Python weekday：周一=0，周六=5，周日=6。
    weekly_pdf_attach_on_weekend: bool = get_bool("WEEKLY_PDF_ATTACH_ON_WEEKEND", False)
    weekly_pdf_weekday: int = int(get_env("WEEKLY_PDF_WEEKDAY", "6"))
    daily_archive_enabled: bool = get_bool("DAILY_ARCHIVE_ENABLED", True)
    official_send_hour: int = int(get_env("OFFICIAL_SEND_HOUR", "7"))
    official_send_minute: int = int(get_env("OFFICIAL_SEND_MINUTE", "20"))
    official_archive_window_minutes: int = int(get_env("OFFICIAL_ARCHIVE_WINDOW_MINUTES", "45"))
    official_archive_start_hour: int = int(get_env("OFFICIAL_ARCHIVE_START_HOUR", "7"))
    official_archive_start_minute: int = int(get_env("OFFICIAL_ARCHIVE_START_MINUTE", "0"))
    official_archive_end_hour: int = int(get_env("OFFICIAL_ARCHIVE_END_HOUR", "9"))
    official_archive_end_minute: int = int(get_env("OFFICIAL_ARCHIVE_END_MINUTE", "30"))
    daily_archive_prefix: str = get_env("DAILY_ARCHIVE_PREFIX", "gongkao-morning-mailer/daily").strip().strip("/")
    history_write_official_only: bool = get_bool("HISTORY_WRITE_OFFICIAL_ONLY", True)
    history_storage: str = get_env("HISTORY_STORAGE", "local").lower()
    candidate_storage: str = get_env("CANDIDATE_STORAGE", get_env("HISTORY_STORAGE", "local")).lower()
    candidate_prefix: str = get_env("CANDIDATE_PREFIX", "gongkao-morning-mailer/candidates").strip().strip("/")
    harness_metrics_enabled: bool = get_bool("HARNESS_METRICS_ENABLED", True)
    harness_metrics_file: str = get_env("HARNESS_METRICS_FILE", "harness_metrics.jsonl").strip()
    oss_endpoint: str = get_env("OSS_ENDPOINT")
    oss_bucket: str = get_env("OSS_BUCKET")
    oss_access_key_id: str = get_env("OSS_ACCESS_KEY_ID")
    oss_access_key_secret: str = get_env("OSS_ACCESS_KEY_SECRET")
    oss_object_key: str = get_env("OSS_OBJECT_KEY", "gongkao-morning-mailer/sent_history.json")
    blocked_titles_raw: str = get_env("BLOCK_TITLES")
    blocked_urls_raw: str = get_env("BLOCK_URLS")

    dashscope_api_key: str = get_env("DASHSCOPE_API_KEY")
    dashscope_base_url: str = get_env(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ).rstrip("/")
    llm_model: str = get_env("QWEN_MODEL") or get_env("LLM_MODEL", "qwen-plus-2025-07-14")
    llm_fallback_model: str = get_env("LLM_FALLBACK_MODEL", "qwen-plus")
    # 分阶段模型：A 选文章 / B 写邮件。未显式配置时回退到 llm_model。
    selection_llm_model: str = get_env("SELECTION_LLM_MODEL")
    selection_llm_fallback_model: str = get_env("SELECTION_LLM_FALLBACK_MODEL")
    writing_llm_model: str = get_env("WRITING_LLM_MODEL")
    writing_llm_fallback_model: str = get_env("WRITING_LLM_FALLBACK_MODEL")
    # 手动测试专用模型：测试事件 {"mode":"test"} 生效时优先使用。
    # 可填 qwen-plus / qwen-turbo / qwen-flash 等低成本模型；填 mock 则完全跳过大模型调用。
    test_llm_model: str = get_env("TEST_LLM_MODEL") or get_env("LLM_TEST_MODEL")
    test_llm_fallback_model: str = get_env("TEST_LLM_FALLBACK_MODEL") or get_env("LLM_TEST_FALLBACK_MODEL")
    test_selection_llm_model: str = get_env("TEST_SELECTION_LLM_MODEL")
    test_selection_llm_fallback_model: str = get_env("TEST_SELECTION_LLM_FALLBACK_MODEL")
    test_writing_llm_model: str = get_env("TEST_WRITING_LLM_MODEL")
    test_writing_llm_fallback_model: str = get_env("TEST_WRITING_LLM_FALLBACK_MODEL")
    llm_temperature: float = float(get_env("LLM_TEMPERATURE", "0.3"))
    llm_timeout: int = int(get_env("LLM_TIMEOUT", "120"))
    llm_selection_timeout: int = int(get_env("LLM_SELECTION_TIMEOUT", str(llm_timeout)))
    llm_writing_timeout: int = int(get_env("LLM_WRITING_TIMEOUT", "180"))
    content_quality_enabled: bool = get_bool("CONTENT_QUALITY_ENABLED", True)
    content_quality_llm_model: str = get_env("CONTENT_QUALITY_LLM_MODEL") or get_env("QUALITY_LLM_MODEL")
    content_quality_llm_fallback_model: str = get_env("CONTENT_QUALITY_LLM_FALLBACK_MODEL") or get_env("QUALITY_LLM_FALLBACK_MODEL")
    test_content_quality_llm_model: str = get_env("TEST_CONTENT_QUALITY_LLM_MODEL")
    test_content_quality_llm_fallback_model: str = get_env("TEST_CONTENT_QUALITY_LLM_FALLBACK_MODEL")
    content_quality_timeout: int = int(get_env("CONTENT_QUALITY_TIMEOUT", str(llm_timeout)))
    quality_rewrite_enabled: bool = get_bool("QUALITY_REWRITE_ENABLED", True)
    quality_rewrite_max_rounds: int = int(get_env("QUALITY_REWRITE_MAX_ROUNDS", "1"))
    daily_question_multi_candidate_enabled: bool = get_bool("DAILY_QUESTION_MULTI_CANDIDATE_ENABLED", True)
    weekly_material_multi_candidate_enabled: bool = get_bool("WEEKLY_MATERIAL_MULTI_CANDIDATE_ENABLED", True)
    question_bank_enabled: bool = get_bool("QUESTION_BANK_ENABLED", True)
    question_bank_source: str = get_env("QUESTION_BANK_SOURCE", "local").lower()
    question_bank_local_path: str = get_env("QUESTION_BANK_LOCAL_PATH", "data/question_bank/shenlun_question_bank_v3_a.csv")
    question_bank_oss_key: str = get_env("QUESTION_BANK_OSS_KEY", "question_bank/shenlun_question_bank_v3_a.csv").strip().lstrip("/")
    question_bank_match_limit: int = int(get_env("QUESTION_BANK_MATCH_LIMIT", "3"))
    question_bank_recent_days_dedup: int = int(get_env("QUESTION_BANK_RECENT_DAYS_DEDUP", "7"))
    question_bank_fail_open: bool = get_bool("QUESTION_BANK_FAIL_OPEN", True)
    knowledge_base_mode: str = get_env("KNOWLEDGE_BASE_MODE", "local").lower()
    knowledge_base_dir: Path = Path(get_env("KNOWLEDGE_BASE_DIR", "knowledge_base"))
    knowledge_oss_prefix: str = get_env("KNOWLEDGE_OSS_PREFIX", "").strip().strip("/")

    smtp_host: str = get_env("SMTP_HOST", "smtp.qq.com")
    smtp_port: int = int(get_env("SMTP_PORT", "465"))
    smtp_user: str = get_env("SMTP_USER")
    smtp_password: str = get_env("SMTP_PASSWORD") or get_env("SMTP_PASS")
    mail_from: str = get_env("MAIL_FROM") or get_env("SMTP_USER")
    recipients_raw: str = get_env("RECIPIENTS") or get_env("MAIL_TO")
    test_recipients_raw: str = get_env("TEST_RECIPIENTS")
    admin_report_enabled: bool = get_bool("ADMIN_REPORT_ENABLED", True)
    admin_report_send_email: bool = get_bool("ADMIN_REPORT_SEND_EMAIL", send_email)
    admin_report_emails_raw: str = get_env("ADMIN_REPORT_EMAILS") or get_env("ADMIN_EMAILS")
    subscribers_storage: str = get_env("SUBSCRIBERS_STORAGE", "local").lower()
    subscribers_oss_key: str = get_env("SUBSCRIBERS_OSS_KEY", "gongkao-morning-mailer/subscribers.csv").strip().lstrip("/")
    send_mode: str = get_env("SEND_MODE", "bcc").lower()
    subject_prefix: str = get_env("MAIL_SUBJECT_PREFIX", "【公考晨读】")
    feedback_base_url: str = get_env("FEEDBACK_BASE_URL").strip()
    paid_trial_entry_url: str = get_env("PAID_TRIAL_ENTRY_URL").strip()
    referral_entry_url: str = get_env("REFERRAL_ENTRY_URL").strip()
    unsubscribe_email_raw: str = get_env("UNSUBSCRIBE_EMAIL").strip()
    unsubscribe_mode: str = get_env("UNSUBSCRIBE_MODE", "mailto").strip().lower()
    feedback_prefix: str = get_env("FEEDBACK_PREFIX", "gongkao-morning-mailer/feedback").strip().strip("/")
    download_tracking_secret: str = get_env("DOWNLOAD_TRACKING_SECRET").strip()
    download_tracking_base_url: str = get_env("DOWNLOAD_TRACKING_BASE_URL").strip()
    download_tracking_prefix: str = get_env("DOWNLOAD_TRACKING_PREFIX", "analytics/pdf_clicks").strip().strip("/")

    @property
    def history_path(self) -> Path:
        return self.output_dir / "sent_history.json"

    @property
    def harness_metrics_path(self) -> Path:
        path = Path(self.harness_metrics_file or "harness_metrics.jsonl")
        return path if path.is_absolute() else self.output_dir / path

    @property
    def knowledge_base_path(self) -> Path:
        return self.knowledge_base_dir if self.knowledge_base_dir.is_absolute() else Path(__file__).resolve().parent / self.knowledge_base_dir

    @property
    def policy_corpus_path(self) -> Path:
        return self.knowledge_base_path / "policy_corpus"

    @property
    def topic_knowledge_path(self) -> Path:
        return self.knowledge_base_path / "topic_knowledge"

    @property
    def recipients(self) -> list[str]:
        return [
            item.strip()
            for item in self.recipients_raw.replace(";", ",").split(",")
            if item.strip()
        ]

    @property
    def test_recipients(self) -> list[str]:
        return [
            item.strip()
            for item in self.test_recipients_raw.replace(";", ",").split(",")
            if item.strip()
        ]

    @property
    def admin_report_emails(self) -> list[str]:
        return [
            item.strip()
            for item in self.admin_report_emails_raw.replace(";", ",").split(",")
            if item.strip()
        ]

    @property
    def unsubscribe_email(self) -> str:
        if self.unsubscribe_email_raw:
            return self.unsubscribe_email_raw
        if self.admin_report_emails:
            return self.admin_report_emails[0]
        return self.smtp_user.strip()

    @property
    def blocked_titles(self) -> list[str]:
        return [item.strip() for item in self.blocked_titles_raw.replace("；", ";").replace(",", ";").split(";") if item.strip()]

    @property
    def blocked_urls(self) -> list[str]:
        return [item.strip() for item in self.blocked_urls_raw.replace("；", ";").replace(",", ";").split(";") if item.strip()]


settings = Settings()

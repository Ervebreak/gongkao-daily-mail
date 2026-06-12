import main
import policy_coordinate_reranker as reranker
import policy_coordinate_usage_history as usage_history
import knowledge_base_loader as kb


class CaptureLogger:
    def __init__(self):
        self.events = []

    def info(self, message, **kwargs):
        self.events.append((message, kwargs))


def _brief_case() -> dict:
    return {
        "today_theme": "正确政绩观",
        "featured_article": {
            "title": "“遮丑”何以变“揭丑”",
            "source": "人民日报",
            "url": "https://example.com/article-1",
            "one_sentence": "文章批评遮丑式整改、应付检查和面子工程，强调接受群众评判、推进系统治理。",
            "core_viewpoint": "整改不能停留在表面文章，而要接受群众评判，形成系统治理闭环。",
            "theme": "正确政绩观",
            "exam_use": ["综合分析", "基层治理"],
        },
        "today_takeaway": {
            "keywords": ["遮丑", "应付检查", "面子工程", "群众评判", "系统治理"],
        },
        "daily_question": {
            "question": "面对遮丑式整改，如何推动真整改、真落实？",
            "question_type": "综合分析",
            "topic_category": "基层治理",
            "exam_focus": "问题整改与政绩观纠偏",
            "answer_framework": ["找准政绩观偏差", "接受群众评判", "形成系统治理闭环"],
        },
    }


def _source_articles() -> list[dict]:
    return [
        {
            "title": "“遮丑”何以变“揭丑”",
            "url": "https://example.com/article-1",
            "body": (
                "一些地方整改停留在遮丑、应付检查和面子工程上，"
                "暴露出重面子轻里子的政绩观偏差。"
                "真正的整改要接受群众评判，把问题摆上台面，"
                "通过系统治理解决表面整改、虚假整改的问题。"
            ),
        }
    ]


def _install_common_kb(monkeypatch):
    monkeypatch.setattr(usage_history, "load_policy_coordinate_usage_history", lambda: ([], {}))
    monkeypatch.setattr(usage_history, "recent_policy_coordinate_usage", lambda history, days=14: [])
    monkeypatch.setattr(
        kb,
        "load_qiushi_article_index",
        lambda: [
            {
                "article_id": "qiushi-1",
                "title": "树立和践行正确政绩观",
                "journal": "《求是》2026年第7期",
                "main_theme": "正确政绩观",
                "sub_themes": ["面子工程", "群众评判"],
                "status": "active",
                "display_priority": 8,
            }
        ],
    )
    monkeypatch.setattr(
        kb,
        "load_qiushi_chunks",
        lambda: [
            {
                "chunk_id": "chunk-1",
                "article_id": "qiushi-1",
                "title": "树立和践行正确政绩观",
                "section_title": "纠偏落实",
                "chunk_text": "要纠治遮丑式整改、面子工程，防止把整改做成表面文章。",
                "theme_tags": ["正确政绩观", "面子工程"],
                "display_ready": True,
            }
        ],
    )
    monkeypatch.setattr(
        kb,
        "load_topic_frameworks",
        lambda: [
            {
                "framework_id": "framework-1",
                "article_id": "qiushi-1",
                "framework_name": "纠治面子工程",
                "framework_items": ["纠治面子工程", "接受群众评判", "形成系统治理闭环"],
                "answer_pattern": "从政绩观偏差切入整改逻辑",
                "theme": "正确政绩观",
                "display_ready": True,
            }
        ],
    )
    monkeypatch.setattr(
        kb,
        "load_qiushi_quotes_core",
        lambda: [
            {
                "quote_id": "quote-correct-performance",
                "article_id": "qiushi-1",
                "short_quote": "重显绩轻潜绩、重面子轻里子，不能把整改做成表面文章。",
                "quote_text": "重显绩轻潜绩、重面子轻里子，不能把整改做成表面文章。",
                "source_title": "树立和践行正确政绩观",
                "theme_level_1": "正确政绩观",
                "theme_level_2": "面子工程",
                "display_ready": True,
                "theme_confidence": "high",
                "usage_tier": "core",
                "display_priority": 9,
                "article_match_keywords": ["重面子轻里子", "面子工程", "整改"],
            },
            {
                "quote_id": "quote-generic-governance",
                "article_id": "qiushi-2",
                "short_quote": "不断提升基层治理效能和服务群众能力。",
                "quote_text": "不断提升基层治理效能和服务群众能力。",
                "source_title": "基层治理现代化",
                "theme_level_1": "基层治理",
                "theme_level_2": "服务群众",
                "display_ready": True,
                "theme_confidence": "high",
                "usage_tier": "display",
                "display_priority": 5,
                "article_match_keywords": ["基层治理", "服务群众"],
            },
        ],
    )
    monkeypatch.setattr(kb, "load_qiushi_quotes_candidates", lambda: [])
    monkeypatch.setattr(
        kb,
        "load_policy_core",
        lambda: [
            {
                "policy_id": "policy-1",
                "policy_quote": "坚持问题导向，推动整改从表面应付转向系统治理。",
                "short_quote": "坚持问题导向，推动整改从表面应付转向系统治理。",
                "plain_explanation": "整改不能停留在遮丑，应当形成系统治理闭环。",
                "source_title": "关于推进作风建设和整改落实的意见",
                "source_type": "policy_statement",
                "theme_level_1": "整改落实",
                "theme_level_2": "系统治理",
                "display_ready": True,
                "theme_confidence": "high",
                "usage_tier": "core",
                "display_priority": 7,
                "article_match_keywords": ["整改", "系统治理", "问题导向"],
                "answer_angles": ["纠偏政绩观", "接受群众监督", "推进系统治理"],
            }
        ],
    )
    monkeypatch.setattr(kb, "load_policy_all", lambda: [])


def test_policy_coordinate_prefers_authoritative_quote_for_correct_performance_case(monkeypatch):
    _install_common_kb(monkeypatch)

    def fake_rerank(**kwargs):
        if kwargs["candidate_family"] == "authoritative_quote":
            return {
                "selected_id": "quote-correct-performance",
                "fit_score": 86,
                "reason": "准确解释了文章批评的重面子轻里子和遮丑式整改。",
                "article_connection": "文章直指遮丑、应付检查和面子工程，本句正好对应重面子轻里子的政绩观偏差。",
                "exam_transfer": "可用于申论综合分析中论证纠治面子工程、树立正确政绩观。",
                "display_level": "A",
                "hidden_reason": "",
            }
        raise AssertionError("policy reranker should be skipped after authoritative selection")

    monkeypatch.setattr(reranker, "rerank_policy_coordinate_candidates", fake_rerank)
    brief = _brief_case()
    logger = CaptureLogger()

    coordinate = main.build_policy_coordinate(brief, logger=logger, source_articles=_source_articles())

    assert coordinate["display_evidence_type"] == "qiushi"
    assert coordinate["matched_qiushi_quote_id"] == "quote-correct-performance"
    assert "重面子轻里子" in coordinate["authoritative_quote"]
    assert coordinate["backend_status"] == "ok"
    assert coordinate["policy_match_score"] == 0.0
    assert coordinate["qiushi_match_score"] == 86
    diagnostics = [payload for message, payload in logger.events if message == "policy coordinate diagnostics"]
    assert diagnostics
    assert diagnostics[-1]["policy_statement_rerank_result"]["hidden_reason"] == "skipped_after_authoritative_selected"


def test_policy_coordinate_falls_back_to_policy_when_authoritative_hidden(monkeypatch):
    _install_common_kb(monkeypatch)

    def fake_rerank(**kwargs):
        if kwargs["candidate_family"] == "authoritative_quote":
            return {
                "selected_id": "quote-correct-performance",
                "fit_score": 62,
                "reason": "相关但不够贴合。",
                "article_connection": "",
                "exam_transfer": "",
                "display_level": "hidden",
                "hidden_reason": "authoritative_not_specific_enough",
            }
        return {
            "selected_id": "policy-1",
            "fit_score": 81,
            "reason": "政策语句准确解释了整改要从表面应付转向系统治理。",
            "article_connection": "文章批评遮丑和应付检查，这条政策语句明确要求从表面应付转向系统治理。",
            "exam_transfer": "可用于申论综合分析题中提出整改落实路径。",
            "display_level": "B",
            "hidden_reason": "",
        }

    monkeypatch.setattr(reranker, "rerank_policy_coordinate_candidates", fake_rerank)
    brief = _brief_case()

    coordinate = main.build_policy_coordinate(brief, source_articles=_source_articles())

    assert coordinate["display_evidence_type"] == "policy"
    assert coordinate["matched_policy_id"] == "policy-1"
    assert coordinate["policy_match_score"] == 81
    assert coordinate["qiushi_match_score"] == 0.0


def test_policy_coordinate_hides_when_both_candidate_families_are_generic(monkeypatch):
    _install_common_kb(monkeypatch)

    def fake_rerank(**kwargs):
        if kwargs["candidate_family"] == "authoritative_quote":
            return {
                "selected_id": "quote-generic-governance",
                "fit_score": 58,
                "reason": "只是泛泛对应基层治理。",
                "article_connection": "",
                "exam_transfer": "",
                "display_level": "hidden",
                "hidden_reason": "authoritative_too_generic",
            }
        return {
            "selected_id": "policy-1",
            "fit_score": 71,
            "reason": "政策也只是一般相关。",
            "article_connection": "",
            "exam_transfer": "",
            "display_level": "hidden",
            "hidden_reason": "policy_too_generic",
        }

    monkeypatch.setattr(reranker, "rerank_policy_coordinate_candidates", fake_rerank)
    brief = _brief_case()

    coordinate = main.build_policy_coordinate(brief, source_articles=_source_articles())

    assert coordinate["display_evidence_type"] == "none"
    assert brief["_policy_coordinate_disabled_reason"].startswith("weak_match:")

from __future__ import annotations

from question_quality import evaluate_daily_question
from quick_reads_quality import evaluate_quick_reads
from takeaway_quality import evaluate_takeaway


def _base_brief() -> dict:
    return {
        "today_theme": "基层治理",
        "featured_article": {
            "title": "规范研学市场乱象",
            "theme": "教育治理",
            "one_sentence": "部分研学活动存在内容注水、收费不透明等问题。",
        },
    }


def test_quick_reads_block_known_truncated_tails() -> None:
    brief = {
        "quick_reads": [
            {
                "title": "儿童消费治理",
                "source": "人民日报",
                "url": "https://example.com/a",
                "one_sentence": "儿童消费市场治理需要标准前置、执法长牙齿和畅通维",
                "exam_value": "可用于市场监管、消费者权益保护等考点。",
            },
            {
                "title": "青年就业结构矛盾",
                "source": "新华社",
                "url": "https://example.com/b",
                "one_sentence": "剖析青年就业中供需错位问题，提出从教育侧改革、产教联动和信息透明",
                "exam_value": "可用于就业服务、教育改革和产业协同等考点。",
            },
        ]
    }
    report = evaluate_quick_reads(brief)
    codes = {item["code"] for item in report["issues"]}
    assert "truncated_quick_read_one_sentence" in codes
    assert not report["ok"]


def test_takeaway_blocks_known_framework_tail() -> None:
    brief = {
        "today_takeaway": {
            "keywords": ["教育治理", "市场监管"],
            "common_knowledge_points": ["研学活动治理要兼顾教育属性、收费规范和安全责任。"],
            "golden_sentences": [
                {"sentence": "治理不能只看活动热不热，更要看责任实不实。", "scenario": "用于教育治理、市场监管类题目的对策结尾。"},
                {"sentence": "新业态发展越快，规则和责任越要跟上。", "scenario": "用于规范发展、行业治理类题目的分析段。"},
            ],
            "framework": "新兴行业乱象治理：先揭示形式化逐利化问题，再归因于标准缺失与监管漏洞，最后用准入、收费、责任、清退四",
        }
    }
    report = evaluate_takeaway(brief)
    codes = {item["code"] for item in report["issues"]}
    assert "truncated_takeaway" in codes
    assert not report["ok"]


def test_daily_question_blocks_trailing_semicolon_answer() -> None:
    brief = _base_brief()
    brief["daily_question"] = {
        "question_type": "申论对策题",
        "question": "假如你是某区教育局工作人员，近期接到多起家长投诉，反映部分研学活动存在内容注水、中途加价、带队老师无资质等问题。领导要求你提出一套整治措施，你会从哪些方面入手？",
        "exam_focus": "本题考查教育治理中如何回应家长投诉、规范机构行为和压实学校责任。",
        "breaking_hint": "先抓投诉点，再建准入、收费、安全和退出机制。",
        "answer_framework": [
            "摸清情况：梳理投诉和活动底数。",
            "规范准入：建立承办机构白名单。",
            "公开收费：明确价格和退费规则。",
            "压实责任：完善安全和清退机制。",
        ],
        "candidate_answer": "我认为，规范研学活动，关键是把家长反映最集中的问题转化为可执行的治理规则。第一，要全面摸清底数，梳理学校合作机构、活动路线、收费项目和家长投诉。第二，要建立准入机制，对承办机构资质、课程内容和安全预案进行审核。第三，要公开收费规则，防止中途加价和强制消费。第四，对投诉属实的承办方，第一次约谈并全区通报，限期停业整改；",
        "thirty_second_answer": "规范研学活动，不能只看活动办没办，更要看内容是否真实、收费是否透明、安全责任是否压实。",
        "output_prompt": "请用一句话写出这道题的开头表态。",
        "output_sentence_template": "我认为，规范研学活动，关键是让教育属性回到核心位置，让收费、安全和责任都有清晰规则。",
    }
    report = evaluate_daily_question(brief)
    codes = {item["code"] for item in report["issues"]}
    assert "truncated_answer" in codes
    assert not report["ok"]

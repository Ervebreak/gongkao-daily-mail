from policy_profile_builder import build_policy_profile, resolve_policy_profile_text


def test_policy_profile_builder_extracts_problem_value_and_governance_anchors():
    article_title = "“遮丑”何以变“揭丑”"
    article_source = "人民日报"
    article_full_text = (
        "一些地方整改工作停留在遮丑、应付检查和面子工程上，"
        "重面子轻里子，表面热闹却没有解决真实问题。"
        "真正的整改不能只求过关，而要接受群众评判，"
        "把问题摆到台面上，在公开监督下推进系统治理和长效机制建设。"
    )

    profile = build_policy_profile(
        article_title=article_title,
        article_source=article_source,
        article_full_text=article_full_text,
        brief={},
    )

    assert "遮丑" in profile["fine_anchors"]
    assert "揭丑" in profile["fine_anchors"]
    assert "应付检查" in profile["negative_behaviors"]
    assert "面子工程" in profile["negative_behaviors"]
    assert "重面子轻里子" in profile["negative_behaviors"]
    assert "群众评判" in profile["positive_behaviors"]
    assert "系统治理" in profile["positive_behaviors"]
    assert any("申论 面试" in query for query in profile["retrieval_queries"])


def test_policy_profile_builder_falls_back_to_brief_when_full_text_missing():
    brief = {
        "today_theme": "基层治理",
        "featured_article": {
            "title": "把问题整改落到群众感受上",
            "one_sentence": "整改不能停留在表面动作，而要接受群众监督，形成闭环治理。",
            "core_viewpoint": "把群众满意度作为检验整改效果的重要标尺。",
        },
        "daily_question": {
            "question": "如果你负责推进问题整改，如何避免形式主义整改？",
            "exam_focus": "问题导向与群众监督",
        },
    }

    resolved_text, source_kind = resolve_policy_profile_text("", brief)
    profile = build_policy_profile(
        article_title="把问题整改落到群众感受上",
        article_source="人民网",
        article_full_text="",
        brief=brief,
    )

    assert source_kind == "brief_fallback"
    assert resolved_text
    assert profile["core_problem"]
    assert profile["governance_logic"]
    assert profile["value_orientation"]
    assert profile["retrieval_queries"]

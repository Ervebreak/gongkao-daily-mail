from policy_coordinate_topic_anchors import build_policy_topic_anchors


def test_policy_topic_anchors_keep_fine_grained_terms_before_broad_theme():
    brief = {
        "today_theme": "基层减负与形式主义隐形变异",
        "today_three_things": {"theme": "基层减负"},
        "featured_article": {
            "theme": "基层治理",
            "one_sentence": "文章聚焦预制会议、数据包袱、造痕补痕等形式主义隐形变异。",
            "three_useful_points": ["识别留痕负担", "防止层层加码", "推动抓落实"],
            "article_framework_map": {
                "exam_tags": ["基层减负", "形式主义隐形变异", "容错纠错机制"],
                "overall_exam_value": "可用于分析基层减负、问责考核和容错纠错。",
            },
        },
        "daily_question": {"upper_exam_points": ["容错纠错", "考核减负"]},
    }

    anchors = build_policy_topic_anchors(brief)
    query_text = anchors["query_text"]

    assert "基层减负" in query_text
    assert "形式主义" in query_text
    assert "造痕补痕" in query_text
    assert "容错纠错" in query_text
    assert query_text != "基层治理"
    assert "基层治理" not in query_text
    assert anchors["primary_theme"] == "基层减负与形式主义隐形变异"
    assert "基层治理" not in anchors["primary_theme"]

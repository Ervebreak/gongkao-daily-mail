from policy_coordinate_semantic_fit import should_display_policy_match


def test_policy_only_generic_grassroots_match_is_hidden():
    article_anchors = {
        "query_text": "基层减负 形式主义隐形变异 过度留痕 考核纠偏",
        "fine_grained_tags": ["基层减负", "形式主义隐形变异", "过度留痕", "考核纠偏"],
    }
    coordinate = {
        "source_type": "policy_only",
        "policy_quote": "将基层就业公共服务融入以党建引领基层治理范畴，完善服务机制。",
    }

    assert should_display_policy_match(article_anchors, coordinate) is False


def test_policy_match_with_formalism_and_burden_reduction_is_displayed():
    article_anchors = {
        "query_text": "基层减负 形式主义隐形变异 过度留痕 考核纠偏",
        "fine_grained_tags": ["基层减负", "形式主义隐形变异", "过度留痕", "考核纠偏"],
    }
    coordinate = {
        "source_type": "policy_only",
        "policy_quote": "持续深化拓展整治形式主义为基层减负工作，让广大基层干部有更多精力抓落实。",
    }

    assert should_display_policy_match(article_anchors, coordinate) is True

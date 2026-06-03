from policy_coordinate_matcher import normalize_article_input, policy_topic_route_keywords
from policy_coordinate_quality import evaluate_policy_coordinate_quality


def test_food_safety_topic_route_keywords_prioritize_platform_regulation():
    routed = policy_topic_route_keywords("幽灵外卖", "食品安全 证照套牌 平台审核")
    assert "食品安全" in routed
    assert "网络餐饮服务" in routed
    assert "平台主体责任" in routed

    query = normalize_article_input(
        article_title="幽灵外卖乱象",
        article_summary="围绕食品安全、证照套牌、平台审核问题展开",
        main_theme="食品安全",
    )
    assert "食品安全" in query["topic_route_keywords"]
    assert "网络餐饮服务" in query["topic_route_keywords"]
    assert "平台主体责任" in query["topic_route_keywords"]
    assert "基层就业公共服务" not in query["topic_route_keywords"]
    assert "党建引领基层治理" not in query["topic_route_keywords"]


def test_policy_coordinate_quality_marks_weak_match_as_skipped():
    brief = {
        "_policy_coordinate_disabled_reason": "weak_match: policy_only policy_match_score=49.0 below backend threshold 65.",
        "policy_coordinate": {},
    }
    quality = evaluate_policy_coordinate_quality(brief)
    codes = {item["code"] for item in quality["issues"]}
    assert quality["ok"] is False
    assert quality["status"] == "skipped"
    assert "policy_coordinate_weak_match" in codes

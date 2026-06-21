from __future__ import annotations

from pre_send_cleanliness import pre_send_cleanliness_guard


def _payload() -> dict:
    return {
        "brief": {
            "daily_question": {
                "question": "某地老旧小区改造推进迟缓，群众多次投诉施工扰民、沟通不畅，请提出对策。",
                "candidate_answer": "先梳理问题，再分类处置，最后闭环反馈。",
                "thirty_second_answer": "先梳理问题，再分类处置，最后闭环反馈。",
                "output_sentence_template": "关键是把群众诉求转化为可执行的整改闭环。",
            }
        }
    }


def test_send_time_guard_does_not_block_daily_question_structure() -> None:
    _fixed, report = pre_send_cleanliness_guard(_payload(), enforce_daily_question_structure=False)

    codes = {str(issue.get("code") or "") for issue in report["issues"]}
    assert "daily_question_missing_identity" not in codes
    assert "daily_question_missing_scene" not in codes
    assert "daily_question_missing_conflict" not in codes
    assert "daily_question_missing_task" not in codes
    assert report["unresolved_issues"] == []


def test_candidate_time_guard_still_blocks_daily_question_structure() -> None:
    _fixed, report = pre_send_cleanliness_guard(_payload(), enforce_daily_question_structure=True)

    codes = {str(issue.get("code") or "") for issue in report["unresolved_issues"]}
    assert "daily_question_missing_identity" in codes

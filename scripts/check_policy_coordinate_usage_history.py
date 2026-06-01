from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from policy_coordinate_matcher import match_policy_coordinate_candidates
from policy_coordinate_usage_history import (
    append_policy_coordinate_usage,
    load_policy_coordinate_usage_history,
    recent_policy_coordinate_usage,
)


def main() -> None:
    temp_path = ROOT / "data" / "policy_coordinate_usage_history_check.jsonl"
    if temp_path.exists():
        temp_path.unlink()

    missing_rows, missing_meta = load_policy_coordinate_usage_history(temp_path)
    print(json.dumps({
        "missing_count": len(missing_rows),
        "missing_warning": missing_meta.get("usage_history_warning"),
    }, ensure_ascii=False))

    append_result = append_policy_coordinate_usage(
        {
            "date": "2026-05-31",
            "theme": "基层治理",
            "matched_policy_id": "POLICY_0001",
            "matched_qiushi_quote_id": "QIUSHI_0001",
            "matched_qiushi_article_id": "ARTICLE_0001",
            "matched_framework_id": "FRAMEWORK_0001",
            "policy_quote": "健全共建共治共享的社会治理制度，提升社会治理效能。",
            "authoritative_quote": "走好新时代党的群众路线。",
        },
        temp_path,
    )
    print(json.dumps({
        "append_ok": append_result.get("usage_history_write_ok"),
        "appended": append_result.get("usage_history_appended"),
        "skip_reason": append_result.get("usage_history_skip_reason"),
        "warning": append_result.get("usage_history_warning"),
    }, ensure_ascii=False))

    temp_path.write_text(
        temp_path.read_text(encoding="utf-8") + "not-json\n",
        encoding="utf-8",
    )
    rows, meta = load_policy_coordinate_usage_history(temp_path)
    recent_rows = recent_policy_coordinate_usage(rows, days=14)
    print(json.dumps({
        "loaded_count": len(rows),
        "bad_lines": meta.get("usage_history_bad_lines"),
        "recent_count": len(recent_rows),
    }, ensure_ascii=False))

    match = match_policy_coordinate_candidates(
        article_title="把新就业群体纳入基层治理体系",
        article_summary="文章聚焦基层治理、社区参与和新就业群体融入。",
        main_theme="基层治理",
        sub_themes=["共建共治共享", "社区治理", "新就业群体"],
        keywords=["基层治理", "新就业群体", "社区治理"],
        exam_scenarios=["基层治理", "社区治理", "面试综合分析"],
        recent_usage=recent_rows,
    ).get("matched_policy_coordinate_candidates", {})
    debug_scores = match.get("debug_scores") if isinstance(match.get("debug_scores"), dict) else {}
    print(json.dumps({
        "best_policy_id": (match.get("best_policy") or {}).get("policy_id"),
        "best_qiushi_quote_id": (match.get("best_qiushi_quote") or {}).get("quote_id"),
        "best_framework_id": (match.get("best_framework") or {}).get("framework_id"),
        "usage_history_debug": debug_scores.get("usage_history"),
    }, ensure_ascii=False))
    if temp_path.exists():
        temp_path.unlink()


if __name__ == "__main__":
    main()

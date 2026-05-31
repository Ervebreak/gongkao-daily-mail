from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from policy_coordinate_matcher import match_policy_coordinate_candidates  # noqa: E402


def main() -> int:
    result = match_policy_coordinate_candidates(
        article_title="小哥议事厅让新就业群体参与基层治理",
        article_summary="通过议事平台畅通外卖骑手等新就业群体诉求表达，推动社区治理从单向管理转向多元参与。",
        main_theme="基层治理",
        sub_themes=["共建共治共享", "社区治理", "新就业群体"],
        keywords=["小哥议事厅", "外卖骑手", "诉求表达", "基层治理", "多元参与"],
        exam_scenarios=["基层治理", "新就业群体服务", "城市精细化治理"],
    )["matched_policy_coordinate_candidates"]

    print(
        json.dumps(
            {
                "best_policy": _brief(result.get("best_policy"), "policy_id", "policy_quote"),
                "best_qiushi_quote": _brief(result.get("best_qiushi_quote"), "quote_id", "quote_text"),
                "matched_chunks": len(result.get("matched_chunks") or []),
                "best_framework": _brief(result.get("best_framework"), "framework_id", "framework_name"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _brief(item: dict | None, id_field: str, text_field: str) -> dict | None:
    if not item:
        return None
    return {
        "id": item.get(id_field),
        "score": item.get("_match_score"),
        "source": item.get("_match_source"),
        "text": str(item.get(text_field) or "")[:80],
    }


if __name__ == "__main__":
    raise SystemExit(main())

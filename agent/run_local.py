"""本地运行入口：python -m agent.run_local --date 2026-09-16 [--test]

用法：
  python -m agent.run_local --date 2026-09-16 --test
    （test 模式：TEST_LLM_MODEL=mock 时用确定性 Planner，不调用模型）
  python -m agent.run_local --date 2026-09-16
    （生产模式：需要 DASHSCOPE_API_KEY 等环境变量）

输出：状态机推进结果；候选通过门禁后进入 WAITING_FOR_APPROVAL，
并发送预览邮件到 SMTP_USER。
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="公考晨读 Agent 本地运行入口")
    parser.add_argument("--date", required=True, help="投递日期 YYYY-MM-DD")
    parser.add_argument("--test", action="store_true", help="test 模式（mock 模型则走确定性策略）")
    parser.add_argument("--confirm", action="store_true", help="模拟管理员点击确认链接（仅测试用）")
    args = parser.parse_args()

    from agent.orchestrator import run

    result = run(args.date, test_mode=args.test)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.confirm and result.get("status") == "waiting_for_approval":
        from agent.confirm import handle_confirm

        state_path = None
        from agent.state import load_run

        state = load_run(args.date)
        page = handle_confirm(
            {
                "path": "/agent-confirm",
                "query": {
                    "date": args.date,
                    "action": "approve",
                    "token": state.confirm_token if state else "",
                },
            }
        )
        print("=== confirm result ===")
        print(json.dumps(page, ensure_ascii=False, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

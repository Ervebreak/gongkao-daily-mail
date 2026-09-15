"""Agent Orchestrator 集成测试（确定性 Planner + mock 依赖）。

测的是「编排正确性」：状态机推进顺序、工具调用序列、人工确认闸门、
幂等与阻断路径。质检内部逻辑由项目既有测试覆盖，不在此重复。
"""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.orchestrator import DeterministicPlanner, run
from agent.state import (
    STATE_BLOCKED,
    STATE_SENT,
    STATE_WAITING_FOR_APPROVAL,
    load_run,
    save_run,
)


def _mock_articles():
    from article_filter import Article

    return [
        Article(
            title=f"测试文章{i}",
            url=f"https://example.com/{i}",
            source="人民日报",
            column="要闻",
            date=dt.date(2026, 9, 15),
            body=["这是测试正文，围绕乡村振兴与基层治理展开，适合申论备考。"] * 5,
            themes=["乡村振兴"],
            score=80 + i,
        )
        for i in range(5)
    ]


def _fake_preview(delivery_date):
    """与真实 send_preview_email 一致：更新 state.preview_sent / confirm_token。"""
    import os

    from agent.state import load_run, save_run

    state = load_run(delivery_date)
    if state is not None:
        state.preview_sent = True
        state.log_event("preview_email_sent", to="admin@example.com")
        if os.environ.get("AGENT_CONFIRM_SECRET"):
            from agent.confirm import build_confirm_token

            state.confirm_token = build_confirm_token(delivery_date, "approve")
        else:
            state.confirm_token = "mock-token"
        save_run(state)
    return {
        "preview_sent": True,
        "to": "admin@example.com",
        "approve_url": f"https://fc.example.com/agent-confirm?date={delivery_date}&action=approve&token=t",
    }


def _patch_pipeline(gate_overall: str = "ok", p0_count: int = 0):
    """返回一个已 enter 所有 mock.patch 的 ExitStack（可作 with 上下文）。"""
    from contextlib import ExitStack

    stack = ExitStack()
    for patcher in [
        mock.patch(
            "fetch_articles.get_candidate_articles_with_stats",
            lambda: (_mock_articles(), {"source_fetch_status": {}, "count": 5}),
        ),
        mock.patch(
            "llm_client.generate_brief",
            lambda articles, today, test_mode=False, selection_context=None: {
                "email_subject": f"测试晨读 {today}",
                "featured_article": {
                    "title": "主线测试文章",
                    "url": "https://example.com/featured",
                    "source": "人民日报",
                    "theme": "乡村振兴",
                },
            },
        ),
        mock.patch(
            "llm_client.rewrite_failed_modules_once",
            lambda brief, articles, question_quality=None, framework_quality=None, takeaway_quality=None, quick_reads_quality=None, test_mode=False: {
                "brief": brief,
                "rewritten_modules": [],
                "details": {},
            },
        ),
        mock.patch("email_renderer.render_email_html", lambda brief: "<html><body>测试渲染</body></html>"),
        mock.patch("email_renderer.render_plain_text", lambda brief: "测试渲染纯文本"),
        mock.patch(
            "quality_gate.evaluate_all_quality",
            lambda brief, plain_text, html_body, test_invocation=False, selection_quality=None, cleanliness_quality=None, latest_json=None: {
                "selection": {"ok": True},
            },
        ),
        mock.patch(
            "quality_gate.build_gate_from_quality_map",
            lambda quality, plain_text="", html_body="": {
                "overall": gate_overall,
                "p0_count": p0_count,
                "p0_issues": (
                    [{"module": "selection", "severity": "P0", "reason": "门禁失败"}]
                    if p0_count
                    else []
                ),
            },
        ),
        mock.patch("agent.confirm.send_preview_email", _fake_preview),
    ]:
        stack.enter_context(patcher)
    return stack


class AgentRunTempDirMixin(unittest.TestCase):
    """把 agent 运行目录隔离到临时目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        import agent.state as state_module

        self._original_run_dir = state_module.default_run_dir
        state_module.default_run_dir = lambda: self._tmp_path

    def tearDown(self):
        import agent.state as state_module

        state_module.default_run_dir = self._original_run_dir
        self._tmp.cleanup()


class TestOrchestratorPipeline(AgentRunTempDirMixin):
    def test_full_pipeline_reaches_waiting_for_approval(self):
        with _patch_pipeline():
            result = run("2026-09-16", test_mode=True, planner=DeterministicPlanner())

        self.assertEqual(result["status"], "waiting_for_approval")
        self.assertEqual(result["state"], STATE_WAITING_FOR_APPROVAL)
        state = load_run("2026-09-16")
        self.assertIsNotNone(state)
        self.assertTrue(state.candidate_saved)
        self.assertTrue(state.preview_sent)
        self.assertEqual(state.selected_article_ids, [0, 1, 2])
        self.assertEqual(state.model_calls, 2)  # 选文 1 次 + 质检放行 1 次
        events = [h.get("event") for h in state.history]
        self.assertIn("articles_selected", events)
        self.assertIn("candidate_saved", events)
        self.assertIn("preview_email_sent", events)

    def test_terminal_state_is_idempotent(self):
        with _patch_pipeline():
            first = run("2026-09-17", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(first["status"], "waiting_for_approval")

            state = load_run("2026-09-17")
            state.transition("PUBLISHED", note="approved")
            state.transition("SENT", note="sent")
            save_run(state)

            second = run("2026-09-17", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(second["status"], "already_terminal")
            self.assertEqual(second["state"], STATE_SENT)

    def test_p0_gate_failure_blocks_after_repair_rounds(self):
        with _patch_pipeline(gate_overall="fail", p0_count=1):
            result = run("2026-09-18", test_mode=True, planner=DeterministicPlanner(auto_pass=True))

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["state"], STATE_BLOCKED)
        state = load_run("2026-09-18")
        self.assertEqual(state.repair_round, 2)
        self.assertFalse(state.candidate_saved)

    def test_waiting_for_approval_does_not_rerun(self):
        with _patch_pipeline():
            first = run("2026-09-19", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(first["status"], "waiting_for_approval")
            second = run("2026-09-19", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(second["status"], "waiting_for_approval")


class TestConfirmFlow(AgentRunTempDirMixin):
    def test_confirm_approve_marks_sent(self):
        with _patch_pipeline(), mock.patch.dict(
            "os.environ", {"AGENT_CONFIRM_SECRET": "test-secret"}, clear=False
        ), mock.patch("main.send_saved_candidate", lambda event: {"status": "ok", "delivery_date": "2026-09-20"}):
            result = run("2026-09-20", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(result["status"], "waiting_for_approval")

            from agent.confirm import handle_confirm

            state = load_run("2026-09-20")
            page = handle_confirm(
                {
                    "path": "/agent-confirm",
                    "query": {
                        "date": "2026-09-20",
                        "action": "approve",
                        "token": state.confirm_token,
                    },
                }
            )
        self.assertEqual(page["statusCode"], 200)
        self.assertIn("已确认发送", page["body"])
        final = load_run("2026-09-20")
        self.assertEqual(final.state, STATE_SENT)
        self.assertTrue(final.sent)

    def test_confirm_bad_token_rejected(self):
        with _patch_pipeline(), mock.patch.dict(
            "os.environ", {"AGENT_CONFIRM_SECRET": "test-secret"}, clear=False
        ):
            result = run("2026-09-21", test_mode=True, planner=DeterministicPlanner())
            self.assertEqual(result["status"], "waiting_for_approval")

            from agent.confirm import handle_confirm

            page = handle_confirm(
                {
                    "path": "/agent-confirm",
                    "query": {"date": "2026-09-21", "action": "approve", "token": "forged-token"},
                }
            )
        self.assertIn("校验失败", page["body"])
        self.assertEqual(load_run("2026-09-21").state, STATE_WAITING_FOR_APPROVAL)

    def test_confirm_reject_marks_blocked(self):
        with _patch_pipeline(), mock.patch.dict(
            "os.environ", {"AGENT_CONFIRM_SECRET": "test-secret"}, clear=False
        ):
            run("2026-09-22", test_mode=True, planner=DeterministicPlanner())

            from agent.confirm import build_confirm_token, handle_confirm

            page = handle_confirm(
                {
                    "path": "/agent-confirm",
                    "query": {
                        "date": "2026-09-22",
                        "action": "reject",
                        "token": build_confirm_token("2026-09-22", "reject"),
                    },
                }
            )
        self.assertIn("已拒绝", page["body"])
        self.assertEqual(load_run("2026-09-22").state, STATE_BLOCKED)


if __name__ == "__main__":
    unittest.main()

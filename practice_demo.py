from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlsplit

from practice_links import (
    PracticeLinkError,
    PracticeQuotaError,
    create_candidate_token,
    question_version,
    verify_token as verify_signed_token,
)


DEFAULT_MAX_REVIEWS = 2
DEFAULT_LINK_DAYS = 7
MAX_POINT_LENGTH = 500
MAX_REQUEST_BYTES = 16_384
Coach = Callable[[list[str], dict[str, Any]], dict[str, Any]]


class PracticeDemoError(ValueError):
    pass


def load_practice_candidate(path: Path) -> dict[str, Any]:
    try:
        candidate = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PracticeDemoError(f"无法读取候选件：{exc}") from exc
    if not isinstance(candidate, dict):
        raise PracticeDemoError("候选件根节点必须是对象。")
    gate = candidate.get("quality_gate") if isinstance(candidate.get("quality_gate"), dict) else {}
    if gate.get("overall") != "ok":
        raise PracticeDemoError("候选件尚未通过质量门禁，不能用于训练。")
    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    if not str(question.get("question") or "").strip():
        raise PracticeDemoError("候选件缺少今日一题。")
    return candidate


def create_token(*, uid: str, candidate: dict[str, Any], secret: bytes, expires_at: int) -> str:
    return create_candidate_token(
        uid=uid,
        candidate=candidate,
        secret=secret,
        expires_at=expires_at,
    )


def verify_token(token: str, *, candidate: dict[str, Any], secret: bytes, now: int | None = None) -> dict[str, Any]:
    try:
        return verify_signed_token(
            token,
            secret=secret,
            expected_date=str(candidate.get("delivery_date") or ""),
            expected_qid=question_version(candidate),
            now=now,
        )
    except PracticeLinkError as exc:
        raise PracticeDemoError(str(exc)) from exc


class AttemptStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    @staticmethod
    def _key(uid: str, qid: str) -> str:
        return hashlib.sha256(f"{uid}\0{qid}".encode("utf-8")).hexdigest()

    def attempts_for(self, payload: dict[str, Any], max_reviews: int | None = None) -> list[dict[str, Any]]:
        del max_reviews
        with self._lock:
            data = self._load()
            return list(data["attempts"].get(self._key(str(payload["uid"]), str(payload["qid"])), []))

    def save(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        points: list[str],
        feedback: dict[str, Any],
        max_reviews: int,
    ) -> tuple[dict[str, Any], bool]:
        with self._lock:
            data = self._load()
            key = self._key(str(payload["uid"]), str(payload["qid"]))
            attempts = data["attempts"].setdefault(key, [])
            for attempt in attempts:
                if attempt.get("request_id") == request_id:
                    return dict(attempt), False
            if len(attempts) >= max_reviews:
                raise PracticeQuotaError(f"今天的 {max_reviews} 次评价机会已经用完。")
            attempt = {
                "attempt_no": len(attempts) + 1,
                "request_id": request_id,
                "delivery_date": payload["date"],
                "question_id": payload["qid"],
                "submitted_at": int(time.time()),
                "points": points,
                "feedback": feedback,
            }
            attempts.append(attempt)
            self._write(data)
            return dict(attempt), True

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "attempts": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PracticeDemoError(f"练习记录无法读取：{exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("attempts"), dict):
            raise PracticeDemoError("练习记录格式无效。")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)


def build_mock_feedback(points: list[str], question: dict[str, Any]) -> dict[str, Any]:
    detailed_count = sum(1 for point in points if len(point) >= 18)
    if detailed_count == 3:
        summary = "三个要点已经形成较完整的答题骨架，下一步重点是压缩句子并强化层次。"
    elif detailed_count:
        summary = "三个方向已经列出，其中部分要点还可以补充对象、动作和预期效果。"
    else:
        summary = "已经完成三点构思。当前表达偏简略，建议把每一点扩成“对象＋动作＋效果”。"
    point_feedback = []
    for index, point in enumerate(points, start=1):
        if len(point) < 12:
            advice = "方向已出现，但还需要补充由谁做、具体怎么做以及解决什么问题。"
        elif len(point) < 28:
            advice = "表达较清楚，可以再补一个执行抓手或结果落点，让对策更可操作。"
        else:
            advice = "信息较完整，建议压缩修饰语，把核心动作放在句首，提升口头表达力度。"
        point_feedback.append({"point": index, "text": point, "advice": advice})
    framework = question.get("answer_framework") or question.get("answer_frame") or []
    return {
        "mode": "mock",
        "summary": summary,
        "point_feedback": point_feedback,
        "reference_framework": [str(item).strip() for item in framework if str(item).strip()],
        "reference_answer": str(question.get("candidate_answer") or "").strip(),
    }


def _page(title: str, content: str) -> bytes:
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#182230; --muted:#667085; --blue:#175cd3; --paper:#fff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#f3f6fb; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ width:min(680px,calc(100% - 28px)); margin:28px auto; }}
    .card {{ background:var(--paper); border:1px solid #e4e7ec; border-radius:22px; padding:24px; box-shadow:0 12px 30px rgba(16,24,40,.07); }}
    .eyebrow {{ color:var(--blue); font-size:13px; font-weight:750; letter-spacing:.08em; }}
    h1 {{ margin:10px 0 8px; font-size:25px; line-height:1.4; }}
    .meta {{ color:var(--muted); font-size:14px; line-height:1.8; }}
    .question {{ margin:22px 0; padding:18px; border-radius:16px; background:#f8faff; border-left:4px solid #528bff; font-size:17px; line-height:1.9; }}
    .quota {{ display:inline-block; padding:7px 11px; border-radius:999px; color:#067647; background:#ecfdf3; font-size:13px; font-weight:700; }}
    .button {{ display:block; width:100%; margin-top:20px; padding:14px 18px; border:0; border-radius:13px; background:#175cd3; color:#fff; text-align:center; text-decoration:none; font-size:16px; font-weight:750; }}
    .hint {{ margin-top:18px; color:var(--muted); font-size:13px; line-height:1.8; }}
    label {{ display:block; margin:16px 0 7px; font-size:14px; font-weight:700; }}
    textarea {{ display:block; width:100%; min-height:88px; resize:vertical; padding:13px 14px; border:1px solid #d0d5dd; border-radius:12px; color:var(--ink); font:inherit; line-height:1.7; }}
    textarea:focus {{ outline:3px solid #dbeafe; border-color:#528bff; }}
    .error {{ margin:16px 0; padding:12px 14px; color:#b42318; background:#fef3f2; border-radius:12px; }}
    .result {{ margin-top:22px; padding-top:22px; border-top:1px solid #e4e7ec; }}
    .result h2 {{ margin:0 0 10px; font-size:19px; }}
    .result ul {{ padding-left:20px; line-height:1.85; }}
    .answer {{ padding:14px 16px; border-radius:12px; background:#f8fafc; line-height:1.85; white-space:pre-wrap; }}
  </style>
</head>
<body><main>{content}</main></body>
</html>"""
    return document.encode("utf-8")


@dataclass
class PracticeDemoApp:
    candidate: dict[str, Any]
    secret: bytes
    store: AttemptStore
    coach: Coach = build_mock_feedback
    coach_name: str = "mock"
    uid: str = "demo-user"
    max_reviews: int = DEFAULT_MAX_REVIEWS
    expires_at: int = 0

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = int(time.time()) + DEFAULT_LINK_DAYS * 86400

    @property
    def token(self) -> str:
        return create_token(uid=self.uid, candidate=self.candidate, secret=self.secret, expires_at=self.expires_at)

    @property
    def training_path(self) -> str:
        return f"/t/{quote(self.token, safe='')}"

    def render_email_preview(self) -> bytes:
        question = self._question()
        content = f"""
<section class="card">
  <div class="eyebrow">测试邮件预览 · 今日一题</div>
  <h1>今天这道题，你能在 30 秒内说出 3 个点吗？</h1>
  <div class="question">{html.escape(str(question.get('question') or ''))}</div>
  <div class="meta">这是本地验收页，不会发送正式邮件，也不会调用模型 API。</div>
  <a class="button" href="{html.escape(self.training_path, quote=True)}">开始训练 →</a>
</section>"""
        return _page("测试邮件预览", content)

    def render_training(self, token: str, *, error: str = "", values: list[str] | None = None) -> bytes:
        payload = verify_token(token, candidate=self.candidate, secret=self.secret)
        question = self._question()
        attempts = self.store.attempts_for(payload, max_reviews=self.max_reviews)
        remaining = max(0, self.max_reviews - len(attempts))
        values = values or ["", "", ""]
        fields = "".join(
            f'<label for="p{index}">第 {index} 点</label><textarea id="p{index}" name="p{index}" maxlength="{MAX_POINT_LENGTH}" required placeholder="写下一个完整要点">{html.escape(values[index - 1])}</textarea>'
            for index in range(1, 4)
        )
        error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
        history_html = self._render_attempts(attempts)
        disabled = " disabled" if remaining == 0 else ""
        button_text = "今日评价次数已用完" if remaining == 0 else "提交并查看点评"
        content = f"""
<section class="card">
  <div class="eyebrow">30 秒申论表达教练</div>
  <h1>{html.escape(str(question.get('question_type') or '今日一题'))}</h1>
  <div class="meta">训练日期：{html.escape(str(self.candidate.get('delivery_date') or ''))}</div>
  <div class="question">{html.escape(str(question.get('question') or ''))}</div>
  <span class="quota">今日剩余 {remaining} 次评价</span>
  <p class="hint">先写下你最想说的三个点。当前点评模式：{html.escape('真实 AI' if self.coach_name == 'api' else '规则化模拟')}。</p>
  {error_html}
  <form method="post" action="{html.escape('/t/' + quote(token, safe=''), quote=True)}">
    <input type="hidden" name="request_id" value="{secrets.token_urlsafe(16)}">
    {fields}
    <button class="button" type="submit"{disabled}>{button_text}</button>
  </form>
  {history_html}
</section>"""
        return _page("30 秒申论表达教练", content)

    def submit_training(self, token: str, body: bytes) -> tuple[int, bytes]:
        payload = verify_token(token, candidate=self.candidate, secret=self.secret)
        if len(body) > MAX_REQUEST_BYTES:
            return 413, self.render_training(token, error="提交内容过长，请精简后重试。")
        try:
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        except UnicodeDecodeError:
            return 400, self.render_training(token, error="提交内容编码无效。")
        values = [" ".join(form.get(f"p{index}", [""])[0].split()) for index in range(1, 4)]
        request_id = str(form.get("request_id", [""])[0]).strip()
        if not request_id or len(request_id) > 100:
            return 400, self.render_training(token, error="本次提交标识无效，请刷新页面后重试。", values=values)
        if any(not value for value in values):
            return 422, self.render_training(token, error="请完整填写三个要点。", values=values)
        if any(len(value) > MAX_POINT_LENGTH for value in values):
            return 422, self.render_training(token, error=f"每个要点不能超过 {MAX_POINT_LENGTH} 个字符。", values=values)
        try:
            existing_attempts = self.store.attempts_for(payload, max_reviews=self.max_reviews)
        except Exception:
            return 503, self.render_training(
                token,
                error="练习记录暂时无法读取，本次未扣次数。请稍后重试。",
                values=values,
            )
        if any(item.get("request_id") == request_id for item in existing_attempts):
            return 200, self.render_training(token)
        if len(existing_attempts) >= self.max_reviews:
            return 429, self.render_training(
                token,
                error=f"今天的 {self.max_reviews} 次评价机会已经用完。",
                values=values,
            )
        try:
            feedback = self.coach(values, self._question())
        except Exception:
            return 502, self.render_training(
                token,
                error="AI 点评暂时不可用，本次未扣次数。请稍后重试。",
                values=values,
            )
        feedback = dict(feedback)
        feedback["reference_framework"] = [
            str(item).strip()
            for item in (self._question().get("answer_framework") or self._question().get("answer_frame") or [])
            if str(item).strip()
        ]
        feedback["reference_answer"] = str(self._question().get("candidate_answer") or "").strip()
        try:
            self.store.save(
                payload,
                request_id=request_id,
                points=values,
                feedback=feedback,
                max_reviews=self.max_reviews,
            )
        except (PracticeDemoError, PracticeQuotaError) as exc:
            return 429, self.render_training(token, error=str(exc), values=values)
        except Exception:
            return 503, self.render_training(
                token,
                error="练习记录暂时无法保存，本次未扣次数。请稍后重试。",
                values=values,
            )
        return 200, self.render_training(token)

    def _render_attempts(self, attempts: list[dict[str, Any]]) -> str:
        if not attempts:
            return ""
        sections = []
        for attempt in reversed(attempts):
            feedback = attempt.get("feedback") if isinstance(attempt.get("feedback"), dict) else {}
            if feedback.get("mode") == "api":
                attempt_title = f"第 {int(attempt.get('attempt_no') or 0)} 次 AI 点评"
                score_names = {"relevance": "切题", "structure": "结构", "specificity": "具体", "expression": "表达"}
                scores = feedback.get("scores") if isinstance(feedback.get("scores"), dict) else {}
                score_text = "　".join(
                    f"{label} {int(scores.get(key) or 0)}/5" for key, label in score_names.items()
                )
                strengths = "".join(f"<li>{html.escape(str(item))}</li>" for item in feedback.get("strengths") or [])
                improvements = "".join(f"<li>{html.escape(str(item))}</li>" for item in feedback.get("improvements") or [])
                improved_points = "".join(f"<li>{html.escape(str(item))}</li>" for item in feedback.get("improved_points") or [])
                coach_details = f"""
  <div class="answer"><strong>{html.escape(score_text)}</strong></div>
  <h2>做得好的地方</h2><ul>{strengths}</ul>
  <h2>下一步怎么改</h2><ul>{improvements}</ul>
  <h2>优化后的三个点</h2><ul>{improved_points}</ul>
  <h2>30 秒示范表达</h2><div class="answer">{html.escape(str(feedback.get('thirty_second_answer') or ''))}</div>"""
                mode_note = "AI 已结合题目和参考答案进行语义点评。"
            else:
                attempt_title = f"第 {int(attempt.get('attempt_no') or 0)} 次模拟点评"
                point_rows = "".join(
                    f"<li><strong>第 {int(item.get('point') or 0)} 点：</strong>{html.escape(str(item.get('text') or ''))}<br><span class=\"meta\">{html.escape(str(item.get('advice') or ''))}</span></li>"
                    for item in feedback.get("point_feedback") or []
                    if isinstance(item, dict)
                )
                coach_details = f"<ul>{point_rows}</ul>"
                mode_note = "本阶段为规则化模拟点评；开启 API 模式后提供语义分析。"
            framework_rows = "".join(
                f"<li>{html.escape(str(item))}</li>" for item in feedback.get("reference_framework") or []
            )
            reference_answer = html.escape(str(feedback.get("reference_answer") or ""))
            sections.append(
                f"""<div class="result">
  <h2>{attempt_title}</h2>
  <div class="meta">{html.escape(mode_note)}</div>
  <p>{html.escape(str(feedback.get('summary') or ''))}</p>
  {coach_details}
  <h2>参考框架</h2><ul>{framework_rows}</ul>
  <h2>考生版参考答案</h2><div class="answer">{reference_answer}</div>
</div>"""
            )
        return "".join(sections)

    def render_error(self, message: str) -> bytes:
        return _page("链接不可用", f'<section class="card"><div class="eyebrow">链接不可用</div><h1>{html.escape(message)}</h1><p class="hint">请从最新收到的测试邮件重新进入。</p></section>')

    def handle(self, method: str, path: str, body: bytes = b"") -> tuple[int, str, bytes]:
        route = urlsplit(path).path
        if method == "GET" and route in {"/", "/demo-email"}:
            return 200, "text/html; charset=utf-8", self.render_email_preview()
        if route.startswith("/t/"):
            token = route[len("/t/") :]
            try:
                if method == "GET":
                    return 200, "text/html; charset=utf-8", self.render_training(token)
                if method == "POST":
                    status, response_body = self.submit_training(token, body)
                    return status, "text/html; charset=utf-8", response_body
                return 405, "text/plain; charset=utf-8", "Method Not Allowed".encode("utf-8")
            except PracticeDemoError as exc:
                return 403, "text/html; charset=utf-8", self.render_error(str(exc))
        if method != "GET":
            return 405, "text/plain; charset=utf-8", "Method Not Allowed".encode("utf-8")
        return 404, "text/plain; charset=utf-8", "Not Found".encode("utf-8")

    def _question(self) -> dict[str, Any]:
        brief = self.candidate.get("brief") if isinstance(self.candidate.get("brief"), dict) else {}
        return brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}


def make_handler(app: PracticeDemoApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status, content_type, body = app.handle("GET", self.path)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            try:
                content_length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                content_length = 0
            if content_length > MAX_REQUEST_BYTES:
                body = b""
                status, content_type, response_body = 413, "text/plain; charset=utf-8", "Payload Too Large".encode("utf-8")
            else:
                body = self.rfile.read(content_length)
                status, content_type, response_body = app.handle("POST", self.path, body)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="本地预览 30 秒申论表达教练的第一个可验收版本。")
    parser.add_argument("--candidate", type=Path, default=Path(__file__).with_name("candidates") / "latest.json")
    parser.add_argument("--uid", default="demo-user")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--attempts", type=Path, default=Path(__file__).with_name("output") / "practice_demo_attempts.json")
    parser.add_argument("--coach-mode", choices=("mock", "api"), default=os.environ.get("PRACTICE_COACH_MODE", "mock").strip().lower())
    parser.add_argument("--coach-model", default=os.environ.get("PRACTICE_COACH_MODEL", "").strip())
    parser.add_argument("--coach-timeout", type=int, default=int(os.environ.get("PRACTICE_COACH_TIMEOUT", "60")))
    args = parser.parse_args()

    candidate = load_practice_candidate(args.candidate)
    coach: Coach = build_mock_feedback
    if args.coach_mode == "api":
        from practice_coach import evaluate_with_api

        coach = lambda points, question: evaluate_with_api(
            points,
            question,
            model=args.coach_model,
            timeout=args.coach_timeout,
        )
    app = PracticeDemoApp(
        candidate=candidate,
        secret=secrets.token_bytes(32),
        store=AttemptStore(args.attempts),
        coach=coach,
        coach_name=args.coach_mode,
        uid=args.uid,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"测试邮件预览：http://{args.host}:{args.port}/demo-email", flush=True)
    print(f"专属训练页面：http://{args.host}:{args.port}{app.training_path}", flush=True)
    print(f"点评模式：{args.coach_mode}", flush=True)
    print("按 Ctrl+C 停止本地演示。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

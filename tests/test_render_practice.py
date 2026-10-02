from __future__ import annotations

from io import BytesIO

import render_practice


def _call(path: str, *, method: str = "GET", body: bytes = b"") -> tuple[str, dict[str, str], bytes]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    response_body = b"".join(render_practice.app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), response_body


def test_render_healthz_is_inline_json() -> None:
    status, headers, body = _call("/healthz")
    assert status == "200 OK"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Content-Disposition"] == "inline"
    assert headers["Content-Length"] == str(len(body))
    assert b'"service": "gongkao-practice"' in body


def test_render_forwards_training_routes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_handler(event, context):
        del context
        captured.update(event)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8", "Content-Disposition": "inline"},
            "body": "<html>ok</html>",
        }

    monkeypatch.setattr(render_practice, "handler", fake_handler)
    status, headers, body = _call("/t/signed-token", method="POST", body=b"p1=one")
    assert status == "200 OK"
    assert captured["httpMethod"] == "POST"
    assert captured["path"] == "/t/signed-token"
    assert captured["body"] == b"p1=one"
    assert headers["Content-Type"].startswith("text/html")
    assert body == b"<html>ok</html>"

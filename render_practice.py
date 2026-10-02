from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable, Iterable

from fc_practice import handler
from practice_demo import MAX_REQUEST_BYTES


StartResponse = Callable[[str, list[tuple[str, str]]], Any]


def _event_from_environ(environ: dict[str, Any]) -> dict[str, Any]:
    method = str(environ.get("REQUEST_METHOD") or "GET").upper()
    path = str(environ.get("PATH_INFO") or "/")
    try:
        content_length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length < 0 or content_length > MAX_REQUEST_BYTES:
        body = b"x" * (MAX_REQUEST_BYTES + 1)
    else:
        stream = environ.get("wsgi.input")
        body = stream.read(content_length) if stream is not None and content_length else b""
    return {
        "httpMethod": method,
        "path": path,
        "body": body,
        "isBase64Encoded": False,
    }


def app(environ: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
    result = handler(_event_from_environ(environ), None)
    status_code = int(result.get("statusCode") or 500)
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "Unknown"
    body = str(result.get("body") or "").encode("utf-8")
    headers = [
        (str(name), str(value))
        for name, value in (result.get("headers") or {}).items()
        if str(name).lower() not in {"content-length", "transfer-encoding"}
    ]
    headers.append(("Content-Length", str(len(body))))
    start_response(f"{status_code} {phrase}", headers)
    return [body]

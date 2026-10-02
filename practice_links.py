from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any


TOKEN_VERSION = 1
MARKER_PREFIX = "__PRACTICE_TOKEN__"
MARKER_SUFFIX = "__"
MARKER_RE = re.compile(re.escape(MARKER_PREFIX) + r"([A-Za-z0-9_-]+)" + re.escape(MARKER_SUFFIX))
HTML_CTA_RE = re.compile(r"<!-- PRACTICE_CTA_START -->.*?<!-- PRACTICE_CTA_END -->", re.S)
PLAIN_CTA_RE = re.compile(r"^开始训练：[^\r\n]*" + re.escape(MARKER_PREFIX) + r"[^\r\n]*$", re.M)


class PracticeLinkError(ValueError):
    pass


class PracticeQuotaError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def question_version_from_question(delivery_date: str, question: dict[str, Any]) -> str:
    stable = {
        "delivery_date": str(delivery_date or ""),
        "question_type": str(question.get("question_type") or ""),
        "question": str(question.get("question") or ""),
        "answer_framework": question.get("answer_framework") or question.get("answer_frame") or [],
        "candidate_answer": str(question.get("candidate_answer") or ""),
    }
    return hashlib.sha256(_canonical_json(stable)).hexdigest()[:16]


def question_version(candidate: dict[str, Any]) -> str:
    brief = candidate.get("brief") if isinstance(candidate.get("brief"), dict) else {}
    question = brief.get("daily_question") if isinstance(brief.get("daily_question"), dict) else {}
    delivery_date = str(candidate.get("delivery_date") or brief.get("date") or "")
    return question_version_from_question(delivery_date, question)


def create_token(*, uid: str, delivery_date: str, qid: str, secret: bytes, expires_at: int) -> str:
    payload = {
        "v": TOKEN_VERSION,
        "uid": uid,
        "date": delivery_date,
        "qid": qid,
        "exp": int(expires_at),
    }
    body = _b64encode(_canonical_json(payload))
    signature = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def create_candidate_token(*, uid: str, candidate: dict[str, Any], secret: bytes, expires_at: int) -> str:
    return create_token(
        uid=uid,
        delivery_date=str(candidate.get("delivery_date") or ""),
        qid=question_version(candidate),
        secret=secret,
        expires_at=expires_at,
    )


def decode_unverified_token(token: str) -> dict[str, Any]:
    if not token or len(token) > 2048:
        raise PracticeLinkError("专属链接格式无效。")
    try:
        body, _ = token.split(".", 1)
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except Exception as exc:
        raise PracticeLinkError("专属链接格式无效。") from exc
    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise PracticeLinkError("专属链接版本无效。")
    return payload


def verify_token(
    token: str,
    *,
    secret: bytes,
    expected_date: str = "",
    expected_qid: str = "",
    now: int | None = None,
) -> dict[str, Any]:
    try:
        body, supplied_signature = token.split(".", 1)
        expected_signature = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise PracticeLinkError("专属链接无效或已被修改。")
        payload = decode_unverified_token(token)
    except PracticeLinkError:
        raise
    except Exception as exc:
        raise PracticeLinkError("专属链接格式无效。") from exc
    if int(payload.get("exp") or 0) < int(now if now is not None else time.time()):
        raise PracticeLinkError("专属链接已经过期。")
    if expected_date and payload.get("date") != expected_date:
        raise PracticeLinkError("专属链接与当前候选件日期不一致。")
    if expected_qid and payload.get("qid") != expected_qid:
        raise PracticeLinkError("专属链接对应的题目版本已经变化。")
    if not str(payload.get("uid") or "").strip():
        raise PracticeLinkError("专属链接缺少用户标识。")
    return payload


def create_email_marker(delivery_date: str, question: dict[str, Any]) -> str:
    marker_payload = {
        "date": delivery_date,
        "qid": question_version_from_question(delivery_date, question),
    }
    return f"{MARKER_PREFIX}{_b64encode(_canonical_json(marker_payload))}{MARKER_SUFFIX}"


def replace_email_markers(
    text: str,
    *,
    uid: str,
    secret: bytes,
    expires_at: int,
) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            payload = json.loads(_b64decode(match.group(1)).decode("utf-8"))
            delivery_date = str(payload["date"])
            qid = str(payload["qid"])
        except Exception as exc:
            raise PracticeLinkError("邮件中的训练链接占位符无效。") from exc
        return create_token(
            uid=uid,
            delivery_date=delivery_date,
            qid=qid,
            secret=secret,
            expires_at=expires_at,
        )

    return MARKER_RE.sub(replace, text)


def has_email_marker(text: str) -> bool:
    return bool(MARKER_RE.search(text or ""))


def remove_practice_cta(text: str) -> str:
    value = HTML_CTA_RE.sub("", text or "")
    return PLAIN_CTA_RE.sub("", value)

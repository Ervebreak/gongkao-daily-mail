from __future__ import annotations

import hashlib
import hmac
import base64
import email.utils
import json
import os
import time
from typing import Any

import requests

from history import oss_headers, oss_url
from practice_links import PracticeQuotaError


class PracticeStorageError(RuntimeError):
    pass


def practice_oss_config(object_key: str = "") -> dict[str, str]:
    return {
        "endpoint": (os.environ.get("PRACTICE_OSS_ENDPOINT") or os.environ.get("OSS_ENDPOINT", "")).strip().rstrip("/"),
        "bucket": (os.environ.get("PRACTICE_OSS_BUCKET") or os.environ.get("OSS_BUCKET", "")).strip(),
        "access_key_id": (os.environ.get("PRACTICE_OSS_ACCESS_KEY_ID") or os.environ.get("OSS_ACCESS_KEY_ID", "")).strip(),
        "access_key_secret": (os.environ.get("PRACTICE_OSS_ACCESS_KEY_SECRET") or os.environ.get("OSS_ACCESS_KEY_SECRET", "")).strip(),
        "object_key": object_key.strip().lstrip("/"),
    }


def practice_oss_ready() -> bool:
    cfg = practice_oss_config("health-check")
    return all(cfg.values())


def practice_oss_put_headers(cfg: dict[str, str], content_type: str) -> dict[str, str]:
    date = email.utils.formatdate(usegmt=True)
    canonical_oss_headers = "x-oss-forbid-overwrite:true\n"
    resource = f"/{cfg['bucket']}/{cfg['object_key']}"
    string_to_sign = f"PUT\n\n{content_type}\n{date}\n{canonical_oss_headers}{resource}"
    signature = hmac.new(
        cfg["access_key_secret"].encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    authorization = base64.b64encode(signature).decode("ascii")
    return {
        "Date": date,
        "Authorization": f"OSS {cfg['access_key_id']}:{authorization}",
        "Content-Type": content_type,
        "x-oss-forbid-overwrite": "true",
    }


class OssAttemptStore:
    def __init__(self, *, prefix: str = "", timeout: int = 15):
        self.prefix = (prefix or os.environ.get("PRACTICE_OSS_PREFIX", "gongkao-morning-mailer/practice")).strip().strip("/")
        self.timeout = timeout
        if not practice_oss_ready():
            raise PracticeStorageError("Practice OSS configuration is incomplete.")

    @staticmethod
    def _user_key(uid: str) -> str:
        return hashlib.sha256(uid.encode("utf-8")).hexdigest()

    def _object_key(self, payload: dict[str, Any], slot: int) -> str:
        delivery_date = str(payload.get("date") or "")
        qid = str(payload.get("qid") or "")
        uid = str(payload.get("uid") or "")
        if not delivery_date or not qid or not uid or "/" in delivery_date or "/" in qid:
            raise PracticeStorageError("Practice storage key is invalid.")
        return f"{self.prefix}/attempts/{delivery_date}/{qid}/{self._user_key(uid)}/slot-{slot}.json"

    def _get(self, object_key: str) -> dict[str, Any] | None:
        cfg = practice_oss_config(object_key)
        response = requests.get(oss_url(cfg), headers=oss_headers("GET", cfg), timeout=self.timeout)
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            value = response.json()
        except Exception as exc:
            raise PracticeStorageError("Practice attempt could not be read from OSS.") from exc
        if not isinstance(value, dict):
            raise PracticeStorageError("Practice attempt stored in OSS is invalid.")
        return value

    def attempts_for(self, payload: dict[str, Any], max_reviews: int = 2) -> list[dict[str, Any]]:
        attempts = []
        for slot in range(1, max_reviews + 1):
            attempt = self._get(self._object_key(payload, slot))
            if attempt is not None:
                attempts.append(attempt)
        return sorted(attempts, key=lambda item: int(item.get("attempt_no") or 0))

    def _create(self, object_key: str, attempt: dict[str, Any]) -> bool:
        cfg = practice_oss_config(object_key)
        content_type = "application/json; charset=utf-8"
        headers = practice_oss_put_headers(cfg, content_type)
        response = requests.put(
            oss_url(cfg),
            headers=headers,
            data=json.dumps(attempt, ensure_ascii=False, indent=2).encode("utf-8"),
            timeout=self.timeout,
        )
        if response.status_code == 409:
            return False
        try:
            response.raise_for_status()
        except Exception as exc:
            raise PracticeStorageError("Practice attempt could not be saved to OSS.") from exc
        return True

    def save(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        points: list[str],
        feedback: dict[str, Any],
        max_reviews: int,
    ) -> tuple[dict[str, Any], bool]:
        for existing in self.attempts_for(payload, max_reviews=max_reviews):
            if existing.get("request_id") == request_id:
                return dict(existing), False

        for slot in range(1, max_reviews + 1):
            object_key = self._object_key(payload, slot)
            if self._get(object_key) is not None:
                continue
            attempt = {
                "attempt_no": slot,
                "request_id": request_id,
                "delivery_date": payload["date"],
                "question_id": payload["qid"],
                "submitted_at": int(time.time()),
                "points": points,
                "feedback": feedback,
            }
            if self._create(object_key, attempt):
                return dict(attempt), True
            collided = self._get(object_key)
            if collided and collided.get("request_id") == request_id:
                return dict(collided), False

        raise PracticeQuotaError(f"今天的 {max_reviews} 次评价机会已经用完。")

from __future__ import annotations

import json

import pytest

import practice_store
from practice_links import PracticeQuotaError
from practice_store import OssAttemptStore


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("OSS_BUCKET", "practice-test")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "test-secret")


def _payload() -> dict:
    return {"uid": "u_123", "date": "2026-10-02", "qid": "abcdef0123456789"}


def test_oss_slots_are_create_only_idempotent_and_anonymous(monkeypatch) -> None:
    _configure(monkeypatch)
    objects: dict[str, dict] = {}

    def fake_get(url, *, headers, timeout):
        del headers, timeout
        return _Response(200, objects[url]) if url in objects else _Response(404)

    def fake_put(url, *, headers, data, timeout):
        del timeout
        assert headers["x-oss-forbid-overwrite"] == "true"
        assert headers["Authorization"].startswith("OSS test-id:")
        if url in objects:
            return _Response(409)
        objects[url] = json.loads(data.decode("utf-8"))
        return _Response(200)

    monkeypatch.setattr(practice_store.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(practice_store.requests, "put", fake_put, raising=False)
    store = OssAttemptStore(timeout=1)
    attempt, created = store.save(
        _payload(),
        request_id="request-1",
        points=["一", "二", "三"],
        feedback={"summary": "ok"},
        max_reviews=2,
    )
    duplicate, duplicate_created = store.save(
        _payload(),
        request_id="request-1",
        points=["一", "二", "三"],
        feedback={"summary": "ok"},
        max_reviews=2,
    )
    assert created is True
    assert duplicate_created is False
    assert attempt == duplicate
    assert len(objects) == 1
    object_url = next(iter(objects))
    assert "u_123" not in object_url
    assert "uid" not in objects[object_url]


def test_quota_uses_two_distinct_slots(monkeypatch) -> None:
    _configure(monkeypatch)
    objects: dict[str, dict] = {}

    def fake_get(url, *, headers, timeout):
        del headers, timeout
        return _Response(200, objects[url]) if url in objects else _Response(404)

    def fake_put(url, *, headers, data, timeout):
        del headers, timeout
        if url in objects:
            return _Response(409)
        objects[url] = json.loads(data.decode("utf-8"))
        return _Response(200)

    monkeypatch.setattr(practice_store.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(practice_store.requests, "put", fake_put, raising=False)
    store = OssAttemptStore(timeout=1)
    for request_id in ("request-1", "request-2"):
        store.save(
            _payload(),
            request_id=request_id,
            points=["一", "二", "三"],
            feedback={"summary": "ok"},
            max_reviews=2,
        )
    with pytest.raises(PracticeQuotaError, match="2 次"):
        store.save(
            _payload(),
            request_id="request-3",
            points=["一", "二", "三"],
            feedback={"summary": "ok"},
            max_reviews=2,
        )
    assert len(objects) == 2

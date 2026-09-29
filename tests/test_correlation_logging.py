from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import structlog

from app import logging_config
from app.logging_config import scrub_event
from app.main import app
from app.pii import hash_user_id

REQUEST_ID_RE = re.compile(r"^req-[0-9a-f]{8}$")


def _post_chats(requests: list[tuple[dict, dict]]) -> list[httpx.Response]:
    async def send() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return [
                await client.post("/chat", json=body, headers=headers)
                for body, headers in requests
            ]

    return asyncio.run(send())


def _body(user_id: str, session_id: str, feature: str = "qa", message: str = "Explain logs") -> dict:
    return {"user_id": user_id, "session_id": session_id, "feature": feature, "message": message}


def _read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_generates_and_returns_correlation_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    (response,) = _post_chats([(_body("u1", "s1"), {})])

    request_id = response.headers["x-request-id"]
    assert REQUEST_ID_RE.fullmatch(request_id)
    assert response.json()["correlation_id"] == request_id
    assert float(response.headers["x-response-time-ms"]) >= 0


def test_reuses_valid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    (response,) = _post_chats([(_body("u1", "s1"), {"x-request-id": "req-1a2b3c4d"})])

    assert response.headers["x-request-id"] == "req-1a2b3c4d"
    assert response.json()["correlation_id"] == "req-1a2b3c4d"


def test_replaces_malformed_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    (response,) = _post_chats([(_body("u1", "s1"), {"x-request-id": "evil\" injected"})])

    request_id = response.headers["x-request-id"]
    assert REQUEST_ID_RE.fullmatch(request_id)
    assert "evil" not in request_id


def test_api_logs_are_enriched_and_do_not_leak_between_requests(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    monkeypatch.setenv("APP_ENV", "test")

    first, second = _post_chats(
        [
            (_body("user-a", "session-a", "qa"), {}),
            (_body("user-b", "session-b", "summary"), {}),
        ]
    )

    api_events = [e for e in _read_log(log_path) if e.get("service") == "api"]
    assert len(api_events) == 4
    expected = {
        first.headers["x-request-id"]: ("user-a", "session-a", "qa"),
        second.headers["x-request-id"]: ("user-b", "session-b", "summary"),
    }
    assert len(expected) == 2
    for event in api_events:
        user_id, session_id, feature = expected[event["correlation_id"]]
        assert event["user_id_hash"] == hash_user_id(user_id)
        assert event["session_id"] == session_id
        assert event["feature"] == feature
        assert event["model"]
        assert event["env"] == "test"
        assert "user_id" not in event


def test_raw_pii_never_reaches_log_file(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    message = (
        "Email student@vinuni.edu.vn, phone 090 123 4567, "
        "CCCD 001203004567, card 4111 1111 1111 1111"
    )

    _post_chats([(_body("u1", "s1", message=message), {})])

    raw = log_path.read_text(encoding="utf-8")
    for pii in ("student@vinuni.edu.vn", "090 123 4567", "001203004567", "4111 1111 1111 1111"):
        assert pii not in raw
    assert "REDACTED_EMAIL" in raw


def test_scrub_event_covers_nested_and_top_level_fields() -> None:
    event = {
        "ts": "2026-01-01T00:00:00Z",
        "event": "failed for student@vinuni.edu.vn",
        "correlation_id": "req-1a2b3c4d",
        "error_detail": "card 4111111111111111 declined",
        "payload": {"items": ["call 0987654321"], "nested": {"id": "001203004567"}},
    }

    out = scrub_event(None, "info", event)

    raw = json.dumps(out)
    for pii in ("student@vinuni.edu.vn", "4111111111111111", "0987654321", "001203004567"):
        assert pii not in raw
    assert out["correlation_id"] == "req-1a2b3c4d"


def test_scrub_runs_before_file_writer_and_renderer() -> None:
    processors = structlog.get_config()["processors"]
    scrub_index = processors.index(scrub_event)
    writer_index = next(
        i for i, p in enumerate(processors) if isinstance(p, logging_config.JsonlFileProcessor)
    )
    renderer_index = next(
        i for i, p in enumerate(processors) if isinstance(p, structlog.processors.JSONRenderer)
    )
    assert scrub_index < writer_index < renderer_index

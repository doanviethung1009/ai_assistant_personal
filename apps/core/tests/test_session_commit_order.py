"""Commit của SessionDep phải xong TRƯỚC khi response được gửi (không cần DB)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.deps import SessionDep
from app.db import session as session_module


class _FakeSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.events.append("commit")

    async def rollback(self) -> None:
        self.events.append("rollback")


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(session_module, "SessionFactory", lambda: _FakeSession(recorded))
    return recorded


def _app() -> FastAPI:
    app = FastAPI()

    @app.delete("/ok", status_code=204)
    async def ok(session: SessionDep) -> None:
        return None

    @app.get("/boom")
    async def boom(session: SessionDep) -> None:
        raise HTTPException(status_code=409, detail="x")

    return app


def _recording(app: FastAPI, events: list[str]):
    async def wrapper(scope, receive, send):
        async def spy(message):
            if message["type"] == "http.response.start":
                events.append("response_start")
            await send(message)

        await app(scope, receive, spy)

    return wrapper


async def test_commit_truoc_khi_gui_response(events: list[str]) -> None:
    transport = httpx.ASGITransport(app=_recording(_app(), events))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.delete("/ok")
    assert resp.status_code == 204
    assert events == ["commit", "response_start"]


async def test_loi_thi_rollback_khong_commit(events: list[str]) -> None:
    transport = httpx.ASGITransport(app=_recording(_app(), events))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/boom")
    assert resp.status_code == 409
    assert "commit" not in events
    assert "rollback" in events

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tender_tracker.config import load_settings
from tender_tracker.storage import GraphOneDriveStorage


@dataclass
class DummyTokenResponse:
    payload: dict[str, object]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class DummyGraphResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_graph_storage_refreshes_expiring_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS_TENANT_ID", "tenant")
    monkeypatch.setenv("MS_CLIENT_ID", "client")
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret")
    settings = load_settings("config/settings.yaml")
    storage = GraphOneDriveStorage(settings)
    issued = iter(
        [
            {"access_token": "first-token", "expires_in": 10},
            {"access_token": "second-token", "expires_in": 3600},
        ]
    )
    calls = {"count": 0}

    def fake_post(url: str, data: dict[str, str], timeout: int):
        calls["count"] += 1
        return DummyTokenResponse(next(issued))

    monkeypatch.setattr(storage._session, "post", fake_post)

    assert storage._token() == "first-token"
    assert storage._token() == "second-token"
    assert calls["count"] == 2


def test_graph_request_refreshes_after_401(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MS_TENANT_ID", "tenant")
    monkeypatch.setenv("MS_CLIENT_ID", "client")
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret")
    settings = load_settings("config/settings.yaml")
    storage = GraphOneDriveStorage(settings)
    calls: list[str] = []

    def fake_headers(*, force_refresh: bool = False) -> dict[str, str]:
        return {"Authorization": "Bearer refreshed" if force_refresh else "Bearer initial"}

    def fake_request(method: str, url: str, headers: dict[str, str], timeout: int, **kwargs):
        calls.append(headers["Authorization"])
        if len(calls) == 1:
            return DummyGraphResponse(401, "expired")
        return DummyGraphResponse(200, "ok")

    monkeypatch.setattr(storage, "_headers", fake_headers)
    monkeypatch.setattr(storage._session, "request", fake_request)

    response = storage._request("GET", "https://graph.microsoft.com/test")

    assert response.status_code == 200
    assert calls == ["Bearer initial", "Bearer refreshed"]

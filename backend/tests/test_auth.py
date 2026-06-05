from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


def _client():
    from common.auth import require_api_key

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected():
        return {"ok": True}

    return TestClient(app)


def test_auth_disabled_allows_request(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)
    resp = _client().get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_auth_enabled_rejects_missing_or_wrong_key(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_API_KEY", "secret-key", raising=False)
    client = _client()

    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"X-API-Key": "wrong"}).status_code == 401


def test_auth_enabled_accepts_bearer_or_header_key(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_API_KEY", "secret-key", raising=False)
    client = _client()

    assert client.get("/protected", headers={"Authorization": "Bearer secret-key"}).status_code == 200
    assert client.get("/protected", headers={"X-API-Key": "secret-key"}).status_code == 200


def test_auth_enabled_without_config_returns_503(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_API_KEY", "", raising=False)

    resp = _client().get("/protected", headers={"X-API-Key": "anything"})
    assert resp.status_code == 503

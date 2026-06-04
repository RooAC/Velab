from __future__ import annotations

import io


def _assert_structured_error(response, expected_code: str):
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == expected_code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    return body


def test_real_routes_use_structured_error_for_http_exceptions(client, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)

    docs_response = client.post(
        "/api/docs/upload",
        files={"file": ("firmware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert docs_response.status_code == 415
    _assert_structured_error(docs_response, "UNSUPPORTED_MEDIA_TYPE")

    session_response = client.get("/api/sessions/not-a-uuid")
    assert session_response.status_code == 400
    _assert_structured_error(session_response, "BAD_REQUEST")


def test_real_routes_use_structured_error_for_validation_errors(client, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", False, raising=False)

    response = client.get("/api/feedback?limit=0")

    assert response.status_code == 422
    body = _assert_structured_error(response, "VALIDATION_ERROR")
    assert isinstance(body["error"]["details"], list)

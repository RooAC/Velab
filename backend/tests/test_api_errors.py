from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from common.errors import register_error_handlers


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    def missing():
        raise HTTPException(status_code=404, detail="item not found")

    @app.get("/typed")
    def typed():
        raise HTTPException(
            status_code=409,
            detail={"code": "CASE_EXISTS", "message": "case already exists"},
        )

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"item_id": item_id}

    return TestClient(app)


def test_http_exception_uses_structured_error_shape():
    response = _client().get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "item not found",
        }
    }


def test_http_exception_can_override_error_code():
    response = _client().get("/typed")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "CASE_EXISTS",
            "message": "case already exists",
        }
    }


def test_validation_error_uses_structured_error_shape():
    response = _client().get("/items/not-an-int")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)

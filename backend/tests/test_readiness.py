from __future__ import annotations

from contextlib import contextmanager


class _FakeSession:
    def execute(self, statement):
        self.statement = statement


class _FakeTaskClient:
    async def get_queue_info(self) -> dict:
        return {
            "queue_length": 0,
            "redis_host": "localhost",
            "redis_port": 6379,
        }


def _patch_ready_dependencies(monkeypatch):
    import main
    import tasks.client as tasks_client

    @contextmanager
    def _session():
        yield _FakeSession()

    async def _get_task_client():
        return _FakeTaskClient()

    async def _gateway_ok():
        return {
            "status": "ok",
            "url": "http://127.0.0.1:4000/health",
            "status_code": 200,
        }

    monkeypatch.setattr(main.db_manager, "get_session", _session)
    monkeypatch.setattr(
        main.db_manager,
        "get_pool_status",
        lambda: {
            "size": 10,
            "checked_in": 9,
            "checked_out": 1,
            "overflow": 0,
            "total": 10,
        },
    )
    monkeypatch.setattr(tasks_client, "get_task_client", _get_task_client)
    monkeypatch.setattr(main, "_check_litellm_gateway", _gateway_ok)


def test_ready_returns_ready_when_all_dependencies_are_healthy(client, monkeypatch):
    _patch_ready_dependencies(monkeypatch)

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["redis_queue"]["status"] == "ok"
    assert payload["checks"]["log_pipeline"]["status"] == "ok"
    assert payload["checks"]["agents"]["status"] == "ok"
    assert payload["checks"]["llm_gateway"]["status"] == "ok"


def test_ready_returns_503_when_database_is_unavailable(client, monkeypatch):
    import main

    _patch_ready_dependencies(monkeypatch)

    def _raise_database_error():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main.db_manager, "get_session", _raise_database_error)

    response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"] == {
        "status": "failed",
        "error": "RuntimeError",
    }


def test_litellm_health_url_strips_openai_v1_path(monkeypatch):
    import main
    from config import settings

    monkeypatch.setattr(
        settings,
        "LITELLM_BASE_URL",
        "http://127.0.0.1:4000/v1",
        raising=False,
    )

    assert main._litellm_health_url() == "http://127.0.0.1:4000/health"

from __future__ import annotations

import json
from uuid import uuid4

import pytest


class _FakeRedis:
    def __init__(self):
        self.set_calls = []

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True


class _FakeCatalog:
    def __init__(self, bundle_id: str):
        self.bundle_id = bundle_id

    def get_bundle(self, bundle_id):
        assert str(bundle_id) == self.bundle_id
        return {"status": "done", "progress": 1.0}


class _FakePipeline:
    def __init__(self, bundle_id: str, run_error: Exception | None = None):
        self._catalog = _FakeCatalog(bundle_id)
        self.register_upload_called = False
        self.run_error = run_error

    def register_upload(self, *args, **kwargs):
        self.register_upload_called = True
        raise AssertionError("worker must not register upload records")

    def run(self, bundle_id, upload_path):
        assert str(bundle_id) == self._catalog.bundle_id
        if self.run_error is not None:
            raise self.run_error
        return {
            "total_files": 1,
            "dedup_skipped": 0,
            "per_controller": {"mpu": 1},
            "decode_counts": {},
            "prescan_counts": {},
            "alignment": {},
        }


@pytest.mark.asyncio
async def test_parse_bundle_task_uses_existing_bundle_id(monkeypatch, tmp_path):
    from tasks import worker

    bundle_id = str(uuid4())
    fake_pipeline = _FakePipeline(bundle_id)
    upload_path = tmp_path / "bundle.log"
    upload_path.write_text("boot\n", encoding="utf-8")

    monkeypatch.setattr(worker.PipelineSettings, "from_env", lambda: object())
    monkeypatch.setattr(worker, "build_pipeline", lambda settings: fake_pipeline)

    result = await worker.parse_bundle_task(
        {"job_id": "job-1", "redis": _FakeRedis()},
        bundle_id,
        str(upload_path),
        "bundle.log",
    )

    assert result["status"] == "completed"
    assert result["bundle_id"] == bundle_id
    assert fake_pipeline.register_upload_called is False


@pytest.mark.asyncio
async def test_parse_bundle_task_invalid_uuid_returns_failed_and_unlinks_upload(monkeypatch, tmp_path):
    from tasks import worker

    upload_path = tmp_path / "bundle.log"
    upload_path.write_text("boot\n", encoding="utf-8")
    redis = _FakeRedis()

    monkeypatch.setattr(worker.PipelineSettings, "from_env", lambda: object())
    monkeypatch.setattr(worker, "build_pipeline", lambda settings: _FakePipeline(str(uuid4())))

    result = await worker.parse_bundle_task(
        {"job_id": "job-1", "redis": redis},
        "not-a-uuid",
        str(upload_path),
        "bundle.log",
    )

    assert result["status"] == "failed"
    assert result["bundle_id"] == "not-a-uuid"
    assert "badly formed hexadecimal UUID" in result["error"]
    assert not upload_path.exists()
    failed_payload = json.loads(redis.set_calls[-1][0][1])
    assert failed_payload["stage"] == "failed"


@pytest.mark.asyncio
async def test_parse_bundle_task_pipeline_run_exception_sets_failed_progress(monkeypatch, tmp_path):
    from tasks import worker

    bundle_id = str(uuid4())
    upload_path = tmp_path / "bundle.log"
    upload_path.write_text("boot\n", encoding="utf-8")
    redis = _FakeRedis()
    fake_pipeline = _FakePipeline(bundle_id, run_error=RuntimeError("decode exploded"))

    monkeypatch.setattr(worker.PipelineSettings, "from_env", lambda: object())
    monkeypatch.setattr(worker, "build_pipeline", lambda settings: fake_pipeline)

    result = await worker.parse_bundle_task(
        {"job_id": "job-2", "redis": redis},
        bundle_id,
        str(upload_path),
        "bundle.log",
    )

    assert result == {
        "bundle_id": bundle_id,
        "status": "failed",
        "error": "decode exploded",
    }
    assert not upload_path.exists()
    failed_payload = json.loads(redis.set_calls[-1][0][1])
    assert failed_payload["percent"] == 100
    assert failed_payload["stage"] == "failed"

from __future__ import annotations

from uuid import uuid4

import pytest


class _FakeRedis:
    async def set(self, *args, **kwargs):
        return True


class _FakeCatalog:
    def __init__(self, bundle_id: str):
        self.bundle_id = bundle_id

    def get_bundle(self, bundle_id):
        assert str(bundle_id) == self.bundle_id
        return {"status": "done", "progress": 1.0}


class _FakePipeline:
    def __init__(self, bundle_id: str):
        self._catalog = _FakeCatalog(bundle_id)
        self.register_upload_called = False

    def register_upload(self, *args, **kwargs):
        self.register_upload_called = True
        raise AssertionError("worker must not register upload records")

    def run(self, bundle_id, upload_path):
        assert str(bundle_id) == self._catalog.bundle_id
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

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from arq.jobs import JobStatus

from tasks.client import TaskClient


class _FakeJobHandle:
    job_id = "job-123"


class _FakePool:
    def __init__(self):
        self.enqueued = []
        self.set_calls = []
        self.progress_raw = None

    async def enqueue_job(self, *args):
        self.enqueued.append(args)
        return _FakeJobHandle()

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True

    async def get(self, key):
        return self.progress_raw


class _FakeJob:
    status_value = JobStatus.queued
    info_value = SimpleNamespace(enqueue_time=datetime(2026, 1, 2, tzinfo=timezone.utc))
    result_info_value = None
    result_value = {"ok": True}

    def __init__(self, task_id, redis):
        self.task_id = task_id
        self.redis = redis

    async def status(self):
        return self.status_value

    async def info(self):
        return self.info_value

    async def result_info(self):
        return self.result_info_value

    async def result(self, timeout):  # noqa: ARG002
        return self.result_value


@pytest.mark.asyncio
async def test_submit_bundle_task_enqueues_existing_bundle_id_and_initial_progress():
    pool = _FakePool()
    client = TaskClient()
    client._pool = pool

    task_id = await client.submit_bundle_task(
        "bundle-1",
        "/tmp/upload.log",
        "upload.log",
    )

    assert task_id == "job-123"
    assert pool.enqueued == [
        ("parse_bundle_task", "bundle-1", "/tmp/upload.log", "upload.log")
    ]
    assert pool.set_calls
    args, kwargs = pool.set_calls[0]
    assert args[0] == "task_progress:job-123"
    assert json.loads(args[1]) == {
        "percent": 5,
        "stage": "queued",
        "message": "任务已入队，等待处理",
    }
    assert kwargs["ex"] == 3600


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arq_status,expected",
    [
        (JobStatus.queued, "pending"),
        (JobStatus.deferred, "pending"),
        (JobStatus.in_progress, "running"),
        (JobStatus.complete, "completed"),
        (JobStatus.not_found, "not_found"),
    ],
)
async def test_get_task_status_maps_arq_statuses(monkeypatch, arq_status, expected):
    import tasks.client as client_module

    pool = _FakePool()
    pool.progress_raw = b'{"percent":50,"stage":"decoding"}'
    fake_job = type(
        "JobForStatus",
        (_FakeJob,),
        {"status_value": arq_status},
    )
    monkeypatch.setattr(client_module, "Job", fake_job)

    client = TaskClient()
    client._pool = pool

    result = await client.get_task_status("job-1")

    assert result["status"] == expected
    assert result["progress"] == {"percent": 50, "stage": "decoding"}
    assert result["enqueue_time"] == "2026-01-02T00:00:00+00:00"


@pytest.mark.asyncio
async def test_get_task_status_complete_failed_sets_failed_and_error(monkeypatch):
    import tasks.client as client_module

    result_info = SimpleNamespace(
        start_time=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
        finish_time=datetime(2026, 1, 2, 2, tzinfo=timezone.utc),
        success=False,
        result=RuntimeError("boom"),
    )
    fake_job = type(
        "FailedJob",
        (_FakeJob,),
        {
            "status_value": JobStatus.complete,
            "result_info_value": result_info,
        },
    )
    monkeypatch.setattr(client_module, "Job", fake_job)

    client = TaskClient()
    client._pool = _FakePool()

    result = await client.get_task_status("job-1")

    assert result["status"] == "failed"
    assert result["error"] == "boom"
    assert result["start_time"] == "2026-01-02T01:00:00+00:00"
    assert result["finish_time"] == "2026-01-02T02:00:00+00:00"


@pytest.mark.asyncio
async def test_get_task_status_malformed_progress_is_ignored(monkeypatch):
    import tasks.client as client_module

    pool = _FakePool()
    pool.progress_raw = b"{not-json"
    monkeypatch.setattr(client_module, "Job", _FakeJob)

    client = TaskClient()
    client._pool = pool

    result = await client.get_task_status("job-1")

    assert result["status"] == "pending"
    assert "progress" not in result

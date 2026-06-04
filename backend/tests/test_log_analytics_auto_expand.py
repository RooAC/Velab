"""Tests for LogAnalyticsAgent auto-expand loop (R1 fix from 试用反馈).

R1 反馈：根因分析仅扫描了 2002 行就给结论，需要在关键词命中过少时扩窗重拉。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.log_analytics import LogAnalyticsAgent
from config import settings


def _bundle_status_ok() -> dict:
    return {
        "status": "done",
        "progress": 1.0,
        "valid_time_range_by_controller": {
            "iCGM": {"start": "2025-09-15T08:00:00Z", "end": "2025-09-15T10:00:00Z"},
        },
    }


def _make_client_with_responses(responses: list) -> AsyncMock:
    """生成一个上下文管理器形态的 AsyncClient mock，按 responses 顺序返回。"""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=responses)
    return client


@pytest.fixture
def agent() -> LogAnalyticsAgent:
    return LogAnalyticsAgent()


@pytest.mark.asyncio
async def test_no_expand_when_hits_above_threshold(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """命中数 >= 阈值时，只发一次 logs 请求，不扩窗。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 1000, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", True, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_EXPAND_THRESHOLD", 5, raising=False)

    # 构造 10 条命中关键词的行
    records = [
        {"ts": f"2025-09-15T09:00:{i:02d}Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC write timeout"}
        for i in range(10)
    ]
    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    log_resp = MagicMock(status_code=200, text="\n".join(json.dumps(r) for r in records))

    client = _make_client_with_responses([status_resp, log_resp])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        result = await agent._load_logs_from_bundle("bundle-x", ["eMMC"])

    # 一次 status + 一次 logs = 2 次 GET
    assert client.get.await_count == 2
    assert "eMMC write timeout" in result
    # header 不应包含 "expanded" 字样
    assert "expanded" not in result


@pytest.mark.asyncio
async def test_expand_when_hits_below_threshold(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """命中数 < 阈值且 limit 未达上限时，扩窗（limit 翻倍）重拉一次。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 400, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", True, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_EXPAND_THRESHOLD", 50, raising=False)

    # 第一次返回满 100 条但只有 2 条命中（远低于 50），说明可能被 limit 截断，应该扩窗。
    first_records = [
        {"ts": "2025-09-15T09:00:00Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC write timeout"},
        {"ts": "2025-09-15T09:00:01Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC retry"},
    ] + [
        {"ts": f"2025-09-15T09:00:{i:02d}Z", "controller": "MPU",
         "level": "INFO", "msg": "download complete"}
        for i in range(2, 100)
    ]
    # 扩窗后返回 60 条命中（超过阈值，停止）
    second_records = [
        {"ts": f"2025-09-15T09:01:{i:02d}Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC error"}
        for i in range(60)
    ]

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    log_resp_1 = MagicMock(status_code=200, text="\n".join(json.dumps(r) for r in first_records))
    log_resp_2 = MagicMock(status_code=200, text="\n".join(json.dumps(r) for r in second_records))

    client = _make_client_with_responses([status_resp, log_resp_1, log_resp_2])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        result = await agent._load_logs_from_bundle("bundle-x", ["eMMC"])

    # 一次 status + 两次 logs = 3 次 GET（扩窗发生）
    assert client.get.await_count == 3
    # header 应当反映扩窗事实
    assert "expanded" in result
    # 第二次 GET 的 params.limit 应当翻倍为 200
    second_call_kwargs = client.get.await_args_list[2].kwargs
    assert second_call_kwargs["params"]["limit"] == 200


@pytest.mark.asyncio
async def test_expand_stops_at_max_limit(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """达到 MAX_LIMIT 后即使仍未命中阈值也不再扩窗。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 200, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", True, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_EXPAND_THRESHOLD", 999, raising=False)

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    # 每次都返回满页，但只有 1 条命中 → 永远低于阈值，直到 MAX_LIMIT 停止。
    first_records = [
        {"ts": "2025-09-15T09:00:00Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC error"},
    ] + [
        {"ts": f"2025-09-15T09:00:{i:02d}Z", "controller": "MPU",
         "level": "INFO", "msg": "download complete"}
        for i in range(1, 100)
    ]
    second_records = [
        {"ts": "2025-09-15T09:01:00Z", "controller": "iCGM",
         "level": "ERROR", "msg": "eMMC error"},
    ] + [
        {"ts": f"2025-09-15T09:01:{i % 60:02d}Z", "controller": "MPU",
         "level": "INFO", "msg": "download complete"}
        for i in range(1, 200)
    ]
    log_responses = [
        MagicMock(status_code=200, text="\n".join(json.dumps(r) for r in first_records)),
        MagicMock(status_code=200, text="\n".join(json.dumps(r) for r in second_records)),
    ]

    client = _make_client_with_responses([status_resp, *log_responses])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        await agent._load_logs_from_bundle("bundle-x", ["eMMC"])

    # 100 → 200（已到 MAX）→ 停止。共 2 次 logs GET（首次 + 扩窗一次后到 MAX 停止）
    log_get_count = client.get.await_count - 1  # 减去 status
    assert log_get_count == 2
    last_call_kwargs = client.get.await_args_list[-1].kwargs
    assert last_call_kwargs["params"]["limit"] == 200


@pytest.mark.asyncio
async def test_no_expand_when_disabled(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """LOG_ANALYSIS_AUTO_EXPAND=False 时不扩窗。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 1000, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", False, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_EXPAND_THRESHOLD", 999, raising=False)

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    rec = json.dumps({"ts": "2025-09-15T09:00:00Z", "controller": "iCGM",
                      "level": "ERROR", "msg": "eMMC error"})
    log_resp = MagicMock(status_code=200, text=rec)

    client = _make_client_with_responses([status_resp, log_resp])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        await agent._load_logs_from_bundle("bundle-x", ["eMMC"])

    # 只有一次 logs GET
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_no_expand_when_no_keywords(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """keywords 为空时即使命中数低也不扩窗（防止盲扫全量），但应直接使用更大的 NO_KEYWORD_LIMIT。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 1000, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_NO_KEYWORD_LIMIT", 800, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", True, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_EXPAND_THRESHOLD", 999, raising=False)

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    records = [
        {"ts": f"2025-09-15T09:00:{i:02d}Z", "controller": "iCGM",
         "level": "INFO", "msg": f"line {i}"}
        for i in range(10)
    ]
    log_resp = MagicMock(
        status_code=200,
        text="\n".join(json.dumps(r) for r in records),
    )

    client = _make_client_with_responses([status_resp, log_resp])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        result = await agent._load_logs_from_bundle("bundle-x", None)

    # 仅一次 status + 一次 logs，无扩窗
    assert client.get.await_count == 2
    # 第二次调用（logs）应使用 NO_KEYWORD_LIMIT 而非 LOG_ANALYSIS_LIMIT
    _, kwargs = client.get.await_args_list[1]
    assert kwargs["params"]["limit"] == 800
    assert "line 0" in result


@pytest.mark.asyncio
async def test_no_keyword_limit_capped_by_max(
    agent: LogAnalyticsAgent, monkeypatch
) -> None:
    """NO_KEYWORD_LIMIT 不应超过 MAX_LIMIT。"""
    monkeypatch.setattr(settings, "LOG_ANALYSIS_LIMIT", 100, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_MAX_LIMIT", 500, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_NO_KEYWORD_LIMIT", 9999, raising=False)
    monkeypatch.setattr(settings, "LOG_ANALYSIS_AUTO_EXPAND", True, raising=False)

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = _bundle_status_ok()
    log_resp = MagicMock(
        status_code=200,
        text=json.dumps({"ts": "2025-09-15T09:00:00Z", "controller": "iCGM",
                         "level": "INFO", "msg": "x"}),
    )

    client = _make_client_with_responses([status_resp, log_resp])

    with patch("agents.log_analytics.httpx.AsyncClient", return_value=client):
        await agent._load_logs_from_bundle("bundle-x", [])

    _, kwargs = client.get.await_args_list[1]
    assert kwargs["params"]["limit"] == 500

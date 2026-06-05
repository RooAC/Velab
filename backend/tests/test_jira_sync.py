"""Tests for Jira sync service and API endpoints.

Covers:
- ADF text extraction
- _parse_issue field mapping
- fetch_jira_issues (pagination)
- sync_jira_issues (skipped / ok / http_error / generic error)
- GET /api/jira/sync-status
- POST /api/jira/sync (202 + 503)
- POST /api/jira/sync/wait
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── ADF 文本提取 ──────────────────────────────────────────────────────────────

from services.jira_sync import _adf_to_text, _parse_issue


class TestAdfToText:
    def test_plain_string(self):
        assert _adf_to_text("hello world") == "hello world"

    def test_empty(self):
        assert _adf_to_text("") == ""
        assert _adf_to_text(None) == ""  # type: ignore[arg-type]

    def test_text_node(self):
        node = {"type": "text", "text": "foo bar"}
        assert _adf_to_text(node) == "foo bar"

    def test_nested_paragraph(self):
        node = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "升级失败"},
                        {"type": "text", "text": "原因不明"},
                    ],
                }
            ],
        }
        result = _adf_to_text(node)
        assert "升级失败" in result
        assert "原因不明" in result

    def test_list_of_nodes(self):
        nodes = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        result = _adf_to_text(nodes)
        assert "a" in result and "b" in result


class TestParseIssue:
    _RAW = {
        "key": "FOTA-100",
        "fields": {
            "summary": "iCGM 升级挂死",
            "description": "raw description string",
            "resolution": {"name": "Fixed", "description": "已修复"},
            "status": {"name": "Resolved"},
            "priority": {"name": "High"},
            "labels": ["fota", "icgm"],
        },
    }

    def test_key_and_summary(self):
        issue = _parse_issue(self._RAW)
        assert issue["key"] == "FOTA-100"
        assert issue["summary"] == "iCGM 升级挂死"

    def test_description_plain_string(self):
        issue = _parse_issue(self._RAW)
        assert issue["description"] == "raw description string"

    def test_resolution_from_description_field(self):
        issue = _parse_issue(self._RAW)
        assert issue["resolution"] == "已修复"

    def test_status_and_priority(self):
        issue = _parse_issue(self._RAW)
        assert issue["status"] == "Resolved"
        assert issue["priority"] == "High"

    def test_labels(self):
        issue = _parse_issue(self._RAW)
        assert issue["labels"] == ["fota", "icgm"]

    def test_synced_at_present(self):
        issue = _parse_issue(self._RAW)
        assert "synced_at" in issue

    def test_missing_fields_graceful(self):
        raw = {"key": "FOTA-999", "fields": {}}
        issue = _parse_issue(raw)
        assert issue["key"] == "FOTA-999"
        assert issue["summary"] == ""
        assert issue["resolution"] == ""


# ── fetch_jira_issues ─────────────────────────────────────────────────────────

from services.jira_sync import fetch_jira_issues


class TestFetchJiraIssues:
    """Tests for HTTP pagination logic using mocked httpx.AsyncClient."""

    def _make_resp(self, issues: list[dict], total: int) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"issues": issues, "total": total})
        return resp

    def _raw_issue(self, key: str) -> dict:
        return {
            "key": key,
            "fields": {
                "summary": f"summary for {key}",
                "description": "desc",
                "resolution": None,
                "status": {"name": "Open"},
                "priority": None,
                "labels": [],
            },
        }

    @pytest.mark.asyncio
    async def test_single_page(self):
        raw_issues = [self._raw_issue(f"FOTA-{i}") for i in range(3)]
        resp = self._make_resp(raw_issues, total=3)

        with patch("services.jira_sync.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_jira_issues(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="token",
                project_keys=["FOTA"],
            )

        assert len(result) == 3
        assert result[0]["key"] == "FOTA-0"

    @pytest.mark.asyncio
    async def test_pagination_two_pages(self):
        page1 = [self._raw_issue(f"FOTA-{i}") for i in range(100)]
        page2 = [self._raw_issue(f"FOTA-{i}") for i in range(100, 130)]
        resp1 = self._make_resp(page1, total=130)
        resp2 = self._make_resp(page2, total=130)

        with patch("services.jira_sync.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[resp1, resp2])
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_jira_issues(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="token",
                project_keys=["FOTA"],
                max_results=500,
            )

        assert len(result) == 130

    @pytest.mark.asyncio
    async def test_max_results_cap(self):
        """max_results=5 时不超过 5 条。"""
        raw_issues = [self._raw_issue(f"FOTA-{i}") for i in range(50)]
        resp = self._make_resp(raw_issues[:5], total=50)

        with patch("services.jira_sync.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_jira_issues(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="token",
                project_keys=["FOTA"],
                max_results=5,
            )

        assert len(result) <= 5


# ── sync_jira_issues ──────────────────────────────────────────────────────────

from services.jira_sync import sync_jira_issues


class TestSyncJiraIssues:
    @pytest.mark.asyncio
    async def test_skipped_when_not_configured(self, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", None, raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", None, raising=False)

        status, count = await sync_jira_issues()
        assert status == "skipped"
        assert count == 0

    @pytest.mark.asyncio
    async def test_skipped_no_api_token(self, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", None, raising=False)

        status, count = await sync_jira_issues()
        assert status == "skipped"
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_projects(self, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)
        monkeypatch.setattr(settings, "JIRA_PROJECT_KEYS", "", raising=False)

        status, count = await sync_jira_issues()
        assert status == "no_projects"

    @pytest.mark.asyncio
    async def test_successful_sync(self, monkeypatch, tmp_path):
        from config import settings
        import services.jira_sync as svc

        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)
        monkeypatch.setattr(settings, "JIRA_EMAIL", "test@example.com", raising=False)
        monkeypatch.setattr(settings, "JIRA_PROJECT_KEYS", "FOTA", raising=False)
        monkeypatch.setattr(settings, "JIRA_SYNC_MAX_RESULTS", 10, raising=False)
        monkeypatch.setattr(settings, "JIRA_JQL_FILTER", "", raising=False)

        cache_path = tmp_path / "tickets.json"
        meta_path = tmp_path / ".sync_meta.json"
        monkeypatch.setattr(svc, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(svc, "_META_PATH", meta_path)

        mock_issues = [{"key": "FOTA-1", "summary": "test", "description": "", "resolution": "",
                        "status": "", "priority": "", "labels": [], "synced_at": "now"}]
        with patch("services.jira_sync.fetch_jira_issues", new=AsyncMock(return_value=mock_issues)):
            status, count = await sync_jira_issues()

        assert status == "ok"
        assert count == 1
        assert cache_path.exists()
        saved = json.loads(cache_path.read_text())
        assert saved[0]["key"] == "FOTA-1"

    @pytest.mark.asyncio
    async def test_http_error_returns_error_status(self, monkeypatch, tmp_path):
        from config import settings
        import services.jira_sync as svc
        import httpx

        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "bad_token", raising=False)
        monkeypatch.setattr(settings, "JIRA_PROJECT_KEYS", "FOTA", raising=False)
        monkeypatch.setattr(settings, "JIRA_SYNC_MAX_RESULTS", 10, raising=False)
        monkeypatch.setattr(settings, "JIRA_JQL_FILTER", "", raising=False)

        meta_path = tmp_path / ".sync_meta.json"
        monkeypatch.setattr(svc, "_META_PATH", meta_path)

        req = httpx.Request("GET", "https://test.atlassian.net/rest/api/3/search")
        resp = httpx.Response(401, request=req, text='{"message":"Unauthorized"}')
        err = httpx.HTTPStatusError("401", request=req, response=resp)

        with patch("services.jira_sync.fetch_jira_issues", new=AsyncMock(side_effect=err)):
            status, count = await sync_jira_issues()

        assert "http_error" in status
        assert "401" in status
        assert count == 0

    @pytest.mark.asyncio
    async def test_generic_error_returns_error_status(self, monkeypatch, tmp_path):
        from config import settings
        import services.jira_sync as svc

        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)
        monkeypatch.setattr(settings, "JIRA_PROJECT_KEYS", "FOTA", raising=False)
        monkeypatch.setattr(settings, "JIRA_SYNC_MAX_RESULTS", 10, raising=False)
        monkeypatch.setattr(settings, "JIRA_JQL_FILTER", "", raising=False)

        meta_path = tmp_path / ".sync_meta.json"
        monkeypatch.setattr(svc, "_META_PATH", meta_path)

        with patch("services.jira_sync.fetch_jira_issues", new=AsyncMock(side_effect=RuntimeError("network unreachable"))):
            status, count = await sync_jira_issues()

        assert "error" in status
        assert count == 0


# ── /api/jira/* 端点 ──────────────────────────────────────────────────────────

class TestJiraSyncApi:
    """使用 conftest.client fixture 测试 Jira API 端点。"""

    def test_sync_status_not_configured(self, client):
        r = client.get("/api/jira/sync-status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False
        assert body["project_keys"] == []

    def test_sync_trigger_503_when_not_configured(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", None, raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", None, raising=False)

        r = client.post("/api/jira/sync")
        assert r.status_code == 503

    def test_sync_trigger_202_when_configured(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)

        with patch("api.jira_sync_api.sync_jira_issues", new=AsyncMock(return_value=("ok", 5))):
            r = client.post("/api/jira/sync")

        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] is True

    def test_sync_wait_503_when_not_configured(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", None, raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", None, raising=False)

        r = client.post("/api/jira/sync/wait")
        assert r.status_code == 503

    def test_sync_wait_returns_result(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)

        with patch("api.jira_sync_api.sync_jira_issues", new=AsyncMock(return_value=("ok", 42))):
            r = client.post("/api/jira/sync/wait")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["synced"] == 42

    def test_sync_wait_502_on_error(self, client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net", raising=False)
        monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok", raising=False)

        with patch("api.jira_sync_api.sync_jira_issues", new=AsyncMock(return_value=("http_error:401", 0))):
            r = client.post("/api/jira/sync/wait")

        assert r.status_code == 502

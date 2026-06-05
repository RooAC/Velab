"""Jira 工单同步服务

从 Jira REST API v3 (Cloud) / v2 (Server) 拉取工单并缓存至
data/jira_mock/tickets.json，供 JiraKnowledgeAgent 使用。

配置（均可通过 .env 覆盖）：
  JIRA_BASE_URL       — Jira 实例地址，例如 https://org.atlassian.net
  JIRA_EMAIL          — Jira Cloud 账号邮箱（Basic Auth user）
  JIRA_API_TOKEN      — API Token（Cloud）或 PAT（Server）
  JIRA_PROJECT_KEYS   — 逗号分隔的项目 Key，例如 FOTA,VEHICLE
  JIRA_SYNC_MAX_RESULTS — 单次同步上限（默认 500，自动分页）
  JIRA_JQL_FILTER     — 额外 JQL 过滤条件（可选）

未配置 JIRA_BASE_URL / JIRA_API_TOKEN 时，sync_jira_issues() 直接返回
("skipped", 0)，系统继续使用已有的本地 JSON 缓存，不影响任何现有功能。

作者：FOTA 诊断平台团队
创建时间：2026-06-04
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)

# 本地缓存路径（JiraKnowledgeAgent._load_mock_tickets() 读取的文件）
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "jira_mock" / "tickets.json"
# 同步元数据（不影响 Agent 读取，仅用于 API 状态查询）
_META_PATH = _CACHE_PATH.parent / ".sync_meta.json"

_JIRA_FIELDS = (
    "summary,description,resolution,status,priority,labels,"
    "created,updated,assignee,reporter"
)


# ── ADF 文本提取 ──────────────────────────────────────────────────────────────

def _adf_to_text(node: Any) -> str:
    """递归提取 Atlassian Document Format (ADF) 节点的纯文本。

    Jira Cloud API v3 的 description 字段返回 ADF JSON 对象；
    Jira Server v2 的 description 仍是普通字符串，直接返回。
    """
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        parts = [_adf_to_text(child) for child in node.get("content", [])]
        return " ".join(p for p in parts if p)
    if isinstance(node, list):
        return " ".join(_adf_to_text(item) for item in node if item)
    return ""


def _parse_issue(raw: dict) -> dict:
    """将 Jira API 返回的原始工单对象转换为 Agent 消费的标准格式。"""
    fields = raw.get("fields") or {}
    resolution = fields.get("resolution") or {}
    resolution_text = (
        resolution.get("description", "") or resolution.get("name", "")
        if isinstance(resolution, dict)
        else str(resolution)
    )
    return {
        "key": raw.get("key", ""),
        "summary": fields.get("summary") or "",
        "description": _adf_to_text(fields.get("description") or ""),
        "resolution": resolution_text,
        "status": (fields.get("status") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "labels": fields.get("labels") or [],
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Jira API 调用 ─────────────────────────────────────────────────────────────

async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    auth: tuple[str, str],
    jql: str,
    start_at: int,
    max_results: int,
) -> tuple[list[dict], int]:
    """拉取单页结果，返回 (issues, total)。"""
    params = {
        "jql": jql,
        "startAt": start_at,
        "maxResults": min(max_results, 100),  # Jira 单页上限为 100
        "fields": _JIRA_FIELDS,
    }
    resp = await client.get(url, params=params, auth=auth)
    resp.raise_for_status()
    data = resp.json()
    return data.get("issues", []), data.get("total", 0)


async def fetch_jira_issues(
    base_url: str,
    email: str,
    api_token: str,
    project_keys: list[str],
    jql_filter: str = "",
    max_results: int = 500,
) -> list[dict]:
    """从 Jira 拉取工单（自动分页），返回标准格式列表。

    Args:
        base_url: Jira 实例地址，例如 https://org.atlassian.net
        email: 账号邮箱（Jira Cloud）或用户名（Jira Server）
        api_token: API Token 或 Personal Access Token
        project_keys: 项目 Key 列表，例如 ["FOTA", "VEHICLE"]
        jql_filter: 额外 JQL 过滤条件，为空则不附加
        max_results: 最多拉取工单数（自动分页）

    Returns:
        标准工单列表（含 key、summary、description、resolution、status 等字段）
    """
    project_clause = "project IN (" + ", ".join(f'"{k}"' for k in project_keys) + ")"
    jql = project_clause
    if jql_filter:
        jql += f" AND ({jql_filter})"
    jql += " ORDER BY updated DESC"

    search_url = f"{base_url.rstrip('/')}/rest/api/3/search"
    auth = (email, api_token)

    issues: list[dict] = []
    start_at = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            batch, total = await _fetch_page(
                client, search_url, auth, jql, start_at, max_results - len(issues)
            )
            if not batch:
                break
            issues.extend(batch)
            start_at += len(batch)
            if start_at >= total or len(issues) >= max_results:
                break

    return [_parse_issue(raw) for raw in issues]


# ── 原子写入工具 ──────────────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: Any) -> None:
    """原子写入 JSON 文件（.partial + os.replace 防止损坏）。"""
    import os
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.flush = lambda: None  # type: ignore[assignment]
    except Exception:
        pass
    os.replace(tmp, path)


# ── 公开同步接口 ──────────────────────────────────────────────────────────────

async def sync_jira_issues() -> tuple[str, int]:
    """
    主同步入口：从 Jira 拉取工单并覆写本地缓存。

    配置未就绪时静默跳过，不影响 Agent 正常运行。

    Returns:
        (status, count)
        status: "ok" | "skipped" | "no_projects" | "error:<type>"
        count: 成功同步的工单数量
    """
    if not settings.JIRA_BASE_URL or not settings.JIRA_API_TOKEN:
        log.info("Jira sync skipped: JIRA_BASE_URL or JIRA_API_TOKEN not configured")
        return "skipped", 0

    project_keys = [p.strip() for p in settings.JIRA_PROJECT_KEYS.split(",") if p.strip()]
    if not project_keys:
        log.warning("Jira sync skipped: JIRA_PROJECT_KEYS is empty")
        return "no_projects", 0

    log.info("Jira sync starting: projects=%s max_results=%d", project_keys, settings.JIRA_SYNC_MAX_RESULTS)
    try:
        issues = await fetch_jira_issues(
            base_url=settings.JIRA_BASE_URL,
            email=settings.JIRA_EMAIL,
            api_token=settings.JIRA_API_TOKEN,
            project_keys=project_keys,
            jql_filter=settings.JIRA_JQL_FILTER,
            max_results=settings.JIRA_SYNC_MAX_RESULTS,
        )

        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(_CACHE_PATH, issues)

        meta = {
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "issue_count": len(issues),
            "project_keys": project_keys,
            "jira_base_url": settings.JIRA_BASE_URL,
            "status": "ok",
        }
        _atomic_write_json(_META_PATH, meta)

        log.info("Jira sync completed: %d issues synced from %s", len(issues), project_keys)
        return "ok", len(issues)

    except httpx.HTTPStatusError as e:
        status = f"http_error:{e.response.status_code}"
        log.error(
            "Jira API HTTP error: %d %s",
            e.response.status_code,
            e.response.text[:200],
        )
        _update_meta_error(status)
        return status, 0
    except Exception as e:
        status = f"error:{type(e).__name__}"
        log.exception("Jira sync failed: %s", e)
        _update_meta_error(status)
        return status, 0


def get_sync_meta() -> dict:
    """返回最近一次同步的元数据。不存在时返回空字典。"""
    try:
        if _META_PATH.exists():
            return json.loads(_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _update_meta_error(status: str) -> None:
    """同步失败时更新元数据中的状态字段，保留上次成功时间。"""
    try:
        meta = get_sync_meta()
        meta["status"] = status
        meta["last_attempted_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(_META_PATH, meta)
    except Exception:
        pass

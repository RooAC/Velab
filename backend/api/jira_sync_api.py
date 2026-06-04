"""Jira 同步管理 API

提供手动触发同步和状态查询端点：
  POST /api/jira/sync       — 立即触发一次 Jira 工单同步（后台异步执行）
  GET  /api/jira/sync-status — 查询配置状态和上次同步元数据

作者：FOTA 诊断平台团队
创建时间：2026-06-04
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from config import settings
from services.jira_sync import get_sync_meta, sync_jira_issues

router = APIRouter()
log = logging.getLogger(__name__)


class JiraSyncStatusResponse(BaseModel):
    configured: bool = Field(description="Jira 是否已配置（URL + Token 均存在）")
    project_keys: list[str] = Field(default_factory=list, description="已配置的项目 Key")
    last_synced_at: str | None = Field(None, description="上次成功同步时间（ISO8601）")
    last_attempted_at: str | None = Field(None, description="上次尝试同步时间")
    issue_count: int | None = Field(None, description="上次同步的工单数量")
    status: str | None = Field(None, description="上次同步状态：ok / skipped / error:...")


class JiraSyncTriggerResponse(BaseModel):
    accepted: bool
    message: str


class JiraSyncResultResponse(BaseModel):
    status: str
    synced: int


@router.get("/sync-status", response_model=JiraSyncStatusResponse)
def get_jira_sync_status() -> JiraSyncStatusResponse:
    """查询 Jira 配置状态及上次同步元数据。"""
    meta = get_sync_meta()
    project_keys = [p.strip() for p in settings.JIRA_PROJECT_KEYS.split(",") if p.strip()]
    configured = bool(settings.JIRA_BASE_URL and settings.JIRA_API_TOKEN)
    return JiraSyncStatusResponse(
        configured=configured,
        project_keys=project_keys if configured else [],
        last_synced_at=meta.get("last_synced_at"),
        last_attempted_at=meta.get("last_attempted_at"),
        issue_count=meta.get("issue_count"),
        status=meta.get("status"),
    )


@router.post("/sync", response_model=JiraSyncTriggerResponse, status_code=202)
async def trigger_jira_sync(background_tasks: BackgroundTasks) -> JiraSyncTriggerResponse:
    """手动触发 Jira 工单同步（后台异步执行，立即返回 202）。

    Raises:
        HTTPException 503: Jira 未配置时拒绝请求。
    """
    if not settings.JIRA_BASE_URL or not settings.JIRA_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Jira integration not configured. Set JIRA_BASE_URL and JIRA_API_TOKEN.",
        )

    async def _run() -> None:
        status, count = await sync_jira_issues()
        log.info("Background Jira sync completed: status=%s count=%d", status, count)

    background_tasks.add_task(_run)
    return JiraSyncTriggerResponse(
        accepted=True,
        message="Jira sync started in background. Check /api/jira/sync-status for progress.",
    )


@router.post("/sync/wait", response_model=JiraSyncResultResponse)
async def trigger_jira_sync_wait() -> JiraSyncResultResponse:
    """触发 Jira 工单同步并等待完成（供脚本/CI 使用，勿在生产前端直接调用）。

    Raises:
        HTTPException 503: Jira 未配置时拒绝请求。
    """
    if not settings.JIRA_BASE_URL or not settings.JIRA_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Jira integration not configured. Set JIRA_BASE_URL and JIRA_API_TOKEN.",
        )
    status, count = await sync_jira_issues()
    if status not in ("ok", "skipped", "no_projects"):
        raise HTTPException(status_code=502, detail=f"Jira sync failed: {status}")
    return JiraSyncResultResponse(status=status, synced=count)

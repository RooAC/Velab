"""
技术文档上传与索引管理 API

提供 PDF / Excel / 文本文档的上传、列表、删除能力。
上传后立即可被 doc_retrieval Agent 通过 TF-IDF 检索；
若启用 embedding 模式且配置 API Key，可通过 BackgroundTasks
异步增量重算 tech_docs.json 索引。

端点：
- POST   /api/docs/upload         上传文档（multipart/form-data, field=file）
- GET    /api/docs                列出已上传文档
- DELETE /api/docs/{doc_id}       删除文档及对应索引片段

存储布局：
  data/docs/uploaded/
    manifest.json               文档元数据清单
    <doc_id>/<original_name>    实际文件

作者：FOTA 诊断平台团队
创建时间：2026-05-25
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

try:  # POSIX only
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows fallback
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 路径常量 ──
_DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "docs" / "uploaded"
_MANIFEST_PATH = _DOCS_ROOT / "manifest.json"
_MANIFEST_LOCKFILE = _DOCS_ROOT / ".manifest.lock"

# 进程内：threading.Lock 串行多线程 manifest 访问
# 进程间：fcntl.flock 串行多 worker（Gunicorn / Uvicorn --workers > 1）
_MANIFEST_LOCK = threading.Lock()

# ── 上传限制 ──
ALLOWED_SUFFIXES = frozenset({".pdf", ".xlsx", ".xlsm", ".txt", ".md"})
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MiB
_SAFE_NAME_RE = re.compile(r"[^\w\u4e00-\u9fff.\-]+")

# Magic bytes（文件头前缀）
_MAGIC_PDF = b"%PDF-"
_MAGIC_ZIP = b"PK\x03\x04"  # xlsx/xlsm 是 zip 容器
_MAGIC_ZIP_EMPTY = b"PK\x05\x06"
_MAGIC_ZIP_SPAN = b"PK\x07\x08"

# Embedding 状态枚举
EMBED_STATUS_DISABLED = "disabled"
EMBED_STATUS_NO_KEY = "skipped_no_key"
EMBED_STATUS_PENDING = "pending"
EMBED_STATUS_OK = "ok"
EMBED_STATUS_FAILED = "failed"


@contextlib.contextmanager
def _manifest_lock() -> Iterator[None]:
    """组合 threading + fcntl 锁，进程内 + 跨进程双重保护。"""
    _ensure_dirs()
    with _MANIFEST_LOCK:
        if not _HAS_FCNTL:
            yield
            return
        # 跨进程文件锁（独占）
        fd = os.open(str(_MANIFEST_LOCKFILE), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


# ── Schema ──

class DocumentMeta(BaseModel):
    """已上传文档元数据"""

    model_config = ConfigDict(populate_by_name=True)

    doc_id: str = Field(..., description="文档唯一 ID（基于内容 SHA-256 前 16 位）")
    filename: str = Field(..., description="原始文件名（清洗后）")
    suffix: str = Field(..., description="文件后缀，含点号")
    size: int = Field(..., description="字节数")
    uploaded_at: str = Field(..., description="上传时间 ISO-8601")
    chunks: int = Field(0, description="切块数量；TF-IDF 索引时填充")
    embedding_status: str = Field(
        EMBED_STATUS_DISABLED,
        description="embedding 索引状态：disabled/skipped_no_key/pending/ok/failed",
    )


class DocumentListResponse(BaseModel):
    total: int
    items: List[DocumentMeta]


class UploadResponse(BaseModel):
    success: bool
    doc: DocumentMeta
    reindex_scheduled: bool = Field(
        False, description="是否已调度后台 embedding 增量重算"
    )


# ── 工具函数 ──

def _ensure_dirs() -> None:
    _DOCS_ROOT.mkdir(parents=True, exist_ok=True)


def _read_manifest() -> List[dict]:
    if not _MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("manifest 读取失败: %s", exc)
        return []


def _write_manifest(items: List[dict]) -> None:
    _ensure_dirs()
    partial = _MANIFEST_PATH.with_suffix(".json.partial")
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    with open(partial, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(partial, _MANIFEST_PATH)


def _safe_filename(name: str) -> str:
    """清洗文件名，保留中英文/数字/点号/连字符"""
    base = Path(name).name  # 去路径
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._")
    return cleaned or "unnamed"


def _compute_doc_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _validate_content_signature(path: Path, suffix: str) -> bool:
    """基于文件头 magic bytes 校验真实内容类型与声称后缀一致。

    返回 True 表示通过；False 表示文件头与后缀不匹配（疑似伪装）。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return False
    if suffix == ".pdf":
        return head.startswith(_MAGIC_PDF)
    if suffix in {".xlsx", ".xlsm"}:
        return head.startswith((_MAGIC_ZIP, _MAGIC_ZIP_EMPTY, _MAGIC_ZIP_SPAN))
    if suffix in {".txt", ".md"}:
        # 纯文本：必须能以 utf-8 或常见文本编码解码前 1KB
        try:
            with open(path, "rb") as f:
                sample = f.read(1024)
            sample.decode("utf-8")
            return True
        except (OSError, UnicodeDecodeError):
            try:
                sample.decode("gbk")
                return True
            except (UnicodeDecodeError, NameError):
                return False
    return False


def _update_embedding_status(doc_id: str, status: str) -> None:
    """在 manifest 中更新指定 doc 的 embedding_status；记录失败但不抛错。"""
    try:
        with _manifest_lock():
            items = _read_manifest()
            changed = False
            for it in items:
                if it.get("doc_id") == doc_id:
                    it["embedding_status"] = status
                    changed = True
                    break
            if changed:
                _write_manifest(items)
    except OSError as exc:
        logger.warning("更新 embedding_status 失败 doc=%s: %s", doc_id, exc)


async def _reindex_embeddings(doc_id: str) -> None:
    """后台任务：增量重算 embedding 索引（如未启用 embedding 则 no-op）"""
    try:
        from config import settings

        if not settings.AGENTS_USE_EMBEDDINGS:
            logger.info("AGENTS_USE_EMBEDDINGS=False，跳过 embedding 重算 doc=%s", doc_id)
            _update_embedding_status(doc_id, EMBED_STATUS_DISABLED)
            return
        if not (settings.OPENAI_API_KEY or settings.LITELLM_API_KEY):
            logger.warning("无可用 API Key，跳过 embedding 重算 doc=%s", doc_id)
            _update_embedding_status(doc_id, EMBED_STATUS_NO_KEY)
            return

        # 复用现有脚本逻辑，避免重复代码
        from scripts.ingest_embeddings import ingest_docs  # type: ignore
        from services.vector_search import VectorSearchService

        svc = VectorSearchService(use_embeddings=True)
        saved = await ingest_docs(svc)
        logger.info("Embedding 重算完成: %d 条 (trigger doc=%s)", saved, doc_id)
        _update_embedding_status(doc_id, EMBED_STATUS_OK)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding 重算失败 doc=%s: %s", doc_id, exc)
        _update_embedding_status(doc_id, EMBED_STATUS_FAILED)


def _initial_embedding_status() -> str:
    """根据当前 settings 给新上传文档赋初始 embedding_status。"""
    try:
        from config import settings

        if not settings.AGENTS_USE_EMBEDDINGS:
            return EMBED_STATUS_DISABLED
        if not (settings.OPENAI_API_KEY or settings.LITELLM_API_KEY):
            return EMBED_STATUS_NO_KEY
        return EMBED_STATUS_PENDING
    except Exception:  # noqa: BLE001
        return EMBED_STATUS_DISABLED


# ── 端点 ──

@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """上传技术文档（PDF / Excel / 文本），写盘 + 更新 manifest + 调度索引"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    safe_name = _safe_filename(file.filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型：{suffix}；允许 {sorted(ALLOWED_SUFFIXES)}",
        )

    # 流式落临时文件并限制大小（防止内存爆炸）
    _ensure_dirs()
    tmp_dir = Path(tempfile.mkdtemp(prefix="docupload_", dir=str(_DOCS_ROOT)))
    tmp_path = tmp_dir / safe_name
    total = 0
    hasher = hashlib.sha256()
    try:
        with open(tmp_path, "wb") as f_out:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过上限 {MAX_UPLOAD_SIZE // (1024 * 1024)} MiB",
                    )
                hasher.update(chunk)
                f_out.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="空文件")

        # 真实文件类型校验（防伪装后缀）
        if not _validate_content_signature(tmp_path, suffix):
            raise HTTPException(
                status_code=415,
                detail=f"文件内容与后缀 {suffix} 不匹配（magic bytes 校验失败）",
            )

        doc_id = hasher.hexdigest()[:16]
        target_dir = _DOCS_ROOT / doc_id
        if target_dir.exists():
            # 内容已存在（去重），返回已有 meta
            shutil.rmtree(tmp_dir, ignore_errors=True)
            with _manifest_lock():
                items = _read_manifest()
                for item in items:
                    if item.get("doc_id") == doc_id:
                        return UploadResponse(
                            success=True,
                            doc=DocumentMeta(**item),
                            reindex_scheduled=False,
                        )

        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / safe_name
        shutil.move(str(tmp_path), str(final_path))
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("文档上传失败: %s", file.filename)
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    meta = DocumentMeta(
        doc_id=doc_id,
        filename=safe_name,
        suffix=suffix,
        size=total,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        chunks=0,
        embedding_status=_initial_embedding_status(),
    )

    with _manifest_lock():
        items = _read_manifest()
        items = [it for it in items if it.get("doc_id") != doc_id]
        items.append(meta.model_dump())
        _write_manifest(items)

    # 调度后台 embedding 重算（如启用）
    background_tasks.add_task(_reindex_embeddings, doc_id)

    return UploadResponse(success=True, doc=meta, reindex_scheduled=True)


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """列出所有已上传文档"""
    items = _read_manifest()
    items.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
    return DocumentListResponse(
        total=len(items),
        items=[DocumentMeta(**it) for it in items],
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str) -> None:
    """删除文档及对应文件"""
    if not re.fullmatch(r"[0-9a-f]{16}", doc_id):
        raise HTTPException(status_code=400, detail="非法 doc_id")
    with _manifest_lock():
        items = _read_manifest()
        matched: Optional[dict] = next((it for it in items if it.get("doc_id") == doc_id), None)
        if matched is None:
            raise HTTPException(status_code=404, detail="文档不存在")

        target_dir = _DOCS_ROOT / doc_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        _write_manifest([it for it in items if it.get("doc_id") != doc_id])

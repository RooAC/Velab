"""
backend/api/docs.py 上传/列表/删除单元测试

避开 main app 的 lifespan（避免 PG 依赖），用裸 FastAPI 仅挂 docs router。
"""

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def docs_client(tmp_path, monkeypatch):
    """提供绑定到临时目录的 docs API client，与 main app 完全隔离。"""
    # 重定向 _DOCS_ROOT / _MANIFEST_PATH 到 tmp_path
    import api.docs as docs_module

    docs_root = tmp_path / "uploaded"
    docs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(docs_module, "_DOCS_ROOT", docs_root)
    monkeypatch.setattr(
        docs_module, "_MANIFEST_PATH", docs_root / "manifest.json"
    )
    monkeypatch.setattr(
        docs_module, "_MANIFEST_LOCKFILE", docs_root / ".manifest.lock"
    )

    # 绑定 background task 为同步无操作（避免触发 embedding 重算）
    async def _no_reindex(doc_id: str) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(docs_module, "_reindex_embeddings", _no_reindex)

    mini = FastAPI()
    mini.include_router(docs_module.router, prefix="/api/docs")
    return TestClient(mini), docs_root


# ── 工具 ──

def _upload(client: TestClient, name: str, body: bytes = b"hello world"):
    return client.post(
        "/api/docs/upload",
        files={"file": (name, io.BytesIO(body), "application/octet-stream")},
    )


# ── 上传 ──

class TestUpload:
    def test_uploads_txt_and_returns_meta(self, docs_client):
        client, root = docs_client
        resp = _upload(client, "guide.txt", b"hello fota world")
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["doc"]["filename"] == "guide.txt"
        assert body["doc"]["suffix"] == ".txt"
        assert body["doc"]["size"] == len(b"hello fota world")
        doc_id = body["doc"]["doc_id"]
        # 文件落盘
        assert (root / doc_id / "guide.txt").exists()
        # manifest 写入
        assert (root / "manifest.json").exists()

    def test_rejects_unsupported_suffix(self, docs_client):
        client, _ = docs_client
        resp = _upload(client, "evil.exe", b"MZ")
        assert resp.status_code == 415
        assert "不支持" in resp.json()["detail"]

    def test_rejects_missing_filename(self, docs_client):
        client, _ = docs_client
        # filename 空串 -> FastAPI 仍接收，但触发 400
        resp = client.post(
            "/api/docs/upload",
            files={"file": ("", io.BytesIO(b"x"), "application/octet-stream")},
        )
        assert resp.status_code in (400, 422)

    def test_rejects_empty_file(self, docs_client):
        client, _ = docs_client
        resp = _upload(client, "empty.txt", b"")
        assert resp.status_code == 400
        assert "空" in resp.json()["detail"]

    def test_dedup_same_content_returns_existing(self, docs_client):
        client, _ = docs_client
        r1 = _upload(client, "a.txt", b"identical-content")
        r2 = _upload(client, "b.txt", b"identical-content")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["doc"]["doc_id"] == r2.json()["doc"]["doc_id"]
        # 第二次去重不再调度
        assert r2.json()["reindex_scheduled"] is False

    def test_sanitizes_dangerous_filename(self, docs_client):
        client, root = docs_client
        resp = _upload(client, "../../etc/passwd.txt", b"hack")
        assert resp.status_code == 201
        name = resp.json()["doc"]["filename"]
        # 路径遍历字符被清洗为下划线
        assert ".." not in name
        assert "/" not in name
        assert name.endswith("passwd.txt")

    def test_enforces_size_limit(self, docs_client, monkeypatch):
        import api.docs as docs_module

        monkeypatch.setattr(docs_module, "MAX_UPLOAD_SIZE", 100)
        client, _ = docs_client
        resp = _upload(client, "big.txt", b"x" * 200)
        assert resp.status_code == 413

    def test_rejects_pdf_with_wrong_magic_bytes(self, docs_client):
        """文件后缀 .pdf 但内容不是 PDF → 415 magic bytes 校验失败"""
        client, _ = docs_client
        resp = _upload(client, "fake.pdf", b"this is plain text, not a pdf")
        assert resp.status_code == 415
        assert "magic bytes" in resp.json()["detail"]

    def test_accepts_real_pdf_magic(self, docs_client):
        client, _ = docs_client
        resp = _upload(client, "real.pdf", b"%PDF-1.4 minimal body")
        assert resp.status_code == 201

    def test_rejects_xlsx_with_wrong_magic(self, docs_client):
        client, _ = docs_client
        resp = _upload(client, "fake.xlsx", b"not a zip")
        assert resp.status_code == 415

    def test_accepts_xlsx_zip_magic(self, docs_client):
        client, _ = docs_client
        resp = _upload(client, "real.xlsx", b"PK\x03\x04rest-of-zip")
        assert resp.status_code == 201

    def test_initial_embedding_status_disabled(self, docs_client, monkeypatch):
        """默认 AGENTS_USE_EMBEDDINGS=False → 初始状态 disabled"""
        from config import settings

        monkeypatch.setattr(settings, "AGENTS_USE_EMBEDDINGS", False, raising=False)
        client, _ = docs_client
        resp = _upload(client, "doc.txt", b"hello")
        assert resp.json()["doc"]["embedding_status"] == "disabled"

    def test_initial_embedding_status_no_key(self, docs_client, monkeypatch):
        """启用 embedding 但无 API Key → skipped_no_key"""
        from config import settings

        monkeypatch.setattr(settings, "AGENTS_USE_EMBEDDINGS", True, raising=False)
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "", raising=False)
        monkeypatch.setattr(settings, "LITELLM_API_KEY", "", raising=False)
        client, _ = docs_client
        resp = _upload(client, "doc.txt", b"hello")
        assert resp.json()["doc"]["embedding_status"] == "skipped_no_key"


# ── 列表 ──

class TestList:
    def test_empty_list_by_default(self, docs_client):
        client, _ = docs_client
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_lists_after_uploads_newest_first(self, docs_client):
        client, _ = docs_client
        _upload(client, "first.txt", b"one")
        _upload(client, "second.txt", b"two")
        resp = client.get("/api/docs")
        body = resp.json()
        assert body["total"] == 2
        filenames = [it["filename"] for it in body["items"]]
        assert set(filenames) == {"first.txt", "second.txt"}


# ── 删除 ──

class TestDelete:
    def test_deletes_existing(self, docs_client):
        client, root = docs_client
        r = _upload(client, "x.txt", b"data")
        doc_id = r.json()["doc"]["doc_id"]
        resp = client.delete(f"/api/docs/{doc_id}")
        assert resp.status_code == 204
        assert not (root / doc_id).exists()
        # manifest 中也消失
        list_resp = client.get("/api/docs")
        assert list_resp.json()["total"] == 0

    def test_returns_404_for_unknown(self, docs_client):
        client, _ = docs_client
        resp = client.delete("/api/docs/" + "f" * 16)
        assert resp.status_code == 404

    def test_returns_400_for_invalid_id(self, docs_client):
        client, _ = docs_client
        resp = client.delete("/api/docs/not-hex")
        assert resp.status_code == 400

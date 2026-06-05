"use client";

import { useEffect, useRef, useState } from "react";

interface DocMeta {
  doc_id: string;
  filename: string;
  suffix: string;
  size: number;
  uploaded_at: string;
  chunks: number;
  embedding_status?: string;
}

const ALLOWED = ".pdf,.xlsx,.xlsm,.txt,.md";

const EMBED_STATUS_LABEL: Record<string, { text: string; color: string }> = {
  disabled: { text: "TF-IDF", color: "var(--text-secondary)" },
  skipped_no_key: { text: "无Key", color: "#d97706" },
  pending: { text: "索引中", color: "#2563eb" },
  ok: { text: "向量", color: "#16a34a" },
  failed: { text: "失败", color: "var(--accent-red)" },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function DocManagerButton() {
  const [open, setOpen] = useState(false);
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/docs", { cache: "no-store" });
      const body = await resp.json();
      setDocs(Array.isArray(body.items) ? body.items : []);
    } catch {
      setError("加载文档列表失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (
        dialogRef.current &&
        !dialogRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const resp = await fetch("/api/docs", { method: "POST", body: fd });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setError(body.detail || body?.error?.message || body.error || `上传失败 (${resp.status})`);
      } else {
        await refresh();
      }
    } catch {
      setError("网络错误，上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(docId: string) {
    if (!confirm("确认删除该文档？")) return;
    setError(null);
    try {
      const resp = await fetch(`/api/docs/${docId}`, { method: "DELETE" });
      if (!resp.ok && resp.status !== 204) {
        const body = await resp.json().catch(() => ({}));
        setError(body.detail || body?.error?.message || body.error || `删除失败 (${resp.status})`);
      } else {
        await refresh();
      }
    } catch {
      setError("网络错误，删除失败");
    }
  }

  return (
    <div className="relative" ref={dialogRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-sm px-3 py-1.5 rounded-md hover:opacity-80 transition-opacity cursor-pointer"
        style={{ color: "var(--text-secondary)" }}
        aria-label="管理技术文档"
      >
        📚 技术文档
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-[420px] max-h-[70vh] overflow-y-auto rounded-lg border shadow-xl z-50"
          style={{
            background: "var(--bg-secondary)",
            borderColor: "var(--border-color)",
          }}
          role="dialog"
          aria-label="技术文档管理"
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--border-color)" }}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                技术文档库
              </h3>
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {docs.length} 份
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept={ALLOWED}
                onChange={handleUpload}
                className="hidden"
                id="doc-upload-input"
              />
              <label
                htmlFor="doc-upload-input"
                className="text-xs px-3 py-1.5 rounded-md font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ background: "var(--accent-blue)", color: "#fff" }}
              >
                {uploading ? "上传中…" : "上传文档"}
              </label>
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                支持 PDF / Excel / TXT / Markdown，≤ 20 MB
              </span>
            </div>
            {error && (
              <div className="mt-2 text-xs px-2 py-1 rounded" style={{ background: "var(--accent-red)", color: "#fff" }}>
                {error}
              </div>
            )}
          </div>

          <div className="p-2">
            {loading ? (
              <div className="p-4 text-center text-xs" style={{ color: "var(--text-secondary)" }}>
                加载中…
              </div>
            ) : docs.length === 0 ? (
              <div className="p-4 text-center text-xs" style={{ color: "var(--text-secondary)" }}>
                尚未上传任何文档
              </div>
            ) : (
              <ul className="space-y-1">
                {docs.map((d) => (
                  <li
                    key={d.doc_id}
                    className="flex items-center justify-between px-2 py-2 rounded hover:opacity-90"
                    style={{ background: "var(--bg-tertiary)" }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium truncate" style={{ color: "var(--text-primary)" }}>
                        {d.filename}
                      </div>
                      <div className="text-[10px] mt-0.5 flex items-center gap-1" style={{ color: "var(--text-secondary)" }}>
                        <span>{d.suffix} · {formatSize(d.size)} · {formatDate(d.uploaded_at)}</span>
                        {d.embedding_status && EMBED_STATUS_LABEL[d.embedding_status] && (
                          <span
                            className="px-1 rounded"
                            style={{
                              color: EMBED_STATUS_LABEL[d.embedding_status].color,
                              border: `1px solid ${EMBED_STATUS_LABEL[d.embedding_status].color}`,
                            }}
                          >
                            {EMBED_STATUS_LABEL[d.embedding_status].text}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDelete(d.doc_id)}
                      className="ml-2 text-xs px-2 py-1 rounded hover:opacity-80 cursor-pointer"
                      style={{ color: "var(--accent-red)" }}
                      aria-label={`删除 ${d.filename}`}
                    >
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

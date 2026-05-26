import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import DocManagerButton from "../DocManagerButton";

describe("DocManagerButton", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("默认仅渲染按钮，不展开面板", () => {
    render(<DocManagerButton />);
    expect(screen.getByRole("button", { name: /管理技术文档/ })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("点击按钮后展开面板并加载列表", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total: 1,
        items: [
          {
            doc_id: "abc1234567890def",
            filename: "FOTA规范.pdf",
            suffix: ".pdf",
            size: 2048,
            uploaded_at: "2026-05-25T10:00:00Z",
            chunks: 0,
          },
        ],
      }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText("FOTA规范.pdf")).toBeInTheDocument();
    });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/docs",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("空列表显示空态文案", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0, items: [] }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText(/尚未上传任何文档/)).toBeInTheDocument();
    });
  });

  it("加载失败时显示错误提示", async () => {
    mockFetch.mockRejectedValueOnce(new Error("network down"));

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText(/加载文档列表失败/)).toBeInTheDocument();
    });
  });

  it("上传按钮 label 关联到 hidden input 且 accept 包含所有支持的后缀", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0, items: [] }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText(/尚未上传任何文档/)).toBeInTheDocument();
    });

    const input = document.getElementById("doc-upload-input") as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.accept).toContain(".pdf");
    expect(input.accept).toContain(".xlsx");
    expect(input.accept).toContain(".xlsm");
    expect(input.accept).toContain(".txt");
    expect(input.accept).toContain(".md");
  });

  it("选择文件后触发 POST /api/docs 并刷新列表", async () => {
    // 1) 初始空列表
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0, items: [] }),
    });
    // 2) POST 上传成功
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, doc: { doc_id: "a".repeat(16), filename: "x.pdf" } }),
    });
    // 3) 刷新列表带上新文档
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total: 1,
        items: [
          {
            doc_id: "a".repeat(16),
            filename: "x.pdf",
            suffix: ".pdf",
            size: 1024,
            uploaded_at: "2026-05-25T10:00:00Z",
            chunks: 0,
            embedding_status: "pending",
          },
        ],
      }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText(/尚未上传任何文档/)).toBeInTheDocument();
    });

    const input = document.getElementById("doc-upload-input") as HTMLInputElement;
    const file = new File(["%PDF-1.4 fake"], "x.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText("x.pdf")).toBeInTheDocument();
    });

    // 校验 POST 调用
    const postCall = mockFetch.mock.calls.find((c) => c[1]?.method === "POST");
    expect(postCall).toBeDefined();
    expect(postCall![0]).toBe("/api/docs");
    expect((postCall![1].body as FormData).get("file")).toBe(file);

    // 校验 embedding_status 徽标渲染
    expect(screen.getByText("索引中")).toBeInTheDocument();
  });

  it("点击删除按钮（confirm 接受）后触发 DELETE 并刷新", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);

    // 1) 初始列表（1 条）
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total: 1,
        items: [
          {
            doc_id: "b".repeat(16),
            filename: "old.txt",
            suffix: ".txt",
            size: 512,
            uploaded_at: "2026-05-24T08:00:00Z",
            chunks: 0,
            embedding_status: "ok",
          },
        ],
      }),
    });
    // 2) DELETE 成功
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    // 3) 刷新列表（空）
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0, items: [] }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText("old.txt")).toBeInTheDocument();
    });
    // 状态徽标
    expect(screen.getByText("向量")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /删除 old\.txt/ }));

    await waitFor(() => {
      expect(screen.getByText(/尚未上传任何文档/)).toBeInTheDocument();
    });

    const deleteCall = mockFetch.mock.calls.find((c) => c[1]?.method === "DELETE");
    expect(deleteCall).toBeDefined();
    expect(deleteCall![0]).toBe(`/api/docs/${"b".repeat(16)}`);
  });

  it("confirm 拒绝时不发起 DELETE 请求", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total: 1,
        items: [
          {
            doc_id: "c".repeat(16),
            filename: "keep.md",
            suffix: ".md",
            size: 256,
            uploaded_at: "2026-05-23T07:00:00Z",
            chunks: 0,
          },
        ],
      }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText("keep.md")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /删除 keep\.md/ }));

    // 没有任何 DELETE 调用
    const deleteCall = mockFetch.mock.calls.find((c) => c[1]?.method === "DELETE");
    expect(deleteCall).toBeUndefined();
  });

  it("上传失败时显示后端 detail 错误", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0, items: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 415,
      json: async () => ({ detail: "magic bytes 校验失败" }),
    });

    render(<DocManagerButton />);
    fireEvent.click(screen.getByRole("button", { name: /管理技术文档/ }));

    await waitFor(() => {
      expect(screen.getByText(/尚未上传任何文档/)).toBeInTheDocument();
    });

    const input = document.getElementById("doc-upload-input") as HTMLInputElement;
    const file = new File(["plain"], "fake.pdf", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/magic bytes 校验失败/)).toBeInTheDocument();
    });
  });
});

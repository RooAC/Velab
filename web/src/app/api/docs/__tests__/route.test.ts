/**
 * /api/docs GET/POST 与 /api/docs/[docId] DELETE 路由测试
 */
import { GET, POST } from "@/app/api/docs/route";
import { DELETE } from "@/app/api/docs/[docId]/route";
import { vi, beforeEach, afterEach, describe, it, expect } from "vitest";

describe("GET /api/docs", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("auth misconfig 时返回 503 且不 fetch backend", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_SESSION_SECRET", "");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "");
    vi.stubEnv("BACKEND_API_KEY", "");

    const req = new Request("http://localhost/api/docs") as import("next/server").NextRequest;
    const res = await GET(req);

    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error.code).toBe("AUTH_NOT_CONFIGURED");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("透传后端列表响应", async () => {
    mockFetch.mockResolvedValue({
      status: 200,
      text: async () => '{"total":1,"items":[]}',
    });
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("total");
  });

  it("后端不可达时返回 502", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
    const res = await GET();
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error.code).toBe("BACKEND_UNREACHABLE");
  });
});

describe("POST /api/docs", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("无 file 字段返回 400", async () => {
    const req = {
      formData: async () => new FormData(),
    } as unknown as import("next/server").NextRequest;
    const res = await POST(req);
    expect(res.status).toBe(400);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("转发文件到后端并透传响应", async () => {
    mockFetch.mockResolvedValue({
      status: 201,
      text: async () =>
        '{"success":true,"doc":{"doc_id":"abcdef0123456789"}}',
    });
    const file = new File(["hello"], "spec.pdf", { type: "application/pdf" });
    const req = {
      formData: async () => {
        const fd = new FormData();
        fd.append("file", file);
        return fd;
      },
    } as unknown as import("next/server").NextRequest;
    const res = await POST(req);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/docs/upload"),
      expect.objectContaining({ method: "POST" })
    );
    expect(res.status).toBe(201);
  });

  it("后端不可达返回 502", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    const req = {
      formData: async () => {
        const fd = new FormData();
        fd.append("file", file);
        return fd;
      },
    } as unknown as import("next/server").NextRequest;
    const res = await POST(req);
    expect(res.status).toBe(502);
  });
});

describe("DELETE /api/docs/[docId]", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("auth misconfig 时返回 503 且不 fetch backend", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_SESSION_SECRET", "");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "");
    vi.stubEnv("BACKEND_API_KEY", "");

    const req = {} as unknown as import("next/server").NextRequest;
    const res = await DELETE(req, {
      params: Promise.resolve({ docId: "abcdef0123456789" }),
    });

    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error.code).toBe("AUTH_NOT_CONFIGURED");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("非法 docId 返回 400", async () => {
    const req = {} as unknown as import("next/server").NextRequest;
    const res = await DELETE(req, {
      params: Promise.resolve({ docId: "not-hex" }),
    });
    expect(res.status).toBe(400);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("合法 docId 透传后端 204", async () => {
    mockFetch.mockResolvedValue({ status: 204, text: async () => "" });
    const req = {} as unknown as import("next/server").NextRequest;
    const res = await DELETE(req, {
      params: Promise.resolve({ docId: "abcdef0123456789" }),
    });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/docs/abcdef0123456789"),
      expect.objectContaining({ method: "DELETE" })
    );
    expect(res.status).toBe(204);
  });

  it("后端不可达返回 502", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
    const req = {} as unknown as import("next/server").NextRequest;
    const res = await DELETE(req, {
      params: Promise.resolve({ docId: "abcdef0123456789" }),
    });
    expect(res.status).toBe(502);
  });
});

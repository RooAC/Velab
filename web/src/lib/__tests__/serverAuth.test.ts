import {
  AUTH_COOKIE_NAME,
  authCookieOptions,
  backendAuthHeaders,
  expiredAuthCookieOptions,
  hasValidSession,
  requireWebSession,
  sessionCookieValue,
  validateLoginPassword,
} from "@/lib/serverAuth";
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("serverAuth", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows requests when web auth is disabled", () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "false");
    const req = new NextRequest("http://localhost/api/chat");
    expect(hasValidSession(req)).toBe(true);
    expect(requireWebSession(req)).toBeNull();
    expect(validateLoginPassword(undefined)).toBe(true);
  });

  it("returns 503 when auth is enabled without a session secret", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    const req = new NextRequest("http://localhost/api/chat");
    const res = requireWebSession(req);
    expect(res?.status).toBe(503);
    expect(await res?.json()).toEqual({ error: "auth_not_configured" });
  });

  it("rejects missing or invalid cookies when auth is enabled", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "secret");

    const missing = new NextRequest("http://localhost/api/chat");
    expect(hasValidSession(missing)).toBe(false);
    const res = requireWebSession(missing);
    expect(res?.status).toBe(401);
    expect(await res?.json()).toEqual({ error: "unauthorized" });

    const invalid = new NextRequest("http://localhost/api/chat", {
      headers: { cookie: `${AUTH_COOKIE_NAME}=wrong` },
    });
    expect(hasValidSession(invalid)).toBe(false);
  });

  it("accepts a valid session cookie", () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_SESSION_SECRET", "session-secret");
    const req = new NextRequest("http://localhost/api/chat", {
      headers: { cookie: `${AUTH_COOKIE_NAME}=${sessionCookieValue()}` },
    });
    expect(hasValidSession(req)).toBe(true);
    expect(requireWebSession(req)).toBeNull();
  });

  it("adds backend bearer auth while preserving extra headers", () => {
    vi.stubEnv("BACKEND_API_KEY", "backend-secret");
    expect(backendAuthHeaders({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer backend-secret",
    });
  });

  it("validates login password inputs with timing-safe comparison", () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "secret");
    expect(validateLoginPassword("secret")).toBe(true);
    expect(validateLoginPassword("wrong")).toBe(false);
    expect(validateLoginPassword(123)).toBe(false);
  });

  it("sets secure cookie attributes in production", () => {
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "secret");
    vi.stubEnv("NODE_ENV", "production");
    expect(authCookieOptions()).toContain("; Secure");
    expect(expiredAuthCookieOptions()).toContain("; Secure");
  });
});

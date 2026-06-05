import { POST as LOGIN } from "@/app/api/auth/login/route";
import { POST as LOGOUT } from "@/app/api/auth/logout/route";
import { GET as STATUS } from "@/app/api/auth/status/route";
import { AUTH_COOKIE_NAME } from "@/lib/serverAuth";
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("/api/auth", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("auth disabled returns authenticated status", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "false");
    const req = new NextRequest("http://localhost/api/auth/status");
    const res = await STATUS(req);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ enabled: false, authenticated: true });
  });

  it("login rejects wrong password when auth enabled", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "secret");
    const req = new NextRequest("http://localhost/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: "wrong" }),
    });
    const res = await LOGIN(req);
    expect(res.status).toBe(401);
  });

  it("login sets httpOnly cookie with correct password", async () => {
    vi.stubEnv("WEB_AUTH_ENABLED", "true");
    vi.stubEnv("AUTH_LOGIN_PASSWORD", "secret");
    const req = new NextRequest("http://localhost/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: "secret" }),
    });
    const res = await LOGIN(req);
    expect(res.status).toBe(200);
    const cookie = res.headers.get("set-cookie") || "";
    expect(cookie).toContain(AUTH_COOKIE_NAME);
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=Lax");
  });

  it("logout expires auth cookie", async () => {
    const res = await LOGOUT();
    const cookie = res.headers.get("set-cookie") || "";
    expect(cookie).toContain(AUTH_COOKIE_NAME);
    expect(cookie).toContain("Max-Age=0");
  });
});

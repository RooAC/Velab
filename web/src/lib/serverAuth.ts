import { createHash, timingSafeEqual } from "crypto";
import { NextRequest } from "next/server";

export const AUTH_COOKIE_NAME = "velab_auth";

export function isWebAuthEnabled(): boolean {
  return (process.env.WEB_AUTH_ENABLED ?? "false").toLowerCase() === "true";
}

function sessionSecret(): string {
  return process.env.AUTH_SESSION_SECRET
    || process.env.AUTH_LOGIN_PASSWORD
    || process.env.BACKEND_API_KEY
    || "";
}

export function sessionCookieValue(): string {
  const secret = sessionSecret();
  if (!secret) return "";
  return createHash("sha256").update(`velab-session:${secret}`).digest("hex");
}

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

export function hasValidSession(request: NextRequest): boolean {
  if (!isWebAuthEnabled()) return true;
  const expected = sessionCookieValue();
  if (!expected) return false;
  const actual = request.cookies.get(AUTH_COOKIE_NAME)?.value ?? "";
  return Boolean(actual) && safeEqual(actual, expected);
}

export function requireWebSession(request: NextRequest): Response | null {
  if (!isWebAuthEnabled()) return null;
  if (!sessionCookieValue()) {
    return Response.json(
      { error: "auth_not_configured" },
      { status: 503 }
    );
  }
  if (!hasValidSession(request)) {
    return Response.json(
      { error: "unauthorized" },
      { status: 401 }
    );
  }
  return null;
}

export function backendAuthHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) };
  const key = process.env.BACKEND_API_KEY || "";
  if (key) headers.Authorization = `Bearer ${key}`;
  return headers;
}

export function validateLoginPassword(password: unknown): boolean {
  const expected = process.env.AUTH_LOGIN_PASSWORD || "";
  if (!isWebAuthEnabled()) return true;
  if (!expected || typeof password !== "string") return false;
  return safeEqual(password, expected);
}

export function authCookieOptions(): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${AUTH_COOKIE_NAME}=${sessionCookieValue()}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400${secure}`;
}

export function expiredAuthCookieOptions(): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${AUTH_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`;
}

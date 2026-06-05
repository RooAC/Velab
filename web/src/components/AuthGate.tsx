"use client";

import { FormEvent, useEffect, useState } from "react";
import type { ReactNode } from "react";

type AuthState = "loading" | "authenticated" | "anonymous";

export default function AuthGate({ children }: { children: ReactNode }) {
  const clientAuthEnabled =
    (process.env.NEXT_PUBLIC_WEB_AUTH_ENABLED ?? "false").toLowerCase() === "true";
  const [state, setState] = useState<AuthState>(
    clientAuthEnabled ? "loading" : "authenticated"
  );
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clientAuthEnabled) return;
    let alive = true;
    async function check() {
      try {
        const resp = await fetch("/api/auth/status", { cache: "no-store" });
        const body = await resp.json();
        if (alive) setState(body.authenticated ? "authenticated" : "anonymous");
      } catch {
        if (alive) setState("anonymous");
      }
    }
    check();
    return () => {
      alive = false;
    };
  }, [clientAuthEnabled]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      setError(body?.error?.message || body.detail || "密码不正确或登录未配置");
      return;
    }
    setState("authenticated");
    setPassword("");
  }

  if (state === "authenticated") return <>{children}</>;

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border p-5"
        style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
      >
        <h1 className="text-base font-semibold">Velab</h1>
        <div className="mt-4">
          <label htmlFor="auth-password" className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
            访问密码
          </label>
          <input
            id="auth-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm outline-none"
            style={{
              borderColor: "var(--border-color)",
              background: "var(--bg-primary)",
              color: "var(--text-primary)",
            }}
            autoFocus
          />
        </div>
        {error && (
          <div className="mt-3 rounded-md px-3 py-2 text-xs" style={{ background: "var(--accent-red)", color: "#fff" }}>
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={state === "loading"}
          className="mt-4 w-full rounded-md px-3 py-2 text-sm font-medium disabled:opacity-60"
          style={{ background: "var(--accent-blue)", color: "#fff" }}
        >
          {state === "loading" ? "检查中..." : "进入诊断平台"}
        </button>
      </form>
    </div>
  );
}

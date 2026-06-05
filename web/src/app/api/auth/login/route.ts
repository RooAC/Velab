import {
  authCookieOptions,
  isWebAuthEnabled,
  validateLoginPassword,
} from "@/lib/serverAuth";
import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  if (!isWebAuthEnabled()) {
    return Response.json({ authenticated: true, disabled: true });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const password = typeof body === "object" && body !== null
    ? (body as Record<string, unknown>).password
    : undefined;
  if (!validateLoginPassword(password)) {
    return Response.json({ error: "invalid_credentials" }, { status: 401 });
  }

  return Response.json(
    { authenticated: true },
    { headers: { "Set-Cookie": authCookieOptions() } }
  );
}

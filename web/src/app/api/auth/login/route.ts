import {
  authCookieOptions,
  isWebAuthEnabled,
  validateLoginPassword,
} from "@/lib/serverAuth";
import { apiError } from "@/lib/apiError";
import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  if (!isWebAuthEnabled()) {
    return Response.json({ authenticated: true, disabled: true });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return apiError("INVALID_JSON", "request body must be valid JSON", 400);
  }

  const password = typeof body === "object" && body !== null
    ? (body as Record<string, unknown>).password
    : undefined;
  if (!validateLoginPassword(password)) {
    return apiError("INVALID_CREDENTIALS", "invalid login password", 401);
  }

  return Response.json(
    { authenticated: true },
    { headers: { "Set-Cookie": authCookieOptions() } }
  );
}

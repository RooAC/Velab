import { NextRequest } from "next/server";
import { apiError, backendUnreachable } from "@/lib/apiError";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  try {
    const response = await fetch(`${BACKEND_URL}/api/docs`, {
      method: "GET",
      cache: "no-store",
      headers: backendAuthHeaders(),
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return backendUnreachable();
  }
}

export async function POST(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const formData = await request.formData();
  const file = formData.get("file");
  if (!file) {
    return apiError("MISSING_FILE", "缺少 file 字段", 400);
  }

  const upstream = new FormData();
  upstream.append("file", file);

  try {
    const response = await fetch(`${BACKEND_URL}/api/docs/upload`, {
      method: "POST",
      body: upstream,
      headers: backendAuthHeaders(),
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return backendUnreachable();
  }
}

import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";
import { backendUnreachable } from "@/lib/apiError";
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  try {
    const response = await fetch(`${BACKEND_URL}/api/sessions`, {
      method: "GET",
      headers: backendAuthHeaders(),
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch {
    return backendUnreachable();
  }
}

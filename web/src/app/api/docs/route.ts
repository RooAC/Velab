import { NextRequest } from "next/server";
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
    return new Response(
      JSON.stringify({ total: 0, items: [], error: "backend_unreachable" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}

export async function POST(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const formData = await request.formData();
  const file = formData.get("file");
  if (!file) {
    return new Response(
      JSON.stringify({ detail: "缺少 file 字段" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
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
    return new Response(
      JSON.stringify({ detail: "后端不可达" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}

import { NextRequest } from "next/server";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const formData = await request.formData();

  // log_pipeline expects multipart with field name "file"; case_id is no longer used.
  const upstream = new FormData();
  const file = formData.get("file");
  if (!file) {
    return Response.json({ detail: "缺少 file 字段" }, { status: 400 });
  }
  upstream.append("file", file);

  let response: globalThis.Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/bundles`, {
      method: "POST",
      body: upstream,
      headers: backendAuthHeaders(),
    });
  } catch {
    return Response.json({ detail: "后端不可达" }, { status: 502 });
  }

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}

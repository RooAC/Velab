import { NextRequest } from "next/server";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const DOC_ID_RE = /^[0-9a-f]{16}$/;

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ docId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { docId } = await params;
  if (!DOC_ID_RE.test(docId)) {
    return new Response(
      JSON.stringify({ detail: "非法 docId" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  try {
    const response = await fetch(`${BACKEND_URL}/api/docs/${docId}`, {
      method: "DELETE",
      headers: backendAuthHeaders(),
    });
    if (response.status === 204) {
      return new Response(null, { status: 204 });
    }
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

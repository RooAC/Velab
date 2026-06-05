import { NextRequest } from "next/server";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";
import { invalidIdResponse, UUID_RE } from "@/lib/routeValidation";
import { backendUnreachable } from "@/lib/apiError";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { sessionId } = await params;
  if (!UUID_RE.test(sessionId)) return invalidIdResponse("sessionId");
  try {
    const response = await fetch(`${BACKEND_URL}/api/sessions/${sessionId}`, {
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

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { sessionId } = await params;
  if (!UUID_RE.test(sessionId)) return invalidIdResponse("sessionId");
  const body = await request.text();
  try {
    const response = await fetch(`${BACKEND_URL}/api/sessions/${sessionId}`, {
      method: "PUT",
      headers: backendAuthHeaders({ "Content-Type": "application/json" }),
      body,
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

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { sessionId } = await params;
  if (!UUID_RE.test(sessionId)) return invalidIdResponse("sessionId");
  try {
    const response = await fetch(`${BACKEND_URL}/api/sessions/${sessionId}`, {
      method: "DELETE",
      headers: backendAuthHeaders(),
    });
    return new Response(null, { status: response.status });
  } catch {
    return backendUnreachable();
  }
}

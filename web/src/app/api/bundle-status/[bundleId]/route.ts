import { NextRequest } from "next/server";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";
import { invalidIdResponse, UUID_RE } from "@/lib/routeValidation";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ bundleId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { bundleId } = await params;
  if (!UUID_RE.test(bundleId)) return invalidIdResponse("bundleId");
  try {
    const response = await fetch(`${BACKEND_URL}/api/bundles/${bundleId}`, {
      method: "GET",
      headers: backendAuthHeaders(),
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json({ error: "backend_unreachable" }, { status: 502 });
  }
}

import { NextRequest } from "next/server";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";
import { invalidIdResponse, UUID_RE } from "@/lib/routeValidation";
import { backendUnreachable } from "@/lib/apiError";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ bundleId: string }> }
) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  const { bundleId } = await params;
  if (!UUID_RE.test(bundleId)) return invalidIdResponse("bundleId");
  const query = request.nextUrl.searchParams.toString();
  const upstreamUrl = `${BACKEND_URL}/api/bundles/${bundleId}/logs${query ? `?${query}` : ""}`;
  let response: globalThis.Response;
  try {
    response = await fetch(upstreamUrl, {
      method: "GET",
      headers: backendAuthHeaders(),
    });
  } catch {
    return backendUnreachable();
  }
  const text = await response.text();

  return new Response(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/x-ndjson; charset=utf-8",
      "X-Truncated": response.headers.get("x-truncated") || "false",
      "X-Estimated-Lines": response.headers.get("x-estimated-lines") || "0",
    },
  });
}

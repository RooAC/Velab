/**
 * FOTA 诊断平台 — Next.js API 路由（聊天代理）
 *
 * 接收前端聊天请求，转发到 FastAPI 后端，并流式透传 SSE 响应。
 */

import { NextRequest } from "next/server";
import { apiError, backendUnreachable } from "@/lib/apiError";
import { UUID_RE } from "@/lib/routeValidation";
import { backendAuthHeaders, requireWebSession } from "@/lib/serverAuth";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export const maxDuration = 120;

export async function POST(request: NextRequest) {
  const authError = requireWebSession(request);
  if (authError) return authError;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return apiError("INVALID_JSON", "request body must be valid JSON", 400);
  }

  if (typeof body !== "object" || body === null) {
    return apiError("INVALID_BODY", "request body must be an object", 400);
  }

  const { message, scenarioId, history, bundleId } = body as Record<string, unknown>;
  if (typeof message !== "string" || message.length === 0 || message.length > 10000) {
    return apiError(
      "INVALID_MESSAGE",
      "message must be a non-empty string (max 10000 chars)",
      400
    );
  }
  if (scenarioId !== undefined && typeof scenarioId !== "string") {
    return apiError("INVALID_SCENARIO_ID", "scenarioId must be a string", 400);
  }
  if (history !== undefined && !Array.isArray(history)) {
    return apiError("INVALID_HISTORY", "history must be an array", 400);
  }
  if (bundleId !== undefined) {
    if (typeof bundleId !== "string" || bundleId.length > 36) {
      return apiError("INVALID_BUNDLE_ID", "bundleId must be a valid UUID string", 400);
    }
    if (!UUID_RE.test(bundleId)) {
      return apiError("INVALID_BUNDLE_ID", "bundleId must be a valid UUID", 400);
    }
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: backendAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!backendResponse.ok) {
      return apiError("BACKEND_ERROR", "backend chat request failed", backendResponse.status);
    }

    const stream = backendResponse.body;
    if (!stream) {
      return apiError("EMPTY_BACKEND_RESPONSE", "backend response body is empty", 502);
    }

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === "AbortError") {
      return apiError("BACKEND_TIMEOUT", "backend chat request timed out", 504);
    }
    return backendUnreachable();
  }
}

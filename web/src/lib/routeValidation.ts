import { apiError } from "@/lib/apiError";

export const UUID_RE = /^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

export function invalidIdResponse(field: string): Response {
  return apiError("INVALID_ID", `${field} must be a valid UUID`, 400, { field });
}

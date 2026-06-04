export const UUID_RE = /^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

export function invalidIdResponse(field: string): Response {
  return Response.json(
    { error: `${field} must be a valid UUID` },
    { status: 400 }
  );
}

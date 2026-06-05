export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
};

export function apiError(
  code: string,
  message: string,
  status: number,
  details?: unknown
): Response {
  const body: ApiErrorBody = {
    error: { code, message },
  };
  if (details !== undefined) body.error.details = details;
  return Response.json(body, { status });
}

export function backendUnreachable(): Response {
  return apiError("BACKEND_UNREACHABLE", "backend service is unreachable", 502);
}

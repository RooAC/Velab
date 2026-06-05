import { hasValidSession, isWebAuthEnabled } from "@/lib/serverAuth";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return Response.json({
    enabled: isWebAuthEnabled(),
    authenticated: hasValidSession(request),
  });
}

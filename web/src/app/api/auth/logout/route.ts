import { expiredAuthCookieOptions } from "@/lib/serverAuth";

export async function POST() {
  return Response.json(
    { authenticated: false },
    { headers: { "Set-Cookie": expiredAuthCookieOptions() } }
  );
}

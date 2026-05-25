import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.text();
  try {
    const response = await fetch(`${BACKEND_URL}/api/sessions/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch (err) {
    // 后端不可达 / 网络错误时返回 502，避免前端将未定义错误作为标题展示
    console.error("session-title proxy failed:", err);
    return new Response(
      JSON.stringify({ title: "新会话", error: "backend_unreachable" }),
      { status: 502, headers: { "Content-Type": "application/json; charset=utf-8" } }
    );
  }
}

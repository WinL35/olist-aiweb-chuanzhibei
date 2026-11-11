import { PY_API_BASE } from "@/lib/api";

/**
 * 对话流式转发（Route Handler）
 *
 * 浏览器 → 本接口 → FastAPI /api/llm/chat/stream → SSE 原样回传。
 *
 * 为什么不直接让浏览器打后端：Next 的 rewrites 属于代理层，可能对响应做缓冲，
 * SSE 事件会被攒包；这里手动透传 ReadableStream，逐块下发，
 * 并显式关掉各级缓存与压缩缓冲。
 *
 * 运行在 Node 运行时（非 Edge），因为要访问内网 FastAPI。
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${PY_API_BASE}/api/llm/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body,
      cache: "no-store",
      // 连接到 FastAPI 失败时尽快失败，不要让前端干等
      signal: AbortSignal.timeout(120_000),
    });
  } catch (e) {
    return new Response(
      `event: error\ndata: ${JSON.stringify({
        message: `无法连接后端服务（${PY_API_BASE}）：${e instanceof Error ? e.message : String(e)}`,
      })}\n\n`,
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" },
      },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(
      `event: error\ndata: ${JSON.stringify({
        message: `后端返回 HTTP ${upstream.status}`,
      })}\n\n`,
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" },
      },
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

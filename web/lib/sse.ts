/**
 * SSE（Server-Sent Events）解析
 *
 * 为什么不用 EventSource：
 *   EventSource 只支持 GET，而后端 /api/llm/chat/stream 需要 POST 提交
 *   问题、模式与多轮历史。因此用 fetch + ReadableStream 手动解析。
 */

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface StreamHandlers {
  onStage?: (d: StageEvent) => void;
  onStep?: (d: StepEvent) => void;
  onDelta?: (text: string) => void;
  onResult?: (data: Record<string, unknown>) => void;
  onError?: (message: string) => void;
}

export interface StageEvent {
  stage: string;
  label: string;
  done?: boolean;
  tool?: string;
  args?: Record<string, unknown>;
  count?: number;
  detail?: { id: string; topic: string }[];
}

export interface StepEvent {
  step: number;
  tool: string;
  args?: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
  elapsed_ms: number;
  preview?: string;
}

/** 逐块解析 SSE 帧 */
export async function* readSse(res: Response): AsyncGenerator<SseEvent> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // 一个事件以空行结束，兼容 \r\n
      let idx: number;
      while ((idx = buf.search(/\r?\n\r?\n/)) >= 0) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + (buf[idx] === "\r" ? 4 : 2));

        let event = "message";
        let dataLine = "";
        for (const line of raw.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
        }
        if (!dataLine) continue;

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(dataLine) as Record<string, unknown>;
        } catch {
          continue; // 半截帧，跳过
        }
        yield { event, data };
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * 发起一次流式对话，把各类事件分发给对应回调。
 * 返回的 promise 在流结束时 resolve，异常统一转成 onError。
 */
export async function streamChat(
  payload: { question: string; mode: string; history: { role: string; content: string }[] },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
      signal,
    });

    if (!res.ok || !res.headers.get("content-type")?.includes("text/event-stream")) {
      // 后端未启动或网关拦截：尽量给出可读原因
      const text = await res.text().catch(() => "");
      handlers.onError?.(text.slice(0, 200) || `接口返回 HTTP ${res.status}`);
      return;
    }

    for await (const { event, data } of readSse(res)) {
      switch (event) {
        case "stage":
          handlers.onStage?.(data as unknown as StageEvent);
          break;
        case "step":
          handlers.onStep?.(data as unknown as StepEvent);
          break;
        case "delta":
          handlers.onDelta?.(String(data.text ?? ""));
          break;
        case "result":
          handlers.onResult?.(data.data as Record<string, unknown>);
          break;
        case "error":
          handlers.onError?.(String(data.message ?? "未知错误"));
          break;
        default:
          break;
      }
    }
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") return;
    handlers.onError?.(e instanceof Error ? e.message : String(e));
  }
}

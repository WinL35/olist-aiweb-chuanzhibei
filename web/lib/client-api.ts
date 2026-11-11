/**
 * 浏览器侧取数
 *
 * 与 serverGet 的差别：
 *   1. 走同源相对路径 /api/*，由 next.config.mjs 的 rewrites 转发到 FastAPI，
 *      浏览器端不产生跨域预检；
 *   2. 不缓存、不预取，配合交互式筛选（切换分群口径、切换品类）实时刷新。
 */
export class ClientApiError extends Error {
  constructor(
    message: string,
    readonly path: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ClientApiError";
  }
}

export async function clientGet<T>(path: string, timeoutMs = 20000): Promise<T> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(`/api${path}`, {
      cache: "no-store",
      signal: ac.signal,
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new ClientApiError(`接口返回 HTTP ${res.status}`, path, res.status);

    let json: T & { code?: number; message?: string };
    try {
      json = await res.json();
    } catch {
      throw new ClientApiError("接口返回的不是 JSON", path, res.status);
    }
    if (json && typeof json.code === "number" && json.code !== 0) {
      throw new ClientApiError(json.message || `接口错误 code=${json.code}`, path);
    }
    return json;
  } catch (e) {
    if (e instanceof ClientApiError) throw e;
    if (e instanceof Error && e.name === "AbortError") {
      throw new ClientApiError(`请求超时（${timeoutMs}ms）`, path);
    }
    throw new ClientApiError(e instanceof Error ? e.message : String(e), path);
  } finally {
    clearTimeout(timer);
  }
}

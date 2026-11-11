import type {
  CategoryGmv,
  DashboardSummary,
  ExperimentMedian,
  FunnelStage,
  HourPoint,
  ListPayload,
  ModelComparison,
  PaymentSlice,
  PredictionCategory,
  PredictionResult,
  PricingByCategory,
  PricingRow,
  PricingSkipped,
  PricingSummary,
  RegionGmv,
  RepurchaseSlice,
  ReviewBucket,
  StatusSlice,
  SummaryStat,
  TopProduct,
  TrendPoint,
  WeekdayPoint,
  CategoryRecommendation,
  SelectionWindow,
  StrategyCompare,
  SelectionSummary,
  SelectionProduct,
  RfmSegment,
  RfmPoint,
} from "@/types/api";

/**
 * 服务端取数基址。
 *
 * 浏览器端统一请求同源 /api/*（由 next.config.mjs 的 rewrites 转发），
 * 而 Server Component 在 Node 进程内运行，没有"相对地址"的概念，
 * 必须用绝对地址直连 FastAPI。
 */
export const PY_API_BASE = process.env.PY_API_BASE || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly path: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 带超时的 GET，服务端使用。
 * cache: "no-store" —— 经营数据是实时查询结果，缓存会导致看板数字滞后。
 */
export async function serverGet<T>(path: string, timeoutMs = 15000): Promise<T> {
  const url = `${PY_API_BASE}/api${path}`;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(url, { cache: "no-store", signal: ac.signal });
    if (!res.ok) {
      throw new ApiError(`接口返回 HTTP ${res.status}`, path, res.status);
    }
    const json = (await res.json()) as T & { code?: number; message?: string };
    // LLM 接口用 {code,message,data} 包装，业务错误 HTTP 仍是 200
    if (json && typeof json.code === "number" && json.code !== 0) {
      throw new ApiError(json.message || `接口错误 code=${json.code}`, path);
    }
    return json;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof Error && e.name === "AbortError") {
      throw new ApiError(`请求超时（${timeoutMs}ms）`, path);
    }
    throw new ApiError(e instanceof Error ? e.message : String(e), path);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 并发取数：任一失败不拖垮整页，返回 { ok, data } 便于页面按块降级。
 * 看板类页面往往并发 4~10 个接口，个体失败只应让对应卡片显示占位，
 * 而不是白屏。
 */
export async function settled<T>(p: Promise<T>): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  try {
    return { ok: true, data: await p };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

/* ================= 具体接口封装 ================= */

export const api = {
  /* 经营看板 */
  dashboardSummary: () => serverGet<DashboardSummary>("/dashboard/summary"),
  dashboardTrend: () => serverGet<ListPayload<TrendPoint>>("/dashboard/trend"),
  dashboardCategory: () => serverGet<ListPayload<CategoryGmv>>("/dashboard/category"),
  dashboardRegion: () => serverGet<ListPayload<RegionGmv>>("/dashboard/region"),
  dashboardPayment: () => serverGet<ListPayload<PaymentSlice>>("/dashboard/payment"),
  dashboardHour: () => serverGet<ListPayload<HourPoint>>("/dashboard/hour"),
  dashboardWeekday: () => serverGet<ListPayload<WeekdayPoint>>("/dashboard/weekday"),
  dashboardOrderStatus: () => serverGet<ListPayload<StatusSlice>>("/dashboard/order_status"),
  dashboardReview: () => serverGet<ListPayload<ReviewBucket>>("/dashboard/review"),
  dashboardTopProducts: () => serverGet<ListPayload<TopProduct>>("/dashboard/top_products"),

  /* 用户分群 */
  rfmSegments: (scheme: string) => serverGet<ListPayload<RfmSegment>>(`/rfm/segments?scheme=${scheme}`),
  rfmScatter: (scheme: string) => serverGet<ListPayload<RfmPoint>>(`/rfm/scatter?scheme=${scheme}`),

  /* 转化分析 */
  conversionFunnel: () => serverGet<ListPayload<FunnelStage>>("/conversion/funnel"),
  conversionRepurchase: () => serverGet<ListPayload<RepurchaseSlice>>("/conversion/repurchase"),

  /* 销量预测 */
  predictionCategories: () => serverGet<ListPayload<PredictionCategory>>("/prediction/categories"),
  predictionSales: (category: string, weeks: number) =>
    serverGet<PredictionResult>(
      `/prediction/sales?category=${encodeURIComponent(category)}&weeks=${weeks}`,
    ),

  /* 选品建议 */
  recommendProducts: () =>
    serverGet<ListPayload<CategoryRecommendation> & { window?: SelectionWindow }>(
      "/recommendation/products",
    ),
  recommendStrategyCompare: () => serverGet<StrategyCompare>("/recommendation/strategy_compare"),
  selectionSummary: () => serverGet<SelectionSummary>("/selection/summary"),
  selectionProducts: (limit = 10) =>
    serverGet<ListPayload<SelectionProduct>>(`/selection/products?limit=${limit}`),

  /* 定价建议 */
  pricingSummary: () => serverGet<PricingSummary>("/pricing/summary"),
  pricingSuggestions: (limit = 50) =>
    serverGet<ListPayload<PricingRow>>(`/pricing/suggestions?limit=${limit}`),
  pricingByCategory: () => serverGet<ListPayload<PricingByCategory>>("/pricing/by-category"),
  pricingSkipped: () => serverGet<ListPayload<PricingSkipped>>("/pricing/skipped"),

  /* 模型实验 */
  experimentCompare: () => serverGet<ListPayload<ModelComparison>>("/experiment/compare"),
  experimentMedian: () => serverGet<ExperimentMedian>("/experiment/median"),
  experimentSummaryStats: () => serverGet<ListPayload<SummaryStat>>("/experiment/summary-stats"),
};

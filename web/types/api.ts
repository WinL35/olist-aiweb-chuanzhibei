/**
 * 后端接口类型定义
 *
 * 约定：FastAPI 侧存在两种返回形态，这里如实建模，不做统一包装——
 *   1. 业务接口（dashboard / pricing / experiment 等）直接返回数据本体；
 *   2. LLM 接口（/api/llm/*）统一返回 { code, message, data }。
 * 把差异显式写在类型里，比在运行时猜更有价值。
 */

/** LLM 统一响应包装 */
export interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

/** 带 data 字段的分页/列表型返回 */
export interface ListPayload<T> {
  data: T[];
}

/* ========== 经营看板 ========== */

export interface DashboardSummary {
  order_cnt: number;
  customer_cnt: number;
  product_cnt: number;
  category_cnt: number;
  gmv: number;
  avg_order_value: number;
  avg_per_customer: number;
  delivery_rate: number;
  conversion_rate: number;
  repurchase_rate: number;
  repurchase_customers: number;
  avg_review: number;
  avg_delivery_days: number;
}

export interface TrendPoint {
  t: string;
  gmv: number | string;
  orders: number;
}

export interface CategoryGmv {
  category: string;
  gmv: number | string;
}

export interface RegionGmv {
  state: string;
  gmv: number | string;
}

export interface PaymentSlice {
  type: string;
  amount: number | string;
}

export interface HourPoint {
  hour: number;
  orders: number;
  gmv: number | string;
}

export interface WeekdayPoint {
  name: string;
  orders: number;
}

export interface StatusSlice {
  status: string;
  cnt: number;
}

export interface ReviewBucket {
  score: number;
  cnt: number;
}

export interface TopProduct {
  product_id: string;
  category: string;
  gmv: number | string;
  items: number;
}

/* ========== RFM 分群 ========== */

export type RfmScheme = "rule8" | "kmeans4";

export interface RfmSegment {
  segment: string;
  cnt: number;
  pct: number;
  avg_recency: number;
  avg_frequency: number;
  avg_monetary: number;
  total_monetary: number;
}

export interface RfmPoint {
  segment: string;
  recency: number;
  frequency: number;
  monetary: number;
}

/* ========== 转化分析 ========== */

export interface FunnelStage {
  stage: string;
  cnt: number;
}

export interface RepurchaseSlice {
  type: string;
  customers: number;
  monetary: number | string;
  customer_pct: number;
}

/* ========== 销量预测 ========== */

export interface PredictionCategory {
  category: string;
  gmv: number | string;
}

export interface PredictionMetrics {
  model: string;
  baseline_model: string;
  mape_model: number;
  mape_baseline: number;
  improvement_pct: number;
  holdout_weeks: number;
}

export interface HistoryPoint {
  week: string;
  qty: number;
}

export interface ForecastPoint {
  week: string;
  forecast: number | string;
  lower: number | string;
  upper: number | string;
  baseline: number | string;
}

export interface PredictionResult {
  metrics?: PredictionMetrics;
  history?: HistoryPoint[];
  future?: ForecastPoint[];
}

/* ========== 选品建议 ========== */

export interface CategoryRecommendation {
  rank: number;
  category: string;
  recent_gmv: number;
  prev_gmv: number;
  growth_rate: number;
  recent_qty: number;
  avg_price: number;
  score: number;
}

export interface SelectionWindow {
  recent: string;
  end: string;
}

export interface StrategySide {
  name: string;
  hit_rate: number;
  recommended: { category: string; train_gmv: number; growth: number }[];
}

export interface StrategyCompare {
  strategy_A?: StrategySide;
  strategy_B?: StrategySide;
  conclusion?: string;
  validation_window?: string;
  top20_count?: number;
}

export interface SelectionSummary {
  total: number;
  by_type?: { selection_type: string; cnt: number }[];
}

export interface SelectionProduct {
  rank: number;
  product_id: string;
  category: string;
  gmv_recent: number | string;
  growth_pct: number | null;
  avg_price: number | string;
  score_total: number;
  recommendation: string;
}

/* ========== 定价建议 ========== */

export interface PricingSummary {
  total: number;
  has_suggestion: number;
  no_suggestion: number;
  confidence: Record<string, number> & { 高?: number };
  avg_expected_revenue_change_pct: number;
}

export interface PricingRow {
  product_id: string;
  category: string;
  confidence: string;
  current_price: number;
  suggested_price: number;
  has_suggestion: boolean;
  price_change_pct: number;
  expected_revenue_change_pct: number;
  elasticity: number | null;
  elasticity_source?: string | null;
  note?: string | null;
}

export interface PricingByCategory {
  category: string;
  product_cnt: number;
  has_suggestion: number;
  avg_current_price: number;
  avg_change_pct: number;
}

export interface PricingSkipped {
  product_id: string;
  category: string;
  months_observed: number;
  price_cv_pct: number;
}

/* ========== 模型实验 ========== */

export interface ModelComparison {
  model: string;
  is_baseline: boolean;
  category_cnt: number;
  avg_mape: number;
  avg_wape: number;
  avg_mae: number;
  avg_rmse: number;
  avg_mape_improve_pct: number;
}

export interface ExperimentMedian {
  median?: { main_model_mape?: number; baseline_mape?: number };
  main_model_better_categories?: { better: number; total: number; pct: number };
  note?: string;
}

export interface SummaryStat {
  name: string;
  value_text: string;
}

/* ========== 垂直大模型对话 ========== */

export type ChatMode = "full" | "no_tools" | "no_rag" | "baseline";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface TraceStep {
  step: number;
  action: "tool" | string;
  tool?: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  error?: string;
  content_chars?: number;
}

export interface Citation {
  指标: string;
  来源: string;
  值: string | number;
}

export interface RuleApplied {
  id: string;
  topic: string;
}

export interface Snippet {
  source: string;
  heading: string;
  score?: number;
}

/** ECharts option 由后端确定性组装后下发，前端只负责渲染 */
export type ChartOption = Record<string, unknown>;

export interface ChatData {
  answer: string;
  charts?: ChartOption[];
  mode?: ChatMode;
  confidence?: number;
  elapsed_ms?: number;
  provider?: string;
  model?: string;
  refused?: boolean;
  datasource?: string;
  trace?: TraceStep[];
  tools_used?: string[];
  citations?: Citation[];
  rules_applied?: RuleApplied[];
  snippets?: Snippet[];
  policy_hits?: string[];
  limitations?: string[];
}

export interface LlmHealth {
  config?: { provider?: string; model?: string; [k: string]: unknown };
  knowledge?: { rules?: number; rag?: { chunks?: number } };
  tools?: { tools_registered?: number; tools?: number; datasource?: string };
}

export type ExampleGroups = Record<string, string[]>;

export interface FeedbackResult {
  id: number;
  ruleset_version: string;
}

export interface EvalRow {
  mode: string;
  A?: number;
  B?: number;
  C?: number;
  D?: number;
  acc: number;
}

export interface EvalResult {
  summary: EvalRow[];
  simulated?: boolean;
}

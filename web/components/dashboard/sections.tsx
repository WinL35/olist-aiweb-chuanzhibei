import { api, settled } from "@/lib/api";
import { fmt, money, pct } from "@/lib/format";
import { ErrorNote, KpiCard, Pill, PillRow, Table, Td } from "@/components/ui/primitives";
import {
  CategoryBar,
  HourBar,
  PaymentPie,
  RegionBar,
  ReviewBar,
  StatusPie,
  TrendChart,
  WeekdayBar,
} from "@/components/charts/dashboard-charts";

/**
 * 看板的各个数据块
 *
 * 每个块都是一个独立的 async Server Component，由页面用 <Suspense> 包裹。
 * 好处：
 *   1. 快接口先到先刷，不必等最慢的那个；
 *   2. 单个块失败只影响自己（ErrorNote 降级），不牵连整页；
 *   3. 每块职责单一，改一个不影响其它。
 */

export async function KpiSection() {
  const r = await settled(api.dashboardSummary());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/summary" />;
  const s = r.data;

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
        <KpiCard label="GMV 商品总额" value={money(s.gmv)} tone="accent" />
        <KpiCard label="客单价（每单）" value={money(s.avg_order_value)} tone="amber" />
        <KpiCard label="订单数" value={fmt(s.order_cnt)} />
        <KpiCard label="客户数（去重）" value={fmt(s.customer_cnt)} />
        <KpiCard label="送达率" value={pct(s.delivery_rate)} tone="mint" />
        <KpiCard label="复购率" value={pct(s.repurchase_rate)} tone="amber" />
        <KpiCard label="支付转化率" value={pct(s.conversion_rate)} tone="accent" />
      </div>
      <div className="mt-3">
        <PillRow>
          <Pill label="商品数" value={fmt(s.product_cnt)} />
          <Pill label="品类数" value={fmt(s.category_cnt)} />
          <Pill label="平均评分" value={fmt(s.avg_review, 2)} />
          <Pill label="平均物流时效" value={`${fmt(s.avg_delivery_days, 1)} 天`} />
          <Pill label="复购客户" value={fmt(s.repurchase_customers)} />
          <Pill label="人均消费" value={money(s.avg_per_customer)} />
        </PillRow>
      </div>
    </>
  );
}

export async function TrendSection() {
  const r = await settled(api.dashboardTrend());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/trend" />;
  return <TrendChart data={r.data.data} />;
}

export async function PaymentSection() {
  const r = await settled(api.dashboardPayment());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/payment" />;
  return <PaymentPie data={r.data.data} />;
}

export async function CategorySection() {
  const r = await settled(api.dashboardCategory());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/category" />;
  return <CategoryBar data={r.data.data} />;
}

export async function RegionSection() {
  const r = await settled(api.dashboardRegion());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/region" />;
  return <RegionBar data={r.data.data} />;
}

export async function StatusSection() {
  const r = await settled(api.dashboardOrderStatus());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/order_status" />;
  return <StatusPie data={r.data.data} />;
}

export async function HourSection() {
  const r = await settled(api.dashboardHour());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/hour" />;
  return <HourBar data={r.data.data} />;
}

export async function WeekdaySection() {
  const r = await settled(api.dashboardWeekday());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/weekday" />;
  return <WeekdayBar data={r.data.data} />;
}

export async function ReviewSection() {
  const r = await settled(api.dashboardReview());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/review" />;
  return <ReviewBar data={r.data.data} />;
}

export async function TopProductsSection() {
  const r = await settled(api.dashboardTopProducts());
  if (!r.ok) return <ErrorNote message={r.error} path="/dashboard/top_products" />;
  return (
    <Table head={["商品 ID", "品类", "GMV", "件数"]}>
      {r.data.data.map((p) => (
        <tr key={p.product_id} className="transition-colors hover:bg-surface2/40">
          <Td muted className="font-mono text-[11px]">
            {p.product_id.slice(0, 10)}…
          </Td>
          <Td>{p.category}</Td>
          <Td num>{money(p.gmv)}</Td>
          <Td num>{fmt(p.items)}</Td>
        </tr>
      ))}
    </Table>
  );
}

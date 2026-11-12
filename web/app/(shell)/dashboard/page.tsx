import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHeader, Panel } from "@/components/ui/primitives";
import { KpiSkeleton, Skeleton } from "@/components/ui/skeleton";
import {
  CategorySection,
  HourSection,
  KpiSection,
  PaymentSection,
  RegionSection,
  ReviewSection,
  StatusSection,
  TopProductsSection,
  TrendSection,
  WeekdaySection,
} from "@/components/dashboard/sections";

export const metadata: Metadata = { title: "经营看板" };

/**
 * 经营看板 —— Server Component + Suspense 流式渲染
 *
 * 页头与所有图表外框先随首字节下发，各数据块独立取数、谁先到谁先刷。
 * 效果：用户在第 200ms 就能看到完整页面骨架和已返回的指标，
 * 而不是对着白屏等最慢的那个接口（10 个接口里最慢的约 2.8s）。
 */
export default function DashboardPage() {
  return (
    <div className="min-w-0 px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="经营看板" desc="巴西 Olist 电商数据集全量概览" />

      <Suspense
        fallback={
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => (
              <KpiSkeleton key={i} />
            ))}
          </div>
        }
      >
        <KpiSection />
      </Suspense>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="GMV 与订单趋势（月）">
          <Suspense fallback={<Skeleton height={320} />}>
            <TrendSection />
          </Suspense>
        </Panel>
        <Panel title="支付方式分布">
          <Suspense fallback={<Skeleton height={320} />}>
            <PaymentSection />
          </Suspense>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <Panel title="品类 GMV Top15">
          <Suspense fallback={<Skeleton height={300} />}>
            <CategorySection />
          </Suspense>
        </Panel>
        <Panel title="各州销售额 Top12">
          <Suspense fallback={<Skeleton height={300} />}>
            <RegionSection />
          </Suspense>
        </Panel>
        <Panel title="订单状态分布" className="lg:col-span-2 xl:col-span-1">
          <Suspense fallback={<Skeleton height={300} />}>
            <StatusSection />
          </Suspense>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="下单时段分布">
          <Suspense fallback={<Skeleton height={260} />}>
            <HourSection />
          </Suspense>
        </Panel>
        <Panel title="下单星期分布">
          <Suspense fallback={<Skeleton height={260} />}>
            <WeekdaySection />
          </Suspense>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="评价星级分布">
          <Suspense fallback={<Skeleton height={260} />}>
            <ReviewSection />
          </Suspense>
        </Panel>
        <Panel title="热销商品 Top10">
          <Suspense fallback={<Skeleton height={260} />}>
            <TopProductsSection />
          </Suspense>
        </Panel>
      </div>
    </div>
  );
}

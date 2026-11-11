/**
 * 骨架屏
 *
 * 配合 <Suspense> 使用：慢数据块先用骨架占位，其余部分照常到达。
 * 这样首字节时间只取决于最快的接口，而不是最慢的那个。
 */
export function Skeleton({
  height = 320,
  className = "",
}: {
  height?: number;
  className?: string;
}) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-surface2/30 ${className}`}
      style={{ height }}
      aria-hidden
    />
  );
}

/** KPI 卡骨架 */
export function KpiSkeleton() {
  return (
    <div className="card p-4">
      <div className="h-2.5 w-16 animate-pulse rounded bg-surface2/50" />
      <div className="mt-3 h-5 w-24 animate-pulse rounded bg-surface2/50" />
    </div>
  );
}

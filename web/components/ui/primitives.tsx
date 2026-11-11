import type { ReactNode } from "react";

/* ============ 面板 ============ */

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card-star p-4 sm:p-5 ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <h3 className="truncate text-[13px] font-semibold text-fg">{title}</h3>
            )}
            {subtitle && (
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{subtitle}</p>
            )}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/* ============ KPI 卡 ============ */

const TONE: Record<string, string> = {
  accent: "text-accent",
  mint: "text-mint",
  amber: "text-amber",
  coral: "text-coral",
  normal: "text-fg",
};

export function KpiCard({
  label,
  value,
  tone = "normal",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: keyof typeof TONE;
  hint?: ReactNode;
}) {
  return (
    <div className="card-star group min-w-0 p-4 transition-colors hover:border-[#35507a]">
      <div className="truncate text-[11.5px] tracking-wide text-muted">{label}</div>
      <div
        className={`tnum mt-2 whitespace-nowrap text-[17px] font-bold leading-none sm:text-[21px] xl:text-[22px] ${TONE[tone]}`}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-[11px] text-muted/80">{hint}</div>}
    </div>
  );
}

/* ============ 指标胶囊 ============ */

export function Pill({
  label,
  value,
  tone,
}: {
  label: ReactNode;
  value?: ReactNode;
  tone?: "mint" | "amber" | "coral" | "accent";
}) {
  const toneClass =
    tone === "mint"
      ? "text-mint"
      : tone === "amber"
        ? "text-amber"
        : tone === "coral"
          ? "text-coral"
          : tone === "accent"
            ? "text-accent"
            : "text-fg";
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-full border border-line bg-surface2/60 px-3 py-1.5 text-[11.5px] text-muted">
      {label}
      {value !== undefined && (
        <b className={`tnum font-semibold ${toneClass}`}>{value}</b>
      )}
    </span>
  );
}

export function PillRow({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}

/* ============ 涨跌标签 ============ */

export function Tag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "up" | "down" | "neutral";
}) {
  const cls =
    tone === "up"
      ? "bg-mint/10 text-mint border-mint/30"
      : tone === "down"
        ? "bg-coral/10 text-coral border-coral/30"
        : "bg-surface2 text-muted border-line";
  return (
    <span
      className={`tnum inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${cls} border`}
    >
      {children}
    </span>
  );
}

/* ============ 空 / 错误状态 ============ */

export function EmptyState({
  children = "暂无数据",
  tone = "muted",
}: {
  children?: ReactNode;
  tone?: "muted" | "coral" | "amber";
}) {
  const cls =
    tone === "coral" ? "text-coral" : tone === "amber" ? "text-amber" : "text-muted";
  return <div className={`px-1 py-6 text-center text-[12px] ${cls}`}>{children}</div>;
}

/** 接口失败时的降级卡片：说清哪一块没取到，而不是整页白屏 */
export function ErrorNote({ message, path }: { message: string; path?: string }) {
  return (
    <div className="rounded-lg border border-coral/30 bg-coral/10 px-3 py-2.5 text-[12px] text-coral">
      <div className="font-medium">这一块数据没取到</div>
      <div className="mt-1 break-all text-coral/80">{message}</div>
      {path && <div className="mt-1 font-mono text-[11px] text-coral/60">GET /api{path}</div>}
    </div>
  );
}

/* ============ 表格 ============ */

export function Table({
  head,
  children,
  dense = false,
}: {
  head: ReactNode[];
  children: ReactNode;
  dense?: boolean;
}) {
  return (
    <div className="-mx-1 min-w-0 max-w-full overflow-x-auto px-1">
      <table className="w-full min-w-[520px] border-collapse text-[12px]">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                className={`whitespace-nowrap border-b border-line font-semibold text-muted ${
                  dense ? "px-2 py-1.5" : "px-2.5 py-2"
                } ${i === 0 ? "text-left" : "text-right"}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Td({
  children,
  num = false,
  muted = false,
  className = "",
}: {
  children: ReactNode;
  num?: boolean;
  muted?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`border-b border-line/60 px-2.5 py-2 ${
        num ? "tnum text-right" : "text-left"
      } ${muted ? "text-muted" : ""} ${className}`}
    >
      {children}
    </td>
  );
}

/* ============ 页头 ============ */

export function PageHeader({
  title,
  desc,
  right,
}: {
  title: string;
  desc: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[19px] font-bold leading-tight text-white">{title}</h1>
        <p className="mt-1 text-[12.5px] text-muted">{desc}</p>
      </div>
      {right}
    </div>
  );
}

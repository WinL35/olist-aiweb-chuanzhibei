"use client";

import { useEffect, useState } from "react";
import { clientGet } from "@/lib/client-api";
import { fmt, money, pctRaw } from "@/lib/format";
import { EmptyState, ErrorNote, PageHeader, Panel } from "@/components/ui/primitives";
import { RfmBar, RfmPie, RfmScatter } from "@/components/charts/rfm-charts";
import type { ListPayload, RfmPoint, RfmScheme, RfmSegment } from "@/types/api";

const SCHEMES: { key: RfmScheme; label: string; hint: string }[] = [
  {
    key: "rule8",
    label: "业务规则 8 类",
    hint: "按 R/F/M 五分位打分落档，业务含义直观",
  },
  {
    key: "kmeans4",
    label: "K-Means 聚类 4 类",
    hint: "R/F/M 三维聚类，题目要求的聚类分群",
  },
];

/**
 * 用户分群 —— Client Component
 *
 * 与看板不同，这里的主指标依赖「分群口径」这一交互状态，
 * 数据必须在浏览器侧按需重取，因此整体下移到客户端。
 */
export default function RfmPage() {
  const [scheme, setScheme] = useState<RfmScheme>("rule8");
  const [segs, setSegs] = useState<RfmSegment[]>([]);
  const [points, setPoints] = useState<RfmPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr("");
    Promise.all([
      clientGet<ListPayload<RfmSegment>>(`/rfm/segments?scheme=${scheme}`),
      clientGet<ListPayload<RfmPoint>>(`/rfm/scatter?scheme=${scheme}`),
    ])
      .then(([sg, sc]) => {
        if (cancelled) return;
        setSegs(sg.data);
        setPoints(sc.data);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scheme]);

  const activeHint = SCHEMES.find((s) => s.key === scheme)?.hint ?? "";

  return (
    <div className="min-w-0 px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="用户分群" desc="RFM 模型 + K-Means 聚类划分用户群体" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-[12px] text-muted">分群口径：</span>
        <div className="inline-flex rounded-[10px] border border-line bg-surface p-0.5">
          {SCHEMES.map((s) => (
            <button
              key={s.key}
              onClick={() => setScheme(s.key)}
              className={`rounded-lg px-3 py-1.5 text-[12px] transition-colors ${
                scheme === s.key
                  ? "bg-accent/20 font-medium text-white"
                  : "text-muted hover:text-fg"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <span className="text-[11.5px] text-muted/80">{activeHint}</span>
      </div>

      {err && <ErrorNote message={err} path={`/rfm/segments?scheme=${scheme}`} />}

      {loading && !segs.length && <EmptyState>正在载入分群结果…</EmptyState>}

      {!err && segs.length > 0 && (
        <div className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {segs.map((seg) => (
              <div key={seg.segment} className="card-star p-4">
                <div className="truncate text-[12px] font-medium text-muted" title={seg.segment}>
                  {seg.segment}
                </div>
                <div className="tnum mt-1.5 text-[24px] font-bold leading-none text-accent">
                  {fmt(seg.cnt)}
                  <small className="ml-1.5 text-[12px] font-normal text-muted">
                    ({pctRaw(seg.pct)})
                  </small>
                </div>
                <div className="mt-2.5 text-[11px] leading-relaxed text-muted">
                  平均 R {fmt(seg.avg_recency)} 天 · 平均 F {fmt(seg.avg_frequency, 1)} · 平均 M{" "}
                  {money(seg.avg_monetary)}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="分群人数占比">
              <RfmPie data={segs} />
            </Panel>
            <Panel title="各分群金额贡献">
              <RfmBar data={segs} />
            </Panel>
          </div>

          <Panel
            title="用户 RFM 散点"
            subtitle="横轴 Recency（距上次购买天数）× 纵轴 Frequency（购买次数），颜色代表分群，随机采样 2000 人"
            className="mt-4"
          >
            <RfmScatter data={points} />
          </Panel>
        </div>
      )}
    </div>
  );
}

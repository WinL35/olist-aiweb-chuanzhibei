"use client";

import { useCallback, useEffect, useState } from "react";
import { clientGet } from "@/lib/client-api";
import { money, pctRaw } from "@/lib/format";
import { EmptyState, ErrorNote, PageHeader, Panel, Pill, PillRow } from "@/components/ui/primitives";
import { PredictionChart } from "@/components/charts/prediction-chart";
import type { ListPayload, PredictionCategory, PredictionResult } from "@/types/api";

const WEEK_OPTIONS = [4, 6, 8, 12] as const;

export default function PredictionPage() {
  const [cats, setCats] = useState<PredictionCategory[]>([]);
  const [category, setCategory] = useState<string>("");
  const [weeks, setWeeks] = useState<number>(8);
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>("");

  // 首次载入品类清单，默认选中床品（数据量最稳的品类之一）
  useEffect(() => {
    let cancelled = false;
    clientGet<ListPayload<PredictionCategory>>("/prediction/categories")
      .then((res) => {
        if (cancelled) return;
        setCats(res.data);
        const fallback = res.data.find((c) => c.category === "bed_bath_table") ?? res.data[0];
        setCategory((prev) => prev || fallback?.category || "");
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setErr(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 品类或周数变化时重新预测
  useEffect(() => {
    if (!category) return;
    let cancelled = false;
    setLoading(true);
    setErr("");
    clientGet<PredictionResult>(`/prediction/sales?category=${encodeURIComponent(category)}&weeks=${weeks}`)
      .then((res) => {
        if (!cancelled) setResult(res);
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
  }, [category, weeks]);

  const m = result?.metrics;
  const improvementTone = (m?.improvement_pct ?? 0) >= 0 ? "mint" : "coral";

  return (
    <div className="mx-auto min-w-0 max-w-shell px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="销量预测" desc="品类未来周销量预测与 95% 置信区间" />

      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <label className="text-[12px] text-muted">选择品类：</label>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="max-w-[280px] rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12.5px] text-fg outline-none focus:border-accent"
        >
          {cats.map((c) => (
            <option key={c.category} value={c.category}>
              {c.category}（GMV {money(c.gmv)}）
            </option>
          ))}
        </select>

        <label className="ml-2 text-[12px] text-muted">预测周数：</label>
        <select
          value={weeks}
          onChange={(e) => setWeeks(Number(e.target.value))}
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12.5px] text-fg outline-none focus:border-accent"
        >
          {WEEK_OPTIONS.map((w) => (
            <option key={w} value={w}>
              {w} 周
            </option>
          ))}
        </select>
      </div>

      {err && <ErrorNote message={err} path={`/prediction/sales?category=${category}`} />}

      {m && (
        <div className="mb-4">
          <PillRow>
            <Pill label="模型" value={m.model} tone="accent" />
            <Pill label="基线" value={m.baseline_model} />
            <Pill label="MAPE（模型）" value={pctRaw(m.mape_model)} tone={m.mape_model <= 15 ? "mint" : "amber"} />
            <Pill label="MAPE（基线）" value={pctRaw(m.mape_baseline)} />
            <Pill
              label="较基线提升"
              value={(m.improvement_pct >= 0 ? "+" : "") + pctRaw(m.improvement_pct)}
              tone={improvementTone}
            />
            <Pill label="验证窗口" value={`${m.holdout_weeks} 周`} />
          </PillRow>
        </div>
      )}

      <Panel title={`${category || "—"} 周销量预测（含 95% 置信区间）`}>
        {loading && !result ? (
          <EmptyState>正在训练与预测…</EmptyState>
        ) : result ? (
          <div className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
            <PredictionChart result={result} />
          </div>
        ) : (
          <EmptyState>暂无可预测的品类数据</EmptyState>
        )}
      </Panel>

      <p className="mt-3 text-[11.5px] leading-relaxed text-muted/80">
        说明：模型采用 Holt-Winters / Holt 阻尼趋势；MAPE 在最近若干周留出窗口上计算，基线为移动平均（近 4
        周）。单品类周销量波动较大，15% 为参考指标而非硬性阈值。
      </p>
    </div>
  );
}

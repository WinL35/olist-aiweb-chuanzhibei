"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import { money, signed } from "@/lib/format";
import type { CategoryRecommendation, SelectionProduct } from "@/types/api";

/** 品类气泡图：规模 × 增长率，气泡大小=综合分 */
export function CategoryBubble({ data }: { data: CategoryRecommendation[] }) {
  const option = useMemo(
    () => ({
      tooltip: {
        ...TOOLTIP_STYLE,
        formatter: (p: { data: [number, number, number, string] }) =>
          `${p.data[3]}<br/>近期 GMV ${money(p.data[0])}<br/>增长率 ${p.data[1].toFixed(1)}%<br/>综合分 ${p.data[2]}`,
      },
      grid: { ...BASE_GRID, bottom: 46 },
      xAxis: {
        name: "近期 GMV",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: {
          color: AXIS_COLOR,
          formatter: (v: number) => (v >= 1e3 ? (v / 1e3).toFixed(0) + "k" : String(v)),
        },
      },
      yAxis: {
        name: "增长率（%）",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      series: [
        {
          type: "scatter",
          itemStyle: { color: PAL[0], opacity: 0.75 },
          symbolSize: (d: number[]) => 8 + Math.max(0, Math.min(100, d[2] ?? 0)) / 5,
          data: data.map(
            (d) =>
              [d.recent_gmv, Number((d.growth_rate * 100).toFixed(1)), d.score, d.category] as [
                number,
                number,
                number,
                string,
              ],
          ),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={340} ariaLabel="品类规模与增长率气泡图" />;
}

/** 商品增长榜横向柱图 */
export function ProductGrowthBar({ data }: { data: SelectionProduct[] }) {
  const option = useMemo(() => {
    const rows = [...data].reverse();
    return {
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "axis",
        formatter: (ps: { dataIndex: number }[]) => {
          const d = rows[ps[0]?.dataIndex ?? 0];
          if (!d) return "";
          return `${d.category}<br/>近期 GMV ${money(d.gmv_recent)}<br/>增长率 ${signed(d.growth_pct)}`;
        },
      },
      grid: { ...BASE_GRID, left: 122, bottom: 40 },
      xAxis: {
        type: "value",
        axisLine,
        splitLine,
        axisLabel: {
          color: AXIS_COLOR,
          formatter: (v: number) => (v >= 1e3 ? (v / 1e3).toFixed(0) + "k" : String(v)),
        },
      },
      yAxis: {
        type: "category",
        data: rows.map((d) => `#${d.rank} ${d.category}`),
        axisLine,
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5 },
      },
      series: [
        {
          type: "bar",
          data: rows.map((d) => Number(d.gmv_recent)),
          itemStyle: { color: PAL[1], borderRadius: [0, 4, 4, 0] },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={340} ariaLabel="商品增长榜 Top10 近期 GMV 条形图" />;
}

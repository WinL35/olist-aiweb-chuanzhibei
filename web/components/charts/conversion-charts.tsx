"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import type { FunnelStage, RepurchaseSlice } from "@/types/api";

export function FunnelChart({ data }: { data: FunnelStage[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "item", formatter: "{b}：{c}（{d}%）" },
      series: [
        {
          type: "funnel",
          left: "8%",
          width: "84%",
          sort: "none",
          gap: 2,
          label: { color: AXIS_COLOR, formatter: "{b}\n{c}" },
          itemStyle: { borderColor: PAL[0], borderWidth: 0 },
          data: data.map((d) => ({ name: d.stage, value: d.cnt })),
        },
      ],
      color: [...PAL],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="订单转化漏斗图" />;
}

export function RepurchasePie({ data }: { data: RepurchaseSlice[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: AXIS_COLOR } },
      color: [PAL[1], PAL[0]],
      series: [
        {
          type: "pie",
          radius: ["38%", "65%"],
          label: { formatter: "{b}\n{d}%", color: AXIS_COLOR },
          data: data.map((d) => ({ name: d.type, value: d.customers })),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="单次与复购客户占比环形图" />;
}

export function RepurchaseMoneyBar({ data }: { data: RepurchaseSlice[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      legend: { data: ["金额贡献", "客户占比%"], textStyle: { color: AXIS_COLOR }, top: 0 },
      grid: { ...BASE_GRID, top: 44 },
      xAxis: { type: "category", data: data.map((d) => d.type), axisLine, axisLabel: { color: AXIS_COLOR } },
      yAxis: [
        {
          type: "value",
          name: "金额",
          axisLine,
          splitLine,
          axisLabel: {
            color: AXIS_COLOR,
            formatter: (v: number) => (v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : (v / 1e3).toFixed(0) + "k"),
          },
        },
        {
          type: "value",
          name: "占比%",
          axisLine,
          splitLine: { show: false },
          axisLabel: { color: AXIS_COLOR },
        },
      ],
      series: [
        { name: "金额贡献", type: "bar", data: data.map((d) => Number(d.monetary)), itemStyle: { color: PAL[0] }, barMaxWidth: 60 },
        {
          name: "客户占比%",
          type: "line",
          yAxisIndex: 1,
          data: data.map((d) => Number(d.customer_pct)),
          itemStyle: { color: PAL[2] },
          symbolSize: 8,
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={300} ariaLabel="复购客户金额贡献与客户占比对比图" />;
}

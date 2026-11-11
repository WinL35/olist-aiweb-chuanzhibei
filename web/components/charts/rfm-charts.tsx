"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import type { RfmPoint, RfmSegment } from "@/types/api";

export function RfmPie({ data }: { data: RfmSegment[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: AXIS_COLOR } },
      series: [
        {
          type: "pie",
          radius: ["35%", "65%"],
          color: [...PAL],
          label: { color: AXIS_COLOR },
          data: data.map((d) => ({ name: d.segment, value: d.cnt })),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="各用户分群人数占比环形图" />;
}

export function RfmBar({ data }: { data: RfmSegment[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      grid: { ...BASE_GRID, bottom: 60 },
      xAxis: {
        type: "category",
        data: data.map((d) => d.segment),
        axisLine,
        axisLabel: { color: AXIS_COLOR, rotate: 28, fontSize: 10, interval: 0 },
      },
      yAxis: {
        type: "value",
        axisLine,
        splitLine,
        axisLabel: {
          color: AXIS_COLOR,
          formatter: (v: number) => (v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : (v / 1e3).toFixed(0) + "k"),
        },
      },
      series: [
        {
          type: "bar",
          data: data.map((d) => Number(d.total_monetary)),
          itemStyle: { color: PAL[2], borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 40,
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="各分群金额贡献柱状图" />;
}

export function RfmScatter({ data }: { data: RfmPoint[] }) {
  const option = useMemo(() => {
    const segments = Array.from(new Set(data.map((d) => d.segment)));
    return {
      tooltip: {
        ...TOOLTIP_STYLE,
        formatter: (p: { data: [number, number, string] }) =>
          `分群：${p.data[2]}<br/>R=${p.data[0]} 天 · F=${p.data[1]} 次`,
      },
      legend: { data: segments, textStyle: { color: AXIS_COLOR }, top: 0, type: "scroll" },
      grid: { ...BASE_GRID, top: 44 },
      xAxis: {
        name: "Recency（天）",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: {
        name: "Frequency",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      series: segments.map((name, i) => ({
        name,
        type: "scatter" as const,
        symbolSize: 7,
        itemStyle: { color: PAL[i % PAL.length], opacity: 0.72 },
        data: data
          .filter((d) => d.segment === name)
          .map((d) => [d.recency, d.frequency, name] as [number, number, string]),
      })),
    };
  }, [data]);
  return (
    <EChart
      option={option}
      height={380}
      ariaLabel={`用户 RFM 散点图，共 ${data.length} 个采样点，颜色代表不同分群`}
    />
  );
}

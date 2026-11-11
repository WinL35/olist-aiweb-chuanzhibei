"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import type { ModelComparison } from "@/types/api";

/** 各模型 MAPE / WAPE 对比；基线模型用警示色标出 */
export function ModelErrorBar({ data }: { data: ModelComparison[] }) {
  const option = useMemo(() => {
    const rows = [...data].sort((a, b) => a.avg_mape - b.avg_mape);
    return {
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["MAPE 均值", "WAPE 均值"], textStyle: { color: AXIS_COLOR }, top: 0 },
      grid: { ...BASE_GRID, left: 138, top: 40, bottom: 40 },
      xAxis: { type: "value", axisLine, splitLine, axisLabel: { color: AXIS_COLOR, formatter: "{value}%" } },
      yAxis: {
        type: "category",
        data: rows.map((d) => (d.model.length > 14 ? d.model.slice(0, 14) + "…" : d.model)),
        axisLine,
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5 },
      },
      series: [
        {
          name: "MAPE 均值",
          type: "bar",
          data: rows.map((d) => Number(d.avg_mape)),
          // 基线用红色，其余用主色，一眼看出"是不是真的比基线好"
          itemStyle: { color: (p: { dataIndex: number }) => (rows[p.dataIndex]?.is_baseline ? PAL[3] : PAL[0]) },
        },
        {
          name: "WAPE 均值",
          type: "bar",
          data: rows.map((d) => Number(d.avg_wape)),
          itemStyle: { color: PAL[2] },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={340} ariaLabel="各预测模型 MAPE 与 WAPE 均值对比条形图" />;
}

/** 主模型 vs 基线：MAPE 中位数 */
export function MedianCompareBar({
  mainModel,
  baseline,
}: {
  mainModel: number;
  baseline: number;
}) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      grid: { ...BASE_GRID, top: 40, bottom: 36 },
      xAxis: {
        type: "category",
        data: ["主模型", "基线（MA4）"],
        axisLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: {
        type: "value",
        name: "MAPE 中位数（%）",
        nameTextStyle: { color: AXIS_COLOR },
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      series: [
        {
          type: "bar",
          barWidth: 70,
          data: [
            { value: mainModel, itemStyle: { color: PAL[1] } },
            { value: baseline, itemStyle: { color: PAL[3] } },
          ],
          label: {
            show: true,
            position: "top",
            color: AXIS_COLOR,
            formatter: (p: { value: number }) => p.value.toFixed(1) + "%",
          },
        },
      ],
    }),
    [mainModel, baseline],
  );
  return <EChart option={option} height={340} ariaLabel="主模型与基线模型 MAPE 中位数对比柱状图" />;
}

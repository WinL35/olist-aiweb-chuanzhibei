"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import type { PredictionResult } from "@/types/api";

/**
 * 周销量预测图
 *
 * 数据拼接口径与旧版完全一致：
 *   - 历史序列尾部补 null，占满 x 轴长度，避免折线错位；
 *   - 预测序列用「历史最后一点」起桥，让虚线从实测值接续，不出现断裂；
 *   - 95% 区间用两条透明线 + 一条填充带实现。
 */
export function PredictionChart({ result }: { result: PredictionResult }) {
  const option = useMemo(() => {
    const hist = result.history ?? [];
    const future = result.future ?? [];
    const histLen = hist.length;

    const xAll = [...hist.map((d) => d.week), ...future.map((d) => d.week)];

    // 用历史最后一点起桥；histLen=0 时保持空数组，不能 new Array(-1)
    const bridge =
      histLen > 0 ? [...new Array<number | null>(histLen - 1).fill(null), hist[histLen - 1]?.qty ?? null] : [];
    const forecastSeries = [...bridge, ...future.map((d) => Number(d.forecast))];

    const lower = [...new Array<number | null>(histLen).fill(null), ...future.map((d) => Number(d.lower))];
    const upper = [...new Array<number | null>(histLen).fill(null), ...future.map((d) => Number(d.upper))];
    const baseline = [...new Array<number | null>(histLen).fill(null), ...future.map((d) => Number(d.baseline))];
    const histSeries = [
      ...hist.map((d) => d.qty),
      ...new Array<number | null>(future.length).fill(null),
    ];

    return {
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      legend: {
        data: ["历史销量", "模型预测", "基线（移动平均）", "95% 置信区间"],
        textStyle: { color: AXIS_COLOR },
        top: 0,
        type: "scroll",
      },
      grid: { ...BASE_GRID, top: 52 },
      xAxis: {
        type: "category",
        data: xAll,
        axisLine,
        axisLabel: { rotate: 40, color: AXIS_COLOR, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: "周销量（件）",
        nameTextStyle: { color: AXIS_COLOR },
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      series: [
        {
          name: "历史销量",
          type: "line",
          data: histSeries,
          itemStyle: { color: PAL[0] },
          areaStyle: { opacity: 0.1 },
          symbolSize: 5,
        },
        {
          name: "模型预测",
          type: "line",
          data: forecastSeries,
          itemStyle: { color: PAL[1] },
          lineStyle: { type: "dashed" },
          symbolSize: 6,
        },
        {
          name: "基线（移动平均）",
          type: "line",
          data: baseline,
          itemStyle: { color: PAL[2] },
          lineStyle: { type: "dotted" },
          symbolSize: 4,
        },
        // 区间带：下限透明、上限填充，二者同色系形成面积
        {
          name: "95% 置信区间",
          type: "line",
          data: lower,
          lineStyle: { opacity: 0 },
          areaStyle: { color: "transparent" },
          symbol: "none",
          stack: "ci",
        },
        {
          name: "95% 置信区间",
          type: "line",
          data: upper,
          lineStyle: { opacity: 0 },
          areaStyle: { color: PAL[1], opacity: 0.15 },
          symbol: "none",
          stack: "ci",
        },
      ],
    };
  }, [result]);

  return <EChart option={option} height={380} ariaLabel="品类周销量预测曲线与 95% 置信区间" />;
}

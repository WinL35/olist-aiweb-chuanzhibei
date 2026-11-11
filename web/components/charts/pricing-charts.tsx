"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import type { PricingByCategory, PricingRow } from "@/types/api";

/** 各品类「可给建议价 / 样本不足」堆叠条形图 */
export function PricingCategoryBar({ data }: { data: PricingByCategory[] }) {
  const option = useMemo(() => {
    const rows = [...data].sort((a, b) => b.product_cnt - a.product_cnt).slice(0, 10).reverse();
    return {
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["可给建议价", "样本不足"], textStyle: { color: AXIS_COLOR }, top: 0 },
      grid: { ...BASE_GRID, left: 132, top: 40, bottom: 36 },
      xAxis: { type: "value", axisLine, splitLine, axisLabel: { color: AXIS_COLOR } },
      yAxis: {
        type: "category",
        data: rows.map((d) => d.category),
        axisLine,
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5 },
      },
      series: [
        {
          name: "可给建议价",
          type: "bar",
          stack: "t",
          data: rows.map((d) => Number(d.has_suggestion)),
          itemStyle: { color: PAL[1] },
        },
        {
          name: "样本不足",
          type: "bar",
          stack: "t",
          data: rows.map((d) => d.product_cnt - d.has_suggestion),
          itemStyle: { color: PAL[2] },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={340} ariaLabel="各品类可给建议价商品数堆叠条形图" />;
}

/** 价格弹性 × 预期营收变化散点 */
export function ElasticityScatter({ data }: { data: PricingRow[] }) {
  const option = useMemo(() => {
    const pts = data.filter((d) => d.has_suggestion && d.elasticity !== null);
    return {
      tooltip: {
        ...TOOLTIP_STYLE,
        formatter: (p: { data: [number, number, number, string] }) =>
          `${p.data[3]}<br/>弹性 ${p.data[0]}<br/>调价 ${p.data[1]}%<br/>预期营收变化 ${p.data[2]}%`,
      },
      grid: { ...BASE_GRID, bottom: 46 },
      xAxis: {
        name: "价格弹性",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: {
        name: "预期营收变化（%）",
        nameTextStyle: { color: AXIS_COLOR },
        type: "value",
        axisLine,
        splitLine,
        axisLabel: { color: AXIS_COLOR },
      },
      series: [
        {
          type: "scatter",
          symbolSize: 9,
          itemStyle: { color: PAL[0], opacity: 0.8 },
          // 零线：预期营收变化=0 的分界，便于肉眼判断哪些调价是负收益
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#4a5a78", type: "dashed" },
            data: [{ yAxis: 0 }],
          },
          data: pts.map(
            (d) =>
              [Number(d.elasticity), Number(d.price_change_pct), Number(d.expected_revenue_change_pct), d.category] as [
                number,
                number,
                number,
                string,
              ],
          ),
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={340} ariaLabel="价格弹性与预期营收变化散点图" />;
}

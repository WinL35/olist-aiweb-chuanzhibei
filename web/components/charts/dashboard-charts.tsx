"use client";

import { useMemo } from "react";
import { EChart } from "@/components/charts/echart";
import { AXIS_COLOR, BASE_GRID, PAL, SPLIT_LINE, TOOLTIP_STYLE, axisLine, splitLine } from "@/lib/echarts";
import { shortNumber } from "@/lib/format";
import type {
  CategoryGmv,
  HourPoint,
  PaymentSlice,
  RegionGmv,
  ReviewBucket,
  StatusSlice,
  TrendPoint,
  WeekdayPoint,
} from "@/types/api";

/* GMV 与订单趋势（双 Y 轴） */
export function TrendChart({ data }: { data: TrendPoint[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      legend: { data: ["GMV", "订单数"], textStyle: { color: AXIS_COLOR } },
      grid: BASE_GRID,
      xAxis: {
        type: "category",
        data: data.map((d) => d.t),
        axisLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: [
        {
          type: "value",
          name: "GMV",
          axisLine,
          splitLine,
          axisLabel: { color: AXIS_COLOR, formatter: (v: number) => shortNumber(v) },
        },
        {
          type: "value",
          name: "订单数",
          axisLine,
          splitLine: { show: false },
          axisLabel: { color: AXIS_COLOR },
        },
      ],
      series: [
        {
          name: "GMV",
          type: "line",
          smooth: true,
          areaStyle: { opacity: 0.15 },
          itemStyle: { color: PAL[0] },
          data: data.map((d) => Number(d.gmv)),
        },
        {
          name: "订单数",
          type: "line",
          yAxisIndex: 1,
          smooth: true,
          itemStyle: { color: PAL[1] },
          data: data.map((d) => d.orders),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="GMV 与订单数随时间变化的双轴折线图" />;
}

/* 支付方式分布 */
export function PaymentPie({ data }: { data: PaymentSlice[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: AXIS_COLOR } },
      series: [
        {
          type: "pie",
          radius: ["38%", "65%"],
          color: [...PAL],
          label: { color: AXIS_COLOR },
          data: data.map((d) => ({ name: d.type, value: Number(d.amount) })),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={320} ariaLabel="支付方式金额占比环形图" />;
}

/* 品类 GMV 横向条形图 */
export function CategoryBar({ data }: { data: CategoryGmv[] }) {
  const option = useMemo(() => {
    const rows = [...data].reverse();
    return {
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      grid: { ...BASE_GRID, left: 150 },
      xAxis: {
        type: "value",
        axisLine,
        splitNumber: 3,
        axisLabel: { color: AXIS_COLOR, formatter: (v: number) => shortNumber(v) },
        splitLine,
      },
      yAxis: {
        type: "category",
        data: rows.map((d) => d.category),
        axisLine,
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          data: rows.map((d) => Number(d.gmv)),
          itemStyle: { color: PAL[0], borderRadius: [0, 4, 4, 0] },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={300} ariaLabel="各品类 GMV 横向条形图" />;
}

/* 各州销售额 */
export function RegionBar({ data }: { data: RegionGmv[] }) {
  const option = useMemo(() => {
    const top = [...data].sort((a, b) => Number(b.gmv) - Number(a.gmv)).slice(0, 12);
    return {
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { ...BASE_GRID, bottom: 46 },
      xAxis: {
        type: "category",
        data: top.map((d) => d.state),
        axisLine,
        axisLabel: { rotate: 38, interval: 0, fontSize: 10, color: AXIS_COLOR },
      },
      yAxis: {
        type: "value",
        axisLine,
        axisLabel: { color: AXIS_COLOR, formatter: (v: number) => shortNumber(v) },
        splitLine,
      },
      series: [
        {
          type: "bar",
          data: top.map((d) => Number(d.gmv)),
          itemStyle: { color: PAL[2], borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 22,
        },
      ],
    };
  }, [data]);
  return <EChart option={option} height={300} ariaLabel="各州销售额 Top12 柱状图" />;
}

/* 订单状态分布 */
export function StatusPie({ data }: { data: StatusSlice[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: AXIS_COLOR }, itemWidth: 10, itemHeight: 10 },
      series: [
        {
          type: "pie",
          radius: "62%",
          color: [...PAL],
          label: { color: AXIS_COLOR, fontSize: 11 },
          data: data.map((d) => ({ name: d.status, value: d.cnt })),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={300} ariaLabel="订单状态分布饼图" />;
}

/* 下单时段分布 */
export function HourBar({ data }: { data: HourPoint[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      legend: { data: ["订单数", "GMV"], textStyle: { color: AXIS_COLOR }, top: 0 },
      grid: { ...BASE_GRID, top: 44 },
      xAxis: {
        type: "category",
        data: data.map((d) => `${d.hour}时`),
        axisLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: [
        { type: "value", axisLine, splitLine, axisLabel: { color: AXIS_COLOR } },
        {
          type: "value",
          name: "GMV",
          axisLine,
          splitLine: { show: false },
          axisLabel: { color: AXIS_COLOR, formatter: (v: number) => shortNumber(v) },
        },
      ],
      series: [
        { name: "订单数", type: "bar", itemStyle: { color: PAL[0] }, data: data.map((d) => d.orders) },
        {
          name: "GMV",
          type: "line",
          yAxisIndex: 1,
          itemStyle: { color: PAL[2] },
          data: data.map((d) => Number(d.gmv)),
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={260} ariaLabel="按小时统计的下单量与 GMV" />;
}

/* 下单星期分布 */
export function WeekdayBar({ data }: { data: WeekdayPoint[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      grid: BASE_GRID,
      xAxis: { type: "category", data: data.map((d) => d.name), axisLine, axisLabel: { color: AXIS_COLOR } },
      yAxis: { type: "value", axisLine, splitLine, axisLabel: { color: AXIS_COLOR } },
      series: [
        {
          type: "bar",
          data: data.map((d) => d.orders),
          itemStyle: { color: PAL[1], borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 40,
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={260} ariaLabel="按星期统计的下单量" />;
}

/* 评价星级分布 */
export function ReviewBar({ data }: { data: ReviewBucket[] }) {
  const option = useMemo(
    () => ({
      tooltip: { ...TOOLTIP_STYLE, trigger: "axis" },
      grid: BASE_GRID,
      xAxis: {
        type: "category",
        data: data.map((d) => `${d.score}星`),
        axisLine,
        axisLabel: { color: AXIS_COLOR },
      },
      yAxis: { type: "value", axisLine, splitLine, axisLabel: { color: AXIS_COLOR } },
      series: [
        {
          type: "bar",
          data: data.map((d) => d.cnt),
          itemStyle: {
            color: (p: { dataIndex: number }) =>
              ["#ff6b6b", "#ff9f43", "#ffd43b", "#a9e34b", "#25d4a4"][p.dataIndex % 5] as string,
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 46,
        },
      ],
    }),
    [data],
  );
  return <EChart option={option} height={260} ariaLabel="评价星级分布柱状图" />;
}

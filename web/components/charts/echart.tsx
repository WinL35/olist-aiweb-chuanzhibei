"use client";

import { useEffect, useRef } from "react";
import echarts from "@/lib/echarts";
import type { ChartOption, EChartsOption } from "@/lib/echarts";

interface EChartProps {
  option: ChartOption;
  /** 容器高度，单位 px */
  height?: number;
  className?: string;
  /** 无障碍描述 */
  ariaLabel?: string;
  /** 初始化后回传实例，供导出 PNG 等操作使用 */
  onInit?: (chart: ReturnType<typeof echarts.init>) => void;
}

/**
 * ECharts 容器组件
 *
 * 三件事：初始化 / option 变化时重绘 / 容器尺寸变化时 resize。
 * 用 ResizeObserver 而非 window.resize，是因为侧栏折叠、面板增删
 * 都不会触发 window.resize，但容器宽度确实变了。
 */
export function EChart({ option, height = 320, className, ariaLabel }: EChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const chart = echarts.init(host, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(host);

    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge=true：切换品类/口径时彻底替换旧配置，避免残留 series
    chartRef.current?.setOption(option as EChartsOption, true);
  }, [option]);

  return (
    <div
      ref={hostRef}
      role="img"
      aria-label={ariaLabel}
      className={className}
      style={{ height, width: "100%" }}
    />
  );
}

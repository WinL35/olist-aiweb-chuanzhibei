"use client";

import { useCallback, useRef, useState } from "react";
import { EChart } from "@/components/charts/echart";
import type { ChartOption } from "@/lib/echarts";

/**
 * 对话内嵌图表
 *
 * 图表 option 由后端工具确定性组装（模型不允许自己编数字），
 * 前端只负责渲染与导出。导出能力是「结论可被带走」的最小闭环：
 * 会议里截图、Excel 里核算，都从这两个按钮开始。
 */
export function ChartCard({ option, index }: { option: ChartOption; index: number }) {
  // 只依赖 getDataURL，无需绑定 ECharts 的完整类型
  const chartRef = useRef<{ getDataURL: (opts: { pixelRatio: number; backgroundColor: string }) => string } | null>(
    null,
  );
  const [saved, setSaved] = useState<"" | "png" | "csv">("");

  const title = (() => {
    const t = option.title as { text?: string } | undefined;
    return t?.text || `chart-${index + 1}`;
  })();

  const flash = (kind: "png" | "csv") => {
    setSaved(kind);
    setTimeout(() => setSaved(""), 1600);
  };

  const exportPng = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // 导出图的底色要和页面一致，否则存下来是一张深色底的图（浅色主题下很突兀）
    const url = chart.getDataURL({ pixelRatio: 2, backgroundColor: "#ffffff" });
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title}.png`;
    a.click();
    flash("png");
  }, [title]);

  const exportCsv = useCallback(() => {
    type SeriesLike = { name?: string; data?: unknown[] };
    const series = (option.series as SeriesLike[] | undefined) ?? [];
    const xAxis = option.xAxis as { data?: unknown[] } | undefined;
    const first = series[0];

    const xs: unknown[] =
      xAxis?.data ??
      (first?.data ?? []).map((d) =>
        d && typeof d === "object" && "name" in (d as Record<string, unknown>)
          ? (d as Record<string, unknown>).name
          : "",
      );

    const cols = series.map((s) => ({
      name: s.name || "值",
      data: (s.data ?? []).map((d) =>
        d && typeof d === "object" && "value" in (d as Record<string, unknown>)
          ? (d as Record<string, unknown>).value
          : d,
      ),
    }));

    let csv = "维度," + cols.map((c) => c.name).join(",") + "\n";
    xs.forEach((x, i) => {
      csv += `"${String(x ?? "")}",` + cols.map((c) => (c.data[i] ?? "") as string).join(",") + "\n";
    });

    // BOM 头：让 Excel 正确识别 UTF-8 中文
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${title}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    flash("csv");
  }, [option, title]);

  return (
    <figure className="mt-3">
      <div className="rounded-[10px] border border-line bg-surface2 p-1">
        <EChart
          option={option}
          height={300}
          onInit={(c) => {
            chartRef.current = c as typeof chartRef.current;
          }}
          ariaLabel={title}
        />
      </div>
      <figcaption className="mt-1.5 flex items-center gap-2">
        <button onClick={exportPng} className="btn-ghost !py-1 !text-[11px]">
          {saved === "png" ? "✓ 已导出" : "导出 PNG"}
        </button>
        <button onClick={exportCsv} className="btn-ghost !py-1 !text-[11px]">
          {saved === "csv" ? "✓ 已导出" : "导出 CSV"}
        </button>
        <span className="text-[10.5px] text-muted/60">数据由工具计算后组装，非模型生成</span>
      </figcaption>
    </figure>
  );
}

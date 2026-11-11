/**
 * 数字格式化工具
 * 与原 static/assets/app.js 的 fmt / money / pct 行为保持一致，
 * 保证迁移前后同一份数据渲染出的文案完全相同。
 */

/** 千分位数字；null 显示为 "-" */
export function fmt(n: number | string | null | undefined, dp = 0): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "-";
  return Number(n).toLocaleString("zh-CN", {
    maximumFractionDigits: dp,
    minimumFractionDigits: dp,
  });
}

/** 巴西雷亚尔（数据集为 Olist 巴西电商） */
export function money(n: number | string | null | undefined): string {
  return "R$ " + fmt(n, 0);
}

/** 比例 → 百分比，输入 0.123 → "12.3%" */
export function pct(n: number | null | undefined, dp = 1): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "-";
  return (Number(n) * 100).toFixed(dp) + "%";
}

/** 已经是百分数的值，输入 12.3 → "12.3%" */
export function pctRaw(n: number | null | undefined, dp = 1): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "-";
  return Number(n).toFixed(dp) + "%";
}

/** 带正负号的百分比，用于增长率 */
export function signed(n: number | null | undefined, dp = 1): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "-";
  const v = Number(n);
  return (v >= 0 ? "+" : "") + v.toFixed(dp) + "%";
}

/** 大数字缩写，用于坐标轴 1234567 → "1.2M" */
export function shortNumber(v: number): string {
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(0) + "k";
  return String(v);
}

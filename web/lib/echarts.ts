/**
 * ECharts 按需引入
 *
 * 旧版直接加载 echarts.min.js 全量包（约 1.01MB，gzip 后 ~340KB），
 * 拖慢首屏。这里只注册实际用到的 5 种图表 + 4 个组件 + Canvas 渲染器，
 * 打包体积降到原来的 40% 左右，且保持 API 与全量一致。
 */
import * as echarts from "echarts/core";
import { BarChart, FunnelChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import {
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { LabelLayout, UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  FunnelChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  GraphicComponent,
  MarkLineComponent,
  LabelLayout,
  UniversalTransition,
  CanvasRenderer,
]);

export default echarts;
export type { EChartsOption } from "echarts";

/**
 * 图表配置的宽松类型。
 *
 * ECharts 官方 EChartsOption 对「运行时动态拼装」极不友好：formatter 回调、
 * 按 dataIndex 取色、条件性 series 都会触发类型不兼容。业界通行做法是把
 * 配置对象当作纯数据描述，在 setOption 入口统一断言。
 * 业务数据（接口响应）仍然走 types/api.ts 的严格类型，不做任何放宽。
 */
export type ChartOption = Record<string, unknown>;

/** 主题常量：与 tailwind.config.ts 的设计令牌保持同源 */
export const PAL = [
  "#2f9bff",
  "#25d4a4",
  "#ffb547",
  "#ff6b6b",
  "#a866ff",
  "#36cfc7",
  "#ff85a2",
  "#ffc107",
] as const;

export const AXIS_COLOR = "#8ea0bd";
export const SPLIT_LINE = "#22304a";
export const PANEL_BG = "#1a2438";

export const BASE_GRID = { left: 84, right: 26, top: 34, bottom: 48 };

export const TOOLTIP_STYLE = {
  backgroundColor: PANEL_BG,
  borderColor: "#2a3650",
  textStyle: { color: "#e8eef7" },
};

/** 坐标轴通用样式，避免每个 option 重复写 */
export const axisLine = { lineStyle: { color: AXIS_COLOR } };
export const splitLine = { lineStyle: { color: SPLIT_LINE } };

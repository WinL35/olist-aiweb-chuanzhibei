/**
 * 导航图标：全部为线性矢量（stroke，无填充），替代原先的 emoji。
 *
 * 为什么不用 emoji：
 *   1. emoji 由系统字体渲染，Windows / macOS / Linux 三端字形与颜色完全不同，
 *      评委在 Linux 上看到的和开发者本机不是同一个东西；
 *   2. emoji 自带彩色，和深灰面板上的白色线性图标放在一起会打架；
 *   3. 无法继承 currentColor，做不了 hover / 选中态的描边变化。
 *
 * 统一规范（与设计稿一致）：24×24 viewBox、fill:none、stroke:currentColor、
 * 圆端圆角（stroke-linecap/linejoin: round）、描边 1.6（在容器上用 CSS 控制，
 * 这样同一个图标在 23px 与 54px 两档尺寸下都能保持视觉重量一致）。
 */

/** 所有图标的公共属性，避免 8 个文件重复写同一串。 */
const BASE = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: "false" as const,
};

/** 经营看板：坐标轴 + 三根柱，最直白的"看数据"语义 */
export function IconDashboard() {
  return (
    <svg {...BASE}>
      <path d="M3 3v18h18" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </svg>
  );
}

/** 用户分群：双人像，第二个人用半截线暗示"群体"而非个体 */
export function IconUsers() {
  return (
    <svg {...BASE}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

/** 转化分析：漏斗，对应"曝光→点击→下单"的逐层收窄 */
export function IconFunnel() {
  return (
    <svg {...BASE}>
      <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />
    </svg>
  );
}

/** 销量预测：上扬折线 + 箭头，强调"预测"而非"当前值" */
export function IconTrendUp() {
  return (
    <svg {...BASE}>
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}

/** 选品建议：同心圆靶心，对应"从全量品类里挑出目标" */
export function IconTarget() {
  return (
    <svg {...BASE}>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

/** 定价建议：价签，圆点是穿绳孔 */
export function IconTag() {
  return (
    <svg {...BASE}>
      <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
      <circle cx="7.5" cy="7.5" r="0.6" />
    </svg>
  );
}

/** 模型实验：锥形瓶，对应"离线评估 / 基线对照" */
export function IconFlask() {
  return (
    <svg {...BASE}>
      <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2" />
      <path d="M8.5 2h7" />
      <path d="M7 16h10" />
    </svg>
  );
}

/**
 * 已废弃：`IconChat`（对话气泡）与 `BrandMark`（六边形 O）
 *
 * 侧栏底部「智能问答」入口已换成四个会追鼠标的小人（见 ./nav-characters.tsx），
 * 这两个图标不再被任何地方引用。保留文件里的其他 7 个线性图标不动，
 * 因为它们是 7 个数据页正在用的。
 */

/*
 * 品牌徽标（旧实现，留作样式参考）：
 * 六边形外框 + 内部 "O" 挖空，用 evenodd 让内圈成为真正的镂空，
 * 而不是叠一个白色圆形——后者在深色背景上会露出白边。
 */
export function BrandMark() {
  return (
    <svg viewBox="0 0 512 512" aria-hidden focusable="false">
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d="M212 59.403A88 88 0 0 1 300 59.403L404.258 119.597A88 88 0 0 1 448.258 195.807L448.258 316.193A88 88 0 0 1 404.258 392.403L300 452.597A88 88 0 0 1 212 452.597L107.742 392.403A88 88 0 0 1 63.742 316.193L63.742 195.807A88 88 0 0 1 107.742 119.597ZM256 152A104 104 0 1 0 256 360A104 104 0 1 0 256 152Z"
      />
    </svg>
  );
}

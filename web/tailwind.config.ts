import type { Config } from "tailwindcss";

/**
 * 设计令牌（Design Tokens）
 * 色值 1:1 迁移自旧版 static/assets/style.css 的 :root 变量，保证视觉不跑偏；
 * 命名改为语义化，避免与 Tailwind 的 border 工具类名冲突。
 *
 * 2026-11-13：主内容区整体切换为浅色主题（用户要求"背景变白，数据图也跟着变"）。
 * 只改了中性色（画布 / 面板 / 边框 / 文字），**主色与语义色一律不动** ——
 * 蓝绿橙红在白底上依然清晰，这样图表的 PAL 色板无需重挑。
 * 左侧导航条（#35363a 深灰油画质感）保持深色，见 fluid-nav.tsx。
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#f4f6fa", // 页面底色（浅灰白，纯白会让卡片边界消失）
        surface: "#ffffff", // 卡片 / 面板
        surface2: "#eef2f8", // 次级面板、输入框
        line: "#dde4ee", // 边框
        accent: "#2f9bff", // 主色（未变，用于色块/描边/图表）
        /**
         * 主色作为**文字**时的替代色。
         * #2f9bff 在白底上对比度只有 2.9，达不到 WCAG AA 的 4.5，小字号下会"发虚"。
         * 压暗到 #0a6ec9 后，三种底色全部过线：
         *   surface 5.14 / canvas 4.75 / surface2 4.57
         * 观感仍是同一个蓝，只是沉了一档。
         */
        accentInk: "#0a6ec9",
        mint: "#25d4a4", // 正向 / 成功（未变）
        amber: "#ffb547", // 警示（未变）
        coral: "#ff6b6b", // 错误（未变）
        fg: "#16202f", // 主文字
        /**
         * 次要文字。原 #66748a 在白卡片上够（4.74），但在 canvas #f4f6fa
         * 和 surface2 #eef2f8 上只有 4.38 / 4.22，刚好卡在 AA 线下。
         * 压到 #5d6b80：surface 5.41 / canvas 5.00 / surface2 4.82，三底全过。
         */
        muted: "#5d6b80",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        card: "14px",
      },
      // 说明：原先有 maxWidth.shell = 1560px，与 mx-auto 一起把内容居中。
      // 屏幕超过 1656px（1560 + 侧栏 96）后左右各空出一大块，反馈"中间太窄、两边太宽"，
      // 已改为内容撑满可用宽度，只保留 px-4/sm:px-6/lg:px-7 内边距。
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        caret: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
      animation: {
        "fade-up": "fade-up .28s ease-out both",
        caret: "caret 1s step-end infinite",
      },
    },
  },
  plugins: [],
};

export default config;

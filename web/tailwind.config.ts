import type { Config } from "tailwindcss";

/**
 * 设计令牌（Design Tokens）
 * 色值 1:1 迁移自旧版 static/assets/style.css 的 :root 变量，保证视觉不跑偏；
 * 命名改为语义化，避免与 Tailwind 的 border 工具类名冲突。
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
        canvas: "#0f1626", // 页面底色
        surface: "#1a2438", // 卡片 / 面板
        surface2: "#22304a", // 次级面板、输入框
        line: "#2a3650", // 边框
        accent: "#2f9bff", // 主色
        mint: "#25d4a4", // 正向 / 成功
        amber: "#ffb547", // 警示
        coral: "#ff6b6b", // 错误
        fg: "#e8eef7", // 主文字
        muted: "#8ea0bd", // 次要文字
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

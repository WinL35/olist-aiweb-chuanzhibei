import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Olist 电商经营决策平台",
    template: "%s · Olist 经营决策平台",
  },
  description:
    "面向巴西 Olist 电商数据集的经营决策垂直大模型：用中文自然语言提问，经口径校验与工具调用后给出可追溯的经营建议，并直接产出图表。",
  applicationName: "Olist 经营决策平台",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f1626",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

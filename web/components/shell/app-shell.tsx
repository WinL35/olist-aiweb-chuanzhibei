"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { FluidNav, NAV_ITEMS } from "@/components/nav/fluid-nav";

/** 兼容旧引用：页面名列表 */
export const NAV = NAV_ITEMS.map((n) => ({ key: n.key, name: n.name }));

export const PAGE_DESC: Record<string, string> = {
  dashboard: "GMV / 客单价 / 转化率 / 复购率等核心经营指标",
  rfm: "RFM 模型 + K-Means 聚类划分用户群体",
  conversion: "订单转化漏斗与复购情况",
  prediction: "品类未来周销量预测与预测区间",
  recommend: "增长潜力品类推荐与离线策略对照评估",
  pricing: "价格弹性分析与建议价格区间",
  experiment: "预测模型离线评估与基线对照",
  assistant: "对话式经营分析：口径校验 → 工具调用 → 可追溯结论与图表",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // 路由切换后自动收起移动端抽屉
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  const active = pathname.split("/")[1] || "dashboard";
  const activeName = NAV_ITEMS.find((n) => n.key === active)?.name ?? "智能问答";

  return (
    <div className="flex min-h-screen">
      {/* 移动端遮罩 */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}

      {/*
        侧栏在移动端是抽屉（可滑出），桌面端常驻。
        宽度必须与 FluidNav 内部一致：移动端只有深灰面板（132px），
        桌面端多了 56px 油画窄条，共 188px。

        ⚠️ 桌面端必须用 sticky + h-screen，不能用 static：
        根容器是 min-h-screen，看板内容很长，static 会让 aside 被拉到整页高度，
        于是"靠 flex-1 推到底部"的圆形入口会被推到几千像素之外。
      */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[132px] shrink-0 transition-transform duration-200 sm:w-[188px] lg:sticky lg:top-0 lg:bottom-auto lg:h-screen lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <FluidNav />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* 移动端顶栏 */}
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-canvas/90 px-4 py-2.5 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(true)} className="btn-ghost" aria-label="打开导航菜单">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.7}
              strokeLinecap="round"
              aria-hidden
            >
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
          <span className="text-[13px] font-semibold text-white">{activeName}</span>
        </div>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

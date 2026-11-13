"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { FluidTooltipEngine } from "./fluid-tooltip-engine";
import {
  IconDashboard,
  IconFlask,
  IconFunnel,
  IconTag,
  IconTarget,
  IconTrendUp,
  IconUsers,
} from "./icons";
import { NavCharacters } from "./nav-characters";

/**
 * 侧栏导航（流体提示气泡版）
 * ============================
 *
 * 相比旧版的三个变化：
 *   1. emoji → 线性矢量图标（跨平台字形一致，可继承 currentColor）；
 *   2. 常驻文字标签 → 悬停/聚焦才出现的共享胶囊；
 *   3. 每个按钮各自弹气泡 → 一个胶囊纵向滑行，文字被裁切显现。
 *
 * 快捷键 ⌘1…⌘8 是**真实生效**的（见下方 keydown），不是画上去的装饰，
 * 因为"提示写着 ⌘3 但按了没反应"比没有提示更糟。
 *
 * 底部「智能问答」入口是四个会追鼠标的小人（NavCharacters）。
 * 它们原先的触发条件是登录页的账号框/密码框聚焦，这里搬过来后改成：
 *   悬停导航按钮 → 小人侧身、眼珠转向该按钮；
 *   点击导航按钮 → 触发一次「对视」。
 * 事件源就在本组件的 nav 上，用 React 状态统一收口后传下去。
 */

export interface NavItem {
  key: string;
  name: string;
  hint: string;
  Icon: () => JSX.Element;
}

/** 7 个数据页 + 1 个对话入口（底部圆形位） */
export const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", name: "经营看板", hint: "⌘1", Icon: IconDashboard },
  { key: "rfm", name: "用户分群", hint: "⌘2", Icon: IconUsers },
  { key: "conversion", name: "转化分析", hint: "⌘3", Icon: IconFunnel },
  { key: "prediction", name: "销量预测", hint: "⌘4", Icon: IconTrendUp },
  { key: "recommend", name: "选品建议", hint: "⌘5", Icon: IconTag },
  { key: "pricing", name: "定价建议", hint: "⌘6", Icon: IconTarget },
  { key: "experiment", name: "模型实验", hint: "⌘7", Icon: IconFlask },
  // 底部圆形位不用线性图标，改用 NavCharacters 四小人，Icon 仅为保持类型一致
  { key: "assistant", name: "智能问答", hint: "⌘8", Icon: IconTarget },
];

export function FluidNav() {
  const pathname = usePathname();
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Array<HTMLAnchorElement | null>>([]);
  /** 引擎实例：快捷键跳转后要用它把气泡定位到目标那一行 */
  const engineRef = useRef<FluidTooltipEngine | null>(null);

  /** 悬停的是第几项（-1 = 没有悬停），四小人靠它决定侧身方向 */
  const [hoverIdx, setHoverIdx] = useState(-1);
  /** 点击脉冲：每点一次导航按钮就 +1，四小人据此触发一次「对视」 */
  const [pulse, setPulse] = useState(0);

  const activeKey = pathname.split("/")[1] || "dashboard";

  /** 供引擎使用的纯数据（不含 React 元素，避免引擎触碰 JSX） */
  const engineItems = useMemo(
    () => NAV_ITEMS.map((n) => ({ id: n.key, label: n.name, hint: n.hint })),
    []
  );

  useEffect(() => {
    const panel = panelRef.current;
    const buttons = itemRefs.current.filter(Boolean) as HTMLAnchorElement[];
    if (!panel || buttons.length !== NAV_ITEMS.length) return;

    const engine = new FluidTooltipEngine({
      panel,
      items: engineItems,
      buttons,
      // 胶囊高 56（原 64）：与引擎内字号 23/19、内边距 22、间距 12 配套
      capsuleHeight: 56,
      // 胶囊左边缘 = 按钮左边距 + 按钮宽。侧栏 96px、按钮 84px → 左边距 6px → 90。
      // 改侧栏宽度时必须同步这里（见 app-shell.tsx 的 aside 宽度）。
      offsetX: 90,
    });

    engineRef.current = engine;
    return () => {
      engineRef.current = null;
      engine.destroy();
    };
  }, [engineItems]);

  /**
   * 真实快捷键：Meta / Ctrl + 1…8 → 对应页面。
   * 输入框内不拦截，否则会在文本框里误触发跳转。
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable)
        return;
      const n = Number(e.key);
      if (!Number.isInteger(n) || n < 1 || n > NAV_ITEMS.length) return;
      e.preventDefault();
      router.push(`/${NAV_ITEMS[n - 1].key}`);
      /**
       * 跳转后把气泡滑到目标那一行，让用户看清"我到了第几项"。
       * 鼠标此时通常不在侧栏上，所以用 reveal 主动唤起；
       * 用户一旦把鼠标移进侧栏，正常的悬停逻辑会立刻接管，不会打架。
       */
      engineRef.current?.reveal(n - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  return (
    <div className="flex h-full min-h-0">
      {/*
        只保留深灰面板，不再有左侧装饰窄条。
        原来那条 56px 油画在深色底上几乎看不出画意，反而被读成"左边空了一块"，
        直接把宽度还给内容区更实在。

        ⚠️ 右缘不要再画亮线。
        这里曾经是 `inset -2px 0 0 rgba(255,255,255,.10)`：在 #35363a 上叠 10% 白，
        实测像素 (75,75,79)，比面板底色亮 20。它紧挨着深蓝黑正文底 (13,19,32)，
        于是这 2px 白线在冷暖反差下被看成"一条蓝线"，贯穿整屏高度非常扎眼。
        现在改为暗色内描边（只是让边缘干净，几乎看不见），
        分层交给底色对比(#35363a vs #0d1320)与柔和外投影完成。
      */}
      <div
        ref={panelRef}
        className="relative flex min-h-0 flex-1 flex-col bg-[#35363a]"
        style={{ boxShadow: "inset -1px 0 0 rgba(0,0,0,.35), 20px 0 46px rgba(0,0,0,.19)" }}
      >
        {/* 静态颗粒：极低不透明度，只为了让纯色面板不显得"塑料" */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-10"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' seed='17' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.024'/%3E%3C/svg%3E\")",
          }}
        />

        <nav
          aria-label="主导航"
          className="nav-scroll flex min-h-0 flex-1 flex-col items-center gap-[9px] overflow-y-auto py-7"
        >
          {NAV_ITEMS.slice(0, 7).map((item, i) => {
            const isActive = activeKey === item.key;
            return (
              <Link
                key={item.key}
                href={`/${item.key}`}
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                aria-label={item.name}
                aria-current={isActive ? "page" : undefined}
                data-active={isActive || undefined}
                /* 四小人的两个触发点：悬停定位 + 点击脉冲 */
                onPointerEnter={() => setHoverIdx(i)}
                onFocus={() => setHoverIdx(i)}
                onPointerLeave={() => setHoverIdx((v) => (v === i ? -1 : v))}
                onBlur={() => setHoverIdx((v) => (v === i ? -1 : v))}
                onClick={() => setPulse((v) => v + 1)}
                className="nav-btn group relative flex h-[84px] w-[84px] shrink-0 items-center justify-center rounded-[28px] text-white/80 outline-none transition-[background-color,color] duration-[130ms] hover:bg-white/[.025] hover:text-white data-[active]:bg-white/[.11] data-[active]:text-white focus-visible:ring-[3px] focus-visible:ring-[#e9edf7] focus-visible:ring-offset-[5px] focus-visible:ring-offset-[#35363a]"
              >
                {/* 只缩小图标本体：按钮 84 / 圆角 28 / 间距 9 / 内边距 全部保持原值 */}
                <span className="h-[26px] w-[26px]">
                  <item.Icon />
                </span>
              </Link>
            );
          })}
        </nav>

        {/* 底部入口：四个小人的纯图标，**不加白色圆底**。
            因为小人本身带颜色（紫/黑/橙/黄），放在白底上看不出"图标感"，
            反而像一张缩略图贴在圆里；直接用图形做按钮，与上方线性图标列
            在深灰面板上的观感更统一。

            宽度：侧栏 96px，按钮给到 92px（左右各留 2px），横向铺满。
            图形本体 84×72 —— 比原来的 52×52 明显更宽更高。
            参考截图量到的目标占比：小人整体约 55×76，宽高比接近 1:1.4（偏竖向），
            所以这里也按竖向构图给，而不是压成一个扁的横向条。
            72 高是上限：再高会撞到上面的导航列（那列是 flex-1 且可滚动）。 */}
        <div className="flex shrink-0 flex-col items-center pb-5">
          <Link
            href="/assistant"
            ref={(el) => {
              itemRefs.current[7] = el;
            }}
            aria-label={NAV_ITEMS[7].name}
            aria-current={activeKey === "assistant" ? "page" : undefined}
            data-active={activeKey === "assistant" || undefined}
            onClick={() => setPulse((v) => v + 1)}
            className="nav-btn mx-auto flex h-[78px] w-[92px] shrink-0 items-center justify-center self-center rounded-[20px] outline-none transition-[background-color,box-shadow] duration-[130ms] hover:bg-white/[.06] data-[active]:bg-white/[.11] data-[active]:shadow-[inset_0_0_0_1.5px_rgba(255,255,255,.28)] focus-visible:ring-[3px] focus-visible:ring-[#e9edf7] focus-visible:ring-offset-[5px] focus-visible:ring-offset-[#35363a]"
          >
            <NavCharacters
              className="h-[72px] w-[84px] shrink-0"
              hovered={hoverIdx >= 0}
              gazeRatio={hoverIdx < 0 ? 0.5 : hoverIdx / 6}
              pulse={pulse}
            />
          </Link>
        </div>
      </div>
    </div>
  );
}

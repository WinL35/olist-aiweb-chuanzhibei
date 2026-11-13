"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

/**
 * 胶囊下拉选择器
 * =================
 *
 * 为什么不用原生 <select>：
 * 原生下拉的弹出层是**浏览器自己画的**（Chromium 里是独立的一层，
 * 甚至不在 DOM 里），CSS 完全无法命中它的背景、边框和 <option>。
 * 所以截图里那个方框 + 蓝底高亮改不掉，只能自己实现一套。
 *
 * 视觉要点（用户明确要求）：
 *   · 触发按钮和每个选项都是 **中间长方、两端半圆的胶囊**（rounded-full）
 *   · **不要外边框** —— 展开的面板只是一层浮起来的深色底 + 柔和阴影，
 *     没有 1px 灰色方框（原生那个方框正是"太丑"的来源）
 *   · 展开时选项 **一条接着一条滑进来**（stagger + translate）
 *
 * 交互与可访问性：
 *   · 点击外部 / Esc 关闭；↑↓ 移动高亮、Enter 选中、Home/End 跳首尾
 *   · role="listbox" + role="option" + aria-selected，键盘可完整操作
 *   · 触发器保留 aria-haspopup / aria-expanded
 */

export interface PillSelectOption<T extends string | number> {
  value: T;
  label: string;
  /** 选项右侧的次要信息（如 GMV），会淡化显示 */
  hint?: string;
}

export interface PillSelectProps<T extends string | number> {
  value: T;
  options: PillSelectOption<T>[];
  onChange: (v: T) => void;
  /** 触发按钮宽度类，默认自适应；品类那种长文案可传 max-w */
  className?: string;
  /** 面板对齐：start 左对齐触发器，end 右对齐（靠右边缘时用） */
  align?: "start" | "end";
  /** 面板最大高度，超出滚动 */
  maxHeight?: number;
  placeholder?: string;
  title?: string;
  ariaLabel?: string;
}

/** 每条选项滑入的间隔（ms）与单条时长（ms） */
const STAGGER = 26;
const ITEM_DURATION = 260;
/**
 * 只有前 N 条参与错峰。
 * 品类有 74 个选项，若全部错峰，最后一条要等 74×26 ≈ 1.9s 才出现，
 * 观感是"卡住了"。N 之后的直接以动画结束态渲染，一次滑入即可。
 */
const STAGGER_LIMIT = 12;

export function PillSelect<T extends string | number>({
  value,
  options,
  onChange,
  className = "",
  align = "start",
  maxHeight = 300,
  placeholder = "请选择",
  title,
  ariaLabel,
}: PillSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  /** 展开动画：每次打开时 +1，作为 key 让 CSS 动画重放 */
  const [round, setRound] = useState(0);
  /**
   * 自绘 tooltip（替代原生 title）。
   * 只保存"当前悬停项 + 文本"，面板一关就清空 ——
   * 原生 tooltip 无法从 JS 主动关掉，这正是上一版气泡残留的原因。
   */
  const [tip, setTip] = useState<{ text: string; top: number } | null>(null);

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const current = options.find((o) => o.value === value) ?? options[0];

  const openMenu = useCallback(() => {
    const i = options.findIndex((o) => o.value === value);
    setActive(i < 0 ? 0 : i);
    setRound((r) => r + 1);
    setOpen(true);
  }, [options, value]);

  const close = useCallback(
    (refocus = true) => {
      setOpen(false);
      // 关键：收起时必须清掉 tooltip，否则它会跟着面板一起"遗留"在页面上
      setTip(null);
      if (refocus) triggerRef.current?.focus();
    },
    [],
  );

  /* ---- 点外部关闭 ---- */
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setTip(null);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown, { passive: true });
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [open]);

  /* ---- 打开后把高亮项滚进可视区 ---- */
  useEffect(() => {
    if (!open) return;
    const list = listRef.current;
    if (!list) return;
    const el = list.querySelector<HTMLElement>(`[data-idx="${active}"]`);
    if (!el) return;
    const top = el.offsetTop;
    const bottom = top + el.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top - 6;
    else if (bottom > list.scrollTop + list.clientHeight)
      list.scrollTop = bottom - list.clientHeight + 6;
  }, [open, active]);

  const commit = (v: T) => {
    onChange(v);
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        openMenu();
      }
      return;
    }
    switch (e.key) {
      case "Escape":
        e.preventDefault();
        close();
        break;
      case "ArrowDown":
        e.preventDefault();
        setActive((i) => Math.min(options.length - 1, i + 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
        break;
      case "Home":
        e.preventDefault();
        setActive(0);
        break;
      case "End":
        e.preventDefault();
        setActive(options.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (options[active]) commit(options[active].value);
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  };

  return (
    <div ref={rootRef} className={`relative inline-block ${className}`}>
      {/* 触发器：胶囊，无方框，只有一层浅浅的底 */}
      <button
        ref={triggerRef}
        type="button"
        /* 不写 title：与选项同理，原生 tooltip 只能靠鼠标移动关掉 */
        aria-label={ariaLabel ?? title}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onKeyDown}
        className={`group flex w-full items-center gap-2 rounded-full border border-line bg-surface py-1.5 pl-3.5 pr-2.5 text-left text-[12.5px] text-fg outline-none transition-colors hover:border-accent/50 hover:bg-surface2 ${
          open ? "border-accent/60 bg-surface2" : ""
        }`}
      >
        <span className="min-w-0 flex-1 truncate">{current?.label ?? placeholder}</span>
        {/* 箭头：展开时旋转 180°，悬停/展开时变成主色 */}
        <svg
          viewBox="0 0 24 24"
          className={`h-3.5 w-3.5 shrink-0 transition-transform duration-300 ${
            open ? "rotate-180 text-accentInk" : "text-muted group-hover:text-accentInk"
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {/* 面板：**没有边框**，只靠深底 + 阴影浮起来 */}
      {open && (
        <div
          className={`absolute z-50 mt-1.5 min-w-full ${align === "end" ? "right-0" : "left-0"}`}
          style={{ width: "max-content", maxWidth: "min(92vw, 460px)" }}
        >
          <div
            ref={listRef}
            id={listId}
            role="listbox"
            tabIndex={-1}
            aria-activedescendant={`${listId}-${active}`}
            onKeyDown={onKeyDown}
            /* 底色写在 inline style 里：面板要压在 ECharts canvas 之上，
               Tailwind 的任意值底色若被 purge/顺序影响会变成透明，
               下面卡片的内容就会透上来（实测过，很难看）。
               浅色主题下用纯白，靠阴影和细边把浮层"抬"起来。 */
            className="scrollbar-slim overflow-y-auto rounded-[22px] p-1.5 shadow-[0_18px_50px_-12px_rgba(16,32,58,.28),0_0_0_1px_rgba(16,32,58,.08)]"
            style={{ maxHeight, backgroundColor: "#ffffff" }}
          >
            {options.map((o, i) => {
              const selected = o.value === value;
              const isActive = i === active;
              return (
                <div
                  key={`${round}-${String(o.value)}`}
                  id={`${listId}-${i}`}
                  data-idx={i}
                  role="option"
                  aria-selected={selected}
                  /* 不要用原生 title：原生 tooltip 只在**鼠标移动**时消失，
                     点选后面板关闭、光标原地不动，气泡就一直挂在那里（实测复现过）。
                     改为 hover 时才挂载的自绘 tooltip，组件卸载即随之消失。 */
                  onMouseEnter={(e) => {
                    setActive(i);
                    // top 取鼠标相对面板的位置：面板内部可滚动，
                    // 用 index*行高 在滚动后会错位
                    const host = listRef.current;
                    const top = host
                      ? e.clientY - host.getBoundingClientRect().top + host.scrollTop
                      : 0;
                    setTip({ text: o.hint ? `${o.label} · ${o.hint}` : o.label, top });
                  }}
                  onMouseLeave={() => setTip(null)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => commit(o.value)}
                  /* 逐条滑入：从左侧 + 轻微下沉开始，按 index 错峰 */
                  className={`pill-option flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-full py-[7px] pl-3.5 pr-3 text-[12.5px] leading-none transition-colors ${
                    selected
                      ? "bg-accent/12 font-medium text-accentInk"
                      : isActive
                        ? "bg-surface2 text-fg"
                        : "text-fg/80"
                  }`}
                  style={{
                    animationDelay: `${Math.min(i, STAGGER_LIMIT) * STAGGER}ms`,
                    animationDuration: `${ITEM_DURATION}ms`,
                  }}
                >
                  <span className="truncate">{o.label}</span>
                  {o.hint && (
                    <span
                      className={`tnum ml-auto shrink-0 pl-2 text-[11.5px] ${
                        selected ? "text-accentInk" : "text-muted/80"
                      }`}
                    >
                      {o.hint}
                    </span>
                  )}
                  {/* 选中标记：小圆点，比 ✓ 更轻 */}
                  {selected && (
                    <span className="ml-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  )}
                </div>
              );
            })}
          </div>

          {/* 自绘 tooltip：跟随鼠标，鼠标移开 / 面板关闭立即消失 */}
          {tip && (
            <div
              data-pill-tip
              role="tooltip"
              className="pointer-events-none absolute left-[calc(100%+10px)] z-50 max-w-[280px] whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] leading-none text-fg shadow-[0_8px_24px_-6px_rgba(16,32,58,.22),0_0_0_1px_rgba(16,32,58,.07)]"
              style={{ top: tip.top - 10, backgroundColor: "#ffffff" }}
            >
              {tip.text}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

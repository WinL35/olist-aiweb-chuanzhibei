"use client";

import { useEffect, useRef } from "react";

/**
 * 四个小人 —— 侧栏「智能问答」入口图标
 * ===================================
 *
 * 原型来自 animated-login-master 的 AnimatedCharacters（紫/黑/橙/黄四根柱子，
 * 眼珠追鼠标、眨眼、密码聚焦时集体闭眼）。搬到这里做了三处必要改造：
 *
 *   1. **插画 → 26px 图标**
 *      原作是 550×400 的登录页配图，柱子宽 120–180px。这里按 100×100 的
 *      「图标坐标系」重画，外层盒子决定显示尺寸，坐标全部按 100 单位写，
 *      所以 26px 和 84px 两种尺寸都只是等比缩放，不用改任何内部数字。
 *
 *   2. **GSAP quickTo → rAF 指数插值**
 *      原作 20 个通道全用 gsap.quickTo 做平滑。图标本身只有 26px，
 *      为了它引 70KB 的 GSAP 不划算，改成「每帧把当前值推向目标值 18%」，
 *      观感几乎一致（同样是减速跟随，不会突然跳）。
 *      瞳孔不插值、直接贴目标 —— 眼睛本来就该比身体跟得快。
 *
 *   3. **触发语义换成本项目的场景**
 *      图标旁边没有账号/密码输入框，原作的两个触发点改成：
 *        · 鼠标移动        → 眼球始终追鼠标（保留，且是常驻的）
 *        · 悬停导航栏按钮   → 四个小人一起侧身，朝向悬停的那个按钮
 *        · 点击导航栏按钮   → 触发原作「对视」那一下：紫、黑两个小人互相看一眼，
 *                            身子轻微错开，350ms 后复位
 *
 * 组件本身不读 DOM 外部状态，全部靠 props 驱动，方便在别处复用。
 */

/** 身体通道的跟随速率：每帧走完剩余距离的 18% */
const BODY_EASE = 0.18;
/** 瞳孔的贴向速率（基本等于直接贴，留一点点缓冲避免抖动） */
const EYE_EASE = 0.6;

type BodyKey =
  | "purpleX"
  | "purpleH"
  | "purpleSkew"
  | "purpleFaceX"
  | "purpleFaceY"
  | "blackX"
  | "blackSkew"
  | "blackFaceX"
  | "blackFaceY"
  | "orangeFaceX"
  | "orangeFaceY"
  | "yellowFaceX"
  | "yellowFaceY";

const initialBody = (): Record<BodyKey, number> => ({
  purpleX: 0,
  purpleH: 0,
  purpleSkew: 0,
  purpleFaceX: 0,
  purpleFaceY: 0,
  blackX: 0,
  blackSkew: 0,
  blackFaceX: 0,
  blackFaceY: 0,
  orangeFaceX: 0,
  orangeFaceY: 0,
  yellowFaceX: 0,
  yellowFaceY: 0,
});

export interface NavCharactersProps {
  /** 外层尺寸，默认与其它导航图标一致：26×26 */
  className?: string;
  /** 是否处于「悬停导航栏」状态 */
  hovered?: boolean;
  /** 悬停目标在导航列里的相对位置 0（顶）→ 1（底），决定侧身方向 */
  gazeRatio?: number;
  /** 每次变化触发一次「对视」脉冲（传入一个自增值即可） */
  pulse?: number;
}

export function NavCharacters({
  className = "h-[26px] w-[26px]",
  hovered = false,
  gazeRatio = 0.5,
  pulse = 0,
}: NavCharactersProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const purpleRef = useRef<HTMLDivElement>(null);
  const blackRef = useRef<HTMLDivElement>(null);
  const orangeRef = useRef<HTMLDivElement>(null);
  const yellowRef = useRef<HTMLDivElement>(null);
  const purpleFaceRef = useRef<HTMLDivElement>(null);
  const blackFaceRef = useRef<HTMLDivElement>(null);
  const orangeFaceRef = useRef<HTMLDivElement>(null);
  const yellowFaceRef = useRef<HTMLDivElement>(null);

  const cur = useRef(initialBody());
  const tgt = useRef(initialBody());
  const eye = useRef({ x: 0, y: 0 });
  const eyeTarget = useRef({ x: 0, y: 0 });

  /** 鼠标视口坐标；还没动过鼠标时为 null，此时默认看向正前方 */
  const mouse = useRef<{ x: number; y: number } | null>(null);
  /** 对视状态：由 pulse 触发，到期自动恢复 */
  const lookUntil = useRef(0);
  const rafRef = useRef(0);

  /* ---------- ① 主循环：算目标 → 插值 → 写内联样式（不触发 React 渲染） ---------- */
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const onMove = (e: MouseEvent) => {
      mouse.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener("mousemove", onMove, { passive: true });

    const plan = () => {
      const box = root.getBoundingClientRect();
      const looking = performance.now() < lookUntil.current;

      // 悬停时眼睛看向「悬停点」，不悬停时看鼠标
      const src = hovered
        ? { x: box.left + box.width / 2, y: box.top + box.height * gazeRatio }
        : mouse.current;

      if (looking) {
        /* 原作的「对视」：紫色往右下、黑色往左上，黑小人身子再错开一点 */
        Object.assign(tgt.current, {
          purpleX: 0,
          purpleH: 0,
          purpleSkew: -4,
          purpleFaceX: 9,
          purpleFaceY: 7,
          blackX: 4,
          blackSkew: 7,
          blackFaceX: -8,
          blackFaceY: -8,
          orangeFaceX: 6,
          orangeFaceY: 2,
          yellowFaceX: -6,
          yellowFaceY: -3,
        });
        eyeTarget.current = { x: 2, y: 1.8 };
        return;
      }

      const t = tgt.current;
      if (!src) {
        // 鼠标未就绪：全部回正
        t.purpleSkew = 0;
        t.purpleX = 0;
        t.purpleH = 0;
        t.purpleFaceX = 0;
        t.purpleFaceY = 0;
        t.blackSkew = 0;
        t.blackX = 0;
        t.blackFaceX = 0;
        t.blackFaceY = 0;
        t.orangeFaceX = 0;
        t.orangeFaceY = 0;
        t.yellowFaceX = 0;
        t.yellowFaceY = 0;
        eyeTarget.current = { x: 0, y: 0 };
        return;
      }

      // 悬停整体侧身：gazeRatio 0→1 映射成 -1→+1，乘以 6 度
      const lean = hovered ? (gazeRatio - 0.5) * 2 : 0;

      /** 把「朝目标的偏移」换算成身体斜度和脸部平移，全部夹在图标可容纳的范围内 */
      const look = (dx: number, dy: number) => ({
        skew: clamp(-dx / 90, -6, 6) + lean * 3,
        fx: clamp(dx / 22, -5, 5) + lean * 2,
        fy: clamp(dy / 30, -3, 3),
      });

      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      const P = look(src.x - cx - 4, src.y - cy);
      const B = look(src.x - cx - 1, src.y - cy);
      const O = look(src.x - cx + 5, src.y - cy + 4);

      Object.assign(tgt.current, {
        purpleSkew: P.skew,
        purpleX: lean * 1.6,
        purpleH: hovered ? -5 : 0,
        purpleFaceX: P.fx,
        purpleFaceY: P.fy,
        blackSkew: B.skew * 1.4,
        blackX: lean * 1.2,
        blackFaceX: B.fx,
        blackFaceY: B.fy,
        orangeFaceX: O.fx,
        orangeFaceY: O.fy,
        yellowFaceX: O.fx * -0.8,
        yellowFaceY: O.fy * 0.8,
      });

      /* 瞳孔：把屏幕偏移方向换算成图标坐标系（100 单位）下的位移 */
      const dx = src.x - cx;
      const dy = src.y - cy;
      const len = Math.hypot(dx, dy) || 1;
      const reach = Math.min(len / 60, 1);
      eyeTarget.current = { x: (dx / len) * reach * 2.4, y: (dy / len) * reach * 2.4 };
    };

    const write = () => {
      const c = cur.current;
      const t = tgt.current;
      (Object.keys(t) as BodyKey[]).forEach((k) => {
        c[k] += (t[k] - c[k]) * BODY_EASE;
      });
      eye.current.x += (eyeTarget.current.x - eye.current.x) * EYE_EASE;
      eye.current.y += (eyeTarget.current.y - eye.current.y) * EYE_EASE;

      const p = purpleRef.current;
      if (p) {
        p.style.transform = `translateX(${c.purpleX}px) skewX(${c.purpleSkew}deg)`;
        p.style.height = `calc(96% + ${c.purpleH}px)`;
      }
      const b = blackRef.current;
      if (b) b.style.transform = `translateX(${c.blackX}px) skewX(${c.blackSkew}deg)`;

      // 脸部/瞳孔的位移量按根节点尺寸换算成百分比：
      // 这样 26px 图标里是 0.3px 级微动、84px 卡片里是 1px 级，视觉比例一致。
      const unit = root.clientWidth || 26;
      const face = (el: HTMLDivElement | null, x: number, y: number) => {
        if (el) el.style.transform = `translate(${(x / unit) * 100}%, ${(y / unit) * 100}%)`;
      };
      face(purpleFaceRef.current, c.purpleFaceX, c.purpleFaceY);
      face(blackFaceRef.current, c.blackFaceX, c.blackFaceY);
      face(orangeFaceRef.current, c.orangeFaceX, c.orangeFaceY);
      face(yellowFaceRef.current, c.yellowFaceX, c.yellowFaceY);

      root.querySelectorAll<HTMLElement>("[data-pupil]").forEach((el) => {
        const k = Number(el.dataset.pupil) || 1;
        const dx = (eye.current.x * k * 100) / unit;
        const dy = (eye.current.y * k * 100) / unit;
        el.style.transform = `translate(${dx}%, ${dy}%)`;
      });
    };

    const tick = () => {
      plan();
      write();
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(rafRef.current);
    };
  }, [hovered, gazeRatio]);

  /* ---------- ② 点击脉冲：进入对视 350ms ---------- */
  useEffect(() => {
    if (!pulse) return;
    lookUntil.current = performance.now() + 350;
  }, [pulse]);

  /**
   * 画布是 100×100，四根柱子横向铺满、底部齐平。
   *
   * 坐标按原作 550×400 画布等比换算：
   *   紫  left 70/550=13%  w 180/550=33%  h 100%
   *   黑  left 240/550=44% w 120/550=22% h 78%
   *   橙  left 0        w 240/550=44% h 50%
   *   黄  left 310/550=56% w 140/550=25% h 58%
   * 图层顺序：紫 z1 → 黑 z2 → 橙 z3 → 黄 z4（橙遮住紫的下半身，与原作一致）。
   */
  const PAD = 6;
  const span = 100 - PAD * 2;

  return (
    <div
      ref={rootRef}
      className={`relative ${className}`}
      aria-hidden="true"
    >
      {/*
        ⚠️ 这里绝对不能加 filter / transform / perspective / contain。
        它们会让本元素成为后代的"包含块"，下面所有子元素的 % 定位就不再相对
        这个 52px 的盒子，而是相对最近的包含块（最终是视口）——
        结果就是四根柱子被撑到全屏大小，整页变成四根巨大的蓝紫柱子。
        （曾经加过 filter: drop-shadow(...)，就是这个故障。）

        深浅对比改用「给柱子加一圈极细的深色描边」实现，效果等价且无副作用。
      */}
      {/* 紫色：最高，被橙色遮住下半身（这就是原作里"只露出上半截"的来源） */}
      <div
        ref={purpleRef}
        className="absolute bottom-0 rounded-t-[2px]"
        style={{
          left: `${PAD + span * 0.09}%`,
          width: `${span * 0.3}%`,
          height: "96%",
          background: "#6C3FF5",
          transformOrigin: "bottom center",
          zIndex: 1,
          willChange: "transform, height",
        }}
      >
        <div ref={purpleFaceRef} className="absolute" style={{ left: "24%", top: "5%", width: "52%", height: "9%" }}>
          <FacePair size={0.42} pupil={0.5} />
        </div>
      </div>

      {/* 黑色：细高个 */}
      <div
        ref={blackRef}
        className="absolute bottom-0 rounded-t-[1.5px]"
        style={{
          left: `${PAD + span * 0.44}%`,
          width: `${span * 0.19}%`,
          height: "75%",
          // 原作是 #2D2D2D，但侧栏面板是 #35363a，两者明度几乎相同会糊在一起。
          // 提到 #1b1c1f（更暗）+ 一圈 0.5px 半透明白描边做轮廓，
          // 既不改变"黑小人"的语义，又能从深灰底上分离出来。
          background: "#1b1c1f",
          boxShadow: "0 0 0 0.5px rgba(255,255,255,.28)",
          transformOrigin: "bottom center",
          zIndex: 2,
          willChange: "transform",
        }}
      >
        <div ref={blackFaceRef} className="absolute" style={{ left: "14%", top: "7%", width: "72%", height: "10%" }}>
          <FacePair size={0.4} pupil={0.5} />
        </div>
      </div>

      {/* 橙色：最胖最矮，在最前层，眼睛是纯黑点（原作如此，没有眼白） */}
      <div
        ref={orangeRef}
        className="absolute bottom-0"
        style={{
          left: `${PAD}%`,
          width: `${span * 0.42}%`,
          height: "48%",
          background: "#FF9B6B",
          borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
          transformOrigin: "bottom center",
          zIndex: 3,
          willChange: "transform",
        }}
      >
        <div ref={orangeFaceRef} className="absolute" style={{ left: "14%", top: "32%", width: "60%", height: "14%" }}>
          <FacePair size={0.16} pupil={1} filled />
        </div>
      </div>

      {/* 黄色：小圆头，有嘴 */}
      <div
        ref={yellowRef}
        className="absolute bottom-0"
        style={{
          left: `${PAD + span * 0.58}%`,
          width: `${span * 0.24}%`,
          height: "56%",
          background: "#E8D754",
          borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
          transformOrigin: "bottom center",
          zIndex: 4,
          willChange: "transform",
        }}
      >
        <div ref={yellowFaceRef} className="absolute inset-0">
          <div className="absolute" style={{ left: "18%", top: "24%", width: "64%", height: "18%" }}>
            <FacePair size={0.26} pupil={1} filled />
          </div>
          <span
            className="absolute rounded-full bg-[#2D2D2D]"
            style={{ left: "28%", top: "52%", width: "44%", height: "5.5%" }}
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}

/**
 * 一对眼睛：左右两只用绝对定位钉在脸部容器两端，不做 flex（窄容器里 flex 会把
 * 百分比宽度收缩到 0，眼睛直接消失）。
 *
 * 脸部容器自带 padding，所以这里的 left:0 / right:0 其实落在容器内沿，
 * 眼睛不会顶到柱子的边上。
 */
function FacePair({
  size,
  pupil,
  filled = false,
}: {
  size: number;
  pupil: number;
  filled?: boolean;
}) {
  const w = `${size * 100}%`;
  const dot = `${Math.max(pupil, 0.5) * 100}%`;

  return (
    <>
      {(["left", "right"] as const).map((side) => (
        // 外框只负责定位 + 用 padding-bottom 撑成正方形。
        // 不用 aspect-ratio：父容器（脸）高度由百分比给定，在某些比例下
        // aspect-ratio 会被 height 约束压扁，出现"横条眼睛"。
        <span
          key={side}
          className="absolute top-0 block"
          style={{ [side]: 0, width: w, paddingBottom: w, height: 0 }}
        >
          <span
            className="absolute inset-0 flex items-center justify-center overflow-hidden rounded-full"
            style={{ background: filled ? "#2D2D2D" : "#fff" }}
          >
            {!filled && (
              <span
                data-pupil={1}
                className="rounded-full bg-[#2D2D2D]"
                style={{ width: dot, height: dot, willChange: "transform" }}
              />
            )}
          </span>
        </span>
      ))}
    </>
  );
}

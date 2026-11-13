"use client";

import { useEffect, useRef } from "react";

/**
 * 四个小人 —— 侧栏「智能问答」入口图标
 * ===================================
 *
 * 原型来自 animated-login-master 的 AnimatedCharacters（紫/黑/橙/黄四根柱子）。
 *
 * ── 这一版重做了「动态」，参考录屏逐帧量出来的原作用量 ──────────────
 * 原素材（1276×1266，紫柱高约 250px）实测：
 *   · 紫柱身横向摆动  −30px ~ +18px   即 ±12% 柱高
 *   · 眼白整体位移    ±8px，瞳孔再在眼白内偏 1/3
 *   · 所有柱子**都**跟着动，不是只有紫黑两个
 * 之前的实现把 skew 夹在 ±6°、脸部平移夹在 ±5%，在 52px 的图标里几乎看不出来。
 * 现在改为「整体倾斜 + 逐柱位移 + 大幅瞳孔位移」三者叠加，
 * 并且位移量统一按 root 宽度的百分比计算，52px 和 96px 两档视觉比例一致。
 *
 * ── 触发语义（原作是账号框/密码框聚焦，这里换成导航栏）──────────────
 *   · 鼠标移动          → 全体身体 + 眼睛追鼠标（常驻）
 *   · 悬停导航按钮       → 额外侧身，朝向悬停的那个按钮
 *   · 点击导航按钮 / 入口 → 一次「对视」脉冲：紫黑互看，身子错开，420ms
 *
 * 不引 GSAP：原作 20 个通道用 gsap.quickTo，为这个图标引 70KB 不划算，
 * 用 rAF 指数插值（每帧走完剩余距离的 16%/38%）观感一致。
 */

/**
 * 对视动作的三个阶段（毫秒，从点击导航那一刻算起）
 *
 *   0   ── 380   APPROACH  紫柱向上拉高 + 向右上甩出，眼睛送到黑色柱子的**左上方**
 *   380 ─ 3380   GAZE      定住对视，整整 3 秒
 *   3380 ─ 3900  RETREAT   松开，各自回位
 *
 * 参考视频（20261113-0928-49）逐帧量出的原作用量，紫柱高 453px 时：
 *   · 顶边 y  124 → 66     即**长高 58px ≈ 13% 柱高**（拉高，这是主动作）
 *   · 顶边右端 x 230 → 431  向右甩出 201px ≈ 44% 柱宽（形成明显的右倾斜边）
 *   · 底边 x 几乎不动（+13px）—— 所以是「以底边为轴，上半身向右上甩出去」
 *   · 紫眼 y 124  vs 黑眼 y 300  → 紫眼比黑眼**高 176px ≈ 39% 柱高**
 *
 * ⚠️ 这个动作**不能**用 skewX 做：skew 是剪切变形，斜边会一路斜到底边，
 *    而原作是"整体变高 + 上半身甩出"，底边保持方正。必须 height + translateX。
 */
const APPROACH_MS = 380;
const GAZE_MS = 3380;
const RETREAT_MS = 3900;

/** 身体通道跟随速率：每帧走完剩余距离的比例 */
const BODY_EASE = 0.16;
/** 眼睛（眼白整体 + 瞳孔）追随速率，明显快于身体 */
const EYE_EASE = 0.38;

/** 四根柱子的 id */
type PillarId = "purple" | "black" | "orange" | "yellow";

const PILLAR_IDS: PillarId[] = ["purple", "black", "orange", "yellow"];

/** 每根柱子的动态通道：横向位移 / 斜度 / 纵向倾斜 / 伸长 / 脸部偏移 */
interface PillarState {
  x: number;
  skew: number;
  /** 纵向倾斜（skewY）：柱子不能上下平移，用这个表达"前倾/后仰" */
  skewY: number;
  /** 纵向伸长（%）：对视时紫色要"够得更长"，靠它而不是靠横向平移 */
  stretch: number;
  faceX: number;
  faceY: number;
}

type BodyState = Record<PillarId, PillarState>;

const zero = (): PillarState => ({ x: 0, skew: 0, skewY: 0, stretch: 0, faceX: 0, faceY: 0 });
const zeroAll = (): BodyState => ({
  purple: zero(),
  black: zero(),
  orange: zero(),
  yellow: zero(),
});

export interface NavCharactersProps {
  /** 外层尺寸。默认 26×26（与其它导航图标一致）；底部入口传更宽的尺寸 */
  className?: string;
  /** 是否处于「悬停导航栏」状态 */
  hovered?: boolean;
  /** 悬停目标在导航列里的相对位置 0（顶）→ 1（底），决定侧身方向 */
  gazeRatio?: number;
  /** 每次变化触发一次「对视」脉冲（传入一个自增值即可） */
  pulse?: number;
}

/**
 * 画布坐标（单位 %，按原作 550×400 等比换算）
 *
 *   紫  left 13%  w 33%  h 100%
 *   黑  left 44%  w 22%  h 78%
 *   橙  left 0    w 44%  h 50%
 *   黄  left 56%  w 25%  h 58%
 *
 * 每根柱子还有一个 weight（跟随鼠标的灵敏度）与 lag（相位差），
 * 让四者不同步地动 —— 原作里它们就是错拍的，整体更像"活物"。
 */
const LAYOUT: Record<
  PillarId,
  {
    left: number;
    width: number;
    height: number;
    z: number;
    weight: number;
    /** 动态幅度系数：柱子越高越要收（倾斜时顶端甩得远，容易出框） */
    swing: number;
    /** 脸部自身位移的缩放：脸越宽/越胖，位移要越小才不会让眼睛跑出轮廓 */
    faceScale: number;
    tint: string;
  }
> = {
  purple: { left: 13, width: 33, height: 92, z: 1, weight: 1.0, swing: 0.56, faceScale: 0.8, tint: "#6C3FF5" },
  black: { left: 44, width: 22, height: 66, z: 2, weight: 1.25, swing: 0.82, faceScale: 0.85, tint: "#1b1c1f" },
  orange: { left: 0, width: 44, height: 50, z: 3, weight: 0.8, swing: 1.0, faceScale: 0.3, tint: "#FF9B6B" },
  yellow: { left: 56, width: 25, height: 48, z: 4, weight: 0.95, swing: 1.0, faceScale: 0.38, tint: "#E8D754" },
};

export function NavCharacters({
  className = "h-[26px] w-[26px]",
  hovered = false,
  gazeRatio = 0.5,
  pulse = 0,
}: NavCharactersProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  /** 四根柱子的 DOM —— 用 Map 存，避免为每根柱子各写一个 ref */
  const pillarRefs = useRef<Record<PillarId, HTMLDivElement | null>>({
    purple: null,
    black: null,
    orange: null,
    yellow: null,
  });
  const faceRefs = useRef<Record<PillarId, HTMLDivElement | null>>({
    purple: null,
    black: null,
    orange: null,
    yellow: null,
  });

  const cur = useRef<BodyState>(zeroAll());
  const tgt = useRef<BodyState>(zeroAll());
  /** 眼白整体位移（图标坐标系，单位 = root 宽度的 1%） */
  const eye = useRef({ x: 0, y: 0 });
  const eyeTarget = useRef({ x: 0, y: 0 });
  /** 瞳孔在眼白内的额外位移比例 -1~1 */
  const pupil = useRef({ x: 0, y: 0 });

  /** 鼠标视口坐标；没动过鼠标时为 null，此时全部回正 */
  const mouse = useRef<{ x: number; y: number } | null>(null);
  /** 对视状态截止时间 */
  const lookUntil = useRef(0);
  /** 对视起始时刻 —— 三阶段包络按它算 elapsed */
  const lookStart = useRef(-1e9);
  const rafRef = useRef(0);

  /** 把 props 的实时值放进 ref，避免每次变化都重建 rAF 循环 */
  const propsRef = useRef({ hovered, gazeRatio });
  propsRef.current = { hovered, gazeRatio };

  /* ---------- ① 主循环 ---------- */
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const onMove = (e: MouseEvent) => {
      mouse.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener("mousemove", onMove, { passive: true });

    const plan = () => {
      const box = root.getBoundingClientRect();
      const { hovered: hv, gazeRatio: gr } = propsRef.current;
      const looking = performance.now() - lookStart.current < RETREAT_MS;
      const T = tgt.current;

      /* ---- 对视三阶段：靠近 → 定住对视 → 离开 ---- */
      const elapsed = performance.now() - lookStart.current;
      if (elapsed < RETREAT_MS) {
        /* 包络 e：0（松开）→ 1（凑到位）→ 0（撤离）。
           靠近用 ease-out（起步快，像"探身"），撤离用 ease-in-out 更柔和。 */
        const e =
          elapsed < APPROACH_MS
            ? easeOut(elapsed / APPROACH_MS)
            : elapsed < GAZE_MS
              ? 1
              : 1 - easeInOut((elapsed - GAZE_MS) / (RETREAT_MS - GAZE_MS));

        /* ⚠️ 紫柱的动作必须是「拉高 + 向右上甩出」。
           参考视频量出来的三个量（紫柱高 453px 换算成 84×72 图标的比例）：
             · 长高   +58/453 ≈ +13% 柱高          → stretch 正向
             · 顶边右移 +201/233 宽 ≈ 柱宽 86%      → x + skewX 合成
             · 底边几乎不动                        → transform-origin: bottom center
           倾斜一定给：只拉高+平移的话，紫柱还是一根直柱，看不出"甩出去"。
           skewX 以底边为轴，斜边向上越甩越开，正是原作那条斜右边。
           横向别给太满：给到 14 时紫柱右缘会压过黑柱左缘 7.8px（实测），
           把黑柱几乎完全盖住。这里 x 收到 4、倾斜给 −10°，紫柱仍明显"往右够"。 */
        const reach = elapsed < GAZE_MS ? e : 0;

        T.purple = {
          x: +6 * reach, // 整体右移：root 宽 84px，6 单位 ≈ 5px，让紫右眼贴到黑左眼
          // 负 skewX = 顶端向右甩（CSS skewX 负角度把上边缘推向 +x）
          // −10° 会让右缘盖到黑柱 13px（实测），收到 −6.5° 仍明显倾斜但不吞黑柱
          skew: -6.5 * reach,
          skewY: 0,
          stretch: 13 * e, // 拉高 13%：这就是用户说的"往上拉高"
          faceX: 0, // 脸跟着柱子走，不再额外挪
          /* 脸往下压：紫柱拉高后眼睛会跟着顶到 y≈9，比黑眼(≈36)差 26px，
             就成了"上下一前一后"而不是"平视对面"。
             压多少要配合黑柱抬多少一起算：紫压 +13、黑抬 −4。
             实测紫右眼 cy≈21.5 / 黑左眼 cy≈30.6，紫眼略高于黑眼 9px ——
             这样两只眼睛既能对望，又保留"下面那根仰头看"的高低差。
             ⚠️ 别压超过 22：脸会滑出柱身、压到橙色头上（试过，眼睛跑到柱子边缘）。 */
          faceY: 13 * e,
        };
        T.black = {
          x: 0,
          skew: 0,
          skewY: 0,
          stretch: 0,
          faceX: 0,
          /* 黑眼往上抬一点点迎上去。注意方向是**负**（往上），
             之前写 2.5 是往下，反而把差距拉得更大。 */
          faceY: -4 * e,
        };
        T.orange = { x: 0, skew: -1.5 * e, skewY: 0, stretch: 0, faceX: 1.5 * e, faceY: 1.5 * e };
        T.yellow = { x: 0, skew: 1.5 * e, skewY: 0, stretch: 0, faceX: -1.5 * e, faceY: -1.5 * e };

        /* 眼珠：**对视的关键在这里**。
           参考帧量出两对眼中心纵向只差 114px（520×600 画面），折算到 84×72 图标 ≈ 13.7px；
           而紫黑两只内眼横向必须贴住（间隙 ≈0），瞳孔再各自朝对方转过去。
           pupil.x 正 = 往右：紫眼往右（黑在它右边）、黑眼往左（紫在它左边）。
           pupil.y 正 = 往下：紫眼略往下、黑眼略往上，让视线在中间交汇。 */
        pupil.current = { x: 0.85 * e, y: 0.45 * e };
        eyeTarget.current = { x: 0.6, y: 0.3 };
        return;
      }

      const src = hv
        ? { x: box.left + box.width / 2, y: box.top + box.height * gr }
        : mouse.current;

      /* ---- 鼠标未就绪：全部回正 ---- */
      if (!src) {
        PILLAR_IDS.forEach((id) => {
          T[id] = zero();
        });
        eyeTarget.current = { x: 0, y: 0 };
        pupil.current = { x: 0, y: 0 };
        return;
      }

      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      const dx = src.x - cx;
      const dy = src.y - cy;

      /**
       * 归一化距离 −1…1。用 260px 做分母：鼠标在侧栏附近移动时就接近满幅，
       * 离开很远则饱和在 ±1，不会出现"越远越离谱"的过冲。
       */
      const nx = clamp(dx / 260, -1, 1);
      const ny = clamp(dy / 260, -1, 1);
      /** 悬停导航时的额外侧身：gazeRatio 0→1 映射成 −1→+1 */
      const lean = hv ? (gr - 0.5) * 2 : 0;

      PILLAR_IDS.forEach((id) => {
        const L = LAYOUT[id];
        // 每根柱子对同一鼠标位置的反应强度不同（weight），再叠一点横向偏好
        const wx = nx * L.weight + lean * 0.55;
        /**
         * 幅度还要乘 L.swing：柱子越高，同样角度下顶部甩得越远。
         * 若不区分，紫色（满高）倾 16° 会直接顶出画框，把眼睛裁掉；
         * 而黑色（78%）和橙黄（50%/58%）还有余量。
         */
        const s = L.swing;
        T[id] = {
          // 横向整体平移：最大 ±13%（相对 root 宽度）。84px 图标 ≈ ±11px
          x: clamp(wx * 13 * s, -13 * s, 13 * s),
          /**
           * ⚠️ 日常跟随**不要给 skew**。
           * 参考视频里四根柱子静止时全是垂直的，只在被点击后才出现斜边。
           * 之前这里给了 ±16°·swing，鼠标在右上角时紫柱被压成 10° 斜柱
           * （实测顶边相对底边左偏 80px），看起来整根柱子是歪的 —— 这就是"没在对视"的错觉源。
           * 现在日常只保留很小的 skew（≤3°）作为"活着"的细微呼吸，
           * 大幅倾斜只在对视阶段出现。
           */
          skew: clamp(wx * 3, -3 * s, 3 * s),
          // 纵向看：柱子不能上下平移（会脱出剪影），改用 skewY 做前倾/后仰，
          // 因为底边固定，skewY 的效果是"上半身朝鼠标俯过去"
          skewY: clamp(ny * 5, -5 * s, 5 * s),
          /**
           * 脸部平移必须按**柱宽**收着给。
           * 之前 faceX 上限是 root 宽度的 ±9%（≈7.6px），可黑柱只有 15px 宽，
           * 脸一挪就带着眼睛跑出柱子，实测静止时黑柱两只眼睛悬在右边缘外。
           * 改成按柱宽比例：最多挪柱宽的 18%。
           */
          faceX: clamp(wx * 9 * L.faceScale, -9 * L.faceScale, 9 * L.faceScale) * (L.width / 33),
          faceY: clamp(ny * 7 * L.faceScale, -7 * L.faceScale, 7 * L.faceScale),
          // 伸长只在「对视」里用，日常跟随不拉伸
          stretch: 0,
        };
      });

      /* ---- 眼白整体位移 ----
         关键：眼睛的位移**不能**和身体的倾斜同向累加。
         身体向右倾 16° 时柱顶本身已经右移了十几像素，如果眼球再往右跑，
         就一起顶出画框（实测会压在柱顶边缘上）。
         所以这里给眼睛一个"反向补偿"，让它在视觉上定在原来的位置附近，
         真正产生"转头看"的是下面那层瞳孔位移。
         垂直方向同理：柱子 skewY 后顶边会上下错，眼睛跟着会被裁。 */
      eyeTarget.current = { x: clamp(nx * 2.2, -2.2, 2.2), y: clamp(ny * 1.6, -1.6, 1.6) };
      /* ---- 瞳孔在眼白内偏移：这才是"眼球转过去"的主力，幅度给足 ---- */
      pupil.current = { x: clamp(nx, -1, 1), y: clamp(ny, -1, 1) };
    };

    const write = () => {
      const c = cur.current;
      const T = tgt.current;

      PILLAR_IDS.forEach((id) => {
        const s = c[id];
        const t = T[id];
        s.x += (t.x - s.x) * BODY_EASE;
        s.skew += (t.skew - s.skew) * BODY_EASE;
        s.skewY += (t.skewY - s.skewY) * BODY_EASE;
        s.stretch += (t.stretch - s.stretch) * BODY_EASE;
        s.faceX += (t.faceX - s.faceX) * BODY_EASE;
        s.faceY += (t.faceY - s.faceY) * BODY_EASE;

        const el = pillarRefs.current[id];
        if (el) {
          // 位移用 px：百分比 translate 是相对元素自身宽度，四根柱子宽度不同
          // 会导致它们位移不一致，读 root 宽度当统一单位。
          const u = root.clientWidth || 84;
          // 顺序很关键：先 scaleY（以底边为轴向上长），再 skew，最后平移。
          // transform-origin 已在样式里设为 bottom center，所以伸长时底边不动。
          el.style.transform =
            `translateX(${(s.x / 100) * u}px) skewX(${s.skew}deg) skewY(${s.skewY}deg)` +
            ` scaleY(${1 + s.stretch / 100})`;
        }
      });

      /* 层级：**永远不换**。
         紫柱 z1、黑柱 z2、橙柱 z3、黄柱 z4 —— 这四层就是原作的剪影：
           · 紫的下半身被橙盖住 → 所以紫看起来是"从橙后面长出来的"
           · 黑的左半被紫压住、右半被黄压住 → 黑才是中间那根
         前几版曾经在对视时把紫提到 z2、黑压到 z1，想救紫色右眼，
         结果紫的下半身从橙后面冒出来，整个层次就散了 —— **不要动 z-index**。
         对视时紫色要往黑柱左上方去，眼睛本来就在黑柱左上方、不会被黑遮，
         所以根本不需要抬层级。 */

      eye.current.x += (eyeTarget.current.x - eye.current.x) * EYE_EASE;
      eye.current.y += (eyeTarget.current.y - eye.current.y) * EYE_EASE;

      const unit = root.clientWidth || 26;

      // 脸部：translate 的百分比是相对**自身**尺寸，不是 root。
      // 所以按 root 尺寸换算成绝对 px 更可控（52px 图标里 1 单位 = 0.52px）。
      PILLAR_IDS.forEach((id) => {
        const el = faceRefs.current[id];
        if (!el) return;
        const s = cur.current[id];
        el.style.transform = `translate(${(s.faceX / 100) * unit}px, ${(s.faceY / 100) * unit}px)`;
      });

      /* 眼白：额外一层位移，叠在脸部容器上。
         ⚠️ 位移量必须按**各自柱宽**收缩，不能统一用 root 宽。
         黑柱只有 15px 宽、脸容器左右各只留 10%（1.5px）边距，
         用 root 宽的 ±2.2% 去推就是 ±1.85px，等于把眼睛顶出柱子右缘
         （实测超出 2.8px，截图上两只眼睛悬在黑柱外面）。
         这里用 el.dataset.eyeScale（渲染时写入的 柱宽/紫柱宽）做归一。 */
      root.querySelectorAll<HTMLElement>("[data-eye]").forEach((el) => {
        const k = Number(el.dataset.eyeScale) || 1;
        const ex = (eye.current.x / 100) * unit * k;
        const ey = (eye.current.y / 100) * unit * k;
        el.style.transform = `translate(${ex}px, ${ey}px)`;
      });

      // 瞳孔：在眼白盒子内部再按比例偏移（box 是 overflow:hidden，瞳孔跑不出眼眶）
      root.querySelectorAll<HTMLElement>("[data-pupil]").forEach((el) => {
        const k = Number(el.dataset.pupil) || 1;
        const px = pupil.current.x * 42 * k;
        const py = pupil.current.y * 42 * k;
        el.style.transform = `translate(${px}%, ${py}%)`;
      });
    };

    let prev = 0;
    const tick = (now: number) => {
      // 省电：页面不可见时跳过，回来时也不会因为时间跳跃而闪
      if (now - prev > 8 || prev === 0) {
        plan();
        write();
        prev = now;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  /* ---------- ② 对视脉冲 ---------- */
  useEffect(() => {
    if (!pulse) return;
    const now = performance.now();
    lookStart.current = now;
    lookUntil.current = now + RETREAT_MS;
  }, [pulse]);

  const PAD = 3;
  const span = 100 - PAD * 2;

  return (
    <div
      ref={rootRef}
      className={`relative ${className}`}
      aria-hidden="true"
    >
      {/*
        ⚠️ 这里绝对不能加 filter / transform / perspective / contain。
        它们会让本元素成为后代的"包含块"，子元素的 % 定位就不再相对
        这个盒子，而是相对最近的包含块（最终是视口）——
        结果就是四根柱子被撑到全屏。深浅对比改用描边实现。

        另：transform 由 rAF 直接写 style，不要在这里写 Tailwind 的
        transition-transform，否则每帧插值会被 CSS 过渡二次平滑，变得迟钝。
      */}
      {/* 紫色：最高，被橙色遮住下半身（这就是"只露出上半截"的来源） */}
      <div
        ref={(el) => {
          pillarRefs.current.purple = el;
        }}
        className="absolute bottom-0 rounded-t-[2px]"
        style={{
          left: `${PAD + span * 0.09}%`,
          width: `${span * 0.3}%`,
          // 96%：横向倾斜最多把顶端吃掉 5.2px（见 char3/check.py 的 outTop），
          // 所以还能留到 96%，比黑色(76%)长出整整 20% —— 对视时一眼能看出紫色更高
          height: "96%",
          background: LAYOUT.purple.tint,
          transformOrigin: "bottom center",
          zIndex: 1,
          willChange: "transform",
        }}
      >
        <div
          ref={(el) => {
            faceRefs.current.purple = el;
          }}
          className="absolute"
          style={{ left: "13%", top: "15%", width: "62%", height: "14%", willChange: "transform" }}
        >
          <FacePair eyeDot={0.42} pupil={0.46} />
        </div>
      </div>

      {/* 黑色：细高个。原作 #2D2D2D，面板 #35363a 上会糊在一起，
          所以压到 #1b1c1f 再加 0.5px 半透明描边勾勒轮廓 */}
      <div
        ref={(el) => {
          pillarRefs.current.black = el;
        }}
        className="absolute bottom-0 rounded-t-[1.5px]"
        style={{
          left: `${PAD + span * 0.44}%`,
          width: `${span * 0.19}%`,
          height: "66%",
          background: LAYOUT.black.tint,
          boxShadow: "0 0 0 0.5px rgba(255,255,255,.3)",
          transformOrigin: "bottom center",
          zIndex: 2,
          willChange: "transform",
        }}
      >
        <div
          ref={(el) => {
            faceRefs.current.black = el;
          }}
          className="absolute"
          style={{ left: "16%", top: "15%", width: "68%", height: "15%", willChange: "transform" }}
        >
          <FacePair eyeDot={0.44} pupil={0.46} eyeScale={0.3} />
        </div>
      </div>

      {/* 橙色：最胖最矮，最前层，眼睛是纯黑点（原作如此，没有眼白） */}
      <div
        ref={(el) => {
          pillarRefs.current.orange = el;
        }}
        className="absolute bottom-0"
        style={{
          left: `${PAD}%`,
          width: `${span * 0.42}%`,
          height: "50%",
          background: LAYOUT.orange.tint,
          borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
          transformOrigin: "bottom center",
          zIndex: 3,
          willChange: "transform",
        }}
      >
        <div
          ref={(el) => {
            faceRefs.current.orange = el;
          }}
          className="absolute"
          style={{ left: "17%", top: "36%", width: "54%", height: "15%", willChange: "transform" }}
        >
          <FacePair eyeDot={0.2} pupil={1} filled />
        </div>
      </div>

      {/* 黄色：小圆头，有嘴 */}
      <div
        ref={(el) => {
          pillarRefs.current.yellow = el;
        }}
        className="absolute bottom-0"
        style={{
          left: `${PAD + span * 0.58}%`,
          width: `${span * 0.24}%`,
          height: "48%",
          background: LAYOUT.yellow.tint,
          borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
          transformOrigin: "bottom center",
          zIndex: 4,
          willChange: "transform",
        }}
      >
        <div
          ref={(el) => {
            faceRefs.current.yellow = el;
          }}
          className="absolute inset-0"
          style={{ willChange: "transform" }}
        >
          <div className="absolute" style={{ left: "22%", top: "28%", width: "56%", height: "19%" }}>
            <FacePair eyeDot={0.3} pupil={1} filled />
          </div>
          {/* 嘴：随脸部一起平移，不动 */}
          <span
            className="absolute rounded-full bg-[#2D2D2D]"
            style={{ left: "27%", top: "57%", width: "46%", height: "5.5%" }}
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

/* 对视包络用的三个缓动，t 都在 0…1 */
const easeOut = (t: number) => 1 - (1 - clamp(t, 0, 1)) ** 3;
const easeInOut = (t: number) => {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
};

/**
 * 一对眼睛。
 *
 * 三个坑，都踩过，注释留在这里防止回退：
 *   1. 不能用 flex 排两只眼 —— 容器窄到 3px 时 flex 会把百分比宽度按内容
 *      计算并收缩到 0，眼睛直接消失。必须 absolute 钉在两端。
 *   2. 不能用 aspect-ratio 做正圆 —— 脸容器高度是百分比，父高受限时
 *      aspect-ratio 会被压扁成"横条眼睛"。改用 padding-bottom 撑方形。
 *   3. 瞳孔要在 overflow:hidden 的眼眶里位移，且位移用 %（相对瞳孔自身），
 *      否则大尺寸时瞳孔会跑出眼眶。
 *
 * 有眼白的两只（紫、黑），眼白盒子外面还包了一层 [data-eye]，
 * 由 rAF 写 transform 做整体位移；瞳孔再用自己的 [data-pupil] 在眼眶内二次偏移。
 */
function FacePair({
  eyeDot,
  pupil,
  filled = false,
  eyeScale = 1,
}: {
  /** 眼白（或黑点）直径，相对脸部容器宽度 */
  eyeDot: number;
  /** 瞳孔占眼白的比例 */
  pupil: number;
  /** 无眼白，整只眼就是一个实心黑点 */
  filled?: boolean;
  /** 眼球整体位移的缩放：按柱宽/紫柱宽归一，窄柱（黑 22、黄 25）要收 */
  eyeScale?: number;
}) {
  const w = `${eyeDot * 100}%`;

  return (
    <>
      {(["left", "right"] as const).map((side) => (
        <span
          key={side}
          data-eye={filled ? undefined : ""}
          data-eye-scale={filled ? undefined : eyeScale}
          className="absolute top-0 block"
          style={{ [side]: 0, width: w, paddingBottom: w, height: 0, willChange: "transform" }}
        >
          <span
            className="absolute inset-0 flex items-center justify-center overflow-hidden rounded-full"
            style={{ background: filled ? "#2D2D2D" : "#fff" }}
          >
            {!filled && (
              <span
                data-pupil={1}
                className="block rounded-full bg-[#2D2D2D]"
                style={{ width: `${pupil * 100}%`, height: `${pupil * 100}%`, willChange: "transform" }}
              />
            )}
          </span>
        </span>
      ))}
    </>
  );
}

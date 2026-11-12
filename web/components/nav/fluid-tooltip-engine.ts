/**
 * 流体提示气泡（Fluid Tooltip）——框架无关的交互核心
 * =====================================================
 *
 * 目的：把"每个按钮各自弹一个小气泡"换成"全组共享一个胶囊窗口纵向滑行"。
 * 视觉上是气泡在动，但文字其实一动不动 —— 动的只有裁切窗口。
 *
 * 实现这个错觉靠的是**两层反向位移**：
 *   胶囊层  translateY(+y)   —— 窗口往下走
 *   轨道层  translateY(-y)   —— 内部文字被等量抵消，留在原地
 * 于是第 i 行文字永远停在"第 i 个按钮的中心高度"，而窗口走到哪，就露出哪一行。
 * 这才有"上沿露出新字、下沿被吃掉旧字"的双行裁切感，而不是淡入淡出。
 *
 * 约束（有意为之）：
 *   - 胶囊只创建一次、永久复用同一个 DOM 节点，不重建、不复制；
 *   - 所有补间都是对 {y, width, opacity} 三个数值插值，不碰布局属性；
 *   - 快速跨项时从"当前正在渲染的值"续接，不跳回上一个目标、不排队；
 *   - 不依赖任何动画库，rAF + 缓动函数即可，包体零增长。
 */

export interface FluidItem {
  id: string;
  /** 主标签：中文页面名 */
  label: string;
  /** 快捷键提示：纯视觉，不参与朗读 */
  hint?: string;
}

export interface FluidEngineOptions {
  /** 深灰面板，胶囊以它为定位父级（需要 position: relative） */
  panel: HTMLElement;
  items: FluidItem[];
  /** 与 items 一一对应的按钮元素（顺序必须一致） */
  buttons: HTMLElement[];
  /** 当前选中项 id，仅用于初始无障碍属性 */
  activeId?: string;
  /** 胶囊高度 px，需与 CSS 中的 --cap-h 一致 */
  capsuleHeight?: number;
  /** 胶囊左边缘相对面板左边的距离 px */
  offsetX?: number;
  /** 覆盖系统"减少动态效果"偏好 */
  reducedMotion?: boolean;
}

/** 指针离开后等这么久再收起：留出跨越按钮间隙的时间，避免闪烁 */
const HIDE_DELAY = 75;
/** 位移 / 宽度过渡时长（秒） */
const MOVE_DURATION = 0.43;
/** 透明度过渡时长（秒） */
const FADE_DURATION = 0.15;

/** expo.out：起步快、尾部极缓，是"流体滑到位"的关键手感 */
function easeExpoOut(t: number): number {
  return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

/** power2.out：柔和收尾，用于透明度，避免线性淡出的生硬感 */
function easePower2Out(t: number): number {
  return 1 - (1 - t) * (1 - t);
}

interface TweenHandle {
  cancel(): void;
}

/**
 * 极简补间器：只做 0→1 的进度驱动，由调用方决定把进度映射到什么属性。
 * 自己实现而不用 GSAP 的原因：全组件只用到一条缓动曲线插值，
 * 引入 24KB 的三方库不划算，也不利于"零依赖"的工程叙事。
 */
function makeTween(
  duration: number,
  ease: (t: number) => number,
  onUpdate: (progress: number) => void,
  onComplete?: () => void
): TweenHandle {
  let raf = 0;
  let start = 0;
  let cancelled = false;

  const step = (now: number) => {
    if (cancelled) return;
    if (!start) start = now;
    const t = duration <= 0 ? 1 : Math.min(1, (now - start) / (duration * 1000));
    onUpdate(ease(t));
    if (t < 1) {
      raf = requestAnimationFrame(step);
    } else {
      onComplete?.();
    }
  };
  raf = requestAnimationFrame(step);

  return {
    cancel() {
      cancelled = true;
      cancelAnimationFrame(raf);
    },
  };
}

/** 运行时状态：胶囊顶部坐标 y、宽度 width、不透明度 */
interface CapsuleState {
  y: number;
  width: number;
  opacity: number;
}

export class FluidTooltipEngine {
  private panel: HTMLElement;
  private items: FluidItem[];
  private buttons: HTMLElement[];
  private capsule: HTMLDivElement;
  private track: HTMLDivElement;
  private rows: HTMLDivElement[] = [];
  private activeTweens = new Set<TweenHandle>();
  private hideTimer: number | null = null;
  private ro: ResizeObserver | null = null;
  private reduced: boolean;
  private destroyed = false;

  /** 当前正在渲染的状态（补间断点续接的依据） */
  private state: CapsuleState = { y: 0, width: 0, opacity: 0 };
  /** 目标状态 */
  private target: CapsuleState = { y: 0, width: 0, opacity: 0 };
  /** 每行的"静止高度"（面板坐标系），由按钮中心推导 */
  private lineTops: number[] = [];
  /** 每行内容宽度（含左右内边距），测量得到 */
  private lineWidths: number[] = [];
  /** 当前展示的索引，-1 表示完全隐藏 */
  private shownIndex = -1;

  private readonly capsuleH: number;
  private readonly offsetX: number;
  private readonly moveTweens = { y: null as TweenHandle | null, fade: null as TweenHandle | null };

  constructor(opts: FluidEngineOptions) {
    this.panel = opts.panel;
    this.items = opts.items;
    this.buttons = opts.buttons;
    this.capsuleH = opts.capsuleHeight ?? 56;
    this.offsetX = opts.offsetX ?? 128;
    this.reduced =
      opts.reducedMotion ??
      (typeof window !== "undefined" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches);

    // ① 构建胶囊（只建一次）
    const capsule = document.createElement("div");
    capsule.className = "fluid-capsule";
    capsule.setAttribute("role", "tooltip");
    capsule.setAttribute("aria-hidden", "true");
    capsule.id = `fluid-cap-${Math.random().toString(36).slice(2, 9)}`;
    capsule.style.cssText = [
      "position:absolute",
      "pointer-events:none",
      "overflow:hidden",
      "display:block",
      `height:${this.capsuleH}px`,
      `border-radius:${this.capsuleH / 2}px`,
      "background:#1e1e23",
      "box-shadow:0 6px 22px rgba(27,32,58,.28)",
      `left:${this.offsetX}px`,
      "top:0",
      "opacity:0",
      "will-change:transform,width,opacity",
      "z-index:60",
    ].join(";");

    // ② 轨道层：与胶囊等量反向位移，抵消后文字不动
    const track = document.createElement("div");
    track.style.cssText = [
      "position:absolute",
      "inset:0",
      "will-change:transform",
    ].join(";");

    // ③ 每行内容：绝对定位，top 稍后按按钮中心算
    // 内边距 / 间距 / 字号与胶囊高度配套（胶囊 56px：0.875 倍于旧的 64px 版）。
    // 改 capsuleHeight 时这几个数要一起调，否则字会在胶囊里挤或飘。
    this.items.forEach((it) => {
      const row = document.createElement("div");
      row.style.cssText = [
        "position:absolute",
        "left:0",
        `height:${this.capsuleH}px`,
        "display:flex",
        "align-items:center",
        "width:max-content",
        "padding:0 22px",
        "gap:12px",
        "white-space:nowrap",
      ].join(";");

      const label = document.createElement("span");
      label.textContent = it.label;
      label.style.cssText =
        "font-size:23px;line-height:1;font-weight:600;letter-spacing:-.5px;color:#f2f2f3;" +
        "font-family:'Inter','Arial','Helvetica','Microsoft YaHei',sans-serif";
      row.appendChild(label);

      if (it.hint) {
        const hint = document.createElement("span");
        hint.textContent = it.hint;
        hint.style.cssText =
          "font-size:19px;line-height:1;font-weight:600;letter-spacing:-.8px;color:#89898e;" +
          "min-width:48px;text-align:right;" +
          "font-family:'Inter','Arial','Helvetica','Microsoft YaHei',sans-serif";
        row.appendChild(hint);
      }

      track.appendChild(row);
      this.rows.push(row);
    });

    capsule.appendChild(track);
    this.panel.appendChild(capsule);
    this.capsule = capsule;
    this.track = track;

    // ④ 几何测量 + 事件绑定
    this.measure();
    this.bind();

    // ⑤ 字体可能尚未就绪：此时测到的是回退字体的宽度，加载完必须重测
    if (document.fonts?.ready) {
      document.fonts.ready.then(() => {
        if (!this.destroyed) this.measure();
      });
    }

    // ⑥ 尺寸变化（窗口缩放 / 侧栏折叠）后行高与宽度都会变
    if (typeof ResizeObserver !== "undefined") {
      this.ro = new ResizeObserver(() => this.measure());
      this.ro.observe(this.panel);
    }

    // ⑦ 页面不可见时暂停补间，回来再继续，避免后台空转
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  /** 测量按钮中心 → 行 top；测量每行宽度 → 胶囊宽度 */
  private measure() {
    const panelRect = this.panel.getBoundingClientRect();
    this.lineTops = this.buttons.map((btn) => {
      const r = btn.getBoundingClientRect();
      // 按钮中心换算到面板坐标系，再减去半个胶囊高度 = 该行静止时的顶部
      const centerY = r.top - panelRect.top + r.height / 2;
      return centerY - this.capsuleH / 2;
    });

    this.rows.forEach((row, i) => {
      row.style.top = `${this.lineTops[i] ?? 0}px`;
      // scrollWidth 取整避免小数导致的 1px 抖动
      this.lineWidths[i] = Math.ceil(row.getBoundingClientRect().width);
    });

    // 测量后如果正在展示，宽度需立即跟上（否则换字体后胶囊会夹字）
    if (this.shownIndex >= 0 && this.state.opacity > 0) {
      const w = this.lineWidths[this.shownIndex] ?? this.state.width;
      this.state.width = w;
      this.target.width = w;
      this.capsule.style.width = `${w}px`;
    }
  }

  private bind() {
    this.buttons.forEach((btn, i) => {
      btn.addEventListener("pointerenter", () => this.onEnter(i));
      btn.addEventListener("focus", () => this.onEnter(i));
      btn.addEventListener("pointerleave", this.onLeave);
      btn.addEventListener("blur", this.onLeave);
    });
    this.panel.addEventListener("keydown", this.onKeyDown);
  }

  /** 进入某一项：取消隐藏计时器，向目标中心与新宽度滑去 */
  private onEnter(index: number) {
    if (this.destroyed) return;
    this.clearHideTimer();

    const firstShow = this.shownIndex < 0 || this.state.opacity <= 0.001;
    this.shownIndex = index;

    const targetY = this.lineTops[index] ?? 0;
    const targetW = this.lineWidths[index] ?? 0;

    this.capsule.style.width = `${this.state.width || targetW}px`;
    this.capsule.setAttribute("aria-hidden", "false");

    // 首次出现：直接把几何放到目标位置，只做透明度，不做位移（规格要求）
    if (firstShow) {
      this.applyState({ y: targetY, width: targetW, opacity: this.state.opacity });
      this.target = { y: targetY, width: targetW, opacity: 1 };
      this.startFade(1);
      this.syncAria(index);
      return;
    }

    this.target = { y: targetY, width: targetW, opacity: 1 };
    this.startMove();
    this.startFade(1);
    this.syncAria(index);
  }

  /** 离开：延迟 75ms 再淡出，给"跨过 9px 间隙"留余量 */
  private onLeave = () => {
    if (this.destroyed) return;
    this.clearHideTimer();
    this.hideTimer = window.setTimeout(() => {
      // 如果仍有本组件内的按钮持焦（键盘操作场景），不得收起
      if (this.buttons.some((b) => b === document.activeElement)) return;
      this.fadeOut();
    }, HIDE_DELAY);
  };

  private fadeOut() {
    this.shownIndex = -1;
    this.target = { ...this.state, opacity: 0 };
    this.startFade(0);
    this.capsule.setAttribute("aria-hidden", "true");
    this.buttons.forEach((b) => b.removeAttribute("aria-describedby"));
  }

  /** 位移补间：从"当前渲染值"续接，因此快速跨项不会回跳 */
  private startMove() {
    this.moveTweens.y?.cancel();
    const fromY = this.state.y;
    const fromW = this.state.width;
    const toY = this.target.y;
    const toW = this.target.width;

    if (this.reduced) {
      this.applyState({ ...this.state, y: toY, width: toW });
      return;
    }

    // 位移与宽度共用一条进度，保证"走得越远、变宽越快"的同步感
    const handle = makeTween(
      MOVE_DURATION,
      easeExpoOut,
      (p) => {
        this.applyState({
          ...this.state,
          y: fromY + (toY - fromY) * p,
          width: fromW + (toW - fromW) * p,
        });
      }
    );
    this.moveTweens.y = handle;
    this.activeTweens.add(handle);
  }

  private startFade(to: number) {
    this.moveTweens.fade?.cancel();

    if (this.reduced) {
      this.applyState({ ...this.state, opacity: to });
      return;
    }

    const from = this.state.opacity;
    const handle = makeTween(
      FADE_DURATION,
      easePower2Out,
      (p) => this.applyState({ ...this.state, opacity: from + (to - from) * p })
    );
    this.moveTweens.fade = handle;
    this.activeTweens.add(handle);
  }

  /** 唯一的写 DOM 出口：所有补间都只改这三个值 */
  private applyState(next: CapsuleState) {
    this.state = next;
    this.capsule.style.transform = `translate3d(0,${next.y}px,0)`;
    this.capsule.style.width = `${next.width}px`;
    this.capsule.style.opacity = String(next.opacity);
    // 反向抵消：文字在画布中的高度因此恒定不变
    this.track.style.transform = `translate3d(0,${-next.y}px,0)`;
  }

  /** 把 tooltip 关联到当前按钮，屏幕阅读器才会念出"名称 + 快捷键" */
  private syncAria(index: number) {
    const id = this.capsule.id;
    this.buttons.forEach((b, i) => {
      if (i === index) b.setAttribute("aria-describedby", id);
      else b.removeAttribute("aria-describedby");
    });
  }

  /** 方向键在项间循环移动焦点；Home/End 跳首尾；Esc 立即收起但保留焦点 */
  private onKeyDown = (e: KeyboardEvent) => {
    const idx = this.buttons.indexOf(document.activeElement as HTMLElement);
    if (idx < 0) return;
    let next = -1;

    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = (idx + 1) % this.buttons.length;
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft")
      next = (idx - 1 + this.buttons.length) % this.buttons.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = this.buttons.length - 1;
    else if (e.key === "Escape") {
      this.fadeOut();
      return;
    } else return;

    e.preventDefault();
    this.buttons[next]?.focus();
  };

  private onVisibility = () => {
    // 标签页隐藏时补间已由浏览器暂停；回到前台重新同步一次几何即可
    if (!document.hidden && !this.destroyed) this.measure();
  };

  private clearHideTimer() {
    if (this.hideTimer !== null) {
      window.clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
  }

  /** 外部强制收起（点击空白 / 外部区域时调用） */
  hide() {
    this.clearHideTimer();
    if (this.state.opacity > 0) this.fadeOut();
  }

  destroy() {
    this.destroyed = true;
    this.clearHideTimer();
    this.activeTweens.forEach((t) => t.cancel());
    this.activeTweens.clear();
    this.moveTweens.y?.cancel();
    this.moveTweens.fade?.cancel();
    this.ro?.disconnect();
    this.ro = null;
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.buttons.forEach((btn) => {
      btn.removeEventListener("pointerenter", this.onEnter as unknown as EventListener);
      btn.removeEventListener("pointerleave", this.onLeave);
      btn.removeEventListener("focus", this.onEnter as unknown as EventListener);
      btn.removeEventListener("blur", this.onLeave);
    });
    this.panel.removeEventListener("keydown", this.onKeyDown);
    this.capsule.remove();
    this.rows = [];
    this.buttons = [];
  }
}

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
  /**
   * 这次气泡是被什么唤起的。
   *
   * 用来区分「键盘聚焦」和「鼠标悬停」两种场景：
   *   · 键盘：按钮持焦即应持续显示，失焦才收 —— 这是可访问性要求
   *   · 鼠标：移开就该收，**不管焦点还在不在按钮上**
   *
   * 踩过的坑：原先 onLeave 里无条件检查 `document.activeElement` 是否在
   * 按钮组内，可鼠标点击导航后焦点本来就留在那个 <a> 上，
   * 于是鼠标移开了气泡也不收，一直挂在那里（实测复现）。
   */
  private showSource: "pointer" | "focus" | null = null;
  /** 已绑定的处理器引用，destroy() 时按引用精确解绑 */
  private handlers: {
    btn: HTMLElement;
    onPointerEnter: EventListener;
    onFocus: EventListener;
  }[] = [];

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
      /*
       * 翡翠绿气泡（2026-11-13 由 #1e1e23 近黑改来；2026-11-14 由 #10a37f 压深至 #0e9375）。
       *
       * 为什么要压深：主标签 23px/600 属 WCAG large text（门槛 3.0），#10a37f 上白字 3.20 勉强过；
       * 但快捷键提示 19px 只有 2.32，怎么都过不去。三条路里：
       *   ① 把提示字提到接近纯白 → 会和主标签抢视线，"次要"表达不出来；
       *   ② 把提示字撤成中性灰 → 绿底上必糊（#89898e 只有 1.09）；
       *   ③ 把背景压深 → 两个字的对比同时抬升，颜色观感几乎不变。
       * 选了 ③：#0e9375 上白字 3.85、#d4f5eb 3.31，都过 large text 门槛。
       *
       * 代价说明：绿底 vs 深灰侧栏 #35363a 从 3.77 掉到 3.13（仍高于非文字图形门槛 3.0），
       * 所以投影加深、加一道极细亮边勾勒轮廓，靠"浮起来"而不是"够亮"来区分层次。
       */
      "background:#0e9375",
      "box-shadow:0 6px 22px rgba(6,44,32,.42), inset 0 0 0 1px rgba(255,255,255,.16)",
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
      /*
       * 绿底上的主文字用纯白：23px/600 属于 WCAG 的 large text，门槛 3.0，实测 3.20 达标。
       * 原来跟着黑底用的 #f2f2f3 在绿底上只有 2.86，会有点发灰。
       */
      label.style.cssText =
        "font-size:23px;line-height:1;font-weight:600;letter-spacing:-.5px;color:#ffffff;" +
        "font-family:'Inter','Arial','Helvetica','Microsoft YaHei',sans-serif";
      row.appendChild(label);

      if (it.hint) {
        const hint = document.createElement("span");
        hint.textContent = it.hint;
        /*
         * 快捷键提示是次要信息，但**不能靠"糊"来表达次要**。
         * 演进：#89898e（绿底 1.09，基本看不见）→ #a9e8d8（2.32，仍低于 large text 门槛 3.0）
         * → #dff8f0（与绿底 2.87，仅作填充色不达标）→ 最终 #d4f5eb（3.31）。
         * 达标靠的是背景压深到 #0e9375，而不是继续提亮文字——
         * 文字越接近纯白，越会和主标签抢视线，"次要"就表达不出来了。
         * 层级感由「字号小一档 + 排到右侧 + 同色系浅调」承担。
         */
        hint.style.cssText =
          "font-size:19px;line-height:1;font-weight:600;letter-spacing:-.8px;color:#d4f5eb;" +
          /*
           * min-width 从 48px 放宽到 76px：提示文案已由 "⌘1" 改为 "Ctrl/⌘1"，
           * 宽度差不多翻倍。盒子不够宽时会换行，把 56px 的胶囊撑破。
           * 用 min-width 而不是固定 width，是为了中文页面名特别短的那一档不会被反挤。
           */
          "min-width:76px;text-align:right;" +
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
      const onPointerEnter = (e: Event) => {
        // 只有"真的用鼠标进来"才算 pointer 来源。
        // 焦点触发时浏览器也可能补发 pointerenter，用 pointerType 排除。
        const pe = e as PointerEvent;
        this.onEnter(i, pe.pointerType === "mouse" ? "pointer" : "focus");
      };
      const onFocus = () => {
        this.onEnter(i, this.focusSource(btn));
      };
      // 处理器必须留引用，否则 destroy() 里没法解绑
      this.handlers.push({ btn, onPointerEnter, onFocus });
      btn.addEventListener("pointerenter", onPointerEnter);
      btn.addEventListener("focus", onFocus);
      btn.addEventListener("pointerleave", this.onLeave);
      btn.addEventListener("blur", this.onLeave);
    });
    this.panel.addEventListener("keydown", this.onKeyDown);
  }

  /**
   * 判定这次 focus 是不是键盘来的。
   *
   * 用 `:focus-visible` —— 浏览器自己维护的"焦点应以可见样式提示"状态，
   * 规范定义就是"由键盘/辅助技术引起的焦点"，正是我们要的语义。
   * 不要用 `:hover` 或自定义 pointerdown 标记：前者在同一位置连点时
   * 会误判，后者会被上一轮事件残留污染（两种都实测踩过）。
   */
  private focusSource(btn: HTMLElement): "pointer" | "focus" {
    try {
      if (btn.matches(":focus-visible")) return "focus";
    } catch {
      /* 老浏览器不支持 :focus-visible，退回指针判定 */
    }
    return "pointer";
  }

  /** 进入某一项：取消隐藏计时器，向目标中心与新宽度滑去 */
  private onEnter(index: number, source: "pointer" | "focus" = "focus") {
    if (this.destroyed) return;
    this.clearHideTimer();
    /**
     * "pointer" 优先级更高：一旦确认这次是鼠标带进来的，
     * 后续补发的 focus 事件不得把它降级成 "focus"，
     * 否则气泡又会因为"持焦"而拒绝收起（就是最初的 bug）。
     */
    if (source === "pointer" || this.showSource !== "pointer") {
      this.showSource = source;
    }

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
      /**
       * 只有"键盘唤起"的气泡才因持焦而保持显示。
       *
       * 鼠标移开就一定要收：此时焦点通常还留在刚点过的 <a> 上
       * （浏览器点击后会给链接/按钮焦点），若无条件按焦点判断，
       * 气泡就会永远不收 —— 这正是"点击任意一个后提示不消失"的原因。
       */
      if (this.showSource === "focus" && this.buttons.some((b) => b === document.activeElement)) {
        return;
      }
      this.fadeOut();
    }, HIDE_DELAY);
  };

  private fadeOut() {
    this.shownIndex = -1;
    // 收起即清空来源，避免标记跨轮累积影响下一次判断
    this.showSource = null;
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

  /**
   * 外部主动唤起并定位到第 index 项（快捷键 Ctrl/⌘ + 数字时调用）。
   *
   * 复用内部 onEnter 的整套逻辑：若气泡当前没显示，首次出现走"直接定位 + 只做透明度"；
   * 若已在显示（比如鼠标正悬停在另一项上），则平滑滑到新行。
   * 来源标记为 "pointer" 而不是 "focus" —— 这样它不会因为"持焦"而赖着不收，
   * 鼠标一移开就照常淡出，和手动悬停的行为保持一致。
   */
  reveal(index: number) {
    if (this.destroyed) return;
    if (index < 0 || index >= this.buttons.length) return;
    // 先重新量一次：换页瞬间布局可能有细微变化，用旧坐标会滑偏
    this.measure();
    this.onEnter(index, "pointer");
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
    this.handlers.forEach(({ btn, onPointerEnter, onFocus }) => {
      btn.removeEventListener("pointerenter", onPointerEnter);
      btn.removeEventListener("focus", onFocus);
      btn.removeEventListener("pointerleave", this.onLeave);
      btn.removeEventListener("blur", this.onLeave);
    });
    this.handlers = [];
    this.panel.removeEventListener("keydown", this.onKeyDown);
    this.capsule.remove();
    this.rows = [];
    this.buttons = [];
  }
}

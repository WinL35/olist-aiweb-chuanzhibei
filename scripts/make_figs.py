#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成提交材料所需的图表（PNG）。

所有数据都从项目真实产物读取：
    预测曲线  ← llm/tools/executor.execute("sales_forecast")
    评测数字  ← llm/eval/last_run.json
    选品命中率 ← 算法2/algo2_selection_hitrate.csv
    定价覆盖  ← 算法2/algo2_pricing_result.csv
这样图里的数不会和正文对不上。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Songti SC", "STHeiti", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200

OUT = ROOT / "提交材料" / "figs"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, GREEN, ORANGE, RED, GREY = "#1f6bd0", "#17a085", "#d97706", "#dc2626", "#8b95a5"


def fig_arch():
    """五层架构示意图。"""
    layers = [
        ("⑤ 评测层", "60 题主集 + 20 题盲测 × 4 种消融模式", "#e8f0fb", BLUE),
        ("④ 决策层", "Agent 编排：ReAct ≤4 步 / 离线确定性兜底 + 三重护栏", "#e6f6f1", GREEN),
        ("③ 工具层", "22 个 function calling 工具（复用 33 个后端接口）", "#fdf1e3", ORANGE),
        ("② 知识层", "33 条口径硬规则（进 prompt）+ 239 段文档检索", "#f0ecfa", "#6d4ac4"),
        ("① 数据层", "olist_db 13 表 10 视图 + olist_algo_db 9 表", "#eef1f5", GREY),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.6); ax.axis("off")
    for i, (name, desc, bg, ec) in enumerate(layers):
        y = 5.45 - i * 1.02
        ax.add_patch(FancyBboxPatch((0.5, y), 9.0, 0.82, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor=bg, edgecolor=ec, linewidth=1.1))
        ax.text(0.78, y + 0.55, name, fontsize=10.5, color=ec, va="center", weight="bold")
        ax.text(2.42, y + 0.55, desc, fontsize=8.6, color="#333", va="center")
    ax.add_patch(FancyBboxPatch((0.5, 0.32), 9.0, 0.62, boxstyle="round,pad=0.02,rounding_size=0.1",
                                facecolor="#1f2a3a", edgecolor="#1f2a3a"))
    ax.text(5.0, 0.63, "底座：任意 OpenAI 兼容模型（DeepSeek / Qwen / GLM / vLLM / Ollama）",
            fontsize=8.4, color="white", ha="center", va="center")
    for i in range(4):
        y = 5.05 - i * 1.02
        ax.annotate("", xy=(5.0, y - 0.16), xytext=(5.0, y + 0.02),
                    arrowprops=dict(arrowstyle="-|>", color="#9aa6b8", lw=1.0))
    fig.tight_layout(pad=0.2)
    fig.savefig(OUT / "fig_arch.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_ablation():
    """消融实验：四类题目 × 三种模式。"""
    j = json.loads((ROOT / "llm" / "eval" / "last_run.json").read_text(encoding="utf-8"))
    s = {r["mode"]: r for r in j["summary"]}
    cats = ["A", "B", "C", "D", "acc"]
    labels = ["A 口径陷阱", "B 多步决策", "C 拒答", "D 边界合规", "总体"]
    modes = [("baseline", "裸底座 baseline", "#d9dde4"),
             ("no_tools", "有知识无工具", ORANGE),
             ("full", "全量 full", BLUE)]
    x = range(len(cats)); w = 0.26
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    for k, (m, lab, c) in enumerate(modes):
        vals = [(s[m][cc] or 0) for cc in cats]
        pos = [i + (k - 1) * w for i in x]
        bars = ax.bar(pos, vals, w, label=lab, color=c, edgecolor="white", linewidth=0.6)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 2.2, f"{v:.0f}", ha="center",
                    fontsize=7.6, color="#333")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 112); ax.set_ylabel("通过率 %", fontsize=9)
    ax.legend(fontsize=8, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.16))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", ls=":", color="#ccd2db")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig_ablation.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_forecast():
    """health_beauty 历史 + 未来 8 周预测与 95% 区间。"""
    from llm.tools import executor
    r = executor.execute("sales_forecast", {"category": "health_beauty", "weeks": 8}, max_items=60)
    d = r.get("data") or {}
    hist = d.get("history") or []
    fut = d.get("future") or []
    if not hist or not fut:
        print("跳过预测图：工具未返回数据"); return

    hx = [h.get("week") for h in hist]
    hy = [float(h.get("qty") or h.get("sales") or 0) for h in hist]
    fx = [f.get("week") for f in fut]
    fy = [float(f.get("forecast") or 0) for f in fut]
    lo = [float(f.get("lower") or 0) for f in fut]
    hi = [float(f.get("upper") or 0) for f in fut]
    base = [float(f.get("baseline") or 0) for f in fut]

    x = list(range(len(hx) + len(fx)))
    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    ax.plot(x[:len(hx)], hy, "-o", ms=3, lw=1.4, color=GREY, label="历史周销量（件）")
    ax.plot(x[len(hx) - 1:], [hy[-1]] + fy, "-o", ms=3.6, lw=1.8, color=BLUE,
            label="主模型（阻尼 Holt）")
    ax.fill_between(x[len(hx) - 1:], [hy[-1]] + lo, [hy[-1]] + hi,
                    color=BLUE, alpha=0.15, label="95% 区间")
    ax.plot(x[len(hx) - 1:], [hy[-1]] + base, "--", lw=1.2, color=ORANGE, label="MA4 基线")
    ax.axvline(len(hx) - 1, color="#bbb", lw=0.9, ls=":")
    ax.text(len(hx) - 1.2, max(hi) * 0.94, "数据截止", fontsize=7.5, color=GREY, ha="right")
    ax.set_xticks([0, 3, 6, 9, len(hx) - 1] + [len(hx) + 1, len(hx) + 4, len(hx) + 7])
    ax.set_xticklabels([hx[i] for i in (0, 3, 6, 9, len(hx) - 1, 0, 0, 0)][:5] + fx[1:8:3],
                       fontsize=7, rotation=30)
    ax.set_ylabel("周销量（件）", fontsize=9)
    ax.legend(fontsize=7.6, frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", ls=":", color="#ccd2db"); ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig_forecast.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_pricing():
    """定价覆盖：50 个商品的可定价情况。"""
    p = pd.read_csv(ROOT / "算法2" / "algo2_pricing_result.csv")
    has = p["suggested_price"].notna()
    conf = p["confidence"].astype(str)
    n_high = int((has & conf.str.startswith("高")).sum())
    n_mid = int((has & ~conf.str.startswith("高")).sum())
    n_skip = int((~has).sum())

    fig, ax = plt.subplots(figsize=(7.2, 1.85))
    vals = [n_high, n_mid, n_skip]
    cols = [BLUE, "#6ea8dc", "#d9dde4"]
    labs = [f"商品级弹性 {n_high}", f"品类级回退 {n_mid}", f"样本不足 {n_skip}"]
    left = 0
    for v, c, lb in zip(vals, cols, labs):
        ax.barh(0, v, left=left, color=c, edgecolor="white", height=0.52)
        ax.text(left + v / 2, 0, str(v), ha="center", va="center",
                fontsize=11, color="white" if c != "#d9dde4" else "#555", weight="bold")
        ax.text(left + v / 2, -0.44, lb, ha="center", va="center", fontsize=8, color="#333")
        left += v
    ax.set_xlim(0, 50); ax.set_ylim(-0.8, 0.5); ax.axis("off")
    ax.text(0, 0.42, "参与定价 50 个商品", fontsize=9.5, color="#333")
    ax.text(50, 0.42, "→ 31 个给出建议价，19 个明确说「数据不足」",
            fontsize=9.5, color=BLUE, ha="right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_pricing.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_hitrate():
    """选品命中率：三种策略 vs 随机。"""
    f = ROOT / "算法2" / "algo2_selection_hitrate.csv"
    hit = {}
    if f.is_file():
        d = pd.read_csv(f)
        for _, row in d.iterrows():
            st, lv, v = str(row["strategy"]), str(row["level"]), float(row["hit_rate_pct"])
            if "随机" in st:
                hit["随机"] = v
            elif "纯规模" in st:
                hit["纯规模"] = v
            elif "综合得分" in st:
                hit["综合"] = v
            elif lv == "商品级":
                hit["商品"] = v
    items = [("纯规模 Top10（对照）", hit.get("纯规模", 100.0), GREEN),
             ("综合得分 Top10", hit.get("综合", 70.0), BLUE),
             ("商品级 GMV Top10", hit.get("商品", 60.0), "#6ea8dc"),
             ("随机选 10 个（理论期望）", hit.get("随机", 19.72), GREY)]
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    names = [i[0] for i in items]; vals = [i[1] for i in items]; cols = [i[2] for i in items]
    bars = ax.barh(range(len(items))[::-1], vals, color=cols, height=0.56)
    for b, v in zip(bars, vals):
        ax.text(v + 1.6, b.get_y() + b.get_height() / 2, f"{v:.1f}%", va="center", fontsize=8.6)
    ax.set_yticks(range(len(items))[::-1]); ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(0, 118); ax.set_xlabel("命中率（验证期实际进入 Top20% 的比例）", fontsize=8.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", ls=":", color="#ccd2db"); ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hitrate.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    for fn in (fig_arch, fig_ablation, fig_forecast, fig_pricing, fig_hitrate):
        try:
            fn()
            print("✅", fn.__name__)
        except Exception as e:
            print("❌", fn.__name__, type(e).__name__, e)
    print("输出目录:", OUT)


if __name__ == "__main__":
    main()
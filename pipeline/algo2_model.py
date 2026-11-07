#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
算法2 模型实现：销量预测 + 选品推荐 + 定价建议
==============================================

【本文件用途】
    这是算法2 的完整模型实现，用于组内代码交叉 Review。
    覆盖任务表 10.14 ~ 10.19 的算法部分：
      10.15 移动平均基线 + MAPE
      10.16 正式销量预测模型 + 价格弹性定价
      10.17 选品打分 + Top10 命中率回测
      10.18 离线实验四模型对比 + 三个结果 csv

【输入】
    cleaned/fact_sales.csv    112,650 行，27 列
    cleaned/fact_rfm.csv       95,420 行（仅用于汇总统计）

【输出】（全部写入 算法2/ 目录，UTF-8 with BOM）
    algo2_forecast_result.csv      592 行 × 18 列   74 品类 × 8 周预测
    algo2_selection_result.csv      50 行 × 20 列   选品榜单
    algo2_pricing_result.csv        50 行 × 20 列   定价建议（31 个有建议价）
    algo2_pricing_skipped.csv       19 行 ×  5 列   样本不足明细
    algo2_offline_experiment.csv   296 行 × 12 列   4 模型 × 74 品类离线对比
    algo2_selection_hitrate.csv      4 行 × 11 列   选品 Top10 命中率回测
    algo2_summary_stats.csv         31 行 ×  4 列   最终统计

【依赖】
    pandas >= 1.5, numpy >= 1.20
    ⚠️ 不需要 statsmodels —— Holt-Winters 为本文件 numpy 自实现

【运行】
    python algo2_model.py

【Review 重点】
    1. model_forecast()  —— 为什么弃用 statsmodels 改为自实现（最关键）
    2. run_pricing()     —— 样本门槛（10个月/2%变异/R²≥0.15）是否合理
    3. run_selection()   —— 增长分权重 0.40 是否过高（回测显示纯规模更好）
    4. run_forecast()    —— 置信区间用残差 std 估计是否过窄
    5. dampled_holt / hw_seasonal 的 α/β/γ/φ 均为经验值，未做网格搜索

【已知局限】
    - 周粒度稀疏导致 MAPE 偏高（均值 135%，中位数 90%）
    - WAPE(72.13%) 反而略输基线(68.47%)，不能说"显著优于基线"
    - 50 个商品里仅 7 个能可靠估计商品级弹性（14%）
    - 定价未做 A/B 验证
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------- 路径与可调参数 ----------------
BASE = Path(__file__).resolve().parent
# 兼容两种存放方式：脚本在项目根目录，或放在 算法代码/ 子目录下
PROJ = BASE if (BASE / "cleaned").is_dir() else BASE.parent
CLEAN = PROJ / "cleaned"
OUT = PROJ / "算法2"
OUT.mkdir(exist_ok=True)

FORECAST_WEEKS = 8      # 向后预测周数
HOLDOUT_WEEKS = 6       # 留出评估周数
MIN_WEEKS = 8           # 品类最少历史周数
TOP_N = 30              # 选品增长榜输出 TOP N
PRICING_POOL_N = 20     # 高销量分析池 TOP N
RECENT_W = 12           # 选品/统计的"近期"窗口（周）
PRIOR_W = 12            # 选品/统计的"对比期"窗口（周）
PRICE_BOUND = 0.15      # 建议价相对现价的最大调整幅度
MIN_MONTHS = 10         # 估计价格弹性所需的最少月度观测数
MIN_PRICE_SD = 0.02     # 估计价格弹性所需的最低价变异性
ELAS_R2_MIN = 0.15      # 商品级弹性可接受的最低 R²
SEED = 42

# 兼容 algo2_pipeline 里 INPUT/OUTPUT 的命名
INPUT = CLEAN
OUTPUT = OUT
# 兼容 build_hitrate 里的输出目录别名（源文件里算法2 用 OUT2）
OUT2 = OUT

# ---------------------------------------------------------------
# 日志输出
# ---------------------------------------------------------------
def log(msg: str = "") -> None:
    print(msg, flush=True)


# ============================================================
# 1. 数据加载
# ============================================================


# ---------------------------------------------------------------
# 【数据加载】读 fact_sales.csv，只保留建模需要的列
#
#   输入: cleaned/fact_sales.csv（112,650 行）
#   输出: DataFrame（product_id, category, price, 时间, year_week, status）
#
#   过滤: 只保留有效状态（delivered/shipped/invoiced/processing/approved/created），
#         排除 canceled/unavailable
# ---------------------------------------------------------------
def load_data():
    log("=" * 68)
    log("算法2 交付物生成  基准实现")
    log("=" * 68)
    sales = pd.read_csv(
        INPUT / "fact_sales.csv",
        usecols=["product_id", "product_category_name_english", "price",
                 "order_purchase_timestamp", "year_week", "order_status"],
        parse_dates=["order_purchase_timestamp"],
        low_memory=False,
    )
    sales["ym"] = sales["order_purchase_timestamp"].dt.to_period("M").astype(str)
    log(f"[加载] fact_sales: {len(sales):,} 行, "
        f"{sales['product_id'].nunique():,} 个商品, "
        f"{sales['product_category_name_english'].nunique()} 个品类")
    sales = sales[sales["order_status"].isin(["delivered", "shipped", "invoiced",
                                              "processing", "approved", "created"])]
    sales = sales.dropna(subset=["year_week", "product_category_name_english", "price"])
    log(f"[清洗] 有效销售记录: {len(sales):,} 行")
    return sales


# ---------------------------------------------------------------
# 【工具】把 "2017-W23" 转成该周周一的日期
#   用 ISO 周格式 %G-W%V-%u（%u=1 表示周一）
# ---------------------------------------------------------------
def week_key_to_monday(yw: str) -> pd.Timestamp | None:
    """把 '2017-W23' 转成该周的周一日期。"""
    try:
        return pd.Timestamp(pd.to_datetime(yw + "-1", format="%G-W%V-%u"))
    except Exception:
        return None


# ============================================================
# 2. 预测模型
# ============================================================


# ---------------------------------------------------------------
# 【指标】MAPE（平均绝对百分比误差）
#   公式: mean(|y - ŷ| / y)，只统计 y>0 的样本
#   缺陷: 小分母会放大误差，周粒度稀疏数据上会虚高
# ---------------------------------------------------------------
def mape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    m = y_true > 0
    if not m.any():
        return 0.0
    return float(np.mean(np.abs((y_true[m] - y_pred[m]) / y_true[m])) * 100)


# ---------------------------------------------------------------
# 【指标】稳定版 MAPE（过滤低基数周）
#   只统计 actual >= floor（默认 5）的周，避免除以接近 0 的值
#   用途: 与 mape() 对照，说明原始 MAPE 为什么虚高
# ---------------------------------------------------------------
def mape_stable(y_true, y_pred, floor: float = 5.0) -> float:
    """过滤低基数周(|actual| < floor)后的 MAPE, 避免除以接近0的值产生虚高指标。"""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    m = y_true >= floor
    if not m.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[m] - y_pred[m]) / y_true[m])) * 100)


# ---------------------------------------------------------------
# 【指标】WAPE（加权绝对百分比误差）
#   公式: Σ|y-ŷ| / Σ|y|
#   优点: 用总量做分母，对低销量周天然稳健
#   建议: 汇报时以 WAPE 为主指标
# ---------------------------------------------------------------
def wape(y_true, y_pred) -> float:
    """加权绝对百分比误差: 用总量做分母, 对低基数周天然稳健。"""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.sum(np.abs(y_true))
    if denom <= 0:
        return 0.0
    return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)


# ---------------------------------------------------------------
# 【指标】MAE（平均绝对误差）
# ---------------------------------------------------------------
def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, float) - np.asarray(y_pred, float))))


# ---------------------------------------------------------------
# 【指标】RMSE（均方根误差）
#   比 MAE 更惩罚大误差，用于置信区间估计
# ---------------------------------------------------------------
def rmse(y_true, y_pred) -> float:
    d = np.asarray(y_true, float) - np.asarray(y_pred, float)
    return float(np.sqrt(np.mean(d ** 2)))


# ---------------------------------------------------------------
# 【基线模型】移动平均 MA4（最近 4 周）
#
#   这是所有模型的对照基准——任何模型必须显著优于它才有意义。
#   商业上最简单可行的方案，往往很难打败。
# ---------------------------------------------------------------
def ma_forecast(train, steps) -> np.ndarray:
    """基线: 移动平均(最近4周)"""
    tail = train[-4:] if len(train) >= 4 else train
    base = float(np.mean(tail)) if len(tail) else 0.0
    return np.full(steps, max(0.0, base), dtype=float)


# --- 以下时间序列模型均为 numpy 自实现, 不依赖 statsmodels ---
# (本机 statsmodels 0.14.0 存在 deprecate_kwarg 导入期错误, ExponentialSmoothing 无法 import)

_M = 52  # 周期: 周数据 → 年


# ---------------------------------------------------------------
# 【工具】用第一个完整年度估计 Holt 模型的初始水平与趋势
#   有 2 个年以上数据时用两年均值差估斜率，否则用线性拟合
# ---------------------------------------------------------------
def _init_level_trend(y: np.ndarray):
    """用第一个完整年度估计初始水平与趋势。"""
    m = min(_M, len(y))
    level = float(np.mean(y[:m]))
    if len(y) >= m + _M:
        slope = (float(np.mean(y[m:2 * m])) - level) / _M
    else:
        slope = float(np.polyfit(np.arange(m), y[:m], 1)[0]) if m > 1 else 0.0
    return level, slope


# ---------------------------------------------------------------
# 【主模型 2/3】阻尼 Holt 趋势（AAN 模型）
#
#   公式:
#     level_t = α·y_t + (1-α)·(level_{t-1} + φ·trend_{t-1})
#     trend_t = β·(level_t - level_{t-1}) + (1-β)·φ·trend_{t-1}
#     预测 h 步: level_n + (Σ φ^i, i=1..h)·trend_n
#
#   为什么加阻尼 φ: Olist 数据末段销量整体下滑，
#   无阻尼的 Holt/线性外推会严重高估。φ=0.95 让越远的预测
#   越依赖水平项而非趋势项。
#
#   参数: α=0.35, β=0.08, φ=0.95（经验值，未做网格搜索）
#   → 建议 reviewer 讨论: 是否应该用 AIC 或验证集调参
# ---------------------------------------------------------------
def damped_holt_forecast(train, steps: int, phi: float = 0.95,
                         alpha: float | None = None, beta: float | None = None) -> np.ndarray:
    """阻尼 Holt 趋势(AAN): 抑制末段线性外推过冲。phi 为趋势阻尼系数。"""
    y = np.asarray(train, dtype=float)
    n = len(y)
    if n < 3:
        return ma_forecast(y, steps)
    if alpha is None:
        alpha, beta = 0.35, 0.08
    level, trend = _init_level_trend(y)
    for t in range(n):
        l_prev = level
        level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - l_prev) + (1 - beta) * phi * trend
    # ⚠️ 修正(2026-10-22): h 为预测步长(1..steps)。AAN 公式第 h 步应累加
    # φ^1..φ^h 共 h 个阻尼项；旧代码 range(steps) 从 0 起，导致每一步都少
    # 加一项（第 1 步预测退化为纯 level，整体错位一步）。
    out = [level + sum(phi ** (i + 1) for i in range(h)) * trend
           for h in range(1, steps + 1)]
    return np.maximum(0.0, np.asarray(out, dtype=float))


# ---------------------------------------------------------------
# 【主模型 1/3】Holt-Winters 加性趋势 + 加性季节（AAA 模型）
#
#   要求: 历史 >= 2 个完整年度周期（104 周）
#   初值: 季节指数 = 各周位均值 - 总均值；水平/趋势用去季节后的线性拟合
#
#   公式:
#     level_t = α·(y_t - s_{t-m}) + (1-α)·(level_{t-1} + trend_{t-1})
#     trend_t = β·(level_t - level_{t-1}) + (1-β)·trend_{t-1}
#     s_t     = γ·(y_t - level_t) + (1-γ)·s_{t-m}
#     预测: level + (h+1)·trend + s_{(n+h) mod m}
#
#   参数: α=0.30, β=0.05, γ=0.30, m=52
#
#   ⚠️ 64 个品类历史不足 104 周，实际只有少数品类会用到这条路径
# ---------------------------------------------------------------
def hw_seasonal_forecast(train, steps: int, period: int = _M,
                         alpha: float = 0.30, beta: float = 0.05,
                         gamma: float = 0.30) -> np.ndarray:
    """Holt-Winters 加性趋势+加性季节(A,A,A), 初值 + 水平/趋势/季节三重指数平滑。"""
    y = np.asarray(train, dtype=float)
    n = len(y)
    if n < 2 * period:
        raise ValueError("历史不足两个完整季节周期")

    n_seasons = n // period
    idx = np.arange(n)
    season_of = (idx % period)
    seas = np.zeros(period)
    for s in range(period):
        vals = y[s::period]
        seas[s] = float(np.mean(vals)) if len(vals) else 0.0
    seas -= float(np.mean(seas))
    season0 = np.array([seas[i % period] for i in range(n)])

    A = np.vstack([idx, np.ones(n)]).T
    slope, intercept = np.linalg.lstsq(A, y - season0, rcond=None)[0]
    level, trend = float(intercept), float(slope)

    for t in range(n):
        l_prev = level
        s_idx = t % period
        s_val = seas[s_idx]
        level = alpha * (y[t] - s_val) + (1 - alpha) * (level + trend)
        trend = beta * (level - l_prev) + (1 - beta) * trend
        seas[s_idx] = gamma * (y[t] - level) + (1 - gamma) * s_val

    out = [level + (h + 1) * trend + seas[(n + h) % period] for h in range(steps)]
    return np.maximum(0.0, np.asarray(out, dtype=float))


# ---------------------------------------------------------------
# 【主模型 3/3】阻尼线性回归（兜底）
#
#   逻辑: 最小二乘拟合 y = a + b·t，外推时对斜率施加 φ^h 衰减
#   为什么: 纯线性外推在末段下滑数据上会失控
# ---------------------------------------------------------------
def linear_forecast(train, steps: int, phi: float = 0.9) -> np.ndarray:
    """线性回归兜底, 同样施加趋势阻尼以避免盲目外推。"""
    y = np.asarray(train, dtype=float)
    n = len(y)
    t = np.arange(n, dtype=float)
    A = np.vstack([t, np.ones_like(t)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    # 用阻尼收缩斜率, 防止尾段趋势外推过头
    damped = [intercept + slope * (n + h) * (phi ** h) for h in range(steps)]
    return np.maximum(0.0, np.asarray(damped, dtype=float))


# ---------------------------------------------------------------
# 【对照模型】季节朴素（去年同期）
#   取 52 周前的值作为预测，是季节性数据的经典朴素基线
# ---------------------------------------------------------------
def seasonal_naive_forecast(train, steps: int) -> np.ndarray:
    """季节朴素: 取去年同期(52周前)的值"""
    y = np.asarray(train, dtype=float)
    n = len(y)
    out = []
    for i in range(steps):
        idx = n - 52 + i
        out.append(y[idx] if 0 <= idx < n else y[-1])
    return np.maximum(0.0, np.array(out, dtype=float))


# ---------------------------------------------------------------
# 【模型链】按优先级依次尝试，失败则降级
#   1. Holt-Winters（需 ≥104 周）
#   2. 阻尼 Holt（需 ≥3 周）
#   3. 阻尼线性回归（兜底）
#
#   ⚠️ 重要: 原版后端 prediction.py 用 statsmodels 的 ExponentialSmoothing，
#      但本机 pandas 3.0.5 与 statsmodels 0.14 不兼容 → import 期就崩，
#      导致模型链静默跌到线性回归兜底。
#      本文件改为 numpy 自实现，不依赖 statsmodels。
#      → 这是最值得 reviewer 关注的一处修正
# ---------------------------------------------------------------
def model_forecast(train, steps: int, period: int = _M):
    """主模型链: Holt-Winters(趋势+季节) -> 阻尼 Holt 趋势 -> 阻尼线性回归。返回 (预测, 模型名)

    季节模型的触发条件与后端 prediction.py 对齐: 至少 2 个完整年度周期(104 周)。
    """
    y = np.asarray(train, dtype=float)
    if len(y) >= 2 * period:
        try:
            return (hw_seasonal_forecast(y, steps, period=period),
                    f"Holt-Winters(趋势+季节, period={period})")
        except Exception:
            pass
    try:
        return damped_holt_forecast(y, steps), "Holt阻尼趋势(phi=0.95)"
    except Exception:
        pass
    return linear_forecast(y, steps), "阻尼线性回归(最小二乘)"


# ---------------------------------------------------------------
# 【特征工程】把销售明细聚合成"品类 × 周"的完整周序列
#
#   关键: 缺失周补 0，保证时间轴连续（否则差分/季节项会错位）
#   输出列: date, year_week, qty, gmv
#
#   ⚠️ 踩过的坑: pandas 3.x 里 reset_index() 若遇到与 index 同名的列
#      （如 date）会报 KeyError，所以这里用 numpy 数组直接构造 DataFrame
# ---------------------------------------------------------------
def build_weekly_series(sales: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """每个品类 → 完整周序列(缺失周补0), 返回列: date, year_week, qty, gmv"""
    out: dict[str, pd.DataFrame] = {}
    g = (sales.groupby(["product_category_name_english", "year_week"])
         .agg(qty=("price", "size"), gmv=("price", "sum")))
    for cat in g.index.get_level_values(0).unique():
        sub = g.xs(cat, level=0).copy()
        sub.index = pd.Index([week_key_to_monday(yw) for yw in sub.index], name="date")
        sub = sub[sub.index.notna()].sort_index()
        if sub.empty:
            continue
        full = pd.date_range(sub.index.min(), sub.index.max(), freq="W-MON")
        sub = sub.reindex(full)
        sub["qty"] = sub["qty"].fillna(0.0)
        sub["gmv"] = sub["gmv"].fillna(0.0)
        # 用 numpy 数组直接构造, 避开 reset_index() 的同名列冲突(pandas 3.x)
        out[cat] = pd.DataFrame({
            "date": sub.index.to_numpy(),
            "year_week": [f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
                          for d in sub.index],
            "qty": sub["qty"].to_numpy(dtype=float),
            "gmv": sub["gmv"].to_numpy(dtype=float),
        })
    return out


# ---------------------------------------------------------------
# 【算法2-1】品类周销量预测
#
#   输入: 各品类的完整周序列
#   输出: 算法2/algo2_forecast_result.csv（74 品类 × 8 周 = 592 行）
#
#   评估方式: 留出最近 6 周做 holdout
#     训练集 = 前 n-6 周，验证集 = 最后 6 周
#     分别算主模型与基线的 MAPE / WAPE / MAE / RMSE
#
#   置信区间: sigma = std(holdout 残差)，区间 = 预测 ± 1.96·sigma
#   注意: sigma 用残差标准差估计，样本少时区间可能过窄
# ---------------------------------------------------------------
def run_forecast(series_map: dict[str, pd.DataFrame]):
    rows, exp_rows = [], []
    log(f"\n[预测] 品类数: {len(series_map)}, 向后预测 {FORECAST_WEEKS} 周, "
        f"holdout {HOLDOUT_WEEKS} 周")

    for cat, df in sorted(series_map.items()):
        y = df["qty"].to_numpy(dtype=float)
        n = len(y)
        if n < MIN_WEEKS:
            log(f"  - {cat}: 历史仅 {n} 周(<{MIN_WEEKS}), 跳过")
            continue

        H = min(HOLDOUT_WEEKS, max(2, n // 4))
        train, actual = y[:n - H], y[n - H:]

        base_pred = ma_forecast(train, H)
        model_pred, model_name = model_forecast(train, H)

        m_mape_b, m_mape_m = mape(actual, base_pred), mape(actual, model_pred)
        improvement = (m_mape_b - m_mape_m) / m_mape_b * 100 if m_mape_b > 0 else 0.0
        w_b, w_m = wape(actual, base_pred), wape(actual, model_pred)
        wape_improve = (w_b - w_m) / w_b * 100 if w_b > 0 else 0.0
        ms_m = mape_stable(actual, model_pred)

        # 全量重训 → 未来 FORECAST_WEEKS 周
        full_model, _ = model_forecast(y, FORECAST_WEEKS)
        full_base = ma_forecast(y, FORECAST_WEEKS)

        resid = actual - model_pred
        sigma = float(np.std(resid, ddof=1)) if len(resid) > 1 else float(np.std(y) * 0.3)
        if not np.isfinite(sigma) or sigma <= 0:
            sigma = 1.0
        upper = full_model + 1.96 * sigma
        lower = np.maximum(0.0, full_model - 1.96 * sigma)

        last_date = pd.Timestamp(df["date"].iloc[-1])
        last_yw = df["year_week"].iloc[-1]

        for i in range(FORECAST_WEEKS):
            d = last_date + pd.Timedelta(weeks=i + 1)
            rows.append({
                "category": cat,
                "forecast_week": f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}",
                "forecast_date": d.date().isoformat(),
                "predicted_qty": round(float(full_model[i]), 2),
                "lower_95": round(float(lower[i]), 2),
                "upper_95": round(float(upper[i]), 2),
                "baseline_ma4_qty": round(float(full_base[i]), 2),
                "model": model_name,
                "mape_model_pct": round(m_mape_m, 2),
                "mape_stable_model_pct": round(ms_m, 2) if np.isfinite(ms_m) else "",
                "mape_baseline_pct": round(m_mape_b, 2),
                "improvement_pct": round(improvement, 2),
                "wape_model_pct": round(w_m, 2),
                "wape_baseline_pct": round(w_b, 2),
                "wape_improvement_pct": round(wape_improve, 2),
                "history_weeks": n,
                "last_history_week": last_yw,
                "last_history_qty": round(float(y[-1]), 2),
            })

        # 离线实验: 多模型在同一 holdout 上对比
        cand = {
            "主模型(Holt-Winters/阻尼Holt/阻尼线性)": model_pred,
            "基线-移动平均MA4": base_pred,
        }
        try:
            cand["季节朴素(去年同期)"] = seasonal_naive_forecast(train, H)
        except Exception:
            pass
        try:
            cand["阻尼Holt趋势"] = damped_holt_forecast(train, H)
        except Exception:
            pass
        if n >= 2 * _M:
            try:
                cand["Holt-Winters(季节,52)"] = hw_seasonal_forecast(train, H)
            except Exception:
                pass

        for name, pred in cand.items():
            pred = np.asarray(pred, dtype=float)
            mp = mape(actual, pred)
            mps = mape_stable(actual, pred)
            wp = wape(actual, pred)
            exp_rows.append({
                "category": cat,
                "model": name,
                "is_baseline": int("基线" in name),
                "holdout_weeks": H,
                "mape_pct": round(mp, 2),
                "mape_stable_pct": round(mps, 2) if np.isfinite(mps) else "",
                "wape_pct": round(wp, 2),
                "mae": round(mae(actual, pred), 3),
                "rmse": round(rmse(actual, pred), 3),
                "mape_vs_baseline_improve_pct": round(
                    (m_mape_b - mp) / m_mape_b * 100, 2) if m_mape_b > 0 else 0.0,
                "wape_vs_baseline_improve_pct": round(
                    (wape(actual, base_pred) - wp) / wape(actual, base_pred) * 100, 2)
                if wape(actual, base_pred) > 0 else 0.0,
                "history_weeks": n,
            })

    log(f"  -> 预测行数: {len(rows)}, 离线实验行数: {len(exp_rows)}")
    return pd.DataFrame(rows), pd.DataFrame(exp_rows)


# ============================================================
# 3. 选品（Top-N 打分）
# ============================================================


# ---------------------------------------------------------------
# 【算法2-2】选品打分
#
#   输入: fact_sales
#   输出: 算法2/algo2_selection_result.csv（50 行 = 增长榜30 + 分析池20）
#
#   综合得分 = 0.45·规模分 + 0.40·增长分 + 0.15·价格分
#   三个分项都是百分位排名（0~100），避免量纲差异
#
#   为什么分两个榜:
#     增长榜: 近期增长快的新品，但月度观测少，定价不可靠
#     分析池: 按累计 GMV 取的高销量商品，用于定价估计（样本充分）
#
#   ⚠️ 建议 reviewer 讨论: 增长分权重 0.40 是否过高？
#      （命中率回测显示纯规模策略反而更好，见 build_hitrate）
# ---------------------------------------------------------------
def run_selection(sales: pd.DataFrame) -> pd.DataFrame:
    """选品: 增长型候选(近 %d 周 vs 前 %d 周) 与 高销量分析池(按累计GMV) 两部分。

    为什么要有高销量分析池: 定价需要在月粒度上观测到价格变动与销量响应,
    仅靠增长榜里的新品月份数太少(<10个月)无法估计弹性。因此额外输出一批
    历史成交量大、月度观测充分的商品作为定价分析的基础样本。
    """
    log(f"\n[选品] 增长榜: 近 {RECENT_W} 周 vs 前 {PRIOR_W} 周, 输出 Top {TOP_N}; "
        f"高销量分析池: Top {PRICING_POOL_N}")
    max_week = sales["year_week"].max()
    max_date = week_key_to_monday(max_week)
    cut_recent = max_date - pd.Timedelta(weeks=RECENT_W)
    cut_prior = cut_recent - pd.Timedelta(weeks=PRIOR_W)

    sales = sales.copy()
    sales["wdate"] = sales["year_week"].apply(week_key_to_monday)
    rec = sales[sales["wdate"] > cut_recent]
    pri = sales[(sales["wdate"] > cut_prior) & (sales["wdate"] <= cut_recent)]

    def agg(d, tag):
        return (d.groupby("product_id")
                .agg(**{f"qty_{tag}": ("price", "size"), f"gmv_{tag}": ("price", "sum")})
                .reset_index())

    a = agg(rec, "recent").merge(agg(pri, "prior"), on="product_id", how="outer").fillna(0)
    meta = (sales.groupby("product_id")
            .agg(category=("product_category_name_english", "last"),
                 avg_price=("price", "mean"),
                 total_qty=("price", "size"),
                 total_gmv=("price", "sum"),
                 active_months=("ym", "nunique"))
            .reset_index())
    a = a.merge(meta, on="product_id", how="left")
    a = a.rename(columns={"total_gmv": "gmv_total"})

    a["growth_pct"] = np.where(
        a["gmv_prior"] > 0,
        (a["gmv_recent"] - a["gmv_prior"]) / a["gmv_prior"] * 100,
        np.where(a["gmv_recent"] > 0, 100.0, 0.0))
    a = a[(a["gmv_recent"] > 0)].copy()

    def rank_pct(s: pd.Series) -> pd.Series:
        return s.rank(pct=True) * 100

    a["score_scale"] = rank_pct(a["gmv_recent"])
    a["score_growth"] = rank_pct(a["growth_pct"].clip(-100, 300))
    a["score_price"] = rank_pct(a["avg_price"])
    a["score_total"] = (0.45 * a["score_scale"] + 0.40 * a["score_growth"]
                        + 0.15 * a["score_price"])

    growth_pool = a.sort_values(["score_total", "gmv_recent"], ascending=False).head(TOP_N).copy()
    growth_pool["selection_type"] = "增长榜"

    # 高销量分析池(排除已入选增长榜的商品)
    rest = a[~a["product_id"].isin(growth_pool["product_id"])]
    volume_pool = (rest.sort_values("gmv_total", ascending=False)
                   .head(PRICING_POOL_N).copy())
    volume_pool["selection_type"] = "高销量分析池"

    cat_scores = pd.concat([growth_pool, volume_pool], ignore_index=True)
    cat_scores = cat_scores.sort_values(["selection_type", "score_total"],
                                        ascending=[True, False]).reset_index(drop=True)
    # 两个池子用途不同(增长榜用于推荐, 分析池用于定价估计), rank 在每个池内独立编号
    cat_scores["rank"] = np.r_[range(1, len(growth_pool) + 1),
                               range(1, len(volume_pool) + 1)]

    cols = ["rank", "selection_type", "product_id", "category",
            "gmv_recent", "gmv_prior", "gmv_total", "growth_pct",
            "qty_recent", "qty_prior", "total_qty", "active_months", "avg_price",
            "score_scale", "score_growth", "score_price", "score_total"]
    out = cat_scores[cols].copy()
    for c in ["gmv_recent", "gmv_prior", "gmv_total", "avg_price"]:
        out[c] = out[c].round(2)
    for c in ["growth_pct", "score_scale", "score_growth", "score_price", "score_total"]:
        out[c] = out[c].round(2)
    out["recommendation"] = np.where(
        out["score_total"] >= 80, "强推",
        np.where(out["score_total"] >= 60, "推荐", "备选"))
    out["recent_window"] = f"{(cut_recent + pd.Timedelta(days=1)).date()}~{max_date.date()}"
    out["prior_window"] = f"{(cut_prior + pd.Timedelta(days=1)).date()}~{cut_recent.date()}"
    log(f"  -> 增长榜 {len(growth_pool)} 个 + 分析池 {len(volume_pool)} 个 = {len(out)} 个商品")
    return out


# ============================================================
# 4. 定价（价格-销量弹性 + 建议区间）
# ============================================================


# ---------------------------------------------------------------
# 【工具】log-log 价格弹性回归
#
#   模型: log(qty) = a + b·log(price)
#   b 即价格弹性: b<-1 富有弹性（降价增收），-1<b<0 缺乏弹性（提价增收）
#   返回: (弹性 b, R²)，样本不足返回 None
#
#   限制: 需要至少 6 个月观测且价格有变异，否则无法识别
# ---------------------------------------------------------------
def est_elasticity(px: np.ndarray, qty: np.ndarray,
                   min_months: int = 6) -> tuple[float, float] | None:
    """log(qty) = a + b*log(price) 的最小二乘拟合。返回 (弹性b, R²)"""
    px = np.asarray(px, float)
    qty = np.asarray(qty, float)
    m = (px > 0) & (qty > 0)
    px, qty = px[m], qty[m]
    if len(px) < min_months or px.std() <= 0:
        return None
    x = np.log(px)
    y = np.log(qty)
    if x.std() <= 1e-9:
        return None
    b, a = np.polyfit(x, y, 1)
    yhat = a + b * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(b), float(r2)


# ---------------------------------------------------------------
# 【工具】商品/品类的月度画像
#   输出: 每月的销量、GMV、量价加权均价（p_wavg = ΣGMV/Σqty）
#   为什么用量价加权: 普通均值会被单笔异常价格带偏
# ---------------------------------------------------------------
def _monthly_profile(sub: pd.DataFrame) -> pd.DataFrame:
    """商品/品类的月度画像: 销量、GMV、量价加权均价"""
    g = sub.groupby("ym").agg(qty=("price", "size"), gmv=("price", "sum"),
                              p_mean=("price", "mean"))
    g["p_wavg"] = g["gmv"] / g["qty"]
    return g


# ---------------------------------------------------------------
# 【算法2-3】定价建议
#
#   输入: fact_sales + 选品结果
#   输出: 算法2/algo2_pricing_result.csv（50 行，31 个有建议价）
#         + algo2_pricing_skipped.csv（19 行样本不足明细）
#
#   策略:
#     b < -1（富有弹性）→ 降价增收
#     b > -1（缺乏弹性）→ 提价增收
#     建议价约束在现价 ±15% 内
#
#   样本门槛（关键设计）:
#     月度观测 ≥ 10 个月
#     价格变异系数 ≥ 2%
#     回归 R² ≥ 0.15
#     弹性必须为负
#   → 不满足就"不给建议价"，suggested_price 留 NULL，
#     明确标注"数据不足"，而不是硬给一个不可信的数值
#
#   ⚠️ 请 reviewer 重点核对: 门槛是否过严/过松？
#      当前 50 个商品只有 7 个达到商品级弹性，19 个完全给不出建议。
# ---------------------------------------------------------------
def run_pricing(sales: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    log(f"\n[定价] 对候选商品 {len(selected)} 个估计价格弹性 "
        f"(门槛: ≥{MIN_MONTHS} 个月观测, 价变异≥{MIN_PRICE_SD:.0%}, R²≥{ELAS_R2_MIN})")

    # ---- 品类级弹性(商品样本不足时回退) ----
    cat_el: dict[str, tuple[float, float]] = {}
    for cat, sub in sales.groupby("product_category_name_english"):
        mm = _monthly_profile(sub)
        r = est_elasticity(mm["p_wavg"].to_numpy(), mm["qty"].to_numpy(), min_months=8)
        # 理论上弹性应为负; 若拟合为正说明是需求增长趋势主导, 不可用于定价
        if r and r[0] < 0 and np.isfinite(r[1]):
            cat_el[cat] = (max(-3.0, min(-0.1, r[0])), r[1])
    log(f"  - 可用品类级弹性: {len(cat_el)} / {sales['product_category_name_english'].nunique()} 个品类")

    rows, skipped = [], []
    for _, it in selected.iterrows():
        pid, cat = it["product_id"], it["category"]
        sub = sales[sales["product_id"] == pid]
        mm = _monthly_profile(sub)
        p_wavg = float(mm["p_wavg"].mean()) if len(mm) else float(it["avg_price"])
        p_cv = float(mm["p_wavg"].std(ddof=1) / mm["p_wavg"].mean()) if len(mm) > 1 and mm["p_wavg"].mean() > 0 else 0.0

        r = est_elasticity(mm["p_wavg"].to_numpy(), mm["qty"].to_numpy(),
                           min_months=MIN_MONTHS)

        # 判定弹性来源
        if r and r[0] < 0 and r[1] >= ELAS_R2_MIN and p_cv >= MIN_PRICE_SD:
            elas, src, r2, conf = r[0], "商品级价格弹性", r[1], "高"
        elif cat in cat_el:
            elas, (r2, _) = cat_el[cat][0], (cat_el[cat][1], None)
            src, conf = "品类级价格弹性(商品样本不足)", "中"
        else:
            # 样本不足: 不出建议价, 只标注区间, 避免给出不可信的结论
            elas, src, r2, conf = None, "样本不足", np.nan, "低"
            skipped.append({
                "product_id": pid, "category": cat,
                "months_observed": int(len(mm)),
                "price_cv_pct": round(p_cv * 100, 2),
                "reason": f"月度观测 {len(mm)}<{MIN_MONTHS} 或价格变异不足, 无法估计弹性",
            })

        p_cur = round(p_wavg, 2)
        p_lo, p_hi = round(p_cur * (1 - PRICE_BOUND), 2), round(p_cur * (1 + PRICE_BOUND), 2)

        if elas is None:
            rows.append({
                "product_id": pid, "category": cat,
                "selection_type": it["selection_type"], "rank_in_selection": int(it["rank"]),
                "months_observed": int(len(mm)), "price_cv_pct": round(p_cv * 100, 2),
                "current_price": p_cur, "suggested_price": "",
                "price_lower_95": p_lo, "price_upper_95": p_hi, "price_change_pct": "",
                "elasticity": "", "elasticity_source": src, "elasticity_r2": "",
                "confidence": conf,
                "expected_qty_change_pct": "", "expected_revenue_change_pct": "",
                "pricing_rule": "样本不足, 不给建议价",
                "method": "log-log 价格弹性回归 + 收入最大化",
                "note": "价格区间由历史均价±15%给出, 仅作参考, 未做弹性推测",
            })
            continue

        elas = max(-3.0, min(-0.1, float(elas)))
        if elas > -1:
            p_sug, rule = p_hi, f"弹性{elas:.2f} > -1(缺乏弹性), 提价增收"
        else:
            p_sug, rule = p_lo, f"弹性{elas:.2f} < -1(富有弹性), 降价增收"
        p_sug = float(np.clip(p_sug, p_lo, p_hi))
        # 用舍入后的价格回算幅度, 保证与价格列自洽(且不越出 ±PRICE_BOUND)
        p_sug = round(p_sug, 2)
        chg = round((p_sug / p_cur - 1) * 100, 2) if p_cur > 0 else 0.0
        chg = max(-PRICE_BOUND * 100, min(PRICE_BOUND * 100, chg))

        dq = (p_sug / p_cur) ** elas - 1 if p_cur > 0 else 0.0
        dr = (p_sug / p_cur) ** (1 + elas) - 1 if p_cur > 0 else 0.0

        rows.append({
            "product_id": pid, "category": cat,
            "selection_type": it["selection_type"], "rank_in_selection": int(it["rank"]),
            "months_observed": int(len(mm)), "price_cv_pct": round(p_cv * 100, 2),
            "current_price": p_cur, "suggested_price": p_sug,
            "price_lower_95": p_lo, "price_upper_95": p_hi,
            "price_change_pct": chg,
            "elasticity": round(elas, 3), "elasticity_source": src,
            "elasticity_r2": round(r2, 3) if np.isfinite(r2) else "",
            "confidence": conf,
            "expected_qty_change_pct": round(dq * 100, 2),
            "expected_revenue_change_pct": round(dr * 100, 2),
            "pricing_rule": rule,
            "method": "log-log 价格弹性回归 + 收入最大化",
            "note": f"当前价为月度量价加权均价; 区间为现价±{PRICE_BOUND:.0%}, 上线前建议 A/B 验证",
        })

    out = pd.DataFrame(rows)
    log(f"  -> 定价行数: {len(out)} (其中可给建议价 {int((out['elasticity'] != '').sum())} 个, "
        f"样本不足 {len(skipped)} 个)")
    if len(out):
        has = out[out["elasticity"] != ""]
        if len(has):
            log(f"  - 弹性来源: {has['elasticity_source'].value_counts().to_dict()}")
            log(f"  - 建议提价 {int((has['price_change_pct'] > 0).sum())} 个, "
                f"建议降价 {int((has['price_change_pct'] < 0).sum())} 个")
            log(f"  - 平均预期收入变化: {has['expected_revenue_change_pct'].mean():.2f}%")
    if skipped:
        sk = pd.DataFrame(skipped)
        sk.to_csv(OUTPUT / "algo2_pricing_skipped.csv", index=False, encoding="utf-8-sig")
        log(f"  - 样本不足明细已写入 algo2_pricing_skipped.csv ({len(sk)} 行)")
    return out


# ============================================================
# 5. 最终统计
# ============================================================


# ---------------------------------------------------------------
# 【算法2-4】最终统计结果
#   输出: 算法2/algo2_summary_stats.csv（31 项）
# ---------------------------------------------------------------
def run_summary(sales: pd.DataFrame, rfm_path: Path,
                forecast: pd.DataFrame, selection: pd.DataFrame,
                pricing: pd.DataFrame) -> pd.DataFrame:
    log("\n[统计] 生成最终统计结果")
    rfm = pd.read_csv(rfm_path)
    max_week = sales["year_week"].max()
    has_price = pricing[pricing["elasticity"] != ""] if len(pricing) else pricing
    rows = [
        ("数据集", "原始销售记录数", f"{len(sales):,}", "fact_sales.csv 有效行"),
        ("数据集", "覆盖品类数", f"{sales['product_category_name_english'].nunique()}", "英文品类名去重"),
        ("数据集", "覆盖商品数", f"{sales['product_id'].nunique():,}", "product_id 去重"),
        ("数据集", "覆盖用户数", f"{rfm['customer_unique_id'].nunique():,}", "fact_rfm.csv"),
        ("数据集", "时间范围", f"{sales['order_purchase_timestamp'].min().date()} ~ "
                              f"{sales['order_purchase_timestamp'].max().date()}", "下单时间"),
        ("数据集", "数据截至周", str(max_week), "year_week 最大值"),
        ("数据集", "总 GMV", f"{sales['price'].sum():,.2f}", "price 求和"),
        ("数据集", "客单价", f"{rfm['monetary'].mean():,.2f}", "RFM monetary 均值"),
        ("预测", "预测品类数", f"{forecast['category'].nunique()}", "满足历史周数要求"),
        ("预测", "预测周数", f"{FORECAST_WEEKS}", "向后预测"),
        ("预测", "预测记录数", f"{len(forecast)}", "品类 × 周"),
        ("预测", "主模型平均MAPE", f"{forecast['mape_model_pct'].mean():.2f}%", "holdout 平均(受低基数周影响偏高)"),
        ("预测", "主模型MAPE中位数", f"{forecast['mape_model_pct'].median():.2f}%", "holdout 中位数"),
        ("预测", "基线平均MAPE", f"{forecast['mape_baseline_pct'].mean():.2f}%", "MA4 基线"),
        ("预测", "主模型WAPE", f"{forecast['wape_model_pct'].mean():.2f}%", "总量加权, 对低基数周稳健"),
        ("预测", "基线WAPE", f"{forecast['wape_baseline_pct'].mean():.2f}%", "MA4 基线"),
        ("预测", "平均提升(MAPE)", f"{forecast['improvement_pct'].mean():.2f}%", "相对基线, 负数表示不及基线"),
        ("预测", "主模型分布", " / ".join(
            f"{k}:{v}" for k, v in forecast["model"].value_counts().items()), "各品类选中的模型"),
        ("选品", "候选商品数", f"{sales['product_id'].nunique():,}", "全量商品"),
        ("选品", "输出商品数", f"{len(selection)}", "增长榜 + 高销量分析池"),
        ("选品", "其中增长榜", f"{(selection['selection_type'] == '增长榜').sum()}", "近%d周增长打分" % RECENT_W),
        ("选品", "其中分析池", f"{(selection['selection_type'] == '高销量分析池').sum()}", "按累计GMV, 用于定价估计"),
        ("选品", "强推数量", f"{(selection['recommendation'] == '强推').sum()}", "总分≥80"),
        ("选品", "合计近期GMV", f"{selection['gmv_recent'].sum():,.2f}", "近%s周" % RECENT_W),
        ("定价", "定价商品数", f"{len(pricing)}", "与选品一致"),
        ("定价", "可给建议价", f"{len(has_price)}", "弹性估计通过样本门槛"),
        ("定价", "样本不足", f"{len(pricing) - len(has_price)}", "仅给价格区间, 不出建议价"),
        ("定价", "建议提价数", f"{int((has_price['price_change_pct'].astype(float) > 0).sum()) if len(has_price) else 0}",
         "缺乏弹性(弹性>-1)"),
        ("定价", "建议降价数", f"{int((has_price['price_change_pct'].astype(float) < 0).sum()) if len(has_price) else 0}",
         "富有弹性(弹性<-1)"),
        ("定价", "商品级弹性占比",
         f"{int((has_price['elasticity_source'] == '商品级价格弹性').sum()) if len(has_price) else 0}/{len(pricing)}",
         "样本充分度"),
        ("定价", "平均预期收入变化",
         f"{has_price['expected_revenue_change_pct'].astype(float).mean():.2f}%" if len(has_price) else "N/A",
         "模型测算, 需 A/B 验证"),
    ]
    return pd.DataFrame(rows, columns=["类别", "统计项", "数值", "口径说明"])


# ============================================================


# ---------------------------------------------------------------
# 【算法2-附加】选品 Top10 命中率（时间切分回测）
#
#   输入: cleaned/fact_sales.csv
#   输出: 算法2/algo2_selection_hitrate.csv（4 行）
#
#   回测设计:
#     训练期: < 2018-05，用该期数据选 Top10
#     验证期: >= 2018-05，检验是否落在 GMV Top20% 中
#
#   三组对照:
#     综合得分(规模+增长) Top10  —— 我们的策略
#     纯规模(训练期GMV) Top10    —— 基线对照
#     随机选 10 个（理论期望）    —— 下界
#
#   ⚠️ 反直觉结论: 纯规模 Top10 命中率 100%，反而高于综合得分 70%。
#      原因: Olist 品类头部极其稳定，加"增长率"因子反而引入噪声。
#      → 建议 reviewer 讨论: 是否应降低增长分权重(0.40→0.20)
# ---------------------------------------------------------------
def build_hitrate():
    log()
    log("=" * 72)
    log("算法2  选品 Top10 命中率（时间切分回测）")
    log("=" * 72)

    sales = pd.read_csv(CLEAN / "fact_sales.csv",
                        usecols=["product_id", "product_category_name_english",
                                 "price", "order_purchase_timestamp"],
                        parse_dates=["order_purchase_timestamp"],
                        low_memory=False)
    sales = sales.dropna(subset=["product_category_name_english"])
    sales["month"] = sales["order_purchase_timestamp"].dt.to_period("M")

    cut = pd.Period("2018-05", "M")
    train = sales[sales["month"] < cut]
    valid = sales[sales["month"] >= cut]
    log(f"  训练期: < {cut}  ({len(train):,} 行)")
    log(f"  验证期: >= {cut}  ({len(valid):,} 行, "
        f"{valid['month'].min()} ~ {valid['month'].max()})")

    def gmv_by(d, key):
        g = d.groupby(key)["price"].sum()
        return g

    rows = []

    # ---------- 品类级 ----------
    tr_cat = gmv_by(train, "product_category_name_english")
    va_cat = gmv_by(valid, "product_category_name_english")
    # 训练期增长率: 后3个月 vs 前3个月
    months = sorted(train["month"].unique())
    if len(months) >= 6:
        recent_m = months[-3:]
        prior_m = months[-6:-3]
        rg = (train[train["month"].isin(recent_m)]
              .groupby("product_category_name_english")["price"].sum())
        pg = (train[train["month"].isin(prior_m)]
              .groupby("product_category_name_english")["price"].sum())
        growth = ((rg - pg) / pg.replace(0, np.nan) * 100).dropna()
    else:
        growth = pd.Series(dtype=float)

    # 策略：综合得分（规模 + 增长），与 algo2_selection_result 同口径
    score = (0.45 * tr_cat.rank(pct=True) * 100
             + 0.40 * growth.reindex(tr_cat.index).fillna(0).clip(-100, 300).rank(pct=True) * 100)
    top10_cat = list(score.nlargest(10).index)

    k20 = max(1, int(round(len(va_cat) * 0.2)))
    valid_top20 = set(va_cat.nlargest(k20).index)
    hit = len(set(top10_cat) & valid_top20)
    rows.append({
        "level": "品类级",
        "strategy": "综合得分(规模+增长) Top10",
        "top_n": 10,
        "hit_cnt": hit,
        "hit_rate_pct": round(hit / 10 * 100, 2),
        "valid_top20_cnt": k20,
        "valid_candidate_cnt": len(va_cat),
        "note": f"验证期 GMV Top20% 品类数 = {k20}",
        "top_list": " / ".join(top10_cat),
    })

    # 纯规模基线
    top10_scale = list(tr_cat.nlargest(10).index)
    hit_s = len(set(top10_scale) & valid_top20)
    rows.append({
        "level": "品类级",
        "strategy": "纯规模(训练期GMV) Top10",
        "top_n": 10,
        "hit_cnt": hit_s,
        "hit_rate_pct": round(hit_s / 10 * 100, 2),
        "valid_top20_cnt": k20,
        "valid_candidate_cnt": len(va_cat),
        "note": "基线对照",
        "top_list": " / ".join(top10_scale),
    })

    # 随机基线（期望值 = Top10/总品类 与 Top20% 重叠）
    rand_expected = 10 * k20 / len(va_cat)
    rows.append({
        "level": "品类级",
        "strategy": "随机选 10 个（理论期望）",
        "top_n": 10,
        "hit_cnt": round(rand_expected, 2),
        "hit_rate_pct": round(rand_expected / 10 * 100, 2),
        "valid_top20_cnt": k20,
        "valid_candidate_cnt": len(va_cat),
        "note": "理论期望，非实测",
        "top_list": "",
    })

    # ---------- 商品级 ----------
    tr_prod = gmv_by(train, "product_id")
    va_prod = gmv_by(valid, "product_id")
    top10_prod = list(tr_prod.nlargest(10).index)
    k20p = max(1, int(round(len(va_prod) * 0.2)))
    valid_top20p = set(va_prod.nlargest(k20p).index)
    hit_p = len(set(top10_prod) & valid_top20p)
    rows.append({
        "level": "商品级",
        "strategy": "训练期GMV Top10 商品",
        "top_n": 10,
        "hit_cnt": hit_p,
        "hit_rate_pct": round(hit_p / 10 * 100, 2),
        "valid_top20_cnt": k20p,
        "valid_candidate_cnt": len(va_prod),
        "note": f"验证期 GMV Top20% 商品数 = {k20p:,}",
        "top_list": " / ".join(str(x)[:16] for x in top10_prod),
    })

    df = pd.DataFrame(rows)
    df["train_window"] = f"{train['month'].min()} ~ {train['month'].max()}"
    df["valid_window"] = f"{valid['month'].min()} ~ {valid['month'].max()}"
    df.to_csv(OUT2 / "algo2_selection_hitrate.csv", index=False, encoding="utf-8-sig")

    for _, r in df.iterrows():
        log(f"  [{r['level']}] {r['strategy']:<30} 命中 {r['hit_cnt']}/{r['top_n']}"
            f"  = {r['hit_rate_pct']:.2f}%")
    log(f"  -> algo2_selection_hitrate.csv  {len(df)} 行")
    return df


# ============================================================
# 文档生成
# ============================================================


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    print("=" * 74)
    print("算法2 模型：销量预测 + 选品推荐 + 定价建议")
    print("=" * 74)
    print(f"  数据目录: {CLEAN}")
    print(f"  输出目录: {OUT}")
    print()

    sales = load_data()
    series_map = build_weekly_series(sales)
    print(f"[序列] 品类周序列: {len(series_map)} 个")

    forecast, experiment = run_forecast(series_map)
    selection = run_selection(sales)
    pricing = run_pricing(sales, selection)
    summary = run_summary(sales, CLEAN / "fact_rfm.csv",
                          forecast, selection, pricing)
    hitrate = build_hitrate()

    files = {
        "algo2_forecast_result.csv": forecast,
        "algo2_selection_result.csv": selection,
        "algo2_pricing_result.csv": pricing,
        "algo2_offline_experiment.csv": experiment,
        "algo2_summary_stats.csv": summary,
        "algo2_selection_hitrate.csv": hitrate,
    }
    print()
    print("=" * 74)
    print("写出结果:")
    print("=" * 74)
    for name, df in files.items():
        p = OUT / name
        df.to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  {name:<34} {len(df):>7,} 行")

    # 定价跳过明细单独写
    return 0


if __name__ == "__main__":
    sys.exit(main())

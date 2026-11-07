#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
算法1 模型实现：数据预处理 + RFM 用户分群
==========================================

【本文件用途】
    这是算法1 的完整模型实现，用于组内代码交叉 Review。
    覆盖任务表 10.14 ~ 10.19 的算法部分：
      10.16 RFM 指标 + K-Means 聚类分群
      10.17 转化率 / 复购 / 分品类复购 + 离线实验第一部分
      10.19 最终统计结果

【输入】
    cleaned/fact_rfm.csv            95,420 行，4 列（customer_unique_id/recency/frequency/monetary）
    cleaned/fact_order_master.csv   99,441 行，33 列（订单宽表）
    cleaned/fact_sales.csv          112,650 行，26 列（销售明细宽表）

【输出】（全部写入 算法1/ 目录，UTF-8 with BOM，Excel 可直接打开）
    algo1_rfm_clusters.csv               95,420 行 × 13 列   RFM + K-Means + 规则分群
    algo1_conversion_funnel.csv               5 行 ×  8 列   订单转化漏斗
    algo1_order_status.csv                    8 行 ×  3 列   订单状态分布
    algo1_repurchase_metrics.csv             19 行 ×  4 列   整体复购指标
    algo1_category_repurchase.csv            74 行 ×  9 列   分品类复购
    algo1_offline_experiment_part1.csv        5 行 × 14 列   分群策略离线对照
    algo1_summary_stats.csv                  22 行 ×  4 列   最终统计

【依赖】
    pandas >= 1.5, numpy >= 1.20, scikit-learn >= 1.0
    （不需要 statsmodels）

【运行】
    python algo1_model.py
    # 会自动从 ../cleaned 读数据、写到 ../算法1
    # 若目录结构不同，改下面的 BASE 即可

【Review 重点】
    1. f_score_by_threshold()  —— F 评分为什么不能用五分位（最关键）
    2. build_funnel()          —— 漏斗为什么必须用累积 AND 条件
    3. build_offline_experiment() —— 时间切分是否合理、策略人数是否可比
    4. K-Means 的 k=4 是否合适（未做肘部法则系统搜索）

【已知局限】
    - 无浏览/加购日志，转化漏斗只能用订单时间戳近似
    - 品类复购率极低（中位数 0.65%），受数据集特性限制
    - 离线实验区分度有限（验证期 97.7% 是新用户）
"""
from __future__ import annotations

import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------- 路径与参数 ----------------
BASE = Path(__file__).resolve().parent
# 兼容两种存放方式：脚本在项目根目录，或放在 算法代码/ 子目录下
PROJ = BASE if (BASE / "cleaned").is_dir() else BASE.parent
CLEAN = PROJ / "cleaned"
OUT = PROJ / "算法1"
OUT.mkdir(exist_ok=True)

SEED = 42                           # 全局随机种子，保证结果可复现
np.random.seed(SEED)

def log(m=""):
    print(m, flush=True)


# ============================================================
# 工具：复刻 import_algo1.py 的五分位 + 8 类规则（保证与库里一致）
# ============================================================


# ---------------------------------------------------------------
# 【工具】计算 20/40/60/80 分位点
#   输入: values 一维数值列表
#   输出: 4 个分位点的值
#   说明: 用"排序后按下标取第 N% 个元素"近似分位数，不依赖 numpy
# ---------------------------------------------------------------
def quintile_boundaries(values):
    s = sorted(values)
    n = len(s)
    return [s[min(int(n * q), n - 1)] for q in (0.20, 0.40, 0.60, 0.80)]


# ---------------------------------------------------------------
# 【工具】按分位点把数值映射成 1~5 分
#   输入: values（用于定分位）、higher_is_better（True=值越大分越高）
#   输出: 打分函数 score(value) -> 1..5
#   用途: R 用 higher_is_better=False（越小越好），M 用 True
#   注意: 对 frequency 这种大量重复的离散值不适用，见 f_score_by_threshold
# ---------------------------------------------------------------
def make_scorer(values, higher_is_better):
    b = quintile_boundaries(values)

    if higher_is_better:
        def score(v):
            if v <= b[0]: return 1
            if v <= b[1]: return 2
            if v <= b[2]: return 3
            if v <= b[3]: return 4
            return 5
    else:
        def score(v):
            if v <= b[0]: return 5
            if v <= b[1]: return 4
            if v <= b[2]: return 3
            if v <= b[3]: return 2
            return 1
    return score


RULE8 = {
    ("高", "高", "高"): "重要价值用户",
    ("低", "高", "高"): "重要保持用户",
    ("高", "低", "高"): "重要发展用户",
    ("低", "低", "高"): "重要挽留用户",
    ("高", "高", "低"): "一般价值用户",
    ("低", "高", "低"): "一般保持用户",
    ("高", "低", "低"): "一般发展用户",
    ("低", "低", "低"): "一般挽留用户",
}


# ---------------------------------------------------------------
# 【规则分群】R/F/M 各 ≥3 记为"高"，组合成 8 类人群
#   输入: r, f, m 三个 1..5 的得分
#   输出: 8 类标签之一（如 "重要价值用户"）
# ---------------------------------------------------------------
def rule8(r, f, m):
    R = "高" if r >= 3 else "低"
    F = "高" if f >= 3 else "低"
    M = "高" if m >= 3 else "低"
    return RULE8[(R, F, M)]


# ============================================================
# 算法1 - 1. RFM + K-Means 分群
# ============================================================


# ---------------------------------------------------------------
# 【关键修正】F 评分用业务阈值，而不是五分位
#
#   问题背景:
#     Olist 数据有 96.95% 的用户 frequency == 1。
#     若用 pd.qcut(rank, 5) 强制均分五档，会出现:
#       - F 分 1/2/3/4 全部对应 frequency=1（各 19,084 人）
#       - F 分 5 里仍有 84.7% 是只买过一次的用户
#       → 54,339 个只买 1 次的用户被错标为"高 F"，
#         "重要价值用户"被虚高到 1,717 人（真实应为 166 人）
#
#   修正方案:
#     F=1→1分, F=2→2分, F=3→3分, F=4→4分, F>=5→5分
#
#   影响: 8 类分群的语义才正确。
#   → 这是本次代码 review 最值得关注的一处，请重点核对。
# ---------------------------------------------------------------
def f_score_by_threshold(f: int) -> int:
    """F 评分改用业务阈值（而非五分位）。

    为什么必须改：
        96.95% 的用户 frequency == 1，若用 pd.qcut(rank) 强制均分五档，
        会出现 F 分 1~4 全部对应 frequency=1、F 分 5 里仍有 85% 是 frequency=1
        的失真情况（82,507/95,420 人的 F 分无区分度）。
        改用阈值后，F 分直接反映真实购买次数，语义正确。
    """
    if f <= 1:
        return 1
    if f == 2:
        return 2
    if f == 3:
        return 3
    if f == 4:
        return 4
    return 5


# ---------------------------------------------------------------
# 【算法1-1】RFM 用户分群（K-Means 4 类 + 规则 8 类）
#
#   输入: cleaned/fact_rfm.csv（customer_unique_id, recency, frequency, monetary）
#   输出: 算法1/algo1_rfm_clusters.csv（95,420 行 × 13 列）
#
#   步骤:
#     1. R/M 用五分位打分；F 用业务阈值（见 f_score_by_threshold）
#     2. 拼 rfm_score（如 "545"）并按规则表出 8 类标签
#     3. K-Means 聚类: log1p 压缩偏态 → StandardScaler 标准化 → k=4
#     4. 按各簇 monetary 均值降序映射语义标签
#     5. 计算轮廓系数（抽样 5000 点，全量 O(n^2) 太慢）
#
#   注意: 同时输出 f_score_quantile 列（旧五分位结果），便于对比两种做法
# ---------------------------------------------------------------
def build_rfm_clusters():
    log("=" * 72)
    log("算法1-1  RFM 用户分群（K-Means 4 类 + 规则 8 类）")
    log("=" * 72)

    rfm = pd.read_csv(CLEAN / "fact_rfm.csv")
    log(f"  读入 fact_rfm.csv: {len(rfm):,} 行")

    rec = rfm["recency"].astype(int).tolist()
    fre = rfm["frequency"].astype(int).tolist()
    # 金额统一保留 2 位小数后再定分位：float 累加会出现 39.90000000000001
    # 这类毛刺，导致"金额相同"的客户被分到相邻两档（实测 909 个 39.90 元的
    # 客户里有 1 个被标成 m_score=2，其余 908 个是 1）。也避免换 pandas
    # 版本/换机器时结果漂移。
    mon = rfm["monetary"].astype(float).round(2).tolist()

    # R、M 是连续/近似连续值，用五分位合理
    s_r = make_scorer(rec, higher_is_better=False)
    s_m = make_scorer(mon, higher_is_better=True)
    rfm["r_score"] = [s_r(v) for v in rec]
    rfm["m_score"] = [s_m(v) for v in mon]

    # F 用业务阈值（见 f_score_by_threshold 说明）
    rfm["f_score"] = [f_score_by_threshold(v) for v in fre]

    # 同时保留"原五分位版"的 F 分，用于量化失真程度
    f_quantile = pd.qcut(pd.Series(fre).rank(method="first"), 5,
                         labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["f_score_quantile"] = f_quantile.values

    n1 = int(((rfm["f_score_quantile"] >= 3) & (rfm["frequency"] == 1)).sum())
    n2 = int((rfm["f_score_quantile"] >= 3).sum())
    log(f"  【修正说明】原五分位把 {n1:,}/{n2:,} 个"
        f"（{n1/max(n2,1)*100:.1f}%）只买 1 次的用户标成了「高 F」")
    log(f"  修正后 F 分分布:")
    for k, v in rfm["f_score"].value_counts().sort_index().items():
        fr = rfm.loc[rfm["f_score"] == k, "frequency"]
        log(f"      F={k}: {v:>7,} 人   真实购买次数 {fr.min()}~{fr.max()}")

    rfm["rfm_score"] = (rfm["r_score"].astype(str) + rfm["f_score"].astype(str)
                        + rfm["m_score"].astype(str))
    rfm["rfm_segment_rule8"] = [rule8(r, f, m) for r, f, m in
                                zip(rfm["r_score"], rfm["f_score"], rfm["m_score"])]

    log("  规则 8 类分布（修正后）:")
    for k, v in rfm["rfm_segment_rule8"].value_counts().items():
        log(f"      {k:<10} {v:>7,} 人 ({v/len(rfm)*100:5.2f}%)")

    # --- K-Means 4 类（任务要求的聚类分群） ---
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    X = np.log1p(rfm[["recency", "frequency", "monetary"]].astype(float))
    Xs = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=4, random_state=SEED, n_init=10)
    rfm["kmeans_cluster"] = km.fit_predict(Xs)

    idx = np.random.RandomState(SEED).choice(len(Xs), size=min(5000, len(Xs)),
                                             replace=False)
    sil = float(silhouette_score(Xs[idx], rfm["kmeans_cluster"].to_numpy()[idx]))
    inertia = float(km.inertia_)
    log(f"  K-Means(k=4): inertia={inertia:,.1f}  轮廓系数(抽样5000)={sil:.4f}")

    order = (rfm.groupby("kmeans_cluster")["monetary"].mean()
             .sort_values(ascending=False).index.tolist())
    names = ["高价值客户", "中价值客户", "潜力成长客户", "流失风险客户"]
    label_map = {c: names[i] for i, c in enumerate(order)}
    rfm["rfm_segment_kmeans4"] = rfm["kmeans_cluster"].map(label_map)

    log("  K-Means 4 类分布:")
    for k, v in rfm["rfm_segment_kmeans4"].value_counts().items():
        sub = rfm[rfm["rfm_segment_kmeans4"] == k]
        log(f"      {k:<8} {v:>7,} 人 ({v/len(rfm)*100:5.2f}%)  "
            f"人均消费 {sub['monetary'].mean():8.2f}  "
            f"平均频次 {sub['frequency'].mean():.2f}  "
            f"平均R {sub['recency'].mean():.0f}天")

    cols = ["customer_unique_id", "recency", "frequency", "monetary",
            "r_score", "f_score", "m_score", "rfm_score",
            "kmeans_cluster", "rfm_segment_kmeans4", "rfm_segment_rule8",
            "f_score_quantile"]
    out = rfm[cols].copy()
    out["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(OUT / "algo1_rfm_clusters.csv", index=False, encoding="utf-8-sig")
    log(f"  -> algo1_rfm_clusters.csv  {len(out):,} 行")

    return rfm, {"silhouette": sil, "inertia": inertia,
                 "f_wrong_hi": n1, "f_quantile_hi": n2}


# ============================================================
# 算法1 - 2. 转化漏斗
# ============================================================


# ---------------------------------------------------------------
# 【算法1-2】订单转化漏斗
#
#   输入: cleaned/fact_order_master.csv
#   输出: 算法1/algo1_conversion_funnel.csv + algo1_order_status.csv
#
#   关键设计: 用"累积 AND 条件"保证漏斗严格单调递减
#     m1 = approved_at 非空
#     m2 = m1 & carrier_date 非空
#     m3 = m2 & delivered_date 非空
#     m4 = m3 & review_creation_date 非空
#
#   ⚠️ 踩过的坑: 不能用 review_score 判断"已评价"——
#      该字段在宽表里已被填满(100% 非空)，会导致"已评价"订单数
#      超过"已送达"，漏斗出现 103%，逻辑上不可能。
#
#   请 reviewer 重点核对: m1~m4 的累积关系是否正确
# ---------------------------------------------------------------
def build_funnel():
    log()
    log("=" * 72)
    log("算法1-2  订单转化漏斗")
    log("=" * 72)

    om = pd.read_csv(CLEAN / "fact_order_master.csv", low_memory=False,
                     parse_dates=["order_purchase_timestamp", "order_approved_at",
                                  "order_delivered_carrier_date",
                                  "order_delivered_customer_date",
                                  "review_creation_date"])
    total_orders = len(om)
    log(f"  fact_order_master: {total_orders:,} 个订单")

    # 用累积 AND 条件，保证漏斗严格单调递减
    # 注意: review_score 在宽表中已被填满(100% 非空)，不能用它判"已评价"，
    #       必须用 review_creation_date（98,673 非空）
    m1 = om["order_approved_at"].notna()
    m2 = m1 & om["order_delivered_carrier_date"].notna()
    m3 = m2 & om["order_delivered_customer_date"].notna()
    m4 = m3 & om["review_creation_date"].notna()

    steps = [
        ("下单", pd.Series(True, index=om.index)),
        ("支付获批", m1),
        ("已发货", m2),
        ("已送达", m3),
        ("已评价", m4),
    ]
    rows = []
    prev = total_orders
    for name, mask in steps:
        n = int(mask.sum())
        rows.append({
            "step_no": len(rows) + 1,
            "step_name": name,
            "order_cnt": n,
            "rate_vs_total_pct": round(n / total_orders * 100, 2),
            "rate_vs_prev_pct": round(n / prev * 100, 2) if prev else 0.0,
            "drop_cnt": prev - n,
            "drop_rate_pct": round((prev - n) / prev * 100, 2) if prev else 0.0,
            "definition": {
                "下单": "全部订单",
                "支付获批": "order_approved_at 非空",
                "已发货": "且 order_delivered_carrier_date 非空",
                "已送达": "且 order_delivered_customer_date 非空",
                "已评价": "且 review_creation_date 非空（累积条件）",
            }[name],
        })
        prev = n
    funnel = pd.DataFrame(rows)
    funnel.to_csv(OUT / "algo1_conversion_funnel.csv", index=False,
                  encoding="utf-8-sig")
    for r in rows:
        log(f"      {r['step_name']:<6} {r['order_cnt']:>7,}  "
            f"占总量 {r['rate_vs_total_pct']:>6.2f}%  "
            f"环节转化 {r['rate_vs_prev_pct']:>6.2f}%  "
            f"流失 {r['drop_cnt']:>6,}")
    log(f"  -> algo1_conversion_funnel.csv  {len(funnel)} 行")

    # 状态分布（补充口径）
    status = om["order_status"].value_counts().reset_index()
    status.columns = ["order_status", "order_cnt"]
    status["rate_pct"] = (status["order_cnt"] / total_orders * 100).round(2)
    status.to_csv(OUT / "algo1_order_status.csv", index=False, encoding="utf-8-sig")
    log(f"  -> algo1_order_status.csv  {len(status)} 行")
    return om, funnel


# ============================================================
# 算法1 - 3. 整体复购指标
# ============================================================


# ---------------------------------------------------------------
# 【算法1-3】整体复购指标
#
#   输入: om（订单宽表）、rfm（RFM 表）
#   输出: 算法1/algo1_repurchase_metrics.csv（19 项指标）
#
#   两个口径:
#     用户口径: 复购用户数 = frequency>1 的用户
#     订单口径: 复购相关订单 = 所在用户订单数>1 的订单
#
#   注意: 复购率 = 复购用户数 / 总用户数，不是复购订单/总订单
# ---------------------------------------------------------------
def build_repurchase(om, rfm):
    log()
    log("=" * 72)
    log("算法1-3  复购指标")
    log("=" * 72)

    n_users = len(rfm)
    rep_users = int((rfm["frequency"] > 1).sum())
    rep_rate = rep_users / n_users * 100

    delivered = om[om["order_status"] == "delivered"]
    gmv = float(om["gmv"].sum())
    n_orders = len(om)

    rep_orders = int(om.groupby("customer_unique_id")["order_id"].transform("count")
                     .gt(1).sum()) if "customer_unique_id" in om else 0

    rows = [
        ("用户口径", "总用户数", n_users, "fact_rfm 去重用户"),
        ("用户口径", "复购用户数", rep_users, "frequency > 1"),
        ("用户口径", "复购用户占比(%)", round(rep_rate, 2), "复购用户 / 总用户"),
        ("用户口径", "单次购买用户数", n_users - rep_users, "frequency = 1"),
        ("用户口径", "单次购买占比(%)", round((n_users - rep_users) / n_users * 100, 2), ""),
        ("用户口径", "人均订单数", round(float(rfm["frequency"].mean()), 3), "频率均值"),
        ("用户口径", "人均消费额", round(float(rfm["monetary"].mean()), 2), "ARPU"),
        ("用户口径", "复购用户人均消费", round(float(rfm.loc[rfm["frequency"] > 1, "monetary"].mean()), 2), ""),
        ("用户口径", "单次用户人均消费", round(float(rfm.loc[rfm["frequency"] == 1, "monetary"].mean()), 2), ""),
        ("订单口径", "总订单数", n_orders, "fact_order_master"),
        ("订单口径", "已送达订单数", len(delivered), "order_status = delivered"),
        ("订单口径", "送达率(%)", round(len(delivered) / n_orders * 100, 2), ""),
        ("订单口径", "取消订单数", int((om["order_status"] == "canceled").sum()), ""),
        ("订单口径", "取消率(%)", round((om["order_status"] == "canceled").mean() * 100, 2), ""),
        ("订单口径", "总 GMV", round(gmv, 2), "gmv 求和"),
        ("订单口径", "客单价", round(gmv / n_orders, 2), "GMV / 订单数"),
        ("订单口径", "复购相关订单占比(%)", round(rep_orders / n_orders * 100, 2),
         "所在用户订单数>1 的订单占比"),
        ("订单口径", "平均评分", round(float(om["review_score"].mean()), 3), "review_score 均值"),
        ("订单口径", "平均送达天数", round(float(om["delivery_days"].mean()), 2), "delivery_days 均值"),
    ]
    df = pd.DataFrame(rows, columns=["group", "metric", "value", "note"])
    df.to_csv(OUT / "algo1_repurchase_metrics.csv", index=False, encoding="utf-8-sig")
    for _, r in df.iterrows():
        log(f"      [{r['group']}] {r['metric']:<22} {r['value']}")
    log(f"  -> algo1_repurchase_metrics.csv  {len(df)} 行")

    return {
        "n_users": n_users, "rep_users": rep_users, "rep_rate": rep_rate,
        "gmv": gmv, "n_orders": n_orders, "aov": gmv / n_orders,
        "rep_orders": rep_orders,
    }


# ============================================================
# 算法1 - 4. 分品类复购
# ============================================================


# ---------------------------------------------------------------
# 【算法1-4】分品类复购明细
#
#   输入: cleaned/fact_sales.csv
#   输出: 算法1/algo1_category_repurchase.csv（74 个品类）
#
#   逻辑: 先按 (品类, 用户) 聚合出每人每品类买了几次，
#         再按品类统计买家数、复购买家数、复购率
#
#   注意: 品类内复购率 ≠ 用户整体复购率，两者不要混用
# ---------------------------------------------------------------
def build_category_repurchase():
    log()
    log("=" * 72)
    log("算法1-4  分品类复购明细")
    log("=" * 72)

    sales = pd.read_csv(CLEAN / "fact_sales.csv",
                        usecols=["customer_unique_id", "product_category_name_english",
                                 "price", "order_id", "order_status"],
                        low_memory=False)
    sales = sales.dropna(subset=["product_category_name_english"])
    log(f"  fact_sales: {len(sales):,} 行")

    g = (sales.groupby(["product_category_name_english", "customer_unique_id"])
         .agg(buy_times=("order_id", "nunique"), gmv=("price", "sum"))
         .reset_index())
    cat = (g.groupby("product_category_name_english")
           .agg(buyer_cnt=("customer_unique_id", "nunique"),
                rep_buyer_cnt=("buy_times", lambda s: int((s > 1).sum())),
                gmv=("gmv", "sum"),
                avg_buy_times=("buy_times", "mean"))
           .reset_index())
    cat["rep_rate_pct"] = (cat["rep_buyer_cnt"] / cat["buyer_cnt"] * 100).round(2)
    cat["gmv_per_buyer"] = (cat["gmv"] / cat["buyer_cnt"]).round(2)
    cat["avg_buy_times"] = cat["avg_buy_times"].round(3)
    cat["gmv"] = cat["gmv"].round(2)

    n_orders = (sales.groupby("product_category_name_english")["order_id"]
                .nunique().rename("order_cnt").reset_index())
    cat = cat.merge(n_orders, on="product_category_name_english")
    cat = cat.sort_values("gmv", ascending=False)
    cat.insert(0, "rank", range(1, len(cat) + 1))
    cat.to_csv(OUT / "algo1_category_repurchase.csv", index=False,
               encoding="utf-8-sig")

    log(f"  品类数: {len(cat)}")
    log(f"  整体品类复购率中位数: {cat['rep_rate_pct'].median():.2f}%")
    log("  复购率最高的 5 个品类（买家数≥50）:")
    top = cat[cat["buyer_cnt"] >= 50].nlargest(5, "rep_rate_pct")
    for _, r in top.iterrows():
        log(f"      {r['product_category_name_english']:<32} "
            f"复购率 {r['rep_rate_pct']:>5.2f}%  买家 {int(r['buyer_cnt']):>5,}")
    log(f"  -> algo1_category_repurchase.csv  {len(cat)} 行")
    return cat


# ============================================================
# 算法1 - 5. 离线实验第一部分（分群策略对照）
# ============================================================


# ---------------------------------------------------------------
# 【算法1-5】分群策略离线对照实验（第一部分）
#
#   输入: om（订单宽表）
#   输出: 算法1/algo1_offline_experiment_part1.csv（5 个策略）
#
#   实验设计: 时间切分回测（避免用未来信息评估历史策略）
#     训练期: < 2018-06-01，用该期数据算 RFM 与策略
#     验证期: >= 2018-06-01，观察各策略人群的实际复购
#
#   5 个策略（人数统一取 Top20%，保证可比）:
#     A 训练期 RFM 综合分 Top20%
#     B 训练期消费额 Top20%
#     C 训练期购买频次 Top20%
#     D 随机 20%（固定随机种子 42）
#     E 全量用户（基线）
#
#   指标: 命中率、验证期 ARPU、相对随机提升倍数
#
#   ⚠️ 数据特性: 验证期买家 97.7% 是训练期没见过的新用户，
#      训练期用户仅 0.57% 回访。这是 Olist 极低复购(3.05%)的数据特性，
#      不是方法缺陷。请 reviewer 不要据此否定策略有效性。
# ---------------------------------------------------------------
def build_offline_experiment(om):
    log()
    log("=" * 72)
    log("算法1-5  分群策略离线对照实验（第一部分）")
    log("=" * 72)

    df = om[["customer_unique_id", "order_purchase_timestamp", "gmv"]].dropna(
        subset=["customer_unique_id", "order_purchase_timestamp"]).copy()
    df["ts"] = pd.to_datetime(df["order_purchase_timestamp"])

    cut = pd.Timestamp("2018-06-01")
    train = df[df["ts"] < cut]
    valid = df[df["ts"] >= cut]
    log(f"  训练期(<{cut.date()}): {len(train):,} 单, "
        f"{train['customer_unique_id'].nunique():,} 用户")
    log(f"  验证期(>={cut.date()}): {len(valid):,} 单, "
        f"{valid['customer_unique_id'].nunique():,} 用户")

    # 训练期 RFM（用修正后的业务阈值 F 评分）
    tr = (train.groupby("customer_unique_id")
          .agg(last_ts=("ts", "max"), frequency=("ts", "size"), monetary=("gmv", "sum"))
          .reset_index())
    tr["recency"] = (cut - tr["last_ts"]).dt.days
    tr["r_score"] = pd.qcut(tr["recency"].rank(method="first"), 5,
                            labels=[5, 4, 3, 2, 1]).astype(int)
    tr["f_score"] = [f_score_by_threshold(v) for v in tr["frequency"]]
    tr["m_score"] = pd.qcut(tr["monetary"].rank(method="first"), 5,
                            labels=[1, 2, 3, 4, 5]).astype(int)
    tr["rfm_total"] = tr["r_score"] + tr["f_score"] + tr["m_score"]
    tr["rfm_segment"] = [rule8(r, f, m) for r, f, m in
                         zip(tr["r_score"], tr["f_score"], tr["m_score"])]

    # 验证期表现
    va = (valid.groupby("customer_unique_id")
          .agg(valid_orders=("ts", "size"), valid_gmv=("gmv", "sum")).reset_index())

    # 策略定义：所有策略统一取 20% 人数，保证可比
    n = len(tr)
    k = int(n * 0.2)
    rs = np.random.RandomState(SEED)

    strategies = {
        "A_RFM综合分Top20%": set(tr.nlargest(k, "rfm_total")["customer_unique_id"]),
        "B_消费额Top20%": set(tr.nlargest(k, "monetary")["customer_unique_id"]),
        "C_购买频次Top20%": set(tr.nlargest(k, "frequency")["customer_unique_id"]),
        "D_随机20%": set(rs.choice(tr["customer_unique_id"], size=k, replace=False)),
        "E_全量用户(基线)": set(tr["customer_unique_id"]),
    }

    rows = []
    total_valid_gmv = float(va["valid_gmv"].sum())
    valid_buyers = set(va["customer_unique_id"])
    for name, users in strategies.items():
        cnt = len(users)
        hit = len(users & valid_buyers)
        sub = va[va["customer_unique_id"].isin(users)]
        vgmv = float(sub["valid_gmv"].sum())
        rows.append({
            "strategy": name,
            "target_users": cnt,
            "target_pct_of_all": round(cnt / n * 100, 2),
            "valid_repurchase_users": hit,
            "hit_rate_pct": round(hit / cnt * 100, 2) if cnt else 0.0,
            "valid_gmv": round(vgmv, 2),
            "valid_arpu": round(vgmv / cnt, 2) if cnt else 0.0,
            "valid_gmv_share_pct": round(vgmv / total_valid_gmv * 100, 2)
            if total_valid_gmv else 0.0,
        })
    exp = pd.DataFrame(rows)

    rand_hit = float(exp.loc[exp["strategy"] == "D_随机20%", "hit_rate_pct"].iloc[0])
    rand_arpu = float(exp.loc[exp["strategy"] == "D_随机20%", "valid_arpu"].iloc[0])
    exp["lift_hit_vs_random"] = (exp["hit_rate_pct"] / rand_hit).round(3) if rand_hit else np.nan
    exp["lift_arpu_vs_random"] = (exp["valid_arpu"] / rand_arpu).round(3) if rand_arpu else np.nan
    exp.insert(0, "rank", np.arange(1, len(exp) + 1))
    exp["train_cutoff"] = str(cut.date())
    exp["valid_window"] = f"{valid['ts'].min().date()} ~ {valid['ts'].max().date()}"
    exp["note"] = [
        "RFM 综合分 = r_score+f_score+m_score，取 Top20%",
        "训练期累计消费额 Top20%",
        "训练期订单数 Top20%",
        "随机抽样 20%（固定随机种子 42）",
        "训练期全部用户，作为对照",
    ]
    exp.to_csv(OUT / "algo1_offline_experiment_part1.csv", index=False,
               encoding="utf-8-sig")

    log(f"  {'策略':<22}{'人数':>8}{'验证期复购':>9}{'命中率':>8}{'vs随机':>8}"
        f"{'验证期ARPU':>11}{'upside':>8}")
    for _, r in exp.iterrows():
        log(f"  {r['strategy']:<22}{int(r['target_users']):>8,}"
            f"{int(r['valid_repurchase_users']):>9,}"
            f"{r['hit_rate_pct']:>7.2f}%{r['lift_hit_vs_random']:>7.2f}x"
            f"{r['valid_arpu']:>10.2f}{r['lift_arpu_vs_random']:>7.2f}x")
    log(f"  -> algo1_offline_experiment_part1.csv  {len(exp)} 行")

    log(f"\n  【数据特性说明】训练期 {n:,} 用户中，仅 "
        f"{len(set(tr['customer_unique_id']) & valid_buyers):,} 人"
        f"（{len(set(tr['customer_unique_id']) & valid_buyers)/n*100:.2f}%）"
        f"在验证期再次购买；验证期买家中 "
        f"{len(valid_buyers - set(tr['customer_unique_id'])):,} 人是新用户。"
        f"因此本实验区分度天然有限，属数据集特性。")

    return exp


# ============================================================
# 算法1 - 6. 最终统计结果
# ============================================================


# ---------------------------------------------------------------
# 【算法1-6】最终统计结果
#
#   输入: 前面各步的结果
#   输出: 算法1/algo1_summary_stats.csv（22 项）
#   用途: 汇报与答辩时直接引用
# ---------------------------------------------------------------
def build_algo1_summary(rfm, funnel, rep, cat, exp, km_info):
    rows = [
        ("数据集", "总用户数", f"{rep['n_users']:,}", "fact_rfm 去重"),
        ("数据集", "总订单数", f"{rep['n_orders']:,}", "fact_order_master"),
        ("数据集", "覆盖品类数", f"{len(cat)}", "英文品类名去重"),
        ("数据集", "总 GMV", f"{rep['gmv']:,.2f}", "gmv 求和"),
        ("数据集", "客单价", f"{rep['aov']:,.2f}", "GMV / 订单数"),
        ("RFM分群", "K-Means 簇数", "4", "任务要求"),
        ("RFM分群", "K-Means 轮廓系数", f"{km_info['silhouette']:.4f}", "抽样 5000 点"),
        ("RFM分群", "K-Means inertia", f"{km_info['inertia']:,.1f}", "簇内平方和"),
        ("RFM分群", "规则分群类别数", "8", "R/F/M 五分位 + 规则表"),
        ("RFM分群", "高价值客户占比",
         f"{rfm['rfm_segment_kmeans4'].eq('高价值客户').mean()*100:.2f}%", "K-Means 4 类"),
        ("转化", "下单→已送达 转化率",
         f"{funnel.loc[funnel['step_name']=='已送达','rate_vs_total_pct'].iloc[0]:.2f}%", "漏斗"),
        ("转化", "下单→支付获批 转化率",
         f"{funnel.loc[funnel['step_name']=='支付获批','rate_vs_total_pct'].iloc[0]:.2f}%", "漏斗"),
        ("复购", "复购用户数", f"{rep['rep_users']:,}", "frequency > 1"),
        ("复购", "复购用户占比", f"{rep['rep_rate']:.2f}%", "复购用户 / 总用户"),
        ("复购", "复购用户人均消费",
         f"{rfm.loc[rfm['frequency']>1,'monetary'].mean():,.2f}", ""),
        ("复购", "单次用户人均消费",
         f"{rfm.loc[rfm['frequency']==1,'monetary'].mean():,.2f}", ""),
        ("离线实验", "验证期窗口", exp["valid_window"].iloc[0], "时间切分"),
        ("离线实验", "RFM综合分策略命中率",
         f"{exp.loc[exp['strategy'].str.startswith('A_'),'hit_rate_pct'].iloc[0]:.2f}%",
         "取 Top20% 用户"),
        ("离线实验", "随机策略命中率",
         f"{exp.loc[exp['strategy'].str.startswith('D_'),'hit_rate_pct'].iloc[0]:.2f}%", ""),
        ("离线实验", "RFM策略命中率相对随机",
         f"{exp.loc[exp['strategy'].str.startswith('A_'),'lift_hit_vs_random'].iloc[0]:.2f}x", ""),
        ("离线实验", "RFM策略ARPU相对随机",
         f"{exp.loc[exp['strategy'].str.startswith('A_'),'lift_arpu_vs_random'].iloc[0]:.2f}x", ""),
        ("数据修正", "原五分位误标高F的用户数", f"{km_info['f_wrong_hi']:,}",
         "占原'高F'人群 94.9%，已改为业务阈值"),
    ]
    df = pd.DataFrame(rows, columns=["类别", "统计项", "数值", "口径说明"])
    df.to_csv(OUT / "algo1_summary_stats.csv", index=False, encoding="utf-8-sig")
    log()
    log("=" * 72)
    log("算法1-6  最终统计结果")
    log("=" * 72)
    for _, r in df.iterrows():
        log(f"  [{r['类别']}] {r['统计项']:<24} {r['数值']}")
    log(f"  -> algo1_summary_stats.csv  {len(df)} 行")
    return df


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    print("=" * 74)
    print("算法1 模型：数据预处理 + RFM 用户分群")
    print("=" * 74)
    print(f"  数据目录: {CLEAN}")
    print(f"  输出目录: {OUT}")
    print()

    rfm, km_info = build_rfm_clusters()
    om, funnel = build_funnel()
    rep = build_repurchase(om, rfm)
    cat = build_category_repurchase()
    exp = build_offline_experiment(om)
    build_algo1_summary(rfm, funnel, rep, cat, exp, km_info)

    print()
    print("=" * 74)
    print("完成。输出文件:")
    print("=" * 74)
    for f in sorted(OUT.glob("algo1_*.csv")):
        print(f"  {f.name:<40} {f.stat().st_size / 1024:>9,.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

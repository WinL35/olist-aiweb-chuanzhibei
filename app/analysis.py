# -*- coding: utf-8 -*-
"""分析 API: RFM 分群 / 转化与复购 / 销量预测

数据来源变更（本次改造）：
  - RFM 分群、RFM 散点 → 改为读 olist_algo_db.algo1_rfm_user_tags（算法1 交付，8 类人群）
  - 销量预测           → 改为读 olist_algo_db.algo2_forecast_result（算法2 交付）
  - 转化漏斗 / 复购     → 仍读 olist_db（业务数据，未变）

返回结构保持与原接口一致，前端无需改动。
"""
from fastapi import APIRouter, Query

import config
from app.db import query, query_one

router = APIRouter(prefix="/api", tags=["analysis"])

ALGO = config.ALGO_DB
BIZ = config.DB_CONFIG["database"]

# 算法2 交付物里每个品类固定 6 周留出验证
HOLDOUT_WEEKS = 6


def _f(v):
    return None if v is None else float(v)


# ====================== RFM 用户分群（算法1） ======================
@router.get("/rfm/segments", summary="RFM 分群汇总（规则 8 类 / K-Means 4 类）")
def rfm_segments(scheme: str = Query("rule8", pattern="^(rule8|kmeans4)$")):
    """各分群的人数、占比、平均 R/F/M、总贡献金额。

    scheme=rule8   ：业务规则 8 分类（默认，按 R/F/M 五分位打分落档）
    scheme=kmeans4 ：K-Means 聚类 4 类（题目要求的"聚类算法划分用户群体"）

    数据源：olist_algo_db.algo1_rfm_user_tags（算法1 交付，两套标签同时存在）
    """
    col = "rfm_segment_rule8" if scheme == "rule8" else "rfm_segment_kmeans4"
    rows = query(f"""
        SELECT {col} AS segment, COUNT(*) AS cnt,
               AVG(recency) AS avg_r, AVG(frequency) AS avg_f, AVG(monetary) AS avg_m,
               SUM(monetary) AS total_m
        FROM {ALGO}.algo1_rfm_user_tags
        WHERE {col} IS NOT NULL
        GROUP BY {col} ORDER BY total_m DESC
    """)
    total = sum(int(r["cnt"]) for r in rows) or 1
    return {"source": "algo1_rfm_user_tags", "scheme": scheme, "total_users": total,
            "data": [{"segment": r["segment"], "cnt": int(r["cnt"]),
                      "pct": round(int(r["cnt"]) / total * 100, 2),
                      "avg_recency": _f(r["avg_r"]), "avg_frequency": _f(r["avg_f"]),
                      "avg_monetary": _f(r["avg_m"]),
                      "total_monetary": _f(r["total_m"])} for r in rows]}


@router.get("/rfm/scatter", summary="RFM 散点采样（供散点图）")
def rfm_scatter(limit: int = Query(2000, le=10000),
                scheme: str = Query("rule8", pattern="^(rule8|kmeans4)$")):
    """RFM 散点(随机采样) 供 3D/2D 散点图。"""
    col = "rfm_segment_rule8" if scheme == "rule8" else "rfm_segment_kmeans4"
    rows = query(f"""
        SELECT recency, frequency, monetary, {col} AS segment, rfm_score
        FROM {ALGO}.algo1_rfm_user_tags
        WHERE {col} IS NOT NULL
        ORDER BY RAND() LIMIT %s
    """, (limit,))
    return {"scheme": scheme,
            "data": [{"recency": int(r["recency"]), "frequency": int(r["frequency"]),
                      "monetary": _f(r["monetary"]),
                      "segment": r["segment"],
                      "rfm_score": r.get("rfm_score")} for r in rows]}


# ====================== 转化与复购分析（业务数据） ======================
@router.get("/conversion/funnel", summary="订单转化漏斗")
def conversion_funnel():
    """订单转化漏斗: 下单->已批准->已发货->已送达->已评价。

    ⚠️ 口径（与算法1 交付的 algo1_conversion_funnel.csv 完全一致）：
      1. 每一级都用【累积 AND 条件】，保证漏斗严格单调递减。
         旧版各级独立计数，出现过「有 carrier 日期但未批准」的 14 单
         导致 API(97,658) 与算法 CSV(97,644) 对不上。
      2. 「已评价」用 review_creation_date 判定，不能用 review_score ——
         宽表里 review_score 几乎 100% 非空，会出现 已评价 > 已送达 的倒挂。
    """
    s = query_one("""
        SELECT COUNT(*) AS placed,
               SUM(order_approved_at IS NOT NULL) AS approved,
               SUM(order_approved_at IS NOT NULL
                   AND order_delivered_carrier_date IS NOT NULL) AS shipped,
               SUM(order_approved_at IS NOT NULL
                   AND order_delivered_carrier_date IS NOT NULL
                   AND order_delivered_customer_date IS NOT NULL) AS delivered,
               SUM(order_approved_at IS NOT NULL
                   AND order_delivered_carrier_date IS NOT NULL
                   AND order_delivered_customer_date IS NOT NULL
                   AND review_creation_date IS NOT NULL) AS reviewed
        FROM fact_order_master
    """)
    stages = [
        {"stage": "下单", "cnt": int(s["placed"])},
        {"stage": "已批准", "cnt": int(s["approved"] or 0)},
        {"stage": "已发货", "cnt": int(s["shipped"] or 0)},
        {"stage": "已送达", "cnt": int(s["delivered"] or 0)},
        {"stage": "已评价", "cnt": int(s["reviewed"] or 0)},
    ]
    base = stages[0]["cnt"] or 1
    for st in stages:
        st["rate"] = round(st["cnt"] / base * 100, 2)
        st["step_rate"] = 0
    for i in range(1, len(stages)):
        prev = stages[i - 1]["cnt"] or 1
        stages[i]["step_rate"] = round(stages[i]["cnt"] / prev * 100, 2)
    return {"data": stages}


@router.get("/conversion/repurchase", summary="复购情况")
def repurchase():
    """复购情况: 单次 vs 复购客户数、金额贡献。"""
    rows = query("""
        SELECT CASE WHEN frequency = 1 THEN '单次购买' ELSE '复购' END AS type,
               COUNT(*) AS customers, SUM(monetary) AS monetary, AVG(frequency) AS avg_freq
        FROM fact_rfm GROUP BY type
    """)
    total_c = sum(int(r["customers"]) for r in rows) or 1
    total_m = sum(_f(r["monetary"]) or 0 for r in rows) or 1
    return {"data": [{"type": r["type"], "customers": int(r["customers"]),
                      "customer_pct": round(int(r["customers"]) / total_c * 100, 2),
                      "monetary": _f(r["monetary"]),
                      "monetary_pct": round((_f(r["monetary"]) or 0) / total_m * 100, 2),
                      "avg_frequency": _f(r["avg_freq"])} for r in rows]}


# ====================== 销量预测（算法2） ======================
@router.get("/prediction/categories", summary="可预测品类列表")
def pred_categories():
    """可预测品类列表（读取算法2 预测结果表，按该品类 GMV 降序）。

    返回 category / gmv 供前端下拉框展示，另附预测元信息。
    """
    rows = query(f"""
        SELECT f.category,
               COALESCE(c.gmv, 0) AS gmv,
               COUNT(*) AS forecast_weeks,
               ROUND(AVG(f.mape_model_pct), 2) AS avg_mape,
               MAX(f.model) AS model
        FROM {ALGO}.algo2_forecast_result f
        LEFT JOIN {BIZ}.dim_category_summary c
               ON f.category = c.product_category_name_english
        GROUP BY f.category, c.gmv
        ORDER BY gmv DESC, f.category
    """)
    return {"data": [{"category": r["category"], "gmv": _f(r["gmv"]) or 0,
                      "forecast_weeks": int(r["forecast_weeks"]),
                      "avg_mape": _f(r["avg_mape"]), "model": r["model"]}
                     for r in rows]}


@router.get("/prediction/sales", summary="品类周销量预测（含区间与基线对比）")
def pred_sales(category: str = Query(..., description="品类英文名，如 health_beauty"),
               weeks: int = Query(8, ge=1, le=26)):
    """指定品类未来周销量预测。

    - future ：来自算法2 结果表 algo2_forecast_result（含 95% 区间、MA4 基线）
    - history：从 fact_sales 按周实时聚合，供前端画历史曲线
    - metrics：模型在留出窗口上的 MAPE 与相对基线提升
    """
    fc = query(f"""
        SELECT forecast_week, forecast_date, predicted_qty, lower_95, upper_95,
               baseline_ma4_qty, model, mape_model_pct, mape_baseline_pct,
               improvement_pct, history_weeks
        FROM {ALGO}.algo2_forecast_result
        WHERE category = %s
        ORDER BY forecast_week
    """, (category,))
    if not fc:
        return {"error": f"该品类暂无预测结果: {category}", "category": category}

    hist = query("""
        SELECT year_week AS week, COUNT(*) AS qty
        FROM fact_sales
        WHERE product_category_name_english = %s AND year_week IS NOT NULL
        GROUP BY year_week ORDER BY year_week
    """, (category,))

    m = fc[0]
    return {
        "source": "algo2_forecast_result",
        "category": category,
        "n_weeks": int(m["history_weeks"] or len(hist)),
        "history": [{"week": r["week"], "qty": int(r["qty"])} for r in hist],
        "future": [{"week": r["forecast_week"],
                    "date": str(r["forecast_date"]),
                    "forecast": _f(r["predicted_qty"]),
                    "lower": _f(r["lower_95"]),
                    "upper": _f(r["upper_95"]),
                    "baseline": _f(r["baseline_ma4_qty"])} for r in fc[:weeks]],
        "metrics": {
            "model": m["model"],
            "baseline_model": "移动平均(最近4周)",
            "mape_model": _f(m["mape_model_pct"]),
            "mape_baseline": _f(m["mape_baseline_pct"]),
            "improvement_pct": _f(m["improvement_pct"]),
            "holdout_weeks": HOLDOUT_WEEKS,
        },
    }


# ====================== 选品建议（品类级，业务数据口径） ======================
@router.get("/recommendation/products", summary="选品推荐 Top10 品类")
def recommendation():
    """品类级选品建议：近90天 vs 前90天，综合分 = 规模×0.5 + 增长×0.5。

    说明：本接口保持项目原有「品类级」口径（前端已在用）。
    算法2 的「商品级」选品结果请使用 /api/selection/products。
    """
    meta = query_one("SELECT MAX(order_purchase_timestamp) AS maxd FROM fact_sales")
    import pandas as pd
    maxd = pd.Timestamp(meta["maxd"])
    r_start = maxd - pd.Timedelta(days=90)
    p_start = r_start - pd.Timedelta(days=90)
    rows = query("""
        SELECT product_category_name_english AS category,
               SUM(CASE WHEN order_purchase_timestamp >= %s THEN price ELSE 0 END) AS recent_gmv,
               SUM(CASE WHEN order_purchase_timestamp < %s AND order_purchase_timestamp >= %s
                        THEN price ELSE 0 END) AS prev_gmv,
               SUM(CASE WHEN order_purchase_timestamp >= %s THEN 1 ELSE 0 END) AS recent_qty,
               AVG(price) AS avg_price
        FROM fact_sales
        WHERE product_category_name_english IS NOT NULL
        GROUP BY product_category_name_english
    """, (r_start, r_start, p_start, r_start))
    items = []
    for r in rows:
        rg = _f(r["recent_gmv"]) or 0
        pg = _f(r["prev_gmv"]) or 0
        growth = (rg - pg) / pg if pg > 0 else (1.0 if rg > 0 else 0.0)
        items.append({"category": r["category"], "recent_gmv": rg, "prev_gmv": pg,
                      "recent_qty": int(r["recent_qty"]), "avg_price": _f(r["avg_price"]),
                      "growth_rate": growth})
    max_gmv = max((it["recent_gmv"] for it in items), default=1) or 1
    growths = [it["growth_rate"] for it in items]
    gmax = max(growths) if growths else 1
    gmin = min(growths) if growths else 0
    for it in items:
        norm_gmv = it["recent_gmv"] / max_gmv
        norm_g = (it["growth_rate"] - gmin) / (gmax - gmin) if gmax > gmin else 0.5
        it["score"] = round(norm_gmv * 0.5 + norm_g * 0.5, 4)
    items.sort(key=lambda x: x["score"], reverse=True)
    top = items[:10]
    return {"window": {"recent": str(r_start.date()), "end": str(maxd.date())},
            "data": [{"rank": i + 1, **it} for i, it in enumerate(top)]}


# ====================== 离线策略对照评估（业务数据口径） ======================
@router.get("/recommendation/strategy_compare", summary="离线策略对照（热门 vs 增长）")
def strategy_compare():
    """对比两种选品策略在验证期的命中率（Top-10 命中前20%）。

    策略A=热门(GMV)  策略B=增长率。
    说明：算法2 的「模型效果对比」（4 个预测模型 × 74 品类）请用 /api/experiment/compare。
    """
    import pandas as pd
    meta = query_one("SELECT MAX(order_purchase_timestamp) AS maxd FROM fact_sales")
    maxd = pd.Timestamp(meta["maxd"])
    val_start = maxd - pd.Timedelta(days=90)              # 验证期起点
    recent_start = val_start - pd.Timedelta(days=90)      # 训练期「近90天」窗口起点
    prev_start = recent_start - pd.Timedelta(days=90)     # 训练期「前90天」窗口起点

    # ⚠️ 三个窗口必须互不重叠，否则 growth 恒为 0：
    #   train_gmv : 验证期之前的全部数据（策略A 热门排序用）
    #   t_recent  : [recent_start, val_start)    训练期最后 90 天
    #   t_prev    : [prev_start,   recent_start) 再往前 90 天
    rows = query("""
        SELECT product_category_name_english AS category,
          SUM(CASE WHEN order_purchase_timestamp < %s THEN price ELSE 0 END) AS train_gmv,
          SUM(CASE WHEN order_purchase_timestamp < %s AND order_purchase_timestamp >= %s
                   THEN price ELSE 0 END) AS t_recent,
          SUM(CASE WHEN order_purchase_timestamp < %s AND order_purchase_timestamp >= %s
                   THEN price ELSE 0 END) AS t_prev,
          SUM(CASE WHEN order_purchase_timestamp >= %s THEN 1 ELSE 0 END) AS val_qty
        FROM fact_sales
        WHERE product_category_name_english IS NOT NULL
        GROUP BY product_category_name_english
    """, (val_start, val_start, recent_start, recent_start, prev_start, val_start))

    cats = []
    for r in rows:
        tg = _f(r["train_gmv"]) or 0
        tr = _f(r["t_recent"]) or 0
        tp = _f(r["t_prev"]) or 0
        growth = (tr - tp) / tp if tp > 0 else (1.0 if tr > 0 else 0.0)
        cats.append({"category": r["category"], "train_gmv": tg, "growth": growth,
                     "val_qty": int(r["val_qty"] or 0)})
    if not cats:
        return {"error": "数据不足"}

    sorted_val = sorted(cats, key=lambda x: x["val_qty"], reverse=True)
    n_top20 = max(1, int(len(sorted_val) * 0.2))
    top20 = {c["category"] for c in sorted_val[:n_top20]}

    stratA = sorted(cats, key=lambda x: x["train_gmv"], reverse=True)[:10]
    stratB = sorted(cats, key=lambda x: x["growth"], reverse=True)[:10]
    hitA = sum(1 for c in stratA if c["category"] in top20)
    hitB = sum(1 for c in stratB if c["category"] in top20)
    return {
        "validation_window": f"最后90天 (≥{val_start.date()})",
        "top20_count": n_top20,
        "strategy_A": {"name": "热门策略(按GMV)", "recommended": stratA,
                       "hit_rate": round(hitA / len(stratA) * 100, 2)},
        "strategy_B": {"name": "增长策略(按增长率)", "recommended": stratB,
                       "hit_rate": round(hitB / len(stratB) * 100, 2)},
        "conclusion": ("增长策略命中率更高" if hitB > hitA else
                       "热门策略命中率更高" if hitA > hitB else "两策略命中率相同"),
    }

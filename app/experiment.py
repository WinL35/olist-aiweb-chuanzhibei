# -*- coding: utf-8 -*-
"""离线实验对比 API（算法2 交付物）

数据源：olist_algo_db.algo2_offline_experiment（74 品类 × 4 模型 = 296 行）

每个品类固定 4 个模型：
  1. 主模型(Holt-Winters/阻尼Holt/阻尼线性)
  2. 阻尼Holt趋势
  3. 季节朴素(去年同期)
  4. 基线-移动平均MA4
（Holt-Winters(季节,52) 仅在品类历史 ≥104 周时才会出现；
  当前 Olist 数据所有品类历史均不足 104 周，故实际只有上述 4 个。）
"""
from typing import Optional

from fastapi import APIRouter, Query

import config
from app.db import query, query_one

router = APIRouter(prefix="/api/experiment", tags=["experiment"])

ALGO = config.ALGO_DB


def _f(v):
    return None if v is None else float(v)


@router.get("/compare", summary="各模型整体效果对比（按模型汇总）")
def experiment_compare():
    """按模型汇总 MAPE / WAPE / MAE / RMSE，并按 MAPE 升序排列。

    ⚠️ 汇报口径提醒：
      主模型平均 MAPE 只比基线领先约 0.1%，WAPE 甚至略输基线。
      真实亮点是【MAPE 中位数】明显优于基线。要看中位数请用 /experiment/detail。
    """
    rows = query(f"""
        SELECT model,
               COUNT(DISTINCT category) AS category_cnt,
               ROUND(AVG(mape_pct), 2) AS avg_mape,
               ROUND(AVG(wape_pct), 2) AS avg_wape,
               ROUND(AVG(mae), 3) AS avg_mae,
               ROUND(AVG(rmse), 3) AS avg_rmse,
               ROUND(AVG(mape_vs_baseline_improve_pct), 2) AS avg_improve_pct,
               MAX(is_baseline) AS is_baseline
        FROM {ALGO}.algo2_offline_experiment
        GROUP BY model
        ORDER BY avg_mape
    """)
    return {"data": [{"model": r["model"],
                      "is_baseline": int(r["is_baseline"] or 0),
                      "category_cnt": int(r["category_cnt"]),
                      "avg_mape": _f(r["avg_mape"]),
                      "avg_wape": _f(r["avg_wape"]),
                      "avg_mae": _f(r["avg_mae"]),
                      "avg_rmse": _f(r["avg_rmse"]),
                      "avg_mape_improve_pct": _f(r["avg_improve_pct"])} for r in rows]}


@router.get("/detail", summary="逐品类的模型效果对比")
def experiment_detail(
    category: Optional[str] = Query(None, description="只看某个品类"),
    holdout_weeks: int = Query(6, ge=1, le=26, description="留出验证周数"),
    limit: int = Query(500, ge=1, le=1000),
):
    """逐品类的 4 个模型指标，供前端画对比柱状图。

    每行含 mape_pct / mape_stable_pct / wape_pct / mae / rmse。
    """
    where, args = ["holdout_weeks = %s"], [holdout_weeks]
    if category:
        where.append("category = %s")
        args.append(category)
    rows = query(f"""
        SELECT category, model, is_baseline, holdout_weeks,
               mape_pct, mape_stable_pct, wape_pct, mae, rmse,
               mape_vs_baseline_improve_pct, wape_vs_baseline_improve_pct,
               history_weeks
        FROM {ALGO}.algo2_offline_experiment
        WHERE {' AND '.join(where)}
        ORDER BY category, mape_pct
        LIMIT %s
    """, (*args, limit))
    return {"count": len(rows),
            "data": [{"category": r["category"], "model": r["model"],
                      "is_baseline": int(r["is_baseline"] or 0),
                      "holdout_weeks": int(r["holdout_weeks"]),
                      "mape_pct": _f(r["mape_pct"]),
                      "mape_stable_pct": _f(r["mape_stable_pct"]),
                      "wape_pct": _f(r["wape_pct"]),
                      "mae": _f(r["mae"]), "rmse": _f(r["rmse"]),
                      "mape_vs_baseline_improve_pct": _f(r["mape_vs_baseline_improve_pct"]),
                      "wape_vs_baseline_improve_pct": _f(r["wape_vs_baseline_improve_pct"]),
                      "history_weeks": r["history_weeks"]} for r in rows]}


@router.get("/median", summary="主模型 vs 基线：均值与中位数对比（汇报用）")
def experiment_median():
    """主模型与基线的 MAPE/WAPE 均值、中位数对比，以及"主模型更优的品类占比"。

    这是汇报时最该引用的口径 —— 平均 MAPE 会被少数低基数品类拉高，中位数更稳健。
    """
    rows = query(f"""
        SELECT model, COUNT(*) AS n,
               ROUND(AVG(mape_pct), 2) AS avg_mape,
               ROUND(AVG(wape_pct), 2) AS avg_wape
        FROM {ALGO}.algo2_offline_experiment
        WHERE model LIKE '主模型%' OR is_baseline = 1
        GROUP BY model
    """)

    def _median(where: str):
        """MySQL 8 没有 MEDIAN 函数，用 ROW_NUMBER 取中位"""
        r = query_one(f"""
            SELECT ROUND(AVG(m), 2) AS med FROM (
                SELECT mape_pct AS m,
                       ROW_NUMBER() OVER (ORDER BY mape_pct) AS rn,
                       COUNT(*) OVER () AS cnt
                FROM {ALGO}.algo2_offline_experiment
                WHERE ({where}) AND mape_pct IS NOT NULL
            ) t WHERE rn IN (FLOOR((cnt+1)/2), CEIL((cnt+1)/2))
        """)
        return _f(r["med"]) if r else None

    main_med = _median("model LIKE '主模型%'")
    base_med = _median("is_baseline = 1")

    better = query_one(f"""
        SELECT COUNT(*) AS total,
               SUM(main_mape < base_mape) AS better
        FROM (
            SELECT category,
                   MAX(CASE WHEN model LIKE '主模型%' THEN mape_pct END) AS main_mape,
                   MAX(CASE WHEN is_baseline = 1 THEN mape_pct END) AS base_mape
            FROM {ALGO}.algo2_offline_experiment
            GROUP BY category
        ) t
        WHERE main_mape IS NOT NULL AND base_mape IS NOT NULL
    """)
    total = int(better["total"] or 0) if better else 0
    n_better = int(better["better"] or 0) if better else 0

    return {
        "by_model": [{"model": r["model"], "n": int(r["n"]),
                      "avg_mape": _f(r["avg_mape"]), "avg_wape": _f(r["avg_wape"])}
                     for r in rows],
        "median": {"main_model_mape": main_med, "baseline_mape": base_med},
        "main_model_better_categories": {
            "better": n_better, "total": total,
            "pct": round(n_better / total * 100, 2) if total else None},
        "note": "平均 MAPE 受低基数品类放大；汇报建议引用中位数与 WAPE",
    }


@router.get("/summary-stats", summary="算法2 最终统计结果（31 项）")
def experiment_summary_stats(group: Optional[str] = Query(None,
                                                         description="数据集/预测/选品/定价")):
    """读取 algo2_summary_stats（算法2 交付的最终统计表）。"""
    where, args = "1=1", []
    if group:
        where = "stat_group = %s"
        args.append(group)
    rows = query(f"""
        SELECT stat_group, stat_name, value_text, value_num, description
        FROM {ALGO}.algo2_summary_stats
        WHERE {where}
        ORDER BY FIELD(stat_group, '数据集', '预测', '选品', '定价'), stat_name
    """, tuple(args))
    return {"count": len(rows),
            "data": [{"group": r["stat_group"], "name": r["stat_name"],
                      "value_text": r["value_text"],
                      "value_num": _f(r["value_num"]),
                      "description": r["description"]} for r in rows]}

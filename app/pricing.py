# -*- coding: utf-8 -*-
"""定价建议 API（算法2 交付物）

数据源：olist_algo_db.algo2_pricing_result / algo2_pricing_skipped

⚠️ 重要口径：
  - suggested_price / elasticity / price_change_pct 等字段【允许为 NULL】
  - NULL 的含义是「样本不足，算法不给建议」，不是 0
  - 前端必须区分「有建议」与「无建议」，不要用 0 或空串代替
  - 50 个商品中只有 31 个有建议价，其中高置信（商品级弹性）7 个
"""
from typing import Optional

from fastapi import APIRouter, Query

import config
from app.db import query, query_one

router = APIRouter(prefix="/api/pricing", tags=["pricing"])

ALGO = config.ALGO_DB


def _f(v):
    return None if v is None else float(v)


def _row(r):
    """把一行的 Decimal/None 规整，并把 NULL 明确标为 null(JSON)"""
    return {
        "product_id": r["product_id"],
        "category": r["category"],
        "selection_type": r["selection_type"],
        "current_price": _f(r["current_price"]),
        # 下面三个为 NULL 表示样本不足、不给建议价
        "suggested_price": _f(r["suggested_price"]),
        "price_change_pct": _f(r["price_change_pct"]),
        "elasticity": _f(r["elasticity"]),
        "has_suggestion": r["suggested_price"] is not None,
        "price_lower_95": _f(r["price_lower_95"]),
        "price_upper_95": _f(r["price_upper_95"]),
        "elasticity_source": r["elasticity_source"],
        "elasticity_r2": _f(r["elasticity_r2"]),
        "confidence": r["confidence"],
        "expected_qty_change_pct": _f(r["expected_qty_change_pct"]),
        "expected_revenue_change_pct": _f(r["expected_revenue_change_pct"]),
        "pricing_rule": r["pricing_rule"],
        "months_observed": r.get("months_observed"),
        "price_cv_pct": _f(r.get("price_cv_pct")),
        "note": r["note"],
    }


@router.get("/summary", summary="定价建议总览（数量口径）")
def pricing_summary():
    """定价结果的总体统计：有建议价/无建议价数量、置信度分布、提降价数量。"""
    r = query_one(f"""
        SELECT COUNT(*) AS total,
               SUM(suggested_price IS NOT NULL) AS has_price,
               SUM(suggested_price IS NULL) AS no_price,
               SUM(confidence = '高') AS high_conf,
               SUM(confidence = '中') AS mid_conf,
               SUM(confidence = '低') AS low_conf,
               SUM(price_change_pct > 0) AS raise_cnt,
               SUM(price_change_pct < 0) AS cut_cnt,
               ROUND(AVG(CASE WHEN expected_revenue_change_pct IS NOT NULL
                              THEN expected_revenue_change_pct END), 2) AS avg_revenue_gain
        FROM {ALGO}.algo2_pricing_result
    """)
    return {
        "total": int(r["total"]),
        "has_suggestion": int(r["has_price"] or 0),
        "no_suggestion": int(r["no_price"] or 0),
        "confidence": {"高": int(r["high_conf"] or 0),
                       "中": int(r["mid_conf"] or 0),
                       "低": int(r["low_conf"] or 0)},
        "raise_cnt": int(r["raise_cnt"] or 0),
        "cut_cnt": int(r["cut_cnt"] or 0),
        "avg_expected_revenue_change_pct": _f(r["avg_revenue_gain"]),
        "note": "只有 has_suggestion=true 的商品才有建议价；其余为样本不足",
    }


@router.get("/suggestions", summary="定价建议列表")
def pricing_suggestions(
    confidence: Optional[str] = Query(None, pattern="^(高|中|低)$",
                                      description="按置信度过滤：高/中/低"),
    has_suggestion: Optional[bool] = Query(None, description="true=只看有建议价的"),
    category: Optional[str] = Query(None, description="按品类过滤"),
    limit: int = Query(100, ge=1, le=200),
):
    """定价建议列表。默认按 置信度(高→低)、调价幅度绝对值 排序。

    - `has_suggestion=false` 的行，suggested_price 为 null（样本不足）
    """
    where, args = ["1=1"], []
    if confidence:
        where.append("confidence = %s")
        args.append(confidence)
    if has_suggestion is True:
        where.append("suggested_price IS NOT NULL")
    elif has_suggestion is False:
        where.append("suggested_price IS NULL")
    if category:
        where.append("category = %s")
        args.append(category)

    select_extra = "months_observed, price_cv_pct"
    rows = query(f"""
        SELECT product_id, category, selection_type,
               current_price, suggested_price, price_lower_95, price_upper_95,
               price_change_pct, elasticity, elasticity_source, elasticity_r2,
               confidence, expected_qty_change_pct, expected_revenue_change_pct,
               pricing_rule, note, {select_extra}
        FROM {ALGO}.algo2_pricing_result
        WHERE {' AND '.join(where)}
        ORDER BY FIELD(confidence, '高', '中', '低'),
                 ABS(COALESCE(price_change_pct, 0)) DESC
        LIMIT %s
    """, (*args, limit))
    return {"count": len(rows), "data": [_row(r) for r in rows]}


@router.get("/product/{product_id}", summary="单个商品的定价详情")
def pricing_product(product_id: str):
    """查单个商品的定价详情，并联合选品得分（跨表 LEFT JOIN）。"""
    r = query_one(f"""
        SELECT p.product_id, p.category, p.selection_type,
               p.current_price, p.suggested_price, p.price_lower_95, p.price_upper_95,
               p.price_change_pct, p.elasticity, p.elasticity_source, p.elasticity_r2,
               p.confidence, p.expected_qty_change_pct, p.expected_revenue_change_pct,
               p.pricing_rule, p.note, p.months_observed, p.price_cv_pct,
               s.score_total, s.growth_pct, s.recommendation, s.gmv_recent
        FROM {ALGO}.algo2_pricing_result p
        LEFT JOIN {ALGO}.algo2_selection_result s ON p.product_id = s.product_id
        WHERE p.product_id = %s
    """, (product_id,))
    if not r:
        return {"error": f"未找到该商品的定价结果: {product_id}"}
    out = _row(r)
    out.update({
        "score_total": _f(r["score_total"]),
        "growth_pct": _f(r["growth_pct"]),
        "recommendation": r["recommendation"],
        "gmv_recent": _f(r["gmv_recent"]),
    })
    return out


@router.get("/skipped", summary="样本不足、未给建议价的商品明细")
def pricing_skipped(limit: int = Query(50, ge=1, le=100)):
    """这 19 个商品因为月度观测太少或价格几乎不变，算法无法估计弹性，
    因此明确不给建议价（数据质量说明，便于汇报时解释）。"""
    rows = query(f"""
        SELECT product_id, category, months_observed, price_cv_pct, reason
        FROM {ALGO}.algo2_pricing_skipped
        ORDER BY months_observed DESC
        LIMIT %s
    """, (limit,))
    return {"count": len(rows),
            "data": [{"product_id": r["product_id"], "category": r["category"],
                      "months_observed": int(r["months_observed"] or 0),
                      "price_cv_pct": _f(r["price_cv_pct"]),
                      "reason": r["reason"]} for r in rows]}


@router.get("/by-category", summary="按品类的定价建议汇总")
def pricing_by_category():
    """按品类聚合：商品数、有建议价数、平均现价、平均建议幅度。"""
    rows = query(f"""
        SELECT category,
               COUNT(*) AS product_cnt,
               SUM(suggested_price IS NOT NULL) AS has_suggestion,
               ROUND(AVG(current_price), 2) AS avg_current_price,
               ROUND(AVG(price_change_pct), 2) AS avg_change_pct
        FROM {ALGO}.algo2_pricing_result
        GROUP BY category
        ORDER BY product_cnt DESC, category
    """)
    return {"data": [{"category": r["category"],
                      "product_cnt": int(r["product_cnt"]),
                      "has_suggestion": int(r["has_suggestion"] or 0),
                      "avg_current_price": _f(r["avg_current_price"]),
                      "avg_change_pct": _f(r["avg_change_pct"])} for r in rows]}

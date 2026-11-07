# -*- coding: utf-8 -*-
"""选品结果 API（算法2 交付物，商品级）

数据源：olist_algo_db.algo2_selection_result（50 行 = 增长榜 30 + 高销量分析池 20）

与 /api/recommendation/products 的区别：
  - /api/recommendation/products  → 品类级 Top10（项目原有口径，前端在用）
  - /api/selection/products       → 商品级榜单（算法2 真实交付物，product_id 粒度）

⚠️ 表里字段名是 `rank`，是 MySQL 保留字，SQL 中必须加反引号。
"""
from typing import Optional

from fastapi import APIRouter, Query

import config
from app.db import query, query_one

router = APIRouter(prefix="/api/selection", tags=["selection"])

ALGO = config.ALGO_DB


def _f(v):
    return None if v is None else float(v)


def _row(r):
    return {
        "rank": int(r["rank"]),
        "selection_type": r["selection_type"],
        "product_id": r["product_id"],
        "category": r["category"],
        "gmv_recent": _f(r["gmv_recent"]),
        "gmv_prior": _f(r["gmv_prior"]),
        "gmv_total": _f(r["gmv_total"]),
        "growth_pct": _f(r["growth_pct"]),
        "qty_recent": _f(r["qty_recent"]),
        "qty_prior": _f(r["qty_prior"]),
        "total_qty": r["total_qty"],
        "active_months": r["active_months"],
        "avg_price": _f(r["avg_price"]),
        "score_scale": _f(r["score_scale"]),
        "score_growth": _f(r["score_growth"]),
        "score_price": _f(r["score_price"]),
        "score_total": _f(r["score_total"]),
        "recommendation": r["recommendation"],
        "recent_window": r["recent_window"],
        "prior_window": r["prior_window"],
    }


@router.get("/summary", summary="选品结果总览")
def selection_summary():
    """两个榜单的数量、推荐等级分布、GMV 合计。"""
    rows = query(f"""
        SELECT selection_type,
               COUNT(*) AS cnt,
               SUM(recommendation = '强推') AS strong,
               SUM(recommendation = '推荐') AS recommend,
               SUM(recommendation = '备选') AS backup,
               ROUND(SUM(gmv_recent), 2) AS gmv_recent_sum,
               ROUND(AVG(score_total), 2) AS avg_score
        FROM {ALGO}.algo2_selection_result
        GROUP BY selection_type
    """)
    total = query_one(f"SELECT COUNT(*) AS n FROM {ALGO}.algo2_selection_result")
    return {
        "total": int(total["n"]) if total else 0,
        "by_type": [{"selection_type": r["selection_type"],
                     "cnt": int(r["cnt"]),
                     "strong": int(r["strong"] or 0),
                     "recommend": int(r["recommend"] or 0),
                     "backup": int(r["backup"] or 0),
                     "gmv_recent_sum": _f(r["gmv_recent_sum"]),
                     "avg_score": _f(r["avg_score"])} for r in rows],
    }


@router.get("/products", summary="商品级选品榜单")
def selection_products(
    selection_type: Optional[str] = Query(None, description="增长榜 / 高销量分析池"),
    recommendation: Optional[str] = Query(None, pattern="^(强推|推荐|备选)$"),
    category: Optional[str] = Query(None, description="按品类过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """返回算法2 的商品级选品榜单（按综合得分降序）。"""
    where, args = ["1=1"], []
    if selection_type:
        where.append("selection_type = %s")
        args.append(selection_type)
    if recommendation:
        where.append("recommendation = %s")
        args.append(recommendation)
    if category:
        where.append("category = %s")
        args.append(category)

    rows = query(f"""
        SELECT `rank`, selection_type, product_id, category,
               gmv_recent, gmv_prior, gmv_total, growth_pct,
               qty_recent, qty_prior, total_qty, active_months, avg_price,
               score_scale, score_growth, score_price, score_total,
               recommendation, recent_window, prior_window
        FROM {ALGO}.algo2_selection_result
        WHERE {' AND '.join(where)}
        ORDER BY selection_type, `rank`
        LIMIT %s
    """, (*args, limit))
    return {"count": len(rows), "data": [_row(r) for r in rows]}


@router.get("/top", summary="强推商品（可直接用于推荐位）")
def selection_top(limit: int = Query(10, ge=1, le=50)):
    """只返回 recommendation='强推' 的商品，按总分降序。"""
    rows = query(f"""
        SELECT `rank`, selection_type, product_id, category,
               gmv_recent, gmv_prior, gmv_total, growth_pct,
               qty_recent, qty_prior, total_qty, active_months, avg_price,
               score_scale, score_growth, score_price, score_total,
               recommendation, recent_window, prior_window
        FROM {ALGO}.algo2_selection_result
        WHERE recommendation = '强推'
        ORDER BY score_total DESC
        LIMIT %s
    """, (limit,))
    return {"count": len(rows), "data": [_row(r) for r in rows]}


@router.get("/by-category", summary="按品类汇总选品情况")
def selection_by_category():
    """把商品级榜单聚到品类级：商品数、强推数、近期GMV、平均得分。"""
    rows = query(f"""
        SELECT category,
               COUNT(*) AS product_cnt,
               SUM(recommendation = '强推') AS strong_cnt,
               ROUND(SUM(gmv_recent), 2) AS gmv_recent,
               ROUND(AVG(score_total), 2) AS avg_score,
               ROUND(AVG(growth_pct), 2) AS avg_growth_pct
        FROM {ALGO}.algo2_selection_result
        GROUP BY category
        ORDER BY gmv_recent DESC
    """)
    return {"data": [{"category": r["category"],
                      "product_cnt": int(r["product_cnt"]),
                      "strong_cnt": int(r["strong_cnt"] or 0),
                      "gmv_recent": _f(r["gmv_recent"]),
                      "avg_score": _f(r["avg_score"]),
                      "avg_growth_pct": _f(r["avg_growth_pct"])} for r in rows]}


@router.get("/product/{product_id}", summary="单个商品的选品详情（联合定价）")
def selection_product(product_id: str):
    """查单个商品的选品明细，并联合定价建议。"""
    r = query_one(f"""
        SELECT s.*, p.current_price, p.suggested_price, p.price_change_pct,
               p.elasticity, p.confidence
        FROM {ALGO}.algo2_selection_result s
        LEFT JOIN {ALGO}.algo2_pricing_result p ON s.product_id = p.product_id
        WHERE s.product_id = %s
    """, (product_id,))
    if not r:
        return {"error": f"未找到该商品的选品结果: {product_id}"}
    out = _row(r)
    out.update({
        "current_price": _f(r["current_price"]),
        "suggested_price": _f(r["suggested_price"]),
        "price_change_pct": _f(r["price_change_pct"]),
        "elasticity": _f(r["elasticity"]),
        "confidence": r["confidence"],
    })
    return out

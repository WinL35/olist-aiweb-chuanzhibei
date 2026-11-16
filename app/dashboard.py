# -*- coding: utf-8 -*-
"""经营与行为看板 API"""
from fastapi import APIRouter, Query

from app.db import query, query_one

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _f(v):
    """数值规整: Decimal/None -> float。"""
    return None if v is None else float(v)


@router.get("/summary")
def summary():
    """核心指标: GMV、客单价、订单数、客户数、送达率、复购率、平均评分。"""
    s = query_one("""
        SELECT COUNT(*) AS order_cnt,
               COUNT(DISTINCT customer_unique_id) AS customer_cnt,
               COALESCE(SUM(gmv),0) AS gmv,
               COALESCE(AVG(gmv),0) AS avg_order_value,
               COALESCE(AVG(review_score),0) AS avg_review,
               COALESCE(AVG(delivery_days),0) AS avg_delivery_days,
               SUM(order_status='delivered')/COUNT(*) AS delivery_rate,
               SUM(order_approved_at IS NOT NULL)/COUNT(*) AS conversion_rate
        FROM fact_order_master
    """)
    rfm = query_one("SELECT COUNT(*) AS total, SUM(frequency>1) AS rep FROM fact_rfm")
    prod = query_one("SELECT COUNT(*) AS p, COUNT(DISTINCT product_category_name_english) AS c FROM dim_product")
    rep = int(rfm["rep"] or 0)
    total = int(rfm["total"])
    return {
        "order_cnt": int(s["order_cnt"]),
        "customer_cnt": int(s["customer_cnt"]),
        "product_cnt": int(prod["p"]),
        "category_cnt": int(prod["c"]),
        "gmv": _f(s["gmv"]),
        "avg_order_value": _f(s["avg_order_value"]),        # 客单价(每单)
        "avg_per_customer": _f(s["gmv"]) / int(s["customer_cnt"]) if s["customer_cnt"] else 0,
        "delivery_rate": _f(s["delivery_rate"]),
        "conversion_rate": _f(s["conversion_rate"]),        # 支付转化率(下单→已批准)
        "repurchase_rate": rep / total if total else 0,
        "repurchase_customers": rep,
        "avg_review": _f(s["avg_review"]),
        "avg_delivery_days": _f(s["avg_delivery_days"]),
    }


@router.get("/trend")
def trend(granularity: str = Query("month", pattern="^(month|day|week)$")):
    """GMV / 订单数 / 客户数 随时间变化。

    ⚠️ 修复(2026-10-22)：week 粒度原先取 fact_order_master.year_week，但该宽表
    并没有这一列（year_week 只在 fact_sales 上），请求 ?granularity=week 会直接
    500。这里改为由 purchase_date 现算 ISO 周（%x=ISO年、%v=ISO周），
    输出格式 '2017-W37' 与 fact_sales.year_week 完全一致。
    """
    col = {
        "month": "purchase_month",
        "day": "purchase_date",
        "week": "DATE_FORMAT(purchase_date, '%x-W%v')",
    }[granularity]
    # 无参数查询不做 % 格式化，故 SQL 里的字面量 % 可直接写（见 app/db.py 说明）
    rows = query(f"""
        SELECT {col} AS t,
               SUM(gmv) AS gmv,
               COUNT(*) AS orders,
               COUNT(DISTINCT customer_unique_id) AS customers
        FROM fact_order_master
        WHERE {col} IS NOT NULL
        GROUP BY {col} ORDER BY {col}
    """)
    return {"granularity": granularity, "data": [{"t": r["t"], "gmv": _f(r["gmv"]),
            "orders": int(r["orders"]), "customers": int(r["customers"])} for r in rows]}


@router.get("/category")
def category(limit: int = Query(15, le=50)):
    """品类 GMV 排行 (Top N)。"""
    rows = query("""
        SELECT product_category_name_english AS category,
               SUM(price) AS gmv, COUNT(*) AS items, AVG(price) AS avg_price
        FROM fact_sales
        WHERE product_category_name_english IS NOT NULL
        GROUP BY product_category_name_english
        ORDER BY gmv DESC LIMIT %s
    """, (limit,))
    return {"data": [{"category": r["category"], "gmv": _f(r["gmv"]),
            "items": int(r["items"]), "avg_price": _f(r["avg_price"])} for r in rows]}


@router.get("/region")
def region():
    """各州销售额。"""
    rows = query("""
        SELECT customer_state AS state, SUM(gmv) AS gmv, COUNT(*) AS orders
        FROM fact_order_master
        WHERE customer_state IS NOT NULL
        GROUP BY customer_state ORDER BY gmv DESC
    """)
    return {"data": [{"state": r["state"], "gmv": _f(r["gmv"]),
            "orders": int(r["orders"])} for r in rows]}


@router.get("/region_map")
def region_map():
    """各州销售额 + 地理坐标(供地图)。

    性能说明（原实现有致命笛卡尔积）：
      原 SQL 直接把 fact_order_master(约 10 万行) 与 dim_geolocation(约 1.9 万行)
      按州关联，而只有 27 个州 → 每个州匹配数百条地理记录 → 中间结果约 7000 万行，
      实测 25 秒超时。
      现改为【先各自聚合再关联】：地理表先按州聚成 27 行，再与订单聚合结果关联，
      实测 0.4 秒，且数值与原来完全一致。
    """
    rows = query("""
        SELECT o.state, o.gmv, o.orders, g.lat, g.lng
        FROM (
            SELECT customer_state AS state,
                   SUM(gmv) AS gmv,
                   COUNT(*) AS orders
            FROM fact_order_master
            WHERE customer_state IS NOT NULL
            GROUP BY customer_state
        ) o
        LEFT JOIN (
            SELECT geolocation_state AS state,
                   AVG(geolocation_lat) AS lat,
                   AVG(geolocation_lng) AS lng
            FROM dim_geolocation
            WHERE geolocation_state IS NOT NULL
            GROUP BY geolocation_state
        ) g ON o.state = g.state
        ORDER BY o.gmv DESC
    """)
    return {"data": [{"state": r["state"], "gmv": _f(r["gmv"]),
            "orders": int(r["orders"]), "lat": _f(r["lat"]), "lng": _f(r["lng"])} for r in rows]}


@router.get("/payment")
def payment():
    """支付方式分布。"""
    rows = query("""
        SELECT primary_payment_type AS type,
               COUNT(*) AS orders, SUM(payment_value_total) AS amount
        FROM fact_order_master
        WHERE primary_payment_type IS NOT NULL
        GROUP BY primary_payment_type ORDER BY amount DESC
    """)
    return {"data": [{"type": r["type"], "orders": int(r["orders"]),
            "amount": _f(r["amount"])} for r in rows]}


@router.get("/hour")
def hour():
    """下单时段分布。"""
    rows = query("""
        SELECT purchase_hour AS hour, COUNT(*) AS orders, SUM(gmv) AS gmv
        FROM fact_order_master
        WHERE purchase_hour IS NOT NULL
        GROUP BY purchase_hour ORDER BY purchase_hour
    """)
    return {"data": [{"hour": int(r["hour"]), "orders": int(r["orders"]),
            "gmv": _f(r["gmv"])} for r in rows]}


@router.get("/weekday")
def weekday():
    """下单星期分布 (0=周一)。"""
    rows = query("""
        SELECT purchase_weekday AS weekday, COUNT(*) AS orders, SUM(gmv) AS gmv
        FROM fact_order_master
        WHERE purchase_weekday IS NOT NULL
        GROUP BY purchase_weekday ORDER BY purchase_weekday
    """)
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return {"data": [{"weekday": int(r["weekday"]), "name": names[int(r["weekday"])],
            "orders": int(r["orders"]), "gmv": _f(r["gmv"])} for r in rows]}


@router.get("/order_status")
def order_status():
    """订单状态分布 (转化漏斗)。"""
    rows = query("""
        SELECT order_status, COUNT(*) AS cnt
        FROM fact_order_master
        GROUP BY order_status ORDER BY cnt DESC
    """)
    return {"data": [{"status": r["order_status"], "cnt": int(r["cnt"])} for r in rows]}


@router.get("/review")
def review():
    """评价星级分布。

    ⚠️ 必须过滤 NULL：未评价订单的 review_score 为 NULL（不再用 0 填充，
    否则会多出一根"0 星"柱并把平均分从 4.09 拉低到 4.05）。若不过滤，
    GROUP BY 会产出 score=None，下面 int() 直接 TypeError。
    """
    rows = query("""
        SELECT review_score, COUNT(*) AS cnt
        FROM fact_order_master
        WHERE review_score IS NOT NULL
        GROUP BY review_score ORDER BY review_score
    """)
    return {"data": [{"score": int(r["review_score"]), "cnt": int(r["cnt"])} for r in rows]}


@router.get("/top_products")
def top_products(limit: int = Query(10, le=50)):
    """热销商品 Top N。"""
    rows = query("""
        SELECT s.product_id, p.product_category_name_english AS category,
               SUM(s.price) AS gmv, COUNT(*) AS items
        FROM fact_sales s JOIN dim_product p ON s.product_id = p.product_id
        GROUP BY s.product_id, p.product_category_name_english
        ORDER BY gmv DESC LIMIT %s
    """, (limit,))
    return {"data": [{"product_id": r["product_id"], "category": r["category"],
            "gmv": _f(r["gmv"]), "items": int(r["items"])} for r in rows]}

# -*- coding: utf-8 -*-
"""工具执行器：真正去取数。

两种模式
--------
db    : 直接调用 app/ 下的路由函数（与网页看到的数据 100% 一致），需要 MySQL；
csv   : MySQL 不可用时，改读 cleaned/*.csv 与 算法2/*.csv 做降级，
        保证无数据库的机器也能演示（会明确标注降级）。

为什么要复用路由函数而不是重写 SQL
----------------------------------
复用的好处是"网页上看到的数"和"模型说的数"永远同源，不会出现两套口径。
这也是本项目把平台当作**工具层**的核心价值：模型的能力边界 = 平台已有能力。
"""
from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

BASE = Path(__file__).resolve().parent.parent.parent
ALGO2_DIR = BASE / "算法2"
CLEAN_DIR = BASE / "cleaned"


class ToolError(RuntimeError):
    """工具执行失败（参数错 / 数据源不可用）。"""


# ---------------------------------------------------------------
# 数据源可用性探测（结果缓存，避免每次调用都连库）
# ---------------------------------------------------------------
_detect_lock = threading.Lock()
_detect_result: str | None = None


def datasource_mode() -> str:
    """返回 'db' 或 'csv'。"""
    global _detect_result
    if _detect_result:
        return _detect_result
    with _detect_lock:
        if _detect_result:
            return _detect_result
        mode = "csv"
        try:
            from app.db import query_one
            row = query_one("SELECT COUNT(*) AS n FROM fact_order_master")
            if row and int(row["n"]) > 0:
                mode = "db"
        except Exception:
            mode = "csv"
        _detect_result = mode
        return mode


def reset_datasource_cache() -> None:
    """测试用：清掉探测缓存。"""
    global _detect_result
    _detect_result = None


# ---------------------------------------------------------------
# CSV 降级数据源
# ---------------------------------------------------------------
@lru_cache(maxsize=8)
def _csv(name: str):
    import pandas as pd
    for d in (ALGO2_DIR, CLEAN_DIR):
        p = d / name
        if p.is_file():
            return pd.read_csv(p, low_memory=False)
    raise ToolError(f"CSV 数据源缺失：{name}（请先运行 pipeline/algo2_model.py）")


def _csv_summary() -> dict:
    om = _csv("fact_order_master.csv")
    rfm = _csv("fact_rfm.csv")
    rep = int((rfm["frequency"] > 1).sum())
    total = int(len(rfm))
    return {
        "order_cnt": int(len(om)),
        "customer_cnt": int(om["customer_unique_id"].nunique()),
        "gmv": float(om["gmv"].sum()),
        "avg_order_value": float(om["gmv"].mean()),
        "avg_per_customer": float(om["gmv"].sum()) / max(1, om["customer_unique_id"].nunique()),
        "repurchase_rate": rep / total if total else 0.0,
        "repurchase_customers": rep,
        "avg_review": float(om["review_score"].mean()),
        "source": "csv-fallback",
    }


def _csv_forecast(category: str, weeks: int) -> dict:
    f = _csv("algo2_forecast_result.csv")
    sub = f[f["category"] == category]
    if sub.empty:
        raise ToolError(f"品类 {category} 无预测结果。可用品类见 prediction_categories。")
    head = sub.iloc[0]
    future = sub.head(weeks)[["forecast_week", "forecast_date", "predicted_qty",
                              "lower_95", "upper_95", "baseline_ma4_qty"]]
    return {
        "category": category,
        "model": head["model"],
        "mape_model_pct": float(head["mape_model_pct"]),
        "mape_baseline_pct": float(head["mape_baseline_pct"]),
        "mape_stable_model_pct": head.get("mape_stable_model_pct"),
        "wape_model_pct": float(head["wape_model_pct"]),
        "wape_baseline_pct": float(head["wape_baseline_pct"]),
        "history_weeks": int(head["history_weeks"]),
        "last_history_week": head["last_history_week"],
        "future": [
            {"week": r.forecast_week, "date": str(r.forecast_date),
             "forecast": float(r.predicted_qty), "lower": float(r.lower_95),
             "upper": float(r.upper_95), "baseline": float(r.baseline_ma4_qty)}
            for r in future.itertuples()
        ],
        "source": "csv-fallback",
    }


def _csv_selection(selection_type=None, recommendation=None, category=None, limit=10):
    s = _csv("algo2_selection_result.csv")
    if selection_type:
        s = s[s["selection_type"] == selection_type]
    if recommendation:
        s = s[s["recommendation"] == recommendation]
    if category:
        s = s[s["category"] == category]
    cols = ["rank", "selection_type", "product_id", "category", "gmv_recent",
            "gmv_prior", "gmv_total", "growth_pct", "qty_recent", "score_total",
            "recommendation"]
    return {"data": s.head(limit)[cols].to_dict("records"), "source": "csv-fallback"}


def _csv_pricing(has_suggestion=None, confidence=None, category=None, limit=10):
    p = _csv("algo2_pricing_result.csv")
    if has_suggestion is True:
        p = p[p["suggested_price"].notna()]
    elif has_suggestion is False:
        p = p[p["suggested_price"].isna()]
    if confidence:
        p = p[p["confidence"] == confidence]
    if category:
        p = p[p["category"] == category]
    cols = ["product_id", "category", "selection_type", "months_observed", "price_cv_pct",
            "current_price", "suggested_price", "price_change_pct", "elasticity",
            "elasticity_source", "elasticity_r2", "confidence",
            "expected_revenue_change_pct"]
    return {"data": p.head(limit)[cols].to_dict("records"), "source": "csv-fallback"}


def _csv_pricing_summary() -> dict:
    p = _csv("algo2_pricing_result.csv")
    has = p[p["suggested_price"].notna()]
    return {
        "total": int(len(p)),
        "has_suggestion": int(len(has)),
        "skipped": int(len(p) - len(has)),
        "raise_cnt": int((has["price_change_pct"] > 0).sum()),
        "cut_cnt": int((has["price_change_pct"] < 0).sum()),
        "item_level_cnt": int((has["elasticity_source"] == "商品级价格弹性").sum()),
        "avg_expected_revenue_change": float(has["expected_revenue_change_pct"].mean()),
        "source": "csv-fallback",
    }


def _csv_selection_summary() -> dict:
    s = _csv("algo2_selection_result.csv")
    by_type = []
    for t, g in s.groupby("selection_type"):
        by_type.append({"selection_type": t, "cnt": int(len(g)),
                        "strong": int((g["recommendation"] == "强推").sum())})
    return {"by_type": by_type, "total": int(len(s)),
            "strong_cnt": int((s["recommendation"] == "强推").sum()),
            "total_gmv": float(s["gmv_recent"].sum()), "source": "csv-fallback"}


def _csv_experiment_compare() -> dict:
    e = _csv("algo2_offline_experiment.csv")
    g = (e.groupby("model")
         .agg(mape_pct=("mape_pct", "mean"), wape_pct=("wape_pct", "mean"),
              mae=("mae", "mean"), rmse=("rmse", "mean")).reset_index())
    g["is_baseline"] = g["model"].str.contains("基线").astype(int)
    return {"data": g.to_dict("records"), "source": "csv-fallback"}


def _csv_experiment_median() -> dict:
    e = _csv("algo2_offline_experiment.csv")
    main = e[e["model"].str.startswith("主模型")]
    base = e[e["model"].str.startswith("基线")]
    def stat(d):
        return {"mape_mean": float(d["mape_pct"].mean()),
                "mape_median": float(d["mape_pct"].median()),
                "wape_mean": float(d["wape_pct"].mean()),
                "mae_mean": float(d["mae"].mean()),
                "rmse_mean": float(d["rmse"].mean()), "n": int(len(d))}
    return {"main": stat(main), "baseline": stat(base),
            "better_than_baseline_cnt": int((main["mape_pct"].values <
                                             base["mape_pct"].values).sum()),
            "source": "csv-fallback"}


def _csv_hitrate() -> dict:
    h = _csv("algo2_selection_hitrate.csv")
    return {"data": h[["level", "strategy", "hit_cnt", "hit_rate_pct",
                       "valid_top20_cnt"]].to_dict("records"),
            "source": "csv-fallback"}


def _csv_region(limit: int = 10) -> dict:
    om = _csv("fact_order_master.csv")
    g = (om.groupby("customer_state")
           .agg(gmv=("gmv", "sum"), orders=("order_id", "count"))
           .sort_values("gmv", ascending=False).head(limit).reset_index())
    g["gmv"] = g["gmv"].round(2)
    return {"data": g.rename(columns={"customer_state": "state"}).to_dict("records"),
            "source": "csv-fallback"}


def _csv_order_status() -> dict:
    om = _csv("fact_order_master.csv")
    vc = om["order_status"].value_counts()
    return {"data": [{"status": k, "cnt": int(v)} for k, v in vc.items()],
            "source": "csv-fallback"}


def _csv_review() -> dict:
    om = _csv("fact_order_master.csv")
    s = om["review_score"].dropna()
    vc = s.value_counts().sort_index()
    return {"data": [{"score": int(k), "cnt": int(v)} for k, v in vc.items()],
            "source": "csv-fallback"}


def _csv_summary_stats(group=None) -> dict:
    s = _csv("algo2_summary_stats.csv")
    if group:
        s = s[s["类别"] == group]
    return {"data": s.to_dict("records"), "source": "csv-fallback"}


# ---------------------------------------------------------------
# 工具实现（db 模式：复用路由函数）
# ---------------------------------------------------------------
def _dash():
    from app import dashboard as d
    return {"summary": d.summary, "trend": d.trend, "category": d.category,
            "top_products": d.top_products, "region": d.region,
            "order_status": d.order_status, "review": d.review}


def _anal():
    from app import analysis as a
    return {"rfm": a.rfm_segments, "funnel": a.conversion_funnel,
            "repurchase": a.repurchase, "pred_cats": a.pred_categories,
            "pred_sales": a.pred_sales, "rec": a.recommendation,
            "strategy": a.strategy_compare}


def _sel():
    from app import selection as s
    return {"summary": s.selection_summary, "products": s.selection_products,
            "top": s.selection_top}


def _pri():
    from app import pricing as p
    return {"summary": p.pricing_summary, "suggestions": p.pricing_suggestions,
            "skipped": p.pricing_skipped}


def _exp():
    from app import experiment as e
    return {"compare": e.experiment_compare, "median": e.experiment_median,
            "stats": e.experiment_summary_stats}


# 工具名 → 调用函数。函数接收 args dict，返回 dict。
def _t_dashboard_summary(a):
    if datasource_mode() == "csv":
        return _csv_summary()
    return _dash()["summary"]()


def _t_dashboard_trend(a):
    if datasource_mode() == "csv":
        raise ToolError("趋势接口需要 MySQL（olist_db）。CSV 降级模式不支持，"
                        "请先运行「一键导入主库.py」。")
    return _dash()["trend"](granularity=a.get("granularity", "month"))


def _t_dashboard_category(a):
    if datasource_mode() == "csv":
        raise ToolError("品类排行需要 MySQL。请先运行「一键导入主库.py」。")
    return _dash()["category"](limit=int(a.get("limit", 15)))


def _t_top_products(a):
    if datasource_mode() == "csv":
        raise ToolError("热销商品需要 MySQL。请先运行「一键导入主库.py」。")
    return _dash()["top_products"](limit=int(a.get("limit", 10)))


def _t_region(a):
    if datasource_mode() == "csv":
        return _csv_region(int(a.get("limit", 10)))
    return _dash()["region"]()


def _t_order_status(a):
    if datasource_mode() == "csv":
        return _csv_order_status()
    return _dash()["order_status"]()


def _t_review(a):
    if datasource_mode() == "csv":
        return _csv_review()
    return _dash()["review"]()


def _t_rfm(a):
    if datasource_mode() == "csv":
        raise ToolError("RFM 分群需要 MySQL。请先运行「一键导入算法库.py」。")
    return _anal()["rfm"](scheme=a.get("scheme", "rule8"))


def _t_funnel(a):
    if datasource_mode() == "csv":
        raise ToolError("漏斗需要 MySQL。请先运行「一键导入主库.py」。")
    return _anal()["funnel"]()


def _t_repurchase(a):
    if datasource_mode() == "csv":
        rfm = _csv("fact_rfm.csv")
        rep = int((rfm["frequency"] > 1).sum())
        return {"repeat_customers": rep, "total_customers": int(len(rfm)),
                "repeat_rate": rep / len(rfm), "source": "csv-fallback"}
    return _anal()["repurchase"]()


def _t_pred_categories(a):
    if datasource_mode() == "csv":
        f = _csv("algo2_forecast_result.csv")
        u = f.drop_duplicates("category")
        return {"categories": [{"category": r.category,
                                "history_weeks": int(r.history_weeks),
                                "last_week": r.last_history_week}
                               for r in u.itertuples()],
                "count": int(len(u)), "source": "csv-fallback"}
    return _anal()["pred_cats"]()


def _trim_forecast(res: dict, keep_history: int = 12) -> dict:
    """预测结果里 history 可能上百周，只保留最近若干周，避免撑爆 prompt。"""
    if not isinstance(res, dict):
        return res
    hist = res.get("history")
    if isinstance(hist, list) and len(hist) > keep_history:
        res = dict(res)
        res["history"] = hist[-keep_history:]
        res["history_note"] = f"仅展示最近 {keep_history} 周，共 {len(hist)} 周"
    return res


def _t_forecast(a):
    cat = a.get("category")
    if not cat:
        raise ToolError("缺少参数 category（品类英文名）。先调用 prediction_categories 获取。")
    weeks = int(a.get("weeks", 8))
    weeks = max(1, min(weeks, 8))
    if datasource_mode() == "csv":
        return _trim_forecast(_csv_forecast(cat, weeks))
    return _trim_forecast(_anal()["pred_sales"](category=cat, weeks=weeks))


def _t_selection_summary(a):
    if datasource_mode() == "csv":
        return _csv_selection_summary()
    return _sel()["summary"]()


def _t_selection_products(a):
    limit = int(a.get("limit", 10))
    if datasource_mode() == "csv":
        return _csv_selection(a.get("selection_type"), a.get("recommendation"),
                              a.get("category"), limit)
    return _sel()["products"](selection_type=a.get("selection_type"),
                              recommendation=a.get("recommendation"),
                              category=a.get("category"), limit=limit)


def _t_recommendation(a):
    if datasource_mode() == "csv":
        # 品类级口径无法从算法2 CSV 还原，明确报错而不是给错数
        raise ToolError("品类级 Top10 需要 MySQL（它在 SQL 里实时计算）。"
                        "商品级榜单请用 selection_products。")
    return _anal()["rec"]()


def _t_strategy(a):
    if datasource_mode() == "csv":
        raise ToolError("策略对照需要 MySQL（实时计算）。CSV 模式下可用 "
                        "algo2_selection_hitrate.csv 的口径替代，见实验工具。")
    return _anal()["strategy"]()


def _t_pricing_summary(a):
    if datasource_mode() == "csv":
        return _csv_pricing_summary()
    return _pri()["summary"]()


def _t_pricing_suggestions(a):
    limit = int(a.get("limit", 10))
    if datasource_mode() == "csv":
        return _csv_pricing(a.get("has_suggestion"), a.get("confidence"),
                            a.get("category"), limit)
    return _pri()["suggestions"](confidence=a.get("confidence"),
                                 has_suggestion=a.get("has_suggestion"),
                                 category=a.get("category"), limit=limit)


def _t_pricing_skipped(a):
    if datasource_mode() == "csv":
        s = _csv("algo2_pricing_skipped.csv")
        return {"data": s.head(int(a.get("limit", 10))).to_dict("records"),
                "source": "csv-fallback"}
    return _pri()["skipped"](limit=int(a.get("limit", 10)))


def _t_exp_median(a):
    if datasource_mode() == "csv":
        return _csv_experiment_median()
    return _exp()["median"]()


def _t_exp_compare(a):
    if datasource_mode() == "csv":
        return _csv_experiment_compare()
    return _exp()["compare"]()


def _t_exp_stats(a):
    if datasource_mode() == "csv":
        return _csv_summary_stats(a.get("group"))
    return _exp()["stats"](group=a.get("group"))


TOOL_IMPL: dict[str, Callable[[dict], Any]] = {
    "dashboard_summary": _t_dashboard_summary,
    "dashboard_trend": _t_dashboard_trend,
    "dashboard_category": _t_dashboard_category,
    "dashboard_top_products": _t_top_products,
    "region_sales": _t_region,
    "order_status_dist": _t_order_status,
    "review_dist": _t_review,
    "rfm_segments": _t_rfm,
    "conversion_funnel": _t_funnel,
    "repurchase": _t_repurchase,
    "prediction_categories": _t_pred_categories,
    "sales_forecast": _t_forecast,
    "selection_summary": _t_selection_summary,
    "selection_products": _t_selection_products,
    "recommendation": _t_recommendation,
    "strategy_compare": _t_strategy,
    "pricing_summary": _t_pricing_summary,
    "pricing_suggestions": _t_pricing_suggestions,
    "pricing_skipped": _t_pricing_skipped,
    "experiment_median": _t_exp_median,
    "experiment_compare": _t_exp_compare,
    "experiment_summary_stats": _t_exp_stats,
}


# ---------------------------------------------------------------
# 结果压缩：把大列表截断、浮点数取 4 位，避免 prompt 过长
# ---------------------------------------------------------------
def _compact(obj: Any, max_items: int = 10, _depth: int = 0) -> Any:
    if _depth > 6:
        return "…"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, list):
                out[k] = [_compact(x, max_items, _depth + 1) for x in v[:max_items]]
                if len(v) > max_items:
                    out[k].append(f"…共 {len(v)} 条，已截断")
            else:
                out[k] = _compact(v, max_items, _depth + 1)
        return out
    if isinstance(obj, list):
        return [_compact(x, max_items, _depth + 1) for x in obj[:max_items]]
    if isinstance(obj, float):
        return round(obj, 4)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    try:
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
    except Exception:
        pass
    return str(obj)


def execute(name: str, args: dict | None = None,
            max_items: int = 10) -> dict:
    """执行工具，永不抛异常——失败也返回结构化错误，让模型能自我纠正。

    返回：
        {"ok": True,  "tool": name, "source": "db"|"csv", "data": {...}}
        {"ok": False, "tool": name, "error": "..."}
    """
    args = args or {}
    fn = TOOL_IMPL.get(name)
    if fn is None:
        return {"ok": False, "tool": name,
                "error": f"未知工具 {name}。可用工具：{', '.join(TOOL_IMPL)}"}
    try:
        raw = fn(args)
        return {"ok": True, "tool": name, "source": datasource_mode(),
                "data": _compact(raw, max_items)}
    except ToolError as e:
        return {"ok": False, "tool": name, "error": str(e)}
    except Exception as e:  # 数据库断了、参数类型错等
        return {"ok": False, "tool": name,
                "error": f"{type(e).__name__}: {str(e)[:200]}"}


def health() -> dict:
    """工具层自检：数据源模式 + 关键工具是否可用。"""
    mode = datasource_mode()
    out = {"datasource": mode, "tools": len(TOOL_IMPL), "probe": {}}
    for name in ("dashboard_summary", "sales_forecast", "pricing_summary",
                 "experiment_median"):
        args = {"category": "health_beauty"} if name == "sales_forecast" else {}
        r = execute(name, args, max_items=1)
        out["probe"][name] = "ok" if r["ok"] else r.get("error", "fail")
    return out
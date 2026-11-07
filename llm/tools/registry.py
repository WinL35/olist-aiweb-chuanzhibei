# -*- coding: utf-8 -*-
"""工具注册表：把现有 API 翻译成 function calling 的 tool schema。

设计要点
--------
description 不是写给人看的注释，而是**给模型的调度指令**。所以每条都写清：
    1. 这个工具能回答什么问题；
    2. 什么时候**必须**调用它（防止模型凭常识瞎编数字）；
    3. 返回什么字段。

这 22 个工具覆盖了现有 33 个接口里与"经营决策"最相关的部分。
"""
from __future__ import annotations

from typing import Any

# JSON Schema 的小子集（足够覆盖 function calling 需求）
TOOLS: list[dict[str, Any]] = [
    # ---------------- 经营看板 ----------------
    {
        "name": "dashboard_summary",
        "kind": "dashboard",
        "description": "查询平台核心经营指标：GMV、客单价（每单）、人均消费、订单数、客户数、"
                       "商品数、品类数、支付转化率、复购率、平均评分、平均送达天数。"
                       "凡是问「整体规模/大盘怎么样/一共卖了多少」必须先调这个，禁止凭印象给数字。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：gmv, avg_order_value, avg_per_customer, order_cnt, customer_cnt, "
                   "repurchase_rate, avg_review 等",
    },
    {
        "name": "dashboard_trend",
        "kind": "dashboard",
        "description": "查询 GMV / 订单数 / 客户数的时间趋势，用于「最近走势/增长趋势」类问题。",
        "parameters": {
            "type": "object",
            "properties": {
                "granularity": {"type": "string", "enum": ["month", "week", "day"],
                                "description": "时间粒度，默认 month"},
            },
        },
        "returns": "dict：data=[{t, gmv, orders, customers}]",
    },
    {
        "name": "dashboard_category",
        "kind": "dashboard",
        "description": "查询品类 GMV 排行（Top N），用于「哪些品类卖得最好/头部品类」。",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50,
                                     "description": "返回条数，默认 15"}},
        },
        "returns": "dict：data=[{category, gmv, items, avg_price}]",
    },
    {
        "name": "dashboard_top_products",
        "kind": "dashboard",
        "description": "查询 GMV 最高的商品（Top N），用于「哪些商品最好卖」。",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        },
        "returns": "dict：data=[{product_id, category, gmv, qty}]",
    },
    # ---------------- 地区 / 状态 / 评分 ----------------
    {
        "name": "region_sales",
        "kind": "dashboard",
        "description": "按巴西州（state）查询 GMV 与订单数分布，用于「哪个州卖得多/地区结构」。"
                       "注意：只能看**历史分布**，不能做地区预测。",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
        },
        "returns": "dict：data=[{state, gmv, orders}]",
    },
    {
        "name": "order_status_dist",
        "kind": "dashboard",
        "description": "查询订单状态分布（delivered/shipped/canceled/unavailable 等）与各状态订单数。"
                       "用于「取消了多少单/缺货多少单/取消率」类问题。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：data=[{status, cnt}]",
    },
    {
        "name": "review_dist",
        "kind": "dashboard",
        "description": "查询评分 1~5 星分布。用于「评分怎么样/好评差评占比」。"
                       "未评价订单不计入，也不能填 0。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：data=[{score, cnt}]",
    },
    # ---------------- 用户与转化 ----------------
    {
        "name": "rfm_segments",
        "kind": "analysis",
        "description": "查询 RFM 用户分群结果。scheme=rule8 为业务规则 8 类（可解释话术），"
                       "scheme=kmeans4 为 K-Means 4 类（验证聚类结构）。"
                       "用于「用户怎么分层/高价值客户多少/流失风险多少」。",
        "parameters": {
            "type": "object",
            "properties": {"scheme": {"type": "string", "enum": ["rule8", "kmeans4"]}},
        },
        "returns": "dict：segments=[{segment, user_cnt, ratio, monetary_sum}]",
    },
    {
        "name": "conversion_funnel",
        "kind": "analysis",
        "description": "查询订单履约漏斗（下单→批准→发货→送达→评价）及各环节流失。"
                       "注意这是订单状态漏斗，不是浏览行为漏斗。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：steps=[{step, cnt, rate}]",
    },
    {
        "name": "repurchase",
        "kind": "analysis",
        "description": "查询复购情况（复购用户数、复购率、复购用户人均金额）。"
                       "回答复购问题必须调它，并说明 Olist 一人一单特性。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：repeat_customers, repeat_rate, ...",
    },
    # ---------------- 预测（算法2）----------------
    {
        "name": "prediction_categories",
        "kind": "forecast",
        "description": "列出所有可预测的品类及其历史周数、数据截止周。"
                       "用户没说具体品类时先调这个再确认，不要自己编品类名。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：categories=[{category, history_weeks, last_week}]",
    },
    {
        "name": "sales_forecast",
        "kind": "forecast",
        "description": "查询指定品类未来 1-8 周的销量预测，含 95% 区间、MA4 基线、"
                       "该品类的 holdout MAPE/WAPE。"
                       "问「下个月/未来几周能卖多少」「要不要备货」必须调用，"
                       "禁止用常识估算销量。粒度只有品类×周，不支持日/单商品/卖家。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "description": "品类英文名，如 health_beauty、computers"},
                "weeks": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["category"],
        },
        "returns": "dict：category, model, mape_model_pct, mape_baseline_pct, wape_model_pct, "
                   "future=[{week, forecast, lower, upper, baseline}]",
    },
    # ---------------- 选品（算法2）----------------
    {
        "name": "selection_summary",
        "kind": "selection",
        "description": "查询选品结果总览：增长榜/分析池各多少、强推多少、合计近期 GMV。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：by_type=[{selection_type, cnt, ...}], total, total_gmv",
    },
    {
        "name": "selection_products",
        "kind": "selection",
        "description": "查询商品级选品榜单（算法2 真实交付物，50 条）。"
                       "可按榜单类型、推荐等级、品类过滤。问「推荐哪些商品」必须调用。"
                       "注意：这是商品级；品类级 Top10 是另一套口径，用 recommendation。",
        "parameters": {
            "type": "object",
            "properties": {
                "selection_type": {"type": "string", "enum": ["增长榜", "高销量分析池"]},
                "recommendation": {"type": "string", "enum": ["强推", "推荐", "备选"]},
                "category": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
        "returns": "dict：data=[{rank, selection_type, product_id, category, gmv_recent, "
                   "growth_pct, score_total, recommendation}]",
    },
    {
        "name": "recommendation",
        "kind": "selection",
        "description": "查询**品类级**选品 Top10（项目原有口径，规模×增长 0.5/0.5 归一化）。"
                       "与 selection_products（商品级 0.45/0.40/0.15）不是同一套，回答时须说明口径。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：data=[{rank, category, score, growth_rate, recent_gmv}]",
    },
    {
        "name": "strategy_compare",
        "kind": "selection",
        "description": "查询品类级两策略离线对照（热门 GMV vs 纯增长）的命中率。"
                       "回答「选品策略哪个好」时必须调用，返回热门策略与纯增长策略的命中率（如 80% vs 0%）。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：strategy_A{name,hit_rate}, strategy_B{name,hit_rate}, conclusion",
    },
    # ---------------- 定价（算法2）----------------
    {
        "name": "pricing_summary",
        "kind": "pricing",
        "description": "查询定价建议数量口径：参与定价数、可给建议价数、样本不足数、"
                       "建议提价/降价数、商品级弹性占比。回答「覆盖了多少商品」必须调用。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：total, has_suggestion, skipped, raise_cnt, cut_cnt, item_level_cnt",
    },
    {
        "name": "pricing_suggestions",
        "kind": "pricing",
        "description": "查询具体商品的定价建议清单（当前价、建议价、调价幅度、弹性、"
                       "弹性来源、置信度、预期营收变化）。问「哪些商品该降价/涨价」必须调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "confidence": {"type": "string", "enum": ["高", "中", "低"]},
                "has_suggestion": {"type": "boolean",
                                   "description": "true=只看有建议价的；false=只看样本不足的"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        "returns": "dict：data=[{product_id, category, current_price, suggested_price, "
                   "price_change_pct, elasticity, elasticity_source, confidence}]",
    },
    {
        "name": "pricing_skipped",
        "kind": "pricing",
        "description": "查询「因样本不足没给建议价」的商品明细及原因。"
                       "回答「为什么有些商品没建议价」必须调用，用于体现『宁可承认不知道』。",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        },
        "returns": "dict：data=[{product_id, category, months_observed, price_cv_pct, reason}]",
    },
    # ---------------- 离线实验 ----------------
    {
        "name": "experiment_median",
        "kind": "experiment",
        "description": "查询主模型 vs MA4 基线的**均值与中位数**对比（汇报标准口径）。"
                       "回答「模型准不准/比基线好吗」必须调用，避免只报均值造成误判。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：main/media/baseline 的 mape 均值、中位数、wape 等",
    },
    {
        "name": "experiment_compare",
        "kind": "experiment",
        "description": "查询 4 个预测模型的整体对比（主模型/MA4/季节朴素/阻尼 Holt），"
                       "含 MAPE、WAPE、MAE、RMSE。用于「几个模型哪个好」。",
        "parameters": {"type": "object", "properties": {}},
        "returns": "dict：data=[{model, mape_pct, wape_pct, mae, rmse, is_baseline}]",
    },
    {
        "name": "experiment_summary_stats",
        "kind": "experiment",
        "description": "查询算法2 最终统计 31 项（数据集/预测/选品/定价四类）。"
                       "用于需要精确口径数字的汇报场景。",
        "parameters": {
            "type": "object",
            "properties": {"group": {"type": "string",
                                     "enum": ["数据集", "预测", "选品", "定价"]}},
        },
        "returns": "dict：data=[{类别, 统计项, 数值, 口径说明}]",
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]
_BY_NAME = {t["name"]: t for t in TOOLS}


def schema_for_llm() -> list[dict]:
    """转成 OpenAI function calling 的 tools 数组。"""
    out = []
    for t in TOOLS:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return out


def get(name: str) -> dict | None:
    return _BY_NAME.get(name)


def catalog() -> list[dict]:
    """给 /api/llm/tools 的展示结构。"""
    return [{"name": t["name"], "kind": t["kind"], "description": t["description"],
             "parameters": t["parameters"], "returns": t.get("returns", "")}
            for t in TOOLS]
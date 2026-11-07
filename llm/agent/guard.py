# -*- coding: utf-8 -*-
"""护栏：越界识别、拒答判定、品类解析、SQL 白名单。

为什么护栏比 prompt 重要
------------------------
垂直模型最大的风险不是"答不出"，而是"答得很像真的"。所以把
「数据不支持什么」写成**代码级规则**，先于模型判断，模型无权绕过：

    · 日粒度/卖家/城市级预测 → 拒答
    · 库存、毛利、退货、竞品 → 数据不含，拒答
    · 调价超过 ±15%          → 拒绝，并给合规替代方案
    · SQL 非白名单视图        → 拦截

这一幕在答辩里非常好讲：**能力边界是写死的，不是靠模型自觉。**
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from llm import config

BASE = Path(__file__).resolve().parent.parent.parent
FORECAST_CSV = BASE / "算法2" / "algo2_forecast_result.csv"

# ---------------------------------------------------------------
# 越界规则：(正则, 结论, 建议替代)
# ---------------------------------------------------------------
OUT_OF_SCOPE: list[tuple[str, str, str]] = [
    (r"(明天|明天能|今天|当日|某天|具体哪天|下周[一二三四五六日]|日粒度|每天能卖)",
     "预测粒度只有「品类 × 周」，最多向后 8 周，无法给出日粒度预测。",
     "可以用「品类未来 1-8 周的周销量区间」替代，或用趋势接口看历史日内分布。"),
    (r"(卖家|商户|店铺|supplier|seller)",
     "数据与算法结果都不支持卖家粒度的预测或选品。",
     "可以给品类级或商品级（product_id）的预测与选品结果。"),
    (r"(城市|州|省份|地区|region)[^，。？！]{0,14}(预测|销量|备货|卖多少)",
     "预测粒度不含地区维度，无法按城市/州做销量预测。",
     "看板支持地区 GMV 分布，可做区域结构分析而非区域预测。"),
    (r"(20(2[5-9]|[3-9]\d))\s*年|明年|后年|未来\s*\d{2}\s*年",
     "数据范围是 2016-09-04 ~ 2018-09-03，预测也只能在其后 8 周内，"
     "无法外推到未来年份。",
     "可以给数据截止周之后 8 周内的周粒度预测。"),
    (r"(是因为|归因|导致|是不是.*造成|促销|节假日|圣诞|黑五|双十一)",
     "数据不含促销活动、节假日、竞品价格等外部变量，无法做因果归因。"
     "只能描述相关性与历史模式。",
     "可做同期对比与季节项分析，但要说明它不能证明因果。"),
    (r"(库存|备货量|安全库存|补多少件|周转)",
     "数据不含库存、在库量、补货周期字段，不能计算库存周转或补货量。",
     "只能给销量预测区间，库存决策需商家自有库存数据配合。"),
    (r"(毛利|利润|利润率|成本|净利)",
     "数据不含成本与费用字段，无法计算毛利/净利。",
     "可给 GMV 与价格弹性方向，利润测算需接入成本数据。"),
    (r"(退货|退款|售后|取消率)",
     "数据只有订单状态（含 canceled），没有退货/退款流程字段，不能算退货率。",
     "可用「取消订单占比」近似描述，但要说明口径不同。"),
    (r"(竞品|对手|别家|同行价格|市场均价)",
     "数据只包含本店（Olist）交易，没有竞品价格。",
     "可做本品历史价格-销量弹性分析，竞品比价需外部数据。"),
    (r"(浏览|曝光|点击|加购|收藏|uv|pv)",
     "原始数据不含浏览/曝光/加购行为，无法计算 UV 转化率、加购率。",
     "「转化率」在本项目口径是「下单→已批准」，属于履约口径。"),
    (r"(个人信息|手机号|身份证|地址定位到人|是谁买)",
     "不做个人身份识别，也不对外提供可识别个人的数据。",
     "只能提供聚合到品类/地区的统计结果。"),
]

# 价格越界：抓取「提高/降低 X%」
_PCT = re.compile(r"(提高|提升|上调|涨价|降低|下调|降价|下降)[^\d%]{0,6}(\d+(?:\.\d+)?)\s*%")
_ANY_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# SQL 白名单（只允许查视图，且禁止写操作）
ALLOWED_VIEWS = {
    "v_category_sales", "v_monthly_sales", "v_order_funnel",
    "v_customer_rfm", "v_seller_performance", "v_payment_dist",
    "v_review_summary", "v_region_sales", "v_product_sales", "v_delivery_perf",
}
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace)\b"
    r"|--|;|\bunion\b|into\s+outfile|load_file", re.I)


# ---------------------------------------------------------------
# 品类解析
# ---------------------------------------------------------------
# 中文口语 → 英文品类（覆盖常见问法）
CATEGORY_ALIAS = {
    "美妆": "health_beauty", "美容": "health_beauty", "个护": "health_beauty",
    "健康": "health_beauty", "电脑": "computers", "计算机": "computers",
    "家具": "furniture_decor", "居家": "furniture_decor", "家装": "furniture_decor",
    "运动": "sports_leisure", "户外": "sports_leisure",
    "玩具": "toys", "婴儿": "baby", "母婴": "baby",
    "床品": "bed_bath_table", "卫浴": "bed_bath_table", "床上": "bed_bath_table",
    "电子": "electronics", "手机": "telephony", "电话": "telephony",
    "手表": "watches_gifts", "礼品": "watches_gifts",
    "办公": "office_furniture", "汽车": "auto", "车品": "auto",
    "家居": "housewares", "厨房": "housewares",
    "花园": "garden_tools", "工具": "construction_tools_construction",
    "服饰": "fashion_underwear_beach", "女装": "fashion_underwear_beach",
    "鞋": "shoes", "箱包": "bag_accessories",
    "宠物": "pet_shop", "图书": "books_general_interest",
    "食品": "food", "饮料": "drinks", "酒": "drinks",
    "音响": "audio", "音乐": "audio", "钟表": "watches_gifts",
    "办公用品": "stationery", "文具": "stationery",
    "珠宝": "jewelry", "配饰": "fashion_accessories",
}


@lru_cache(maxsize=1)
def category_list() -> tuple[str, ...]:
    """从预测结果 CSV 读品类全集（74 个）。"""
    try:
        import pandas as pd
        df = pd.read_csv(FORECAST_CSV, usecols=["category"])
        return tuple(sorted(df["category"].dropna().unique()))
    except Exception:
        return ()


def resolve_category(text: str) -> str | None:
    """从问题里解析品类英文名。

    顺序：中文别名 → 英文全名子串 → 英文近似（下划线分词命中）。
    解析不到返回 None，由调用方去问用户，**不允许模型自己编品类**。
    """
    if not text:
        return None
    low = text.lower()

    # 1) 英文全名直接出现
    for c in category_list():
        if c in low:
            return c

    # 2) 中文别名
    for zh, en in CATEGORY_ALIAS.items():
        if zh in text:
            if en in category_list():
                return en
            for c in category_list():
                if c.startswith(en.split("_")[0]):
                    return c
            return en

    # 3) 英文单词片段（如 "beauty" → health_beauty）
    words = re.findall(r"[a-z]{4,}", low)
    for w in words:
        for c in category_list():
            if w in c.split("_"):
                return c
    return None


# ---------------------------------------------------------------
# 越界与合规检查
# ---------------------------------------------------------------
def check_bounds(question: str) -> list[dict]:
    """返回命中的越界项 [{rule, conclusion, alternative}]。"""
    hits = []
    for pattern, conclusion, alt in OUT_OF_SCOPE:
        if re.search(pattern, question, re.I):
            hits.append({"rule": pattern, "conclusion": conclusion, "alternative": alt})
    return hits


def check_price_bound(question: str) -> dict | None:
    """检查是否要求超出 ±15% 的调价。返回 {pct, allowed, direction, message}。"""
    m = _PCT.search(question)
    if not m:
        return None
    direction = "上调" if m.group(1) in ("提高", "提升", "上调", "涨价") else "下调"
    pct = float(m.group(2))
    allowed = pct <= config.PRICE_BOUND * 100 + 1e-9
    return {
        "pct": pct, "direction": direction, "allowed": allowed,
        "limit_pct": config.PRICE_BOUND * 100,
        "message": (f"要求{direction} {pct:g}%，在允许范围 ±{config.PRICE_BOUND:.0%} 内。"
                    if allowed else
                    f"要求{direction} {pct:g}%，超出建议价允许的 ±{config.PRICE_BOUND:.0%} 约束。"
                    f"模型给出的建议价只在现价 ±{config.PRICE_BOUND:.0%} 内有效，"
                    f"超范围需业务侧单独评估（且上线前必须 A/B）。"),
    }


def sql_guard(sql: str) -> dict:
    """NL2SQL 护栏：只允许 SELECT 白名单视图，禁止写操作与注释拼接。"""
    if not sql or not sql.strip():
        return {"ok": False, "reason": "空 SQL"}
    s = sql.strip()
    if not re.match(r"^(select|with)\b", s, re.I):
        return {"ok": False, "reason": "只允许 SELECT 查询"}
    if _FORBIDDEN_SQL.search(s):
        return {"ok": False, "reason": "SQL 含被禁止的关键字（写操作/注释/多语句/UNION）"}
    # 至少出现一个白名单视图
    used = [v for v in ALLOWED_VIEWS if v in s.lower()]
    if not used:
        return {"ok": False,
                "reason": f"只能查询白名单视图：{', '.join(sorted(ALLOWED_VIEWS))}"}
    if "limit" not in s.lower():
        s = s.rstrip().rstrip(";") + " LIMIT 200"
    return {"ok": True, "sql": s, "views": used}


def is_refusal_needed(question: str) -> dict | None:
    """综合判定是否需要拒答；需要时返回结构化拒答原因。"""
    hits = check_bounds(question)
    if hits:
        return {"type": "out_of_scope", "hits": hits}
    return None
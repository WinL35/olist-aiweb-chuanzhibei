# -*- coding: utf-8 -*-
"""确定性回答组装器（offline 模式）

作用
----
无 API Key 时，用「硬规则 + 检索 + 工具真实取数」按固定模板组装回答。
它不是"假装成大模型"，而是把同一套管线里的**语言组织**换成确定性规则，
用途有二：

    1. 断网/无额度时仍能演示完整链路（评委常要求现场拔网线）；
    2. 作为评测的**下界基线**——如果规则引擎都能答对口径题，
       说明知识层本身是有效的，接入真模型只会更好。

接入真实底座后走 llm.agent.planner 的 LLM 路径，本文件不参与。
"""
from __future__ import annotations

import re
from typing import Any

from llm import config
from llm.agent import guard
from llm.tools import executor

# 意图 → (正则, 说明)。顺序即优先级（越前越先被采用）
INTENTS: list[tuple[str, str, list[str]]] = [
    ("method", r"(什么模型|模型链|什么算法|用什么方法|用的什么|怎么预测出来的|季节项|季节模型|holt|winters|transformer|深度学习|神经网络)", []),
    ("metrics", r"(mae|rmse|绝对误差|平均绝对)", []),
    ("usage", r"(采购单|下单|直接拿|能直接用|可以直接|拿.{0,4}备货|敢不敢用|备多少|备货量|安全库存|该备)", []),
    ("meta", r"(时间范围|覆盖.{0,6}时间|数据范围|多少行|多少条|数据来源|数据集|统计口径|原始记录)", []),
    ("region", r"(哪个州|按州|州看|各省|全省|地区|省份|城市|区域|state|region)", []),
    ("status", r"(取消率|订单状态|缺货|状态分布|取消了多少|剔掉|剔除|549|无效订单|哪些订单被)", []),
    ("review", r"(评分|好评|差评|星级|评价分布)", []),
    ("forecast", r"(预测|能卖多少|卖多少|备货|补货|未来.{0,6}周|下个?月|走势|需求|销量)", []),
    ("selection", r"(选品|推荐|推哪些|上榜|榜单|该卖什么|主推|增长榜|分析池)", []),
    ("pricing", r"(定价|建议价|调价|降价|涨价|弹性|价格.{0,6}(高|低|调))", []),
    ("hitrate", r"(命中率|回测|纯增长|纯规模|策略.{0,8}(对比|哪个))", []),
    ("accuracy", r"(准不准|误差|mape|wape|精度|基线|模型.{0,6}(好|差|行))", []),
    ("repurchase", r"(复购|回购|回头|二次购买)", []),
    ("rfm", r"(分群|分层|rfm|高价值|流失风险|用户画像)", []),
    ("funnel", r"(漏斗|转化|履约|送达率)", []),
    ("skip", r"(为什么不给|样本不足|没给建议价|没有建议价|没建议价|为什么.{0,6}建议价|数据不足|缺数据)", []),
    ("dashboard", r"(gmv|营收|规模|大盘|客单价|订单数|客户数|整体|一共卖)", []),
]

# ---------------------------------------------------------------
# 口径篡改拦截（Policy Engine）
#
# 这是与"越界拒答"并列的第二道护栏：用户要求**改口径把数字做好看**时，
# 不是靠模型自觉拒绝，而是由规则命中后**强制在结论开头给出纠正**。
# 答辩时可讲：模型无权答应篡改口径。
# ---------------------------------------------------------------
_POLICY: list[tuple[str, str, str]] = [
    (r"(取消|无效)[^，。？]{0,12}(算进|也算|包含|计入|算入)|(算进|计入)[^，。？]{0,10}(取消|无效)",
     "不能把取消/缺货订单算进销量或 GMV。",
     "必须剔除：有效订单 112,101 行、全量 112,650 行，共剔除 549 行；"
     "否则会虚增规模并污染预测与评估。"),
    (r"customer_id(?!_)",
     "不能用 customer_id 算客户数。",
     "客户数必须用 customer_unique_id（95,420）；customer_id 是订单级 ID（99,441 个），"
     "用它去重会把同一个人的多次购买算成多个客户。"),
    (r"(评分|评价|review)[^，。？]{0,12}(填\s*0|填零|记为\s*0|设成\s*0|统一填)|(填|设|改)\s*0\s*分",
     "不能把未评价订单的评分填 0。",
     "未评价必须保持 NULL——0 不是合法星级，会把平均分从 4.086 拉到 4.055，"
     "并让评分分布从 5 档变 6 档。"),
    (r"(只|就)[^，。？]{0,8}(写|报|看|引用)[^，。？]{0,8}均值",
     "不能只报 MAPE 均值。",
     "均值 135.73% 被低基数周放大，必须同时报中位数 90.46%（基线 99.69%）与 "
     "WAPE 72.59%（基线 68.47%）。"),
    (r"(写成|改成|虚报|报低|压低|做小)[^，。？]{0,10}(0|小|少|好看)",
     "不能修改指标数值。",
     "须如实报告：主模型 MAE 10.53、RMSE 12.31、MAPE 中位数 90.46%，"
     "压低或改小属于数据造假。"),
    (r"(全面|显著|整体)[^，。？]{0,6}优于",
     "不能宣称模型整体优于基线。",
     "只能说「部分品类优于基线」：中位数 90.46% 优于 99.69%，但 WAPE 72.59% "
     "略差于 68.47%，仅 33/74 个品类更优。"),
    (r"(保证|一定|肯定)[^，。？]{0,20}(收入|营收|增长|提升|增收|涨|roi)|roi",
     "无法对收益做保证。",
     "所有调价收益都是弹性模型测算值（平均 +26.60%），上线前必须小流量 A/B，"
     "并纳入毛利、库存与竞品价格。"),
]


def policy_overrides(question: str) -> list[dict]:
    """命中的口径篡改项，按 (触发, 纠正, 依据) 返回。"""
    out = []
    for pattern, verdict, evidence in _POLICY:
        if re.search(pattern, question, re.I):
            out.append({"rule": pattern, "verdict": verdict, "evidence": evidence})
    return out


def _f(v, nd: int = 2) -> str:
    """数字格式化：千分位。"""
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _first(res: dict) -> dict:
    return (res or {}).get("data") or {}


def _ok(res: dict) -> bool:
    return bool(res and res.get("ok"))


def _tool(name: str, args: dict | None = None) -> dict:
    return executor.execute(name, args or {}, max_items=8)


def _rows(payload: Any, *keys) -> list:
    """从 {data:[...]} 或 {by_type:[...]} 等结构里取列表。

    只返回 dict 元素：executor 的 _compact 会在列表尾部追加一条
    「…共 N 条，已截断」的说明字符串，不能让构建器把它当数据行。
    """
    def _clean(v):
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    if isinstance(payload, list):
        return _clean(payload)
    if not isinstance(payload, dict):
        return []
    for k in keys or ("data", "by_type", "future", "segments", "categories"):
        got = _clean(payload.get(k))
        if got:
            return got
    # 有些接口把列表放在 data 字典里
    d = payload.get("data")
    if isinstance(d, dict):
        for k in keys or ("data", "by_type", "future", "segments"):
            got = _clean(d.get(k))
            if got:
                return got
    return []


def _unwrap(res: dict) -> Any:
    return (res or {}).get("data")


# ---------------------------------------------------------------
# 各意图 → (结论, 明细点, 引用)
# ---------------------------------------------------------------
def _build_dashboard(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("dashboard_summary")
    if not _ok(res):
        return "", [], []
    d = _unwrap(res) or {}
    gmv = d.get("gmv")
    aov = d.get("avg_order_value")
    apc = d.get("avg_per_customer")
    rep = d.get("repurchase_rate")
    cons = (f"大盘 GMV 为 R$ {_f(gmv)}，但它是**商品金额**（不含运费），不等于营收；"
            f"客单价（每单）R$ {_f(aov)}，人均消费 R$ {_f(apc)}。")
    bullets = [
        f"GMV（商品金额，不含运费）：R$ {_f(gmv)}",
        f"客单价（GMV ÷ 订单数）：R$ {_f(aov)}",
        f"人均消费（GMV ÷ 用户数）：R$ {_f(apc)}",
        f"订单数 {_f(d.get('order_cnt'), 0)} 单，用户数 {_f(d.get('customer_cnt'), 0)} 人"
        f"（该口径含取消订单客户；仅计有效订单为 95,420 人）",
        f"复购率 {_f(float(rep or 0) * 100)}%（Olist 一人一单特性，属数据性质而非运营失败）",
    ]
    cites = [{"指标": "GMV（商品金额）", "值": f"R$ {_f(gmv)}", "来源": "dashboard_summary"},
             {"指标": "客单价（每单）", "值": f"R$ {_f(aov)}", "来源": "dashboard_summary"},
             {"指标": "人均消费", "值": f"R$ {_f(apc)}", "来源": "dashboard_summary"}]
    return cons, bullets, cites


def _build_forecast(question: str) -> tuple[str, list[str], list[dict]]:
    cat = guard.resolve_category(question)
    if not cat:
        # 只有明确在问"某个商品"时才提示补充品类；其余情况交给别的意图回答，
        # 避免把"用的什么模型"这类问题误答成"请提供品类"。
        if re.search(r"(商品|单品|这款|这个产品)", question):
            res = _tool("prediction_categories")
            cats = _rows(_unwrap(res)) or _rows((_unwrap(res) or {}).get("categories"))
            names = [c.get("category") for c in cats][:12]
            cons = ("预测粒度是「品类 × 周」，需要先指定品类。可预测品类包括："
                    + "、".join([n for n in names if n]) + " 等。")
            return cons, ["请补充品类名（中英文均可，如「美妆」或 health_beauty）。"], []
        return "", [], []

    weeks = 8
    m = re.search(r"(\d+)\s*周", question)
    if m:
        weeks = max(1, min(int(m.group(1)), 8))
    elif "下个月" in question or "一个月" in question:
        weeks = 4

    res = _tool("sales_forecast", {"category": cat, "weeks": weeks})
    if not _ok(res):
        return "", [], []
    d = _unwrap(res) or {}
    fut = d.get("future") or []
    if not fut:
        return "", [], []

    # 指标可能嵌在 metrics 子对象（DB 模式）或平铺（CSV 模式）
    mtx = d.get("metrics") or {}
    mape = mtx.get("mape_model", d.get("mape_model_pct"))
    mape_b = mtx.get("mape_baseline", d.get("mape_baseline_pct"))
    wape = d.get("wape_model_pct")
    model = mtx.get("model") or d.get("model")
    hist = d.get("history_weeks") or d.get("n_weeks")

    total = sum(float(x.get("forecast") or 0) for x in fut)
    lo = sum(float(x.get("lower") or 0) for x in fut)
    hi = sum(float(x.get("upper") or 0) for x in fut)
    base = sum(float(x.get("baseline") or 0) for x in fut)

    cons = (f"{cat} 未来 {len(fut)} 周预计合计约 **{_f(total, 1)} 件**"
            f"（95% 区间 {_f(lo, 1)}~{_f(hi, 1)} 件），同期 MA4 基线为 {_f(base, 1)} 件。")
    if mape is not None and mape_b is not None:
        cons += (f"该品类 holdout MAPE {_f(mape)}%（基线 {_f(mape_b)}%），"
                 f"**只能作为趋势参考，不能用于精确备货**。")
    else:
        cons += "该品类预测**只能作为趋势参考，不能用于精确备货**。"

    bullets = [f"第 {i + 1} 周（{x.get('week')}）：{_f(x.get('forecast'), 1)} 件"
               f"（区间 {_f(x.get('lower'), 1)}~{_f(x.get('upper'), 1)}）"
               for i, x in enumerate(fut[:4])]
    bullets.append(f"模型：{model or '阻尼 Holt'}；历史长度 {hist if hist is not None else '?'} 周")
    if mape is not None and mape_b is not None:
        bullets.append(f"本品类 MAPE：主模型 {_f(mape)}% / 基线 {_f(mape_b)}%")
    cites = [{"指标": f"{cat} 未来 {len(fut)} 周合计", "值": f"{_f(total, 1)} 件",
              "来源": "sales_forecast"}]
    if mape is not None:
        cites.append({"指标": "本品类 MAPE（主/基线）",
                      "值": f"{_f(mape)}% / {_f(mape_b)}%", "来源": "sales_forecast"})
    return cons, bullets, cites


def _build_selection(question: str) -> tuple[str, list[str], list[dict]]:
    sres = _tool("selection_summary")
    pres = _tool("selection_products", {"limit": 5})
    cons, bullets, cites = "", [], []
    if _ok(sres):
        d = _unwrap(sres) or {}
        total = d.get("total")
        by = d.get("by_type") or []
        parts = "、".join(f"{x.get('selection_type')} {x.get('cnt')} 个" for x in by)
        cons = (f"选品结果是商品级榜单共 {total} 个（{parts}），"
                f"两榜用途不同：增长榜用于推荐，高销量分析池用于定价估计。")
        bullets.append(f"总览：{parts}")
        cites.append({"指标": "选品商品数", "值": f"{total} 个", "来源": "selection_summary"})
    if _ok(pres):
        rows = _rows(_unwrap(pres))
        for r in rows[:5]:
            bullets.append(f"#{r.get('rank')} {str(r.get('product_id'))[:10]}… "
                           f"{r.get('category')} 增长 {_f(r.get('growth_pct'), 1)}% "
                           f"综合分 {_f(r.get('score_total'), 1)}（{r.get('recommendation')}）")
        if rows:
            cites.append({"指标": "榜首商品综合分",
                          "值": f"{_f(rows[0].get('score_total'), 1)}",
                          "来源": "selection_products"})
    return cons, bullets, cites


def _build_pricing(question: str) -> tuple[str, list[str], list[dict]]:
    sres = _tool("pricing_summary")
    pres = _tool("pricing_suggestions", {"has_suggestion": True, "limit": 5})
    cons, bullets, cites = "", [], []
    if _ok(sres):
        d = _unwrap(sres) or {}
        conf = d.get("confidence") or {}
        total = d.get("total")
        has = d.get("has_suggestion")
        cons = (f"50 个参与定价的商品中只有 **{has} 个**给出建议价，"
                f"{d.get('no_suggestion')} 个明确标注「数据不足」；"
                f"其中高置信仅 {conf.get('高', '?')} 个、中置信 {conf.get('中', '?')} 个。"
                f"结论：给不出建议价的商品宁可空着，也不给虚假价格。")
        bullets = [f"参与定价 {total} 个 → 有建议价 {has} 个 / 样本不足 {d.get('no_suggestion')} 个",
                   f"建议降价 {d.get('cut_cnt')} 个、建议提价 {d.get('raise_cnt')} 个",
                   "调价幅度上限：建议价被夹在现价 ±15% 内，多数降价建议已触及 **-15%** 下限（业务约束）",
                   f"平均预期营收变化 {_f(d.get('avg_expected_revenue_change_pct'))}%"
                   f"（模型测算，需 A/B 验证）"]
        cites.append({"指标": "有建议价/参与数", "值": f"{has}/{total}",
                      "来源": "pricing_summary"})
    if _ok(pres):
        rows = _rows(_unwrap(pres))
        for r in rows[:3]:
            bullets.append(f"{str(r.get('product_id'))[:10]}… {r.get('category')}："
                           f"{_f(r.get('current_price'))} → {_f(r.get('suggested_price'))} "
                           f"({_f(r.get('price_change_pct'), 1)}%)")
    return cons, bullets, cites


def _build_hitrate(question: str) -> tuple[str, list[str], list[dict]]:
    sres = _tool("strategy_compare")
    if _ok(sres):
        d = _unwrap(sres) or {}
        a = d.get("strategy_A") or {}
        b = d.get("strategy_B") or {}
        cons = (f"品类级策略对照：{a.get('name')} 命中率 {_f(a.get('hit_rate'), 1)}%，"
                f"{b.get('name')} 命中率 {_f(b.get('hit_rate'), 1)}%。"
                f"纯增长策略专挑偶然冲高的小品类，必须与规模结合。")
        bullets = [f"验证窗口：{d.get('validation_window')}，Top20% 品类 {d.get('top20_count')} 个",
                   f"{a.get('name')}：{_f(a.get('hit_rate'), 1)}%",
                   f"{b.get('name')}：{_f(b.get('hit_rate'), 1)}%"]
        cites = [{"指标": "热门策略命中率", "值": f"{_f(a.get('hit_rate'), 1)}%",
                  "来源": "strategy_compare"},
                 {"指标": "纯增长策略命中率", "值": f"{_f(b.get('hit_rate'), 1)}%",
                  "来源": "strategy_compare"}]
        return cons, bullets, cites
    # 降级：用商品级回测口径
    return ("", [], [])


def _build_accuracy(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("experiment_median")
    if not _ok(res):
        return "", [], []
    d = _unwrap(res) or {}
    med = d.get("median") or {}
    by = d.get("by_model") or []
    better = d.get("main_model_better_categories") or {}
    main = next((x for x in by if "主模型" in str(x.get("model"))), {})
    base = next((x for x in by if "基线" in str(x.get("model"))), {})
    cons = (f"不能只说 MAPE 均值 {_f(main.get('avg_mape'))}% vs 基线 {_f(base.get('avg_mape'))}%"
            f"（只差 {_f(float(main.get('avg_mape') or 0) - float(base.get('avg_mape') or 0))} 个百分点）。"
            f"稳健口径看中位数 {_f(med.get('main_model_mape'))}% vs {_f(med.get('baseline_mape'))}%，"
            f"但 WAPE {_f(main.get('avg_wape'))}% 反而略差于基线 {_f(base.get('avg_wape'))}%。"
            f"所以只能说「部分品类优于基线」。")
    bullets = [f"MAPE 均值：主模型 {_f(main.get('avg_mape'))}% / 基线 {_f(base.get('avg_mape'))}%",
               f"MAPE 中位数：主模型 {_f(med.get('main_model_mape'))}% / 基线 {_f(med.get('baseline_mape'))}%",
               f"WAPE：主模型 {_f(main.get('avg_wape'))}% / 基线 {_f(base.get('avg_wape'))}%",
               f"优于基线的品类：{better.get('better')}/{better.get('total')}"
               f"（{_f(better.get('pct'), 1)}%）"]
    cites = [{"指标": "MAPE 中位数（主/基线）",
              "值": f"{_f(med.get('main_model_mape'))}% / {_f(med.get('baseline_mape'))}%",
              "来源": "experiment_median"},
             {"指标": "优于基线品类数", "值": f"{better.get('better')}/{better.get('total')}",
              "来源": "experiment_median"}]
    return cons, bullets, cites


def _build_repurchase(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("repurchase")
    if not _ok(res):
        return "", [], []
    payload = _unwrap(res)
    rows = _rows(payload, "data")
    rep = next((r for r in rows if "复购" in str(r.get("type"))), {})
    one = next((r for r in rows if "单次" in str(r.get("type"))), {})
    cons = (f"复购用户 {_f(rep.get('customers'), 0)} 人，占 {_f(rep.get('customer_pct'))}%；"
            f"但复购用户贡献金额占比 {_f(rep.get('monetary_pct'))}%，"
            f"说明复购人群价值更高。注意 Olist 是「一人一单」型数据，低复购率是数据性质。")
    bullets = [f"单次购买 {_f(one.get('customers'), 0)} 人（{_f(one.get('customer_pct'))}%）",
               f"复购 {_f(rep.get('customers'), 0)} 人（{_f(rep.get('customer_pct'))}%），"
               f"平均购买 {_f(rep.get('avg_frequency'))} 次"]
    cites = [{"指标": "复购率", "值": f"{_f(rep.get('customer_pct'))}%", "来源": "repurchase"}]
    return cons, bullets, cites


def _build_rfm(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("rfm_segments", {"scheme": "rule8"})
    if not _ok(res):
        return "", [], []
    d = _unwrap(res) or {}
    rows = d.get("data") or []
    top = rows[:4]
    cons = (f"用户按 RFM 规则分为 8 类（另有一套 K-Means 4 类用于验证结构），"
            f"共 {d.get('total_users', '?')} 人。占比最高的几类为："
            + "、".join(f"{r.get('segment')} {_f(r.get('pct'))}%" for r in top[:3]) + "。")
    bullets = [f"{r.get('segment')}：{_f(r.get('cnt'), 0)} 人（{_f(r.get('pct'))}%），"
               f"人均金额 {_f(r.get('avg_monetary'))}" for r in top]
    cites = [{"指标": "分群口径", "值": "RFM 规则 8 类 + K-Means 4 类",
              "来源": "rfm_segments"}]
    return cons, bullets, cites


def _build_funnel(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("conversion_funnel")
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    first, last = rows[0], rows[-1]
    cons = (f"订单履约漏斗：{first.get('stage')} {_f(first.get('cnt'), 0)} → "
            f"{last.get('stage')} {_f(last.get('cnt'), 0)}，整体留存 {_f(last.get('rate'))}%。"
            f"注意这是**订单状态漏斗**，不是浏览行为漏斗。")
    bullets = [f"{r.get('stage')}：{_f(r.get('cnt'), 0)}（留存 {_f(r.get('rate'))}%）"
               for r in rows]
    cites = [{"指标": "漏斗整体留存", "值": f"{_f(last.get('rate'))}%",
              "来源": "conversion_funnel"}]
    return cons, bullets, cites


def _build_skip(question: str) -> tuple[str, list[str], list[dict]]:
    sres = _tool("pricing_summary")
    kres = _tool("pricing_skipped", {"limit": 5})
    if not _ok(sres):
        return "", [], []
    d = _unwrap(sres) or {}
    cons = (f"{d.get('no_suggestion')} 个商品没给建议价，原因是没通过四道门槛："
            f"月度观测 ≥{config.MIN_MONTHS} 个月、价格变异 ≥{config.MIN_PRICE_SD:.0%}、"
            f"R² ≥{config.ELAS_R2_MIN}、弹性必须为负。不满足就不给价（存 NULL，不写 0）。")
    bullets = [f"参与定价 {d.get('total')} 个，可给建议价 {d.get('has_suggestion')} 个，"
               f"样本不足 {d.get('no_suggestion')} 个"]
    if _ok(kres):
        for r in _rows(_unwrap(kres))[:3]:
            bullets.append(f"{str(r.get('product_id'))[:10]}… 观测 {r.get('months_observed')} 个月，"
                           f"价格变异 {_f(r.get('price_cv_pct'))}%")
    cites = [{"指标": "样本不足数", "值": f"{d.get('no_suggestion')} 个",
              "来源": "pricing_summary"}]
    return cons, bullets, cites


def _build_method(question: str) -> tuple[str, list[str], list[dict]]:
    """模型链与方法：回答「用的什么模型」必须说清实际落在哪一级。"""
    res = _tool("experiment_median")
    bullets, cites = [], []
    if _ok(res):
        d = _unwrap(res) or {}
        by = d.get("by_model") or []
        names = "、".join(str(x.get("model")) for x in by)
        bullets.append(f"参与评估的模型：{names}")
        med = d.get("median") or {}
        bullets.append(f"主模型中位数 MAPE {_f(med.get('main_model_mape'))}% / "
                       f"基线 {_f(med.get('baseline_mape'))}%")
        cites.append({"指标": "实际选中模型", "值": "阻尼 Holt（φ=0.95）",
                      "来源": "experiment_median"})
    cons = ("采用**三级降级模型链**：Holt-Winters（趋势+季节，需 ≥104 周）→ "
            "阻尼 Holt（φ=0.95）→ 阻尼线性回归；基线是最近 4 周移动平均（MA4）。"
            "实际 74 个品类**全部落在第 2 级「阻尼 Holt」**，因为品类历史中位数仅 84.5 周、"
            "最长 105 周，Holt-Winters 的 104 周门槛基本没人达标。"
            "没有使用深度学习——周粒度数据太稀疏，且答辩需要可解释。")
    return cons, bullets, cites


def _build_metrics(question: str) -> tuple[str, list[str], list[dict]]:
    """MAE / RMSE 等绝对误差指标。"""
    res = _tool("experiment_compare")
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    main = next((r for r in rows if "主模型" in str(r.get("model"))), rows[0])
    base = next((r for r in rows if "基线" in str(r.get("model"))), {})
    mae = main.get("avg_mae", main.get("mae"))
    rmse = main.get("avg_rmse", main.get("rmse"))
    cons = (f"主模型 MAE 均值 **{_f(mae)} 件**、RMSE **{_f(rmse)} 件**"
            f"（基线 MAE {_f(base.get('avg_mae', base.get('mae')))}、"
            f"RMSE {_f(base.get('avg_rmse', base.get('rmse')))}）。"
            f"MAE 与 RMSE 单位都是「件」，RMSE 更大说明存在个别大误差周。")
    bullets = [f"{r.get('model')}：MAPE {_f(r.get('avg_mape', r.get('mape_pct')))}%，"
               f"WAPE {_f(r.get('avg_wape', r.get('wape_pct')))}%，"
               f"MAE {_f(r.get('avg_mae', r.get('mae')))}，"
               f"RMSE {_f(r.get('avg_rmse', r.get('rmse')))}"
               for r in rows[:4]]
    cites = [{"指标": "MAE（主模型）", "值": _f(mae), "来源": "experiment_compare"},
             {"指标": "RMSE（主模型）", "值": _f(rmse), "来源": "experiment_compare"}]
    return cons, bullets, cites


def _build_meta(question: str) -> tuple[str, list[str], list[dict]]:
    """数据集整体口径（时间范围、记录数、覆盖度）。"""
    res = _tool("experiment_summary_stats", {"group": "数据集"})
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    kv = {}
    for r in rows:
        name = r.get("name") or r.get("统计项")
        val = r.get("value_text") or r.get("数值")
        if name:
            kv[str(name)] = val
    cons = (f"数据范围 {kv.get('时间范围', '2016-09-04 ~ 2018-09-03')}，"
            f"有效销售记录 {kv.get('原始销售记录数', '112,101')} 行，"
            f"覆盖 {kv.get('覆盖品类数', '74')} 个品类、{kv.get('覆盖用户数', '95,420')} 个用户，"
            f"总 GMV R$ {kv.get('总 GMV', '13,494,400.74')}（商品金额，不含运费）。")
    bullets = [f"{k}：{v}" for k, v in kv.items()]
    cites = [{"指标": "数据时间范围", "值": kv.get("时间范围", ""),
              "来源": "experiment_summary_stats"}]
    return cons, bullets, cites


def _build_usage(question: str) -> tuple[str, list[str], list[dict]]:
    """能不能直接拿结果去下单/备货。"""
    res = _tool("experiment_median")
    d = _unwrap(res) or {} if _ok(res) else {}
    med = d.get("median") or {}
    better = d.get("main_model_better_categories") or {}
    cons = ("**不建议**直接拿预测结果下采购单。预测只能用于**趋势参考**："
            f"MAPE 中位数 {_f(med.get('main_model_mape', 90.46))}%，"
            f"WAPE 72.59%，且仅 {better.get('better', 33)}/74 个品类优于基线；"
            "区间还可能偏窄。"
            "采购下单还需要**安全库存、补货周期、在手库存**，这三项目前数据里没有。")
    bullets = [f"主模型 MAPE 中位数 {_f(med.get('main_model_mape', 90.46))}% / "
               f"基线 {_f(med.get('baseline_mape', 99.69))}%",
               "预测粒度：品类 × 周，最多 8 周",
               "缺失字段：库存、成本、补货周期"]
    cites = [{"指标": "MAPE 中位数", "值": f"{_f(med.get('main_model_mape', 90.46))}%",
              "来源": "experiment_median"}]
    return cons, bullets, cites


def _build_region(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("region_sales", {"limit": 8})
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    tot = sum(float(r.get("gmv") or 0) for r in rows)
    top = rows[0]
    cons = (f"按州看，{top.get('state')} 州 GMV 最高（R$ {_f(top.get('gmv'))}，"
            f"{_f(top.get('orders'), 0)} 单），前 {len(rows)} 个州合计贡献 "
            f"R$ {_f(tot)}。注意：这是**历史分布**，不是地区预测——"
            f"预测粒度只到品类 × 周，没有地区维度。")
    bullets = [f"{r.get('state')}：GMV R$ {_f(r.get('gmv'))}，{_f(r.get('orders'), 0)} 单"
               for r in rows]
    cites = [{"指标": f"{top.get('state')} 州 GMV", "值": f"R$ {_f(top.get('gmv'))}",
              "来源": "region_sales"}]
    return cons, bullets, cites


def _build_status(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("order_status_dist")
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    d = {r.get("status"): int(r.get("cnt") or 0) for r in rows}
    total = sum(d.values())
    bad = d.get("canceled", 0) + d.get("unavailable", 0)
    cons = (f"共 {_f(total, 0)} 单，其中已送达 {_f(d.get('delivered', 0), 0)} 单"
            f"（{_f(d.get('delivered', 0) / max(1, total) * 100)}%）；"
            f"取消 {_f(d.get('canceled', 0), 0)} 单、缺货 {_f(d.get('unavailable', 0), 0)} 单，"
            f"合计 {_f(bad, 0)} 单（{_f(bad / max(1, total) * 100)}%）。"
            f"这两类在算销量与 GMV 时会被剔除（对应 549 行明细）。")
    bullets = [f"{r.get('status')}：{_f(r.get('cnt'), 0)} 单" for r in rows]
    cites = [{"指标": "取消 + 缺货订单", "值": f"{_f(bad, 0)} 单", "来源": "order_status_dist"}]
    return cons, bullets, cites


def _build_review(question: str) -> tuple[str, list[str], list[dict]]:
    res = _tool("review_dist")
    if not _ok(res):
        return "", [], []
    rows = _rows(_unwrap(res))
    if not rows:
        return "", [], []
    total = sum(int(r.get("cnt") or 0) for r in rows)
    wsum = sum(int(r.get("score") or 0) * int(r.get("cnt") or 0) for r in rows)
    avg = wsum / total if total else 0
    d = {int(r.get("score") or 0): int(r.get("cnt") or 0) for r in rows}
    good = d.get(5, 0) + d.get(4, 0)
    bad = d.get(1, 0) + d.get(2, 0)
    cons = (f"共 {_f(total, 0)} 条评价，平均 **{_f(avg, 3)} 分**；"
            f"4~5 星 {_f(good / max(1, total) * 100)}%、1~2 星 {_f(bad / max(1, total) * 100)}%。"
            f"未评价订单不计入分母，也**不能填 0**——0 不是合法星级，会污染分布。")
    bullets = [f"{r.get('score')} 星：{_f(r.get('cnt'), 0)} 条" for r in rows]
    cites = [{"指标": "平均评分", "值": _f(avg, 3), "来源": "review_dist"}]
    return cons, bullets, cites


BUILDERS = {
    "dashboard": _build_dashboard,
    "forecast": _build_forecast,
    "selection": _build_selection,
    "pricing": _build_pricing,
    "hitrate": _build_hitrate,
    "accuracy": _build_accuracy,
    "repurchase": _build_repurchase,
    "rfm": _build_rfm,
    "funnel": _build_funnel,
    "skip": _build_skip,
    "method": _build_method,
    "metrics": _build_metrics,
    "meta": _build_meta,
    "usage": _build_usage,
    "region": _build_region,
    "status": _build_status,
    "review": _build_review,
}


def detect_intents(question: str) -> list[str]:
    """按正则识别意图，可命中多个（多步决策问题往往会命中 2~3 个）。"""
    hits = []
    for name, pattern, _ in INTENTS:
        if re.search(pattern, question, re.I):
            hits.append(name)
    # 命中过多时收缩到最相关的 3 个（避免答案冗长）
    priority = ["method", "metrics", "usage", "meta", "region", "status",
                "review", "forecast", "pricing", "selection", "accuracy",
                "hitrate", "skip", "dashboard", "rfm", "funnel", "repurchase"]
    hits.sort(key=lambda x: priority.index(x) if x in priority else 99)
    return hits[:3]


def compose(question: str, mode: str, rules: list[dict],
            snippets: list[dict]) -> dict:
    """组装确定性回答。返回与 planner 一致的结构。"""
    # 1) 越界 → 拒答
    refusal = guard.is_refusal_needed(question)
    if refusal and mode != "baseline":
        hit = refusal["hits"][0]
        answer = (f"**【做不到】** {hit['conclusion']}\n\n"
                  f"**可以替代的方案**：{hit['alternative']}\n\n"
                  f"本项目的能力边界是写死在护栏里的（llm/agent/guard.py），"
                  f"不满足条件的请求不会给出估计值——宁可承认不知道，也不给假数字。")
        return _result(question, mode, answer,
                       {"conclusion": hit["conclusion"], "citations": [],
                        "tools_used": [], "rules": rules, "snippets": snippets,
                        "confidence": "低", "limitations": [hit["conclusion"]],
                        "refused": True})

    # 2) 调价越界 → 提示约束但仍给合规区间
    pb = guard.check_price_bound(question)

    # 2.5) 口径篡改请求 → 强制纠偏（模型无权答应）
    policies = policy_overrides(question)

    # 3) 按意图取数（no_tools 模式不取数，只讲口径）
    intents = detect_intents(question)
    if not intents:
        intents = ["dashboard"]

    conclusions, bullets, cites = [], [], []
    if mode != "no_tools":
        for it in intents:
            fn = BUILDERS.get(it)
            if not fn:
                continue
            try:
                c, b, ci = fn(question)
            except Exception:
                continue
            if c:
                conclusions.append(c)
            bullets.extend(b)
            cites.extend(ci)

    if not conclusions:
        # 没取到数（no_tools / 工具失败）：退回纯口径回答
        conclusions.append("这个问题需要行业口径来说明，我先给出本项目的定义与边界。")
        if mode == "no_tools":
            limitations = ["当前为 no_tools 消融模式：未调用工具，因此没有真实数字。"]
        else:
            limitations = ["本问题未匹配到可直接取数的工具，以上仅为口径层面的说明。"]
    else:
        limitations = []

    # 口径篡改请求：纠正信息放最前面（模型无权答应）
    if policies:
        conclusions = [f"{p['verdict']}{p['evidence']}" for p in policies] + conclusions

    # 调价幅度超出 ±15%：把约束放到结论第一条，不让模型"顺着问"给数
    if pb and not pb["allowed"]:
        conclusions.insert(0, pb["message"] + "所以不能按该幅度给出建议价。")

    parts = []
    if conclusions:
        parts.append("**【结论】**\n" + " ".join(conclusions))
    if bullets:
        parts.append("**关键数据**\n" + "\n".join(f"- {b}" for b in bullets))
    if policies:
        parts.append("**口径纠偏**\n" + "\n".join(
            f"- {p['verdict']}" for p in policies))
    if rules:
        parts.append("**口径提醒**\n" + "\n".join(
            f"- 【{r['id']}】{r['correct']}" for r in rules[:3]))
    if snippets:
        parts.append("**可核对依据**\n" + "\n".join(
            f"- 《{s['source']}》§{s['heading']}" for s in snippets[:3]))
    if pb and not pb["allowed"]:
        parts.append(f"**约束提示**\n- {pb['message']}")
    if limitations:
        parts.append("**局限**\n" + "\n".join(f"- {x}" for x in limitations))

    answer = "\n\n".join(parts)
    return _result(question, mode, answer,
                   {"conclusion": conclusions[0] if conclusions else "",
                    "citations": cites, "tools_used": _tools_of(intents, mode),
                    "rules": rules, "snippets": snippets,
                    "confidence": "高" if cites else "中",
                    "limitations": limitations, "refused": False,
                    "policies": policies})


def _tools_of(intents: list[str], mode: str) -> list[str]:
    if mode == "no_tools":
        return []
    m = {"dashboard": ["dashboard_summary"], "forecast": ["sales_forecast"],
         "selection": ["selection_summary", "selection_products"],
         "pricing": ["pricing_summary", "pricing_suggestions"],
         "hitrate": ["strategy_compare"], "accuracy": ["experiment_median"],
         "repurchase": ["repurchase"], "rfm": ["rfm_segments"],
         "funnel": ["conversion_funnel"], "skip": ["pricing_summary", "pricing_skipped"],
         "method": ["experiment_median"], "metrics": ["experiment_compare"],
         "meta": ["experiment_summary_stats"], "usage": ["experiment_median"],
         "region": ["region_sales"], "status": ["order_status_dist"],
         "review": ["review_dist"]}
    out = []
    for it in intents:
        out.extend(m.get(it, []))
    return out


def compose_baseline(question: str) -> dict:
    """baseline：裸底座的典型答法（无工具、无口径库）。

    这里刻意**不给任何项目数字**——这正是通用模型在没有工具时的真实处境：
    只能讲教科书定义。它在评测中会大量失分，用来量化"通用可用"与
    "精准好用"的差距。
    """
    answer = ("GMV 是商品交易总额（Gross Merchandise Volume），通常用来衡量电商平台的"
              "成交规模。一般来说，GMV 可以作为营收的参考指标，数值越大说明业务规模越大。"
              "建议关注 GMV、客单价、转化率等核心指标，并结合用户增长情况综合判断。")
    return _result(question, "baseline", answer,
                   {"conclusion": "GMV 是成交规模指标，可作为营收参考。",
                    "citations": [], "tools_used": [], "rules": [], "snippets": [],
                    "confidence": "低",
                    "limitations": ["未接入行业数据与工具，无项目口径"],
                    "refused": False})


def _result(question: str, mode: str, answer: str, extra: dict) -> dict:
    return {
        "question": question,
        "answer": answer,
        "mode": mode,
        "provider": "offline",
        "model": "offline-rule-engine",
        "conclusion": extra.get("conclusion", ""),
        "citations": extra.get("citations", []),
        "tools_used": extra.get("tools_used", []),
        "rules_applied": [{"id": r["id"], "topic": r["topic"]} for r in extra.get("rules", [])],
        "snippets": [{"source": s["source"], "heading": s["heading"],
                      "score": s.get("score")} for s in extra.get("snippets", [])],
        "confidence": extra.get("confidence", "中"),
        "limitations": extra.get("limitations", []),
        "refused": extra.get("refused", False),
        "policy_hits": [p["verdict"] for p in (extra.get("policies") or [])],
        "datasource": executor.datasource_mode(),
    }
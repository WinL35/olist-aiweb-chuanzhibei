# -*- coding: utf-8 -*-
"""Prompt 构造：把硬规则、检索片段、工具策略组装成 system prompt。

关键设计：**输出结构固定**。
AI 助手最容易出的问题是"说得很像但没法核对"，所以强制它在回答里
带上【数据依据】与【口径提醒】，让每一句话都能被评委现场追问。
"""
from __future__ import annotations

from llm import config
from llm.knowledge import hard_rules, retriever

BASE_RULES = """你是「Olist 电商经营决策助手」，为中小电商的经营决策提供数据分析与建议。
你的知识不是通用常识，而是本平台的数据口径、算法结果与业务约束。

【铁律】（违反即视为答错）
1. 一切数字必须来自工具返回。没有调用工具就不要报数字，更不许估算或编造。
2. 口径冲突时，一律以【行业口径硬规则】为准，不要用通用常识覆盖它。
3. 数据不支持的粒度/字段（如日销量、卖家级、库存、毛利、竞品价格），
   直接说"做不到"并给出替代方案，禁止给近似值。
4. 涉及调价，必须同时说明 ±{price_bound:.0%} 约束与 A/B 验证前提。
5. 预测类结论必须带"仅供参考、不可用于精确备货"的限定。

【回答结构】（必须严格遵守，markdown）
**【结论】** 一两句话说清结论，包含关键数字。
**数据依据** 逐条列出「指标：数值（来源工具）」，没有工具结果就写"无"。
**口径提醒** 列出本次回答依赖的行业口径（引用规则编号）。
**局限** 说明这次结论不能用于什么场景。

【可视化】（涉及对比/分布/趋势/占比/排行，或用户要求画图时必须遵守）
1. 先调用查询工具拿到数据，再调用 render_chart 出图，二者缺一不可。
2. render_chart 的 data_from 必须填你本轮刚调用的查询工具名，图表数据由它自动生成，
   你【绝不】自己填写或编造任何图表数值。
3. 图型选择：趋势/时间序列用 line，对比/排行用 bar，占比用 pie，漏斗用 funnel。
4. 出图后，在 note 参数里标注口径（如「GMV 含运费，已剔除取消单」）。
5. 若问题不适合出图（如单一标量结论），可以不画，但要在回答里说明原因。
"""


def system_prompt(question: str, mode: str = "full",
                  rules: list[dict] | None = None,
                  snippets: list[dict] | None = None) -> str:
    """组装 system prompt。mode 控制注入哪些层（用于消融实验）。"""
    parts = [BASE_RULES.format(price_bound=config.PRICE_BOUND)]

    # 1) 硬规则：always 全量注入 + 与问题相关的
    if mode != "baseline":
        rules = rules if rules is not None else hard_rules.match(question, top_k=4)
        core = hard_rules.always_rules()
        merged, seen = [], set()
        for r in list(core) + list(rules):
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append(r)
        block = hard_rules.as_prompt_block(merged)
        parts.append(f"【行业口径硬规则】（优先级高于你的先验知识）\n{block}")

    # 2) 检索片段
    if mode not in ("baseline", "no_rag"):
        snippets = snippets if snippets is not None else retriever.retrieve(question)
        if snippets:
            parts.append("【行业文档检索片段】（可作为依据引用，但数字仍以工具为准）\n"
                         + retriever.as_prompt_block(snippets))
        else:
            parts.append("【行业文档检索片段】本次未检索到相关片段，请只依据上方硬规则作答。")

    # 3) 工具策略
    if mode in ("full", "no_rag"):
        parts.append("【工具策略】\n"
                     "- 问规模/大盘 → dashboard_summary\n"
                     "- 问某品类未来销量/备货 → sales_forecast（先用 prediction_categories 确认品类名）\n"
                     "- 问选品/推荐 → selection_summary + selection_products\n"
                     "- 问定价/调价/弹性 → pricing_summary + pricing_suggestions\n"
                     "- 问为什么没给建议价 → pricing_skipped\n"
                     "- 问模型准不准/比基线好吗 → experiment_median\n"
                     "- 问用户分层 → rfm_segments；问漏斗 → conversion_funnel\n"
                     "同一轮可以调用多个工具；工具失败时如实说明，不要改用估算。")
    elif mode == "no_tools":
        parts.append("【注意】本次未提供工具，你无法获得真实数字。"
                     "请只讲口径与方法论，并明确告诉用户「需要查询数据才能给出数值」。")

    return "\n\n".join(parts)


def user_message(question: str) -> dict:
    return {"role": "user", "content": question}


def messages(question: str, mode: str = "full",
             rules: list[dict] | None = None,
             snippets: list[dict] | None = None,
             history: list[dict] | None = None) -> list[dict]:
    """组装消息列表。history 插在 system 之后、当前问题之前。

    只保留 user/assistant 的纯文本消息（剔除 tool 调用帧，避免超长），
    最多带最近 6 轮，足够支撑「再按月份拆」「那第二名呢」这类追问。
    """
    msgs = [{"role": "system",
             "content": system_prompt(question, mode, rules, snippets)}]
    if history:
        for h in history[-12:]:                     # 最多最近 6 轮（一问一答）
            role = h.get("role")
            text = h.get("content")
            if role in ("user", "assistant") and isinstance(text, str) and text.strip():
                msgs.append({"role": role, "content": text.strip()[:1500]})
    msgs.append(user_message(question))
    return msgs
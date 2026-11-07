# -*- coding: utf-8 -*-
"""Agent 编排：把「护栏 → 口径 → 检索 → 工具 → 回答」串起来。

两种执行路径
------------
LLM 路径（有 API Key）：ReAct 循环，最多 MAX_STEPS 轮，模型自己决定调哪些工具；
offline 路径（无 Key） ：确定性规则引擎，按意图调同一批工具。

两条路径共享同一份规则库、同一批工具、同一个输出结构，
所以在评测里可以公平对比（差别只在"语言组织"这一层）。
"""
from __future__ import annotations

import json
import time
from typing import Any

from llm import config
from llm.agent import composer, guard, prompts
from llm.knowledge import hard_rules, retriever
from llm.providers import ProviderError, get_provider
from llm.tools import executor, registry


def _norm_mode(mode: str | None) -> str:
    m = (mode or config.DEFAULT_MODE).lower()
    return m if m in config.MODES else "full"


# ---------------------------------------------------------------
# 工具调用
# ---------------------------------------------------------------
def _call_tool(name: str, args: dict) -> dict:
    return executor.execute(name, args or {}, max_items=8)


def _citation_from(tool: str, res: dict) -> list[dict]:
    """从工具结果里抠出可引用的关键数值（给前端"数据依据"用）。"""
    if not res.get("ok"):
        return []
    d = res.get("data")
    out: list[dict] = []
    if not isinstance(d, dict):
        return out
    picks = [
        ("gmv", "GMV"), ("avg_order_value", "客单价"), ("avg_per_customer", "人均消费"),
        ("repurchase_rate", "复购率"), ("order_cnt", "订单数"), ("customer_cnt", "用户数"),
        ("total", "总数"), ("has_suggestion", "有建议价数"), ("no_suggestion", "样本不足数"),
        ("cut_cnt", "建议降价数"), ("raise_cnt", "建议提价数"),
        ("mape_model_pct", "MAPE(主模型)"), ("mape_baseline_pct", "MAPE(基线)"),
        ("wape_model_pct", "WAPE(主模型)"), ("history_weeks", "历史周数"),
    ]
    for k, label in picks:
        if k in d and d[k] is not None:
            out.append({"指标": label, "值": d[k], "来源": tool})
    if "median" in d and isinstance(d["median"], dict):
        for k, v in d["median"].items():
            out.append({"指标": k, "值": v, "来源": tool})
    if "main_model_better_categories" in d and isinstance(d["main_model_better_categories"], dict):
        b = d["main_model_better_categories"]
        out.append({"指标": "优于基线品类数", "值": f"{b.get('better')}/{b.get('total')}",
                    "来源": tool})
    if "future" in d and isinstance(d["future"], list) and d["future"]:
        out.append({"指标": "未来首周预测", "值": d["future"][0].get("forecast"),
                    "来源": tool})
    if "confidence" in d and isinstance(d["confidence"], dict):
        out.append({"指标": "置信度分布", "值": json.dumps(d["confidence"], ensure_ascii=False),
                    "来源": tool})
    return out[:8]


# ---------------------------------------------------------------
# LLM 路径
# ---------------------------------------------------------------
def _run_llm(question: str, mode: str, rules: list[dict],
             snippets: list[dict]) -> dict:
    provider = get_provider()
    msgs = prompts.messages(question, mode, rules, snippets)
    use_tools = mode in ("full", "no_rag")
    schemas = registry.schema_for_llm() if use_tools else None

    trace: list[dict] = []
    tools_used: list[str] = []
    citations: list[dict] = []
    content: str | None = None
    t0 = time.time()

    for step in range(config.MAX_STEPS):
        resp = provider.chat(msgs, tools=schemas)
        calls = resp.get("tool_calls") or []
        if not calls:
            content = resp.get("content")
            trace.append({"step": step + 1, "action": "final", "content_chars": len(content or "")})
            break

        # 把助手的 tool_calls 原样回填，保持对话协议完整
        msgs.append(resp.get("raw_message") or {
            "role": "assistant", "content": resp.get("content"),
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["raw_arguments"]}}
                           for c in calls],
        })
        for c in calls:
            name = c.get("name", "")
            args = c.get("arguments") or {}
            res = _call_tool(name, args)
            tools_used.append(name)
            citations.extend(_citation_from(name, res))
            trace.append({"step": step + 1, "action": "tool", "tool": name,
                          "args": args, "ok": res.get("ok"),
                          "error": res.get("error"),
                          "preview": _preview(res)})
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""),
                         "content": json.dumps(res, ensure_ascii=False, default=str)[:4000]})

    if not content:
        # 模型没给出终稿（或步数用尽）→ 用确定性组装兜底，保证不空手
        fb = composer.compose(question, mode, rules, snippets)
        fb["provider"] = provider.name
        fb["model"] = provider.model
        fb["llm_fallback"] = True
        fb["trace"] = trace
        fb["elapsed_ms"] = int((time.time() - t0) * 1000)
        return fb

    return {
        "question": question,
        "answer": content,
        "mode": mode,
        "provider": provider.name,
        "model": provider.model,
        "conclusion": _first_sentence(content),
        "citations": citations[:10],
        "tools_used": sorted(set(tools_used)),
        "rules_applied": [{"id": r["id"], "topic": r["topic"]} for r in rules],
        "snippets": [{"source": s["source"], "heading": s["heading"],
                      "score": s.get("score")} for s in snippets],
        "confidence": "高" if tools_used else "中",
        "limitations": [],
        "refused": False,
        "trace": trace,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "datasource": executor.datasource_mode(),
    }


def _preview(res: dict) -> str:
    s = json.dumps(res.get("data") if res.get("ok") else res.get("error"),
                   ensure_ascii=False, default=str)
    return s[:220]


def _first_sentence(text: str) -> str:
    t = (text or "").strip().replace("\n", " ")
    for sep in ("。", ". ", "！"):
        if sep in t:
            return t.split(sep)[0][:160]
    return t[:160]


# ---------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------
def run(question: str, mode: str | None = None) -> dict:
    """回答一个问题。永不抛异常，失败也返回可读结果。"""
    question = (question or "").strip()
    mode = _norm_mode(mode)
    t0 = time.time()

    if not question:
        return {"question": "", "answer": "请先输入问题。", "mode": mode,
                "provider": "none", "model": "", "conclusion": "",
                "citations": [], "tools_used": [], "rules_applied": [],
                "snippets": [], "confidence": "低", "limitations": [],
                "refused": False, "trace": [], "elapsed_ms": 0}

    # baseline：裸底座（用于对照实验）
    if mode == "baseline":
        r = composer.compose_baseline(question)
        r["elapsed_ms"] = int((time.time() - t0) * 1000)
        return r

    rules = hard_rules.match(question, top_k=4)
    own = guard.is_refusal_needed(question)
    snippets = [] if mode == "no_rag" else retriever.retrieve(question)

    # 有底座 → LLM 路径；否则 offline
    if get_provider() is not None:
        try:
            r = _run_llm(question, mode, rules, snippets)
            r["elapsed_ms"] = int((time.time() - t0) * 1000)
            return r
        except ProviderError as e:
            r = composer.compose(question, mode, rules, snippets)
            r["provider"] = "offline"
            r["llm_error"] = str(e)[:300]
            r["limitations"] = list(r.get("limitations") or []) + [f"底座调用失败，已降级：{e}"]
            r["elapsed_ms"] = int((time.time() - t0) * 1000)
            return r

    r = composer.compose(question, mode, rules, snippets)
    r["elapsed_ms"] = int((time.time() - t0) * 1000)
    return r


def health() -> dict:
    """给 /api/llm/health 用：各层是否就绪。"""
    from llm import config as cfg
    rs = retriever.stats()
    return {
        "config": cfg.describe(),
        "knowledge": {"rules": len(hard_rules.all_rules()),
                      "always_rules": len(hard_rules.always_rules()),
                      "rag": rs},
        "tools": executor.health(),
        "guard": {"out_of_scope_rules": len(guard.OUT_OF_SCOPE),
                  "sql_whitelist_views": len(guard.ALLOWED_VIEWS)},
    }
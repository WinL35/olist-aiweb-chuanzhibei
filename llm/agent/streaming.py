# -*- coding: utf-8 -*-
"""SSE 流式对话编排

为什么不直接复用 planner.run()
--------------------------------
run() 是「一次性返回」，内部的护栏、口径匹配、检索、工具调用对外全不可见，
用户只能盯着转圈等 5~7 秒。要做到「边算边说」，必须在编排层留出事件出口。

这里独立实现一条流式链路，**复用同一批工具、同一份口径库、同一个护栏**，
输出结构与 run() 完全一致，因此不影响既有评测结果（评测仍走 run()）。

事件协议（SSE）
--------------
    stage   阶段开始：guard → rules → retrieve → tool → compose
    step    一次真实的工具调用，带工具名、参数、成功与否、真实耗时
    delta   回答正文增量（按句切块）
    result  完整结构化结果，前端据此渲染图表 / 引用 / 轨迹
    error   失败

关于「这是不是真正的 token 流式」
--------------------------------
不是。ReAct 的约束决定了：只有全部工具返回后，模型才可能生成终稿，
因此终稿天然不可能早于工具阶段。这里选择**真实地推送过程进度，
再让终稿按句落屏**，而不是伪造一个匀速打字机——
前者能让用户在第 200ms 就看到「正在查价格弹性」，
后者只是把等待藏起来而已。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator

from llm import config
from llm.agent import composer, guard, planner, prompts
from llm.knowledge import hard_rules, retriever
from llm.providers import ProviderError, get_provider
from llm.tools import executor, registry

# 按中文句末标点切块；过长的句子再按字数二次切分，避免整段一次涌出
_SENT_RE = re.compile(r"[^。！？；\n]*[。！？；\n]|[^。！？；\n]+$")


def _split_chunks(text: str, max_len: int = 42) -> list[str]:
    """把终稿切成适合逐句落屏的块。"""
    text = text or ""
    if not text:
        return []
    parts: list[str] = []
    for seg in _SENT_RE.findall(text):
        if not seg:
            continue
        while len(seg) > max_len:
            parts.append(seg[:max_len])
            seg = seg[max_len:]
        if seg:
            parts.append(seg)
    return parts


def _ev(event: str, **kw: Any) -> dict:
    return {"event": event, **kw}


def events(question: str, mode: str | None = None,
           history: list[dict] | None = None) -> Iterator[dict]:
    """流式回答一个问题的全过程。永不抛异常，失败也给出可读事件。"""
    question = (question or "").strip()
    try:
        mode_n = planner._norm_mode(mode)
    except Exception:
        mode_n = "full"

    t0 = time.time()
    executor.begin_turn()

    if not question:
        yield _ev("error", message="问题不能为空")
        return

    # ---- 对照组：裸底座，不经过任何编排 ----
    if mode_n == "baseline":
        yield _ev("stage", stage="baseline", label="裸底座直答（对照组）")
        r = composer.compose_baseline(question)
        r["elapsed_ms"] = int((time.time() - t0) * 1000)
        for chunk in _split_chunks(r.get("answer", "")):
            yield _ev("delta", text=chunk)
            time.sleep(0.012)
        yield _ev("result", data=r)
        return

    # ---- 阶段 1：护栏 ----
    yield _ev("stage", stage="guard", label="护栏检查")
    refusal = guard.is_refusal_needed(question)
    if refusal:
        # 命中拒答规则：直接给出「为什么不做」，不需要检索与工具
        r = composer.compose(question, mode_n, [], [])
        r["elapsed_ms"] = int((time.time() - t0) * 1000)
        for chunk in _split_chunks(r.get("answer", "")):
            yield _ev("delta", text=chunk)
            time.sleep(0.012)
        yield _ev("result", data=r)
        return

    # ---- 阶段 2：口径匹配 ----
    yield _ev("stage", stage="rules", label="匹配行业口径")
    rules = hard_rules.match(question, top_k=4)
    yield _ev("stage", stage="rules", label=f"命中 {len(rules)} 条口径", done=True,
              detail=[{"id": r["id"], "topic": r["topic"]} for r in rules])

    # ---- 阶段 3：检索 ----
    if mode_n == "no_rag":
        snippets: list[dict] = []
        yield _ev("stage", stage="retrieve", label="已关闭检索（no_rag 对照）", done=True, count=0)
    else:
        yield _ev("stage", stage="retrieve", label="检索知识库")
        snippets = retriever.retrieve(question)
        yield _ev("stage", stage="retrieve", label=f"召回 {len(snippets)} 段文档", done=True,
                  count=len(snippets))

    provider = get_provider()

    # ---- 没有底座：确定性规则引擎 ----
    if provider is None:
        yield _ev("stage", stage="compose", label="离线规则引擎组装回答")
        r = composer.compose(question, mode_n, rules, snippets)
        r["elapsed_ms"] = int((time.time() - t0) * 1000)
        for chunk in _split_chunks(r.get("answer", "")):
            yield _ev("delta", text=chunk)
            time.sleep(0.012)
        yield _ev("result", data=r)
        return

    # ---- 有底座：ReAct 循环，逐步推送 ----
    msgs = prompts.messages(question, mode_n, rules, snippets, history=history)
    use_tools = mode_n in ("full", "no_rag")
    schemas = registry.schema_for_llm() if use_tools else None

    trace: list[dict] = []
    tools_used: list[str] = []
    citations: list[dict] = []
    charts: list[dict] = []
    content: str | None = None

    try:
        for step in range(config.MAX_STEPS):
            resp = provider.chat(msgs, tools=schemas)
            calls = resp.get("tool_calls") or []

            if not calls:
                content = resp.get("content")
                trace.append({"step": step + 1, "action": "final",
                              "content_chars": len(content or "")})
                break

            # 助手消息原样回填，保持 tool_calls 协议完整
            msgs.append(resp.get("raw_message") or {
                "role": "assistant", "content": resp.get("content"),
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": c["raw_arguments"]}}
                               for c in calls],
            })

            for c in calls:
                name = c.get("name", "")
                args = c.get("arguments") or {}
                yield _ev("stage", stage="tool", label=f"调用 {name}",
                          tool=name, args=args)

                t_tool = time.time()
                res = planner._call_tool(name, args)
                tool_ms = int((time.time() - t_tool) * 1000)

                tools_used.append(name)
                citations.extend(planner._citation_from(name, res))
                if res.get("ok"):
                    data = res.get("data")
                    chart = data.get("chart") if isinstance(data, dict) else None
                    if isinstance(chart, dict):
                        charts.append(chart)

                tr = {"step": step + 1, "action": "tool", "tool": name, "args": args,
                      "ok": res.get("ok"), "error": res.get("error"),
                      "preview": planner._preview(res)}
                trace.append(tr)

                yield _ev("step", step=step + 1, tool=name, args=args,
                          ok=bool(res.get("ok")), error=res.get("error"),
                          elapsed_ms=tool_ms, preview=planner._preview(res))

                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""),
                             "content": json.dumps(res, ensure_ascii=False, default=str)[:4000]})
    except ProviderError as e:
        yield _ev("stage", stage="fallback", label=f"底座调用失败，降级为离线引擎：{e}")
        r = composer.compose(question, mode_n, rules, snippets)
        r["provider"] = "offline"
        r["llm_error"] = str(e)[:300]
        r["limitations"] = list(r.get("limitations") or []) + [f"底座调用失败，已降级：{e}"]
        r["charts"] = charts
        r["trace"] = trace
        r["elapsed_ms"] = int((time.time() - t0) * 1000)
        for chunk in _split_chunks(r.get("answer", "")):
            yield _ev("delta", text=chunk)
            time.sleep(0.012)
        yield _ev("result", data=r)
        return

    # ---- 收尾：组装结构化结果，并把正文逐句推送 ----
    yield _ev("stage", stage="compose", label="生成回答")

    if not content:
        fb = composer.compose(question, mode_n, rules, snippets)
        fb["provider"] = provider.name
        fb["model"] = provider.model
        fb["llm_fallback"] = True
        fb["charts"] = charts
        fb["trace"] = trace
        fb["elapsed_ms"] = int((time.time() - t0) * 1000)
        final = fb
    else:
        final = {
            "question": question,
            "answer": content,
            "mode": mode_n,
            "provider": provider.name,
            "model": provider.model,
            "conclusion": planner._first_sentence(content),
            "citations": citations[:10],
            "charts": charts,
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

    for chunk in _split_chunks(final.get("answer", "")):
        yield _ev("delta", text=chunk)
        time.sleep(0.012)

    yield _ev("result", data=final)


def sse(question: str, mode: str | None = None,
        history: list[dict] | None = None) -> Iterator[str]:
    """把事件序列编码成 SSE 文本流。"""
    try:
        for ev in events(question, mode, history=history):
            name = ev.get("event", "message")
            payload = {k: v for k, v in ev.items() if k != "event"}
            yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
    except Exception as e:  # 兜底：任何未捕获异常都要让前端收到可读原因
        payload = {"message": f"{type(e).__name__}: {e}"}
        yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

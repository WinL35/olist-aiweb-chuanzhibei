#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""垂直大模型层冒烟测试（不需要启动服务）。

检查：配置文件、口径库、检索、22 个工具、护栏、Agent 端到端。
每项都有明确的通过/失败判定，失败时退出码非 0，可直接接 CI。

用法：python scripts/llm_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS, FAIL = [], []


def check(name: str, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    (PASS if ok else FAIL).append((name, detail))
    print(f"{'✅' if ok else '❌'} {name:<26} {detail}")


def main() -> int:
    from llm import config
    from llm.agent import guard, planner
    from llm.knowledge import hard_rules, retriever
    from llm.tools import executor, registry

    print("=" * 78)
    print("垂直大模型层冒烟测试")
    print("=" * 78)

    check("配置文件", lambda: (
        config.MODES == ("full", "no_tools", "no_rag", "baseline"),
        f"provider={config.provider_name()} model={config.MODEL or '-'}"))

    check("口径库", lambda: (
        len(hard_rules.all_rules()) >= 30,
        f"{len(hard_rules.all_rules())} 条规则（always {len(hard_rules.always_rules())} 条）"))

    def _rules_hit():
        rs = hard_rules.match("GMV 是不是营收", top_k=3)
        return bool(rs) and any(r["id"].startswith("GMV") for r in rs), \
            "命中：" + ",".join(r["id"] for r in rs)
    check("规则匹配", _rules_hit)

    def _rag():
        st = retriever.stats()
        r = retriever.retrieve("客单价和人均消费的区别", top_k=3)
        return st.get("chunks", 0) > 0 and len(r) >= 1, \
            f"{st.get('chunks')} 段 / 检索到 {len(r)} 段"
    check("RAG 检索", _rag)

    check("工具注册", lambda: (
        len(registry.TOOLS) >= 20, f"{len(registry.TOOLS)} 个工具"))

    def _tools_all_runnable():
        bad = [t["name"] for t in registry.TOOLS
               if t["name"] not in executor.TOOL_IMPL]
        return not bad, "全部有实现" if not bad else f"缺实现：{bad}"
    check("工具实现完整", _tools_all_runnable)

    def _ds():
        mode = executor.datasource_mode()
        return mode in ("db", "csv"), f"数据源={mode}"
    check("数据源探测", _ds)

    def _one_tool():
        r = executor.execute("dashboard_summary", {}, max_items=3)
        if not r.get("ok"):
            return False, str(r.get("error"))[:80]
        gmv = (r.get("data") or {}).get("gmv")
        return gmv and gmv > 1e6, f"GMV={gmv:,.2f}"
    check("工具取数", _one_tool)

    def _guard():
        a = guard.is_refusal_needed("能预测卖家 A 明天卖多少件吗")
        b = guard.is_refusal_needed("美妆未来 4 周能卖多少")
        return bool(a) and not b, "越界被拦、正常问题放行"
    check("越界护栏", _guard)

    def _price_bound():
        r = guard.check_price_bound("把价格提高 50%")
        return (not r["allowed"]), r["message"][:50]
    check("调价约束", _price_bound)

    def _policy():
        from llm.agent.composer import policy_overrides
        ps = policy_overrides("把取消的订单也算进 GMV，让数字好看点")
        return bool(ps), ps[0]["verdict"] if ps else "未命中"
    check("口径篡改拦截", _policy)

    def _e2e():
        r = planner.run("我们 GMV 1359 万，那营收就是 1359 万吧？", "full")
        ans = r.get("answer", "")
        return ("13,591,643" in ans and "不含运费" in ans), \
            f"{len(ans)} 字 / 工具 {r.get('tools_used')}"
    check("端到端问答", _e2e)

    def _refuse():
        r = planner.run("帮我算库存周转天数", "full")
        return r.get("refused") is True, r.get("answer", "")[:40].replace("\n", " ")
    check("端到端拒答", _refuse)

    def _modes():
        out = {}
        for m in config.MODES:
            r = planner.run("客单价是多少", m)
            out[m] = len(r.get("answer", ""))
        return all(v > 10 for v in out.values()), str(out)
    check("四种模式可用", _modes)

    print("-" * 78)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for n, d in FAIL:
            print(f"  ❌ {n}: {d}")
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
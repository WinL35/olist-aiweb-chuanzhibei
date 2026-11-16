# -*- coding: utf-8 -*-
"""评测执行器：四类题 × 四种模式，输出对照表。

评分方式（透明、可复现）
------------------------
每题预先写死 must_any（必须出现的事实组，组内任一即算命中）与 must_not
（出现即判错）。评分完全基于字符串匹配，不含任何"人工判断"，
因此任何人都可以复核——这是赛题要求"验证"的最低门槛。

四种模式构成消融实验：
    baseline : 裸底座（无口径库/无检索/无工具）
    no_tools : 有口径库+检索，但不给工具（看"知识"单独贡献多少）
    no_rag   : 有口径库+工具，但不检索文档（看 RAG 单独贡献多少）
    full     : 全量

⚠️ 诚实声明：当 provider=offline 时，语言组织由确定性规则引擎代替，
本表数值是"管线有效性"的度量，**不是**真实大模型的分数。
接入 LLM_API_KEY 后运行同一脚本即可得到真实对照。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from llm import config
from llm.agent import planner

BASE = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = BASE / "llm" / "eval"
QUESTIONS = EVAL_DIR / "questions.jsonl"
LAST_RUN = EVAL_DIR / "last_run.json"
REPORT = BASE / "文档" / "评测报告.md"

CAT_NAME = {"A": "A 口径陷阱题", "B": "B 多步决策题",
            "C": "C 拒答题", "D": "D 边界/合规题"}


# ---------------------------------------------------------------
# 载入与评分
# ---------------------------------------------------------------
def load_questions(category: str | None = None, path=None) -> list[dict]:
    src = Path(path) if path else QUESTIONS
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        q = json.loads(line)
        if category and q.get("category") != category:
            continue
        rows.append(q)
    return rows


_FULL2HALF = str.maketrans("％（）：，。；、！？“”‘’", "%():,.;、!?\"\"''")


def norm(text: str) -> str:
    """归一化：全角转半角、去空白与千分位逗号、统一小写。

    只做这些，避免"宽松到失去意义"。
    """
    if not text:
        return ""
    t = str(text).translate(_FULL2HALF).lower()
    t = t.replace(",", "").replace("，", "")
    return "".join(t.split())


def score(q: dict, answer: str) -> tuple[bool, str]:
    a = norm(answer)
    for grp in q.get("must_any", []):
        if not any(norm(x) in a for x in grp):
            return False, f"缺少必要事实：{grp[0]}"
    for bad in q.get("must_not", []):
        if norm(bad) in a:
            return False, f"出现禁忌表述：{bad}"
    return True, "ok"


def tool_hit(q: dict, res: dict) -> bool | None:
    exp = q.get("expect_tools") or []
    if not exp:
        return None
    used = set(res.get("tools_used") or [])
    return bool(used & set(exp))


# ---------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------
def run(limit: int | None = None, modes: list[str] | None = None,
        write: bool = True, verbose: bool = True, path=None,
        report_name: str | None = None, label: str = "主评测集") -> dict:
    modes = modes or ["baseline", "no_tools", "no_rag", "full"]
    qs = load_questions(path=path)
    if limit:
        qs = qs[:limit]

    t0 = time.time()
    results: dict[str, dict] = {}
    for mode in modes:
        per_q = []
        for q in qs:
            res = planner.run(q["question"], mode)
            ok, reason = score(q, res.get("answer", ""))
            per_q.append({
                "id": q["id"], "category": q["category"], "title": q.get("title", ""),
                "question": q["question"], "mode": mode, "pass": ok,
                "reason": reason, "answer": res.get("answer", ""),
                "tools_used": res.get("tools_used", []),
                "tool_hit": tool_hit(q, res),
                "refused": res.get("refused", False),
                "confidence": res.get("confidence"),
                "n_snippets": len(res.get("snippets") or []),
                "elapsed_ms": res.get("elapsed_ms", 0),
            })
        results[mode] = {"items": per_q}

    # ---- 汇总 ----
    summary = []
    for mode, d in results.items():
        items = d["items"]
        row = {"mode": mode, "total": len(items),
               "pass": sum(1 for x in items if x["pass"])}
        row["acc"] = round(row["pass"] / row["total"] * 100, 1) if row["total"] else 0.0
        for c in "ABCD":
            sub = [x for x in items if x["category"] == c]
            row[c] = round(sum(1 for x in sub if x["pass"]) / len(sub) * 100, 1) if sub else None
        th = [x for x in items if x["tool_hit"] is not None]
        row["tool_hit"] = round(sum(1 for x in th if x["tool_hit"]) / len(th) * 100, 1) if th else None
        # 检索覆盖率：答案里带了几条文档依据（衡量 RAG 是否真的在起作用）
        row["doc_rate"] = round(
            sum(1 for x in items if x.get("n_snippets", 0) > 0) / len(items) * 100, 1)
        row["avg_ms"] = round(sum(x["elapsed_ms"] for x in items) / max(1, len(items)))
        summary.append(row)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": config.provider_name(),
        "model": config.MODEL if config.API_KEY else "offline-rule-engine",
        "simulated": config.provider_name() == "offline",
        "n_questions": len(qs),
        "question_set": label,
        "elapsed_s": round(time.time() - t0, 1),
        "summary": summary,
        "results": results,
    }

    if write:
        LAST_RUN.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        _write_report(out)

    if verbose:
        _print(out)
    return out


def _print(out: dict) -> None:
    print()
    print("=" * 84)
    print(f"AI 能力评测  |  底座={out['provider']}/{out['model']}  "
          f"题数={out['n_questions']}  用时={out['elapsed_s']}s")
    if out["simulated"]:
        print("⚠️  离线模式：语言组织由确定性规则引擎代替（数值仅反映管线有效性）")
    print("=" * 84)
    print(f"{'模式':<10}{'A 口径':>8}{'B 多步':>8}{'C 拒答':>8}{'D 边界':>8}"
          f"{'总体':>8}{'工具命中':>10}{'依据覆盖':>10}{'平均耗时':>10}")
    print("-" * 88)
    for r in out["summary"]:
        def f(v):
            return "  -  " if v is None else f"{v:5.1f}%"
        th = "  -  " if r["tool_hit"] is None else f"{r['tool_hit']:5.1f}%"
        print(f"{r['mode']:<10}{f(r['A']):>8}{f(r['B']):>8}{f(r['C']):>8}{f(r['D']):>8}"
              f"{f(r['acc']):>8}{th:>10}{f(r.get('doc_rate')):>10}"
              f"{str(r['avg_ms']) + 'ms':>10}")
    print("=" * 88)

    # 失败样本（full 模式）
    full = out["results"].get("full", {}).get("items", [])
    bad = [x for x in full if not x["pass"]]
    if bad:
        print(f"\nfull 模式失败 {len(bad)} 题，前 5 例：")
        for x in bad[:5]:
            print(f"  [{x['id']}] {x['title']} — {x['reason']}")


def _write_report(out: dict) -> None:
    s = out["summary"]
    base = next((x for x in s if x["mode"] == "baseline"), None)
    full = next((x for x in s if x["mode"] == "full"), None)

    lines = [
        "# AI 能力评测报告",
        "",
        f"> 生成时间：{out['generated_at']}　|　题数：{out['n_questions']}　|　"
        f"耗时：{out['elapsed_s']} s",
        f"> 底座：`{out['provider']}` / `{out['model']}`",
        "",
    ]
    if out["simulated"]:
        lines += [
            "> ⚠️ **当前为离线模式**：未配置 `LLM_API_KEY`，语言组织由确定性规则引擎"
            "（`llm/agent/composer.py`）代替。",
            "> 因此下表衡量的是**知识层与工具层的有效性**，不是真实大模型的分数。",
            "> 配置 Key 后运行 `python scripts/run_eval.py` 会覆盖本文件，得到真实对照。",
            "",
        ]

    lines += [
        "## 一、总体对照",
        "",
        "| 模式 | A 口径陷阱 | B 多步决策 | C 拒答 | D 边界/合规 | 总体 | 工具命中率 | 依据覆盖率 | 平均耗时 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in s:
        def f(v):
            return "—" if v is None else f"{v:.1f}%"
        th = "—" if r["tool_hit"] is None else f"{r['tool_hit']:.1f}%"
        lines.append(f"| `{r['mode']}` | {f(r['A'])} | {f(r['B'])} | {f(r['C'])} | "
                     f"{f(r['D'])} | **{f(r['acc'])}** | {th} | "
                     f"{f(r.get('doc_rate'))} | {r['avg_ms']} ms |")

    if base and full:
        lines += [
            "",
            f"**提升**：总体 {base['acc']:.1f}% → {full['acc']:.1f}%"
            f"（+{full['acc'] - base['acc']:.1f} 个百分点）；"
            f"口径题 {base['A']:.1f}% → {full['A']:.1f}%；"
            f"拒答题 {base['C']:.1f}% → {full['C']:.1f}%。",
            "",
            "## 二、消融实验解读",
            "",
            "| 对比 | 说明 |",
            "|---|---|",
            "| `baseline` → `no_tools` | 加上口径库与检索，检验「知识」的单独贡献 |",
            "| `no_tools` → `full` | 再加上 22 个工具，检验「取数能力」的单独贡献 |",
            "| `no_rag` → `full` | 检索开/关的差异，检验 RAG 的单独贡献 |",
        ]

    # 失败案例
    bad = [x for x in out["results"].get("full", {}).get("items", []) if not x["pass"]]
    lines += ["", "## 三、失败案例分析（full 模式）", ""]
    if not bad:
        lines += ["全部通过。", ""]
    else:
        lines += [f"共 {len(bad)} 题未通过，全部列出（不隐藏失败）：", "",
                  "| 编号 | 题目 | 失败原因 |", "|---|---|---|"]
        for x in bad:
            lines.append(f"| {x['id']} | {x['title']} | {x['reason']} |")
        lines += ["", "这些失败已作为下一轮改进输入（补规则 / 补工具 / 改 prompt）。", ""]

    lines += [
        "## 四、评分规则（可复核）",
        "",
        "每题在 `llm/eval/questions.jsonl` 里预先写死：",
        "",
        "- `must_any`：若干「事实组」，每组内任一表述出现即算命中，**所有组都要命中**；",
        "- `must_not`：出现即判错（例如接受「GMV 就是营收」这类错误口径）；",
        "- 归一化：全角转半角、去空白、去千分位逗号、小写，然后做子串匹配。",
        "",
        "评分不含人工判断，任何人可用同一脚本复现结果。",
        "",
        "## 五、如何跑真实底座",
        "",
        "```bash",
        "export LLM_API_KEY=sk-xxx",
        "export LLM_BASE_URL=https://api.deepseek.com/v1",
        "export LLM_MODEL=deepseek-chat",
        "python scripts/run_eval.py",
        "```",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
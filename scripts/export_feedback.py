#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把待审反馈导出成 JSONL，并给出「下一步该改什么」的提示。

用法：
    python scripts/export_feedback.py             # 导出待审 → llm/eval/feedback_review.jsonl
    python scripts/export_feedback.py --all       # 含已审
    python scripts/export_feedback.py --mark 1,2  # 把 1、2 号标记为已处理

流程（与方案书「持续学习」一节一致）：
    1. 对话页点 👎 / 写纠正 → llm/feedback/feedback.db
    2. 本脚本导出 → 人工判定归入「口径规则 / 意图路由 / 文档片段 / 新评测题」
    3. 改完规则跑 scripts/run_eval.py --gate，任一维度掉超过 2 个百分点就回滚
    4. 第三套 holdout 验收，不拿盲测调参
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm import feedback  # noqa: E402

OUT = ROOT / "llm" / "eval" / "feedback_review.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="导出全部（含已审）")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--mark", default="", help="把指定 id 标记为已处理，逗号分隔")
    a = ap.parse_args()

    st = feedback.stats()
    print(f"反馈库：共 {st['total']} 条（👍 {st['up']} / 👎 {st['down']}，待审 {st['pending']}）")
    for m in st["by_mode"]:
        print(f"  · 模式 {m['mode']}: {m['n']} 条")

    out = Path(a.out)
    n = feedback.export(out, only_pending=not a.all)
    print(f"已导出 {n} 条 → {out.relative_to(ROOT)}")

    if n:
        # 粗分类：带「应为/应该是/不对」的多半是口径问题；带「没听懂/答非所问」的是路由问题
        rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
        hint = {"口径": 0, "路由": 0, "其他": 0}
        for r in rows:
            c = (r.get("correction") or "") + (r.get("question") or "")
            if any(k in c for k in ("应为", "应该是", "不对", "口径", "不是")):
                hint["口径"] += 1
            elif any(k in c for k in ("没听懂", "答非所问", "答错", "理解错")):
                hint["路由"] += 1
            else:
                hint["其他"] += 1
        print(f"粗分类：口径 {hint['口径']} / 路由 {hint['路由']} / 其他 {hint['其他']}")
        print("下一步：人工判定后改规则或补评测题，再跑 run_eval.py --gate")

    if a.mark:
        ids = [int(x) for x in a.mark.split(",") if x.strip().isdigit()]
        print(f"已标记 {feedback.mark_reviewed(ids)} 条为已处理")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
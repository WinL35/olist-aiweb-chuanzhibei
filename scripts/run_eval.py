#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑全量评测并生成 文档/评测报告.md。

用法：
    python scripts/run_eval.py                # 主评测集 60 题 × 4 模式
    python scripts/run_eval.py --blind        # 盲测集 20 题（只跑 full）
    python scripts/run_eval.py --limit 10     # 快速试跑
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.eval import runner  # noqa: E402

GATE = ROOT / "llm" / "eval" / "gate_baseline.json"
GATE_TOL = 2.0   # 任一维度下降超过 2 个百分点即拦截


def _compare(out: dict) -> list[str]:
    """与上一次基线逐维度比对，返回超阈值的说明（空列表=通过）。"""
    if not GATE.is_file():
        GATE.write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                                    "summary": out.get("summary", [])},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        return [f"未找到基线，已用本次结果建立基线：{GATE.name}"]
    prev = {r["mode"]: r for r in json.loads(GATE.read_text(encoding="utf-8"))["summary"]}
    bad = []
    for r in out.get("summary", []):
        p = prev.get(r["mode"])
        if not p:
            continue
        for k, name in (("acc", "总体"), ("A", "口径"), ("B", "多步"),
                        ("C", "拒答"), ("D", "边界")):
            drop = round(p.get(k, 0) - r.get(k, 0), 1)
            if drop > GATE_TOL:
                bad.append(f"{r['mode']} {name}：{p.get(k)}% → {r.get(k)}%（-{drop}pt）")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", action="store_true", help="跑盲测集")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--modes", default=None, help="逗号分隔，如 baseline,full")
    ap.add_argument("--no-write", action="store_true", help="不覆盖报告")
    ap.add_argument("--gate", action="store_true", help="与基线比对，任一维度下降 >2pt 则退出码 1")
    ap.add_argument("--update-gate", action="store_true", help="把本次结果设为新基线")
    a = ap.parse_args()

    if a.blind:
        out = runner.run(path=ROOT / "llm" / "eval" / "questions_blind.jsonl",
                         modes=(a.modes.split(",") if a.modes else ["full"]),
                         limit=a.limit, write=not a.no_write, label="盲测集")
    else:
        out = runner.run(limit=a.limit,
                         modes=(a.modes.split(",") if a.modes else None),
                         write=not a.no_write, label="主评测集")

    if out.get("simulated"):
        print("\n提示：当前是离线模式，报告里已标注。配置 LLM_API_KEY 后重跑即为真实底座结果。")
    print(f"\n报告：{ROOT / '文档' / '评测报告.md'}")

    if a.update_gate and not a.blind:
        GATE.write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                                    "summary": out.get("summary", [])},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已更新回归基线：{GATE.name}")

    if a.gate and not a.blind:
        bad = _compare(out)
        if len(bad) == 1 and bad[0].startswith("未找到基线"):
            print("\n回归门槛：✅ 首次运行，已建立基线（下一次起生效）")
            return 0
        if bad:
            print("\n回归门槛：❌ 未通过")
            for b in bad:
                print("  ·", b)
            return 1
        print("\n回归门槛：✅ 通过（各维度较基线下降均 ≤ 2pt）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
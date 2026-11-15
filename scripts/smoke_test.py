#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口连通性与响应时间冒烟测试。

前置条件：后端已启动（默认 http://127.0.0.1:8000）。
检查内容：
  1. /api/health           —— MySQL 主库与算法库都真的连上了（不是"服务起来了"就算过）
  2. 8 个核心业务接口       —— HTTP 200 且返回体非空
  3. 单次响应时间           —— 每个接口 < 2 秒
  4. /api/llm/health       —— 工具 / 口径规则 / RAG 三件套就绪

任一失败 → 退出码 1，可直接接 CI。不做任何"重试到通过"的粉饰。

用法：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Windows 控制台默认可能是 GBK，中文会抛 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PASS, FAIL = [], []
SLOW_LIMIT = 2.0  # 秒

# 8 个核心业务接口，与前端 8 个页面一一对应
CORE_ENDPOINTS = [
    ("经营看板", "/api/dashboard/summary"),
    ("RFM 用户分群", "/api/rfm/segments"),
    ("转化漏斗", "/api/conversion/funnel"),
    ("销量预测", "/api/prediction/sales"),
    ("选品建议", "/api/recommendation/products"),
    ("定价建议", "/api/pricing/suggestions"),
    ("模型实验", "/api/experiment/summary-stats"),
    ("品类分布", "/api/dashboard/category"),
]


def check(name: str, fn):
    """执行一项检查，记录结果而不是直接中断——一次跑完能看全貌。"""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  —— {detail}")
    return ok


def fetch(base: str, path: str, timeout: float = 15.0):
    """GET 一个接口，返回 (状态码, 解析后的 JSON 或原文, 耗时秒)。"""
    url = base.rstrip("/") + path
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        code = resp.status
    elapsed = time.perf_counter() - t0
    try:
        return code, json.loads(raw.decode("utf-8")), elapsed
    except Exception:
        return code, raw.decode("utf-8", "replace"), elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="后端地址")
    args = ap.parse_args()
    base = args.base

    print(f"冒烟测试目标：{base}\n")

    # ---- 1. 服务与数据库 ----
    def _health():
        code, data, _ = fetch(base, "/api/health")
        if code != 200:
            return False, f"HTTP {code}"
        if not isinstance(data, dict):
            return False, "返回体不是 JSON 对象"
        db, algo = data.get("db", {}), data.get("algo_db", {})
        if not db.get("ok"):
            return False, f"主库未连通（{db.get('database')}）"
        if not algo.get("ok"):
            return False, f"算法库未连通（{algo.get('database')}）"
        return True, (
            f"MySQL {db.get('version')} · olist_db 正常 · "
            f"olist_algo_db 正常（RFM {algo.get('rfm_rows')} 行）"
        )

    print("[1/3] 服务与数据库")
    health_ok = check("GET /api/health", _health)
    if not health_ok:
        print("\n数据库没连上，后面的接口检查必然全失败，先修环境再跑。")
        print("  排查：MySQL 是否启动 → .env 的 MYSQL_PASSWORD 是否填对 → 是否跑过一键导入脚本")
        return 1

    # ---- 2. 8 个核心接口 ----
    print("\n[2/3] 8 个核心业务接口（200 + 返回非空 + < 2 秒）")

    def make_case(label: str, path: str):
        def _case():
            code, data, elapsed = fetch(base, path)
            if code != 200:
                return False, f"HTTP {code}"
            if not data:
                return False, "返回体为空"
            if elapsed >= SLOW_LIMIT:
                return False, f"{elapsed:.2f}s 超过 {SLOW_LIMIT:.0f}s 上限"
            # 尽量报一个可核对的行数，便于确认返回的不是空壳
            n = ""
            if isinstance(data, list):
                n = f"{len(data)} 条"
            elif isinstance(data, dict):
                for k in ("rows", "items", "data", "list"):
                    v = data.get(k)
                    if isinstance(v, list):
                        n = f"{len(v)} 条"
                        break
            return True, f"{elapsed * 1000:.0f} ms" + (f" · {n}" if n else "")
        return _case

    for label, path in CORE_ENDPOINTS:
        check(f"{label:8s} {path}", make_case(label, path))

    # ---- 3. 大模型层 ----
    print("\n[3/3] 大模型层就绪状态")

    def _llm_health():
        code, data, _ = fetch(base, "/api/llm/health")
        if code != 200:
            return False, f"HTTP {code}"
        cfg = data.get("config", {})
        kn = data.get("knowledge", {})
        tl = data.get("tools", {})
        if not kn.get("rules"):
            return False, "口径规则数为 0"
        rag = kn.get("rag", {})
        if not rag.get("ready"):
            return False, "RAG 未就绪"
        # tools.probe 是后端自带的四个真实数据源探针，有一个不通就说明工具层有洞
        probe = tl.get("probe", {}) if isinstance(tl, dict) else {}
        bad = [k for k, v in probe.items() if v != "ok"]
        if bad:
            return False, f"工具探针未通过：{', '.join(bad)}"
        return True, (
            f"provider={cfg.get('provider')} · model={cfg.get('model')} · "
            f"key={'有' if cfg.get('has_api_key') else '无(走离线兜底)'} · "
            f"工具 {tl.get('tools')} 个 · 规则 {kn.get('rules')} 条 · "
            f"RAG {rag.get('chunks')} 段 · 探针 {len(probe)}/{len(probe)} 通"
        )

    check("GET /api/llm/health", _llm_health)

    # ---- 汇总 ----
    total = len(PASS) + len(FAIL)
    print("\n" + "=" * 62)
    print(f"结果：{len(PASS)}/{total} 通过" + ("" if not FAIL else f"，{len(FAIL)} 项失败"))
    if FAIL:
        print("失败项：")
        for name in FAIL:
            print(f"  - {name}")
        print("\n未通过，请按上面的 FAIL 明细排查，不要按通过处理。")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

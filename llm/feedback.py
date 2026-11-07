# -*- coding: utf-8 -*-
"""反馈闭环存储（持续学习的第 0 步）。

只做三件事：把对话页的 👍/👎 与「纠正」原样落库、给统计、导出待审清单。
不在这里改规则——规则变更必须经过人工审核与回归评测，见 scripts/export_feedback.py。

数据落在 llm/feedback/feedback.db（SQLite），不依赖 MySQL，答辩现场断网也能演示。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "llm" / "feedback" / "feedback.db"

DDL = """
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT,
    mode       TEXT,
    verdict    TEXT,          -- up / down
    correction TEXT,
    reviewed   INTEGER NOT NULL DEFAULT 0
)
"""

VERDICTS = ("up", "down")


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=5)
    conn.execute(DDL)
    conn.commit()
    return conn


def add(question: str, answer: str = "", mode: str = "", verdict: str = "down",
        correction: str = "") -> int:
    """写入一条反馈，返回自增 id。字段超长时截断，避免脏数据撑爆库。"""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 必须是 {VERDICTS}")
    row = (
        datetime.now().isoformat(timespec="seconds"),
        (question or "").strip()[:500],
        (answer or "")[:8000],
        (mode or "")[:20],
        verdict,
        (correction or "").strip()[:2000],
    )
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO feedback(ts, question, answer, mode, verdict, correction) "
            "VALUES (?,?,?,?,?,?)", row)
        return int(cur.lastrowid)


def stats() -> dict:
    """总量、好评/差评、待审数、按模式分布。空库返回 0，不报错。"""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        up = conn.execute("SELECT COUNT(*) FROM feedback WHERE verdict='up'").fetchone()[0]
        down = conn.execute("SELECT COUNT(*) FROM feedback WHERE verdict='down'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM feedback WHERE reviewed=0").fetchone()[0]
        rows = conn.execute(
            "SELECT mode, COUNT(*) FROM feedback GROUP BY mode ORDER BY 2 DESC").fetchall()
    return {
        "total": total,
        "up": up,
        "down": down,
        "pending": pending,
        "by_mode": [{"mode": m or "-", "n": n} for m, n in rows],
        "db": str(DB.relative_to(BASE)),
    }


def recent(n: int = 20) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, ts, question, verdict, correction FROM feedback "
            "ORDER BY id DESC LIMIT ?", (int(n),)).fetchall()
    return [{"id": r[0], "ts": r[1], "question": r[2], "verdict": r[3], "correction": r[4]}
            for r in rows]


def export(path: Path, only_pending: bool = True) -> int:
    """导出为 JSONL，供人工归并成规则/评测题。返回导出行数。"""
    sql = ("SELECT id, ts, question, answer, mode, verdict, correction FROM feedback"
           + (" WHERE reviewed=0" if only_pending else "")
           + " ORDER BY id")
    with _conn() as conn:
        rows = conn.execute(sql).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "ts", "question", "answer", "mode", "verdict", "correction"]
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(dict(zip(cols, r)), ensure_ascii=False) + "\n")
    return len(rows)


def mark_reviewed(ids: list[int]) -> int:
    if not ids:
        return 0
    q = ",".join("?" * len(ids))
    with _conn() as conn:
        cur = conn.execute(f"UPDATE feedback SET reviewed=1 WHERE id IN ({q})",
                           [int(i) for i in ids])
        return cur.rowcount
# -*- coding: utf-8 -*-
"""算法结果 SQLite -> MySQL 同步脚本。

背景
----
`import_algo1.py` / `import_algo2.py` 只把算法结果写进本地 SQLite
`olist_algo.db`，而 FastAPI 后端读的是 MySQL 里的 `olist_algo_db`。
过去这两步之间靠手工执行一次性的 `olist_algo_mysql.sql` 快照，
**算法 CSV 一旦重跑，MySQL 不会跟着更新**，容易出现"代码改了、页面还是旧数"。

本脚本补上这条链路：
    cleaned/*.csv  →  algo1/algo2 模型  →  olist_algo.db  →  olist_algo_db(MySQL)

用法
----
    python3 export_algo_to_mysql.py

前提：先跑过 import_algo1.py / import_algo2.py（SQLite 里已有最新结果），
      且 MySQL 里已执行过 olist_algo_mysql.sql 建好表结构。
"""
import sqlite3
import sys
from pathlib import Path

import pymysql

BASE = Path(__file__).resolve().parent.parent   # 项目根目录
sys.path.append(str(BASE))
import config

SQLITE_PATH = BASE / "olist_algo.db"

# 需要同步的表（顺序无所谓，都是全量覆盖）
TABLES = [
    "algo1_rfm_user_tags",
    "algo2_forecast_result",
    "algo2_selection_result",
    "algo2_pricing_result",
    "algo2_pricing_skipped",
    "algo2_offline_experiment",
    "algo2_summary_stats",
    "algo2_selection_hitrate",
    "algo_import_log",
]

BATCH = 2000


def main() -> int:
    if not SQLITE_PATH.exists():
        print(f"[错误] 找不到 {SQLITE_PATH}，请先运行 import_algo1.py / import_algo2.py")
        return 1

    lite = sqlite3.connect(str(SQLITE_PATH))
    lite.row_factory = sqlite3.Row

    cfg = config.ALGO_DB_CONFIG
    my = pymysql.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], database=cfg["database"],
        charset=cfg["charset"], autocommit=False,
    )
    cur = my.cursor()

    print("=" * 70)
    print("算法结果同步：SQLite -> MySQL")
    print(f"  源  : {SQLITE_PATH}")
    print(f"  目标: {cfg['host']}:{cfg['port']}/{cfg['database']}")
    print("=" * 70)

    total_rows = 0
    for table in TABLES:
        # 两边字段必须一致，否则直接报错，避免静默丢列
        s_cols = [r[1] for r in lite.execute(f"PRAGMA table_info({table})")]
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        m_cols = [r[0] for r in cur.fetchall()]
        if not s_cols:
            print(f"  [跳过] {table}：SQLite 中没有这张表")
            continue
        if s_cols != m_cols:
            print(f"  [错误] {table} 字段不一致，已中止")
            print(f"         sqlite={s_cols}")
            print(f"         mysql ={m_cols}")
            return 1

        rows = lite.execute(f"SELECT * FROM `{table}`").fetchall()
        cur.execute(f"DELETE FROM `{table}`")
        if rows:
            cols = ",".join(f"`{c}`" for c in s_cols)
            ph = ",".join(["%s"] * len(s_cols))
            sql = f"INSERT INTO `{table}` ({cols}) VALUES ({ph})"
            for i in range(0, len(rows), BATCH):
                chunk = [tuple(r) for r in rows[i:i + BATCH]]
                cur.executemany(sql, chunk)
        my.commit()
        total_rows += len(rows)
        print(f"  [完成] {table:<28} {len(rows):>7,} 行")

    cur.close()
    my.close()
    lite.close()
    print("-" * 70)
    print(f"同步完成，共 {total_rows:,} 行。后端无需重启，刷新页面即可看到最新结果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
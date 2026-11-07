#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
算法1（RFM 用户标签）批量数据入库脚本  v2
==========================================

功能：
    读取算法1 的输出 CSV，批量写入 SQLite 数据库，
    并在写入后自动做完整性校验（行数比对、唯一性、空值、标签一致性、抽样核对）。

v2 变更（重要，务必阅读）
------------------------
    旧版读 `算法1/algo1_rfm_user_tags.csv`（只有 R/F/M 三列），
    在脚本里自行用「五分位」给 R/F/M 打分并生成 8 类人群。

    但 Olist 数据有 96.95% 的用户 frequency == 1。
    `pd.qcut(rank, 5)` 会强制均分五档，结果：
        - F 分 1、2、3、4 全部对应 frequency = 1
        - F 分 5 中仍有 84.7% 是只买过一次的用户
    即 54,339 个只买 1 次的用户被错标为「高 F」，
    「重要价值用户」被虚高到 1,717 人（真实应为 166 人）。

    v2 改为直接读取算法1 的输出 `算法1/algo1_rfm_clusters.csv`：
        - R/M 用五分位（连续值，不会退化）
        - F 用业务阈值（1 次→1分，2 次→2分，...，≥5 次→5分）
        - 含 K-Means 4 类聚类结果
    脚本只负责「入库 + 校验」，不再重新计算标签。

数据来源：
    算法1/algo1_rfm_clusters.csv  （13 列，95,420 行）

运行方式：
    在本文件所在目录执行：  python import_algo1.py
"""

import csv
import os
import sqlite3
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# 配置区：所有路径集中在这里，换台电脑只改这几行
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根目录（pipeline/ 的上一级）
CSV_PATH = os.path.join(PROJECT_DIR, "算法1", "algo1_rfm_clusters.csv")
DB_PATH = os.path.join(PROJECT_DIR, "olist_algo.db")
BATCH_SIZE = 10000

# 建表语句：字段与 csv 一一对应
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS algo1_rfm_user_tags (
    customer_unique_id  TEXT PRIMARY KEY,   -- 用户ID，唯一，做主键
    recency             INTEGER NOT NULL,   -- 距数据截止日的天数
    frequency           INTEGER NOT NULL,   -- 购买次数
    monetary            REAL    NOT NULL,   -- 累计消费额
    r_score             INTEGER NOT NULL,   -- R 得分 1~5
    f_score             INTEGER NOT NULL,   -- F 得分 1~5（业务阈值法）
    m_score             INTEGER NOT NULL,   -- M 得分 1~5
    rfm_score           TEXT    NOT NULL,   -- 三位拼接，如 "545"
    kmeans_cluster      INTEGER NOT NULL,   -- K-Means 簇编号 0~3
    rfm_segment_kmeans4 TEXT    NOT NULL,   -- K-Means 4 类人群标签
    rfm_segment_rule8   TEXT    NOT NULL,   -- 规则 8 类人群标签
    f_score_quantile    INTEGER,            -- 旧版五分位 F 分（仅作对比，可为空）
    imported_at         TEXT    NOT NULL    -- 本次导入时间
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_algo1_segment
    ON algo1_rfm_user_tags (rfm_segment_kmeans4)
"""

CREATE_INDEX2_SQL = """
CREATE INDEX IF NOT EXISTS idx_algo1_segment8
    ON algo1_rfm_user_tags (rfm_segment_rule8)
"""

# 导入日志表（两个脚本共用）
CREATE_LOG_SQL = """
CREATE TABLE IF NOT EXISTS algo_import_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    algo_name    TEXT NOT NULL,
    table_name   TEXT NOT NULL,
    source_file  TEXT NOT NULL,
    csv_rows     INTEGER,
    db_rows      INTEGER,
    status       TEXT NOT NULL,
    message      TEXT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    duration_sec REAL
)
"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def to_int(s):
    s = (s or "").strip()
    return int(float(s)) if s else None


def to_float(s):
    s = (s or "").strip()
    return float(s) if s else None


def ensure_schema(conn):
    """检测已存在的表是否为旧版结构，是则删除重建。

    旧版（v1）表只有 r_score/f_score/m_score/rfm_score 四个派生列，
    没有 kmeans_cluster / rfm_segment_kmeans4 / rfm_segment_rule8 / f_score_quantile。
    数据本身完全由 CSV 决定，删表重建是安全的（不会丢真实数据）。
    """
    cur = conn.execute("PRAGMA table_info(algo1_rfm_user_tags)")
    cols = {r[1] for r in cur.fetchall()}
    if not cols:
        return False
    need = {"kmeans_cluster", "rfm_segment_kmeans4", "rfm_segment_rule8",
            "f_score_quantile"}
    missing = need - cols
    if missing:
        print(f"      [迁移] 检测到 v1 旧表结构（缺列 {sorted(missing)}），删除重建 ...")
        conn.execute("DROP TABLE IF EXISTS algo1_rfm_user_tags")
        conn.commit()
        return True
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    started = datetime.now()
    t0 = time.time()

    # 0. 前置检查
    if not os.path.exists(CSV_PATH):
        print(f"[错误] 找不到 CSV 文件: {CSV_PATH}")
        print("       请先运行算法1 生成 algo1_rfm_clusters.csv，")
        print("       或修改脚本顶部的 CSV_PATH。")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    print(f"[1/5] 已连接数据库: {DB_PATH}")

    # 1. 建表（重复运行安全）
    ensure_schema(conn)          # 旧版结构自动重建
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_INDEX_SQL)
    conn.execute(CREATE_INDEX2_SQL)
    conn.execute(CREATE_LOG_SQL)
    conn.commit()
    print("[2/5] 数据表已就绪（algo1_rfm_user_tags / algo_import_log）")

    # 2. 读 CSV
    print("[3/5] 正在读取 CSV ...")
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)
    if not raw_rows:
        print("[错误] CSV 只有表头、没有数据行，已中止。")
        conn.close()
        sys.exit(1)

    need_cols = {"customer_unique_id", "recency", "frequency", "monetary",
                 "r_score", "f_score", "m_score", "rfm_score",
                 "kmeans_cluster", "rfm_segment_kmeans4", "rfm_segment_rule8"}
    missing = need_cols - set(raw_rows[0].keys())
    if missing:
        print(f"[错误] CSV 缺少必需字段: {missing}")
        print("       本脚本 v2 需要 algo1_rfm_clusters.csv（含标签列），")
        print("       旧版 algo1_rfm_user_tags.csv 只有 4 列，不受支持。")
        conn.close()
        sys.exit(1)

    print(f"      CSV 数据行数: {len(raw_rows):,}")

    # 3. 组装并分批写入
    imported_at = started.strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for r in raw_rows:
        cid = (r["customer_unique_id"] or "").strip()
        if not cid:
            print("[错误] 存在 customer_unique_id 为空的行，已中止。")
            conn.close()
            sys.exit(1)
        rows.append((
            cid,
            to_int(r["recency"]), to_int(r["frequency"]), to_float(r["monetary"]),
            to_int(r["r_score"]), to_int(r["f_score"]), to_int(r["m_score"]),
            (r["rfm_score"] or "").strip(),
            to_int(r["kmeans_cluster"]),
            (r["rfm_segment_kmeans4"] or "").strip(),
            (r["rfm_segment_rule8"] or "").strip(),
            to_int(r.get("f_score_quantile")),
            imported_at,
        ))

    try:
        with conn:
            conn.execute("DELETE FROM algo1_rfm_user_tags")
            conn.executemany(
                """INSERT INTO algo1_rfm_user_tags
                   (customer_unique_id, recency, frequency, monetary,
                    r_score, f_score, m_score, rfm_score,
                    kmeans_cluster, rfm_segment_kmeans4, rfm_segment_rule8,
                    f_score_quantile, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
    except sqlite3.Error as e:
        conn.execute(
            """INSERT INTO algo_import_log
               (algo_name, table_name, source_file, csv_rows, db_rows,
                status, message, started_at, finished_at, duration_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("算法1", "algo1_rfm_user_tags", os.path.basename(CSV_PATH),
             len(raw_rows), 0, "FAILED", str(e),
             started.strftime("%Y-%m-%d %H:%M:%S"),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 2)),
        )
        conn.commit()
        conn.close()
        print(f"[错误] 写入数据库失败: {e}")
        sys.exit(1)
    print(f"[4/5] 已写入 {len(rows):,} 行")

    # 4. 入库后校验
    print("[5/5] 正在校验入库数据完整性 ...")
    checks = []

    db_rows = conn.execute("SELECT COUNT(*) FROM algo1_rfm_user_tags").fetchone()[0]
    checks.append(("行数一致（CSV vs 数据库）", len(raw_rows) == db_rows,
                   f"CSV {len(raw_rows):,} / DB {db_rows:,}"))

    dup = conn.execute(
        """SELECT COUNT(*) FROM (SELECT customer_unique_id FROM algo1_rfm_user_tags
                                 GROUP BY customer_unique_id HAVING COUNT(*) > 1)"""
    ).fetchone()[0]
    checks.append(("用户ID唯一（无重复）", dup == 0, f"重复组数 {dup}"))

    null_cnt = conn.execute(
        """SELECT COUNT(*) FROM algo1_rfm_user_tags
           WHERE recency IS NULL OR frequency IS NULL OR monetary IS NULL
              OR rfm_segment_kmeans4 IS NULL OR rfm_segment_rule8 IS NULL
              OR kmeans_cluster IS NULL"""
    ).fetchone()[0]
    checks.append(("核心字段无空值", null_cnt == 0, f"异常行 {null_cnt}"))

    # 关键：F 分与真实购买次数是否一致
    bad_f = conn.execute(
        "SELECT COUNT(*) FROM algo1_rfm_user_tags "
        "WHERE (f_score >= 3 AND frequency < 3) OR (f_score = 1 AND frequency <> 1)"
    ).fetchone()[0]
    checks.append(("F 分与购买次数一致（无失真）", bad_f == 0,
                   f"不一致 {bad_f} 行（旧版五分位会有 54,339 行）"))

    # rfm_score 拼接一致性
    bad_score = conn.execute(
        "SELECT COUNT(*) FROM algo1_rfm_user_tags "
        "WHERE rfm_score <> (CAST(r_score AS TEXT) || CAST(f_score AS TEXT) "
        "|| CAST(m_score AS TEXT))"
    ).fetchone()[0]
    checks.append(("rfm_score 拼接正确", bad_score == 0, f"不一致 {bad_score} 行"))

    bad_range = conn.execute(
        "SELECT COUNT(*) FROM algo1_rfm_user_tags "
        "WHERE r_score NOT BETWEEN 1 AND 5 OR f_score NOT BETWEEN 1 AND 5 "
        "OR m_score NOT BETWEEN 1 AND 5"
    ).fetchone()[0]
    checks.append(("R/F/M 得分均在 1~5", bad_range == 0, f"越界行 {bad_range}"))

    n_cluster = conn.execute(
        "SELECT COUNT(DISTINCT kmeans_cluster) FROM algo1_rfm_user_tags"
    ).fetchone()[0]
    checks.append(("K-Means 簇数为 4", n_cluster == 4, f"实际 {n_cluster} 簇"))

    n_seg8 = conn.execute(
        "SELECT COUNT(DISTINCT rfm_segment_rule8) FROM algo1_rfm_user_tags"
    ).fetchone()[0]
    checks.append(("规则分群为 8 类", n_seg8 == 8, f"实际 {n_seg8} 类"))

    # 抽样核对
    spot_ok = True
    detail = []
    for r in raw_rows[:3]:
        cid = r["customer_unique_id"].strip()
        row = conn.execute(
            "SELECT recency, frequency, monetary, f_score, rfm_segment_rule8 "
            "FROM algo1_rfm_user_tags WHERE customer_unique_id = ?", (cid,)
        ).fetchone()
        if row is None:
            spot_ok = False
            detail.append(f"{cid[:8]}... 未找到")
        else:
            ok = (row[0] == to_int(r["recency"])
                  and row[1] == to_int(r["frequency"])
                  and abs(row[2] - to_float(r["monetary"])) < 1e-9
                  and row[3] == to_int(r["f_score"])
                  and row[4] == r["rfm_segment_rule8"].strip())
            spot_ok = spot_ok and ok
            detail.append(f"{cid[:8]}... {'一致' if ok else '不一致!'}")
    checks.append(("抽样核对（CSV前3行）", spot_ok, "; ".join(detail)))

    all_ok = True
    for name, ok, info in checks:
        all_ok = all_ok and ok
        print(f"      [{'PASS' if ok else 'FAIL'}] {name}: {info}")

    # 5. 写日志 + 分布
    finished = datetime.now()
    conn.execute(
        """INSERT INTO algo_import_log
           (algo_name, table_name, source_file, csv_rows, db_rows,
            status, message, started_at, finished_at, duration_sec)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("算法1", "algo1_rfm_user_tags", os.path.basename(CSV_PATH),
         len(raw_rows), db_rows,
         "SUCCESS" if all_ok else "WARN",
         "; ".join(f"{n}:{'PASS' if ok else 'FAIL'}" for n, ok, _ in checks),
         started.strftime("%Y-%m-%d %H:%M:%S"),
         finished.strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 2)),
    )
    conn.commit()

    print("\nK-Means 4 类人群分布:")
    for seg, cnt in conn.execute(
        "SELECT rfm_segment_kmeans4, COUNT(*) c FROM algo1_rfm_user_tags "
        "GROUP BY rfm_segment_kmeans4 ORDER BY c DESC"
    ):
        print(f"      {seg:<10} {cnt:>8,} 人 ({cnt / db_rows * 100:.2f}%)")

    print("\n规则 8 类人群分布:")
    for seg, cnt in conn.execute(
        "SELECT rfm_segment_rule8, COUNT(*) c FROM algo1_rfm_user_tags "
        "GROUP BY rfm_segment_rule8 ORDER BY c DESC"
    ):
        print(f"      {seg:<10} {cnt:>8,} 人 ({cnt / db_rows * 100:.2f}%)")

    conn.close()
    print(f"\n完成，耗时 {time.time() - t0:.2f} 秒。数据库文件: {DB_PATH}")
    if not all_ok:
        print("注意：有校验项未通过，请检查上方 [FAIL] 项。")
        sys.exit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
算法2（销量预测 / 选品 / 定价）批量数据入库脚本
================================================

功能：
    读取算法2输出的 6 个 CSV，批量写入 SQLite 数据库的 6 张表，
    写入后逐表校验，并做跨表一致性核对，最后打印汇总报告。

设计说明（为什么这样写）：
    1. 用 SQLite：与算法1脚本一致，Python 自带 sqlite3 驱动，零依赖。
    2. 每张表都设了主键（PRIMARY KEY），从数据库层面保证记录不重复；
       预测表用「品类+预测周」、离线实验用「品类+模型+holdout周数」做联合主键。
    3. CSV 里的空单元格统一转成 NULL，不要让空字符串污染数值列——
       比如定价结果里有 19 个商品「样本不足」没有建议价，就应该是 NULL。
    4. 支持重复执行：每次运行在同一事务内「先清空、再插入」，
       中途失败自动回滚，数据库永远和 CSV 保持一致。
    5. 每张表导入后都写一条 algo_import_log 日志，可追溯每次导入。
    6. 除了单表行数核对外，还做了跨表业务校验，例如：
       - 选品商品数 = 定价商品数（定价以选品为输入）
       - 定价跳过表的商品 = 定价表中无建议价的商品
       - 汇总统计表里的数字与库内实际 COUNT 对得上

运行方式：
    在本文件所在目录执行：  python import_algo2.py
"""

import csv
import os
import sqlite3
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# 配置区
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根目录（pipeline/ 的上一级）
ALGO2_DIR = os.path.join(PROJECT_DIR, "算法2")
DB_PATH = os.path.join(PROJECT_DIR, "olist_algo.db")
BATCH_SIZE = 5000

# ---------------------------------------------------------------------------
# 建表语句（6 张业务表 + 1 张共享的导入日志表）
# ---------------------------------------------------------------------------
CREATE_LOG_SQL = """
CREATE TABLE IF NOT EXISTS algo_import_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    algo_name    TEXT NOT NULL,
    table_name   TEXT NOT NULL,
    source_file  TEXT NOT NULL,
    csv_rows     INTEGER,
    db_rows      INTEGER,
    status       TEXT NOT NULL,            -- SUCCESS / FAILED
    message      TEXT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    duration_sec REAL
)
"""

# 预测结果：74 个品类 × 8 个预测周，主键 = 品类 + 预测周
CREATE_FORECAST_SQL = """
CREATE TABLE IF NOT EXISTS algo2_forecast_result (
    category                TEXT NOT NULL,
    forecast_week           TEXT NOT NULL,   -- 如 2018-W35
    forecast_date           TEXT NOT NULL,   -- 该周周一日期
    predicted_qty           REAL NOT NULL,   -- 预测销量
    lower_95                REAL NOT NULL,   -- 95% 区间下限
    upper_95                REAL NOT NULL,   -- 95% 区间上限
    baseline_ma4_qty        REAL,            -- MA4 基线预测值
    model                   TEXT NOT NULL,   -- 选中的模型名
    mape_model_pct          REAL,            -- 主模型 MAPE
    mape_stable_model_pct   REAL,            -- 主模型 MAPE(稳定周)，可为 NULL
    mape_baseline_pct       REAL,            -- 基线 MAPE
    improvement_pct         REAL,            -- MAPE 相对基线提升%
    wape_model_pct          REAL,            -- 主模型 WAPE
    wape_baseline_pct       REAL,            -- 基线 WAPE
    wape_improvement_pct    REAL,
    history_weeks           INTEGER,         -- 使用的历史周数
    last_history_week       TEXT,            -- 最后一个历史周
    last_history_qty        REAL,            -- 最后一个历史周的实际销量
    imported_at             TEXT NOT NULL,
    PRIMARY KEY (category, forecast_week)
)
"""

# 选品结果：增长榜 + 高销量分析池，主键 = 榜单类型 + 排名
CREATE_SELECTION_SQL = """
CREATE TABLE IF NOT EXISTS algo2_selection_result (
    rank             INTEGER NOT NULL,
    selection_type   TEXT NOT NULL,          -- 增长榜 / 高销量分析池
    product_id       TEXT NOT NULL,
    category         TEXT NOT NULL,
    gmv_recent       REAL,                   -- 近12周 GMV
    gmv_prior        REAL,                   -- 前12周 GMV
    gmv_total        REAL,                   -- 累计 GMV
    growth_pct       REAL,                   -- 增长率%
    qty_recent       REAL,
    qty_prior        REAL,
    total_qty        INTEGER,
    active_months    INTEGER,
    avg_price        REAL,
    score_scale      REAL,                   -- 规模分
    score_growth     REAL,                   -- 增长分
    score_price      REAL,                   -- 价格分
    score_total      REAL,                   -- 总分
    recommendation   TEXT,                   -- 强推 / 推荐 / 备选
    recent_window    TEXT,                   -- 近期窗口
    prior_window     TEXT,                   -- 对照窗口
    imported_at      TEXT NOT NULL,
    PRIMARY KEY (selection_type, rank)
)
"""
CREATE_SELECTION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_algo2_selection_product
    ON algo2_selection_result (product_id)
"""

# 定价结果：一个商品一行，主键 = 商品ID；无建议价的字段为 NULL
CREATE_PRICING_SQL = """
CREATE TABLE IF NOT EXISTS algo2_pricing_result (
    product_id                    TEXT PRIMARY KEY,
    category                      TEXT NOT NULL,
    selection_type                TEXT NOT NULL,
    rank_in_selection             INTEGER,
    months_observed               INTEGER,   -- 观测月数
    price_cv_pct                  REAL,      -- 价格变异系数%
    current_price                 REAL,      -- 当前价（月度量价加权均价）
    suggested_price               REAL,      -- 建议价（样本不足时为 NULL）
    price_lower_95                REAL,      -- 价格区间下限
    price_upper_95                REAL,      -- 价格区间上限
    price_change_pct              REAL,      -- 建议价相对现价变动%（无建议价时 NULL）
    elasticity                    REAL,      -- 价格弹性（无建议价时 NULL）
    elasticity_source             TEXT,      -- 弹性来源：商品级 / 品类级 / 样本不足
    elasticity_r2                 REAL,      -- 弹性回归 R²（无建议价时 NULL）
    confidence                    TEXT,      -- 高 / 中 / 低
    expected_qty_change_pct       REAL,      -- 预期销量变化%（无建议价时 NULL）
    expected_revenue_change_pct   REAL,      -- 预期收入变化%（无建议价时 NULL）
    pricing_rule                  TEXT,      -- 定价规则说明
    method                        TEXT,      -- 方法
    note                          TEXT,      -- 备注
    imported_at                   TEXT NOT NULL
)
"""

# 定价跳过表：样本不满足门槛、无法估计弹性的商品
CREATE_PRICING_SKIPPED_SQL = """
CREATE TABLE IF NOT EXISTS algo2_pricing_skipped (
    product_id      TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    months_observed INTEGER,
    price_cv_pct    REAL,
    reason          TEXT NOT NULL,
    imported_at     TEXT NOT NULL
)
"""

# 离线实验：每个品类 4 个模型（主模型 + MA4基线 + 季节朴素 + 阻尼Holt）
CREATE_EXPERIMENT_SQL = """
CREATE TABLE IF NOT EXISTS algo2_offline_experiment (
    category                     TEXT NOT NULL,
    model                        TEXT NOT NULL,
    is_baseline                  INTEGER NOT NULL,  -- 1=基线, 0=非基线
    holdout_weeks                INTEGER NOT NULL,  -- 验证周数
    mape_pct                     REAL,
    mape_stable_pct              REAL,              -- 可为 NULL
    wape_pct                     REAL,
    mae                          REAL,
    rmse                         REAL,
    mape_vs_baseline_improve_pct  REAL,              -- 相对基线 MAPE 提升%
    wape_vs_baseline_improve_pct  REAL,
    history_weeks                INTEGER,
    imported_at                  TEXT NOT NULL,
    PRIMARY KEY (category, model, holdout_weeks)
)
"""

# 汇总统计：一行一个统计项；数值列保留原文 + 尽量解析出数值
CREATE_SUMMARY_SQL = """
CREATE TABLE IF NOT EXISTS algo2_summary_stats (
    stat_group   TEXT NOT NULL,          -- 数据集 / 预测 / 选品 / 定价
    stat_name    TEXT NOT NULL,          -- 统计项名称
    value_text   TEXT NOT NULL,          -- 原始数值（如 "112,101"、"135.73%"）
    value_num    REAL,                   -- 可解析为数值时给出，否则 NULL
    description  TEXT,                   -- 口径说明
    imported_at  TEXT NOT NULL,
    PRIMARY KEY (stat_group, stat_name)
)
"""

# 选品 Top10 命中率（时间切分回测结果，算法2 追加交付）
CREATE_HITRATE_SQL = """
CREATE TABLE IF NOT EXISTS algo2_selection_hitrate (
    level                TEXT NOT NULL,     -- 品类级 / 商品级
    strategy             TEXT NOT NULL,     -- 策略名
    top_n                INTEGER NOT NULL,  -- 选前几名
    hit_cnt              REAL,              -- 命中数（随机基线为理论期望值，可为小数）
    hit_rate_pct         REAL,              -- 命中率%
    valid_top20_cnt      INTEGER,           -- 验证期 Top20% 的候选数量
    valid_candidate_cnt  INTEGER,           -- 验证期候选总数
    note                 TEXT,              -- 口径说明
    top_list             TEXT,              -- 入选清单
    train_window         TEXT,              -- 训练期窗口
    valid_window         TEXT,              -- 验证期窗口
    imported_at          TEXT NOT NULL,
    PRIMARY KEY (level, strategy)
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


def try_parse_num(s):
    """尽力把 '112,101' / '135.73%' 这类文本转成数值，失败返回 None。"""
    s = (s or "").strip().replace(",", "").rstrip("%")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_csv(path):
    """读 CSV 返回 (字段名列表, 行字典列表)；文件不存在直接退出并提示。"""
    if not os.path.exists(path):
        print(f"[错误] 找不到 CSV 文件: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return reader.fieldnames, rows


def write_table(conn, table, csv_name, rows, col_names, row_maker, started, t0):
    """
    通用写入函数：清空旧数据 → 分批插入 → 记日志 → 返回 (CSV行数, 库内行数)。

    col_names: 数据库列名（与 VALUES 中的 ? 一一对应）
    row_maker: 把 CSV 行字典转成元组的函数，顺手做类型转换
    """
    placeholders = ",".join("?" for _ in col_names)
    sql = f"INSERT INTO {table} ({','.join(col_names)}) VALUES ({placeholders})"
    try:
        data = [row_maker(r) for r in rows]
        with conn:   # 事务：要么全部成功，要么全部回滚
            conn.execute(f"DELETE FROM {table}")
            conn.executemany(sql, data)
    except sqlite3.Error as e:
        conn.execute(
            """INSERT INTO algo_import_log
               (algo_name, table_name, source_file, csv_rows, db_rows,
                status, message, started_at, finished_at, duration_sec)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("算法2", table, csv_name, len(rows), 0, "FAILED", str(e),
             started.strftime("%Y-%m-%d %H:%M:%S"),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 2)),
        )
        conn.commit()
        print(f"[错误] 写入 {table} 失败: {e}")
        sys.exit(1)

    db_rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.execute(
        """INSERT INTO algo_import_log
           (algo_name, table_name, source_file, csv_rows, db_rows,
            status, message, started_at, finished_at, duration_sec)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("算法2", table, csv_name, len(rows), db_rows,
         "SUCCESS" if db_rows == len(rows) else "WARN",
         f"CSV {len(rows)} / DB {db_rows}",
         started.strftime("%Y-%m-%d %H:%M:%S"),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 2)),
    )
    conn.commit()
    return len(rows), db_rows


# ---------------------------------------------------------------------------
# 各表的「CSV 行 → 数据库元组」转换函数
# ---------------------------------------------------------------------------
def mk_forecast(r):
    return (r["category"], r["forecast_week"], r["forecast_date"],
            to_float(r["predicted_qty"]), to_float(r["lower_95"]), to_float(r["upper_95"]),
            to_float(r["baseline_ma4_qty"]), r["model"],
            to_float(r["mape_model_pct"]), to_float(r["mape_stable_model_pct"]),
            to_float(r["mape_baseline_pct"]), to_float(r["improvement_pct"]),
            to_float(r["wape_model_pct"]), to_float(r["wape_baseline_pct"]),
            to_float(r["wape_improvement_pct"]), to_int(r["history_weeks"]),
            r["last_history_week"], to_float(r["last_history_qty"]))


def mk_selection(r):
    return (to_int(r["rank"]), r["selection_type"], r["product_id"], r["category"],
            to_float(r["gmv_recent"]), to_float(r["gmv_prior"]), to_float(r["gmv_total"]),
            to_float(r["growth_pct"]), to_float(r["qty_recent"]), to_float(r["qty_prior"]),
            to_int(r["total_qty"]), to_int(r["active_months"]), to_float(r["avg_price"]),
            to_float(r["score_scale"]), to_float(r["score_growth"]), to_float(r["score_price"]),
            to_float(r["score_total"]), r["recommendation"],
            r["recent_window"], r["prior_window"])


def mk_pricing(r):
    return (r["product_id"], r["category"], r["selection_type"],
            to_int(r["rank_in_selection"]), to_int(r["months_observed"]),
            to_float(r["price_cv_pct"]), to_float(r["current_price"]),
            to_float(r["suggested_price"]), to_float(r["price_lower_95"]),
            to_float(r["price_upper_95"]), to_float(r["price_change_pct"]),
            to_float(r["elasticity"]), r["elasticity_source"], to_float(r["elasticity_r2"]),
            r["confidence"], to_float(r["expected_qty_change_pct"]),
            to_float(r["expected_revenue_change_pct"]), r["pricing_rule"],
            r["method"], r["note"])


def mk_skipped(r):
    return (r["product_id"], r["category"], to_int(r["months_observed"]),
            to_float(r["price_cv_pct"]), r["reason"])


def mk_experiment(r):
    return (r["category"], r["model"], to_int(r["is_baseline"]), to_int(r["holdout_weeks"]),
            to_float(r["mape_pct"]), to_float(r["mape_stable_pct"]), to_float(r["wape_pct"]),
            to_float(r["mae"]), to_float(r["rmse"]),
            to_float(r["mape_vs_baseline_improve_pct"]),
            to_float(r["wape_vs_baseline_improve_pct"]), to_int(r["history_weeks"]))


def mk_summary(r):
    return (r["类别"], r["统计项"], r["数值"], try_parse_num(r["数值"]), r["口径说明"])


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    started = datetime.now()
    t0 = time.time()

    conn = sqlite3.connect(DB_PATH)
    print(f"[1/6] 已连接数据库: {DB_PATH}")

    # 1. 建表（重复运行安全）
    for sql in (CREATE_LOG_SQL, CREATE_FORECAST_SQL, CREATE_SELECTION_SQL,
                CREATE_SELECTION_INDEX_SQL, CREATE_PRICING_SQL,
                CREATE_PRICING_SKIPPED_SQL, CREATE_EXPERIMENT_SQL, CREATE_SUMMARY_SQL,
                CREATE_HITRATE_SQL):
        conn.execute(sql)
    conn.commit()
    print("[2/6] 8 张数据表已就绪（预测/选品/定价/定价跳过/离线实验/汇总统计/命中率/导入日志）")

    imported_at = started.strftime("%Y-%m-%d %H:%M:%S")
    tables = []   # (表名, 列名..., row_maker) —— 用统一入口写入

    # 2. 逐个 CSV 读取并入库
    print("[3/6] 正在导入 7 个 CSV ...")

    # --- 预测结果 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_forecast_result.csv"))
    # 显式列出数据库列名（与 INSERT 中的 ? 一一对应，最后一个是导入时间戳）
    fc_cols = ["category", "forecast_week", "forecast_date", "predicted_qty", "lower_95",
               "upper_95", "baseline_ma4_qty", "model", "mape_model_pct",
               "mape_stable_model_pct", "mape_baseline_pct", "improvement_pct",
               "wape_model_pct", "wape_baseline_pct", "wape_improvement_pct",
               "history_weeks", "last_history_week", "last_history_qty", "imported_at"]
    def mk_forecast_full(r):
        return mk_forecast(r) + (imported_at,)
    n1 = write_table(conn, "algo2_forecast_result", "algo2_forecast_result.csv",
                     rows, fc_cols, mk_forecast_full, started, t0)
    print(f"      algo2_forecast_result      CSV {n1[0]:>5} / DB {n1[1]:>5}")

    # --- 选品结果 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_selection_result.csv"))
    sel_cols = ["rank", "selection_type", "product_id", "category", "gmv_recent", "gmv_prior",
                "gmv_total", "growth_pct", "qty_recent", "qty_prior", "total_qty",
                "active_months", "avg_price", "score_scale", "score_growth", "score_price",
                "score_total", "recommendation", "recent_window", "prior_window", "imported_at"]
    def mk_selection_full(r):
        return mk_selection(r) + (imported_at,)
    n2 = write_table(conn, "algo2_selection_result", "algo2_selection_result.csv",
                     rows, sel_cols, mk_selection_full, started, t0)
    print(f"      algo2_selection_result     CSV {n2[0]:>5} / DB {n2[1]:>5}")

    # --- 定价结果 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_pricing_result.csv"))
    pr_cols = ["product_id", "category", "selection_type", "rank_in_selection",
               "months_observed", "price_cv_pct", "current_price", "suggested_price",
               "price_lower_95", "price_upper_95", "price_change_pct", "elasticity",
               "elasticity_source", "elasticity_r2", "confidence",
               "expected_qty_change_pct", "expected_revenue_change_pct",
               "pricing_rule", "method", "note", "imported_at"]
    def mk_pricing_full(r):
        return mk_pricing(r) + (imported_at,)
    n3 = write_table(conn, "algo2_pricing_result", "algo2_pricing_result.csv",
                     rows, pr_cols, mk_pricing_full, started, t0)
    print(f"      algo2_pricing_result       CSV {n3[0]:>5} / DB {n3[1]:>5}")

    # --- 定价跳过 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_pricing_skipped.csv"))
    sk_cols = ["product_id", "category", "months_observed", "price_cv_pct", "reason", "imported_at"]
    def mk_skipped_full(r):
        return mk_skipped(r) + (imported_at,)
    n4 = write_table(conn, "algo2_pricing_skipped", "algo2_pricing_skipped.csv",
                     rows, sk_cols, mk_skipped_full, started, t0)
    print(f"      algo2_pricing_skipped      CSV {n4[0]:>5} / DB {n4[1]:>5}")

    # --- 离线实验 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_offline_experiment.csv"))
    ex_cols = ["category", "model", "is_baseline", "holdout_weeks", "mape_pct",
               "mape_stable_pct", "wape_pct", "mae", "rmse",
               "mape_vs_baseline_improve_pct", "wape_vs_baseline_improve_pct",
               "history_weeks", "imported_at"]
    def mk_experiment_full(r):
        return mk_experiment(r) + (imported_at,)
    n5 = write_table(conn, "algo2_offline_experiment", "algo2_offline_experiment.csv",
                     rows, ex_cols, mk_experiment_full, started, t0)
    print(f"      algo2_offline_experiment   CSV {n5[0]:>5} / DB {n5[1]:>5}")

    # --- 汇总统计 ---
    _, rows = read_csv(os.path.join(ALGO2_DIR, "algo2_summary_stats.csv"))
    sm_cols = ["stat_group", "stat_name", "value_text", "value_num", "description", "imported_at"]
    def mk_summary_full(r):
        return mk_summary(r) + (imported_at,)
    n6 = write_table(conn, "algo2_summary_stats", "algo2_summary_stats.csv",
                     rows, sm_cols, mk_summary_full, started, t0)
    print(f"      algo2_summary_stats        CSV {n6[0]:>5} / DB {n6[1]:>5}")

    # --- 选品 Top10 命中率（v2 新增） ---
    hr_path = os.path.join(ALGO2_DIR, "algo2_selection_hitrate.csv")
    if os.path.exists(hr_path):
        _, rows = read_csv(hr_path)
        hr_cols = ["level", "strategy", "top_n", "hit_cnt", "hit_rate_pct",
                   "valid_top20_cnt", "valid_candidate_cnt", "note", "top_list",
                   "train_window", "valid_window", "imported_at"]

        def mk_hitrate_full(r):
            return (r["level"], r["strategy"], to_int(r["top_n"]),
                    to_float(r["hit_cnt"]), to_float(r["hit_rate_pct"]),
                    to_int(r["valid_top20_cnt"]), to_int(r["valid_candidate_cnt"]),
                    r["note"], r["top_list"], r["train_window"], r["valid_window"],
                    imported_at)
        n7 = write_table(conn, "algo2_selection_hitrate", "algo2_selection_hitrate.csv",
                         rows, hr_cols, mk_hitrate_full, started, t0)
        print(f"      algo2_selection_hitrate    CSV {n7[0]:>5} / DB {n7[1]:>5}")
    else:
        print("      [跳过] 未找到 algo2_selection_hitrate.csv（命中率表不导入）")
        n7 = (0, 0)

    # 3. 校验：先逐表核对行数与空值，再做跨表业务校验
    print("[4/6] 单表校验（行数 / 主键唯一 / 关键字段非空）...")
    checks = []

    for tbl, csv_n, db_n, key_col, must_cols in [
        ("algo2_forecast_result", n1[0], n1[1], "category",
         ["forecast_week", "predicted_qty"]),
        ("algo2_selection_result", n2[0], n2[1], "product_id",
         ["selection_type", "score_total"]),
        ("algo2_pricing_result", n3[0], n3[1], "product_id",
         ["category", "current_price"]),
        ("algo2_pricing_skipped", n4[0], n4[1], "product_id", ["reason"]),
        ("algo2_offline_experiment", n5[0], n5[1], "category", ["model", "mape_pct"]),
        ("algo2_summary_stats", n6[0], n6[1], "stat_name", ["value_text"]),
        ("algo2_selection_hitrate", n7[0], n7[1], "strategy", ["level", "hit_rate_pct"]),
    ]:
        checks.append((f"{tbl} 行数一致", csv_n == db_n, f"CSV {csv_n} / DB {db_n}"))
        null_sql = (f"SELECT COUNT(*) FROM {tbl} WHERE "
                    + " OR ".join(f"{c} IS NULL" for c in must_cols))
        bad = conn.execute(null_sql).fetchone()[0]
        checks.append((f"{tbl} 关键字段无空值", bad == 0, f"异常行 {bad}"))

    # 抽样核对：每张表取 CSV 首行，确认库内能按主键找到且数值一致
    print("[5/6] 抽样核对 + 跨表业务校验 ...")
    _, f_rows = read_csv(os.path.join(ALGO2_DIR, "algo2_forecast_result.csv"))
    r0 = f_rows[0]
    got = conn.execute(
        "SELECT predicted_qty FROM algo2_forecast_result WHERE category=? AND forecast_week=?",
        (r0["category"], r0["forecast_week"])).fetchone()
    ok = got is not None and abs(got[0] - float(r0["predicted_qty"])) < 1e-9
    checks.append(("预测表抽样核对（首行）", ok, f"{r0['category']} {r0['forecast_week']}"))

    _, s_rows = read_csv(os.path.join(ALGO2_DIR, "algo2_selection_result.csv"))
    r0 = s_rows[0]
    got = conn.execute(
        "SELECT score_total FROM algo2_selection_result WHERE selection_type=? AND rank=?",
        (r0["selection_type"], int(r0["rank"]))).fetchone()
    ok = got is not None and abs(got[0] - float(r0["score_total"])) < 1e-9
    checks.append(("选品表抽样核对（首行）", ok, f"{r0['selection_type']} 第{r0['rank']}名"))

    _, p_rows = read_csv(os.path.join(ALGO2_DIR, "algo2_pricing_result.csv"))
    r0 = p_rows[0]
    got = conn.execute(
        "SELECT current_price FROM algo2_pricing_result WHERE product_id=?",
        (r0["product_id"],)).fetchone()
    ok = got is not None and abs(got[0] - float(r0["current_price"])) < 1e-9
    checks.append(("定价表抽样核对（首行）", ok, r0["product_id"][:12] + "..."))

    _, e_rows = read_csv(os.path.join(ALGO2_DIR, "algo2_offline_experiment.csv"))
    r0 = e_rows[0]
    got = conn.execute(
        "SELECT mape_pct FROM algo2_offline_experiment WHERE category=? AND model=? AND holdout_weeks=?",
        (r0["category"], r0["model"], int(r0["holdout_weeks"]))).fetchone()
    ok = got is not None and abs(got[0] - float(r0["mape_pct"])) < 1e-9
    checks.append(("离线实验抽样核对（首行）", ok, f"{r0['category']} / {r0['model'][:12]}"))

    # --- 跨表业务校验 ---
    # a. 选品商品 = 定价商品（定价以选品为输入，应一一对应）
    sel_cnt = conn.execute("SELECT COUNT(DISTINCT product_id) FROM algo2_selection_result").fetchone()[0]
    pr_cnt = conn.execute("SELECT COUNT(*) FROM algo2_pricing_result").fetchone()[0]
    checks.append(("选品商品数 = 定价商品数", sel_cnt == pr_cnt, f"选品 {sel_cnt} / 定价 {pr_cnt}"))

    orphan = conn.execute(
        """SELECT COUNT(*) FROM algo2_pricing_result p
           WHERE NOT EXISTS (SELECT 1 FROM algo2_selection_result s
                              WHERE s.product_id = p.product_id)"""
    ).fetchone()[0]
    checks.append(("定价商品都能在选品表找到", orphan == 0, f"孤立记录 {orphan}"))

    # b. 无建议价的商品集合 == 定价跳过表的商品集合
    no_price = {r[0] for r in conn.execute(
        "SELECT product_id FROM algo2_pricing_result WHERE suggested_price IS NULL")}
    skipped = {r[0] for r in conn.execute("SELECT product_id FROM algo2_pricing_skipped")}
    checks.append(("无建议价商品 == 定价跳过商品", no_price == skipped,
                   f"无建议价 {len(no_price)} / 跳过表 {len(skipped)}"))

    # c. 汇总统计表里的数字与库内实际统计对得上
    def stat(group, name):
        return conn.execute(
            "SELECT value_num FROM algo2_summary_stats WHERE stat_group=? AND stat_name=?",
            (group, name)).fetchone()[0]

    act_fc = conn.execute("SELECT COUNT(*) FROM algo2_forecast_result").fetchone()[0]
    checks.append(("汇总「预测记录数」与实际一致", stat("预测", "预测记录数") == act_fc,
                   f"汇总 {stat('预测', '预测记录数'):.0f} / 实际 {act_fc}"))

    act_cat = conn.execute("SELECT COUNT(DISTINCT category) FROM algo2_forecast_result").fetchone()[0]
    checks.append(("汇总「预测品类数」与实际一致", stat("预测", "预测品类数") == act_cat,
                   f"汇总 {stat('预测', '预测品类数'):.0f} / 实际 {act_cat}"))

    act_sel = conn.execute("SELECT COUNT(*) FROM algo2_selection_result").fetchone()[0]
    checks.append(("汇总「输出商品数」与实际一致", stat("选品", "输出商品数") == act_sel,
                   f"汇总 {stat('选品', '输出商品数'):.0f} / 实际 {act_sel}"))

    act_priced = conn.execute(
        "SELECT COUNT(*) FROM algo2_pricing_result WHERE suggested_price IS NOT NULL").fetchone()[0]
    checks.append(("汇总「可给建议价」与实际一致", stat("定价", "可给建议价") == act_priced,
                   f"汇总 {stat('定价', '可给建议价'):.0f} / 实际 {act_priced}"))

    # d. 每个品类都应有 4 个模型的离线实验记录
    bad_cat = conn.execute(
        """SELECT COUNT(*) FROM (SELECT category FROM algo2_offline_experiment
                                 GROUP BY category HAVING COUNT(*) <> 4)"""
    ).fetchone()[0]
    checks.append(("每个品类均有 4 个模型记录", bad_cat == 0, f"异常品类 {bad_cat}"))

    # e. 导入日志：本次 6 张表全部 SUCCESS
    fail_logs = conn.execute(
        "SELECT COUNT(*) FROM algo_import_log WHERE algo_name='算法2' AND status<>'SUCCESS'"
    ).fetchone()[0]
    checks.append(("导入日志无失败记录", fail_logs == 0, f"失败 {fail_logs} 条"))

    # 4. 输出校验报告
    print("[6/6] 校验结果汇总:")
    all_ok = True
    for name, ok, info in checks:
        all_ok = all_ok and ok
        print(f"      [{'PASS' if ok else 'FAIL'}] {name}: {info}")

    finished = datetime.now()
    conn.execute(
        """INSERT INTO algo_import_log
           (algo_name, table_name, source_file, csv_rows, db_rows,
            status, message, started_at, finished_at, duration_sec)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("算法2", "(汇总)", "7 个 CSV",
         n1[0] + n2[0] + n3[0] + n4[0] + n5[0] + n6[0] + n7[0],
         n1[1] + n2[1] + n3[1] + n4[1] + n5[1] + n6[1] + n7[1],
         "SUCCESS" if all_ok else "WARN",
         "; ".join(f"{n}:{'PASS' if ok else 'FAIL'}" for n, ok, _ in checks),
         started.strftime("%Y-%m-%d %H:%M:%S"),
         finished.strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 2)),
    )
    conn.commit()
    conn.close()

    total = n1[1] + n2[1] + n3[1] + n4[1] + n5[1] + n6[1] + n7[1]
    print(f"\n完成，共入库 {total:,} 行，耗时 {time.time() - t0:.2f} 秒。数据库文件: {DB_PATH}")
    if not all_ok:
        print("注意：有校验项未通过，请检查上方 [FAIL] 项。")
        sys.exit(2)


if __name__ == "__main__":
    main()

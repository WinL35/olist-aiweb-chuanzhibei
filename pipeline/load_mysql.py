# -*- coding: utf-8 -*-
"""
将 cleaned/*.csv 导入 MySQL olist_db，并计算 RFM 评分 + K-Means 分群写入 fact_rfm。
用法: python load_mysql.py
依赖: pymysql, pandas, scikit-learn, sqlalchemy
"""
import os
import sys
import time
import pymysql
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

DB = config.DB_CONFIG
CLEANED = Path(config.CLEANED_DIR)
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

# (csv 文件名, 表名, 是否解析日期列)
TABLES = [
    ("dim_category_translation.csv", "dim_category_translation", []),
    ("dim_geolocation.csv", "dim_geolocation", []),
    ("dim_customer.csv", "dim_customer", []),
    ("dim_seller.csv", "dim_seller", []),
    ("dim_product.csv", "dim_product", []),
    ("fact_order.csv", "fact_order",
     ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
      "order_delivered_customer_date", "order_estimated_delivery_date"]),
    ("fact_order_item.csv", "fact_order_item", ["shipping_limit_date"]),
    ("fact_order_payment_agg.csv", "fact_order_payment_agg", []),
    ("fact_review.csv", "fact_review", ["review_creation_date"]),
    ("fact_order_master.csv", "fact_order_master",
     ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
      "order_delivered_customer_date", "order_estimated_delivery_date",
      "review_creation_date", "purchase_date"]),
    ("fact_sales.csv", "fact_sales", ["shipping_limit_date", "order_purchase_timestamp", "purchase_date"]),
    ("fact_rfm.csv", "fact_rfm", []),
    ("dim_category_summary.csv", "dim_category_summary", []),
]


def run_schema(cursor):
    sql = SCHEMA.read_text(encoding="utf-8")
    # 先剔除整行注释, 再按分号拆分
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    sql_clean = "\n".join(lines)
    stmts = [s.strip() for s in sql_clean.split(";") if s.strip()]
    for stmt in stmts:
        cursor.execute(stmt)
    print(f"[schema] 执行 {len(stmts)} 条 DDL 语句完成")


def load_table(cursor, csv_name, table, date_cols):
    p = CLEANED / csv_name
    df = pd.read_csv(p, parse_dates=date_cols if date_cols else False)
    # 整表转 object 并把所有 NaN/NaT/None 统一为 Python None (pymysql 仅识别 None)
    df = df.astype(object).where(pd.notnull(df), None)
    cols = ",".join([f"`{c}`" for c in df.columns])
    placeholders = ",".join(["%s"] * len(df.columns))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    BATCH = 3000
    t0 = time.time()
    for i in range(0, len(rows), BATCH):
        cursor.executemany(sql, rows[i:i + BATCH])
    print(f"  -> {table}: {len(rows)} 行, {time.time()-t0:.1f}s")
    return len(rows)


def compute_rfm(cursor):
    """读取 fact_rfm 的 R/F/M，计算分箱评分 + K-Means 分群并回写。"""
    # 与算法1 共用同一套打分函数（单一事实来源，避免两处口径漂移）
    try:
        from algo1_model import make_scorer, f_score_by_threshold
    except ImportError:                    # 以包形式导入时
        from pipeline.algo1_model import make_scorer, f_score_by_threshold

    cursor.execute("SELECT customer_unique_id, recency, frequency, monetary FROM fact_rfm")
    rows = cursor.fetchall()
    rfm = pd.DataFrame(rows, columns=["customer_unique_id", "recency", "frequency", "monetary"])
    # 分箱评分(1-5): R 越小分越高, M 越大分越高
    # ⚠️ 必须用 algo1 的"分位数值边界"法（quintile_boundaries），不能用
    #    qcut(rank(method="first"))：后者按排名均分，会把【同一金额】的客户
    #    拆进不同分箱（实测 m_score 有 2,152 行与算法1 不一致，例如同样消费
    #    69.90 元的客户被标成 3 分和 2 分两种）。业务上相同消费额应同分。
    rec = rfm["recency"].tolist()
    mon = rfm["monetary"].astype(float).tolist()
    s_r = make_scorer(rec, higher_is_better=False)
    s_m = make_scorer(mon, higher_is_better=True)
    rfm["r_score"] = [s_r(v) for v in rec]
    rfm["m_score"] = [s_m(v) for v in mon]
    # F 分同样复用算法1 的业务阈值（96.95% 用户 frequency==1，五分位会失真）
    rfm["f_score"] = [f_score_by_threshold(v) for v in rfm["frequency"]]
    # K-Means: 对偏态特征做 log 变换后标准化
    X = np.log1p(rfm[["recency", "frequency", "monetary"]].astype(float))
    Xs = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    rfm["cluster"] = km.fit_predict(Xs)
    # 按各簇 monetary 均值排序, 映射语义标签
    order = rfm.groupby("cluster")["monetary"].mean().sort_values(ascending=False).index.tolist()
    label_map = {}
    names = ["高价值客户", "中价值客户", "潜力成长客户", "流失风险客户"]
    for i, c in enumerate(order):
        label_map[c] = names[i]
    rfm["rfm_segment"] = rfm["cluster"].map(label_map)
    # 回写
    sql = ("UPDATE fact_rfm SET r_score=%s, f_score=%s, m_score=%s, rfm_segment=%s "
           "WHERE customer_unique_id=%s")
    data = [(int(r.r_score), int(r.f_score), int(r.m_score), r.rfm_segment, r.customer_unique_id)
            for r in rfm.itertuples(index=False)]
    BATCH = 3000
    for i in range(0, len(data), BATCH):
        cursor.executemany(sql, data[i:i + BATCH])
    print(f"\n[RFM] K-Means 分群完成:")
    seg = rfm["rfm_segment"].value_counts()
    for k, v in seg.items():
        print(f"    {k}: {v} 人 ({v/len(rfm)*100:.1f}%)")
    return rfm


def main():
    print("=" * 60)
    print("MySQL 数据导入  olist_db")
    print("=" * 60)
    conn = pymysql.connect(host=DB["host"], port=DB["port"], user=DB["user"],
                           password=DB["password"], charset=DB["charset"])
    try:
        conn.autocommit(False)
        cur = conn.cursor()
        run_schema(cur)
        conn.commit()
        total = 0
        for csv_name, table, dcols in TABLES:
            n = load_table(cur, csv_name, table, dcols)
            total += n
            conn.commit()
        print(f"\n[完成] 共导入 {total} 行")
        # fact_rfm 表此时只有基础 R/F/M(由 fact_rfm.csv 导入), 计算评分分群回写
        compute_rfm(cur)
        conn.commit()
        # 校验
        print("\n[校验] 各表行数:")
        for _, table, _ in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"    {table}: {cur.fetchone()[0]}")
    finally:
        conn.close()
    print("\n导入完成。")


if __name__ == "__main__":
    main()

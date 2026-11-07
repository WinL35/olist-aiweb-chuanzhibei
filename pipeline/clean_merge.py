# -*- coding: utf-8 -*-
"""Olist 原始数据清洗与宽表合并
=================================

【在整条链路中的位置】
    Dataset/*.csv  --本脚本-->  cleaned/*.csv  --一键导入主库.py-->  MySQL olist_db
                                              --algo1_model.py-->  算法1/*.csv
                                              --algo2_model.py-->  算法2/*.csv

【输入】项目根目录 Dataset/ 下的 9 个 Kaggle 原始文件
    olist_customers_dataset.csv          olist_geolocation_dataset.csv
    olist_order_items_dataset.csv        olist_order_payments_dataset.csv
    olist_order_reviews_dataset.csv      olist_orders_dataset.csv
    olist_products_dataset.csv           olist_sellers_dataset.csv
    product_category_name_translation.csv

【输出】项目根目录 cleaned/ 下 13 个 csv + data_quality_report.txt
    fact_order_master / fact_sales / fact_rfm / fact_order / fact_order_item /
    fact_order_payment_agg / fact_review / dim_customer / dim_seller /
    dim_product / dim_geolocation / dim_category_summary / dim_category_translation

【用法】
    python pipeline/clean_merge.py        # 会提示原始数据是否齐全
    （原始数据约 100 MB，不进交付包；只有需要从零重建 cleaned/ 时才跑本脚本）

【本版相对早期版本修复的问题】
    1. 未评价订单的 review_score 不再填 0。0 不是合法星级（合法值 1~5），
       早期用 fillna(0) 让 768 个未评价订单变成"0 星"，把平均评分从 4.086
       拉低到 4.055，前端评分分布还多出一根"0 星"柱。现在保持空值，
       入库即 NULL，聚合（AVG 等）自动忽略。
    2. 支付表中被丢弃的 not_defined 订单会打印并写入质量报告（实测 4 单），
       避免下游出现"订单金额莫名变 0"却查不到原因。
    3. purchase_week 仅是 ISO 周序号，跨年时不能单独排序（1 月首周会与上一年
       第 1 周混同）；按周聚合请用 purchase_date 现算 ISO 年周（'%x-W%v'），
       app/dashboard.py 已按此处理。
    4. 原始数据缺失时给出明确提示和放置说明，不再直接抛 FileNotFoundError。
    5. 输出前做"列契约校验"：与现有 cleaned/*.csv 表头不一致时直接报错，
       防止悄悄改坏下游 schema。
    6. 质量报告增加行数、空值率与本次修复说明。
"""
import unicodedata
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent   # 项目根目录
RAW = BASE / "Dataset"
OUT = BASE / "cleaned"


def _norm_city(s: pd.Series) -> pd.Series:
    """城市名规范化：去空格 → 小写 → 去重音（"são paulo" → "sao paulo"）。

    原始数据 7.3 万行带重音，统一成 ASCII 可避免不同终端/编码下显示成乱码，
    也与项目现有 cleaned 数据保持一致。
    """
    def _f(v):
        if not isinstance(v, str):
            return v
        return unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode()
    return s.astype("string").str.strip().str.lower().map(_f)

REQUIRED = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


def check_raw() -> bool:
    """检查原始数据是否齐全，缺什么列什么。"""
    OUT.mkdir(exist_ok=True)
    if not RAW.is_dir():
        print("[错误] 找不到原始数据目录:", RAW)
        print("       本项目不附带原始数据（约 100 MB）。如需从零重建 cleaned/：")
        print("       1) 下载 Kaggle 'Brazilian E-Commerce Public Dataset by Olist'")
        print("       2) 把 9 个 csv 解压到 Dataset/ 目录")
        print("       3) 重新运行 python pipeline/clean_merge.py")
        print("       注意：直接使用仓库里已有的 cleaned/*.csv 则无需本脚本。")
        return False
    missing = [f for f in REQUIRED if not (RAW / f).exists()]
    if missing:
        print("[错误] Dataset/ 下缺少文件：")
        for m in missing:
            print("       -", m)
        return False
    return True


def fix_dates(df: pd.DataFrame, columns) -> pd.DataFrame:
    """统一日期解析：兼容 '2017/01/01' 与 '2017-01-01' 两种写法。"""
    for c in columns:
        df[c] = pd.to_datetime(
            df[c].astype("string").str.replace("/", "-", regex=False),
            errors="coerce",
        )
    return df


def load_raw():
    print("读取原始数据 ...")
    data = {
        "customers": pd.read_csv(RAW / "olist_customers_dataset.csv"),
        "geolocation": pd.read_csv(RAW / "olist_geolocation_dataset.csv"),
        "order_items": pd.read_csv(RAW / "olist_order_items_dataset.csv"),
        "payments": pd.read_csv(RAW / "olist_order_payments_dataset.csv"),
        "reviews": pd.read_csv(RAW / "olist_order_reviews_dataset.csv"),
        "orders": pd.read_csv(RAW / "olist_orders_dataset.csv"),
        "products": pd.read_csv(RAW / "olist_products_dataset.csv"),
        "sellers": pd.read_csv(RAW / "olist_sellers_dataset.csv"),
        "translation": pd.read_csv(RAW / "product_category_name_translation.csv",
                                   encoding="utf-8-sig"),
    }
    for k, v in data.items():
        print(f"  {k:<12} {v.shape[0]:>8,} 行 × {v.shape[1]} 列")
    return data


def main() -> int:
    if not check_raw():
        return 1

    d = load_raw()
    customers, geolocation = d["customers"], d["geolocation"]
    order_items, payments, reviews = d["order_items"], d["payments"], d["reviews"]
    orders, products, sellers = d["orders"], d["products"], d["sellers"]
    translation = d["translation"]

    # ---------- 订单表 ----------
    orders = fix_dates(orders, [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ])
    orders["order_status"] = orders["order_status"].astype("string").str.strip().str.lower()
    n_before = len(orders)
    orders = orders.drop_duplicates("order_id")
    if n_before != len(orders):
        print(f"  订单表去重：{n_before:,} → {len(orders):,}")

    # ---------- 订单商品表 ----------
    order_items["price"] = pd.to_numeric(order_items["price"], errors="coerce")
    order_items["freight_value"] = pd.to_numeric(order_items["freight_value"], errors="coerce")
    order_items["shipping_limit_date"] = pd.to_datetime(
        order_items["shipping_limit_date"], errors="coerce")
    order_items = order_items.dropna(subset=["price", "freight_value"])
    order_items = order_items.drop_duplicates(["order_id", "order_item_id"])
    order_items["item_total"] = order_items["price"] + order_items["freight_value"]

    # ---------- 商品表 ----------
    products["product_category_name"] = products["product_category_name"].fillna("unknown")
    for c in ["product_name_lenght", "product_description_lenght", "product_photos_qty",
              "product_weight_g", "product_length_cm", "product_height_cm",
              "product_width_cm"]:
        products[c] = products[c].fillna(products[c].median())
    products = products.merge(translation, on="product_category_name", how="left")
    products["product_category_name_english"] = (
        products["product_category_name_english"].fillna(products["product_category_name"])
    )

    # ---------- 客户 / 卖家 ----------
    # 【修复】州代码保持原始大写（SP/RJ/...），不能 .lower()：
    #   前端地区地图与 region_map 接口都按 "SP" 这类大写代码查表，lower 后会画不出图。
    #   城市则统一「去空格 + 小写 + 去重音」（原始数据有 7.3 万行是 "são paulo"）。
    customers = customers.drop_duplicates("customer_id").copy()
    sellers = sellers.drop_duplicates("seller_id").copy()
    for df, city_col, state_col in [(customers, "customer_city", "customer_state"),
                                    (sellers, "seller_city", "seller_state")]:
        df[city_col] = _norm_city(df[city_col])
        df[state_col] = df[state_col].astype("string").str.strip()

    # ---------- 支付表 ----------
    payments["payment_type"] = payments["payment_type"].astype("string").str.strip().str.lower()
    pay_dropped_orders = int(payments.loc[payments["payment_type"] == "not_defined",
                                          "order_id"].nunique())
    payments = payments[payments["payment_type"] != "not_defined"].copy()
    payments["payment_value"] = pd.to_numeric(payments["payment_value"], errors="coerce")
    payments = payments.dropna(subset=["payment_value"])
    if pay_dropped_orders:
        print(f"  支付表：丢弃 payment_type=not_defined 的订单 {pay_dropped_orders} 个"
              f"（其支付汇总将缺失，宽表金额按 0 处理）")

    pay_agg = payments.groupby("order_id", as_index=False).agg(
        payment_value_total=("payment_value", "sum"),
        payment_sequential_max=("payment_sequential", "max"),
        payment_installments_max=("payment_installments", "max"),
        primary_payment_type=("payment_type", "first"),
        n_payment_methods=("payment_type", "nunique"),
    )

    # ---------- 评价表 ----------
    reviews = fix_dates(reviews, ["review_creation_date", "review_answer_timestamp"])
    reviews["review_comment_message"] = reviews["review_comment_message"].fillna("")
    reviews["review_comment_title"] = reviews["review_comment_title"].fillna("")
    reviews["has_comment"] = (reviews["review_comment_message"].str.len() > 0).astype(int)
    # 同一订单多条评价时保留"最晚回复"的那条
    reviews = (reviews.sort_values("review_answer_timestamp", na_position="first")
               .drop_duplicates("order_id", keep="last"))
    reviews_order = reviews[["order_id", "review_score", "has_comment", "review_creation_date"]]

    # ---------- 订单商品汇总 ----------
    item_agg = order_items.groupby("order_id", as_index=False).agg(
        n_items=("order_item_id", "count"),
        gmv=("price", "sum"),
        total_freight=("freight_value", "sum"),
        order_revenue=("item_total", "sum"),
    )

    # ---------- 订单宽表 ----------
    om = (orders
          .merge(customers, on="customer_id", how="left")
          .merge(pay_agg, on="order_id", how="left")
          .merge(reviews_order, on="order_id", how="left")
          .merge(item_agg, on="order_id", how="left"))

    for c in ["gmv", "total_freight", "order_revenue", "payment_value_total"]:
        om[c] = om[c].fillna(0)
    om["n_items"] = om["n_items"].fillna(0).astype(int)

    # 【修复】未评价订单保持空值（入库为 NULL），不填 0 星。
    #   Int64 是 pandas 的可空整型，写 csv 时整数写 "4"、缺失写空，不会变成 "4.0"。
    om["review_score"] = om["review_score"].astype("Int64")
    om["has_comment"] = om["has_comment"].fillna(0).astype(int)
    om["primary_payment_type"] = om["primary_payment_type"].fillna("unknown")

    om["purchase_date"] = om["order_purchase_timestamp"].dt.date
    om["purchase_year"] = om["order_purchase_timestamp"].dt.year
    om["purchase_month"] = om["order_purchase_timestamp"].dt.to_period("M").astype(str)
    # 仅 ISO 周序号；跨年聚合请用 purchase_date 现算 '%x-W%v'（见文件头说明第 3 条）
    om["purchase_week"] = om["order_purchase_timestamp"].dt.isocalendar().week.astype("Int64")
    om["purchase_weekday"] = om["order_purchase_timestamp"].dt.dayofweek
    om["purchase_hour"] = om["order_purchase_timestamp"].dt.hour
    om["delivery_days"] = (om["order_delivered_customer_date"]
                           - om["order_purchase_timestamp"]).dt.days
    om["approve_hours"] = ((om["order_approved_at"] - om["order_purchase_timestamp"])
                           .dt.total_seconds() / 3600)
    om["delivery_vs_estimated_days"] = (om["order_delivered_customer_date"]
                                        - om["order_estimated_delivery_date"]).dt.days
    print(f"订单宽表：{om.shape[0]:,} 行 × {om.shape[1]} 列")

    # ---------- 销售明细表 ----------
    sales = (order_items
             .merge(products[["product_id", "product_category_name",
                              "product_category_name_english"]], on="product_id", how="left")
             .merge(sellers[["seller_id", "seller_city", "seller_state"]],
                    on="seller_id", how="left")
             .merge(orders[["order_id", "customer_id", "order_purchase_timestamp",
                            "order_status"]], on="order_id", how="left")
             .merge(customers[["customer_id", "customer_unique_id", "customer_city",
                               "customer_state"]], on="customer_id", how="left"))
    sales["purchase_date"] = sales["order_purchase_timestamp"].dt.date
    sales["purchase_year"] = sales["order_purchase_timestamp"].dt.year
    sales["purchase_month"] = sales["order_purchase_timestamp"].dt.to_period("M").astype(str)
    iso = sales["order_purchase_timestamp"].dt.isocalendar()
    sales["iso_week"] = iso.week.astype("Int64")
    sales["iso_year"] = iso.year.astype("Int64")
    sales["weekday"] = sales["order_purchase_timestamp"].dt.dayofweek
    sales["hour"] = sales["order_purchase_timestamp"].dt.hour
    sales["year_week"] = (sales["iso_year"].astype("string") + "-W"
                          + sales["iso_week"].astype("string").str.zfill(2))
    print(f"销售明细表：{sales.shape[0]:,} 行 × {sales.shape[1]} 列")

    # ---------- RFM ----------
    max_date = orders["order_purchase_timestamp"].max()
    rfm = sales.groupby("customer_unique_id", as_index=False).agg(
        last_purchase=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("price", "sum"),
    )
    rfm["recency"] = (max_date - rfm["last_purchase"]).dt.days
    rfm = rfm[["customer_unique_id", "recency", "frequency", "monetary"]]
    rfm["monetary"] = rfm["monetary"].round(2)     # 与打分口径保持一致（见 load_mysql）
    print(f"RFM：{len(rfm):,} 个用户（基准日 {max_date.date()}）")

    # ---------- 品类 / 地理 ----------
    cat = (sales.groupby("product_category_name_english", as_index=False)
           .agg(order_cnt=("order_id", "nunique"), item_cnt=("order_item_id", "count"),
                gmv=("price", "sum"), avg_price=("price", "mean"))
           .sort_values("gmv", ascending=False))

    geolocation["geolocation_lat"] = pd.to_numeric(geolocation["geolocation_lat"], errors="coerce")
    geolocation["geolocation_lng"] = pd.to_numeric(geolocation["geolocation_lng"], errors="coerce")
    geolocation = geolocation.dropna(subset=["geolocation_lat", "geolocation_lng"])
    geolocation["geolocation_city"] = _norm_city(geolocation["geolocation_city"])
    geo_agg = (geolocation.groupby("geolocation_zip_code_prefix", as_index=False)
               .agg(geolocation_lat=("geolocation_lat", "mean"),
                    geolocation_lng=("geolocation_lng", "mean"),
                    geolocation_city=("geolocation_city", "first"),
                    geolocation_state=("geolocation_state", "first")))

    outputs = {
        "fact_order_master": om, "fact_sales": sales, "fact_rfm": rfm,
        "dim_category_summary": cat, "dim_customer": customers, "dim_seller": sellers,
        "dim_product": products, "dim_geolocation": geo_agg,
        "fact_order_payment_agg": pay_agg, "fact_review": reviews_order,
        "fact_order": orders, "fact_order_item": order_items,
        "dim_category_translation": translation,
    }

    # ---------- 列契约校验：表头必须与现有 cleaned 一致 ----------
    problems = []
    for name, df in outputs.items():
        target = OUT / f"{name}.csv"
        if target.exists():
            old_cols = pd.read_csv(target, nrows=0).columns.tolist()
            if old_cols != list(df.columns):
                problems.append((name, set(old_cols) ^ set(df.columns)))
    if problems:
        print("\n[错误] 列契约不一致，已中止写入（避免改坏下游 schema）：")
        for name, diff in problems:
            print(f"  {name}: 差异列 {sorted(diff)}")
        return 2

    # ---------- 写出 ----------
    for name, df in outputs.items():
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
        print(f"  已输出 {name}.csv：{len(df):,} 行")

    # ---------- 质量报告 ----------
    n_orders = orders["order_id"].nunique()
    n_customers = customers["customer_unique_id"].nunique()
    total_gmv = sales["price"].sum()
    delivered_rate = (orders["order_status"] == "delivered").sum() / n_orders * 100 if n_orders else 0
    repurchase_rate = (rfm["frequency"] > 1).sum() / n_customers * 100 if n_customers else 0
    null_reviews = int(om["review_score"].isna().sum())
    report = [
        "Olist 数据质量报告",
        "=" * 40,
        f"生成脚本：pipeline/clean_merge.py",
        f"订单数：{n_orders:,}",
        f"客户数（customer_unique_id 去重）：{n_customers:,}",
        f"商品数：{products['product_id'].nunique():,}",
        f"品类数（英文名去重）：{products['product_category_name_english'].nunique()}",
        f"GMV（商品金额合计）：{total_gmv:,.2f} BRL",
        f"客单价：{total_gmv / n_orders:,.2f} BRL" if n_orders else "客单价：0",
        f"送达率：{delivered_rate:.2f}%",
        f"复购率：{repurchase_rate:.2f}%",
        f"时间范围：{orders['order_purchase_timestamp'].min()} 至 "
        f"{orders['order_purchase_timestamp'].max()}",
        f"订单宽表：{om.shape[0]:,} 行 × {om.shape[1]} 列",
        f"销售明细表：{sales.shape[0]:,} 行 × {sales.shape[1]} 列",
        "",
        "数据质量说明：",
        f"  - 未评价订单 {null_reviews:,} 单，review_score 存为 NULL（不是 0 星）",
        f"  - payment_type=not_defined 的订单 {pay_dropped_orders} 个，支付汇总缺失、金额按 0 计",
        "  - purchase_week 仅为 ISO 周序号，跨年聚合请由 purchase_date 现算 '%x-W%v'",
        "",
        "订单表缺失值统计：",
        orders.isnull().sum().to_string(),
        "",
        "销售明细表缺失值统计：",
        sales.isnull().sum().to_string(),
    ]
    (OUT / "data_quality_report.txt").write_text("\n".join(report), encoding="utf-8")

    print("\n完成，已写入 cleaned/ 与 data_quality_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
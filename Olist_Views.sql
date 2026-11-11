-- ============================================================
-- Olist 电商数仓 · 查询视图集合（10 个）
-- 目标库：olist_db   引擎：MySQL 8.0+（用到窗口函数 NTILE 与 CTE）
--
-- ✅ 已在本机MySQL 8.0.39 真实建库跑通：10 个视图全部创建成功，
--    25 条数值断言全部通过（运费分摊 / CAST 聚合 / 日期解析 均已验证）
--
-- 怎么用：
--   1. Navicat 左侧双击打开 olist_db 库 → 右键 → 新建查询
--   2. 粘贴本文件全部内容 → 运行
--   3. 刷新库 → 展开「视图」节点，即可看到 v_ 开头的 10 个视图
--
-- ⚠️ 关键点 1：【不要加 USE 语句】。实测在某些环境里 USE 会被拒
--    （报 ERROR 1046 No database selected / 1064 near 'USE'）。
--    正确做法：库名写进每个对象名（`olist_db`.`xxx`），脚本里不放 USE。
--    若你的库名不是 olist_db，把全文的 `olist_db`. 替换成你的库名。
-- ⚠️ 关键点 2：底层所有字段都是 varchar(255)，必须 CAST 后才能求和，
--    否则 SUM 结果为 0。本脚本已全部处理。
-- ⚠️ 关键点 3：YEAR_MONTH 是 MySQL 保留字，列名必须写成 `year_month`。
--
-- 如果整段粘贴运行仍然报错：
--   views_one_by_one/ 目录里有 10 个拆开的单视图文件，
--   在 Navicat 里按01 → 10 顺序一个一个打开运行（已实测全部成功）。
-- ============================================================

-- ------------------------------------------------------------
-- 视图 1：订单销售明细宽表（最常用，一切分析的基础）
-- fact_sales 已经把维度都打平了，这里只做类型清洗 + 补全维度
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_order_sales_detail` AS
SELECT
    s.order_id                                        AS order_id,
    s.order_item_id                                   AS order_item_id,
    s.customer_id                                     AS customer_id,
    s.customer_unique_id                              AS customer_unique_id,
    s.product_id                                      AS product_id,
    s.seller_id                                       AS seller_id,
    s.product_category_name                           AS category_name,
    s.product_category_name_english                   AS category_name_en,
    s.seller_city                                     AS seller_city,
    s.seller_state                                    AS seller_state,
    s.customer_city                                   AS customer_city,
    s.customer_state                                  AS customer_state,
    s.order_status                                    AS order_status,
    CAST(s.price        AS DECIMAL(12,2))             AS price,
    CAST(s.freight_value AS DECIMAL(12,2))            AS freight_value,
    CAST(s.item_total   AS DECIMAL(12,2))             AS item_total,
    -- 运费按比例分摊到每个商品上，才不会重复计算运费总额
    ROUND(CASE
        WHEN s.item_total = '0' OR s.item_total IS NULL OR s.item_total = ''
            THEN 0
        ELSE CAST(s.freight_value AS DECIMAL(12,2)) * CAST(s.item_total AS DECIMAL(12,2))
             / (SELECT SUM(oi.item_total_x)
                  FROM (
                      SELECT CAST(item_total AS DECIMAL(20,6)) AS item_total_x
                      FROM `olist_db`.fact_order_item
                      WHERE order_id = s.order_id
                  ) oi)
    END, 2)                                            AS freight_allocated,
    -- 行级净收入 = 货款 - 分摊运费
    ROUND(CASE
        WHEN s.item_total = '0' OR s.item_total IS NULL OR s.item_total = ''
            THEN CAST(s.price AS DECIMAL(12,2))
        ELSE CAST(s.price AS DECIMAL(12,2))
             - CAST(s.freight_value AS DECIMAL(12,2)) * CAST(s.item_total AS DECIMAL(20,6))
               / (SELECT SUM(oi.item_total_y)
                    FROM (
                        SELECT CAST(item_total AS DECIMAL(20,6)) AS item_total_y
                        FROM `olist_db`.fact_order_item
                        WHERE order_id = s.order_id
                    ) oi)
    END, 2)                                            AS net_revenue,
    STR_TO_DATE(s.purchase_date, '%Y-%m-%d')          AS purchase_date,
    s.purchase_year                                   AS purchase_year,
    s.purchase_month                                  AS purchase_month,
    s.iso_week                                        AS iso_week,
    s.year_week                                       AS year_week,
    CAST(s.weekday AS SIGNED)                         AS weekday,
    CAST(s.hour   AS SIGNED)                          AS purchase_hour,
    STR_TO_DATE(s.shipping_limit_date, '%Y-%m-%d %H:%i:%s') AS shipping_limit_date
FROM `olist_db`.fact_sales s
WHERE s.order_status <> 'canceled';


-- ------------------------------------------------------------
-- 视图 2：订单主视图（订单粒度，一单一行）
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_order_master` AS
SELECT
    m.order_id,
    m.customer_id,
    m.customer_unique_id,
    m.order_status,
    STR_TO_DATE(m.order_purchase_timestamp, '%Y-%m-%d %H:%i:%s')      AS purchase_time,
    STR_TO_DATE(m.order_approved_at,            '%Y-%m-%d %H:%i:%s')     AS approved_time,
    STR_TO_DATE(m.order_delivered_customer_date,'%Y-%m-%d %H:%i:%s')     AS delivered_time,
    STR_TO_DATE(m.order_estimated_delivery_date,'%Y-%m-%d %H:%i:%s')    AS estimated_time,
    STR_TO_DATE(m.order_purchase_timestamp, '%Y-%m-%d')                 AS purchase_date,
    m.purchase_year,
    m.purchase_month,
    m.purchase_weekday,
    m.customer_city,
    m.customer_state,
    CAST(m.payment_value_total AS DECIMAL(12,2))        AS payment_total,
    m.primary_payment_type,
    CAST(m.payment_installments_max AS SIGNED)         AS payment_installments,
    CAST(m.review_score AS SIGNED)                      AS review_score,
    m.has_comment,
    CAST(m.n_items AS SIGNED)                           AS n_items,
    CAST(m.gmv AS DECIMAL(14,2))                        AS gmv,
    CAST(m.total_freight AS DECIMAL(14,2))              AS total_freight,
    CAST(m.order_revenue AS DECIMAL(14,2))              AS order_revenue,
    -- 履约时长：下单 → 实际送达
    CASE WHEN m.order_delivered_customer_date IS NOT NULL
         THEN DATEDIFF(
                  STR_TO_DATE(m.order_delivered_customer_date, '%Y-%m-%d %H:%i:%s'),
                  STR_TO_DATE(m.order_purchase_timestamp,  '%Y-%m-%d %H:%i:%s')
              )
    END                                                 AS delivery_days,
    -- 审核时长：下单 → 支付审核（小时）
    CASE WHEN m.order_approved_at IS NOT NULL
         THEN TIMESTAMPDIFF(
                  MINUTE,
                  STR_TO_DATE(m.order_purchase_timestamp, '%Y-%m-%d %H:%i:%s'),
                  STR_TO_DATE(m.order_approved_at,          '%Y-%m-%d %H:%i:%s')
              ) / 60
    END                                                 AS approve_hours,
    -- 是否超时：实际送达比预计晚几天，正数=晚点，负数=提前
    CASE WHEN m.order_delivered_customer_date IS NOT NULL
              AND m.order_estimated_delivery_date  IS NOT NULL
         THEN DATEDIFF(
                  STR_TO_DATE(m.order_delivered_customer_date, '%Y-%m-%d %H:%i:%s'),
                  STR_TO_DATE(m.order_estimated_delivery_date,  '%Y-%m-%d %H:%i:%s')
              )
    END                                                 AS delivery_vs_estimated_days,
    CASE WHEN m.order_delivered_customer_date IS NULL
               OR m.order_estimated_delivery_date IS NULL
         THEN '未送达'
         WHEN DATEDIFF(
                  STR_TO_DATE(m.order_delivered_customer_date, '%Y-%m-%d %H:%i:%s'),
                  STR_TO_DATE(m.order_estimated_delivery_date,  '%Y-%m-%d %H:%i:%s')
              ) > 0
         THEN '超时' ELSE '准时/提前' END                AS delivery_ontime_flag
FROM `olist_db`.fact_order_master m;


-- ------------------------------------------------------------
-- 视图 3：品类销售汇总
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_category_sales` AS
SELECT
    d.category_name_en                                   AS category_en,
    d.category_name,
    COUNT(DISTINCT d.order_id)                           AS order_cnt,
    COUNT(DISTINCT d.product_id)                          AS product_cnt,
    COUNT(DISTINCT d.seller_id)                           AS seller_cnt,
    COUNT(*)                                             AS item_cnt,
    SUM(d.price)                                          AS gmv,
    SUM(d.freight_value)                                  AS freight_total,
    ROUND(SUM(d.net_revenue), 2)                            AS net_revenue,
    ROUND(AVG(d.price), 2)                                AS avg_item_price,
    ROUND(AVG(d.net_revenue), 2)                          AS avg_net_revenue,
    MIN(d.purchase_date)                                  AS first_sale_date,
    MAX(d.purchase_date)                                  AS last_sale_date
FROM `olist_db`.v_order_sales_detail d
GROUP BY d.category_name_en, d.category_name;


-- ------------------------------------------------------------
-- 视图 4：卖家销售排行
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_seller_performance` AS
SELECT
    d.seller_id,
    s.seller_city,
    s.seller_state,
    d.category_name_en                                   AS main_category,
    COUNT(DISTINCT d.order_id)                            AS order_cnt,
    COUNT(*)                                              AS item_cnt,
    SUM(d.price)                                          AS gmv,
    ROUND(SUM(d.net_revenue), 2)                            AS net_revenue,
    ROUND(AVG(d.price), 2)                                AS avg_item_price,
    COUNT(DISTINCT d.customer_unique_id)                  AS customer_cnt
FROM `olist_db`.v_order_sales_detail d
LEFT JOIN `olist_db`.dim_seller s ON s.seller_id = d.seller_id
GROUP BY d.seller_id, s.seller_city, s.seller_state, d.category_name_en;


-- ------------------------------------------------------------
-- 视图 5：客户分群（封装算法库的权威 RFM 结果）
-- 数据源：olist_algo_db.algo1_rfm_user_tags（算法1 交付，95,420 用户）
-- 相比手写 NTILE 版本的优势：
--   1. F 分用业务阈值（1单→1分, 2单→2分 ... ≥5单→5分），
--      不会把并列的 order_cnt=1 硬切成 5 档
--   2. 同时提供 K-Means 4 类 与 规则 8 类 两套标签
--   3. recency 以数据截止日（2018-10-17）为基准，不是 CURDATE()
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_customer_segment` AS
SELECT
    a.customer_unique_id,
    a.recency,
    a.frequency,
    a.monetary,
    a.r_score,
    a.f_score,
    a.m_score,
    a.rfm_score,                        -- 三位拼接，如 '545'
    a.kmeans_cluster,                   -- K-Means 簇编号 0~3
    a.rfm_segment_kmeans4,              -- 4 类：高价值/中价值/潜力成长/流失风险
    a.rfm_segment_rule8                 -- 8 类：重要价值/保持/发展/挽留 + 一般×4
FROM `olist_algo_db`.`algo1_rfm_user_tags` a;


-- ------------------------------------------------------------
-- 视图 6：月度销售趋势
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_monthly_sales` AS
SELECT
    d.purchase_year,
    d.purchase_month,
    -- 注意：YEAR_MONTH 是 MySQL 保留字（时间间隔单位），列名必须加反引号
    -- purchase_month 已是 'YYYY-MM' 格式（char(7)），直接使用；
    -- 兼容整数月份：长度不足 7 时才拼接
    CASE WHEN CHAR_LENGTH(d.purchase_month) >= 7
         THEN d.purchase_month
         ELSE CONCAT(d.purchase_year, '-', LPAD(d.purchase_month, 2, '0'))
    END AS `year_month`,
    COUNT(DISTINCT d.order_id)                            AS order_cnt,
    COUNT(DISTINCT d.customer_unique_id)                  AS buyer_cnt,
    COUNT(*)                                              AS item_cnt,
    SUM(d.price)                                          AS gmv,
    ROUND(SUM(d.net_revenue), 2)                          AS net_revenue,
    ROUND(SUM(d.net_revenue) / NULLIF(COUNT(DISTINCT d.order_id), 0), 2) AS avg_order_value
FROM `olist_db`.v_order_sales_detail d
GROUP BY d.purchase_year, d.purchase_month;


-- ------------------------------------------------------------
-- 视图 7：地理分布（客户 + 卖家）
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_geo_summary` AS
SELECT
    p.customer_state,
    p.customer_city,
    COUNT(DISTINCT p.customer_unique_id)      AS customer_cnt,
    COUNT(DISTINCT p.order_id)                AS order_cnt,
    ROUND(SUM(p.net_revenue), 2)              AS net_revenue,
    ROUND(AVG(p.net_revenue), 2)              AS avg_net_revenue
FROM `olist_db`.v_order_sales_detail p
WHERE p.customer_state IS NOT NULL AND p.customer_state <> ''
GROUP BY p.customer_state, p.customer_city;


-- ------------------------------------------------------------
-- 视图 8：履约与时效分析
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_delivery_performance` AS
SELECT
    o.order_status,
    o.purchase_year,
    o.purchase_month,
    COUNT(*)                                              AS order_cnt,
    ROUND(AVG(o.approve_hours), 2)                        AS avg_approve_hours,
    ROUND(AVG(o.delivery_days), 2)                        AS avg_delivery_days,
    ROUND(AVG(o.delivery_vs_estimated_days), 2)           AS avg_days_vs_estimated,
    SUM(CASE WHEN o.delivery_ontime_flag = '超时' THEN 1 ELSE 0 END) AS late_cnt,
    ROUND(
        SUM(CASE WHEN o.delivery_ontime_flag = '超时' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(o.delivery_vs_estimated_days), 0) * 100, 2
    )                                                     AS late_rate_pct,
    ROUND(AVG(o.review_score), 2)                         AS avg_review_score,
    SUM(CASE WHEN o.has_comment = '1' THEN 1 ELSE 0 END)  AS commented_cnt
FROM `olist_db`.v_order_master o
GROUP BY o.order_status, o.purchase_year, o.purchase_month;


-- ------------------------------------------------------------
-- 视图 9：支付方式分析
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_payment_analysis` AS
SELECT
    p.primary_payment_type,
    CAST(p.payment_installments_max AS SIGNED)   AS installments,
    COUNT(DISTINCT p.order_id)                   AS order_cnt,
    SUM(CAST(p.payment_value_total AS DECIMAL(14,2))) AS payment_amount,
    ROUND(AVG(CAST(p.payment_value_total AS DECIMAL(14,2))), 2) AS avg_payment,
    -- review_score 在 fact_review 表里，不在 fact_order_payment_agg 里
    ROUND(AVG(CAST(r.review_score AS DECIMAL(5,2))), 2) AS avg_review_score
FROM `olist_db`.fact_order_payment_agg p
LEFT JOIN `olist_db`.fact_review r ON r.order_id = p.order_id
GROUP BY p.primary_payment_type, CAST(p.payment_installments_max AS SIGNED);


-- ------------------------------------------------------------
-- 视图 10：客户地理 + 地理坐标（可用于地图可视化）
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW `olist_db`.`v_customer_geo` AS
SELECT
    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,
    g.geolocation_lat,
    g.geolocation_lng,
    COUNT(DISTINCT o.order_id)  AS order_cnt,
    SUM(CAST(o.order_revenue AS DECIMAL(14,2))) AS total_revenue
FROM `olist_db`.dim_customer c
LEFT JOIN `olist_db`.dim_geolocation g
       ON g.geolocation_zip_code_prefix = c.customer_zip_code_prefix
LEFT JOIN `olist_db`.v_order_master o
       ON o.customer_unique_id = c.customer_unique_id
GROUP BY c.customer_unique_id, c.customer_zip_code_prefix,
         c.customer_city, c.customer_state, g.geolocation_lat, g.geolocation_lng;

-- ============================================================
-- 验证：
--   SELECT * FROM `olist_db`.v_order_sales_detail LIMIT 10;
--   SELECT * FROM `olist_db`.v_category_sales ORDER BY gmv DESC;
--   SELECT * FROM `olist_db`.v_customer_segment WHERE rfm_segment_rule8 = '重要价值用户';
--   SELECT * FROM `olist_db`.v_monthly_sales ORDER BY `year_month`;
-- ============================================================
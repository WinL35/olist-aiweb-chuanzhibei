-- Olist 电商数据平台 MySQL 库表结构（13 张表）
-- 数据库: olist_db
--
-- ⚠️⚠️ 危险提示：本脚本在 `USE olist_db` 之后紧跟着 13 条 DROP TABLE IF EXISTS，
--      会**清空已有数据**。且库名已写死，无论你用哪种方式执行（包括
--      `mysql <库名> < schema.sql` 指定了别的库），它都会切到 olist_db 上执行。也就是说：
--        · 空库首次建表       → 可以放心执行
--        · 库里已有业务数据   → 执行后会变成 13 张空表，数据需重新导入
--      正常复现流程请用 `python 一键导入主库.py`，它建表后会紧接着导入 CSV，
--      不需要手工执行本文件。只有「完全从零开始、库还没建」时才单独跑它。
--
-- 如果只是想查看表结构而不动数据，请用：
--      mysqldump --no-data -uroot -p olist_db

CREATE DATABASE IF NOT EXISTS olist_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE olist_db;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS fact_order_master;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS fact_rfm;
DROP TABLE IF EXISTS dim_category_summary;
DROP TABLE IF EXISTS fact_review;
DROP TABLE IF EXISTS fact_order_payment_agg;
DROP TABLE IF EXISTS fact_order_item;
DROP TABLE IF EXISTS fact_order;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_seller;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_geolocation;
DROP TABLE IF EXISTS dim_category_translation;
SET FOREIGN_KEY_CHECKS = 1;

-- ===== 维度表 =====
CREATE TABLE dim_customer (
  customer_id VARCHAR(40) PRIMARY KEY,
  customer_unique_id VARCHAR(40) NOT NULL,
  customer_zip_code_prefix VARCHAR(10),
  customer_city VARCHAR(60),
  customer_state CHAR(2),
  KEY idx_unique (customer_unique_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_seller (
  seller_id VARCHAR(40) PRIMARY KEY,
  seller_zip_code_prefix VARCHAR(10),
  seller_city VARCHAR(60),
  seller_state CHAR(2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_product (
  product_id VARCHAR(40) PRIMARY KEY,
  product_category_name VARCHAR(50),
  product_category_name_english VARCHAR(50),
  product_name_lenght INT,
  product_description_lenght INT,
  product_photos_qty INT,
  product_weight_g INT,
  product_length_cm INT,
  product_height_cm INT,
  product_width_cm INT,
  KEY idx_cat (product_category_name_english)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_geolocation (
  geolocation_zip_code_prefix VARCHAR(10) PRIMARY KEY,
  geolocation_lat DECIMAL(10,6),
  geolocation_lng DECIMAL(10,6),
  geolocation_city VARCHAR(60),
  geolocation_state CHAR(2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_category_translation (
  product_category_name VARCHAR(50) PRIMARY KEY,
  product_category_name_english VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== 基础事实表 =====
CREATE TABLE fact_order (
  order_id VARCHAR(40) PRIMARY KEY,
  customer_id VARCHAR(40) NOT NULL,
  order_status VARCHAR(20),
  order_purchase_timestamp DATETIME,
  order_approved_at DATETIME NULL,
  order_delivered_carrier_date DATETIME NULL,
  order_delivered_customer_date DATETIME NULL,
  order_estimated_delivery_date DATETIME,
  KEY idx_cust (customer_id),
  KEY idx_status (order_status),
  KEY idx_purchase (order_purchase_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_order_item (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id VARCHAR(40) NOT NULL,
  order_item_id INT,
  product_id VARCHAR(40),
  seller_id VARCHAR(40),
  shipping_limit_date DATETIME,
  price DECIMAL(12,2),
  freight_value DECIMAL(12,2),
  item_total DECIMAL(12,2),
  UNIQUE KEY uq_order_item (order_id, order_item_id),
  KEY idx_product (product_id),
  KEY idx_seller (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_order_payment_agg (
  order_id VARCHAR(40) PRIMARY KEY,
  payment_value_total DECIMAL(12,2),
  payment_sequential_max INT,
  payment_installments_max INT,
  primary_payment_type VARCHAR(20),
  n_payment_methods INT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_review (
  order_id VARCHAR(40) PRIMARY KEY,
  review_score INT,
  has_comment INT,
  review_creation_date DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ===== 分析宽表 =====
CREATE TABLE fact_order_master (
  order_id VARCHAR(40) PRIMARY KEY,
  customer_id VARCHAR(40),
  customer_unique_id VARCHAR(40),
  customer_zip_code_prefix VARCHAR(10),
  customer_city VARCHAR(60),
  customer_state CHAR(2),
  order_status VARCHAR(20),
  order_purchase_timestamp DATETIME,
  order_approved_at DATETIME NULL,
  order_delivered_carrier_date DATETIME NULL,
  order_delivered_customer_date DATETIME NULL,
  order_estimated_delivery_date DATETIME,
  payment_value_total DECIMAL(14,2),
  payment_sequential_max INT,
  payment_installments_max INT,
  primary_payment_type VARCHAR(20),
  n_payment_methods INT,
  review_score INT,
  has_comment INT,
  review_creation_date DATETIME NULL,
  n_items INT,
  gmv DECIMAL(14,2),
  total_freight DECIMAL(14,2),
  order_revenue DECIMAL(14,2),
  purchase_date DATE,
  purchase_year INT,
  purchase_month CHAR(7),
  purchase_week INT,
  purchase_weekday INT,
  purchase_hour INT,
  delivery_days DECIMAL(10,2) NULL,
  approve_hours DECIMAL(10,2) NULL,
  delivery_vs_estimated_days DECIMAL(10,2) NULL,
  KEY idx_uniq (customer_unique_id),
  KEY idx_pdate (purchase_date),
  KEY idx_pmonth (purchase_month),
  KEY idx_status (order_status),
  KEY idx_ptyear (purchase_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_sales (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id VARCHAR(40),
  order_item_id INT,
  product_id VARCHAR(40),
  seller_id VARCHAR(40),
  shipping_limit_date DATETIME,
  price DECIMAL(12,2),
  freight_value DECIMAL(12,2),
  item_total DECIMAL(12,2),
  product_category_name VARCHAR(50),
  product_category_name_english VARCHAR(50),
  seller_city VARCHAR(60),
  seller_state CHAR(2),
  customer_id VARCHAR(40),
  order_purchase_timestamp DATETIME,
  order_status VARCHAR(20),
  customer_unique_id VARCHAR(40),
  customer_city VARCHAR(60),
  customer_state CHAR(2),
  purchase_date DATE,
  purchase_year INT,
  purchase_month CHAR(7),
  iso_week INT,
  iso_year INT,
  weekday INT,
  hour INT,
  year_week CHAR(10),
  KEY idx_cat (product_category_name_english),
  KEY idx_pid (product_id),
  KEY idx_odate (purchase_date),
  KEY idx_yw (year_week),
  KEY idx_pmonth (purchase_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_rfm (
  customer_unique_id VARCHAR(40) PRIMARY KEY,
  recency INT,
  frequency INT,
  monetary DECIMAL(14,2),
  r_score INT,
  f_score INT,
  m_score INT,
  rfm_segment VARCHAR(30),
  KEY idx_seg (rfm_segment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_category_summary (
  product_category_name_english VARCHAR(50) PRIMARY KEY,
  order_cnt INT,
  item_cnt INT,
  gmv DECIMAL(14,2),
  avg_price DECIMAL(12,2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

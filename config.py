# -*- coding: utf-8 -*-
"""项目统一配置：数据库连接、数据目录、算法结果库名。

本文件放在项目根目录（Olist项目/config.py），被以下代码共用：
  - load_mysql.py        （导入主库 olist_db）
  - 一键导入主库.py       （带密码交互的启动器）
  - app/db.py            （FastAPI 数据库连接）
  - app/main.py          （FastAPI 静态目录）

密码默认写的是本机 MySQL 的 root 密码；换电脑时改这里，或用环境变量覆盖：
    set MYSQL_PASSWORD=你的密码
"""
import os

# 项目根目录（本文件所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- MySQL 连接 ----------------
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "root"),
    # 主业务库：项目原有 13 张表（fact_* / dim_*）
    "database": os.getenv("MYSQL_DB", "olist_db"),
    "charset": "utf8mb4",
}

# ---------------- 算法结果库 ----------------
# 算法1（RFM 用户标签）+ 算法2（预测/选品/定价/离线实验）的结果都在这个库里。
# 它与 DB_CONFIG["database"] 在【同一个 MySQL 实例】上，所以可以跨库查询：
#     SELECT * FROM olist_algo_db.algo1_rfm_user_tags
# 因此后端只连主库就够了，不需要维护第二个连接。
ALGO_DB = os.getenv("MYSQL_ALGO_DB", "olist_algo_db")

# 算法库的连接参数 = 主库连接参数 + 算法库名（同实例，只是库名不同）
# 供 export_algo_to_mysql.py 等需要显式连算法库的脚本使用
ALGO_DB_CONFIG = {**DB_CONFIG, "database": ALGO_DB}

# ---------------- 目录 ----------------
# 清洗后的 csv（load_mysql.py 的输入）
CLEANED_DIR = os.path.join(BASE_DIR, "cleaned")
# 前端静态文件（index.html + assets/）
STATIC_DIR = os.path.join(BASE_DIR, "static")

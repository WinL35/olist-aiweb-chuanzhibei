# -*- coding: utf-8 -*-
"""
一键导入算法库 olist_algo_db（含主库 10 个查询视图）
====================================================
双击运行，或在项目根目录执行：python3 一键导入算法库.py

本脚本用 pymysql 直接执行两个 SQL 文件，【不需要 mysql 命令行】：
  1. olist_algo_mysql.sql  → 建算法库 olist_algo_db（9 张表 + 全部结果数据）
  2. Olist_Views.sql       → 在主库 olist_db 上建 10 个查询视图

前提：
  - 已 pip install -r requirements.txt（需要 PyMySQL）
  - 主库 olist_db 已存在：先跑「一键导入主库.py」，
    或先执行过 Olist.sql 快照（视图建在 olist_db 上，库不在会报错提示）

密码：环境变量 MYSQL_PASSWORD 优先，否则交互输入（与一键导入主库.py 一致）。
"""
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

ALGO_SQL = BASE / "olist_algo_mysql.sql"
VIEWS_SQL = BASE / "Olist_Views.sql"


def iter_statements(path: Path):
    """逐行累积 SQL 文本，遇到以 ';' 结尾的行就产出一条完整语句。

    安全性说明：mysqldump 导出的字符串值里不含裸换行（换行已转义为 \\n），
    因此"以分号结尾的一行"就是语句边界，按行切分不会截断 INSERT 数据。
    注释行（-- 开头）与空行直接跳过；/*!40xxx ... */; 条件注释会被执行。
    """
    buf = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if not buf and (not s.strip() or s.lstrip().startswith("--")):
                continue
            buf.append(s)
            if s.endswith(";"):
                stmt = "\n".join(buf).strip()
                buf = []
                if stmt and stmt != ";":
                    yield stmt
    if buf:  # 文件末尾没有分号的兜底
        tail = "\n".join(buf).strip()
        if tail:
            yield tail


def run_sql_file(conn, path: Path, label: str) -> int:
    """在给定连接上执行整个 SQL 文件，返回执行成功的语句数。"""
    n = 0
    t0 = time.time()
    with conn.cursor() as cur:
        for stmt in iter_statements(path):
            cur.execute(stmt)
            n += 1
            if n % 20 == 0:
                print(f"    ... 已执行 {n} 条语句", flush=True)
    conn.commit()
    print(f"  [OK] {label}: {n} 条语句, 耗时 {time.time() - t0:.1f} 秒")
    return n


def main() -> int:
    print("=" * 64)
    print("  导入算法库 olist_algo_db + 主库视图")
    print("=" * 64)
    print(f"  工作目录: {BASE}")

    # 前置文件检查
    missing = [str(p) for p in (ALGO_SQL, VIEWS_SQL) if not p.exists()]
    if missing:
        print("[错误] 缺少 SQL 文件:")
        for m in missing:
            print(f"        {m}")
        return 1

    # 密码: 环境变量优先, 否则交互输入（不用 getpass, PyCharm 控制台不显示提示）
    pwd = os.getenv("MYSQL_PASSWORD")
    if not pwd:
        print("请输入 MySQL root 密码（输入后按回车；密码会显示出来，这正常）:",
              flush=True)
        pwd = input("  > ").strip()
    if not pwd:
        print("[错误] 密码为空，已退出。")
        return 2
    os.environ["MYSQL_PASSWORD"] = pwd

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    main_db = os.getenv("MYSQL_DB", "olist_db")
    algo_db = os.getenv("MYSQL_ALGO_DB", "olist_algo_db")

    import pymysql
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=pwd,
                               charset="utf8mb4", connect_timeout=10,
                               autocommit=False)
    except Exception as e:
        print(f"[错误] 连接 MySQL 失败: {e}")
        return 2

    # 主库必须已存在（视图建在 olist_db 上）
    with conn.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE %s", (main_db,))
        if cur.fetchone() is None:
            print(f"[错误] 主库 {main_db} 不存在。请先运行「一键导入主库.py」，"
                  f"或执行 Olist.sql 快照，再重跑本脚本。")
            conn.close()
            return 3

    print(f"  [OK] MySQL 连接成功，主库 {main_db} 已存在")
    print()

    # 1) 算法库（dump 自带 CREATE DATABASE + USE，重复执行为全量覆盖）
    print(f"  (1/2) 执行 olist_algo_mysql.sql → {algo_db}")
    run_sql_file(conn, ALGO_SQL, "算法库导入")

    # 2) 视图（Olist_Views.sql 内全部是 `olist_db`.xxx 全限定名 + CREATE OR REPLACE）
    print(f"  (2/2) 执行 Olist_Views.sql → {main_db} 的 10 个视图")
    run_sql_file(conn, VIEWS_SQL, "视图创建")

    # ---- 核对 ----
    print()
    print("=" * 64)
    print("  核对结果")
    print("=" * 64)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=%s", (algo_db,))
        n_tables = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM `{algo_db}`.algo1_rfm_user_tags")
        n_rfm = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.views "
                    "WHERE table_schema=%s", (main_db,))
        n_views = cur.fetchone()[0]
    conn.close()

    ok = True
    print(f"    {algo_db} 表数量: {n_tables}"
          + ("  OK" if n_tables == 9 else "  !! 应为 9"))
    print(f"    algo1_rfm_user_tags 行数: {n_rfm:,}"
          + ("  OK" if n_rfm == 95420 else "  !! 应为 95,420"))
    print(f"    {main_db} 视图数量: {n_views}"
          + ("  OK" if n_views == 10 else "  !! 应为 10"))
    ok = (n_tables == 9 and n_rfm == 95420 and n_views == 10)

    print()
    if ok:
        print("  [成功] 算法库与视图就绪。下一步: python3 启动后端.py")
        return 0
    print("  [注意] 数量与预期不符，请检查上方输出。")
    return 4


if __name__ == "__main__":
    sys.exit(main())

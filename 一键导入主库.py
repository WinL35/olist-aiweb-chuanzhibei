# -*- coding: utf-8 -*-
"""
一键导入项目主库 olist_db
=========================
双击运行或在 PyCharm 里 Run 即可。会提示输入 MySQL root 密码（输入时不显示）。
导入内容: 13 张表, 约 87 万行, 预计 1~2 分钟。
"""
import getpass
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "pipeline"))


def main() -> int:
    print("=" * 64)
    print("  导入项目主库 olist_db")
    print("=" * 64)
    print(f"  工作目录: {BASE}")
    print()

    # 检查前置文件
    missing = [str(p) for p in [BASE / "config.py", BASE / "schema.sql",
                                BASE / "pipeline" / "load_mysql.py", BASE / "cleaned"]
               if not p.exists()]
    if missing:
        print("[错误] 缺少必要文件/目录:")
        for m in missing:
            print(f"        {m}")
        return 1

    csvs = list((BASE / "cleaned").glob("*.csv"))
    print(f"  待导入 csv: {len(csvs)} 个")
    print()

    # 密码: 环境变量优先, 否则用 input() 交互输入
    # 注意: 不用 getpass —— PyCharm 运行控制台不显示它的提示, 看起来像卡住
    pwd = os.getenv("MYSQL_PASSWORD")
    if not pwd:
        print("请输入 MySQL root 密码（输入后按回车；密码会显示出来，这正常）:",
              flush=True)
        pwd = input("  > ").strip()
    if not pwd:
        print("[错误] 密码为空，已退出。")
        return 2
    os.environ["MYSQL_PASSWORD"] = pwd
    print(f"  已接收密码（长度 {len(pwd)} 位），正在连接 ...", flush=True)

    # 连接参数与 config.py 同一套环境变量（MYSQL_HOST/PORT/USER/DB），
    # 避免换机器/换账号时这里还写死 localhost+root
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    db_name = os.getenv("MYSQL_DB", "olist_db")

    # 先验证连接, 避免跑到一半才报错
    try:
        import pymysql
        conn = pymysql.connect(host=host, port=port, user=user,
                               password=pwd, charset="utf8mb4", connect_timeout=8)
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
        conn.close()
        print(f"[OK] MySQL 连接成功，版本 {ver}")
    except Exception as e:
        print(f"[错误] 连接 MySQL 失败: {e}")
        print("       密码不对请重跑本脚本；也确认 MySQL80 服务在运行。")
        return 2

    print()
    t0 = time.time()
    import load_mysql
    load_mysql.main()
    print()
    print(f"[总计] 耗时 {time.time() - t0:.1f} 秒")

    # 导入后核对
    print()
    print("=" * 64)
    print("  核对结果")
    print("=" * 64)
    conn = pymysql.connect(host=host, port=port, user=user,
                           password=pwd, database=db_name, charset="utf8mb4")
    expect = {"fact_rfm": 95420, "fact_sales": 112650}
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  {db_name} 共有 {len(tables)} 张表")
        ok = True
        for t in sorted(tables):
            cur.execute(f"SELECT COUNT(*) FROM `{t}`")
            n = cur.fetchone()[0]
            flag = ""
            if t in expect:
                good = (n == expect[t])
                ok = ok and good
                flag = "  OK" if good else f"  !! 应为 {expect[t]}"
            print(f"    {t:32s} {n:>10,}{flag}")
    conn.close()
    print()
    if ok:
        print("  [成功] 主库导入完成，后端可以连了")
    else:
        print("  [注意] 行数与预期不符，请检查")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())

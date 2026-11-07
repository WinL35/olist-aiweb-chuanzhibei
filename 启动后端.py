# -*- coding: utf-8 -*-
"""
一键启动后端服务
================
双击运行，或在 PyCharm 里 Run。
启动后浏览器打开 http://127.0.0.1:8000/ 看前端页面
接口文档: http://127.0.0.1:8000/docs
健康检查: http://127.0.0.1:8000/api/health （会显示两个库的连通状态）
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)          # uvicorn 需要以项目根目录为工作目录
sys.path.insert(0, str(BASE))

print("=" * 64)
print("  Olist 经营分析与智能选品平台 - 后端")
print("=" * 64)
print(f"  工作目录: {BASE}")

# 依赖检查
missing = []
try:
    import fastapi  # noqa
except ImportError:
    missing.append("fastapi")
try:
    import uvicorn  # noqa
except ImportError:
    missing.append("uvicorn")
try:
    import pymysql  # noqa
except ImportError:
    missing.append("pymysql")
try:
    import pandas  # noqa
except ImportError:
    missing.append("pandas")

if missing:
    print()
    print(f"[错误] 缺少依赖: {', '.join(missing)}")
    print("       请先执行下面的命令安装（复制到终端运行）：")
    print()
    print(f'       "{sys.executable}" -m pip install ' + " ".join(
        '"uvicorn[standard]"' if m == "uvicorn" else m for m in missing))
    print()
    input("按回车键退出...")
    sys.exit(1)

# 数据库连通性预检（密码不对时直接提示输入，省得去改 config.py）
import config
import pymysql

def _connect(pwd):
    return pymysql.connect(host=config.DB_CONFIG["host"], port=config.DB_CONFIG["port"],
                           user=config.DB_CONFIG["user"], password=pwd,
                           charset="utf8mb4", connect_timeout=6)

pwd = config.DB_CONFIG["password"]
conn = None
for attempt in (1, 2):
    try:
        conn = _connect(pwd)
        break
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else None
        if code == 1045 and attempt == 1 and not os.getenv("MYSQL_PASSWORD"):
            print("  [提示] MySQL 拒绝登录：config.py 里的密码与本机不一致。")
            print("         请输入本机 MySQL 的 root 密码（输入会显示出来，这是正常的）:")
            try:
                pwd = input("  > ").strip()
            except EOFError:
                pwd = ""
            config.DB_CONFIG["password"] = pwd
            os.environ["MYSQL_PASSWORD"] = pwd
            continue
        print(f"  [错误] 连接 MySQL 失败: {e}")
        if code == 1045:
            print("         密码仍不正确。可直接编辑 config.py 的 \"password\" 一行，或设置环境变量 MYSQL_PASSWORD。")
        else:
            print("         请确认 MySQL 服务（MySQL80）已启动，端口 3306 未被占用。")
        input("按回车键退出...")
        sys.exit(2)

try:
    c = conn
    with c.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE %s", (config.DB_CONFIG["database"],))
        has_biz = cur.fetchone() is not None
        cur.execute("SHOW DATABASES LIKE %s", (config.ALGO_DB,))
        has_algo = cur.fetchone() is not None
    c.close()
    print(f"  [OK] MySQL 连接成功")
    print(f"       主库 {config.DB_CONFIG['database']}: {'存在' if has_biz else '缺失!'}")
    print(f"       算法库 {config.ALGO_DB}: {'存在' if has_algo else '缺失!'}")
    if not has_biz or not has_algo:
        print("  [警告] 库不完整，接口可能取不到数据，请先跑导入脚本")
except Exception as e:
    print(f"  [错误] 连接 MySQL 失败: {e}")
    print("         请检查 config.py 里的密码，以及 MySQL80 服务是否运行。")
    input("按回车键退出...")
    sys.exit(2)

print()
print("  启动中... 就绪后访问 http://127.0.0.1:8000/")
print("  接口文档:        http://127.0.0.1:8000/docs")
print("  健康检查:        http://127.0.0.1:8000/api/health")
print("  按 Ctrl+C 停止服务")
print("=" * 64)
print()

import uvicorn

# 关于 ws="none"：
#   本机 websockets 版本 10.4 太旧，而 uvicorn 0.54 需要 websockets>=12 才有
#   ServerProtocol，否则启动时报 ImportError。
#   本项目所有接口都是普通 HTTP，没有 WebSocket，所以直接关闭 WS 支持最省事。
#   （如果以后确实要用 WebSocket，可改成 ws="wsproto"，本机已装 wsproto 1.2.0）
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False,
            log_level="info", ws="none")

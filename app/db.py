# -*- coding: utf-8 -*-
"""MySQL 连接与查询辅助。

使用 pymysql 同步连接，配合 FastAPI 同步路由（由线程池执行）。

跨库说明：
    本模块只连主库 olist_db；算法1/算法2 的结果在 olist_algo_db 里，
    两者在同一个 MySQL 实例上，写全限定表名即可跨库查询：
        SELECT * FROM olist_algo_db.algo1_rfm_user_tags
    不需要维护第二个连接池。

⚠️ 关于 SQL 里的百分号：
    query() 在没有参数时【不】做 % 格式化，所以 LIKE '主模型%' 可以直接写单个 %；
    只有在传了 params 的 SQL 里，字面量 % 才需要写成 %%（pymysql 的规则）。
"""
import sys
from contextlib import contextmanager
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config


@contextmanager
def get_conn():
    conn = pymysql.connect(
        host=config.DB_CONFIG["host"], port=config.DB_CONFIG["port"],
        user=config.DB_CONFIG["user"], password=config.DB_CONFIG["password"],
        database=config.DB_CONFIG["database"], charset=config.DB_CONFIG["charset"],
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
    )
    try:
        yield conn
    finally:
        conn.close()


def query(sql, params=None):
    """执行查询, 返回 dict 列表。

    params 为空时不走 pymysql 的 % 格式化，避免 SQL 中的字面量 % 被误解析
    （例如 LIKE '主模型%'）。
    """
    with get_conn() as conn, conn.cursor() as cur:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchall()


def query_one(sql, params=None):
    """执行查询并返回第一行（无结果返回 None）。"""
    row = query(sql, params)
    return row[0] if row else None

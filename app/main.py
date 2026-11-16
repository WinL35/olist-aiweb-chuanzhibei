# -*- coding: utf-8 -*-
"""Olist 用户行为分析与智能选品推荐平台 - 后端入口

启动方式（在项目根目录 Olist项目 下执行）:
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

也可以双击运行上一级的「启动后端.py」。
"""
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# 让 `import config` 能命中项目根目录的 config.py
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from app.analysis import router as analysis_router
from app.dashboard import router as dashboard_router
from app.experiment import router as experiment_router
from app.llm_api import router as llm_router
from app.pricing import router as pricing_router
from app.selection import router as selection_router

app = FastAPI(
    title="Olist 经营分析与智能选品平台",
    version="1.1",
    description="数据源：olist_db（业务宽表）+ olist_algo_db（算法1/算法2 结果，跨库查询）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 全局异常处理（统一 JSON 结构）----------------
def _err(code: int, message: str, data=None):
    # HTTP 状态保持 200，业务错误码放 body，前端统一按 code 判断
    return JSONResponse(status_code=200,
                        content={"code": code, "message": message, "data": data})


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    """业务型 HTTP 异常（如 404）"""
    return _err(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    """参数校验失败（如缺 category、weeks 超范围）"""
    return _err(422, "参数校验失败", exc.errors())


# ---------------- 只读守卫（看板数据不可被写）----------------
# 设计意图：本平台所有看板页面都是「只读呈现」，AI 问答也「只提供查询」。
# 唯一允许的写入是问答页的 👍/👎 反馈，它落 llm/feedback/feedback.db（独立 SQLite），
# 不经过本守卫、也不触碰 olist_db。其余任何对业务接口的写请求一律拒绝，
# 这样即便前端误加了按钮、或有人手工构造 PUT/DELETE，看板数据也改不动。
_WRITE_METHODS = {"PUT", "PATCH", "DELETE"}
_SAFE_PREFIX = "/api/llm/feedback"  # 问答页 👍/👎：写独立 SQLite，不碰看板数据


@app.middleware("http")
async def readonly_guard(request: Request, call_next):
    """拦掉所有对业务接口的 PUT/PATCH/DELETE。

    POST 不拦：它在本项目里全是「查询型」用法（前端把复杂筛选条件放 body，
    例如 /api/llm/chat、/api/llm/chat/stream 都是 POST），拦了会打挂问答。
    真正的写库风险是改/删，这里直接从方法层面禁死。
    """
    if request.method in _WRITE_METHODS and not request.url.path.startswith(_SAFE_PREFIX):
        return JSONResponse(
            status_code=200,
            content={"code": 403, "message": "看板数据为只读，不支持修改或删除", "data": None},
        )
    return await call_next(request)


@app.exception_handler(Exception)
async def any_exc_handler(request: Request, exc: Exception):
    """兜底：数据库连不上、SQL 报错等"""
    import traceback
    traceback.print_exc()
    return _err(500, f"服务异常: {type(exc).__name__}: {exc}")


# ---------------- 路由注册 ----------------
app.include_router(dashboard_router)    # /api/dashboard/*
app.include_router(analysis_router)     # /api/*（RFM / 转化 / 预测）
app.include_router(pricing_router)      # /api/pricing/*（算法2 定价建议）
app.include_router(experiment_router)   # /api/experiment/*（算法2 离线实验）
app.include_router(selection_router)    # /api/selection/*（算法2 选品结果）
app.include_router(llm_router)          # /api/llm/*（垂直大模型：口径/工具/评测）


@app.get("/api/health", tags=["基础"])
def health():
    """健康检查 + 数据库连通性（同时验证主库和算法结果库）。"""
    from app.db import query_one
    out = {"status": "ok", "db": {}, "algo_db": {}}
    try:
        r = query_one("SELECT DATABASE() AS db, VERSION() AS ver")
        out["db"] = {"database": r["db"], "version": r["ver"], "ok": True}
    except Exception as e:
        out["db"] = {"ok": False, "error": str(e)}
        out["status"] = "degraded"
    try:
        r = query_one(f"SELECT COUNT(*) AS n FROM {config.ALGO_DB}.algo1_rfm_user_tags")
        out["algo_db"] = {"database": config.ALGO_DB, "rfm_rows": int(r["n"]), "ok": True}
    except Exception as e:
        out["algo_db"] = {"ok": False, "error": str(e)}
        out["status"] = "degraded"
    return out


# ---------------- 前端入口 ----------------
# 前端是与本服务分离的 Next.js 14 应用（web/，默认 3000 端口），本服务只提供 /api/*。
# 旧版 static/（Vue 3 CDN + 手写 HTML）已于本次重构中移除，功能全部迁至 web/。
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:3000")


@app.get("/", include_in_schema=False)
def index():
    """根路径给出入口指引：本服务是纯 API，界面在 Next.js 侧。"""
    return {
        "service": "Olist 电商经营决策垂直大模型 · API",
        "docs": "/docs",
        "health": "/api/health",
        "frontend": FRONTEND_URL,
        "hint": "界面为独立 Next.js 应用，请访问 frontend 地址；本服务仅提供 /api/* 接口",
    }

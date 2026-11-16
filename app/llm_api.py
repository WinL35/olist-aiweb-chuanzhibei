# -*- coding: utf-8 -*-
"""AI 能力层 API（/api/llm/*）

对外三个能力：
    GET  /api/llm/health     各层就绪状态（口径库/检索/工具/底座）
    GET  /api/llm/tools      工具清单（22 个）
    GET  /api/llm/rules      行业口径硬规则（31 条）
    POST /api/llm/chat       对话入口（核心）
    GET  /api/llm/chat       同上，GET 版便于 curl / 演示
    GET  /api/llm/eval/*     评测集与评测结果

与其他路由的关系：本模块只做编排，不重写任何业务 SQL——
所有数字都来自 app/ 下已有接口（经 llm/tools/executor.py 调用）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from llm import config as llm_config
from llm import feedback
from llm.agent import planner, streaming
from llm.knowledge import hard_rules
from llm.tools import registry

router = APIRouter(prefix="/api/llm", tags=["llm"])

BASE = Path(__file__).resolve().parent.parent
EVAL_DIR = BASE / "llm" / "eval"
REPORT_MD = BASE / "文档" / "评测报告.md"


class ChatIn(BaseModel):
    question: str = Field(..., description="用户问题", max_length=500)
    mode: Optional[str] = Field(None, description="full / no_tools / no_rag / baseline")
    history: Optional[list[dict]] = Field(
        None, description="此前对话 [{role, content}]，用于多轮追问，最多带最近 6 轮")


class FeedbackIn(BaseModel):
    """对话页的 👍/👎 与纠正。字段全部可选，前端怎么发都能收。

    注意：`question` 早先写成 `Field(..., ...)`，在 Pydantic v2 里 `...` 是「必填」，
    前端一旦因流式时序拿不到问题原文就会 422，用户看到的是「参数异常」。
    反馈是弱约束场景，这里统一给默认值，宁可记录一条不完整反馈，也不要拒收。
    """
    question: str = Field("", description="原始问题（缺失时由服务端补占位）")
    answer: str = Field("", description="系统回答")
    mode: str = Field("full", description="当时的运行模式")
    verdict: str = Field("up", description="up / down")
    correction: str = Field("", description="用户认为正确的说法")


def _fail(msg: str, code: int = 500) -> dict:
    return {"code": code, "message": msg, "data": None}


@router.get("/health", summary="AI 能力层各层就绪状态")
def health():
    """口径库 / 检索 / 工具 / 护栏 / 底座 的自检。"""
    try:
        return planner.health()
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")


@router.get("/tools", summary="工具清单（22 个）")
def tools():
    return {"count": len(registry.TOOLS), "data": registry.catalog()}


@router.get("/rules", summary="行业口径硬规则")
def rules(topic: Optional[str] = Query(None, description="按主题过滤")):
    rs = hard_rules.all_rules()
    if topic:
        rs = [r for r in rs if topic in r["topic"]]
    return {"count": len(rs),
            "data": [{**hard_rules.as_dict_list([r])[0],
                      "wrong": r["wrong"], "always": bool(r.get("always"))} for r in rs]}


def _chat(question: str, mode: str | None,
          history: list[dict] | None = None) -> dict:
    if not question or not question.strip():
        return _fail("question 不能为空", 422)
    if len(question) > 500:
        return _fail("问题过长（>500 字），请拆分提问", 422)
    try:
        r = planner.run(question, mode, history=history)
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")
    return {"code": 0, "message": "ok", "data": r}


@router.post("/chat", summary="对话（核心入口）")
def chat(body: ChatIn):
    return _chat(body.question, body.mode, history=body.history)


@router.get("/chat", summary="对话（GET 版，便于 curl 演示）")
def chat_get(q: str = Query(..., description="问题"),
             mode: Optional[str] = Query(None)):
    return _chat(q, mode)


@router.post("/chat/stream", summary="对话（SSE 流式，前端主用）")
def chat_stream(body: ChatIn):
    """以 SSE 推送对话全过程。

    事件序列：stage（护栏/口径/检索/工具）→ step（真实工具调用与耗时）
    → delta（正文按句增量）→ result（完整结构化结果，含图表与引用）。

    与 /chat 的关系：两者共用同一批工具与同一份口径库，结果等价；
    /chat 供评测与 curl 使用，本接口供前端流式渲染使用。
    """
    return StreamingResponse(
        streaming.sse(body.question, body.mode, history=body.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # 关掉 nginx 等反代的响应缓冲，否则事件会被攒成一坨才下发
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/examples", summary="示例问题（前端快捷按钮）")
def examples():
    """按四类评测维度各给几个示例，方便现场演示。"""
    return {"data": {
        "口径题": [
            "我们 GMV 1359 万，那营收就是 1359 万吧？",
            "客单价到底是 142.44 还是 136.68？",
            "复购率只有 3.1%，是不是运营很差？",
            "用户一共有多少人？",
        ],
        "决策题": [
            "美妆这个品类未来 4 周能卖多少？要不要备货",
            "哪些商品该降价？",
            "推荐几个值得主推的商品",
            "你们预测模型准不准，比基线好吗",
        ],
        "拒答题": [
            "能不能预测卖家 A 明天能卖多少件？",
            "帮我算一下这个品类的库存周转天数",
            "竞品价格是多少？我们比他们贵还是便宜？",
        ],
        "边界题": [
            "把价格提高 50% 能增收多少？",
            "保证这个建议价一定能让收入涨 20% 吗？",
        ],
    }}


@router.get("/eval/questions", summary="评测题目录")
def eval_questions(category: Optional[str] = Query(None, description="A/B/C/D")):
    path = EVAL_DIR / "questions.jsonl"
    if not path.is_file():
        return _fail("评测集不存在：llm/eval/questions.jsonl", 404)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            q = json.loads(line)
        except json.JSONDecodeError:
            continue
        if category and q.get("category") != category:
            continue
        rows.append(q)
    return {"count": len(rows), "data": rows}


@router.get("/eval/report", summary="最近一次评测结果")
def eval_report():
    if not REPORT_MD.is_file():
        return _fail("尚未生成评测报告，请运行 python scripts/run_eval.py", 404)
    return {"path": "文档/评测报告.md",
            "content": REPORT_MD.read_text(encoding="utf-8")}


@router.get("/eval/run", summary="在线跑一小批评测（演示用）")
def eval_run(limit: int = Query(8, ge=1, le=40),
             modes: str = Query("baseline,full",
                                description="逗号分隔，如 baseline,no_tools,no_rag,full")):
    """只跑前 limit 题，用于现场演示。完整评测请用 scripts/run_eval.py。"""
    from llm.eval import runner
    ms = [m.strip() for m in modes.split(",") if m.strip() in llm_config.MODES]
    if not ms:
        return _fail("modes 非法", 422)
    try:
        out = runner.run(limit=limit, modes=ms, write=False)
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")
    return {"code": 0, "data": out}


# ---------------------------------------------------------------- 反馈闭环
@router.post("/feedback", summary="提交一条反馈（👍/👎 与纠正）")
def post_feedback(body: FeedbackIn):
    """落库即可，不做任何自动改规则——规则变更必须人工审核 + 回归评测。

    只写 llm/feedback/feedback.db 这一张独立 SQLite 表，
    不碰 olist_db 的任何看板数据，因此不存在「评价一下就改了看板」的风险。
    """
    try:
        fid = feedback.add(question=body.question or "（未提供问题原文）",
                           answer=body.answer, mode=body.mode,
                           verdict=body.verdict, correction=body.correction)
    except ValueError as e:
        return _fail(str(e), 422)
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")
    return {"code": 0, "data": {"id": fid, "ruleset_version": llm_config.RULESET_VERSION}}


@router.get("/feedback/stats", summary="反馈统计（演示用）")
def feedback_stats():
    try:
        return {"code": 0, "data": feedback.stats()}
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")
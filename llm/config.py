# -*- coding: utf-8 -*-
"""AI 能力层配置。

所有配置都走环境变量，不把 key 写进代码（与项目 config.py 的做法一致）。

    # 接入任意 OpenAI 兼容接口（DeepSeek / 通义 / 智谱 / vLLM / Ollama 均可）
    export LLM_API_KEY=sk-xxx
    export LLM_BASE_URL=https://api.deepseek.com/v1
    export LLM_MODEL=deepseek-chat

未设置 LLM_API_KEY 时，自动降级为 offline 规则引擎：
    管线（硬规则 + RAG + 工具调用 + 护栏）全部照常运行，
    只是"语言组织"这一步由确定性规则代替模型生成，
    用于无网络/无额度时验证工程链路与跑通评测。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 先加载项目根目录的 .env（纯标准库实现），再读下面的 os.getenv。
# 这样 scripts/run_eval.py、scripts/llm_smoke.py 等脚本也能自动读到 key，
# 不必每次在命令行 export（也避免把密钥留在 shell history 里）。
# 说明：直接把根目录塞进 sys.path，避免「从 scripts/ 下运行」时 import 不到 envload。
try:
    _ROOT = Path(__file__).resolve().parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from envload import load_dotenv as _load_dotenv

    _load_dotenv(_ROOT / ".env")
except Exception:
    pass

# ---------------- 底座模型 ----------------
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1200"))
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))

# ---------------- 默认运行模式 ----------------
# full       : 硬规则 + RAG + 工具（默认，答辩演示用）
# no_tools   : 硬规则 + RAG，不给工具（用于消融实验）
# no_rag     : 硬规则 + 工具，不检索文档（用于消融实验）
# baseline   : 裸底座，什么都不给（用于对照实验）
MODES = ("full", "no_tools", "no_rag", "baseline")
DEFAULT_MODE = os.getenv("LLM_MODE", "full")

# 口径规则库版本号：每次增删规则必须同步改这里，并跑 scripts/run_eval.py --gate
RULESET_VERSION = "2026.11.02"

# ---------------- Agent 行为 ----------------
MAX_STEPS = int(os.getenv("LLM_MAX_STEPS", "4"))       # 最多几轮工具调用
MAX_TOOL_CALLS = int(os.getenv("LLM_MAX_TOOL_CALLS", "6"))
RAG_TOP_K = int(os.getenv("LLM_RAG_TOP_K", "4"))       # 检索返回片段数
RAG_MIN_SCORE = float(os.getenv("LLM_RAG_MIN_SCORE", "0.05"))

# ---------------- 项目约束（与算法层保持一致）----------------
PRICE_BOUND = 0.15          # 建议价最大调整幅度 ±15%
MIN_MONTHS = 10             # 估计弹性最少月度观测
MIN_PRICE_SD = 0.02         # 最低价格变异系数
ELAS_R2_MIN = 0.15          # 弹性回归最低 R²
FORECAST_WEEKS = 8          # 预测最大周数
TOP_N = 30                  # 选品增长榜


def provider_name() -> str:
    """当前生效的底座。"""
    return "openai_compat" if API_KEY else "offline"


def describe() -> dict:
    """给 /api/llm/health 用的配置快照（不泄露 key）。"""
    return {
        "provider": provider_name(),
        "model": MODEL if API_KEY else "offline-rule-engine",
        "base_url": BASE_URL if API_KEY else None,
        "has_api_key": bool(API_KEY),
        "default_mode": DEFAULT_MODE,
        "max_steps": MAX_STEPS,
        "rag_top_k": RAG_TOP_K,
        "ruleset_version": RULESET_VERSION,
    }
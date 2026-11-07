# -*- coding: utf-8 -*-
"""底座模型适配层。

    openai_compat : 任意 OpenAI 兼容接口（DeepSeek / 通义 / 智谱 / vLLM / Ollama）
    offline       : 无 API Key 时的确定性规则引擎（见 llm.agent.planner）

新增底座只需实现 Provider.chat 三个字段，不必改 Agent。
"""
from llm.providers.base import Provider, ProviderError  # noqa: F401
from llm.providers.openai_compat import OpenAICompatProvider  # noqa: F401

__all__ = ["Provider", "ProviderError", "OpenAICompatProvider", "get_provider"]


def get_provider():
    """按配置返回底座；无 key 返回 None（由 planner 走 offline 路径）。"""
    from llm import config
    if not config.API_KEY:
        return None
    return OpenAICompatProvider()
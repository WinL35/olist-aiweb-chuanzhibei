# -*- coding: utf-8 -*-
"""Provider 抽象。"""
from __future__ import annotations

from typing import Any


class ProviderError(RuntimeError):
    """底座调用失败（网络 / 额度 / 鉴权）。"""


class Provider:
    """底座模型接口。"""

    name = "base"
    model = ""

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float | None = None, max_tokens: int | None = None) -> dict[str, Any]:
        """一次对话调用。

        返回：
            {"content": str | None,
             "tool_calls": [{"id","name","arguments"(dict)}],
             "finish_reason": str,
             "usage": {...}}
        """
        raise NotImplementedError
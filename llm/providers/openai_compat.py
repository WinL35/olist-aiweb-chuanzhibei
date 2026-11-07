# -*- coding: utf-8 -*-
"""OpenAI 兼容接口适配（DeepSeek / 通义 / 智谱 / vLLM / Ollama 等）。

用法：
    export LLM_API_KEY=sk-xxx
    export LLM_BASE_URL=https://api.deepseek.com/v1
    export LLM_MODEL=deepseek-chat
"""
from __future__ import annotations

import json

import requests

from llm import config
from llm.providers.base import Provider, ProviderError


class OpenAICompatProvider(Provider):
    name = "openai_compat"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = (base_url or config.BASE_URL).rstrip("/")
        self.model = model or config.MODEL
        if not self.api_key:
            raise ProviderError("缺少 LLM_API_KEY")

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": config.TEMPERATURE if temperature is None else temperature,
            "max_tokens": config.MAX_TOKENS if max_tokens is None else max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        try:
            resp = requests.post(
                url, json=payload, timeout=config.TIMEOUT,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
            )
        except requests.RequestException as e:
            raise ProviderError(f"调用底座失败：{type(e).__name__}: {e}") from e

        if resp.status_code != 200:
            raise ProviderError(f"底座返回 HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            msg = data["choices"][0]["message"]
        except Exception as e:
            raise ProviderError(f"底座响应格式异常：{e}; body={resp.text[:300]}") from e

        calls = []
        for c in (msg.get("tool_calls") or []):
            fn = c.get("function", {}) or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": c.get("id", ""), "name": fn.get("name", ""),
                          "arguments": args, "raw_arguments": raw_args})

        return {
            "content": msg.get("content"),
            "tool_calls": calls,
            "finish_reason": data["choices"][0].get("finish_reason", ""),
            "usage": data.get("usage", {}),
            "raw_message": msg,
        }
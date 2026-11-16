# -*- coding: utf-8 -*-
"""AI 能力层（电商经营决策）

设计目标
--------
把已有平台（13 张业务表 / 9 张算法结果表 / 33 个接口）升级为"懂行"的
AI 应用，补齐赛题要求的三个能力：

    1. 行业知识融合  → llm.knowledge（硬规则 + RAG 检索）
    2. 精准决策      → llm.tools + llm.agent（工具调用 + 多步推理）
    3. 可评估        → llm.eval（四类评测题 + 对照实验）

分层
----
    providers/   底座模型适配（OpenAI 兼容 / 离线规则引擎）
    knowledge/   口径硬规则与行业文档检索
    tools/       现有 33 个接口 → function calling 工具
    agent/       护栏 + ReAct 循环
    eval/        评测集与评测执行器
"""
__version__ = "1.0.0"
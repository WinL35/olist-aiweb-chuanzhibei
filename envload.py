# -*- coding: utf-8 -*-
"""极简 .env 加载器（纯标准库，不依赖 python-dotenv）。

为什么自己写：
- 项目要求"零额外依赖也能跑"，多装一个包就多一个评委会踩的坑；
- 只需要 KEY=VALUE 这一种语法，python-dotenv 的能力远超需求。

规则（故意保守）：
- 忽略空行与 # 注释；
- **不覆盖已存在的环境变量** —— 命令行/系统变量优先于 .env，便于临时改配置；
- 去掉值两端成对的引号；
- 找不到文件就静默返回，不影响离线运行。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_dotenv(path: str | Path | None = None) -> int:
    """把 .env 读进 os.environ。返回成功注入的变量个数（便于自检/日志）。"""
    p = Path(path) if path else BASE_DIR / ".env"
    if not p.exists():
        return 0
    n = 0
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val
            n += 1
    return n


# 被 import 即生效：任何脚本 `import envload` 后即可读到 .env
load_dotenv()

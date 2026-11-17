# Olist 电商经营决策 AI Web 应用

> 第九届传智杯全国大学生计算机技能大赛 · **AI WEB 网页开发挑战赛**
> 团队赛 · **B 组** · 选题方向：**AI 数据分析与可视化**
>
> 仓库地址：https://github.com/WinL35/olist-aiweb-chuanzhibei

用户用自然语言提问，系统自动**取数 → 分析 → 出图**。回答里的每个数字都来自真实工具返回，
每张图的数据由后端确定性组装，模型不参与数值生成；图注还会自动标注口径编号。

底层数据为 Olist 真实交易数据：**99,441 订单 / 96,096 客户 / GMV ¥13,591,643.70（BRL 计价）**。

按赛道「特别说明」——作品以**前端 Web 应用**为主要呈现形态，后端仅作为 AI 能力的接入层。
本项目遵循此定位：8 个页面全部在前端，后端不返回任何 HTML。

---

## 一、项目介绍

### 1.1 解决什么问题

中小电商有数据但没有决策能力：Excel 做不出图、BI 工具要人懂维度建模、直接问通用大模型则会被编数字。
本项目把「经营口径」固化进系统（33 条硬规则先于模型生效），把「出图」做成模型无法伪造的确定性流程，
让不会写 SQL 的运营人员也能一句话拿到带口径标注的图表。

### 1.2 八个页面

| # | 页面 | 路由 | 干什么 |
|---|---|---|---|
| 1 | 经营看板 | `/dashboard` | 订单 / GMV / 客单价 / 复购率等核心指标 + 9 张分布图 |
| 2 | 用户分群 | `/rfm` | RFM 打分 + K-Means 九象限，95,420 用户可下钻明细 |
| 3 | 转化分析 | `/conversion` | 订单状态漏斗、品类复购、工作日分布 |
| 4 | 销量预测 | `/prediction` | 74 品类周销量预测，含 MAPE 与基线对比 |
| 5 | 选品建议 | `/recommend` | 三维综合评分选品，支持策略对比 |
| 6 | 定价建议 | `/pricing` | 基于价格弹性的建议价与置信度 |
| 7 | 模型实验 | `/experiment` | 消融实验、MAPE 中位数、命中率对比 |
| 8 | **智能问答** | `/assistant` | 对话式分析：自然语言 → 取数 → 出图 → 结论 |

快捷键 `Ctrl/⌘ + 1…8` 可直达，全部路由可深链。

### 1.3 三条可以现场验证的路径

| 你会看到什么 | 怎么触发 |
|---|---|
| 一句话出一张图，数字不编 | 智能问答页 → 点示例「各品类 GMV 画柱状图」 |
| 多轮追问不失忆 | 接着问「那第二名是谁？」 |
| 图表数字可核对 | 与 `GET /api/dashboard/category` 返回的 GMV 逐项对照，完全一致 |

---

## 二、技术架构

### 2.1 分层

```
┌──────────────────────────────────────────────────────────────┐
│  前端主体 · Next.js 14 App Router（web/）                     │
│    app/(shell)/  8 个页面路由        ← 主要呈现形态            │
│    components/   导航 / 图表 / 助手 / UI 基元                  │
│    lib/          ECharts 主题、SSE 解析、取数层                │
│    app/api/chat/ Route Handler → 透传 SSE                     │
└───────────────────────────┬──────────────────────────────────┘
                            │  POST /api/llm/chat/stream
┌───────────────────────────▼──────────────────────────────────┐
│  AI 接入层 · FastAPI（app/ + llm/）                           │
│    ReAct planner + 23 个 function calling 工具                │
│    33 条口径硬规则（先于模型生效）· 239 段 RAG                  │
└───────────────────────────┬──────────────────────────────────┘
┌───────────────────────────▼──────────────────────────────────┐
│  数据层 · MySQL 8.0                                          │
│    olist_db（13 表 + 10 视图）· olist_algo_db（9 表）          │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端框架 | Next.js 14 App Router + React 18 + **TypeScript strict** | 赛道推荐首选栈 |
| 样式 | Tailwind CSS 3 | `web/tailwind.config.ts` 为唯一配色入口 |
| 图表 | ECharts 5 **按需引入** | 首屏共享 JS **87.3 kB**（全量包约 1.01 MB） |
| AI 交互 | **SSE 流式** `text/event-stream` | 阶段进度 + 终稿按句落屏 |
| 后端 | FastAPI + PyMySQL | 纯 API，无 HTML 输出 |
| 模型 | OpenAI 兼容协议 | 默认 DeepSeek-Chat，可换 Qwen / GLM / Ollama |
| 检索 | TF-IDF + 余弦（scikit-learn） | 零外部依赖，断网可用 |

### 2.3 目录结构

```
├─ app/                    后端 API 层（FastAPI，47 个接口）
│   ├─ main.py             应用装配、只读护栏中间件、CORS
│   ├─ db.py               连接池与查询封装
│   ├─ llm_api.py          大模型层接口
│   └─ dashboard / analysis / pricing / experiment / selection.py   五个业务路由模块
├─ llm/                    大模型层
│   ├─ agent/              planner（ReAct）· streaming · guard（三重护栏）· composer
│   ├─ tools/              registry（23 个工具 schema）· executor · chart
│   ├─ knowledge/          33 条口径规则 + 239 段 RAG
│   └─ eval/               60 题主集 + 20 题盲测
├─ web/                    前端 Next.js 14（8 个路由）
│   ├─ app/(shell)/        8 个页面
│   ├─ components/         图表 / UI / 对话 / 侧栏
│   ├─ lib/                取数、SSE 解析、ECharts 注册
│   └─ types/api.ts        后端接口的 TypeScript 类型定义
├─ pipeline/               离线流水线（清洗 / 算法 / 入库）
├─ scripts/                运行与验证脚本
├─ 文档/                   技术文档、口径手册、算法文档、评测报告
├─ schema.sql              主库建表（13 表）    ← 复现必读
├─ Olist_Views.sql         主库视图（10 个）    ← 复现必读
├─ olist_algo_mysql.sql    算法库（9 表 + 结果数据）
├─ 一键导入主库.py          入口：建库并导入 cleaned/*.csv
├─ 一键导入算法库.py        入口：建算法库 + 主库视图
└─ 启动后端.py              入口：启动 FastAPI
```

### 2.4 三个关键设计

**① 图表防幻觉** —— `render_chart` 的参数里**没有数据字段**，只有「画什么」：
`data_from` 指定用哪个工具的既成结果，后端从本轮上下文里取真实返回做确定性转换。
模型无法编造数值；若 `data_from` 本轮未被调用过，工具直接返回错误。

**② 口径即代码** —— 33 条硬规则在模型之前生效（GMV 是否含运费、有效订单如何界定等），
模型只能引用规则编号，不能自行解释口径。规则库版本见 `llm/config.py::RULESET_VERSION`。

**③ 流式不是 token 级** —— ReAct 必须先跑完工具才能生成终稿，所以推送的是
「正在查什么 → 查到几条 → 正在组织结论」的阶段进度，终稿到达后按句落屏。
不做匀速打字机式的伪造。理由写在 `llm/agent/streaming.py` 文件头。

---

## 三、安装与运行

### 3.1 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 纯 Python 包，无编译依赖 |
| MySQL | 8.0+ | 主库 + 算法库 |
| Node.js | 18+ | 前端构建 |

无需 GPU、无需 Docker、无需联网调模型（不配 Key 时走离线确定性引擎，界面会明确标注）。

### 3.2 五步复现

**① 装 Python 依赖（1 分钟）**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

依赖清单：`fastapi` / `uvicorn[standard]` / `PyMySQL` / `pandas` / `numpy` / `scikit-learn` / `requests`。

**② 配环境变量（1 分钟）**

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

**MySQL（`config.py` 读取）**

| 变量 | 默认值 | 必填 | 说明 |
|---|---|---|---|
| `MYSQL_PASSWORD` | `root` | ✅ | 本机 MySQL root 密码，模板里默认值是占位，必须改成你自己的 |
| `MYSQL_HOST` | `localhost` | | 装在本机就保持默认 |
| `MYSQL_PORT` | `3306` | | |
| `MYSQL_USER` | `root` | | |
| `MYSQL_DB` | `olist_db` | | 主库名，13 张表 + 10 个视图 |
| `MYSQL_ALGO_DB` | `olist_algo_db` | | 算法库名，9 张表 |

**大模型（`llm/config.py` 读取，OpenAI 兼容协议）**

| 变量 | 默认值 | 必填 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | 空 | 可选 | 不填则走离线确定性引擎（`provider=offline`，界面会标注） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | | 换通义 / 智谱 / 本地 Ollama 只改这一行 |
| `LLM_MODEL` | `deepseek-chat` | | |
| `LLM_TEMPERATURE` | `0.2` | | 取数类任务不需发散 |
| `LLM_MAX_TOKENS` | `1200` | | 终稿长度上限 |
| `LLM_TIMEOUT` | `45` | | 单次请求超时（秒） |
| `LLM_MAX_STEPS` | `4` | | ReAct 最多几轮工具调用 |
| `LLM_MAX_TOOL_CALLS` | `6` | | 单轮最多几次工具调用（防跑飞） |
| `LLM_RAG_TOP_K` | `4` | | 一次召回几段文档 |
| `LLM_RAG_MIN_SCORE` | `0.05` | | 相关性下限，低于不注入 |
| `LLM_MODE` | `full` | | 消融开关：`full` / `no_tools` / `no_rag` / `baseline`，用于跑对照实验 |

**前端（写在 `web/.env.local`，模板 `web/.env.example`）**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PY_API_BASE` | `http://127.0.0.1:8000` | 前端把 `/api/*` 转发到哪个后端地址，换机器只改这一行 |

`.env` 与 `web/.env.local` 均已在 `.gitignore` 中，不会进仓库；`OPENAI_API_KEY` /
`OPENAI_BASE_URL` 作为兼容别名同样生效（填了会覆盖 `LLM_*` 对应项）。

> 两条线的模板是分开的：根 `.env.example` 管后端 + MySQL，`web/.env.example` 管前端。
> 原因是 Next.js 进程只读 `web/` 下的 `.env.local`，不会读根目录的 `.env` ——
> 这一点不写清楚，新人一定会把 `PY_API_BASE` 填到根 `.env` 里然后疑惑为什么不生效。

**③ 导数据（5 分钟，一次性）**

```bash
python 一键导入主库.py       # 建 olist_db（13 表），导入 cleaned/ 下 13 个 csv
python 一键导入算法库.py     # 建 olist_algo_db（9 表）+ 主库 10 个视图
```

> 仓库不含 128 MB 的 `cleaned/` 与原始数据（体积原因）。获取方式见
> [文档/数据集说明.md](文档/数据集说明.md)，或把 `cleaned/*.csv` 放回项目根目录。
> 注意：`schema.sql` / `Olist_Views.sql` / `olist_algo_mysql.sql` 三个建表脚本**已随仓库提供**，
> 缺少任一个都无法建出完整库。

> ⚠️ **不要手工单独执行 `schema.sql`**。它开头有 13 条 `DROP TABLE IF EXISTS`，
> 且库名写死为 `olist_db`——不管你用 `mysql <别的库> < schema.sql` 指定了什么库，
> 它都会切回 `olist_db` 执行，结果是 13 张表被清空成空表，业务数据全丢。
> 上面两条 `一键导入` 脚本已经包含建表步骤，**不需要**再手工跑 SQL。
> 只在「完全从零、库都还没建」时才单独执行它。
>
> 真误执行了也不用慌，按上面两条命令重跑一遍即可完整恢复（实测约 2 分钟，
> `一键导入主库.py` 会重新建表并导入全部 CSV）。恢复后可这样核对：
>
> ```sql
> SELECT COUNT(*) FROM olist_db.fact_order_master;      -- 99441
> SELECT COUNT(DISTINCT customer_unique_id) FROM olist_db.dim_customer;  -- 96096
> SELECT ROUND(SUM(payment_value),2) FROM olist_db.fact_order_payment_agg;  -- 13591643.70
> ```

**④ 启动（30 秒）**

```bash
# 终端 1：后端 API（8000）
python 启动后端.py

# 终端 2：前端（3000）
cd web
npm install                # 首次运行
npm run dev                # 开发；演示可用 npm run build && npm start
```

浏览器打开 **http://127.0.0.1:3000/**。接口文档在 http://127.0.0.1:8000/docs。
前端通过 `web/next.config.mjs` 的 rewrites 把 `/api/*` 代理到后端，
换后端地址只需设 `PY_API_BASE` 环境变量。

**⑤ 自检（30 秒）**

```bash
python scripts/smoke_test.py     # 服务连通性：数据库 + 8 个核心接口 + 响应时间 + 大模型层
python scripts/llm_smoke.py      # 大模型层 14 项冒烟（护栏 / 出图 / 端到端）
```

两个脚本都会在失败时明确报错并以非 0 退出码结束，不做"重试到通过"的粉饰。
`smoke_test.py` 需要后端已启动，`llm_smoke.py` 不需要。

典型输出（本机实测）：

```
[1/3] 服务与数据库
  PASS  GET /api/health  —— MySQL 8.0.39 · olist_db 正常 · olist_algo_db 正常（RFM 95420 行）
[2/3] 8 个核心业务接口（200 + 返回非空 + < 2 秒）
  PASS  经营看板     /api/dashboard/summary  —— 1059 ms
  ...
[3/3] 大模型层就绪状态
  PASS  GET /api/llm/health  —— 工具 23 个 · 规则 33 条 · RAG 239 段 · 探针 4/4 通
结果：10/10 通过
```

### 3.3 用 Docker 跑（可选）

```bash
docker compose up -d                                   # MySQL + 应用
docker compose run --rm app python 一键导入主库.py       # 首次导数据
docker compose run --rm app python 一键导入算法库.py
```

`docker-compose.yml` 把 MySQL 映射到宿主机 3307，避免与本地 3306 冲突。

**诚实说明**：`Dockerfile` 只覆盖 Python 侧，前端仍需 `cd web && npm run dev` 单独启动；
该配置按标准语法编写，但**未在本机实际构建验证**（开发机未安装 Docker），
推荐用上面的 pip 方式复现（已验证）。

本次已修正两处会直接导致跑不通的问题，供有 Docker 环境的评审复核：

| 问题 | 现象 | 修正 |
|---|---|---|
| `CMD` 调用 `启动后端.py` | 该脚本含 `input()` 交互提示、且绑 `127.0.0.1`，容器内无 TTY 会退出、端口也对外不可达 | 改为直接 `uvicorn app.main:app --host 0.0.0.0` |
| `.dockerignore` 排除了 `*.sql` | 三个建表脚本被挡在镜像外，`一键导入主库.py` 检查到缺 `schema.sql` 直接退出 | 只排除全量导出 `Olist.sql`，保留三个建表脚本 |

### 3.4 从零重算算法结果（可选，验证可复现）

```bash
python pipeline/algo1_model.py      # RFM / K-Means / 漏斗 / 复购
python pipeline/algo2_model.py      # 预测 / 选品 / 定价
python pipeline/import_algo1.py && python pipeline/import_algo2.py
python pipeline/export_algo_to_mysql.py
```

---

## 四、代码规范

前后端各有一套**可执行**的检查工具，配置随仓库提供，clone 下来即可复跑，
不靠「我们很规范」这类口头承诺。

| 范围 | 工具 | 配置文件 | 复跑命令 | 当前结果 |
|---|---|---|---|---|
| 前端类型 | TypeScript `strict` | `web/tsconfig.json` | `cd web && npm run typecheck` | **0 错误** |
| 前端规范 | ESLint（`next/core-web-vitals`） | `web/.eslintrc.json` | `cd web && npm run lint` | **0 warning / 0 error** |
| 后端规范 | Ruff（替代 flake8 + isort + pyupgrade） | `pyproject.toml` | `ruff check .` | **0 错误** |

开发期依赖单独放在 `requirements-dev.txt`，运行项目只需 `requirements.txt`。

### 4.1 分层边界

- **后端三层不互相越界**：`app/` 只做 HTTP 参数校验与响应组装，`llm/` 只管 AI 编排与工具，`pipeline/` 只跑离线算法。路由层不写 SQL，一律走 `app/db.py`。
- **前端**：函数组件 + Hooks；跨层数据全部有 TS 类型（`web/types/`）；服务端组件与客户端组件用 `"use client"` 显式区分；ECharts 按需引入，首屏共享 JS 87.3 kB（全量引入约 1.01 MB）。
- **两个库物理隔离**：业务库 `olist_db` 只读，用户反馈落独立 SQLite（`llm/feedback/feedback.db`），互不影响。

### 4.2 注释约定

模块头写**「这个文件解决什么问题、为什么这样设计」**，不写「本函数返回列表」这类同义反复。
当前覆盖情况（脚本实测）：

- 42 个 Python 模块中 **40 个**有模块级 docstring（另 2 个是空的 `__init__.py`）；
- HTTP 路由层（`app/`）**75%** 的函数带 docstring（49/65）；
- 23 个工具的说明以 **schema description** 形式写在注册表里 —— 模型直接消费这段文字，比 docstring 更靠前、更有效；
- 离线算法脚本（`pipeline/`）以文件头注释声明「输入什么 CSV、输出什么表」。

### 4.3 提交信息约定

`feat` / `fix` / `docs` / `chore` / `refactor` 前缀 + 一句话说明「改了什么、为什么改」，
不含「update」「修改一下」这类无信息量的标题。历史提交可在 GitHub 上逐条核对。

### 4.4 存量问题的处理方式（不隐瞒）

`ruff check` 有 4 条规则做了**全局豁免**、另有 3 条只对**具体文件**放宽，
理由逐条写在同一份 `pyproject.toml` 的注释里，不是静默关规则：

| 豁免项 | 范围 | 理由 |
|---|---|---|
| `E701` 单行 `if` | 全局 | 算法分段统计处一行一个区间，可读性更好 |
| `B905` `zip()` 缺 `strict=` | 全局（存量 6 处） | 数据长度由同源保证；新增代码要求显式传入 |
| `SIM105` `try/except/pass` | 全局 | RAG 打分与出图兜底处故意吞异常 |
| `RET504` 多余赋值 | 全局 | 保留局部变量便于调试断点 |
| `F841` 未使用变量 | 4 个文件 | 5 处早期调试残留，已登记待清理 |
| `B007` 循环键未使用 | 1 个文件 | `import_algo2.py` 的建表缓冲循环 |
| `E402` 导入不在顶部 | 4 个文件 | 需先插 `sys.path` / 先打印横幅，属有意为之 |

---

## 五、团队信息

| 项目 | 内容 |
|---|---|
| 参赛赛道 | 第九届传智杯 · AI WEB 网页开发挑战赛（团队赛） |
| 参赛组别 | **B 组**（非 985/211 普通本科院校） |
| 学校 | 广州商学院 |
| 队长 | 卢泳豪 |
| 团队成员 | 卢泳豪、梁金鹏、王海琳（共 **3 人**，同校） |
| 指导教师 | 叶丽珠（第一指导教师）、郑冬花（第二指导教师） |

### 成员与分工

| 成员 | 负责模块 |
|---|---|
| 卢泳豪（队长） | 项目统筹；AI 接入层（ReAct 编排、三重护栏、评测集）、前端工程化重构（Next.js 迁移、SSE 流式）；数据库设计与数据入库（13 张业务表建表、批量导入、10 个查询视图）；UI 视觉规范与侧栏导航 |
| 梁金鹏 | FastAPI 接口层（47 个接口）；数据清洗与 RFM 用户分群算法（K-Means 分群、转化漏斗、复购分析） |
| 王海琳 | 销量预测 / 选品推荐 / 定价建议算法；图表与页面实现 |

> 说明：以上分工按实际开发记录整理，完整任务排期见团队内部任务打卡表（10.14–10.23）。

---

## 六、文档索引

| 要看什么 | 打开 |
|---|---|
| **技术文档（提交版 · PDF · 29 页）** | [提交材料/电商经营决策智能助手_技术文档_20261117.pdf](提交材料/电商经营决策智能助手_技术文档_20261117.pdf) |
| 技术文档（可编辑源文件） | [提交材料/电商经营决策智能助手_技术文档_20261117.docx](提交材料/电商经营决策智能助手_技术文档_20261117.docx) |
| 技术文档（早期 Markdown 稿） | [文档/技术文档.md](文档/技术文档.md) |
| 提交材料清单 | [提交材料/提交清单_AIWEB.md](提交材料/提交清单_AIWEB.md) |
| 演示视频（成片 6 分 31 秒 · 2026×1080 · 30 fps · 内嵌字幕） | [提交材料/演示视频_AIWEB_20261117.mp4](提交材料/演示视频_AIWEB_20261117.mp4)（31 MB，已修复音量偏小；原始录屏版 83 MB 不进仓库） |
| AI 协同过程（Prompt 快照） | [文档/Prompt快照.md](文档/Prompt快照.md) |
| 演示视频录制脚本 | [文档/演示视频脚本.md](文档/演示视频脚本.md) |
| 数据来源与口径 | [文档/数据集说明.md](文档/数据集说明.md)、[文档/口径手册.md](文档/口径手册.md) |
| 算法实现 | [文档/算法1_算法文档.md](文档/算法1_算法文档.md)、[文档/算法2_算法文档.md](文档/算法2_算法文档.md) |
| 数据库设计 | [文档/数据库设计文档.md](文档/数据库设计文档.md) |
| 接口清单 | [文档/API接口清单_20261112.md](文档/API接口清单_20261112.md) |
| 评测结果 | [文档/评测报告.md](文档/评测报告.md) |
| 验收记录 | [文档/验收记录.md](文档/验收记录.md) |

### 主要接口

| 接口 | 作用 |
|---|---|
| `POST /api/llm/chat` | 对话（核心），body `{"question":"...","mode":"full","history":[...]}` |
| `POST /api/llm/chat/stream` | 同上，SSE 流式 |
| `GET /api/llm/health` | 各层就绪状态（provider / 工具数 / RAG / 规则数） |
| `GET /api/llm/tools` | 23 个工具清单 |
| `GET /api/llm/rules` | 33 条口径规则 |
| `POST /api/llm/feedback` | 提交 👍/👎 与纠正，落 `llm/feedback/feedback.db` |
| `GET /api/llm/feedback/stats` | 反馈统计 |

### 反馈闭环（持续学习）

```bash
python scripts/export_feedback.py     # 导出待审清单，人工归并成规则 / 评测题
python scripts/run_eval.py --gate     # 改完规则跑回归，任一维度掉 >2pt 退出码 1
python scripts/run_eval.py --update-gate   # 确认无回归后更新基线
```

规则库版本在 `llm/config.py::RULESET_VERSION`，每次增删规则同步改版本号。

---

## 七、诚实声明

- 未配置 Key 时所有数字来自**离线规则引擎**，不可当作大模型能力指标；
- 主评测集 100% 属**自出题自评分**，离线引擎在其上拿到 100% 属于过拟合：同一批题换盲测立刻掉到 75%；
- **真实模型（DeepSeek-Chat）实测是反过来的**：主集 91.7%、盲测 **100%** ——
  语义理解解决了泛化，但会偶发漏掉该声明的免责语；
- 图表数字由后端确定性组装，**模型不参与数值生成**；
- 未做参数微调（LoRA），口径靠 prompt 注入与检索；
- **RAG 仍为 TF-IDF 而非向量检索**，理由是答辩现场断网也能跑、零额外依赖；
  接口已抽象，可平滑替换为 bge-m3 + 向量库；
- **多模态尚未覆盖**（当前为纯文本对话 + 结构化图表）；
- 数据为巴西 Olist 公开数据集，货币单位为 BRL，业务结论**不可直接套用于国内平台**。

详见 [文档/技术文档.md](文档/技术文档.md)、[文档/口径手册.md](文档/口径手册.md)、
[文档/评测报告.md](文档/评测报告.md)。

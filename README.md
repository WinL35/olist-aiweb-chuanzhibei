# Olist 电商经营决策 AI Web 应用

> 第九届传智杯全国大学生计算机技能大赛 · **AI WEB 网页开发挑战赛**（团队赛 · B 组）
> 选题方向：**AI 数据分析与可视化** — 基于自然语言交互的数据分析平台

一个以 **前端 Web 应用**为主要呈现形态的电商经营决策系统：用户用自然语言提问，
系统自动**取数 → 分析 → 出图**，每个数字都带口径标注、每张图的数据都来自真实工具返回
（不是模型编的）。底层数据为 Olist 真实交易数据（99,441 订单 / 96,096 客户）。

## 技术栈（按赛道推荐栈选型）

| 层 | 选型 | 说明 |
|---|---|---|
| 前端框架 | **Next.js 14 App Router + React 18 + TypeScript(strict)** | 赛道推荐首选：`App Router` / `Server Components` / `API Routes` / `流式渲染` |
| 样式方案 | **Tailwind CSS 3**（设计令牌集中管理） | `web/tailwind.config.ts` 为唯一配色入口 |
| 图表 | **ECharts 5 按需引入** | 首屏共享 JS 仅 **87.3 kB**（全量包约 1.01 MB） |
| AI 交互 | **SSE 流式**（`text/event-stream`） | 阶段进度 + 终稿按句落屏 |
| 状态与路由 | React Hooks + App Router | 8 条真路由，可深链，`⌘/Ctrl + 1…8` 快捷键 |

## 架构一览

```
┌──────────────────────────────────────────────────────────────┐
│  前端主体 · Next.js 14（web/）                                │
│  ────────────────────────────────────────────────────────    │
│  app/(shell)/  8 个页面路由     ← 评分主战场                  │
│  components/   导航/图表/助手/UI 组件                          │
│  lib/          ECharts 主题、SSE 解析、API 客户端              │
│  app/api/chat/ Next.js API Route → 透传 SSE                   │
└───────────────────────────┬──────────────────────────────────┘
                            │  POST /api/llm/chat/stream
┌───────────────────────────▼──────────────────────────────────┐
│  AI Access Layer · FastAPI（app/ + llm/）                     │
│  ────────────────────────────────────────────────────────    │
│  ReAct planner + 23 个 function calling 工具                  │
│  33 条口径硬规则（先于模型生效）· 239 段 RAG                    │
│  ⇢ 定位：仅作为 AI 能力的接入层（赛道原文口径）                 │
└──────────────────────────────────────────────────────────────┘
```

> 按赛道「特别说明」：作品以前端 Web 应用为主要呈现形态，后端服务仅作为 AI 能力的接入层，
> 不作为重点考察对象。本项目遵循此定位——**评测权重 75% 的部分（AI 技术深度 + 创新性 +
> 前端工程 + 用户体验）全部落在前端与 AI 交互上**。

除对话能力外，前端还包含经营看板、RFM 用户分群、转化漏斗与复购、销量预测、选品建议、
定价建议、模型实验、智能问答共 8 个页面，图表由 ECharts 渲染。

**三条最能体现选题的验证路径**（评委可现场复现）：

| 你会看到什么 | 怎么触发 |
|---|---|
| 一句话出一张图，数字不编 | 智能问答页 → 点「各品类GMV画柱状图」 |
| 多轮追问不失忆 | 上一步之后接着问「那第二名是谁？」 |
| 图表数字可核对 | 对比 `GET /api/dashboard/category` 返回的 GMV，与图上的 y 值完全一致 |

## 团队信息

| 项目 | 内容 |
|---|---|
| 参赛赛道 | 第九届传智杯 · **AI WEB 网页开发挑战赛**（团队赛） |
| 参赛组别 | **B 组**（非 985/211 普通本科院校本科生） |
| 学校 | 广州商学院 |
| 团队成员 | 卢泳豪（队长）· 待补 |
| 分工 | 前端开发 / AI 工程 / 数据与算法 —— 待细化 |
| 指导教师 | 待补 |

> 注：本表「待补」项须在提交前补齐，官方要求 README 须包含完整团队信息。

## 10 分钟极速复现（官方要求的复现指南）

> 环境：Windows / macOS / Linux 均可，需要 **Python 3.10+** 与 **MySQL 8.0+**。
> 无需 GPU，无需 Docker，无需联网调模型也能跑（离线兜底引擎）。

**① 装依赖（1 分钟）**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

依赖清单（`requirements.txt`，全部为纯 Python 包，无编译依赖）：
fastapi / uvicorn[standard] / PyMySQL / pandas / numpy / scikit-learn / requests。

**② 配环境变量（1 分钟）**

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

然后编辑 `.env`，最少改这两个：

| 变量 | 必填 | 说明 |
|---|---|---|
| `MYSQL_PASSWORD` | ✅ | 本机 MySQL root 密码 |
| `LLM_API_KEY` | 可选 | 不填则走离线确定性引擎（界面会明确标注） |

其余变量（`MYSQL_HOST/PORT/USER/DB`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_TEMPERATURE`、
`LLM_MAX_STEPS` 等）均有默认值，模板里有注释说明。`.env` 已在 `.gitignore` 中，不会进仓库。

**③ 导数据（5 分钟，一次性）**

```bash
python 一键导入主库.py       # 建 olist_db（23 表），导入 cleaned/ 下 13 个 csv
python 一键导入算法库.py     # 建 olist_algo_db（9 表）+ 主库 10 个视图
```

> 仓库不含 128MB 的 `cleaned/` 与原始数据（体积原因）。获取方式见
> [文档/数据集说明.md](文档/数据集说明.md)；或直接把 `cleaned/*.csv` 放回项目根目录。

**④ 启动（30 秒）**

```bash
# 终端 1：后端 API（FastAPI，8000 端口）
python 启动后端.py

# 终端 2：Web 前端（Next.js 14，3000 端口）
cd web
npm install          # 首次运行
npm run dev          # 开发模式；演示可用 npm run build && npm start
```

浏览器打开 **`http://127.0.0.1:3000/`** —— Next.js App Router 主界面。

> 旧版静态页仍保留在 `http://127.0.0.1:8000/`（Vue CDN 实现，作为技术演进对照），
> 接口文档在 `http://127.0.0.1:8000/docs`。
> 前端默认连 `http://127.0.0.1:8000`，如后端换了地址，用 `PY_API_BASE` 环境变量覆盖。

**⑤ 自检（30 秒）**

```bash
python scripts/smoke_test.py    # 接口连通性与响应时间
python scripts/llm_smoke.py     # 大模型层 14 项冒烟（含护栏、出图、端到端）
```

两个脚本都会在失败时明确报错，不会伪造通过。

**（可选）用 Docker 跑**

```bash
docker compose up -d                                   # MySQL + 应用
docker compose run --rm app python 一键导入主库.py       # 首次导数据
docker compose run --rm app python 一键导入算法库.py
```

> 提供 `Dockerfile` 与 `docker-compose.yml`（MySQL 映射到宿主机 3307，避免与本地 3306 冲突）。
> 说明：本机无 Docker 环境，该配置**未做实际构建验证**，仅按标准语法编写；
> 推荐用上面的 pip 方式复现（已验证）。

## 交付物速查

| 要看什么 | 打开 |
|---|---|
| 提交前核对清单 | [提交材料/提交清单.md](提交材料/提交清单.md) |
| AI 协同过程（Prompt 快照） | [文档/Prompt快照.md](文档/Prompt快照.md) |
| 技术文档（PDF 14 页） | `提交材料/技术文档.pdf`，源文件 [文档/技术文档.md](文档/技术文档.md) |
| 演示视频录制脚本 | [文档/演示视频脚本.md](文档/演示视频脚本.md) |
| 数据来源与口径 | [文档/数据集说明.md](文档/数据集说明.md)、[文档/口径手册.md](文档/口径手册.md) |
| 算法怎么做的 | [文档/算法1_算法文档.md](文档/算法1_算法文档.md)、[文档/算法2_算法文档.md](文档/算法2_算法文档.md) |
| 系统全貌 | [文档/项目文档.md](文档/项目文档.md) |
| 大模型层设计 | [文档/垂直大模型方案.md](文档/垂直大模型方案.md) |
| 评测结果 | [文档/评测报告.md](文档/评测报告.md) |
| 各类取证截图 | `文档/截图/`（对话出图、浮窗、页面入口） |
| 自测与复检记录 | [文档/验收记录.md](文档/验收记录.md) |

## 目录说明

**代码结构（分层，按职责划分）**

```
├─ 启动后端.py            入口：启动 FastAPI 服务
├─ 一键导入主库.py         入口：建库建表并导入 cleaned/*.csv
├─ 一键导入算法库.py       入口：建算法库(9表)+主库视图(10个)，不需要 mysql 命令行
├─ config.py              全局配置（数据库连接、目录常量）
├─ .env.example           环境变量模板（复制为 .env 使用，.env 已 gitignore）
├─ app/                   Web 层：FastAPI，44 个接口、5 个路由模块
│    ├─ main.py           应用装配、静态资源挂载、CORS
│    ├─ db.py             数据库连接池与查询封装
│    ├─ llm_api.py        大模型层接口（chat / health / tools / eval / feedback）
│    └─ dashboard/analysis/pricing/experiment/selection.py   五个路由模块
├─ llm/                   大模型层（详见下文「垂直行业大模型层」）
│    ├─ agent/            planner（ReAct）、prompts、guard（三重护栏）、composer
│    ├─ tools/            registry（23 个工具 schema）、executor、chart（出图）
│    ├─ knowledge/        33 条口径规则 + 239 段 RAG
│    └─ eval/             60 题主集 + 20 题盲测
├─ pipeline/              离线流水线：数据清洗 + 算法模型 + 数据导入
│    ├─ clean_merge.py            原始 Dataset/*.csv → cleaned/*.csv（预处理）
│    ├─ algo1_model.py            RFM / K-Means / 漏斗 / 复购
│    ├─ algo2_model.py            预测 / 选品 / 定价 / 离线实验
│    ├─ import_algo1.py           算法1 CSV → SQLite
│    ├─ import_algo2.py           算法2 CSV → SQLite
│    ├─ export_algo_to_mysql.py   SQLite → MySQL（olist_algo_db）
│    └─ load_mysql.py             建表 + cleaned CSV → olist_db
├─ web/                   前端：Next.js 14 + React 18 + TS + Tailwind（8 个路由）
│    ├─ app/              App Router：7 个看板页 + 对话页 + /api/chat 透传
│    ├─ components/       图表（ECharts 按需）、UI 基元、对话组件、侧栏布局
│    ├─ lib/              取数层、SSE 解析、ECharts 注册、格式化
│    └─ types/api.ts      40 个后端接口的 TypeScript 类型定义
├─ schema.sql             主库建表脚本（olist_db，13 表）← 复现必读
├─ Olist_Views.sql        主库视图脚本（olist_db，10 个视图）← 复现必读
├─ olist_algo_mysql.sql   算法库建表 + 结果数据（olist_algo_db，9 表）
├─ cleaned/               清洗后的 13 张业务数据表（128 MB，由 pipeline 重建）
├─ 算法1/、算法2/           模型结果 CSV（由 pipeline 重建）
└─ Olist.sql              全量原始数据导出（151 MB，体积过大不入库）

> 建表链：`schema.sql` → `Olist.sql`/`cleaned/*.csv` → `Olist_Views.sql` → `olist_algo_mysql.sql`。
> 前两个脚本已随仓库提供，clone 后无需下载 45 MB 原始数据即可建出空库结构。
```

> 全部脚本均可在项目根目录用 `python pipeline/xxx.py` 直接运行；
> `config.py` 通过 `BASE_DIR` 定位根目录，`pipeline/` 内的脚本已自带向上一级寻址，无需 `cd`。

**材料目录**

- `文档/`：项目文档、数据库设计文档、算法1/算法2 算法文档、验收记录、说明。
- `答辩材料/`：`答辩PPT.pptx`、`演示脚本.md`、`截图/`（7 张 2 倍分辨率页面截图）。
- `交付包/`：提交用压缩包、`算法代码_Review包/`。
- `归档/`：历史备份（`olist_algo_mysql.sql.bak`）与不参与提交的临时文件。

## 运行前准备

需要 Python 3.10+、MySQL 8.0+。在项目根目录执行：

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

将 MySQL 账号、密码和库名通过环境变量传入，避免把个人密码写进代码：

```bash
# macOS / Linux
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=你的密码
export MYSQL_DB=olist_db
export MYSQL_ALGO_DB=olist_algo_db
```

> 也可以什么都不设：`一键导入主库.py`、`一键导入算法库.py`、`启动后端.py` 发现连不上时都会
> 提示你输入 MySQL 密码（输入内容会显示出来，属正常），不必先去改 `config.py`。

## 初始化数据

新机器上按顺序执行（全部是 Python 脚本，不需要 mysql 命令行）：

> **可选第 0 步：从原始数据重建 `cleaned/`**（交付包已带清洗结果，通常跳过）
> 把 Kaggle Olist 的 9 个原始 csv 放到项目根目录 `Dataset/`，执行 `python pipeline/clean_merge.py`，
> 会重新生成 `cleaned/` 13 个 csv 与 `data_quality_report.txt`。脚本带列契约校验，表头与下游不一致时会中止。

1. `python 一键导入主库.py` —— 导入 `cleaned/` 主业务数据，建 `olist_db`（13 张表）。
2. `python 一键导入算法库.py` —— 执行 `olist_algo_mysql.sql` 建算法结果库 `olist_algo_db`（9 张表），并执行 `Olist_Views.sql` 建主库 10 个查询视图，导入后自动核对行数。
3. `python 启动后端.py`，另开终端 `python scripts/smoke_test.py` 验收。

可选（从零重算算法结果，验证可复现）：依次运行 `pipeline/algo1_model.py`、`pipeline/algo2_model.py` 重新生成 CSV，再运行 `pipeline/import_algo1.py`、`pipeline/import_algo2.py`（写入并校验 SQLite 快照 `olist_algo.db`），最后 `pipeline/export_algo_to_mysql.py` 同步到 MySQL。

详细字段、表关系和导入校验见 [数据库设计文档.md](文档/数据库设计文档.md)。

## 启动与验收

```bash
python 启动后端.py
# 或：python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`，接口文档在 `http://127.0.0.1:8000/docs`。

另开一个终端，待服务启动后运行：

```bash
python scripts/smoke_test.py
```

该脚本检查健康状态、核心页面依赖接口和单次响应是否低于 2 秒。若数据库未初始化，脚本会明确报错而不会伪造通过。

最近一次本地验收结果见 [验收记录.md](文档/验收记录.md)。

## 结果口径

Olist 不包含浏览、加购行为，因此“转化分析”采用订单状态和时间戳构建订单漏斗；它不是曝光到下单的行为漏斗。销量预测的真实离线结果及限制见 [算法2_算法文档.md](文档/算法2_算法文档.md)，不得将其表述为全面显著优于移动平均基线。

---

## Web 前端（web/）

技术栈：**Next.js 14（App Router）+ React 18 + TypeScript（strict）+ Tailwind CSS 3 + ECharts 5（按需引入）**

| 能力 | 落地方式 | 位置 |
|---|---|---|
| 服务端组件 RSC | 看板各卡片在服务端取数，HTML 直出数字，不必等客户端 JS 水合 | `app/(shell)/dashboard/page.tsx` |
| 流式渲染 | 每个数据块一个 `<Suspense>` 边界，谁先返回谁先刷新 | `components/dashboard/sections.tsx` |
| Route Handler | 对话 SSE 逐块透传，避免代理层把事件攒成一包 | `app/api/chat/route.ts` |
| 流式对话 | 阶段事件（护栏/口径/检索/工具）+ 正文按句落屏 | `llm/agent/streaming.py`、`lib/sse.ts` |
| 类型安全 | 40 个后端接口全量建模，`tsc --noEmit` 零错误 | `types/api.ts` |
| 样式体系 | 原子化 CSS，设计令牌与旧版色板同源 | `tailwind.config.ts` |

路由：`/dashboard` `/rfm` `/conversion` `/prediction` `/recommend` `/pricing` `/experiment` `/assistant`

三个刻意的取舍（也是答辩时值得讲的点）：

1. **对话页是客户端组件**。多轮历史、流式增量、图表导出都依赖浏览器状态，放服务端没有收益。
2. **图表配置对象放宽类型**。ECharts 官方类型对「运行时拼装 option」极不友好，在 `EChart` 入口统一断言；业务数据的类型仍然严格。
3. **流式不是 token 级**。ReAct 必须先跑完工具调用才可能生成终稿，所以选择「真实推送过程进度 + 终稿按句落屏」，而不是伪造一个匀速打字机。理由写在 `llm/agent/streaming.py` 文件头。

## 垂直行业大模型层（llm/）

在原有"分析 → 算法 → 页面"三层之上，新增一层**经营决策助手**：
用通用模型底座 + 行业口径 + 真实数据接口，回答老板会问的经营问题，**并且能把答案画成图**。

### 五层结构

| 层 | 位置 | 内容 |
|---|---|---|
| 数据层 | `olist_db` / `olist_algo_db` | 23 表 10 视图 + 9 张算法结果表 |
| 知识层 | `llm/knowledge/` | **33 条口径硬规则** + **239 段文档 RAG**（TF-IDF，零依赖） |
| 工具层 | `llm/tools/` | **23 个** function calling 工具（22 查询 + 1 出图），复用 `app/` 路由函数 |
| 决策层 | `llm/agent/` | ReAct 编排 / 离线确定性组装 + **三重护栏** |
| 评测层 | `llm/eval/` | 60 题主集 + 20 题盲测 × 4 种消融模式 |

### 对话式分析与可视化（本作品的核心能力）

一条问题走完三步，全程可追溯：

```
用户提问
  → [ReAct step1] 模型选择查询工具，如 dashboard_category
  → [ReAct step2] 模型调用 render_chart(chart_type, data_from, x_field, y_fields)
  → [ReAct step3] 模型基于工具真实返回撰写结论，图与文字一起返回前端
```

**图表防幻觉的关键设计**：`render_chart` 的参数里**没有数据字段**，只有「画什么」——
`data_from` 指定用哪个工具的既成结果，后端从本轮上下文里取原始返回做确定性转换。
所以模型无法编造数值；且若 `data_from` 本轮没被调用过，工具直接返回错误。
图注还会自动标注口径编号（如「GMV = Σ 商品单价，不含运费（GMV-01）」）。

两条前端入口：

| 入口 | 定位 | 能力 |
|---|---|---|
| 看板右下角浮窗（`static/assets/ai-widget.js`） | 边看图边随手问 | 对话、出图、多轮追问、导出 PNG/CSV |
| 独立分析页 `assistant.html` | 完整分析工作台 | 上述全部 + 取数轨迹面板、口径/依据侧栏、消融模式切换、👍👎 反馈 |

### 启动

```bash
python 启动后端.py
```

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/ | 经营看板（右下角带对话浮窗） |
| http://127.0.0.1:8000/assistant.html | 独立对话页面（完整工作台） |
| http://127.0.0.1:8000/docs | 接口文档（含 `/api/llm/*`） |

### 接入真实模型底座

不配置也能跑——此时走**离线确定性引擎**，回答里会明确标注 `provider=offline`。
配置任一 OpenAI 兼容模型即可切换到 LLM 路径（DeepSeek / Qwen / GLM / vLLM / Ollama 均可）：

```bash
# 写进 .env 即可，启动时自动加载（不必 export）
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

验证是否真的接通：`GET /api/llm/health` 应返回 `"provider":"openai_compat"` 且 `"has_api_key":true`。

### 主要接口

| 接口 | 作用 |
|---|---|
| `POST /api/llm/chat` | 对话（核心），body `{"question":"...","mode":"full","history":[...]}` |
| `GET /api/llm/chat?q=...` | 同上，GET 版便于 curl 演示 |
| `GET /api/llm/health` | 各层就绪状态（provider / 工具数 / RAG / 规则数） |
| `GET /api/llm/tools` | 23 个工具清单 |
| `GET /api/llm/rules` | 33 条口径规则 |
| `GET /api/llm/examples` | 示例问题（前端快捷按钮） |
| `GET /api/llm/eval/run?limit=8` | 在线跑一小批评测 |
| `POST /api/llm/feedback` | 提交 👍/👎 与「纠正」，落 `llm/feedback/feedback.db` |
| `GET /api/llm/feedback/stats` | 反馈统计（总数/好评/差评/待审） |

### 持续学习（反馈闭环）

对话页每条回答下方有 👍/👎 与「纠正」输入框，反馈落 SQLite，不改模型参数：

```bash
python scripts/export_feedback.py          # 导出待审清单，人工归并成规则/评测题
python scripts/run_eval.py --gate          # 改完规则跑回归，任一维度掉 >2pt 退出码 1
python scripts/run_eval.py --update-gate   # 确认无回归后更新基线
```

规则库版本在 `llm/config.py::RULESET_VERSION`，每次增删规则同步改版本号。

### 验证

```bash
python scripts/llm_smoke.py     # 14 项冒烟检查（含护栏与端到端）
python scripts/run_eval.py      # 全量评测，生成 文档/评测报告.md
python scripts/run_eval.py --blind   # 盲测集
```

### 诚实声明

- 未配置 Key 时所有数字来自**离线规则引擎**，报告里已标注"仅反映管线有效性"，
  不可当作大模型能力指标；
- 主评测集 100% 属**自出题自评分**，离线引擎在上面拿到 100% 属于**过拟合**：
  同一批题换盲测立刻掉到 75%；
- **真实模型（DeepSeek-Chat）实测结果是"反过来的"**：主集 91.7%、盲测 **100%** ——
  语义理解解决了泛化，但会偶发漏掉该声明的免责语（A 口径 80%）；
  两份报告都保留：`文档/评测报告.md`（真模型）与 `文档/评测报告_离线基线_20261102.md`（离线消融）；
- 图表数字由后端从工具返回确定性组装，**模型不参与数值生成**；
  `render_chart` 若指定的数据源本轮未被调用会直接报错，这是刻意设计的防编造机制；
- 未做参数微调（LoRA），口径靠 prompt 注入与检索，原因与触发条件见
  [垂直大模型方案.md](文档/垂直大模型方案.md) 第八节；
- 数据为巴西 Olist 公开数据集，货币单位为 BRL，业务结论**不可直接套用于国内平台**。

详见 [垂直大模型方案.md](文档/垂直大模型方案.md)、[口径手册.md](文档/口径手册.md)、
[评测报告.md](文档/评测报告.md)。

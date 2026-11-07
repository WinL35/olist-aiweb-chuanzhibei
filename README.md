# Olist 电商经营分析与智能选品平台

基于 Olist Brazilian E-Commerce Public Dataset 的本地 Web 平台。系统将经营看板、RFM 用户分群、订单转化与复购、销量预测、选品建议、定价建议和离线模型评估整合到同一界面。

## 交付物速查

| 要看什么 | 打开 |
|---|---|
| 提交前核对清单 | [提交材料/提交清单.md](提交材料/提交清单.md) |
| 三分钟跑起来 | 本文件「初始化数据」「启动与验收」两节 |
| 数据来源与口径 | [文档/数据集说明.md](文档/数据集说明.md) |
| 算法怎么做的 | [文档/算法1_算法文档.md](文档/算法1_算法文档.md)、[文档/算法2_算法文档.md](文档/算法2_算法文档.md) |
| 系统全貌 | [文档/项目文档.md](文档/项目文档.md) |
| 演示视频（4 分 53 秒） | [B 站 BV1tH4P6ZETk](https://www.bilibili.com/video/BV1tH4P6ZETk)（二维码在申报书附录） |
| 答辩 PPT（10 页，**旧版**） | `答辩材料/答辩PPT.pptx`（仍是题目一版本，决赛前需重做） |
| 自测与复检记录 | [文档/验收记录.md](文档/验收记录.md) |

## 目录说明

**代码结构（分层，按职责划分）**

```
├─ 启动后端.py            入口：启动 FastAPI 服务
├─ 一键导入主库.py         入口：建库建表并导入 cleaned/*.csv
├─ 一键导入算法库.py       入口：建算法库(9表)+主库视图(10个)，不需要 mysql 命令行
├─ config.py              全局配置（数据库连接、目录常量）
├─ app/                   Web 层：FastAPI，33 个 GET 接口、5 个路由模块
│    ├─ main.py           应用装配、静态资源挂载、CORS
│    ├─ db.py             数据库连接池与查询封装
│    └─ dashboard/analysis/pricing/experiment/selection.py   五个路由模块
├─ pipeline/              离线流水线：数据清洗 + 算法模型 + 数据导入
│    ├─ clean_merge.py            原始 Dataset/*.csv → cleaned/*.csv（预处理）
│    ├─ algo1_model.py            RFM / K-Means / 漏斗 / 复购
│    ├─ algo2_model.py            预测 / 选品 / 定价 / 离线实验
│    ├─ import_algo1.py           算法1 CSV → SQLite
│    ├─ import_algo2.py           算法2 CSV → SQLite
│    ├─ export_algo_to_mysql.py   SQLite → MySQL（olist_algo_db）
│    └─ load_mysql.py             建表 + cleaned CSV → olist_db
├─ static/                前端：Vue 3 + ECharts（7 页 / 21 图，依赖已本地化）
├─ cleaned/               清洗后的 13 张业务数据表（128 MB）
├─ 算法1/、算法2/           模型结果 CSV
└─ *.sql、olist_algo.db    建表脚本、完整数据泵、算法库 SQLite
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

## 垂直行业大模型层（llm/）

在原有"分析 → 算法 → 页面"三层之上，新增一层**经营决策助手**：
用通用模型底座 + 行业口径 + 真实数据接口，回答老板会问的经营问题。

### 五层结构

| 层 | 位置 | 内容 |
|---|---|---|
| 数据层 | `olist_db` / `olist_algo_db` | 13 表 10 视图 + 9 张算法结果表 |
| 知识层 | `llm/knowledge/` | **33 条口径硬规则** + **239 段文档 RAG**（TF-IDF，零依赖） |
| 工具层 | `llm/tools/` | **22 个** function calling 工具，复用 `app/` 路由函数 |
| 决策层 | `llm/agent/` | ReAct 编排 / 离线确定性组装 + **三重护栏** |
| 评测层 | `llm/eval/` | 60 题主集 + 20 题盲测 × 4 种消融模式 |

### 启动

```bash
python -m uvicorn app.main:app --reload --port 8000
```

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/assistant | 对话页面（独立页面，不影响原有 7 个页面） |
| http://127.0.0.1:8000/docs | 接口文档（含 `/api/llm/*`） |

### 接入真实模型底座（可选）

不配置也能跑——此时走**离线确定性引擎**，回答里会明确标注。
配置任一 OpenAI 兼容模型即可切换到 LLM 路径：

```bash
export LLM_API_KEY=sk-xxx
export LLM_BASE_URL=https://api.deepseek.com/v1   # 或 Qwen/GLM/vLLM/Ollama
export LLM_MODEL=deepseek-chat
```

### 主要接口

| 接口 | 作用 |
|---|---|
| `POST /api/llm/chat` | 对话（核心），body `{"question": "...", "mode": "full"}` |
| `GET /api/llm/chat?q=...` | 同上，GET 版便于 curl 演示 |
| `GET /api/llm/health` | 各层就绪状态 |
| `GET /api/llm/tools` | 22 个工具清单 |
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
- 主评测集 100% 属**自出题自评分**，会过拟合；盲测集第一次为 **75%**，
  失败的 5 题全是意图路由问题，这才是真实泛化下界；
- 未做参数微调（LoRA），口径靠 prompt 注入与检索，原因与触发条件见
  [垂直大模型方案.md](文档/垂直大模型方案.md) 第八节。

详见 [垂直大模型方案.md](文档/垂直大模型方案.md)、[口径手册.md](文档/口径手册.md)、
[评测报告.md](文档/评测报告.md)。

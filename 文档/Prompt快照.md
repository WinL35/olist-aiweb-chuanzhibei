# AI 对话历史 Prompt 快照

> 赛道：第九届传智杯 · **AI WEB 网页开发挑战赛（团队赛 · B 组）**· 赛道方向「AI 数据分析与可视化」
> 说明：本文件从实际开发对话中整理，覆盖 **4 条核心功能迭代的完整 Prompt 链**。
> 每条链包含：**原始提问 → AI 的判断与建议 → 落地改动 → 遇到的 Bug →
> 我如何引导 AI 定位修复 → 验证证据**。
>
> AI 工具：WorkBuddy（IDE 内 AI 编程助手，具备文件读写、命令执行、浏览器自动化能力）
> 模型底座：Claude Sonnet（编码）/ DeepSeek-Chat（被开发系统自身调用的模型）
> 项目起始提交：`626cfd6 chore: 传智杯参赛基线`；当前 HEAD 见仓库 `git log`
>
> **口径说明（2026-11-14）**：本文件最初按「AI创新应用挑战赛 · 个人赛 · 选题 8」撰写，
> 现投赛道为 AI WEB（团队赛）。开发过程与 Prompt 内容本身不变，
> 仅赛道命名与材料项数按 AI WEB 口径修正。

---

## 链 0：项目起点与选题对齐

**我的 Prompt（原话）**

> @image#1:Clipboard_Screenshot.png 选题是这个，源文件是早期版本，现在我要将这个文件
> 修改成完全符合传智杯要求的项目，给出修改意见还有方法，大模型要不要重新接，现在缺什么

**AI 的判断**（关键部分摘录）

> 选题 8「AI数据分析与可视化」—— 这个跟现有项目底子高度吻合。但之前的方案有个前提错了：
> 当时以为传智杯是「选题自由」或「科研助手固定命题」，现在有了明确的选题 8。
> ……问题在于「可视化」：看板里 20 多张 ECharts 图全是写死的，而对话区 `assistant.html:154`
> 的 `render()` 只处理加粗、列表和标题 —— **它不能出图**。
> 评委只要问一句「帮我把各品类 GMV 画成柱状图」，现在只会回一段文字。
> 选题原文写的是「通过对话方式完成数据查询、分析与**可视化**」，这一条就够把「解题有效性」打穿。

**AI 给出的三件事**（我认同并采纳）

1. 大模型不用重写架构：`planner.py:88-114` 已是完整 ReAct 循环，`llm/config.py:21` 只差一个 `LLM_API_KEY`，
   但必须同时改 Prompt（加出图指令）、工具集（加出图工具）、接口（加 history）三处；
2. 出图的关键设计：**图表数字必须来自工具返回值，模型只决定「画什么」不决定「画多少」**；
3. 必须先修一个隐藏 Bug：`guard.py` 的 SQL 白名单视图名与库里实际视图 10 对 3。

**我的追问方式（经验）**：没有直接说「帮我做」，而是先让它**实测再说话**——
后面所有结论我都要求带文件行号和接口返回，避免它凭印象编。

---

## 链 1：接通真实模型底座（含 2 个真实 Bug）

### 1.1 我的 Prompt

> deep seek密钥sk-bc69…（略），开始按照缺少项进行改进

> ⚠️ 安全处理：AI 收到 key 后主动提示
> 「这个 key 已经以明文出现在聊天里，我不会把它写进任何会被 git 提交的文件」，
> 后续只落到 `.env`（已被 `.gitignore` 排除），并建议赛后轮换。本条为真实交互。

### 1.2 AI 的动作与建议

| 步骤 | AI 做了什么 | 为什么 |
|---|---|---|
| 1 | `curl` 直连 `api.deepseek.com/v1/models` 验 key | 先证 key 有效，再谈接项目 |
| 2 | 建 `.gitignore`：排除 `.env`、`cleaned/`、`算法1/2`、SQL 转储、`.workbuddy` | 仓库 325MB 推不上 GitHub，且不能泄密 |
| 3 | 补 `requirements.txt` 的 `requests` | `llm/providers` 依赖它，漏写会导致评委首启即崩 |
| 4 | 建 `.env.example`（模板进仓库）+ `.env`（本地） | 官方要求「环境变量模板」 |

### 1.3 Bug A：`git init` 在中文+不间断空格路径下静默失败

**现象**

```
$ git init -q && git config user.name ...
fatal: not a git repository: ...
$ cat .git/config     # 不完整
$ ls .git/HEAD        # 不存在
```

**我的引导 Prompt**

> `git init` 在 junction 路径下被拒了（写 config 权限问题）。诊断一下

**AI 的排查路径（值得复用的思路）**

1. `ls -la .git` 看目录是否建了 → 建了，但只有半套；
2. `touch .git/test_write` 测写权限 → 可写，排除权限；
3. `cat .git/config` + `ls .git/HEAD` → **config 残缺、HEAD 缺失**；
4. 结论：`git init` 中途失败，根因是目录名末尾是 **U+00A0（不间断空格）**，
   与普通空格肉眼无差但 git 处理异常。

**修复**：手工补最小可用仓库结构

```bash
rm -rf .git && mkdir -p .git/refs/heads .git/objects .git/info .git/hooks
printf 'ref: refs/heads/main\n' > .git/HEAD
printf '[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = false\n' > .git/config
git rev-parse --is-inside-work-tree   # → true
```

**结果**：首次提交 `626cfd6`，**103 文件 / 2.1MB**（从 325MB 瘦身），历史第一条就干净。

### 1.4 Bug B：接口返回被包了一层，我取错层级

**现象**：按文档写的 `d['provider']` 全部拿到 `None`。

**我的 Prompt**

> 返回被包了一层 `{code, data}`，我取错层了。重测

**AI 的处理**：不猜，先把原始响应落盘再解析

```bash
curl ... -o _tmp_chat.json
python -c "raw=json.load(...); d=raw.get('data', raw); print(raw.get('code'), d.get('provider'))"
```

**结果**：`code=0`，`provider=openai_compat`，`model=deepseek-chat`，
`tools_used=['dashboard_category']`，2 步完成，5.5s。

**这条链的价值**：验证了方案里的关键判断 —— **接上真模型后，离线引擎的意图错路由问题自动消失**
（离线版把「哪个品类卖得最好」错路由到 `dashboard_summary`，真模型正确选了 `dashboard_category`）。

---

## 链 2：对话驱动出图（选题 8 的题眼，核心功能）

### 2.1 我的 Prompt

> 增加一个回答助手功能
> （AI 先澄清形态，我选择：**看板内嵌对话浮窗（推荐）**）

> 前序 Prompt（在选题分析阶段）：
> 给出修改意见还有方法，大模型要不要重新接，现在缺什么

### 2.2 AI 的设计建议（我采纳的核心约束）

> **图表里的每个数字必须来自工具返回值，模型只被允许决定「画什么」，不允许提供「画多少」。**
> 新增 `render_chart(chart_type, data_from, x_field, y_fields)`，参数里没有数据字段，
> 只能指定「用哪个工具的既成结果」，后端做确定性转换。原因是：让模型直接吐 ECharts 的
> `series.data`，它一定会编数字 —— **一个编了数的 BI 图比没图严重得多**，评委拿数字一核对就穿帮。

### 2.3 落地改动（AI 自主完成，我审）

| 文件 | 改动 |
|---|---|
| `llm/tools/chart.py`（新增） | `build_option()` 纯函数：记录数组 → ECharts option，字段不存在抛 `ChartError` |
| `llm/tools/executor.py` | 加 thread-local「本轮上下文」`begin_turn()/last_result()`；`execute()` 记录每次工具原始返回；`render_chart` 从中取数，`data_from` 未调用过则报错 |
| `llm/tools/registry.py` | 注册 23 个工具 schema，描述里写明「先查再画」的调度要求 |
| `llm/agent/prompts.py` | 输出结构加【可视化】段，明确**禁止编造图表数值** |
| `llm/agent/planner.py` | `run()` 入口 `begin_turn()`；收集 `charts` 进响应 |
| `app/llm_api.py` | `ChatIn` 加 `history` 字段，支持多轮追问 |

### 2.4 AI 的自检方式（值得学习）

写完不直接跑服务，先做**离线断言**：

```
✓ 模块导入 OK
✓ bar/line/pie 三图型构建成功
✓ 坏字段被拦截: 字段 category 不存在
✓ 未查先画被拦截: 本轮未调用 dashboard_category，无法出图
```

### 2.5 端到端验证（真实模型）

**Prompt**：`把各品类的GMV画成柱状图看看`

**返回**：

```
tools : ['dashboard_category', 'render_chart']
charts: 1 张   bar | 品类 GMV 排行 Top 15（BRL）
y 前3 : [1258681.34, 1205005.68, 1036988.68]   ← 与直连接口完全一致，未编造
口径  : GMV = Σ 商品单价，不含运费（GMV-01）；货币 BRL（GMV-04）
```

**额外收获**：模型自发在图注写了口径编号 —— 这正是设计里预埋的加分项，它自己做了。

---

## 链 3：看板内嵌浮窗 + 真实浏览器验证（踩坑最多的一条链）

### 3.1 我的 Prompt

> 问答助手在哪里
> → AI 发现首页侧栏**根本没有入口**，只有独立页面 URL；于是补 `ai-entry` 卡片 + 助手页「← 返回看板」

> 增加一个回答助手功能
> → AI 用 AskUserQuestion 澄清「浮窗 / 侧栏 / 独立页 / 全新助手」四种形态，我选浮窗

### 3.2 AI 的实现要点

- 新文件 `static/assets/ai-widget.js`（8.4KB，零依赖）
- 复用 `/api/llm/chat`（`mode=full` + 最近 6 轮 `history`）
- 气泡内 `echarts.init` 渲染 `render_chart` 返回的 option，配 PNG/CSV 导出
- 3 个示例 chip、Esc 收起、元信息显示 `provider/model · 工具×N · 耗时`

### 3.3 Bug C：误判「服务挂了」（代理陷阱）

**现象**：`curl http://127.0.0.1:8000/api/health` 返回空 / 000，我以为服务没起来。

**AI 的排查**：`env | grep -i proxy` → 本机有 `HTTP_PROXY=http://127.0.0.1:54967`，
**curl 把 127.0.0.1 也送了代理**，报 `upstream connect failed`。

**修复**：所有本地请求加 `--noproxy '*'`。教训已写进 README 的排查小节。

### 3.4 Bug D：headless 浏览器拿不到 page target

**现象**：CDP 探针一直打印 `FAIL: 调试端口未就绪`。

**AI 的定位过程**

1. `tasklist /FI "IMAGENAME eq msedge.exe"` → 进程存在；
2. 单独 `spawn` 并抓 stderr → 看到 `DevTools listening on ws://127.0.0.1:9333/...`，端口确实起了；
3. 请求 `/json/list` → **返回空数组**；
4. 结论：`--headless=new` 启动后**初始没有 page target**，需主动创建。

**修复**

```js
PUT /json/new?url=http://127.0.0.1:8000/
```

### 3.5 Bug E：CDP 响应多一层，取到 undefined

**现象**：`首页入口: undefined`

**AI 的修正**：CDP 的响应结构是 `{id, result:{result:{value}}}`，
我写成了 `resp.result.value`，**少一层**。改成 `resp.result.result.value`。

### 3.6 最终验证证据（真实 Edge + CDP，1440×900）

```
FAB: {"found":true,"rect":{"x":1358,"y":818,"w":56},"visible":true,"panelExists":true}
面板: {"on":true,"welcome":1,"rect":{"w":400,"h":600},"chips":3}
图表: {"canvasCount":1,"chartSized":true,"thinking":false,
       "meta":"openai_compat/deepseek-chat\n工具×2\n5400ms"}
追问: {"count":5,"thinking":false,
       "text":"【结论】 第二名是 watches_gifts，GMV 为 R$ 1,205,005.68…"}
PASS: 浮窗对话出图验证通过
```

截图存档：`文档/截图/看板浮窗_展开.png`、`文档/截图/看板浮窗_对话出图.png`、
`文档/截图/对话出图验证.png`、`文档/截图/首页问答助手入口.png`、`文档/截图/问答助手页面.png`。

---

## 链 4：`.env` 自动加载（体验修复）

**我的 Prompt**

> 运行
> （连续两次启动都要手敲 `MYSQL_PASSWORD` / `LLM_API_KEY`，AI 主动提出把它做掉）

**AI 的建议**

> 给 `启动后端.py` 加 `_load_dotenv()`（纯 stdlib，不依赖 python-dotenv，不覆盖已有环境变量）。
> 此前每次启动都得手敲密码和 key，现在直接 `python 启动后端.py` 即可。

**验证**：在**不传任何环境变量**的情况下启动，`/api/llm/health` 返回
`"has_api_key":true`，MySQL 连接正常 —— 证明 `.env` 真的生效。

---

## 附：我引导 AI 的三条经验（供评审参考）

1. **先让它自证，再让它动手。** 每次结论都要求「带文件行号 / 带接口返回 / 带实测输出」，
   否则模型容易按印象给建议（本项目它就一度凭旧文档误判了赛事命题方向）。
2. **Bug 不要直接告诉它答案。** 只贴现象与报错，让它自己二分排查
   （链 1.3 的 `git init`、链 3.4 的 page target 都是它自己定位的）。
3. **硬约束要写进代码，不要只写在 Prompt 里。**
   「图表不许编数」这条如果只靠提示词，模型迟早会破例；改成 `render_chart` 参数里**没有数据字段**、
   且校验 `data_from` 必须本轮调用过，就从机制上堵死了。

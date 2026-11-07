# -*- coding: utf-8 -*-
"""行业口径硬规则库（电商经营决策）

为什么单独一个文件
------------------
"懂行"的本质不是词汇量，而是**口径**。同一个词在行业里有唯一定义，
通用大模型按常识答就会错，而且错得很自信。例如：

    问：我们 GMV 1,359 万，营收就是 1,359 万吧？
    通用模型：是的，GMV 就是营收。                    ← 错
    本层    ：GMV 是商品交易总额，不含运费；用户实付 1,601 万，
              两者都不是营收（未扣成本）。            ← 对

所以这里把 30 条规则做成结构化的「错误说法 / 正确说法 / 数据来源」，
分两种使用方式：

    1. always=True 的规则 → 直接写进 system prompt，不依赖检索命中率；
    2. 其余规则           → 由 llm.knowledge.retriever 按问题检索后注入。

这样即使检索失败，最关键的十来条口径也不会丢——这是对 RAG 不确定性
的兜底设计。
"""
from __future__ import annotations

from typing import Iterable

# 每条规则：
#   id        唯一编号
#   topic     主题
#   keywords  命中关键词（中文按子串匹配，英文小写）
#   wrong     通用模型/业务方的典型错误说法（用于教学与评测）
#   correct   正确口径
#   evidence  可复核的数字
#   source    出处文件
#   always    是否无条件注入 system prompt
RULES: list[dict] = [
    # ---------------- 金额与规模口径 ----------------
    dict(id="GMV-01", topic="GMV 口径", always=True,
         keywords=["gmv", "营收", "成交额", "交易额", "营业额", "销售额", "收入", "流水"],
         wrong="GMV 就是营收/营业额。",
         correct="GMV（商品交易总额）= Σ 商品单价，不含运费、不扣成本，"
                 "既不等于收入，也不等于用户实付。本项目全量口径 R$ 13,591,643.70"
                 "（99,441 单），算法口径 R$ 13,494,400.74（仅有效订单 112,101 行）。"
                 "用户实付为 R$ 16,008,872.12（含运费 2,251,909.54）。",
         evidence="全量口径 13,591,643.70 BRL（99,441 单）；"
                  "算法口径 13,494,400.74 BRL（剔除取消/缺货 549 行后 112,101 行）。",
         source="文档/数据集说明.md、算法2/algo2_summary_stats.csv"),
    dict(id="GMV-02", topic="GMV 与支付额", always=True,
         keywords=["运费", "实付", "支付", "payment", "客单价", "对不上"],
         wrong="GMV 和支付金额应该一样。",
         correct="支付额 = GMV + 运费 + 分期手续费等，恒大于 GMV。"
                 "本项目 运费 2,251,909.54，商品+运费 15,843,553.24，"
                 "实际支付 16,008,872.12。差额不能说成「损耗」。",
         evidence="运费 2,251,909.54 BRL；支付总额 16,008,872.12 BRL。",
         source="cleaned/fact_sales.csv、cleaned/fact_order_master.csv"),
    dict(id="GMV-03", topic="客单价", always=True,
         keywords=["客单价", "人均", "每单", "142.44", "136.68", "160.99"],
         wrong="客单价 142.44。",
         correct="142.44 是**人均消费**（RFM monetary 均值，95,420 人），不是客单价。"
                 "客单价（每单）= GMV / 订单数 = 136.68；每单实付 = 160.99。三个数不能混用。",
         evidence="客单价 136.68；人均消费 142.44（中位 89.90）；每单实付 160.99。",
         source="文档/数据集说明.md；algo2_summary_stats.csv 中该行标签写岔了"),
    dict(id="GMV-04", topic="货币单位", always=True,
         keywords=["币", "人民币", "美元", "雷亚尔", "brl", "单位"],
         wrong="金额单位是元。",
         correct="数据为巴西 Olist，货币单位是巴西雷亚尔（BRL / R$），"
                 "不是人民币也不是美元，跨币种比较需先换算。",
         evidence="数据集来源 Kaggle Olist Brazilian E-Commerce。",
         source="文档/数据集说明.md"),

    # ---------------- 用户与订单口径 ----------------
    dict(id="USER-01", topic="用户粒度", always=True,
         keywords=["用户", "客户", "客户数", "唯一", "user", "customer", "重复"],
         wrong="客户数用 customer_id 去重。",
         correct="真实用户粒度必须用 customer_unique_id（95,420 人）。"
                 "customer_id 是「每单一个」的订单级 ID（99,441 个），"
                 "用它去重会把同一个人的多次购买算成多个客户。",
         evidence="customer_unique_id 95,420；customer_id 99,441。",
         source="cleaned/fact_rfm.csv、fact_order_master.csv"),
    dict(id="USER-02", topic="复购率", always=True,
         keywords=["复购", "回购", "留存", "回头", "3.1"],
         wrong="复购率低，说明用户流失严重，要加大召回。",
         correct="复购率 3.1% 是**数据本身的性质**，不是运营失败：Olist 是"
                 "「一人一单」型公开数据集，95,420 人里仅约 3% 有第二单。"
                 "解读时必须先说明这一点，否则会得出错误的召回结论。",
         evidence="复购用户占比 3.1%。",
         source="文档/项目文档.md、app/dashboard.py"),
    dict(id="USER-03", topic="转化率", always=True,
         keywords=["转化", "漏斗", "转化率", "下单率", "99.8"],
         wrong="转化率 99.8%，说明下单几乎不会流失。",
         correct="本项目的「转化率」是**下单→已批准**（order_approved_at 非空），"
                 "不是「浏览→下单」。Olist 不含浏览/加购行为数据，"
                 "因此不能称其为行为漏斗，也不能与行业 UV 转化率对标。",
         evidence="下单 99,441 → 已批准占比 99.8%。",
         source="README.md「结果口径」、app/analysis.py"),
    dict(id="USER-04", topic="漏斗口径", always=True,
         keywords=["漏斗", "99,441", "95,815", "流失"],
         wrong="漏斗展示的是用户行为路径。",
         correct="漏斗按**订单状态与时间戳**构建：99,441 下单 → 99,281 批准 → "
                 "97,644 发货 → 96,461 送达 → 95,815 评价，"
                 "本质是履约漏斗，不是行为漏斗。",
         evidence="99,441 / 99,281 / 97,644 / 96,461 / 95,815。",
         source="app/analysis.py::conversion_funnel"),

    # ---------------- 数据质量 ----------------
    dict(id="DATA-01", topic="评价空值", always=True,
         keywords=["评分", "评价", "review", "空值", "null", "4.086", "填0"],
         wrong="没有评价就填 0 分，方便统计。",
         correct="未评价订单的 review_score 必须保持 NULL，不能填 0——"
                 "0 不是合法星级，填 0 会把平均分从 4.086 拉到 4.055 "
                 "并污染整个评分分布。",
         evidence="平均评分 4.086；评分分布 5 档。",
         source="文档/数据集说明.md、文档/验收记录.md"),
    dict(id="DATA-02", topic="有效订单", always=True,
         keywords=["取消", "剔除", "有效", "112,101", "112,650", "无效"],
         wrong="所有订单都算销量。",
         correct="销量/预测只使用有效状态：delivered/shipped/invoiced/"
                 "processing/approved/created；排除 canceled（取消）与 unavailable（缺货）。"
                 "因此 112,650 行明细里有效为 112,101 行。",
         evidence="有效行 112,101 / 全量 112,650。",
         source="pipeline/algo2_model.py::load_data"),
    dict(id="DATA-03", topic="商品数口径",
         keywords=["商品数", "32,951", "32,729", "sku", "多少个商品"],
         wrong="商品数就是 32,951。",
         correct="两个口径：dim_product 维度表 32,951 个 SKU；"
                 "fact_sales 中实际有成交的商品 32,729 个。"
                 "讲「在售商品」用前者，讲「有销量的商品」用后者。",
         evidence="32,951（维度表）/ 32,729（有成交）。",
         source="文档/项目文档.md、algo2_summary_stats.csv"),
    dict(id="DATA-04", topic="不完整周", always=True,
         keywords=["最后一周", "不完整", "2018-w36", "末段", "缺失"],
         wrong="最后一周销量暴跌，说明需求下滑。",
         correct="2018-W36 是**不完整周**（数据截至 2018-09-03），"
                 "销量天然偏低，建模时必须按「覆盖天数 < 7」剔除，"
                 "否则会污染评估。预测的 MAPE 异常偏高主要就是它造成的。",
         evidence="数据范围 2016-09-04 ~ 2018-09-03；2018-W36 不完整。",
         source="文档/算法2_算法文档.md 三、特征工程"),
    dict(id="USER-05", topic="用户数两个口径", always=False,
         keywords=["96,096", "96096", "95,420", "95420", "用户数", "多少人"],
         wrong="用户数 96,096，和 RFM 的 95,420 对不上就是错。",
         correct="两个口径都合法：看板 dashboard_summary 的 96,096 是"
                 "「订单表里出现过的客户数」（含取消/缺货订单）；"
                 "RFM 与 fact_sales 的 95,420 是「有效订单客户数」。"
                 "讲用户规模用前者，讲 RFM 分群/复购用后者，并说明差异来自 549 行无效订单。",
         evidence="96,096（fact_order_master 去重）/ 95,420（fact_sales、fact_rfm）。",
         source="app/dashboard.py、cleaned/fact_rfm.csv"),
    dict(id="DATA-06", topic="1,234 单 vs 549 行", always=False,
         keywords=["1234", "1,234", "549", "剔除", "取消单", "对不上"],
         wrong="取消了 1,234 单，却只剔除 549 行，数据算错了。",
         correct="两个数都对，单位不同：取消+缺货共 1,234 单，其中 775 单完全没有商品明细；"
                 "真正带明细的 459 单共 549 行，从事实表剔除的就是这 549 行"
                 "（112,650 − 549 = 112,101）。订单数看 1,234，明细行看 549，用户数看 96,096/95,420。",
         evidence="fact_order_master 取消625+缺货609=1,234 单；其中 775 单无明细；"
                  "fact_order_item 对应 549 行。",
         source="文档/口径手册.md §3.2"),
    dict(id="DATA-05", topic="时间范围",
         keywords=["时间范围", "多久", "哪年到哪年", "2016", "2018"],
         wrong="数据覆盖到现在。",
         correct="数据范围 2016-09-04 至 2018-09-03，任何「现在/今年」的"
                 "经营结论都必须限定在这个区间内，不能外推为当前市场状况。",
         evidence="2016-09-04 ~ 2018-09-03。",
         source="algo2_summary_stats.csv"),

    # ---------------- 预测 ----------------
    dict(id="FC-01", topic="预测粒度", always=True,
         keywords=["预测", "能卖多少", "明天", "下周", "以后", "备货", "补货"],
         wrong="可以预测任意商品明天卖多少件。",
         correct="预测粒度固定为**品类 × 周**，最多向后 8 周。"
                 "不支持日粒度、单商品粒度、卖家粒度——数据在这些粒度上过于稀疏，"
                 "给不出可信区间时应明确拒绝，而不是硬编一个数。",
         evidence="74 品类 × 8 周 = 592 行预测。",
         source="算法2/algo2_forecast_result.csv"),
    dict(id="FC-02", topic="预测精度", always=True,
         keywords=["mape", "准不准", "误差", "精度", "135", "90.46", "wape"],
         wrong="MAPE 135%，模型很差 / 模型能精确预测。",
         correct="MAPE 均值 135.73% 被低基数周放大，不代表模型差；"
                 "稳健口径看中位数 90.46%（基线 99.69%）与 WAPE 72.59%（基线 68.47%）。"
                 "结论是「部分品类优于基线」，用于趋势参考而非精确备货。",
         evidence="均值 135.73 vs 136.89；中位 90.46 vs 99.69；WAPE 72.59 vs 68.47。",
         source="文档/算法2_算法文档.md 五、结果"),
    dict(id="FC-03", topic="与基线比较", always=True,
         keywords=["优于基线", "打败", "比较", "33", "44.6", "提升"],
         wrong="我们的模型显著优于移动平均基线。",
         correct="只能说「部分品类优于基线」：74 个品类中 33 个（44.6%）MAPE 更优，"
                 "逐品类平均提升为 **-1.03%**（负数），WAPE 还略输基线。"
                 "周粒度稀疏数据下，移动平均本身就是很强的基线。",
         evidence="33/74；平均提升 -1.03%；WAPE 改善均值 -5.29%。",
         source="algo2_summary_stats.csv「平均提升(MAPE)」"),
    dict(id="FC-04", topic="模型链实际状态",
         keywords=["holt", "winters", "arima", "lstm", "什么模型", "模型链", "阻尼"],
         wrong="用了 Holt-Winters 和深度学习。",
         correct="模型链是 三级降级：Holt-Winters（需 ≥104 周）→ 阻尼 Holt（φ=0.95）→ "
                 "阻尼线性。实际 74 个品类**全部落在阻尼 Holt**，因为历史中位数仅 84.5 周、"
                 "最长 105 周（仅 1 个品类达标且训练集不足 104 周）。",
         evidence="历史周数 17~105，中位 84.5；model 列 74/74 为「Holt阻尼趋势」。",
         source="algo2_forecast_result.csv、pipeline/algo2_model.py"),
    dict(id="FC-05", topic="预测区间",
         keywords=["区间", "置信", "上下限", "95%", "波动范围"],
         wrong="95% 区间保证真实值一定落在里面。",
         correct="区间 = 预测 ± 1.96σ，σ 由最近 6 周 holdout 残差标准差估计。"
                 "holdout 仅 6 周，σ 估计不稳定，区间可能偏窄，"
                 "应作为「波动幅度参考」而非严格置信区间。",
         evidence="HOLDOUT_WEEKS=6；sigma=std(残差, ddof=1)。",
         source="pipeline/algo2_model.py::run_forecast"),

    # ---------------- 选品 ----------------
    dict(id="SEL-01", topic="选品粒度与数量", always=True,
         keywords=["选品", "推荐", "top", "榜单", "50 个", "多少个商品"],
         wrong="选品给出了 50 个推荐商品。",
         correct="50 个要分开说：增长榜 30 个（近期增长打分）+ 高销量分析池 20 个"
                 "（按累计 GMV，专门用于定价估计）。两榜用途不同，不能合并宣传为"
                 "「50 个推荐」。",
         evidence="增长榜 30 + 分析池 20 = 50；强推 30、推荐 6、备选 14。",
         source="算法2/algo2_selection_result.csv"),
    dict(id="SEL-02", topic="选品打分公式", always=True,
         keywords=["得分", "权重", "0.45", "0.40", "0.15", "怎么打分", "综合分"],
         wrong="综合分 = 规模×0.5 + 增长×0.5。",
         correct="商品级综合分 = 0.45×规模分 + 0.40×增长分 + 0.15×价格分，"
                 "三个分项都是百分位排名（0~100）而非原始值，以消除量纲差异。"
                 "（页面上的 0.5/0.5 是**品类级**的另一套口径，不要混用。）",
         evidence="score_total = 0.45*score_scale + 0.40*score_growth + 0.15*score_price。",
         source="pipeline/algo2_model.py::run_selection"),
    dict(id="SEL-03", topic="选品命中率", always=True,
         keywords=["命中率", "70%", "100%", "80%", "回测", "选品效果", "纯规模", "纯增长"],
         wrong="选品命中率 80%，效果很好。",
         correct="存在两套不同口径，必须分开讲："
                 "① 商品级（算法2 交付物，2018-05 切分）：综合得分 70%、纯规模 100%、"
                 "随机 19.72%、商品级 Top10 60%；"
                 "② 品类级（页面策略对照，最后 90 天）：热门 GMV 80%、纯增长 0%。"
                 "两者都指向同一结论：增长因子不能单独用。",
         evidence="algo2_selection_hitrate.csv：70/100/19.72/60。",
         source="算法2/algo2_selection_hitrate.csv、app/analysis.py::strategy_compare"),
    dict(id="SEL-04", topic="选品改进方向",
         keywords=["改进", "增长分", "权重过高", "0.20", "乘法"],
         wrong="选品模型已经最优。",
         correct="回测显示纯规模（100%）优于综合得分（70%），说明增长因子引入噪声。"
                 "改进方向：增长分权重 0.40 → 0.20，或改用「规模 × 增长」乘法形式。",
         evidence="纯规模命中 10/10，综合得分 7/10。",
         source="文档/算法2_算法文档.md 5.3"),

    # ---------------- 定价 ----------------
    dict(id="PRC-01", topic="定价覆盖率", always=True,
         keywords=["定价", "建议价", "多少个能", "31", "19", "覆盖"],
         wrong="算法给出了 50 个商品的定价建议。",
         correct="50 个参与定价的商品里，31 个给出了建议价，19 个明确标注"
                 "「数据不足，不给建议价」。31 个中**高置信只有 7 个**（商品级弹性），"
                 "24 个是品类级回退（中置信）。",
         evidence="可给建议价 31；样本不足 19；商品级弹性 7/50。",
         source="算法2/algo2_pricing_result.csv、pricing_skipped.csv"),
    dict(id="PRC-02", topic="定价门槛", always=True,
         keywords=["门槛", "条件", "为什么不给", "样本不足", "r²", "观测"],
         wrong="只要商品有销量就能估弹性。",
         correct="四道门槛缺一不可：月度观测 ≥10 个月、价格变异系数 ≥2%、"
                 "回归 R² ≥0.15、弹性必须为负。不满足就不给建议价（存 NULL，不写 0），"
                 "宁可承认不知道。",
         evidence="MIN_MONTHS=10；MIN_PRICE_SD=0.02；ELAS_R2_MIN=0.15。",
         source="pipeline/algo2_model.py::run_pricing"),
    dict(id="PRC-03", topic="调价幅度", always=True,
         keywords=["调价", "涨多少", "降多少", "15%", "范围", "算不准", "50%"],
         wrong="可以把价格提高 50% 来提升收入。",
         correct="建议价被强制夹在现价的 ±15% 内，这是业务约束不是模型能力上限；"
                 "超出范围的诉求应拒绝并说明原因。当前 50 个商品中 30 个建议降价、1 个建议提价。",
         evidence="PRICE_BOUND=0.15；降价 30、提价 1。",
         source="pipeline/algo2_model.py::run_pricing"),
    dict(id="PRC-04", topic="收入变化预期",
         keywords=["收入变化", "26.6", "增收", "提升多少"],
         wrong="调价后收入一定提升 26.6%。",
         correct="+26.60% 是按弹性公式外推的**模型测算值**，不是实验结果；"
                 "上线前必须做小流量 A/B 验证，并把毛利、库存、竞品价格纳入。",
         evidence="平均预期收入变化 26.60%。",
         source="algo2_summary_stats.csv「平均预期收入变化」"),
    dict(id="PRC-05", topic="弹性解读", always=True,
         keywords=["弹性", "价格弹性", "b<", "富有弹性", "缺乏弹性", "因果"],
         wrong="弹性是因果关系，降价一定多卖。",
         correct="log-log 回归 log(qty)=a+b·log(price) 得到的是**相关关系**；"
                 "b<-1 富有弹性（降价增收方向）、-1<b<0 缺乏弹性（提价增收方向），"
                 "弹性会被截断在 [-3, -0.1]。价格与促销内生，不能直接当因果结论。",
         evidence="弹性截断区间 [-3, -0.1]；31 个中 24 个为品类级回退。",
         source="文档/算法2_算法文档.md 2.3"),
    dict(id="PRC-06", topic="价格口径",
         keywords=["均价", "加权", "价格怎么算", "p_wavg"],
         wrong="商品价格 = 历史价格简单平均。",
         correct="价格用**月度量价加权均价** p_wavg = ΣGMV / Σ件数，"
                 "消除单笔异常高价的影响；简单均值会被极端订单带偏。",
         evidence="p_wavg = gmv / qty。",
         source="pipeline/algo2_model.py::_monthly_profile"),

    # ---------------- 系统与合规 ----------------
    dict(id="SYS-01", topic="数据库结构", always=True,
         keywords=["数据库", "表", "视图", "几张", "olist_db", "算法库"],
         wrong="所有数据在一张表里。",
         correct="分库设计：主业务库 olist_db 有 13 张表 + 10 个视图；"
                 "算法结果库 olist_algo_db 有 9 张表。两者同实例不同库，"
                 "跨库查询要写全限定名（olist_algo_db.algo2_forecast_result）。",
         evidence="主库 13 表 + 10 视图；算法库 9 表。",
         source="文档/数据库设计文档.md"),
    dict(id="SYS-02", topic="数据合规", always=True,
         keywords=["合规", "隐私", "个人信息", "数据来源", "版权"],
         wrong="数据是从别处爬来的。",
         correct="数据为 Kaggle 公开数据集 Olist Brazilian E-Commerce，"
                 "仅用于课程/比赛实践；不做个人身份识别，不再分发原始数据。"
                 "所有分析结果不含可识别个人信息。",
         evidence="9 张原始表 → 13 张清洗表。",
         source="README.md、文档/数据集说明.md"),
    dict(id="SYS-03", topic="能力边界",
         keywords=["能不能", "支持吗", "可以做什么", "局限", "做不到"],
         wrong="什么都能分析。",
         correct="能力边界：不含浏览/加购/曝光行为数据，不含库存、毛利、退货、"
                 "竞品价格；因此不能做 UV 转化率、库存周转、利润优化、"
                 "竞品比价。这些必须明确回答「数据不支持」。",
         evidence="原始 9 张表无浏览/加购/库存/成本字段。",
         source="文档/项目文档.md 局限、README.md"),
]

# 索引
_BY_ID = {r["id"]: r for r in RULES}
_ALWAYS = [r for r in RULES if r.get("always")]


def all_rules() -> list[dict]:
    return RULES


def get(rule_id: str) -> dict | None:
    return _BY_ID.get(rule_id)


def always_rules() -> list[dict]:
    """无条件注入 system prompt 的核心规则。"""
    return _ALWAYS


def match(text: str, top_k: int = 4) -> list[dict]:
    """按关键词命中程度给规则排序，返回最相关的若干条。

    简单但对本场景足够：问题里出现「gmv」「营收」就直接命中 GMV 规则，
    比向量检索更可控、可解释——答辩时能指着说「因为问了 GMV，所以命中 GMV-01」。
    """
    if not text:
        return []
    low = text.lower()
    scored: list[tuple[float, dict]] = []
    for r in RULES:
        hits = sum(1 for kw in r["keywords"] if kw.lower() in low)
        if hits:
            # 命中越多越相关；always 规则轻微加权
            scored.append((hits + (0.5 if r.get("always") else 0.0), r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:top_k]]


def missing_rules(topics: Iterable[str]) -> list[dict]:
    """预留：按主题补规则。"""
    ts = {t.strip() for t in topics}
    return [r for r in RULES if r["topic"] in ts]


def as_prompt_block(rules: list[dict]) -> str:
    """把规则渲染成可注入 prompt 的文本。"""
    lines = []
    for r in rules:
        lines.append(f"【{r['id']}·{r['topic']}】{r['correct']}")
        if r.get("evidence"):
            lines.append(f"    数据依据：{r['evidence']}")
    return "\n".join(lines)


def as_dict_list(rules: list[dict]) -> list[dict]:
    """给 API 返回用的精简结构。"""
    return [{"id": r["id"], "topic": r["topic"], "correct": r["correct"],
             "evidence": r.get("evidence", ""), "source": r.get("source", "")}
            for r in rules]
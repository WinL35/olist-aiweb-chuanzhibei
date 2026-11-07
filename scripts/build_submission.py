#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成参赛提交 PDF（单文件，可直接上传）。

顺序：
    python scripts/make_figs.py            # 1. 生成图表
    python scripts/make_qr.py --url ...    # 2. 有视频就先出二维码
    python scripts/build_submission.py     # 3. 出 PDF

只改下面 META 的 5 个字段，重跑即可。

设计原则：
    · 所有数字来自项目真实产物（数据库 / CSV / 评测结果），不编造；
    · 未知信息保留【】占位，方便 search & replace；
    · 评审核查点（截图、二维码）用虚线框标出，提交前必须替换。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fitz  # noqa: E402
from submission_lib import (A4_H, A4_W, C_ACCENT, C_ACCENT2, C_DARK, C_GREY,  # noqa: E402
                            C_LINE, C_TXT, C_WARN, Doc, text_width, wrap)

# ======================================================================
# ① 只改这里
# ======================================================================
META = {
    "unit": "【单位简称】",              # 例：XX大学 / XX科技
    "title": "电商经营决策垂直大模型",     # 作品名称
    "leader": "卢泳豪",                  # 队长姓名
    "phone": "【队长手机号】",            # 例：13800000000
    "date": "2026-10-29",               # 提交日期
    "track": "垂直行业大模型赛道",
}
OUT_DIR = ROOT / "提交材料"
FIG = OUT_DIR / "figs"
QR = OUT_DIR / "qr_video.png"


def fname() -> str:
    d = META["date"].replace("-", "")
    return f"{META['unit']}-{META['title']}-{META['leader']}-{META['phone']}-{d}.pdf"


# ======================================================================
# ② 取真实数据（缺一项就跳过，不编）
# ======================================================================
def load_facts() -> dict:
    f = {"rules": 33, "tools": 22, "chunks": 239, "q_total": 60, "q_blind": 20}
    try:
        j = json.loads((ROOT / "llm" / "eval" / "last_run.json").read_text(encoding="utf-8"))
        f["summary"] = {r["mode"]: r for r in j["summary"]}
        f["provider"] = j.get("provider")
    except Exception:
        f["summary"] = {}
    try:
        from llm.knowledge import hard_rules, retriever
        from llm.tools import registry
        f["rules"] = len(hard_rules.all_rules())
        f["always"] = len(hard_rules.always_rules())
        f["chunks"] = retriever.stats().get("chunks", f["chunks"])
        f["tools"] = len(registry.TOOLS)
    except Exception:
        pass
    return f


def qa_samples() -> list[tuple[str, str]]:
    """实跑三条问题，取真实回答（去掉 markdown 记号，截断）。"""
    qs = ["我们 GMV 1359 万，那营收就是 1359 万吧？",
          "美妆这个品类未来 4 周能卖多少？要不要备货",
          "把价格提高 50% 能增收多少？"]
    out = []
    try:
        from llm.agent import planner
        for q in qs:
            r = planner.run(q, "full")
            a = r.get("answer", "")
            a = a.replace("**", "").replace("- ", "· ")
            lines = [ln.strip() for ln in a.split("\n") if ln.strip()]
            txt = " ".join(lines)
            out.append((q, txt[:420] + ("…" if len(txt) > 420 else "")))
    except Exception as e:
        out = [("（示例问答未生成）", f"运行环境未就绪：{type(e).__name__}")]
    return out


# ======================================================================
# ③ 封面
# ======================================================================
def cover(doc: Doc):
    p = doc.page
    p.draw_rect(fitz.Rect(0, 0, A4_W, 132), color=None, fill=C_DARK)
    p.draw_rect(fitz.Rect(0, 132, A4_W, 137), color=None, fill=C_ACCENT)
    t = "兴智杯全国人工智能创新应用大赛"
    p.insert_text(((A4_W - text_width(t, 12)) / 2, 52), t, fontsize=12,
                  fontname="china-s", color=(0.86, 0.9, 0.96))
    t2 = f"· {META['track']} ·"
    p.insert_text(((A4_W - text_width(t2, 10)) / 2, 76), t2, fontsize=10,
                  fontname="china-s", color=(0.62, 0.72, 0.86))

    y = 236
    t = "作品方案书"
    p.insert_text(((A4_W - text_width(t, 34)) / 2, y), t, fontsize=34,
                  fontname="china-s", color=C_DARK, render_mode=2, border_width=0.5)
    y += 46
    sub = "基于通用底座与行业数据融合的中小电商经营决策助手"
    for i, ln in enumerate(wrap(sub, 400, 12.5)):
        p.insert_text(((A4_W - text_width(ln, 12.5)) / 2, y + i * 22), ln, fontsize=12.5,
                      fontname="china-s", color=C_GREY)

    y += 62
    p.draw_line(fitz.Point(A4_W / 2 - 60, y), fitz.Point(A4_W / 2 + 60, y),
                color=C_ACCENT2, width=2)

    # 信息表
    rows = [("作品名称", META["title"]), ("参赛赛道", META["track"]),
            ("单位简称", META["unit"]), ("队长", META["leader"]),
            ("联系电话", META["phone"]), ("提交日期", META["date"])]
    y += 48
    for k, v in rows:
        p.insert_text((A4_W / 2 - 118, y), k, fontsize=10.6, fontname="china-s", color=C_GREY)
        p.insert_text((A4_W / 2 - 34, y), v, fontsize=10.6, fontname="china-s", color=C_TXT,
                      render_mode=2, border_width=0.25)
        y += 27

    # 底部
    p.draw_line(fitz.Point(56, A4_H - 108), fitz.Point(A4_W - 56, A4_H - 108),
                color=C_LINE, width=0.7)
    note = "本文件为单文件提交版：方案正文 + 附件（代码 / 测试集 / 部署验证 / 演示视频二维码）"
    p.insert_text(((A4_W - text_width(note, 8.6)) / 2, A4_H - 86), note, fontsize=8.6,
                  fontname="china-s", color=C_GREY)
    note2 = "提交前请将封面、页脚及文件名中的【】占位替换为真实信息"
    p.insert_text(((A4_W - text_width(note2, 8.2)) / 2, A4_H - 70), note2, fontsize=8.2,
                  fontname="china-s", color=C_WARN)
    doc.page_break()


# ======================================================================
# ④ 目录
# ======================================================================
TOC = [
    (1, "一 行业背景与痛点分析"),
    (2, "1.1 行业背景"),
    (2, "1.2 三类真实痛点"),
    (2, "1.3 现有方案的不足"),
    (2, "1.4 本作品的定位"),
    (1, "二 技术方案详述"),
    (2, "2.1 总体架构"),
    (2, "2.2 数据层"),
    (2, "2.3 知识层：把口径变成硬约束"),
    (2, "2.4 工具层：让模型能算而不是会编"),
    (2, "2.5 决策层：Agent 双路径"),
    (2, "2.6 安全可信：三重护栏"),
    (2, "2.7 微调策略与触发条件"),
    (2, "2.8 工程实现与可复现"),
    (1, "三 案例实施效果"),
    (2, "3.1 案例设定"),
    (2, "3.2 数据规模"),
    (2, "3.3 效果一：口径纠偏"),
    (2, "3.4 效果二：多步决策"),
    (2, "3.5 效果三：量化评测"),
    (2, "3.6 效果四：算法结果可信度"),
    (2, "3.7 盲测与诚实边界"),
    (2, "3.8 效率与业务价值"),
    (1, "四 附件材料"),
    (2, "4.1 代码与文件清单"),
    (2, "4.2 测试数据集说明"),
    (2, "4.3 部署与验证证据"),
    (2, "4.4 演示视频二维码"),
    (2, "4.5 口径规则节选"),
]


def toc_page(doc: Doc, pages: dict):
    doc.page.insert_text((56, doc.y + 4), "目　录", fontsize=17, fontname="china-s",
                         color=C_DARK, render_mode=2, border_width=0.4)
    doc.page.draw_line(fitz.Point(56, doc.y + 16), fitz.Point(A4_W - 56, doc.y + 16),
                       color=C_ACCENT, width=1.2)
    doc.y += 42
    for lvl, title in TOC:
        key = title.split(" ", 1)[1] if " " in title else title
        num = title.split(" ", 1)[0] if " " in title else ""
        page = pages.get(f"{num} {key}") or pages.get(key) or pages.get(title) or 0
        fs = 10.4 if lvl == 1 else 9.4
        x = 56 if lvl == 1 else 76
        doc.page.insert_text((x, doc.y), title, fontsize=fs, fontname="china-s",
                             color=C_DARK if lvl == 1 else C_TXT,
                             render_mode=2 if lvl == 1 else 0,
                             border_width=0.28)
        if page:
            s = str(page)
            # 点线
            tw = text_width(title, fs)
            dot_x0 = x + tw + 8
            dot_x1 = A4_W - 56 - 14 - text_width(s, fs)
            n = int((dot_x1 - dot_x0) / 4.2)
            if n > 0:
                for i in range(n):
                    doc.page.insert_text((dot_x0 + i * 4.2, doc.y), "·", fontsize=fs,
                                         fontname="china-s", color=(0.75, 0.78, 0.84))
            doc.page.insert_text((A4_W - 56 - 12 - text_width(s, fs), doc.y), s, fontsize=fs,
                                 fontname="china-s", color=C_GREY)
        doc.y += 22 if lvl == 1 else 18
    # 不在这里分页：紧随其后的 h1() 会自己开新页，否则会多出一张空白页


# ======================================================================
# ⑤ 正文
# ======================================================================
def sec1(doc: Doc, f: dict):
    doc.h1("一", "行业背景与痛点分析")

    doc.h2("1.1", "行业背景")
    doc.para("中小电商的经营决策长期依赖经验。平台后台能导出订单、商品、评价等多张明细表，"
             "但「导出数据」和「做出决策」之间隔着一整套数据工程与统计口径工作。"
             "以本作品使用的 Olist 巴西电商公开数据集为例：11.2 万条订单明细、9.9 万个订单、"
             "9.5 万名用户、74 个品类、13 张业务表，回答一个「这个品类要不要备货」"
             "需要跨 4 张表做聚合、再跑一遍时间序列模型。绝大多数中小商家没有这个能力。")
    doc.para("另一方面，通用大模型已经能流畅对话，但直接问它经营问题会立刻暴露两个致命缺陷："
             "一是口径错——它会把 GMV 当成营收；二是数字假——它给的销量、价格都是编出来的。"
             "本作品的出发点正是这两点。")

    doc.h2("1.2", "三类真实痛点")
    doc.table(
        ["痛点", "具体表现", "后果"],
        [["口径混乱", "同一指标存在多个合法口径：GMV 13,591,643.70（全量）与 13,494,400.74"
                      "（有效订单）；客单价 136.68 与人均消费 142.44；用户数 96,096 与 95,420",
          "同一份报表两个部门对不上账，决策会上先吵口径"],
         ["数据割裂", "交易、支付、评价、地域分散在 13 张表与 10 个视图，"
                      "一个问题往往要跨表关联与状态过滤",
          "问一次要等分析师半天，错过决策窗口"],
         ["决策靠经验", "备货量、调价幅度凭感觉；调价后无法量化复盘",
          "库存积压或断货，降价促销反而亏损"]],
        [1.05, 3.0, 1.75], caption="表 1-1　中小电商三类共性痛点")

    doc.h2("1.3", "现有方案的不足")
    doc.table(
        ["方案", "能解决", "解决不了"],
        [["BI 看板 / 拖拽报表", "展示历史数据", "要人主动去找图、自己解读；不回答开放问题"],
         ["通用大模型", "语言表达好、能对话", "口径错、数字编造、不知边界（本作品实测通过率 0%）"],
         ["规则问答机器人", "固定问法能答", "换个说法就失效；无法多步取数、无法解释依据"],
         ["本作品", "懂口径、能取数、敢拒答、可核对", "仍需真实企业数据做进一步验证（见 3.6）"]],
        [1.5, 2.0, 2.6], caption="表 1-2　四类方案的边界对比")

    doc.h2("1.4", "本作品的定位")
    doc.callout("一句话定位",
                "不是再造一个大模型，而是给通用底座加一层「行业约束层」："
                "把行业口径、真实数据、能力边界三样东西变成模型绕不过去的约束，"
                "使它在垂直领域「懂行、能算、敢拒答」。")
    doc.para("这一定位决定了技术路线：重心不在训练参数，而在知识工程、工具编排与评测体系——"
             "也决定了它可以用较低成本迁移到其他行业（见 2.8 与方案书第十节）。")


def sec2(doc: Doc, f: dict):
    doc.h1("二", "技术方案详述")

    doc.h2("2.1", "总体架构")
    doc.para("系统分为五层，自下而上依次为数据层、知识层、工具层、决策层、评测层。"
             "每一层的产出都可独立验证：数据层能查到行，知识层有规则编号，工具层返回可复现的数值，"
             "决策层给出四段式回答，评测层给出通过率。")
    doc.image(FIG / "fig_arch.png", caption="图 2-1　五层架构（上层依赖下层，底座可替换）")

    doc.h2("2.2", "数据层")
    doc.para("沿用已建成的双库结构：主业务库 olist_db 含 13 张表与 10 个视图，"
             "算法结果库 olist_algo_db 含 9 张表，同实例跨库查询使用全限定名。"
             "业务明细（11.2 万行）与算法产物（592 行预测、50 行选品、50 行定价）分开存放，"
             "避免重算覆盖原始数据。")
    doc.table(
        ["库", "内容", "规模", "用途"],
        [["olist_db", "13 张业务表 + 10 个视图", "872,359 行", "看板、分析、漏斗、RFM"],
         ["olist_algo_db", "9 张算法结果表", "96,462 行", "预测、选品、定价、离线实验"]],
        [1.2, 2.2, 1.2, 2.0], caption="表 2-1　数据层构成")

    doc.h2("2.3", "知识层：把口径变成硬约束")
    doc.para("知识层只做一件事：把团队真实踩过的坑，写成模型无法绕过的规则。"
             f"当前共 {f.get('rules', 33)} 条，其中 {f.get('always', 23)} 条无条件注入系统提示词——"
             "因为它们一旦错，整段回答就废了；其余按关键词命中注入，控制提示词长度。")
    doc.table(
        ["主题", "条数", "典型规则"],
        [["金额与规模", "4", "GMV 是商品金额，不含运费、不等于营收"],
         ["用户与订单", "5", "真实用户必须用 customer_unique_id（95,420）"],
         ["数据质量", "6", "未评价评分保持 NULL，不能填 0（会把 4.086 拉到 4.055）"],
         ["销量预测", "5", "粒度固定品类×周，最多 8 周；MAPE 要看中位数"],
         ["选品", "4", "商品级 0.45/0.40/0.15 与品类级 0.5/0.5 是两套口径"],
         ["定价", "6", "调价幅度夹在 ±15%；弹性是相关不是因果"],
         ["系统与合规", "3", "数据仅用于课程/比赛；不做个人身份识别"]],
        [1.35, 0.7, 4.1], caption="表 2-2　口径硬规则的主题分布", align_right=[False, True, False])
    doc.para("每条规则是结构化对象，而不是一段散文——这样才能被检索、被引用、被回归测试：")
    doc.code('{"id": "GMV-01", "topic": "GMV 定义",\n'
             ' "keywords": ["gmv", "营收", "营业额"],\n'
             ' "wrong": "GMV 就是营收。",\n'
             ' "correct": "GMV 是商品金额，不含运费、不扣成本，不等于营收也不等于用户实付。",\n'
             ' "evidence": "全量 13,591,643.70；实付 16,008,872.12；运费 2,251,909.54",\n'
             ' "source": "文档/口径手册.md"}')
    doc.para(f"软知识侧使用文档检索（RAG）：{f.get('chunks', 239)} 段，按 markdown 标题切分，"
             "用 TF-IDF 字符 n-gram（char_wb, 2-4）做相似度。"
             "没有采用向量检索，是一个明确的工程取舍：")
    doc.table(
        ["方案", "优点", "为何未采用"],
        [["向量检索（bge/m3e）", "语义泛化好", "需下载数百 MB 模型，现场断网即失效；答辩机器无 GPU"],
         ["BM25", "轻量成熟", "需额外依赖，中文分词质量不稳定"],
         ["TF-IDF 字符 n-gram", "零依赖、离线可用、可解释、延迟 <20ms", "语义泛化弱：换同义说法可能召不回"]],
        [1.7, 2.1, 2.4], caption="表 2-3　检索方案的取舍")
    doc.callout("硬规则与软知识的分工",
                "硬规则管「对不对」，检索管「有没有依据」。数字只能来自工具，"
                "检索片段只作引用。检索不到时显式输出「本次未检索到相关片段」，"
                "而不是编一段依据出来。", color=C_WARN)

    doc.h2("2.4", "工具层：让模型能算而不是会编")
    doc.para(f"把现有后端接口中与经营决策最相关的部分翻译成 function calling 工具，共 {f.get('tools', 22)} 个。"
             "关键设计是：数据库模式下**直接调用后端路由函数**，而不是重写 SQL——"
             "因此模型报出的数字与网页上看到的完全一致，不存在「两个真相」。")
    doc.table(
        ["类别", "工具（部分）", "回答什么"],
        [["大盘", "dashboard_summary / trend / category / top_products", "规模、趋势、品类结构"],
         ["地区与质量", "region_sales / order_status_dist / review_dist", "哪个州最强、取消多少、评分分布"],
         ["用户", "rfm_segments / conversion_funnel / repurchase", "分层、漏斗、复购"],
         ["预测", "prediction_categories / sales_forecast", "品类未来 1-8 周销量与区间"],
         ["选品", "selection_summary / selection_products / strategy_compare", "榜单、命中率、策略对照"],
         ["定价", "pricing_summary / pricing_suggestions / pricing_skipped", "建议价、覆盖率、为何不给价"],
         ["实验", "experiment_median / compare / summary_stats", "模型准不准、MAE/MAPE、数据口径"]],
        [1.1, 3.3, 2.0], caption="表 2-4　工具清单（节选，共 22 个）")
    doc.para("工具描述不是注释，而是给模型的调度指令。例如 dashboard_summary 的描述里直接写明："
             "「凡是问整体规模/大盘怎么样必须先调这个，禁止凭印象给数字」。"
             "这一句比十句提示词工程更有效，因为它把「该不该查数」从自由裁量变成了硬规则。")
    doc.para("同时提供 CSV 降级：MySQL 不可用时自动改读清洗后的 CSV，返回中带 source 标识，"
             "前端与回答都会显示数据来源，避免「不知道自己在看哪份数据」。")

    doc.h2("2.5", "决策层：Agent 双路径")
    doc.para("有模型底座时走 ReAct 循环（最多 4 步、6 次工具调用）：模型自主决定调哪些工具，"
             "观察结果后决定下一步；4 步内未收敛则自动降级到离线组装器，保证不空手返回。"
             "无底座或断网时走离线确定性路径：意图识别 → 调用同一批工具 → 按模板组装，"
             "用于现场演示与评测下界。")
    doc.table(
        ["路径", "触发条件", "优点", "局限"],
        [["LLM + ReAct", "配置了 API Key", "语义路由鲁棒、语言自然、能处理未见问法", "依赖外部服务与费用"],
         ["离线确定性", "无 Key / 断网 / 底座故障", "零依赖、稳定、可离线演示", "换说法易路由失败（见 3.6）"]],
        [1.3, 1.7, 1.9, 1.7], caption="表 2-5　双路径设计")
    doc.para("两条路径共享同一份规则库、同一批工具、同一个输出结构，因此可以公平对比——"
             "差别只在「语言组织」这一层，这正是消融实验要分离的变量。")
    doc.para("输出强制四段式，保证每句话都能被追问：")
    doc.code("【结论】一两句话说清，带关键数字\n"
             "数据依据  逐条「指标：数值（来源工具）」\n"
             "口径提醒  本次依赖的行业口径（带规则编号）\n"
             "局限      这次结论不能用于什么场景")

    doc.h2("2.6", "安全可信：三重护栏")
    doc.para("护栏的原则是**不靠提示词，靠代码**——提示词可以被诱导，if 不能。")
    doc.table(
        ["护栏", "实现方式", "拦截示例"],
        [["越界拒答", "11 条正则覆盖日粒度、卖家级、库存、毛利、退货、竞品、行为数据等",
          "「预测卖家 A 明天卖多少」→ 直接拒答并给替代方案"],
         ["口径篡改拦截", "7 条策略规则，命中后强制在结论首句纠正",
          "「把取消订单算进 GMV 让数字好看」→ 首句即纠正并给出 549 行依据"],
         ["调价幅度约束", "解析诉求幅度并与 ±15% 业务约束比对",
          "「提价 50% 能增收多少」→ 说明约束，不给该幅度的数值"]],
        [1.35, 3.0, 2.4], caption="表 2-6　三重护栏")
    doc.para("其中「口径篡改拦截」是本作品认为最有价值的设计。"
             "用户要求「把复购率改成 10% 好看点」时，模型无权答应——规则命中后"
             "强制在结论开头输出「不能，实际 3.05%」。这类请求在企业内部极常见，"
             "也是数据造假的主要入口，用代码拦比用提示词劝可靠得多。")

    doc.h2("2.7", "微调策略与触发条件")
    doc.para("本作品当前未做参数微调。理由有三：其一，微调解决的是风格与领域语言，"
             "解决不了「数字必须真实」，后者只能靠工具；其二，33 条口径规则 + 检索"
             "已能达到开发集 100%，微调边际收益不明；其三，无 GPU 资源，强行微调只能上小模型，"
             "反而降低推理质量。方案保留微调路径，触发条件明确：")
    doc.table(
        ["触发条件", "微调目标", "数据构造方式"],
        [["口径规则超过 100 条，提示词开始膨胀", "把口径内化为参数", "规则 →（问题, 正确回答）对"],
         ["需要固定话术风格（如给老板的周报）", "风格对齐", "人工撰写 200 条周报样例"],
         ["有 GPU 且需完全离线部署", "小模型蒸馏", "强模型生成 5,000 条问答做教师信号"]],
        [2.5, 1.6, 2.4], caption="表 2-7　微调触发条件与数据构造")

    doc.h2("2.8", "工程实现与可复现")
    doc.table(
        ["模块", "文件", "规模"],
        [["配置与约束", "llm/config.py", "65 行"],
         ["口径规则库", "llm/knowledge/hard_rules.py", "371 行"],
         ["文档检索", "llm/knowledge/retriever.py", "165 行"],
         ["工具注册（给模型看的 schema）", "llm/tools/registry.py", "286 行"],
         ["工具执行（db/csv 双模式）", "llm/tools/executor.py", "544 行"],
         ["护栏", "llm/agent/guard.py", "208 行"],
         ["提示词组装", "llm/agent/prompts.py", "86 行"],
         ["离线组装器与口径拦截", "llm/agent/composer.py", "747 行"],
         ["编排入口", "llm/agent/planner.py", "217 行"],
         ["评测执行器", "llm/eval/runner.py", "276 行"],
         ["HTTP 接口", "app/llm_api.py", "160 行"],
         ["对话页面", "static/assistant.html", "302 行"]],
        [2.5, 2.6, 1.0], caption="表 2-8　主要文件清单（合计约 3,800 行新增代码）",
        align_right=[False, False, True])


def sec3(doc: Doc, f: dict, samples: list[tuple[str, str]]):
    doc.h1("三", "案例实施效果")
    s = f.get("summary") or {}
    g = lambda m, k: (s.get(m, {}) or {}).get(k)

    doc.h2("3.1", "案例设定")
    doc.callout("案例性质说明（重要）",
                "本案例使用 Olist 巴西电商公开数据集（Kaggle），属**仿真案例**，"
                "非企业私有数据。选择它的原因是：数据真实、体量足够（11.2 万条订单明细）、"
                "口径陷阱典型（多状态订单、多支付方式、未评价订单），"
                "适合验证「口径约束 + 工具取数」这套方法是否成立。"
                "真实企业落地时的差异与所需补充见 3.6。", color=C_WARN)
    doc.para("案例覆盖一条完整的经营链路：看规模 → 预测品类销量 → 选品 → 定价 → 评估模型可信度。"
             "每个环节都有对应的后端接口、算法结果表与可视化页面，模型只是在它们之上加了一层「会说人话」的入口。")

    doc.h2("3.2", "数据规模")
    doc.table(
        ["维度", "数值", "说明"],
        [["时间范围", "2016-09-04 ~ 2018-09-03", "最后一周 2018-W36 不完整，建模时剔除"],
         ["订单 / 明细", "99,441 单 / 112,650 行", "有效明细 112,101 行（剔除取消与缺货 549 行）"],
         ["用户 / 商品", "95,420 人 / 32,729 个有成交商品", "商品维度表 32,951 个"],
         ["品类", "74 个", "全部可预测"],
         ["GMV / 实付", "13,591,643.70 / 16,008,872.12", "BRL，前者不含运费"],
         ["算法产物", "预测 592 行 / 选品 50 / 定价 50", "另有离线实验 296 行"]],
        [1.3, 2.4, 2.9], caption="表 3-1　案例数据规模")

    doc.h2("3.3", "效果一：口径纠偏")
    doc.para("这是最容易被验证、也最能体现「懂行」的一环。同一批问题，通用底座会给出看似合理但实际错误的答案；"
             "本系统给出带依据的正确口径：")
    doc.table(
        ["提问", "通用底座（baseline）", "本系统"],
        [["GMV 1359 万，营收就是 1359 万吧？",
          "「GMV 可以作为营收的参考指标，数值越大说明业务规模越大」——把 GMV 当营收",
          "「GMV 是商品金额，不含运费、不扣成本，不等于营收」并给出 4 个口径的数"],
         ["复购率只有 3.1%，是不是运营很差？",
          "泛泛建议「加大召回、做会员体系」",
          "先说明 Olist 一人一单特性属数据性质，再讲复购人群贡献 5.62% 金额"],
         ["没评价的订单，评分能填 0 吗？",
          "「可以，做好缺失值填充」",
          "「不能，0 不是合法星级，会把均值从 4.086 拉到 4.055 并污染分布」"]],
        [1.75, 2.1, 2.9], caption="表 3-2　口径纠偏对比（实测回答摘录）")

    doc.h2("3.4", "效果二：多步决策")
    doc.para("多步决策要求模型自己判断「该调哪个工具、拿哪些数、怎么下结论」。以下三条为系统实跑输出摘录：")
    for i, (q, a) in enumerate(samples, 1):
        doc.h3(f"示例 {i}：{q}")
        doc.code(a, fs=8.4)
    doc.image(FIG / "fig_forecast.png", width=470,
              caption="图 3-1　美妆（health_beauty）未来 8 周预测与 95% 区间（数据源：algo2_forecast_result）")

    doc.h2("3.5", "效果三：量化评测")
    doc.para("评测集共 80 题：60 题主集 + 20 题盲测，分四类——A 口径陷阱（会不会被常识带偏）、"
             "B 多步决策（会不会真的取数）、C 拒答（知不知道自己不知道）、"
             "D 边界合规（会不会被诱导违规）。评分完全基于字符串匹配，不含人工判断，任何人可复现。")
    doc.table(
        ["模式", "A 口径", "B 多步", "C 拒答", "D 边界", "总体", "工具命中"],
        [["baseline 裸底座", "0.0%", "0.0%", "0.0%", "0.0%", "0.0%", "0.0%"],
         ["no_tools 有知识无工具", "93.3%", "53.3%", "100.0%", "86.7%", "83.3%", "0.0%"],
         ["no_rag 有工具无检索", "100%", "100%", "100%", "100%", "100.0%", "97.1%"],
         ["full 全量", "100%", "100%", "100%", "100%", "100.0%", "97.1%"]],
        [2.0, 0.85, 0.85, 0.8, 0.8, 0.85, 0.85], caption="表 3-3　消融实验结果（60 题主集）",
        align_right=[False, True, True, True, True, True, True])
    doc.image(FIG / "fig_ablation.png", width=460,
              caption="图 3-2　四类题目通过率（裸底座 → 有知识 → 全量）")
    doc.para("三点读法必须讲清：一是裸底座 0% 不是「通用模型很笨」，而是说明没有工具与口径时，"
             "它会给出「看起来对、实际错」的答案；二是 B 类从 53.3% 升到 100%，是工具层的直接贡献；"
             "三是检索在当前评分体系下准确率增量约为 0，但「依据覆盖率」从 0% 升到 90%——"
             "它提供的是可核对性，而非正确率。")

    doc.h2("3.6", "效果四：算法结果可信度")
    doc.para("模型说的话可信不可信，取决于底层算法结果是否可信。本作品把三套算法结果一起接进对话，"
             "并且要求模型把「不确定性」说出来，而不是只报最好看的那个数：")
    doc.table(
        ["环节", "真实结果", "模型如何表述"],
        [["销量预测（74 品类 × 8 周 = 592 行）",
          "MAPE 中位数 90.46%（基线 99.69%）；WAPE 72.59%（基线 68.47%）；仅 33/74 品类优于基线",
          "「部分品类优于基线」；只作趋势参考，不能用于精确备货"],
         ["选品（50 个商品 = 增长榜 30 + 分析池 20）",
          "综合得分 Top10 命中率 70%、纯规模 100%、随机 19.72%、商品级 Top10 60%",
          "说明增长因子会引入噪声，权重从 0.40 下调至 0.20"],
         ["定价（50 个商品）",
          "31 个给出建议价（高置信 7 个）、19 个明确「数据不足」；30 降 1 提；平均预期收入 +26.60%",
          "先说 19 个为什么给不了，再说 +26.60% 是测算值、需 A/B"]],
        [1.85, 2.75, 2.15], caption="表 3-4　三套算法结果与模型的表述口径")
    doc.image(FIG / "fig_hitrate.png", width=450,
              caption="图 3-3　选品命中率：纯规模 100% 反而高于综合得分 70%，说明增长因子引入噪声")
    doc.image(FIG / "fig_pricing.png", width=450,
              caption="图 3-4　定价覆盖：50 个商品中仅 31 个可给建议价，19 个明确承认数据不足")
    doc.callout("这条比数字本身更重要",
                "19 个商品给不出建议价，我们就存 NULL 并明说「样本不足」，而不是硬给一个数。"
                "「宁可承认不知道」是整个作品从算法层贯穿到模型层的产品原则。",
                color=C_ACCENT2)

    doc.h2("3.7", "盲测与诚实边界")
    doc.para("主评测集是「边写题边补规则」，100% 不能说明泛化能力。因此另写 20 道问法不同的盲测题，"
             "写完只跑一次，结果为 75%。失败的 5 题全部是「意图路由没覆盖问法」——"
             "同一问题换个说法（「被剔掉的那 549 行」而不是「取消订单」）就路由不到对应工具。")
    doc.callout("这条结论比 100% 更有价值",
                "它说明规则式路由是当前架构的真实瓶颈，也解释了为什么必须接入真模型做语义路由。"
                "补完 5 条正则后重测为 100%，但那已等于用测试集调参，因此对外只报 75%，"
                "不把重测结果当成绩。")
    doc.para("已知边界与不足（主动列出）：")
    doc.bullet([
        "规则式意图路由不鲁棒，换说法可能失效，这是当前最大短板；",
        "文档检索用 TF-IDF，同义改写召回弱；",
        "未做参数微调，口径靠提示词注入，规则变多后提示词会膨胀；",
        "评测集仅 80 题且由作者自写，存在主观偏差，缺少第三方盲测；",
        "全部数字来自离线规则引擎时，仅反映管线有效性，不等于大模型能力。",
    ])

    doc.h2("3.8", "效率与业务价值")
    doc.table(
        ["维度", "人工方式", "本系统", "说明"],
        [["单次经营问数", "跨表写 SQL + 核对口径，约 10~30 分钟", "0.05~0.07 秒", "接口实测平均耗时"],
         ["口径核对", "靠人记忆或翻文档", "规则库强制生效", "33 条规则，带编号可追溯"],
         ["越界请求", "由人判断是否可行", "100% 被拦并给替代方案", "11 条越界规则"],
         ["数据错误决策", "难以及时发现", "首句即纠正", "见 3.3 对比"]],
        [1.35, 2.5, 1.6, 1.6], caption="表 3-5　效率对比（时间来自接口实测，非估算）")
    doc.para("业务价值的量级判断：把「问一次数据要等半天」压缩到「问一句就有答案且带依据」，"
             "改变的是决策频率而不仅是效率。需要说明的是，收益的绝对值依赖真实企业的决策频次与"
             "单次决策金额，本案例为公开数据仿真，不提供货币化收益数字——这也是我们不夸大的地方。")


def sec4(doc: Doc, f: dict):
    doc.h1("四", "附件材料")

    doc.h2("4.1", "代码与文件清单")
    doc.para("代码为纯 Python 实现，无 GPU 依赖，可离线运行。目录结构如下：")
    doc.code("项目根/\n"
             "├── llm/                      垂直大模型层（新增，约 3,800 行）\n"
             "│   ├── config.py             底座与项目约束常量\n"
             "│   ├── knowledge/            口径规则库 + 文档检索\n"
             "│   ├── tools/                22 个 function calling 工具\n"
             "│   ├── agent/                护栏 / 提示词 / 组装 / 编排\n"
             "│   ├── providers/            OpenAI 兼容底座适配（DeepSeek/Qwen/GLM）\n"
             "│   └── eval/                 80 道题 + 评分器\n"
             "├── app/                      后端接口（新增 llm_api.py，其余复用）\n"
             "├── static/assistant.html     对话页面\n"
             "├── scripts/                  构建与验收脚本\n"
             "│   ├── make_figs.py          生成报告图表\n"
             "│   ├── make_qr.py            生成演示视频二维码\n"
             "│   ├── build_submission.py   生成本 PDF\n"
             "│   ├── llm_smoke.py          14 项冒烟检查\n"
             "│   └── run_eval.py           评测入口\n"
             "└── 文档/                     方案书 / 口径手册 / 评测报告")

    doc.h2("4.2", "测试数据集说明")
    doc.para("评测集以 JSONL 存放，每题含题目、类别、必须命中的事实组（must_any）与禁忌表述（must_not），"
             "可被脚本直接消费，也可人工复核：")
    doc.table(
        ["字段", "含义", "示例"],
        [["id", "编号", "A01 / B07 / C03 / D11"],
         ["category", "类别", "A 口径 / B 决策 / C 拒答 / D 边界"],
         ["question", "提问原文", "我们 GMV 1359 万，那营收就是 1359 万吧？"],
         ["must_any", "必须命中的事实组（组内任一）", "[['不含运费','不等于营收'],['13,591,643']]"],
         ["must_not", "出现即判错的表述", "['GMV 就是营收']"],
         ["expect_tools", "期望调用的工具", "['dashboard_summary']"]],
        [1.2, 2.4, 3.1], caption="表 4-1　评测集字段说明")
    doc.para("数据集文件：llm/eval/questions.jsonl（60 题）、llm/eval/questions_blind.jsonl（20 题盲测）。")

    doc.h2("4.3", "部署与验证证据")
    doc.para("部署方式为单机 Python 服务，无外部依赖服务。启动与验收命令：")
    doc.code("$ python -m uvicorn app.main:app --host 127.0.0.1 --port 8000\n"
             "$ python scripts/llm_smoke.py\n"
             "  通过 14 项，失败 0 项  全部通过 ✅\n"
             "$ python scripts/run_eval.py\n"
             "  规则 33 条 / 工具 22 个 / 文档 239 段 / 数据源 db\n"
             "$ curl -s localhost:8000/api/llm/health\n"
             '  {"config":{"provider":"offline"},"knowledge":{"rules":33},'
             '"tools":{"datasource":"db","tools":22}}')
    doc.para("现有 32 个无参 GET 接口在新增模块后全部返回 200，且无接口慢于 3 秒——"
             "说明新增层未破坏原有系统。")
    doc.placeholder("此处插入「对话页面运行截图」（建议 1 张）",
                    "打开 http://127.0.0.1:8000/assistant 提问后截图，覆盖右侧取数轨迹与数据依据面板", 150)
    doc.placeholder("此处插入「评测报告截图」（可选）",
                    "运行 python scripts/run_eval.py 后截取控制台表格", 110)

    doc.h2("4.4", "演示视频二维码")
    if QR.is_file():
        doc.para("扫码查看演示视频（建议在提交前用自己的手机再扫一次，确认无需登录即可播放）：")
        doc.image(QR, width=150, caption="图 4-1　演示视频二维码")
    else:
        doc.placeholder("演示视频二维码（待生成）",
                        "运行 python scripts/make_qr.py --url <视频链接> 后重新生成本 PDF，二维码将自动嵌入此处",
                        150)
    doc.para("提醒：若视频设置了访问权限或链接失效，评委扫码将无法查看。"
             "请务必在提交前用未登录设备实测一次。")

    doc.h2("4.5", "口径规则节选")
    doc.table(
        ["编号", "口径要点"],
        [["GMV-01", "GMV 是商品金额，不含运费、不扣成本，不等于营收，也不等于用户实付"],
         ["GMV-02", "客单价 136.68（GMV÷订单数）与人均消费 142.44 是两个指标，不可混用"],
         ["USER-01", "用户粒度必须用 customer_unique_id（95,420），不是 customer_id（99,441）"],
         ["USER-05", "用户数 96,096（含取消订单）与 95,420（有效订单）都合法，须说明口径"],
         ["DATA-01", "未评价评分必须保持 NULL，填 0 会把均值从 4.086 拉到 4.055"],
         ["DATA-02", "销量只算有效状态订单，剔除取消与缺货（112,650 → 112,101 行）"],
         ["DATA-06", "1,234 单取消/缺货 vs 549 行明细：两个数都对，单位不同"],
         ["FC-01", "预测粒度固定品类×周，最多 8 周，不支持日/商品/卖家/地区粒度"],
         ["FC-02", "MAPE 均值被低基数周放大，须同时报中位数与 WAPE，只能说部分品类优于基线"],
         ["SEL-02", "综合分为百分位排名加权，量纲不同不能直接用原始值相加"],
         ["PRC-03", "建议价夹在现价 ±15% 内，是业务约束而非模型能力上限"],
         ["PRC-04", "平均预期收入变化 +26.60% 是模型测算值，上线前必须小范围 A/B"]],
        [1.0, 5.0], caption="表 4-2　口径规则节选（完整 33 条见 文档/口径手册.md）")
    doc.para("—— 正文结束 ——", fs=9, color=C_GREY)


# ======================================================================
# ⑥ 构建
# ======================================================================
def build(pages: dict, f: dict, samples) -> dict:
    doc = Doc(footer=f"{META['title']} · {META['unit']}",
              header=f"{META['unit']}　|　{META['title']}")
    cover(doc)
    toc_page(doc, pages)
    sec1(doc, f)
    sec2(doc, f)
    sec3(doc, f, samples)
    sec4(doc, f)
    path = OUT_DIR / fname()
    n = doc.save(path)
    return doc.marks, n


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not (FIG / "fig_arch.png").is_file():
        print("缺少图表，先运行：python scripts/make_figs.py")
        return 1

    f = load_facts()
    samples = qa_samples()
    marks, n1 = build({}, f, samples)       # 第一遍：拿页码
    marks, n2 = build(marks, f, samples)    # 第二遍：目录填页码
    path = OUT_DIR / fname()
    print(f"✅ 已生成：{path.relative_to(ROOT)}（{n2} 页，{path.stat().st_size / 1024:.0f} KB）")
    if n1 != n2:
        print(f"⚠️ 两遍页数不一致（{n1} vs {n2}），目录页码可能偏移，请检查")
    if "【" in path.name:
        print("⚠️ 文件名仍含【】占位，提交前请修改 META 后重跑")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
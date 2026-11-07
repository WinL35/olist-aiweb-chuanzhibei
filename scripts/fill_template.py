#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把内容填进官方申报模板（保留模板样式）。

用法：
    /path/to/bundled/python3 scripts/fill_template.py

要点：
  · 正文按模板要求用「仿宋_GB2312 五号」；
  · 只替换模板里的说明性占位段，不动封面、填写说明、章节标题；
  · 表格/图片插在对应小节内，位置由锚点元素决定；
  · 未确认的信息用【】标出，便于替换。
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent.parent
TPL = Path("/Users/jaymon./Downloads/第三届“兴智杯”全国人工智能创新应用大赛解决方案赛项目申报模版 - 主题赛及专项赛阶段-2.docx")
OUT = ROOT / "提交材料" / "申报书_模板版.docx"
FIG = ROOT / "提交材料" / "figs"
QR = ROOT / "提交材料" / "qr_video.png"

FONT = "仿宋_GB2312"
BODY_PT = 10.5          # 五号
GREEN = RGBColor(0x1F, 0x6B, 0xD0)
GREY = RGBColor(0x60, 0x66, 0x70)


# ---------------------------------------------------------------- 基础工具
def style_run(run, size=BODY_PT, bold=False, color=None, font=FONT):
    run.font.size = Pt(size)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    run.font.name = font
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font)


def ins_para(doc, anchor, text="", *, indent=True, bold=False, size=BODY_PT,
             align=None, color=None, space_before=0, space_after=4, lead=1.5):
    """在 anchor 元素之后插入段落，返回新段落元素（作为下一个锚点）。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = lead
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if indent:
        pf.first_line_indent = Pt(size * 2)
    if align is not None:
        p.alignment = align
    if text:
        style_run(p.add_run(text), size=size, bold=bold, color=color)
    anchor.addnext(p._p)
    return p._p


def ins_table(doc, anchor, headers, rows, widths=None, fs=9.0, caption=""):
    """插入三线表（表头深色底）。返回最后一个元素。"""
    cur = anchor
    if caption:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        style_run(p.add_run(caption), size=9.0, bold=True, color=GREY)
        cur.addnext(p._p)
        cur = p._p

    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    data = [headers] + rows
    for ri, row in enumerate(data):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_before = Pt(1)
            para.paragraph_format.space_after = Pt(1)
            para.paragraph_format.line_spacing = 1.0
            run = para.add_run(str(val))
            style_run(run, size=fs, bold=(ri == 0))
            if ri == 0:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                shd = cell._tc.get_or_add_tcPr().makeelement(qn("w:shd"), {})
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), "1F2A3A")
                cell._tc.get_or_add_tcPr().append(shd)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if widths:
                cell.width = Cm(widths[ci])
    cur.addnext(tbl._tbl)
    return tbl._tbl


def ins_image(doc, anchor, path: Path, width_cm=14.6, caption=""):
    cur = anchor
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    if path.is_file():
        p.add_run().add_picture(str(path), width=Cm(width_cm))
    else:
        style_run(p.add_run(f"【缺少图片：{path.name}】"), size=9, color=RGBColor(0xC0, 0x40, 0x00))
    cur.addnext(p._p)
    cur = p._p
    if caption:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.space_after = Pt(8)
        style_run(cp.add_run(caption), size=9.0, color=GREY)
        cur.addnext(cp._p)
        cur = cp._p
    return cur


def ins_note(doc, anchor, text):
    """灰底提示条（用于占位提醒）。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    style_run(p.add_run(text), size=9.5, bold=True, color=RGBColor(0xC0, 0x50, 0x00))
    anchor.addnext(p._p)
    return p._p


def find_para(doc, needle: str) -> Paragraph | None:
    for p in doc.paragraphs:
        if needle in p.text:
            return p
    return None


def replace_text(p: Paragraph, text: str, bold=False):
    """清空段落并写入一个 run（保留段落属性）。"""
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    style_run(p.add_run(text), bold=bold)


def tick_table(table: Table, targets: dict[str, str]):
    """把指定 □ 项改为 ■；targets: {原文字: 新文字}"""
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            if cell._tc in seen:
                continue
            seen.add(cell._tc)
            t = cell.text.strip()
            for old, new in targets.items():
                if old in t:
                    para = cell.paragraphs[0]
                    for r in list(para.runs):
                        r._element.getparent().remove(r._element)
                    style_run(para.add_run(t.replace(old, new)), size=10.5)


# ---------------------------------------------------------------- 正文内容
def fill_cover_table(doc):
    meta = {
        "项目名称": "电商经营决策垂直大模型",
        "主题赛名称": "行业赋能赛",
        "赛题名称": "垂直行业大模型应用",
        "团队名称": "【团队名称，例：XX大学大数据2403实践队】",
        "填报日期": "2026年10月29日",
    }
    if not doc.tables:
        return
    tbl = doc.tables[0]
    for row in tbl.rows:
        key = row.cells[0].text.replace("：", "").replace(":", "").strip()
        if key in meta:
            cell = row.cells[1]
            para = cell.paragraphs[0]
            for r in list(para.runs):
                r._element.getparent().remove(r._element)
            style_run(para.add_run(meta[key]), size=10.5)


def sec_basic(doc):
    # 项目名称
    p = find_para(doc, "项目名称（与官网提交材料保持一致）")
    if p:
        cur = ins_para(doc, p._p, "电商经营决策垂直大模型（Olist 经营决策助手）", bold=True)
        # 应用行业及场景
        h = find_para(doc, "应用行业及场景")
        if h:
            cur = ins_para(doc, h._p, "应用行业：跨境电子商务、中小电商经营分析。")
            cur = ins_para(doc, cur,
                           "应用场景：面向没有数据分析岗位的中小电商团队，用自然语言直接问经营问题，"
                           "系统给出带数据依据、带口径说明的回答。覆盖六类高频场景——经营大盘问数、"
                           "统计口径核对与纠偏、品类销量预测、选品、定价建议、用户分层与转化漏斗解读。"
                           "系统以对话方式调用现有接口与算法结果，不改变原有数据链路，可叠加在已有业务系统之上。")
            cur = ins_para(doc, cur,
                           "说明：本文中「GMV（Gross Merchandise Volume，商品交易总额）」"
                           "「MAPE（Mean Absolute Percentage Error，平均绝对百分比误差）」"
                           "「RAG（Retrieval-Augmented Generation，检索增强生成）」"
                           "「RFM（Recency-Frequency-Monetary，最近一次消费-消费频率-消费金额模型）」"
                           "等外文缩写，首次出现时已给出全称，后文使用缩写。")


def sec_core_tech(doc):
    tbl = None
    for t in doc.tables:
        if t.rows and "计算机视觉" in t.rows[0].cells[0].text:
            tbl = t
            break
    if tbl is None:
        return
    tick_table(tbl, {"□自然语言处理": "■自然语言处理",
                     "□其他（请提供核心技术名称）": "■其他：检索增强生成（RAG）、大模型工具调用与机器学习建模"})


def sec_stage(doc):
    tbl = None
    for t in doc.tables:
        if t.rows and "方案验证阶段" in t.rows[0].cells[0].text:
            tbl = t
            break
    if tbl is None:
        return
    tick_table(tbl, {"□方案验证阶段": "■方案验证阶段"})


def sec_background(doc):
    p = find_para(doc, "从行业痛点、市场需求、场景价值性等方面阐述")
    if not p:
        return
    replace_text(p, "一、中小电商有数据，但没有把数据变成决策的能力。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "以本作品使用的公开数据集为例：11.2 万条订单明细、9.9 万个订单、9.5 万名用户、74 个品类、"
                   "13 张业务表、10 个统计视图。回答一个「这个品类下周要不要备货」，需要跨 4 张表做聚合，"
                   "再跑一遍时间序列模型。绝大多数中小商家既没有分析师，也没有时间。"
                   "数据资产在账上，决策仍然凭感觉。")
    cur = ins_para(doc, cur,
                   "二、通用大模型已经能对话，但在经营场景里有两个致命缺陷。"
                   "第一是口径错——它会自然地把「GMV」当作「营收」，把「客单价」和「人均消费」混用；"
                   "第二是数字假——它给出的销量、价格、增长率往往是编出来的，看起来合理却无从核对。"
                   "在本作品的对照实验中，未加固的通用模型在口径类问题上的通过率为 0%。")
    cur = ins_para(doc, cur,
                   "三、需要的不是更大的模型，而是一层「行业约束」。"
                   "本项目的判断是：垂直行业大模型的难点不在参数规模，而在三件事——"
                   "把行业口径写成模型绕不过去的硬规则、把真实数据接成模型可以调用的工具、"
                   "把能力边界写成明确会拒答的范围。这三件事都属于工程问题，与模型大小无关。"
                   "因此项目定位为「约束层」：底座可替换，约束可迁移。")
    cur = ins_para(doc, cur,
                   "四、场景价值。中小电商最缺的不是报表，而是「问一句就有答案，且答案能被追问」。"
                   "把问一次数据从「等分析师半天」压缩到「0.05 秒出结果、并附口径与依据」，"
                   "改变的是决策频率，而不仅是效率。这一点在后续应用情况中有实测数据支撑。")


def sec_scenarios(doc):
    p = find_para(doc, "介绍项目（产品、解决方案等）的核心功能及主要应用场景")
    if not p:
        return
    replace_text(p, "系统以「一个对话入口 + 五个能力模块」的形式提供，六类高频场景如下：")
    cur = p._p
    cur = ins_table(doc, cur,
                    ["场景", "用户怎么问", "系统怎么做", "输出"],
                    [["经营大盘", "「我们整体做得怎么样？」", "调用大盘工具取规模、趋势、品类结构", "数＋趋势判断＋口径提醒"],
                     ["口径纠偏", "「GMV 就是营收吧？」", "命中口径硬规则，首句纠正", "正确口径＋4 个相关数值"],
                     ["销量预测", "「美妆未来 4 周能卖多少？」", "调预测工具，取品类周销量与区间", "预测值＋区间＋可信度说明"],
                     ["选品", "「该重点推哪些商品？」", "调选品榜单与命中率工具", "榜单＋命中率＋权重说明"],
                     ["定价", "「这款能不能降价？」", "调价格弹性与建议价工具", "建议价＋幅度约束＋A/B 提醒"],
                     ["用户与漏斗", "「为什么下单少？」", "调 RFM、漏斗、复购工具", "分层占比＋漏斗损耗环节"]],
                    widths=[2.5, 4.6, 5.2, 4.2],
                    caption="表 1　六类核心场景")
    cur = ins_para(doc, cur, "核心功能模块：")
    for line in [
        "（1）对话式问数：自然语言 → 工具调用 → 结构化数字，所有数字来自后端接口，与网页端一致，不存在第二个真相。",
        "（2）口径守护：33 条口径硬规则常驻，其中 23 条无条件注入，用户要求「把数字改好看」时系统拒绝并纠正。",
        "（3）文档依据：239 段行业文档检索，回答附带出处，检索不到时显式说明「本次未检索到」，不编依据。",
        "（4）越界拒答：日粒度、单品级、卖家级、库存、毛利等超出数据能力的提问直接拒答，并给出可行的替代问法。",
        "（5）离线可运行：未配置模型密钥或断网时，走确定性引擎，功能不缺失，回答中明确标注模式。",
        "（6）可视化页面：独立的对话页，左侧对话、右侧实时显示取数轨迹、引用片段与命中的规则编号。",
    ]:
        cur = ins_para(doc, cur, line, indent=False, space_after=2)


def sec_solution(doc):
    p = find_para(doc, "从设计理念、核心技术路线、系统架构、软硬件部署等方面")
    if not p:
        return
    replace_text(p, "1. 设计理念：约束优先于生成。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "传统做法是「让模型更懂行业」，靠喂语料、做微调。本项目选择另一条路："
                   "承认模型会犯错，然后用代码把错误挡住——数字只能来自工具、口径只能来自规则库、"
                   "越界只能拒答。提示词可以被诱导，if 语句不能。"
                   "这一取舍使系统在没有任何模型微调的情况下，口径类问题通过率从 0% 提升到 100%。")
    cur = ins_para(doc, cur, "2. 系统架构：五层，自下而上职责单一。")
    cur = ins_image(doc, cur, FIG / "fig_arch.png", 14.2, "图 1　五层架构（上层依赖下层，底座可替换）")
    cur = ins_table(doc, cur,
                    ["层级", "职责", "实现要点"],
                    [["数据层", "提供可信数据", "业务库 13 表 10 视图（87.2 万行）＋算法结果库 9 表（9.6 万行）"],
                     ["知识层", "把口径变成约束", "33 条结构化硬规则 ＋ 239 段文档检索（TF-IDF 字符 n-gram）"],
                     ["工具层", "让模型能算", "22 个 function calling 工具，直接复用后端路由函数"],
                     ["决策层", "编排与表达", "ReAct 循环（≤4 步）＋ 离线确定性引擎双路径，四段式输出"],
                     ["评测层", "量化有效性", "80 道题（60 主集＋20 盲测）× 4 种消融模式，纯字符串判分"]],
                    widths=[2.2, 4.2, 10.0],
                    caption="表 2　五层架构职责")
    cur = ins_para(doc, cur, "3. 知识层：33 条硬规则，只收真实踩过的坑。")
    cur = ins_para(doc, cur,
                   "规则不是散文，而是带编号、关键词、错误说法、正确说法、证据与出处的结构化对象，"
                   "因此可以被检索、被引用、被回归测试。规则全部来源于团队真实答错过的场景，"
                   "例如「未评价订单的评分填 0」会把均值从 4.086 拉到 4.055，"
                   "「取消订单算进 GMV」会让口径从 13,494,400.74 虚增到 13,591,643.70。")
    cur = ins_para(doc, cur,
                   "文档侧使用检索增强生成（RAG），未采用向量库是一个明确的工程取舍："
                   "向量模型需下载数百 MB，答辩现场断网即失效；TF-IDF 字符 n-gram 零依赖、可解释、延迟低于 20 ms。"
                   "代价是同义改写召回较弱，已在不足中说明。")
    cur = ins_para(doc, cur, "4. 工具层：22 个工具，复用后端函数而非重写 SQL。")
    cur = ins_para(doc, cur,
                   "工具执行器在数据库模式下直接调用既有路由函数，因此模型报出的数字与网页上看到的完全一致。"
                   "工具描述本身即为调度指令，例如大盘工具的描述中明确写「凡问整体规模必须先调用，禁止凭印象给数」，"
                   "把「该不该查数」从自由裁量变为硬规则。数据库不可用时自动降级读清洗后的 CSV，并在回答中标注来源。")
    cur = ins_para(doc, cur, "5. 决策层：双路径，保证任何情况下都不空手返回。")
    cur = ins_table(doc, cur,
                    ["路径", "触发条件", "特点"],
                    [["模型 + ReAct", "已配置底座密钥", "语义路由鲁棒、语言自然，能处理未见问法"],
                     ["离线确定性引擎", "无密钥／断网／底座故障", "零依赖、稳定、可离线演示，作为能力下界"]],
                    widths=[3.2, 4.8, 8.4],
                    caption="表 3　双路径设计")
    cur = ins_para(doc, cur,
                   "两条路径共享同一套规则、同一批工具、同一种输出结构，因此可以公平对比——"
                   "差异只在语言组织这一层，这正是消融实验要分离的变量。输出强制四段式："
                   "结论（带关键数字）、数据依据（指标：数值＋来源工具）、口径提醒（带规则编号）、局限（不能用于什么）。")
    cur = ins_para(doc, cur, "6. 安全可信：三重护栏，全部落在代码里。")
    cur = ins_table(doc, cur,
                    ["护栏", "实现", "拦截示例"],
                    [["越界拒答", "11 条正则，覆盖日粒度、卖家级、库存、毛利、退货、竞品、用户行为",
                      "「预测卖家 A 明天卖多少」→ 拒答并给替代方案"],
                     ["口径篡改拦截", "7 条策略规则，命中后强制在结论首句纠正",
                      "「把取消订单算进 GMV 让数字好看」→ 首句纠正，给 549 行依据"],
                     ["调价幅度约束", "诉求幅度与 ±15% 业务约束比对，超出即说明",
                      "「提价 50% 能增收多少」→ 说明约束，不给该幅度数值"]],
                    widths=[2.6, 6.6, 6.2],
                    caption="表 4　三重护栏")
    cur = ins_para(doc, cur,
                   "其中「口径篡改拦截」是本项目的重点设计。企业内要求「把复购率改成 10% 好看点」的请求极常见，"
                   "也是数据造假的主要入口。系统对这类请求无权答应，规则命中后强制在结论开头说明「不能，实际 3.05%」。"
                   "用代码拦截比用提示词劝阻可靠得多。")
    cur = ins_para(doc, cur, "7. 部署方式：单机可跑，成本可控。")
    cur = ins_table(doc, cur,
                    ["项", "配置", "说明"],
                    [["运行环境", "Python 3.13 + FastAPI + uvicorn", "无 GPU 依赖，普通笔记本可跑"],
                     ["数据", "MySQL 8（本机或内网）", "缺失时自动降级为 CSV 文件"],
                     ["模型底座", "任意 OpenAI 兼容接口", "DeepSeek／通义千问／GLM／vLLM／Ollama 均可，改一个环境变量"],
                     ["硬件", "8 核 16 GB 云主机（建议）", "当前开发机为普通 MacBook，32 个接口平均响应 0.05 秒"]],
                    widths=[2.4, 6.4, 6.6],
                    caption="表 5　部署配置")
    cur = ins_para(doc, cur,
                   "接底座只需设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 三个环境变量；不设则跑离线引擎。"
                   "这一设计使现场演示不依赖网络与付费账号，也便于评委在自己机器上复现。")
    cur = ins_para(doc, cur, "8. 关于微调：本项目暂未做参数微调，理由是技术判断而非资源妥协。")
    cur = ins_para(doc, cur,
                   "微调能改善领域语言与话术风格，但无法保证「数字真实」——后者只能靠工具调用；"
                   "而本项目 33 条硬规则已使开发集达到 100%，微调边际收益不明。方案保留微调路径并明确触发条件："
                   "口径规则超过 100 条导致提示词膨胀时、需要固定话术风格时、有 GPU 需完全离线部署时，"
                   "分别对应「口径内化」「风格对齐」「小模型蒸馏」三种目标，数据构造方式已在方案书中写明。")


def sec_innovation(doc):
    p = find_para(doc, "介绍项目（产品、解决方案等）的创新点")
    if not p:
        return
    replace_text(p, "1. 口径即代码：把行业知识写成可回归测试的硬约束。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "多数垂直问答系统把行业知识写进提示词，效果依赖措辞且无法回归。本项目把 33 条口径做成"
                   "带编号的结构化对象，每条都有「错误说法／正确说法／证据／出处」，可被检索、可被引用、"
                   "可用测试集回归。新增一条规则，测试集立刻能验证它是否生效。这是把知识工程化的做法，"
                   "而不是把知识堆进提示词。")
    cur = ins_para(doc, cur, "2. 口径篡改拦截：在数据造假入口处设闸。")
    cur = ins_para(doc, cur,
                   "业内普遍关注「模型会不会说错」，较少关注「用户要求模型说错」。后者在企业场景中更危险，"
                   "因为它会系统性地污染报表。本项目用 7 条策略规则识别此类诉求，并强制在回答首句纠正，"
                   "同时给出正确数值与依据。这一设计在同类产品中少见，且实现成本极低。")
    cur = ins_para(doc, cur, "3. 工具复用后端路由：从架构上消灭「两个真相」。")
    cur = ins_para(doc, cur,
                   "常见做法是为模型另写一套查询 SQL，结果与系统页面常对不上，用户信任迅速崩塌。"
                   "本项目让工具直接调用既有路由函数，页面与对话共用同一实现，数字天然一致。"
                   "这一决定牺牲了一点性能（多一层函数调用），换来的是可核对性。")
    cur = ins_para(doc, cur, "4. 双路径与离线评测：答辩现场断网也能演示完整能力。")
    cur = ins_para(doc, cur,
                   "离线确定性引擎与模型路径共享规则与工具，既是兜底，也是评测下界。"
                   "它让「模型有没有帮助」可以被量化，而不是只能靠观感。")
    cur = ins_para(doc, cur, "5. 可迁移的评测方法：四模式消融，把「有效性」拆成可测的量。")
    cur = ins_para(doc, cur,
                   "评测集按「口径陷阱／多步决策／拒答／边界合规」四类设计，配合 baseline（裸底座）、"
                   "no_tools（有知识无工具）、no_rag（有工具无检索）、full（全量）四种模式，"
                   "可以分别回答「知识有没有用」「工具有没有用」「检索有没有用」。"
                   "这套方法不依赖具体行业，换一个垂直领域可直接复用。")
    cur = ins_para(doc, cur, "6. 迁移成本低：五步法把行业约束层搬到新领域。")
    cur = ins_para(doc, cur,
                   "步骤为：梳理该行业的高频口径陷阱 → 写成结构化规则 → 把已有接口注册为工具 → "
                   "设计四类评测题 → 用消融实验定位短板。经验上 2～3 人周可完成一个垂直领域的首版，"
                   "不需要标注数据，也不需要 GPU。这使方案具备横向复制到金融、医疗、制造的可行性。")


def sec_market(doc):
    p = find_para(doc, "分析项目（产品、解决方案等）的市场需求、趋势、容量")
    if not p:
        return
    replace_text(p, "（一）需求是结构性的，不是一两个工具能解决的。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "中小电商的数量远大于其数据分析能力。一家年成交几百万的店铺，通常有 1～3 人负责运营，"
                   "没有专职分析师；平台后台能导出明细，但导出之后仍要人做透视、写公式、算同比。"
                   "这部分工作既重复又容易出错，且高度依赖个别员工的隐性经验——人一走，口径就乱。"
                   "这是需求侧的刚性：不是「想要更酷的工具」，而是「没人做这件事」。")
    cur = ins_para(doc, cur, "（二）趋势：大模型落地正从「通用问答」转向「垂直＋工具」。")
    cur = ins_para(doc, cur,
                   "过去两年，企业对大模型的期待从「什么都能聊」转向「在我的业务里别出错」。"
                   "对应的技术重心也从模型规模转向检索增强、工具调用与流程编排。"
                   "本项目正好落在这条主线上：不追求模型能力，追求把模型约束在可核对的范围内。"
                   "这一方向与行业主流判断一致，但具体到「口径硬约束＋篡改拦截」的实现路径，尚未见到成熟产品。")
    cur = ins_para(doc, cur, "（三）市场容量：以部署成本反推可及市场。")
    cur = ins_para(doc, cur,
                   "本项目单实例部署成本可测算：一台 8 核 16 GB 云主机年费约数千元；若接通用底座 API，"
                   "按每次问答千级 token 估算，单店日均 50 次问答的年调用成本在百元量级（以上为估算，"
                   "随模型单价波动）。这意味着单店年成本可以控制在千元以内，落在中小商家的可接受区间。"
                   "本报告不引用未经核实的行业规模数字，仅说明：成本结构支持「按店收费」的商业模式成立。")
    cur = ins_para(doc, cur, "（四）市场接受度：门槛低是关键。")
    cur = ins_para(doc, cur,
                   "目标用户不会写 SQL、不会用 BI 拖拽、也不愿学新软件。对话是唯一不需要培训的交互方式，"
                   "这是本项目选择对话形态而非看板形态的根本原因。同时系统保留「数据依据」与「口径提醒」，"
                   "让用户逐步建立信任——对不懂数据的用户，可核对性比准确性更重要，因为前者才能被感知。")
    cur = ins_para(doc, cur, "（五）规模化可行性：分层部署。")
    cur = ins_para(doc, cur,
                   "小微商家走 SaaS 多租户，共享底座、按席位收费；中型商家走私有化，本地部署、数据不出内网；"
                   "平台方（ERP、电商 SaaS）走嵌入集成，把对话能力做成其产品的一个入口。"
                   "三种形态共用同一套规则库与工具层，差别只在部署与计费，边际成本低。")


def sec_business(doc):
    p = find_para(doc, "分析项目（产品、解决方案等）的市场定位、潜在竞争者")
    if not p:
        return
    replace_text(p, "（一）市场定位：不做大模型，做垂直行业大模型的「约束层」。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "定位的差异决定竞争关系。本项目不与通用大模型厂商竞争底座，反而可以在任意底座之上运行；"
                   "不与 BI 厂商竞争可视化，反而把 BI 的结果作为工具暴露给模型。"
                   "本项目卖的是「懂行」这件事本身：口径、边界、拒答规则，以及把这三样接进业务系统的工程能力。")
    cur = ins_para(doc, cur, "（二）潜在竞争者与替代品。")
    cur = ins_table(doc, cur,
                    ["类别", "代表形态", "相对优劣"],
                    [["通用大模型直连", "直接调用 ChatGPT／文心等", "优：便宜、快；劣：口径错、数字编造，本场景不可用"],
                     ["BI 与报表工具", "拖拽式看板、自助取数", "优：成熟、稳定；劣：要人主动找图，不回答开放问题"],
                     ["电商 SaaS 内置助手", "平台自带的智能客服／问数", "优：数据就绪；劣：只覆盖本平台数据，跨系统即失效"],
                     ["规则问答机器人", "关键词匹配的 FAQ 机器人", "优：可控；劣：换说法即失效，无法多步取数"],
                     ["本项目", "约束层＋工具编排＋评测体系", "优：能算、敢拒答、可核对、可迁移；劣：需对接数据，首版需 2～3 人周"]],
                    widths=[3.4, 5.4, 7.0],
                    caption="表 6　竞争格局与替代品")
    cur = ins_para(doc, cur, "（三）合作模式与开发策略。")
    cur = ins_para(doc, cur,
                   "与 ERP／电商 SaaS 厂商合作：对方提供数据接口与客户，本项目提供约束层与评测能力，"
                   "按调用量或席位分成。与咨询／代运营机构合作：把系统作为交付工具，提升其人均服务店铺数。"
                   "核心规则库与评测集计划开源，行业包（口径规则＋工具适配）按年订阅——"
                   "开源建立信任，订阅获得收入，这与当前开发者工具的通行做法一致。")
    cur = ins_para(doc, cur, "（四）份额预期与融资：现阶段如实说明。")
    cur = ins_para(doc, cur,
                   "项目目前处于方案验证阶段，尚无商业合同与营业收入，因此不提供份额与融资数字，"
                   "以免误导。下一步计划是先完成 2～3 家商户的试点，验证「口径纠偏」在真实业务中的价值，"
                   "再据试点数据测算单位经济模型。这一保守表述与项目阶段一致。")


def sec_application(doc):
    p = find_para(doc, "对项目（产品、解决方案等）当前的应用情况进行阐述")
    if not p:
        return
    replace_text(p, "（一）验证方式：公开数据仿真案例。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "本项目使用 Olist 巴西电商公开数据集（Kaggle）构建仿真案例，属方案验证，不是企业私有数据。"
                   "选择它的理由是数据真实、体量足够、口径陷阱典型：多状态订单、多支付方式、未评价订单，"
                   "正好覆盖本项目要解决的三类问题。案例覆盖完整经营链路：看规模 → 预测品类销量 → 选品 → 定价 → 评估可信度。")
    cur = ins_table(doc, cur,
                    ["维度", "数值"],
                    [["时间范围", "2016-09-04 ～ 2018-09-03（最后一周不完整，建模剔除）"],
                     ["订单／明细", "99,441 单／112,650 行，有效明细 112,101 行"],
                     ["用户／商品／品类", "95,420 人／32,729 个有成交商品／74 个品类"],
                     ["算法产物", "预测 592 行、选品 50 个、定价 50 个"]],
                    widths=[3.6, 12.0],
                    caption="表 7　仿真案例数据规模")
    cur = ins_para(doc, cur, "（二）应用成效一：口径纠偏，从 0% 到 100%。")
    cur = ins_table(doc, cur,
                    ["提问", "未加固的通用模型", "本系统"],
                    [["GMV 1359 万，营收就是 1359 万吧？", "把 GMV 当营收，答「可作为营收参考」",
                      "指出 GMV 不含运费、不等于营收，并给 4 个口径数值"],
                     ["复购率只有 3.1%，运营很差吧？", "泛泛建议做会员体系", "先说明一人一单属数据性质，再讲复购人群贡献 5.62% 金额"],
                     ["未评价订单评分能填 0 吗？", "答「可以，做好缺失值填充」", "拒绝：0 非合法星级，会把均值从 4.086 拉到 4.055"]],
                    widths=[4.6, 5.4, 5.8],
                    caption="表 8　口径纠偏效果对比（实测回答摘录）")
    cur = ins_para(doc, cur, "（三）应用成效二：量化评测，四模式消融。")
    cur = ins_para(doc, cur,
                   "评测集 80 题（60 主集＋20 盲测），按口径陷阱、多步决策、拒答、边界合规四类设计，"
                   "评分完全基于字符串匹配（必须命中的事实组／出现即错的禁忌表述），不含人工判断，任何人可复现。")
    cur = ins_table(doc, cur,
                    ["模式", "口径 A", "多步 B", "拒答 C", "边界 D", "总体", "工具命中"],
                    [["baseline 裸底座", "0.0%", "0.0%", "0.0%", "0.0%", "0.0%", "0.0%"],
                     ["no_tools 有知识无工具", "93.3%", "53.3%", "100%", "86.7%", "83.3%", "0.0%"],
                     ["no_rag 有工具无检索", "100%", "100%", "100%", "100%", "100%", "97.1%"],
                     ["full 全量", "100%", "100%", "100%", "100%", "100%", "97.1%"]],
                    widths=[4.4, 1.9, 1.9, 1.9, 1.9, 2.0, 1.9],
                    caption="表 9　消融实验结果（60 题主集）")
    cur = ins_image(doc, cur, FIG / "fig_ablation.png", 13.6, "图 2　四类题目通过率对比")
    cur = ins_para(doc, cur,
                   "读法有三点：裸底座 0% 说明没有工具与口径时模型会给出「看似正确、实际错误」的答案；"
                   "多步决策从 53.3% 提升到 100%，是工具层的直接贡献；检索在准确率上的增量为 0，"
                   "但依据覆盖率从 0% 提升到 90%，它提供的是可核对性而非正确率。项目如实报告这一结果，"
                   "不把「检索有用」说成准确率提升。")
    cur = ins_para(doc, cur, "（四）应用成效三：诚实边界，盲测 75%。")
    cur = ins_para(doc, cur,
                   "主评测集是边写题边补规则，100% 不能说明泛化能力。因此另写 20 道问法不同的盲测题，"
                   "写完只跑一次，结果为 75%。失败的 5 题全部是意图路由未覆盖问法（例如用「被剔掉的那 549 行」"
                   "而非「取消订单」），不是知识错误。补完正则后重测为 100%，但那已等于用测试集调参，"
                   "因此本报告只报 75%。这一发现的价值高于 100%：它定位了当前架构的真实瓶颈——规则式路由，"
                   "也说明接入真实底座做语义路由是必要的一步。")
    cur = ins_para(doc, cur, "（五）部署情况与工程验证。")
    cur = ins_para(doc, cur,
                   "系统已在本机完成部署，新增垂直大模型层后，原有 32 个无参接口全部返回 200，无一慢于 3 秒，"
                   "说明新增层未破坏既有系统。冒烟测试 14 项全部通过，评测脚本可一键复现上表结果。"
                   "对话页与评测报告均已实际运行，界面见附录。")
    cur = ins_para(doc, cur, "（六）经济效益：给可验证的效率数据，不给估算的货币数字。")
    cur = ins_table(doc, cur,
                    ["维度", "人工方式", "本系统"],
                    [["单次经营问数", "跨表写 SQL 并核对口径，约 10～30 分钟", "0.05 秒（接口实测平均耗时）"],
                     ["口径核对", "靠记忆或翻文档，易出错", "33 条规则强制生效，带编号可追溯"],
                     ["越界请求识别", "依赖个人判断", "11 条规则 100% 拦截并给替代方案"]],
                    widths=[3.4, 7.2, 4.8],
                    caption="表 10　效率对比")
    cur = ins_para(doc, cur,
                   "货币化的收益取决于真实企业的决策频次与单次决策金额，本项目尚无真实企业数据，因此不作估算。"
                   "这一点与「不给无依据数字」的产品原则一致。")


def sec_social(doc):
    p = find_para(doc, "分析项目（产品等）的社会效益")
    if not p:
        return
    replace_text(p, "（一）降低数字化门槛，惠及小微商家。")
    cur = p._p
    cur = ins_para(doc, cur,
                   "数据分析能力长期集中在中大型企业。本项目的核心价值是把「问一句就有答案」的能力带到"
                   "只有一两个人做运营的小店：不需要买 BI、不需要雇分析师、不需要学 SQL。"
                   "当工具的使用门槛降到「会说话」时，受益的首先是资源最少的那批经营者，这是数字普惠的直接体现。")
    cur = ins_para(doc, cur, "（二）守护数据诚信。")
    cur = ins_para(doc, cur,
                   "「把数字改好看」是数据造假的起点。本项目把口径约束与篡改拦截写进代码，使系统在被人要求"
                   "篡改口径时明确拒绝并给出正确值。这一设计在商业上并不讨好——它拒绝了部分用户需求——"
                   "但从行业视角看，一个默认不肯造假的工具，比一百份合规倡议更有约束力。"
                   "这是本项目认为最值得强调的社会价值。")
    cur = ins_para(doc, cur, "（三）能力可迁移，方法可复用。")
    cur = ins_para(doc, cur,
                   "项目的五步迁移法（梳理口径陷阱 → 结构化规则 → 注册工具 → 设计四类题 → 消融定位短板）"
                   "同样适用于金融风控、医疗问诊、工业质检等强口径行业。约束层与行业无关，只要该行业存在"
                   "「说错就会出事」的知识点，方法就成立。这使本项目的社会价值不局限于电商。")
    cur = ins_para(doc, cur, "（四）人才培养与教学价值。")
    cur = ins_para(doc, cur,
                   "项目由在校学生团队在课程实践中完成，覆盖数据建模、时间序列、机器学习、后端工程、"
                   "检索与评测六个环节，全部代码与文档开源可复现。评测集、盲测方法与失败案例（含 5 道路由失败题）"
                   "一并保留，可作为「大模型应用落地」的教学案例——尤其是那份诚实记录的失败清单，"
                   "比只展示成功的作品更有教学意义。")


def sec_appendix(doc):
    p = find_para(doc, "1、项目（产品、解决方案等）实物或实际应用图片")
    if p is None:
        return
    replace_text(p, "1、实际应用图片")
    cur = p._p
    cur = ins_para(doc, cur,
                   "下图为系统实际运行界面：左侧为对话，右侧实时显示取数轨迹（调用了哪些工具、返回什么）、"
                   "引用片段与命中的口径规则编号。截图由本机实际运行产生。", indent=True)
    cur = ins_note(doc, cur, "【此处插入对话页面运行截图 1 张：打开 /assistant 提问后截图，建议覆盖右侧轨迹面板】")
    cur = ins_para(doc, cur,
                   "系统已实现 7 个可视化页面（经营总览、区域分析、用户画像、销量预测、智能选品、智能定价、"
                   "对话助手）与 33 个后端接口，均可正常运行。")
    cur = ins_note(doc, cur, "【此处可插入看板页面截图 1～2 张（可选）】")

    # 第二项：评测报告 + 二维码
    p2 = find_para(doc, "2、项目（产品、解决方案等）的评估验证证书")
    if p2 is not None:
        replace_text(p2, "2、评测报告与产品应用演示视频")
        cur = p2._p
        cur = ins_para(doc, cur,
                       "评测报告（摘要）：80 道题、4 种模式、7 项指标，全部由脚本生成，可一键复现。"
                       "关键结论已列入表 9；完整报告见项目文档《评测报告》。评分规则为纯字符串匹配，"
                       "不含人工评分，避免自评偏差。")
        cur = ins_para(doc, cur, "产品应用演示视频（扫码查看，建议在提交前用未登录设备实测一次）：")
        if QR.is_file():
            cur = ins_image(doc, cur, QR, 4.6, "图 3　演示视频二维码")
        else:
            cur = ins_note(doc, cur, "【此处插入演示视频二维码：运行 scripts/make_qr.py --url <视频链接> 后重新生成】")
        cur = ins_para(doc, cur,
                       "如视频设置了访问权限或链接失效，评委将无法扫码查看，请务必确认链接公开可用。",
                       indent=True)

    # 第三项：其他材料
    p3 = find_para(doc, "3、其他相关说明或证明材料")
    if p3 is not None:
        replace_text(p3, "3、其他说明与证明材料")
        cur = p3._p
        cur = ins_para(doc, cur, "（1）口径规则节选（完整 33 条见《口径手册》）：")
        cur = ins_table(doc, cur,
                        ["编号", "口径要点"],
                        [["GMV-01", "GMV 是商品金额，不含运费、不扣成本，不等于营收，也不等于用户实付"],
                         ["USER-01", "用户粒度须用 customer_unique_id（95,420），不是 customer_id（99,441）"],
                         ["DATA-01", "未评价评分必须保持 NULL，填 0 会把均值从 4.086 拉到 4.055"],
                         ["DATA-06", "取消与缺货 1,234 单对应 549 行明细，两个数都对，单位不同"],
                         ["FC-01", "预测粒度固定品类×周，最多 8 周，不支持日／单品／卖家粒度"],
                         ["PRC-04", "平均预期收入变化 +26.60% 为模型测算值，上线前必须小范围 A/B 验证"]],
                        widths=[2.6, 13.0],
                        caption="表 11　口径硬规则节选")
        cur = ins_para(doc, cur, "（2）代码与文档清单（全部可复现）：")
        cur = ins_table(doc, cur,
                        ["模块", "文件", "说明"],
                        [["口径规则库", "llm/knowledge/hard_rules.py", "33 条结构化规则"],
                         ["文档检索", "llm/knowledge/retriever.py", "239 段，TF-IDF 字符 n-gram"],
                         ["工具注册与执行", "llm/tools/registry.py｜executor.py", "22 个工具，db/csv 双模式"],
                         ["护栏", "llm/agent/guard.py", "越界拒答、口径拦截、幅度约束"],
                         ["编排与组装", "llm/agent/planner.py｜composer.py", "ReAct 双路径、四段式输出"],
                         ["评测", "llm/eval/runner.py｜questions*.jsonl", "80 题、4 模式消融"],
                         ["接口与页面", "app/llm_api.py｜static/assistant.html", "8 个接口、1 个对话页"]],
                        widths=[3.2, 6.6, 5.6],
                        caption="表 12　主要代码文件")
        cur = ins_para(doc, cur,
                       "（3）复现命令：python -m uvicorn app.main:app --port 8000；"
                       "python scripts/llm_smoke.py（14 项冒烟）；python scripts/run_eval.py（四模式评测）。")


# ---------------------------------------------------------------- 主流程
def main() -> int:
    if not TPL.is_file():
        print("模板不存在：", TPL)
        return 1
    doc = Document(str(TPL))

    fill_cover_table(doc)
    sec_core_tech(doc)
    sec_stage(doc)
    sec_basic(doc)
    sec_background(doc)
    sec_scenarios(doc)
    sec_solution(doc)
    sec_innovation(doc)
    sec_market(doc)
    sec_business(doc)
    sec_application(doc)
    sec_social(doc)
    sec_appendix(doc)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"✅ 已保存：{OUT.relative_to(ROOT)}")

    # 自检
    d2 = Document(str(OUT))
    text = "\n".join(p.text for p in d2.paragraphs)
    print(f"   段落 {len(d2.paragraphs)} 段，表格 {len(d2.tables)} 个，正文字数约 {len(text)} 字")
    for kw in ["一、中小电商有数据", "表 1　六类核心场景", "表 9　消融实验结果", "演示视频", "【"]:
        print(f"   {'✅' if kw in text or any(kw in c.text for t in d2.tables for r in t.rows for c in r.cells) else '❌'} {kw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
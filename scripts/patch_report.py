#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对已填好的申报书做一次定点补丁（不重新套模板，保留截图与二维码，并保留手工填的封面）。

补丁内容：
    1. 附录页面名与接口数改正（经营看板/用户分群/…；41 个接口 = 33 业务 + 8 对话）
    2. 新增「持续学习」一节（表 11 四步闭环 + 一次真实闭环记录）
    3. 新增「语义对齐」三层落地说明（194 个触发词 / 22 个工具 / 239 段语料）
    4. 新增「普惠可及性」成本段（离线 0 API 成本 / 单机配置 / 云主机量级）
    5. 表 11、表 12 顺延为表 12、表 13；视频链接清理并补 1080P 提示

用法：
    python scripts/patch_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from fill_template import ins_para, ins_table  # noqa: E402

DOC = ROOT / "提交材料" / "申报书_模板版.docx"
VIDEO = "https://www.bilibili.com/video/BV1tH4P6ZETk"


def paras(doc):
    return doc.paragraphs


def find(doc, needle):
    for p in doc.paragraphs:
        if needle in p.text:
            return p
    return None


def set_run_text(p, text):
    """只改文字 run，保留图片 run（附录截图段落里图和文在同一个段落）。"""
    for r in p.runs:
        if r._element.findall(".//" + qn("a:blip")):
            continue
        if r.text.strip():
            r.text = text
            return True
    return False


def main() -> int:
    if not DOC.is_file():
        print("找不到：", DOC)
        return 1
    doc = Document(str(DOC))
    done = []

    # 1. 附录：页面名 + 接口数 ------------------------------------------------
    p = find(doc, "系统已实现 7 个可视化页面")
    if p:
        set_run_text(p,
                     "系统已实现 7 个可视化页面（经营看板、用户分群、转化分析、销量预测、选品建议、"
                     "定价建议、模型实验）与 41 个后端接口（33 个业务接口 + 8 个对话接口），均可正常运行。")
        done.append("附录页面名/接口数")

    # 2. 部署段：32 → 33 个业务接口 -------------------------------------------
    p = find(doc, "原有 32 个无参接口")
    if p:
        set_run_text(p, p.text.replace("原有 32 个无参接口", "原有 33 个业务接口"))
        done.append("部署段接口数")

    # 表 5 里也有「32 个接口」
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                if "32 个接口平均响应" in c.text:
                    for para in c.paragraphs:
                        for r in para.runs:
                            r.text = r.text.replace("32 个接口平均响应", "33 个业务接口平均响应")
                    done.append("表 5 接口数")

    # 3. 语义对齐（插在 RAG 段之后） -------------------------------------------
    p = find(doc, "文档侧使用检索增强生成（RAG）")
    if p:
        cur = ins_para(doc, p._p,
                       "语义对齐在本项目分三层落地，不是把文档一股脑塞进向量库：① 指标对齐——33 条口径规则共 "
                       "194 个触发词与别名（平均每条 5.9 个），把「营收／销售额／流水／GMV」这类同义说法收敛到"
                       "唯一指标与唯一定义；② 字段对齐——22 个工具的参数绑定真实表／视图字段，模型只能通过这些"
                       "参数取数，取不到就报错而不是编造；③ 文档对齐——239 段语料按标题切分，回答附来源与命中"
                       "段落，full 模式实测依据覆盖率 90.0%，检索不到时显式写「本次未检索到」。")
        done.append("语义对齐段")

    # 4. 持续学习（插在应用情况末尾，表 10 之后） ------------------------------
    p = find(doc, "货币化的收益取决于真实企业的决策频次")
    if p:
        cur = ins_para(doc, p._p, "（七）持续学习：反馈闭环、规则版本与回归门槛。")
        cur = ins_para(doc, cur,
                       "垂直模型的能力不是训练一次就固定，而是被真实问题不断「顶」出来的。本项目把这一过程做成"
                       "可运行的四步闭环，落点在规则与评测集，而不是参数——人在环上，模型不自动改规则，"
                       "所有变更必须经人工审核并跑回归，避免把错误答案学进去。")
        cur = ins_table(doc, cur,
                        ["步骤", "做什么", "落在哪里", "判据"],
                        [["① 收集", "对话页每条回答下方提供 👍/👎 与「纠正」输入框，无需注册",
                          "feedback.db（问题/回答/模式/判定/纠正/时间）", "单条入库 < 1 秒"],
                         ["② 归并", "每周导出待审清单，人工判定为口径缺失、路由未覆盖、文档缺口或新评测题",
                          "hard_rules.py、questions.jsonl、语料", "每条反馈必须有结论"],
                         ["③ 回归", "规则库带版本号（当前 2026.11.02），改完必跑 80 题四模式评测并与基线比对",
                          "scripts/run_eval.py --gate", "任一维度下降 > 2pt 即回滚"],
                         ["④ 验收", "新能力只在第三套 holdout 上验收，不拿盲测集调参",
                          "新建 20 题 holdout", "盲测结果保持只跑一次"]],
                        widths=[1.8, 7.0, 4.6, 3.0],
                        caption="表 11　持续学习闭环的四步与判据")
        cur = ins_para(doc, cur,
                       "闭环已经真实跑通过一次：首轮盲测 20 题失败 5 题，全部是意图路由未覆盖的问法"
                       "（例如用「被剔掉的那 549 行」而不是「取消订单」），归并出 5 条路由规则后同集重测为 100%。"
                       "由于这等于用测试集调参，该结果不计入对外指标，对外仍报 75%，另建 holdout 复测。"
                       "这套机制的价值在于：下一次出错时，系统知道该把错误沉淀到哪一层——"
                       "是补一条口径、补一个意图、补一段文档，还是补一道评测题——而不是重训一个模型。")
        done.append("持续学习节")

    # 5. 普惠（插在商业模式末尾） ---------------------------------------------
    p = find(doc, "项目目前处于方案验证阶段，尚无商业合同与营业收入")
    if p:
        cur = ins_para(doc, p._p, "（五）普惠的可及性：把成本压到个体商户能承受的量级。")
        cur = ins_para(doc, cur,
                       "离线模式不调用任何付费接口，模型 API 成本为 0；单机 8 GB 内存的普通笔记本即可运行，"
                       "本机实测 33 个业务接口平均响应 0.05 秒、单次问答 43 毫秒；若改用云主机，8 核 16 GB "
                       "约 300～500 元／月（市场价，随配置浮动）；规则库与评测集计划开源，行业包按年订阅，"
                       "单店年费目标控制在千元级，让只有一两个人做运营的小店也用得起，而不是只服务得起"
                       "有数据团队的企业。")
        done.append("普惠段")

    # 6. 附录表号顺延 --------------------------------------------------------
    for old, new in (("表 11\u3000口径硬规则节选", "表 12\u3000口径硬规则节选"),
                     ("表 12\u3000主要代码文件", "表 13\u3000主要代码文件")):
        p = find(doc, old)
        if p:
            set_run_text(p, new)
            done.append(f"{old[:5]}→{new[:5]}")

    # 7. 视频链接与清晰度提示 -------------------------------------------------
    p = find(doc, "bilibili.com/video")
    if p:
        set_run_text(p, VIDEO + "（稿件已通过审核，公开可播）")
        cur = ins_para(doc, p._p,
                       "提示：源文件为 4K，手机端默认可能只给低清晰度，建议登录后手动切到 1080P 再观看；"
                       "二维码见下方，扫码即可。")
        done.append("视频链接/提示")

    doc.save(str(DOC))
    print("已保存：", DOC.relative_to(ROOT))
    print("完成项：")
    for d in done:
        print("  ✅", d)

    # 自检
    d2 = Document(str(DOC))
    text = "\n".join(x.text for x in d2.paragraphs)
    for t in d2.tables:
        for r in t.rows:
            for c in r.cells:
                text += "\n" + c.text
    for kw in ["经营看板", "41 个后端接口", "持续学习", "194 个触发词", "普惠的可及性",
               "表 11　持续学习", "表 12　口径硬规则节选", "表 13　主要代码文件", "1080P"]:
        print(("  ✅ " if kw in text else "  ❌ ") + kw)
    print(f"  段落 {len(d2.paragraphs)}，表格 {len(d2.tables)}，图片 {len(d2.inline_shapes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
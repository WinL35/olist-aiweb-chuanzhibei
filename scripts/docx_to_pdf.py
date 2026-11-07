#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把填好的 docx 转成 PDF（不依赖 Word / LibreOffice）。

路线：python-docx 读取 → 生成受控 HTML → Chrome 无头打印为 PDF。

为什么这么做：
    本机 Word 的 AppleScript 权限被 macOS 拦截（错误 -10004），又没有安装
    LibreOffice，所以无法直接 docx→PDF。Chrome 的 --print-to-pdf 能按 @page
    规则排版，字体、表格、图片、分页都可控，是当前环境下保真度最高的办法。

用法：
    python scripts/docx_to_pdf.py 提交材料/申报书_模板版.docx 提交材料/out.pdf
"""
from __future__ import annotations

import html
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 2.4cm 2.2cm 2.2cm 2.2cm; }
* { box-sizing: border-box; }
body { font-family: "Songti SC", "STSong", serif;
       font-size: 10.5pt; line-height: 1.62; color: #1a1a1a; margin: 0; }
p { margin: 0 0 5pt 0; text-align: justify; text-indent: 2em; }
p.noindent { text-indent: 0; }
p.center { text-align: center; text-indent: 0; }
h1 { font-family: "Heiti SC", "STHeiti", "黑体", sans-serif; font-size: 16pt;
     margin: 0 0 10pt 0; padding-bottom: 4pt; border-bottom: 1.6pt solid #1f6bd0;
     page-break-after: avoid; color: #14203a; margin-top: 20pt;
     padding-top: 10pt; border-top: 0.5pt solid #cdd4dd; }
h1.pb { page-break-before: always; border-top: none; margin-top: 0; padding-top: 0; }
h2 { font-family: "Heiti SC", "STHeiti", "黑体", sans-serif; font-size: 12pt;
     margin: 14pt 0 6pt 0; page-break-after: avoid; color: #1f2a3a; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0 10pt 0; table-layout: fixed;
        font-size: 9pt; page-break-inside: auto; }
th, td { border: 0.6pt solid #8b95a5; padding: 3pt 4pt; vertical-align: top;
         line-height: 1.45; text-align: left; word-wrap: break-word; overflow-wrap: break-word; }
th { background: #1f2a3a; color: #fff; font-weight: normal; text-align: center;
     font-family: "Heiti SC", "STHeiti", sans-serif; letter-spacing: 0.2pt; }
tr { page-break-inside: avoid; }
table.keep { page-break-inside: avoid; }
table.chk { font-size: 9pt; margin: 2pt 0 6pt 0; }
table.chk td { padding: 2pt 4pt; line-height: 1.35; }
img { max-width: 100%; display: block; margin: 6pt auto 4pt auto; }
.cap { text-align: center; font-size: 9pt; color: #5b636e; margin: 2pt 0 10pt 0; text-indent: 0; }
.note { text-align: center; font-size: 9.5pt; color: #c05000; font-weight: bold;
        border: 1pt dashed #e0a060; padding: 8pt; margin: 8pt 0; text-indent: 0; }
.cover { text-align: center; text-indent: 0; }
body.cover-page { page-break-after: always; }
"""


FIRST_H1_DONE = {"v": False}


def esc(s: str) -> str:
    return html.escape(s or "").replace("\u3000", "&emsp;")


def cell_span(cell_tc) -> tuple[int, int]:
    tcPr = cell_tc.find(qn("w:tcPr"))
    span, vmerge = 1, None
    if tcPr is not None:
        gs = tcPr.find(qn("w:gridSpan"))
        if gs is not None:
            span = int(gs.get(qn("w:val")) or 1)
        vm = tcPr.find(qn("w:vMerge"))
        if vm is not None:
            vmerge = vm.get(qn("w:val")) or "continue"
    return span, vmerge


def grid_widths(tbl: Table) -> str:
    """从 docx 的 tblGrid 读列宽，转成 <colgroup>，避免浏览器把列挤成竖排。"""
    grid = tbl._tbl.find(qn("w:tblGrid"))
    if grid is None:
        return ""
    ws = []
    for col in grid.findall(qn("w:gridCol")):
        try:
            ws.append(int(col.get(qn("w:w")) or 0))
        except (TypeError, ValueError):
            ws.append(0)
    total = sum(ws)
    if total <= 0:
        n = max(len(ws), 1)
        ws = [1] * n
        total = n
    cols = "".join(f'<col style="width:{w * 100.0 / total:.2f}%">' for w in ws)
    return f"<colgroup>{cols}</colgroup>"


def render_table(tbl: Table, media: dict[str, str]) -> str:
    rows_html = []
    for ri, row in enumerate(tbl.rows):
        cells = []
        seen_tc = set()
        for cell in row.cells:
            if cell._tc in seen_tc:      # 合并单元格在 row.cells 里会重复出现
                continue
            seen_tc.add(cell._tc)
            span, vmerge = cell_span(cell._tc)
            if vmerge == "continue":
                continue
            tag = "th" if ri == 0 else "td"
            attr = f' colspan="{span}"' if span > 1 else ""
            inner = "".join(
                para_html(p, media, in_cell=True) for p in cell.paragraphs
            ) or "&nbsp;"
            cells.append(f"<{tag}{attr}>{inner}</{tag}>")
        if cells:
            rows_html.append("<tr>" + "".join(cells) + "</tr>")
    cls_parts = []
    if len(rows_html) <= 4:
        cls_parts.append("keep")
    if rows_html and "□" in rows_html[0] or (rows_html and "■" in rows_html[0]):
        cls_parts.append("chk")
    cls = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
    return f"<table{cls}>" + grid_widths(tbl) + "".join(rows_html) + "</table>"


def para_html(p: Paragraph, media: dict[str, str], in_cell=False) -> str:
    if not p.text.strip() and not p._p.findall(".//" + qn("a:blip")):
        return "" if in_cell else "<p>&nbsp;</p>"

    # 图片：同一段落里可能既有图又有文字（附录截图段），不能把文字丢掉
    blips = p._p.findall(".//" + qn("a:blip"))
    img_html = ""
    for blip in blips:
        rid = blip.get(qn("r:embed"))
        if rid and rid in media:
            img_html += f'<img src="{media[rid]}" />'
    if blips and not p.text.strip():
        return img_html

    parts = []
    for run in p.runs:
        t = esc(run.text)
        if not t:
            continue
        if run.bold:
            t = f'<b style="font-family:\'Heiti SC\'">{t}</b>'
        if run.italic:
            t = f"<i>{t}</i>"
        size = run.font.size.pt if run.font.size else None
        if size and abs(size - 10.5) > 0.6:
            t = f'<span style="font-size:{size:.1f}pt">{t}</span>'
        color = run.font.color.rgb if run.font.color and run.font.color.rgb else None
        if color and str(color) not in ("000000", "1A1A1A"):
            t = f'<span style="color:#{color}">{t}</span>'
        parts.append(t)

    if not parts:
        return img_html if img_html else ("" if in_cell else "<p>&nbsp;</p>")
    body = img_html + "".join(parts)

    style = p.style.name
    if in_cell:
        return f'<p class="noindent">{body}</p>'
    if style == "Heading 1":
        cls = ' class="pb"' if not FIRST_H1_DONE.get("v") else ""
        FIRST_H1_DONE["v"] = True
        return f"<h1{cls}>{body}</h1>"
    if style == "Heading 2":
        return f"<h2>{body}</h2>"

    txt = p.text.strip()
    align = p.alignment
    if txt.startswith("【") and ("插入" in txt or "此处" in txt):
        return f'<div class="note">{body}</div>'
    if re.match(r"^(图|表)\s?\d+", txt) and len(txt) < 90:
        return f'<div class="cap">{body}</div>'
    if align is not None and int(align) == 1:
        return f'<p class="center">{body}</p>'
    if txt.startswith(("（", "·", "-", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")):
        if re.match(r"^\d+、|^[（(]\d+[）)]", txt) is None:
            return f'<p class="noindent">{body}</p>'
    return f"<p>{body}</p>"


def build_html(doc: Document, media: dict[str, str]) -> str:
    FIRST_H1_DONE["v"] = False
    body = doc.element.body
    chunks: list[str] = []
    seen_first_h1 = False
    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            cls = ""
            if not seen_first_h1:
                cls = ' class="cover"'   # 封面区（第一个一级标题之前）
            if p.style.name == "Heading 1" and not seen_first_h1:
                seen_first_h1 = True
            h = para_html(p, media)
            if cls and h.startswith("<p"):
                h = h.replace("<p", '<p class="center"', 1)
            elif cls and h.startswith("<div"):
                h = h
            chunks.append(h)
        elif tag == "tbl":
            chunks.append(render_table(Table(child, doc), media))
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>" + "".join(chunks) + "</body></html>")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        print("源文件不存在:", src)
        return 1

    doc = Document(str(src))
    tmp = Path(tempfile.mkdtemp(prefix="docx2pdf_"))
    media: dict[str, str] = {}
    for i, (rid, part) in enumerate(doc.part.related_parts.items()):
        if "image" in getattr(part, "content_type", ""):
            ext = part.content_type.split("/")[-1].replace("jpeg", "jpg")
            fp = tmp / f"img{i}.{ext}"
            fp.write_bytes(part.blob)
            media[rid] = fp.as_uri()

    html_text = build_html(doc, media)
    hp = tmp / "doc.html"
    hp.write_text(html_text, encoding="utf-8")

    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
           f"--user-data-dir={tmp / 'profile'}", "--no-first-run",
           "--no-default-browser-check", "--virtual-time-budget=8000",
           "--run-all-compositor-stages-before-draw",
           "--no-pdf-header-footer", f"--print-to-pdf={out.resolve()}",
           hp.as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.is_file() or out.stat().st_size < 5000:
        print("❌ 导出失败")
        print(r.stdout[-800:], r.stderr[-800:])
        return 1
    print(f"✅ PDF: {out}  {out.stat().st_size/1024:.0f} KB  图片 {len(media)} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 排版引擎（供 build_submission.py 使用）。

为什么自己写排版而不走 Word→PDF：
    本机没有 LibreOffice，无法把 docx 转 PDF；PyMuPDF 可直接生成 PDF，
    并且能精确控制每页每个元素的位置，避免"转格式导致跑版"。
    代价是表格/分页要自己算——本文件就是这部分工作。

中文字体：使用 PyMuPDF 内置 CJK 字体 `china-s`（简体），字体数据随 PDF 嵌出，
不需要系统装字体，评审电脑打开不会缺字。
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

A4_W, A4_H = 595.0, 841.89
M_L, M_R = 56.0, 56.0
M_T, M_B = 58.0, 56.0
BODY = 10.5          # 正文字号
LEAD = 1.62          # 行距倍数
FONT = "china-s"

C_DARK = (0.09, 0.13, 0.20)
C_TXT = (0.16, 0.18, 0.22)
C_GREY = (0.45, 0.48, 0.53)
C_LINE = (0.78, 0.81, 0.86)
C_ACCENT = (0.11, 0.42, 0.78)
C_ACCENT2 = (0.09, 0.60, 0.51)
C_WARN = (0.78, 0.42, 0.08)
C_BG = (0.965, 0.972, 0.982)


def md(s) -> str:
    """去掉 markdown 记号（**加粗** 等），PDF 里不需要。"""
    return str(s).replace("**", "").replace("`", "")


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or \
           (0xFF00 <= o <= 0xFF60) or (0x3000 <= o <= 0x303F)


_WCACHE: dict[tuple[str, float], float] = {}


def _heuristic_w(s: str, fs: float) -> float:
    w = 0.0
    for ch in s:
        if _is_cjk(ch):
            w += fs
        elif ch in "ilj.,:;'|!":
            w += fs * 0.28
        elif ch in "mwMW@%":
            w += fs * 0.86
        else:
            w += fs * 0.52
    return w


def text_width(s: str, fs: float) -> float:
    """文字宽度（点）。

    优先用 MuPDF 自己的度量 `fitz.get_text_length`（与实际渲染一致，
    实测比启发式估算宽约 5%）——早期用启发式估算导致正文溢出页面右边界，
    必须用真实度量。取不到时退回启发式。
    """
    if not s:
        return 0.0
    key = (s, fs)
    hit = _WCACHE.get(key)
    if hit is not None:
        return hit
    w = None
    try:
        w = fitz.get_text_length(s, fontname=FONT, fontsize=fs)
    except Exception:
        w = None
    if w is None or w <= 0:
        w = _heuristic_w(s, fs)
    _WCACHE[key] = w
    return w


_NO_LEAD = "，。、；：！？）」』】·%…,.;:!?)]}"     # 不能出现在行首
_NO_TAIL = "（「『【([{"                              # 不能出现在行尾


def _tokens(s: str) -> list[str]:
    """切分为不可再分的词块：连续的 ASCII 字母数字（含 . , % - + /）算一块。

    这样 99.69%、13,591,643.70、/api/llm/health 不会被拆到两行。
    """
    out, buf = [], ""
    for ch in s:
        if _is_cjk(ch) or ch == " ":
            if buf:
                out.append(buf); buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def wrap(s: str, width: float, fs: float) -> list[str]:
    """按词块换行：中文可断任意处，数字/英文单词整体不拆。"""
    limit = width * 0.985
    hard = width * 1.03          # 为避免标点落行首，允许的轻微超宽
    out, line, cur = [], "", 0.0
    for tok in _tokens(s):
        w = text_width(tok, fs)
        if cur + w <= limit:
            line += tok; cur += w
            continue
        # 行首禁则：标点跟着上一行走（轻微超宽可接受）
        if tok and tok[0] in _NO_LEAD and line and cur + w <= hard:
            line += tok; cur += w
            continue
        # 行尾禁则：开括号不留在行尾
        if line and line[-1] in _NO_TAIL:
            out.append(line[:-1])
            line, cur = line[-1] + tok, text_width(line[-1], fs) + w
            continue
        if line:
            out.append(line)
            line, cur = "", 0.0
        if tok == " ":
            continue
        # 单个词块比整行还宽 → 只能按字符硬切
        if w > width:
            for ch in tok:
                cw = text_width(ch, fs)
                if cur + cw > limit and line:
                    out.append(line); line, cur = "", 0.0
                line += ch; cur += cw
        else:
            line, cur = tok, w
    if line.strip():
        out.append(line)
    return out or [""]


class Doc:
    """顺序排版：cursor 向下推进，超页自动翻页。"""

    def __init__(self, footer: str = "", header: str = ""):
        self.doc = fitz.open()
        self.footer = footer
        self.header = header
        self.page = None
        self.y = 0.0
        self.page_no = 0
        self.marks: dict[str, int] = {}   # 章节标题 → 页码（供目录用）
        self._new_page(first=True)

    # ---------------- 页面 ----------------
    def _new_page(self, first: bool = False):
        self.page = self.doc.new_page(width=A4_W, height=A4_H)
        self.page_no += 1
        self.y = M_T
        if first:
            return
        # 页眉：细线 + 作品名
        if self.header:
            self.page.insert_text((M_L, 34), self.header, fontsize=7.6,
                                  fontname=FONT, color=C_GREY)
            self.page.draw_line(fitz.Point(M_L, 40), fitz.Point(A4_W - M_R, 40),
                                color=C_LINE, width=0.6)
        # 页脚：页码
        self.page.draw_line(fitz.Point(M_L, A4_H - 42), fitz.Point(A4_W - M_R, A4_H - 42),
                            color=C_LINE, width=0.6)
        label = f"— {self.page_no} —"
        self.page.insert_text(((A4_W - text_width(label, 8)) / 2, A4_H - 30), label,
                              fontsize=8, fontname=FONT, color=C_GREY)
        if self.footer:
            self.page.insert_text((M_L, A4_H - 30), self.footer, fontsize=7.6,
                                  fontname=FONT, color=C_GREY)

    def space(self, h: float):
        self.y += h

    def need(self, h: float):
        if self.y + h > A4_H - M_B:
            self._new_page()

    def page_break(self):
        self._new_page()

    # ---------------- 文本 ----------------
    def _put(self, s: str, fs: float, color, x: float, align: str = "left",
             bold_shift: float = 0.0):
        w = text_width(s, fs)
        if align == "center":
            x = M_L + (A4_W - M_L - M_R - w) / 2
        elif align == "right":
            x = A4_W - M_R - w
        self.page.insert_text((x, self.y + fs), s, fontsize=fs, fontname=FONT, color=color)
        if bold_shift:
            # 伪加粗：同一行偏移重绘一次
            self.page.insert_text((x + bold_shift, self.y + fs), s, fontsize=fs,
                                  fontname=FONT, color=color, render_mode=2,
                                  border_width=0.32)

    def para(self, text: str, fs: float = BODY, color=C_TXT, indent: float = 0.0,
             gap: float = 5.0, lead: float = LEAD, bold: bool = False, align="left"):
        width = A4_W - M_L - M_R - indent
        for seg in md(text).split("\n"):
            lines = wrap(seg, width, fs)
            for ln in lines:
                self.need(fs * lead)
                self._put(ln, fs, color, M_L + indent, align, 0.28 if bold else 0.0)
                self.y += fs * lead
            self.y += 1.0
        self.y += gap

    def h1(self, num: str, title: str):
        """一级标题：带色块 + 细线，强制从新页开始。"""
        self._new_page()
        self.marks[title] = self.page_no
        self.marks[f"{num} {title}"] = self.page_no
        self.page.draw_rect(fitz.Rect(M_L, self.y, M_L + 5, self.y + 26),
                            color=None, fill=C_ACCENT)
        self.page.insert_text((M_L + 14, self.y + 19), num, fontsize=17,
                              fontname=FONT, color=C_ACCENT)
        self.page.insert_text((M_L + 14 + text_width(num, 17) + 8, self.y + 19),
                              title, fontsize=15.5, fontname=FONT, color=C_DARK,
                              render_mode=2, border_width=0.35)
        self.y += 30
        self.page.draw_line(fitz.Point(M_L, self.y), fitz.Point(A4_W - M_R, self.y),
                            color=C_ACCENT, width=1.1)
        self.y += 16

    def h2(self, num: str, title: str):
        self.need(46)
        self.marks[f"{num} {title}"] = self.page_no
        self.y += 6
        self.page.insert_text((M_L, self.y + 12), f"{num}  {title}", fontsize=11.6,
                              fontname=FONT, color=C_DARK,
                              render_mode=2, border_width=0.3)
        self.y += 18
        self.page.draw_line(fitz.Point(M_L, self.y), fitz.Point(M_L + 46, self.y),
                            color=C_ACCENT2, width=1.6)
        self.y += 9

    def h3(self, title: str):
        self.need(30)
        self.y += 3
        self.page.insert_text((M_L, self.y + 10), "▍" + title, fontsize=10.4,
                              fontname=FONT, color=C_ACCENT)
        self.y += 16

    def bullet(self, items: list[str] | str, fs: float = BODY, marker: str = "•",
               color=C_TXT, gap: float = 2.4):
        if isinstance(items, str):
            items = [items]
        items = [md(x) for x in items]
        for it in items:
            width = A4_W - M_L - M_R - 15
            lines = wrap(it, width, fs)
            for i, ln in enumerate(lines):
                self.need(fs * LEAD)
                if i == 0:
                    self.page.insert_text((M_L + 2, self.y + fs), marker, fontsize=fs,
                                          fontname=FONT, color=C_ACCENT)
                self.page.insert_text((M_L + 15, self.y + fs), ln, fontsize=fs,
                                      fontname=FONT, color=color)
                self.y += fs * LEAD
            self.y += gap
        self.y += 2

    # ---------------- 表格 ----------------
    def table(self, headers: list[str], rows: list[list], widths: list[float],
              fs: float = 8.6, head_fill=C_DARK, head_color=(1, 1, 1),
              zebra=True, align_right: list[bool] | None = None, caption: str = ""):
        total = sum(widths)
        avail = A4_W - M_L - M_R
        widths = [w / total * avail for w in widths]
        pad = 4.0
        align_right = align_right or [False] * len(headers)

        def row_h(cells, size):
            n = 1
            for c, w in zip(cells, widths):
                n = max(n, len(wrap(md(c), w - pad * 2, size)))
            return n * size * 1.42 + pad * 1.6

        # 表头（可能重复）
        def draw_head():
            h = row_h(headers, fs)
            self.need(h + 30)
            x = M_L
            self.page.draw_rect(fitz.Rect(M_L, self.y, A4_W - M_R, self.y + h),
                                color=None, fill=head_fill)
            for c, w, r in zip(headers, widths, align_right):
                lines = wrap(md(c), w - pad * 2, fs)
                ty = self.y + pad * 0.8 + fs
                for ln in lines:
                    tw = text_width(ln, fs)
                    tx = x + (w - tw - pad if r else pad)
                    self.page.insert_text((tx, ty), ln, fontsize=fs, fontname=FONT,
                                          color=head_color)
                    ty += fs * 1.42
                x += w
            self.y += h

        if caption:
            self.need(20)
            self.page.insert_text((M_L, self.y + 9), caption, fontsize=8.8,
                                  fontname=FONT, color=C_GREY)
            self.y += 14

        draw_head()
        for i, row in enumerate(rows):
            h = row_h(row, fs)
            if self.y + h > A4_H - M_B:
                self._new_page()
                draw_head()
            if zebra and i % 2 == 1:
                self.page.draw_rect(fitz.Rect(M_L, self.y, A4_W - M_R, self.y + h),
                                    color=None, fill=C_BG)
            x = M_L
            for c, w, r in zip(row, widths, align_right):
                lines = wrap(md(c), w - pad * 2, fs)
                ty = self.y + pad * 0.8 + fs
                for ln in lines:
                    tw = text_width(ln, fs)
                    tx = x + (w - tw - pad if r else pad)
                    self.page.insert_text((tx, ty), ln, fontsize=fs, fontname=FONT,
                                          color=C_TXT)
                    ty += fs * 1.42
                x += w
            self.page.draw_line(fitz.Point(M_L, self.y + h),
                                fitz.Point(A4_W - M_R, self.y + h),
                                color=C_LINE, width=0.5)
            self.y += h
        self.y += 8

    # ---------------- 图片 ----------------
    def image(self, path: str | Path, width: float = 0, caption: str = "",
              gap: float = 8.0):
        path = str(path)
        try:
            pix = fitz.Pixmap(path)
            iw, ih = pix.width, pix.height
            pix = None
        except Exception:
            return
        avail = A4_W - M_L - M_R
        w = width or avail
        w = min(w, avail)
        h = w * ih / iw
        if self.y + h + (16 if caption else 0) > A4_H - M_B:
            self._new_page()
        x = M_L + (avail - w) / 2
        self.page.insert_image(fitz.Rect(x, self.y, x + w, self.y + h), filename=path)
        self.y += h + 4
        if caption:
            cap_lines = wrap(md(caption), A4_W - M_L - M_R, 8.4)
            self.y += 9
            for ln in cap_lines:
                self.page.insert_text((M_L, self.y + 3), ln, fontsize=8.4,
                                      fontname=FONT, color=C_GREY)
                self.y += 12
            self.y += 2
        self.y += gap

    # ---------------- 提示框 ----------------
    def callout(self, title: str, body: str, color=C_ACCENT, fs: float = 9.4):
        body_lines = wrap(md(body), A4_W - M_L - M_R - 26, fs)
        h = 22 + len(body_lines) * fs * 1.5 + 8
        if self.y + h > A4_H - M_B:
            self._new_page()
        rect = fitz.Rect(M_L, self.y, A4_W - M_R, self.y + h)
        self.page.draw_rect(rect, color=color, fill=(0.97, 0.98, 1.0) if color == C_ACCENT
                            else (1.0, 0.98, 0.94), width=0.8)
        self.page.draw_rect(fitz.Rect(M_L, self.y, M_L + 3.2, self.y + h),
                            color=None, fill=color)
        title = md(title)
        self.page.insert_text((M_L + 14, self.y + 15), title, fontsize=fs + 0.6,
                              fontname=FONT, color=color,
                              render_mode=2, border_width=0.3)
        ty = self.y + 32
        for ln in body_lines:
            self.page.insert_text((M_L + 14, ty), ln, fontsize=fs, fontname=FONT, color=C_TXT)
            ty += fs * 1.5
        self.y += h + 10

    def code(self, text: str, fs: float = 8.2, fill=(0.955, 0.96, 0.97), gap: float = 8.0):
        lines = text.split("\n")
        maxw = A4_W - M_L - M_R - 20
        # 折行
        flat = []
        for ln in lines:
            flat.extend(wrap(ln, maxw, fs) if ln else [""])
        h = len(flat) * fs * 1.5 + 14
        if self.y + h > A4_H - M_B:
            self._new_page()
        self.page.draw_rect(fitz.Rect(M_L, self.y, A4_W - M_R, self.y + h),
                            color=C_LINE, fill=fill, width=0.6)
        ty = self.y + fs + 6
        for ln in flat:
            self.page.insert_text((M_L + 10, ty), ln, fontsize=fs, fontname=FONT, color=(0.2, 0.24, 0.3))
            ty += fs * 1.5
        self.y += h + gap

    def placeholder(self, label: str, hint: str, h: float = 96.0):
        """截图/二维码占位框（虚线），提交前替换。"""
        if self.y + h > A4_H - M_B:
            self._new_page()
        rect = fitz.Rect(M_L + 40, self.y, A4_W - M_R - 40, self.y + h)
        self.page.draw_rect(rect, color=C_WARN, width=1.0, dashes="[3 3] 0")
        cx = (rect.x0 + rect.x1) / 2
        self.page.insert_text((cx - text_width(label, 10.4) / 2, rect.y0 + h / 2 - 4),
                              label, fontsize=10.4, fontname=FONT, color=C_WARN)
        for i, ln in enumerate(wrap(hint, rect.width - 24, 8.2)[:2]):
            self.page.insert_text((cx - text_width(ln, 8.2) / 2, rect.y0 + h / 2 + 14 + i * 12),
                                  ln, fontsize=8.2, fontname=FONT, color=C_GREY)
        self.y += h + 8

    def save(self, path: str | Path):
        self.doc.save(str(path), garbage=4, deflate=True)
        n = self.doc.page_count
        self.doc.close()
        return n
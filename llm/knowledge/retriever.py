# -*- coding: utf-8 -*-
"""行业文档检索（RAG 的 R）

为什么不用向量库
----------------
1. 本项目语料只有 6 份 markdown（约 90 KB），TF-IDF 的召回已经够用；
2. 无需联网下载 embedding 模型，答辩现场断网也能跑；
3. 可解释：能给出「命中哪个文件的哪一节」，评委可以现场核对原文。

真实生产环境可替换为 bge-m3 + 向量库，接口保持一致（retrieve 签名不变）。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from llm import config

BASE = Path(__file__).resolve().parent.parent.parent
DOC_DIR = BASE / "文档"
EXTRA_DIR = Path(__file__).resolve().parent / "corpus"

# 参与检索的文档（按重要性排序，越前越优先被引用）
DOC_FILES = [
    "口径手册.md",
    "算法2_算法文档.md",
    "数据集说明.md",
    "项目文档.md",
    "数据库设计文档.md",
    "算法1_算法文档.md",
    "验收记录.md",
]

_HEAD = re.compile(r"^(#{1,6})\s*(.+)$", re.M)


def _read_docs() -> list[tuple[str, str]]:
    """读取文档，返回 [(文件名, 全文)]。"""
    out: list[tuple[str, str]] = []
    for name in DOC_FILES:
        for d in (EXTRA_DIR, DOC_DIR):
            p = d / name
            if p.is_file():
                try:
                    out.append((name, p.read_text(encoding="utf-8", errors="ignore")))
                except Exception:
                    pass
                break
    return out


def _chunk(text: str, name: str, max_len: int = 420, overlap: int = 80) -> list[dict]:
    """按 markdown 标题切块，过长再滑窗切分。

    按标题切而不是按固定长度切，是为了让每个片段自带「这一节讲什么」的
    上下文，检索命中后可以直接当答案依据引用。
    """
    chunks: list[dict] = []
    marks = [(m.start(), m.group(2).strip()) for m in _HEAD.finditer(text)]
    if not marks:
        marks = [(0, name)]

    for i, (start, heading) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[start:end].strip()
        # 去掉 markdown 表格分隔符等噪声，但保留内容
        body = re.sub(r"\n{3,}", "\n\n", body)
        if len(body) < 20:
            continue
        if len(body) <= max_len:
            chunks.append({"text": body, "source": name, "heading": heading})
            continue
        step = max_len - overlap
        for s in range(0, len(body), step):
            piece = body[s:s + max_len].strip()
            if len(piece) >= 40:
                chunks.append({"text": piece, "source": name, "heading": heading})
            if s + max_len >= len(body):
                break
    return chunks


@lru_cache(maxsize=1)
def _index():
    """构建 TF-IDF 索引（进程内缓存，首次检索约 0.3 秒）。"""
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = _read_docs()
    chunks: list[dict] = []
    for name, text in docs:
        chunks.extend(_chunk(text, name))
    if not chunks:
        return None, []

    # 中文用字符 2-4 gram：无需分词词典，对专业术语（如「价格弹性」「阻尼 Holt」）更稳
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                          min_df=1, sublinear_tf=True)
    matrix = vec.fit_transform([c["text"] for c in chunks])
    return (vec, matrix), chunks


def stats() -> dict:
    idx, chunks = _index()
    if idx is None:
        return {"docs": 0, "chunks": 0, "ready": False}
    sources = sorted({c["source"] for c in chunks})
    return {"docs": len(sources), "chunks": len(chunks),
            "ready": True, "files": sources}


def retrieve(query: str, top_k: int | None = None,
             min_score: float | None = None) -> list[dict]:
    """检索最相关的文档片段。

    返回 [{text, source, heading, score}]，按相关度降序。
    检索不到任何片段时返回空列表——调用方应据此降级为「仅用硬规则」，
    而不是编造一段依据。
    """
    top_k = top_k or config.RAG_TOP_K
    min_score = config.RAG_MIN_SCORE if min_score is None else min_score
    if not query or not query.strip():
        return []

    idx, chunks = _index()
    if idx is None:
        return []
    vec, matrix = idx

    # 查询侧也用同样的 char ngram
    q = vec.transform([query])
    scores = (matrix @ q.T).toarray().ravel()

    order = scores.argsort()[::-1]
    out: list[dict] = []
    seen: set[str] = set()
    for i in order:
        s = float(scores[i])
        if s < min_score or len(out) >= top_k:
            break
        c = chunks[i]
        # 同一文件的同一节只保留一次（避免依据列表重复）
        key = f"{c['source']}::{c['heading']}"
        if key in seen or c["text"][:60] in seen:
            continue
        seen.add(key)
        seen.add(c["text"][:60])
        out.append({"text": c["text"], "source": c["source"],
                    "heading": c["heading"], "score": round(s, 4)})
    return out


def as_prompt_block(snippets: list[dict], max_chars: int = 1800) -> str:
    """把检索结果渲染成可注入 prompt 的文本（带出处，便于溯源）。"""
    if not snippets:
        return ""
    parts, used = [], 0
    for s in snippets:
        body = s["text"]
        if used + len(body) > max_chars:
            body = body[:max(0, max_chars - used)]
        if not body:
            break
        parts.append(f"《{s['source']}》§{s['heading']}\n{body}")
        used += len(body)
    return "\n\n---\n\n".join(parts)
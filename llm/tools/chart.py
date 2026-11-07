# -*- coding: utf-8 -*-
"""把工具返回的真实数据确定性转换为 ECharts option。

为什么这里是纯函数、不联网、不查库
------------------------------------
图表的所有数据都来自「本轮已经被调用的查询工具」的真实返回（executor 的
本轮上下文）。模型只能决定 **画什么**（图型、字段、标题），**不允许提供画多少**。
这从机制上杜绝了图表幻觉：数字若有错，一定是查询工具的错，可追、可测、可回归。
"""
from __future__ import annotations

from typing import Any

CHART_TYPES = ("line", "bar", "pie", "scatter", "funnel")

# 常见「记录数组」字段名，按出现概率排序
_RECORD_KEYS = ("data", "future", "history", "categories", "segments",
                "steps", "by_type", "items", "rows", "list")


class ChartError(RuntimeError):
    """图表构建失败（数据缺失 / 字段不存在 / 图型不支持）。"""


def _find_records(payload: Any) -> list[dict] | None:
    """从工具结果里提取「记录数组」（list[dict]）。找不到返回 None。"""
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload
    if not isinstance(payload, dict):
        return None
    # 1) 常见键优先
    for key in _RECORD_KEYS:
        v = payload.get(key)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    # 2) 兜底：第一个长得像记录数组的字段
    for v in payload.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    return None


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, 4)   # 过滤 NaN


def build_option(chart_type: str, records: list[dict], x_field: str,
                 y_fields: list[str], title: str = "", note: str = "") -> dict:
    """把记录数组转换为 ECharts option。失败抛 ChartError。"""
    chart_type = (chart_type or "").lower().strip()
    if chart_type not in CHART_TYPES:
        raise ChartError(
            f"不支持的图型「{chart_type}」。支持：{', '.join(CHART_TYPES)}")
    if not records:
        raise ChartError("无可用数据，无法出图。")
    y_fields = [y for y in (y_fields or []) if y]
    if not x_field or not y_fields:
        raise ChartError("必须提供 x_field（维度字段）与 y_fields（数值字段）。")

    # 校验字段存在，避免画出空图
    probe = records[0]
    if x_field not in probe:
        avail = ", ".join(sorted(probe.keys()))
        raise ChartError(f"x_field「{x_field}」不在数据里。可用字段：{avail}")
    missing = [y for y in y_fields if y not in probe]
    if missing:
        avail = ", ".join(sorted(probe.keys()))
        raise ChartError(f"y_fields {missing} 不在数据里。可用字段：{avail}")

    xs = [str(r.get(x_field, "")) for r in records]
    base_title = {"text": title, "left": "center",
                  "textStyle": {"fontSize": 14, "fontWeight": 500}}
    if note:
        base_title["subtext"] = note
        base_title["subtextStyle"] = {"fontSize": 11}

    if chart_type == "pie":
        yf = y_fields[0]
        option = {
            "title": base_title,
            "tooltip": {"trigger": "item",
                        "formatter": "{b}<br/>{c}（{d}%）"},
            "legend": {"type": "scroll", "bottom": 0},
            "series": [{
                "type": "pie", "radius": ["35%", "62%"], "center": ["50%", "52%"],
                "data": [{"name": x, "value": _num(r.get(yf))}
                         for x, r in zip(xs, records)],
                "label": {"formatter": "{b}"},
            }],
        }
    elif chart_type == "funnel":
        yf = y_fields[0]
        option = {
            "title": base_title,
            "tooltip": {"trigger": "item", "formatter": "{b}：{c}"},
            "series": [{
                "type": "funnel", "sort": "descending",
                "left": "12%", "right": "12%", "top": 60, "bottom": 20,
                "data": [{"name": x, "value": _num(r.get(yf))}
                         for x, r in zip(xs, records)],
                "label": {"show": True, "formatter": "{b}：{c}"},
            }],
        }
    elif chart_type == "scatter":
        yf = y_fields[0]
        option = {
            "title": base_title,
            "tooltip": {"trigger": "item",
                        "formatter": x_field + "：{@[0]}<br/>" + yf + "：{@[1]}"},
            "xAxis": {"type": "value", "name": x_field},
            "yAxis": {"type": "value", "name": yf},
            "series": [{
                "type": "scatter",
                "data": [[_num(r.get(x_field)), _num(r.get(yf))] for r in records],
            }],
        }
    else:  # line / bar
        option = {
            "title": base_title,
            "tooltip": {"trigger": "axis"},
            "legend": {"type": "scroll", "bottom": 0} if len(y_fields) > 1
                      else {"show": False},
            "xAxis": {"type": "category", "data": xs,
                      "axisLabel": {"interval": 0, "rotate": 30 if len(xs) > 8 else 0}},
            "yAxis": {"type": "value"},
            "series": [{"name": yf, "type": chart_type, "smooth": chart_type == "line",
                        "data": [_num(r.get(yf)) for r in records]}
                       for yf in y_fields],
        }
    return option

"""Number formatting and server-side SVG used by pages and the offline report (same functions → same look,
AC-F12-03)."""

from __future__ import annotations

import math
from html import escape
from typing import Any

from markupsafe import Markup

NO_DATA = "无数据"


def is_none(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def pct(v: Any, digits: int = 1, signed: bool = False) -> str:
    if is_none(v):
        return NO_DATA
    s = f"{v * 100:.{digits}f}%"
    return ("+" + s) if signed and v > 0 else s


def pct0(v: Any) -> str:
    return NO_DATA if is_none(v) else f"{round(v * 100):.0f}%"


def num(v: Any, digits: int = 0) -> str:
    if is_none(v):
        return NO_DATA
    return f"{v:,.{digits}f}"


def money(v: Any) -> str:
    return NO_DATA if is_none(v) else f"${v:,.0f}"


def mult(v: Any) -> str:
    return NO_DATA if is_none(v) else f"{v:.2f}×"


def ci_text(ci: Any, digits: int = 0) -> str:
    if not ci or is_none(ci[0]) or is_none(ci[1]):
        return NO_DATA
    return f"{ci[0] * 100:.{digits}f}–{ci[1] * 100:.{digits}f}%"


def pp(v: Any) -> str:
    return NO_DATA if is_none(v) else f"{v:+.1f} 个百分点"


SCALE_MAX = 0.60  # interval bars: 0–60 % on 160 px (prototype geometry)


def _x(v: float, width: int = 160, scale: float = SCALE_MAX) -> float:
    return round(max(0.0, min(1.0, v / scale)) * width, 1)


def ibar(point: Any, ci: Any, avg: Any, n: Any = None, grey: bool = False, label: str = "预期命中率",
         avg_label: str = "全类目平均", tip: bool = True, standalone: bool = False) -> Markup:
    """Interval bar: band = 90 % interval, dot = point estimate, vertical line = category average."""
    if is_none(point) or not ci or is_none(ci[0]):
        return Markup(f'<span class="etag etag--nodata">{NO_DATA}</span>')
    lo, hi = ci
    band_x, band_w = _x(lo), max(1.0, round(_x(hi) - _x(lo), 1))
    parts = ['<line class="ibar__track" x1="0" y1="10" x2="160" y2="10"/>',
             f'<rect class="ibar__band" x="{band_x}" y="7" width="{band_w}" height="6" rx="3"/>']
    if not is_none(avg):
        ax = _x(avg)
        parts.append(f'<line class="ibar__avg" x1="{ax}" y1="3" x2="{ax}" y2="17"/>')
    over = hi > SCALE_MAX
    if over and _x(point) < 149:  # fixed 0–60 % scale (prototype geometry): an arrow marks a band running past it
        parts.append('<path class="ibar__over" d="M154 6 L160 10 L154 14 Z"/>')
    parts.append(f'<circle class="ibar__dot" cx="{_x(point)}" cy="10" r="4"/>')
    desc = f"{label} {pct0(point)}，90% 区间 {ci_text(ci)}"
    if over:
        desc += "（上限超出 60% 刻度）"
    if n is not None:
        desc += f"，样本 {n}"
    if not is_none(avg):
        desc += f"；竖线为{avg_label} {pct(avg)}"
    title = f"<title>{escape(desc)}</title>" if standalone else ""
    svg = (f'<svg width="160" height="20" viewBox="0 0 160 20" {"role=img" if standalone else "aria-hidden=true"}'
           f' aria-label="{escape(desc)}">{title}{"".join(parts)}</svg>')
    cls = "ibar ibar--grey" if grey else "ibar"
    data_tip = ""
    if tip and not standalone:
        line2 = f"90% 区间 {ci_text(ci)}" + (f" · 样本 {n}" if n is not None else "") + (" · 上限超出 60% 刻度" if over else "")
        line3 = f"竖线：{avg_label} {pct(avg)}" if not is_none(avg) else ""
        data_tip = f' tabindex="0" data-tip="{escape(pct0(point))}|{escape(line2)}|{escape(line3)}" aria-label="{escape(desc)}"'
    return Markup(f'<span class="{cls}"{data_tip}>{svg}</span>')


def etag(text: str, kind: str = "n", pop: dict[str, Any] | None = None, title: str | None = None) -> Markup:
    cls = f"etag etag--{kind}" if kind else "etag"
    if pop:
        data = ";".join(f"{escape(str(k))}={escape(str(v))}" for k, v in pop.items())
        return Markup(f'<button class="{cls}" type="button" data-pop-title="{escape(title or text)}" '
                      f'data-pop="{data}">{escape(text)}</button>')
    return Markup(f'<span class="{cls}">{escape(text)}</span>')


ACTION_BADGE = {"立项候选": ("hit", "flag"), "观察": ("watch", "eye"), "放弃": ("miss", "prohibit")}
STATUS_BADGE = {
    "命中": ("hit", "check-circle"), "未命中": ("miss", "minus"), "观察中": ("watch", "hourglass"),
    "数据不全": ("incomplete", "warning"), "截面命中": ("cross", "intersect"), "截面未命中": ("miss", "minus"),
    "老品": ("old", "archive"), "已验证": ("pass", "seal-check"), "历史观察": ("", "clock-counter-clockwise"),
    "未验证经验": ("unverified", "seal-question"), "已达标": ("pass", "seal-check"), "达标": ("pass", "seal-check"),
    "达标（截面）": ("cross", "intersect"), "未验证": ("unverified", "warning"), "未达标": ("warn", "warning"),
    "样本不足": ("insufficient", "info"), "需重算": ("stale", "arrows-clockwise"), "通过": ("pass", "check-circle"),
    "有警告": ("warn", "warning"), "阻断": ("block", "warning-octagon"), "预警": ("warn", "warning"),
    "已知晓": ("ack", "check"), "正常": ("ok", "check-circle"), "不适用": ("nodata", "minus"),
    "疑似重新上架": ("warn", "clock-counter-clockwise"), "已确认": ("", "check"), "待确认": ("warn", "seal-question"),
    "补录": ("", "clock-counter-clockwise"), "更正": ("", "arrows-clockwise"), "已更正": ("old", "arrows-clockwise"),
    "记录": ("", "note-pencil"), "立项": ("", "flag"), "不立项": ("", "prohibit"), "截面": ("cross", "intersect"),
    "未到期": ("watch", "hourglass"), "已对账": ("ok", "seal-check"), "不用于对账": ("old", "prohibit"),
    "达成": ("hit", "check-circle"), "成功": ("ok", "check-circle"), "失败": ("block", "x-circle"),
    "进行中": ("watch", "hourglass"), "已拒绝": ("old", "x-circle"), "待审": ("warn", "hourglass"),
    "当前": ("", "target"), "本月新增": ("", "plus"),
}


def icon(name: str, extra: str = "") -> Markup:
    return Markup(f'<svg class="icon{(" " + extra) if extra else ""}" aria-hidden="true"><use href="#ph-{name}"/></svg>')


def badge(text: str, kind: str | None = None, icon_name: str | None = None) -> Markup:
    k, ic = ACTION_BADGE.get(text) or STATUS_BADGE.get(text) or ("", "info")
    k = kind if kind is not None else k
    ic = icon_name or ic
    cls = f"badge badge--{k}" if k else "badge"
    return Markup(f'<span class="{cls}">{icon(ic)}{escape(text)}</span>')


def segname(name: str) -> Markup:
    parts = name.replace("|", " · ").split(" · ")
    inner = "".join(f"<span>{escape(p)}</span>" for p in parts)
    return Markup(f'<span class="segname">{inner}</span>')


def hbar_width(rate: Any, scale: float = 0.5) -> float:
    if is_none(rate):
        return 0.0
    return round(min(1.0, rate / scale) * 100, 1)

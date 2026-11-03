"""品类配置（PAGE-F27-01，API-F27-01；AC-F27-01～03）。仅操作者可用；第一版只有浴室柜，不提供新建品类入口。"""
import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .. import catconfig
from ..config import CATEGORY, CHANNEL_NAMES
from ..db import session
from ..models import Snapshot, Tag, User
from ..models_settings import ConfigNote
from ..auth import operator_only
from .ui import redirect, render

router = APIRouter()

METHODS = {"review": "评论换算", "rank": "榜单排名平滑"}
MIN_FIT = 10  # 拟合商品少于 10 个时不提供榜单排名平滑（AC-F28-04）
FIELD_NAMES = {
    "low_conf_threshold": "低置信度阈值", "vp_coef": "VP 系数", "nonvp_coef": "非 VP 系数", "method": "估算方法",
    "bsr_top": "成功线 · 小类 BSR 名次", "spu_revenue": "成功线 · SPU 月销售额", "rank_top": "成功线 · 榜单名次",
    "units": "成功线 · 估算月销", "scan": "参与扫描", "values": "取值", "tag_rules": "打标规则", "frame_dims": "分框维度",
    "scan_attrs": "扫描属性", "budget_warn_pct": "接近上限提示比例", "min_frame_units": "框最小月销",
    "min_value_units": "属性值最小月销", "verify": "Amazon 核对阈值",
}


def label(path: str, cfg: dict) -> str:
    """把配置路径变成中文名，例：channels.lowes.nonvp_coef → Lowe's 非 VP 系数。"""
    p = path.split(".")
    if p[0] == "channels" and len(p) >= 3:
        return f"{CHANNEL_NAMES.get(p[1], p[1])} {FIELD_NAMES.get(p[-1], p[-1])}"
    if p[0] in ("frame_dims", "scan_attrs") and len(p) >= 3 and p[1].isdigit():
        lst = cfg.get(p[0]) or []
        i = int(p[1])
        name = (lst[i].get("dim") or lst[i].get("attr")) if i < len(lst) else p[1]
        return f"{FIELD_NAMES[p[0]]} · {name} {FIELD_NAMES.get(p[2], p[2])}"
    if p[0] == "tag_rules":
        return "打标规则" + (f" · {p[1]}" if len(p) > 1 else "")
    return " · ".join(FIELD_NAMES.get(x, x) for x in p)


def _fmt(v):
    if v is None:
        return "（无）"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and v in METHODS:
        return METHODS[v]
    return str(v)


def _diff_rows(diff: list, cfg: dict):
    return [dict(path=d["path"], label=label(d["path"], cfg), old=_fmt(d["old"]), new=_fmt(d["new"])) for d in diff]


def validate(new: dict) -> str:
    """返回错误信息；空字符串表示通过。"""
    if new.get("category") != CATEGORY:
        return "第一版只开浴室柜，不能修改或新建品类"
    try:
        thr = float(new.get("low_conf_threshold"))
    except (TypeError, ValueError):
        return "低置信度阈值需在 0.50–0.95 之间"
    if not 0.5 - 1e-9 <= thr <= 0.95 + 1e-9:
        return "低置信度阈值需在 0.50–0.95 之间"
    for ch, c in (new.get("channels") or {}).items():
        name = CHANNEL_NAMES.get(ch, ch)
        for k in ("vp_coef", "nonvp_coef"):
            if k in c and not _pos(c[k]):
                return f"{name} {FIELD_NAMES[k]}：请填正数"
        if "method" in c and c["method"] not in METHODS:
            return f"{name} 估算方法只能是评论换算或榜单排名平滑"
        for k, v in (c.get("success") or {}).items():
            if not _pos(v):
                return f"{name} {FIELD_NAMES.get(k, k)}：请填正数"
    for d in new.get("frame_dims") or []:
        if not d.get("values"):
            return f"分框维度 {d.get('dim')} 至少要有一个取值"
    if not isinstance(new.get("tag_rules", {}), dict):
        return "打标规则需为 JSON 对象"
    return ""


def _pos(v) -> bool:
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def fit_counts() -> dict:
    """各其他渠道可用于拟合排名—销量曲线的商品数（同时有榜单名次和评论换算销量）。"""
    with session() as s:
        rows = s.execute(select(Snapshot.channel, func.count(func.distinct(Snapshot.item_id)))
                         .where(Snapshot.rank.is_not(None), Snapshot.units.is_not(None), Snapshot.channel != "amazon")
                         .group_by(Snapshot.channel)).all()
    return {ch: n for ch, n in rows}


def _tag_values() -> dict:
    with session() as s:
        rows = s.execute(select(Tag.tag, Tag.value, func.count()).where(Tag.value != "").group_by(Tag.tag, Tag.value)
                         .order_by(func.count().desc())).all()
    out = {}
    for tag, val, _ in rows:
        for v in val.split("|"):
            if v and v not in out.setdefault(tag, []):
                out[tag].append(v)
    return out


def _queue_count(thr: float) -> int:
    with session() as s:
        return s.scalar(select(func.count()).select_from(Tag).where(Tag.status != "confirmed", Tag.source != "manual",
                                                                     (Tag.confidence < thr) | (Tag.tag == "元素"))) or 0


def _history(cfg: dict):
    with session() as s:
        notes = {n.version: n.note for n in s.scalars(select(ConfigNote))}
        names = {u.id: u.name for u in s.scalars(select(User))}
    out = []
    for h in catconfig.history():
        out.append(dict(version=h["version"], at=h["at"], by=names.get(h["by"], "系统默认" if h["by"] is None else "—"),
                        note=notes.get(h["version"], "浴室柜初始配置（默认值）" if h["version"] == 1 else ""),
                        changes=_diff_rows(h["diff"], cfg)))
    return out


@router.get("/settings/category")
def category_page(request: Request, tab: str = "frame", user=operator_only):
    v, cfg = catconfig.current()
    fits = fit_counts()
    channels = []
    for ch, c in cfg.get("channels", {}).items():
        channels.append(dict(key=ch, name=CHANNEL_NAMES.get(ch, ch), cfg=c, fit=fits.get(ch, 0)))
    hist = _history(cfg)
    thr = cfg.get("low_conf_threshold", 0.75)
    return render(request, "settings_category.html", "PAGE-F27-01", "品类配置", version=v, cfg=cfg, channels=channels,
                  history=hist, current=hist[0] if hist else None, methods=METHODS, min_fit=MIN_FIT,
                  tag_values=_tag_values(), queue_n=_queue_count(thr), thr=thr,
                  tab=tab if tab in ("frame", "tag", "ch", "ver") else "frame")


def _parse(data: str):
    try:
        new = json.loads(data or "")
    except ValueError:
        return None, "配置不是有效的 JSON"
    if not isinstance(new, dict):
        return None, "配置不是有效的 JSON"
    return new, validate(new)


@router.post("/settings/category/preview")
def category_preview(data: str = Form(""), user=operator_only):
    """保存前的前后对比（catconfig.preview）。"""
    new, err = _parse(data)
    if err:
        return JSONResponse({"detail": err}, status_code=400)
    v, cfg = catconfig.current()
    return {"version": v, "next_version": v + 1, "changes": _diff_rows(catconfig.preview(new), cfg)}


@router.post("/settings/category")
def category_save(data: str = Form(""), note: str = Form(""), tab: str = Form("frame"), user=operator_only):
    new, err = _parse(data)
    if err:
        return redirect(f"/settings/category?tab={tab}", f"保存失败：{err}", "error")
    if not note.strip():
        return redirect(f"/settings/category?tab={tab}", "请填写修改说明", "error")
    v, _ = catconfig.current()
    nv = catconfig.save(new, user.id)
    if nv == v:
        return redirect(f"/settings/category?tab={tab}", "没有修改，参数仍为 v%d" % v, "warn")
    with session() as s:
        s.add(ConfigNote(version=nv, note=note.strip()))
    return redirect(f"/settings/category?tab={tab}", f"已保存参数 v{nv}，之后的估算、扫描和判定使用新值")

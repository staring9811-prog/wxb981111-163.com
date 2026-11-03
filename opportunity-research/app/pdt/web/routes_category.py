"""品类配置（PAGE-F27-01，API-F27-01；AC-F27-01～03）。仅操作者可用；第一版只有浴室柜，不提供新建品类入口。"""
import json
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .. import catconfig
from ..config import CATEGORY, CHANNEL_NAMES
from ..db import session
from ..core import channels as chm
from ..models import Tag, User
from ..models_settings import ConfigNote
from ..auth import operator_only
from .ui import redirect, render

router = APIRouter()

METHODS = {"review": "评论换算", "rank": "榜单排名平滑"}
FIELD_NAMES = {
    "low_conf_threshold": "低置信度阈值", "vp_coef": "VP 系数", "nonvp_coef": "非 VP 系数", "method": "估算方法",
    "bsr_top": "成功线 · 小类 BSR 名次", "spu_revenue": "成功线 · SPU 月销售额", "rank_top": "成功线 · 榜单名次",
    "units": "成功线 · 估算月销", "scan": "参与扫描", "values": "取值", "tag_rules": "打标规则", "frame_dims": "分框维度",
    "scan_attrs": "扫描属性", "budget_warn_pct": "接近上限提示比例", "min_frame_units": "框最小月销",
    "min_value_units": "属性值最小月销", "verify": "Amazon 核对阈值",
    "start": "回补起始月份", "n": "回补商品页数 N", "rank_corr": "打折 · 秩相关减值", "high_pp": "打折 · 把握 ≥70% 档减值（百分点）",
    "dir_cap": "打折 · 方向对上限（%）", "backfill": "历史回补", "discount": "打折规则",
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
        bf, dc = c.get("backfill") or {}, c.get("discount") or {}
        if "start" in bf and not re.match(r"^20\d{2}-(0[1-9]|1[0-2])$", str(bf["start"])):
            return f"{name} 回补起始月份格式应为 YYYY-MM"
        if "n" in bf and not (_pos(bf["n"]) and float(bf["n"]) == int(float(bf["n"]))):
            return f"{name} 商品页数 N 要填正整数"
        for k, lo, hi in (("rank_corr", 0, 1), ("high_pp", 0, 100), ("dir_cap", 0, 100)):
            if k in dc:
                try:
                    ok = lo <= float(dc[k]) <= hi
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    return f"{name} {FIELD_NAMES[k]}：需在 {lo}–{hi} 之间"
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


CONF_NAMES = {"text_supported": "文字直接写明", "derived": "推导", "business_mapping": "业务映射", "business_inference": "业务推断",
              "order_inference": "顺序推断", "parent_fill": "父体补齐", "family_fill": "家族补齐", "business_default": "业务默认",
              "business_assumption": "业务假设", "parent_candidate": "父体候选", "conflict": "证据冲突", "missing": "缺失"}


def _arrow_items(m: dict, n: int = 6) -> str:
    """{原词: 归类} → “原词 → 归类、…”，同一归类的原词合并。"""
    by = {}
    for k, v in m.items():
        by.setdefault(v, []).append(k)
    parts = [f"{' / '.join(ks)} → {v}" for v, ks in by.items()]
    return "；".join(parts[:n]) + ("；…" if len(parts) > n else "")


def tag_rule_rows(rules: dict) -> list[dict]:
    """打标规则按业务标签分行的中文摘要（PAGE-F27-01 打标规则表）；JSON 原文只在“编辑”抽屉里。"""
    from ..core.tagging import CANDIDATES
    bands = rules.get("size_bands") or []
    size = "；".join(f"{lo:g}–{hi:g} 英寸 → {c}″" for c, lo, hi in bands) + "；≥ 66 英寸 → 72″+"
    em = rules.get("element_map") or {}
    vocab = rules.get("element_vocab") or []
    cm = rules.get("color_map") or {}
    cab = str(rules.get("cabinet_map") or "")
    top = str(rules.get("top_type_map") or "")
    return [
        dict(tag="尺寸段", method="规则", n=len(bands) + 1, summary=f"读标题、规格、商品尺寸中的宽度，按区间归段：{size}"),
        dict(tag="拆装", method="规则", n=3, summary="写明 fully assembled / no assembly required / 到货已组装 → 整装；"
                                                     "assembly required、RTA、partially assembled 等或没写 → 拆装"),
        dict(tag="形态", method="规则", n=5, summary="floating / wall mounted → 悬浮式；freestanding / floor standing → 落地式；"
                                                    "pedestal sink → 柱状盆；corner vanity → 转角式；同时写可壁挂和可落地 → 两用；无关键词默认落地式"),
        dict(tag="台面材质", method="规则", n=len(CANDIDATES["台面材质"]),
             summary=f"读台面描述归入 {len(CANDIDATES['台面材质'])} 种材质（{'、'.join(CANDIDATES['台面材质'][:6])} …）；分析时再归大类：{top}"),
        dict(tag="元素", method="规则 + 看图", n=len(em),
             summary=f"标题关键词：{_arrow_items({k: catconfig.value_name(v) for k, v in em.items()})}；判断不了的由大模型看主图，从 {len(vocab)} 个元素词里选；未配置大模型时进入人工确认。元素一律人工确认"),
        dict(tag="主色", method="规则", n=len(cm) + 1, summary=f"颜色词归类：{_arrow_items(cm, 8)}；其余颜色 → 其他"),
        dict(tag="柜体材质", method="规则", n=len([x for x in cab.split("；") if x.strip()]), summary=cab),
    ]


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
    channels = []
    for ch, c in cfg.get("channels", {}).items():
        # 锚点数与其他渠道数据页同一函数（AC-F28-04：同时有排名和评论换算销量的商品数，少于 10 个不提供）
        channels.append(dict(key=ch, name=CHANNEL_NAMES.get(ch, ch), cfg=c, fit=chm.rank_fit(ch)[2]))
    hist = _history(cfg)
    thr = cfg.get("low_conf_threshold", 0.75)
    from ..core.tagging import queued_count, rules_cfg  # 队列条数与打标确认页、侧栏角标同一口径
    rules = rules_cfg()[0]
    conf = rules.get("confidence") or {}
    from ..core import backfill
    bf_params = {c["key"]: catconfig.channel_params(c["key"])[1] for c in channels if c["key"] != "amazon"}
    bf_state = {k: (backfill.last_rebuild(k) or {}).get("stats") for k in bf_params}
    from ..core import channel_model  # 现状带上证据等级：读该渠道最近一次回测
    bf_ev = {k: channel_model.evidence(k) for k in bf_params}
    return render(request, "settings_category.html", "PAGE-F27-01", "品类配置", version=v, cfg=cfg, channels=channels, bf_params=bf_params, bf_state=bf_state, bf_ev=bf_ev,
                  history=hist, current=hist[0] if hist else None, methods=METHODS, min_fit=chm.MIN_RANK_POINTS,
                  tag_values=_tag_values(), queue_n=queued_count(), thr=thr, tag_rows=tag_rule_rows(rules), rule_version=rules.get("rule_version", ""),
                  conf_text="、".join(f"{CONF_NAMES.get(k, k)} {float(v):.2f}" for k, v in conf.items()), vision_usd=rules.get("vision_usd_per_call") or [],
                  rules_json=json.dumps(cfg.get("tag_rules") or {}, ensure_ascii=False, indent=2),
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

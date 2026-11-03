"""决策卡（F21 / F29）：从扫描单元生成数字、十项内容、状态机、叙述编辑、另存为新草稿。

数字全部由系统按数据计算，存在 Card.numbers；wen 只能改 Card.narrative 里的叙述与决策输入（拟定售价、预计上架月、上架渠道、
停止条件阈值）。批准时把数字与利润回写结果存进 Card.snapshot，之后页面只读快照（AC-F25-02）。
"""
import copy
import math
import time
from datetime import datetime

from sqlalchemy import select

from .. import catconfig, costgate, services
from ..config import CHANNEL_NAMES, CHANNELS
from ..db import session
from ..models import Batch, Card, ModelRun, Opportunity, ProfitPlan, UnitScore, now
from ..models_decision import CardEvent
from . import panel_adapter as pa

STATUS_NAMES = {"draft": "草稿", "pending": "待审批", "approved": "已批准", "rejected": "已驳回",
                "tracking": "跟踪中", "reconciled": "已对账"}
# 合法迁移（技术方案 §5.1）：其他一律非法，尤其"已批准后改数字"
TRANSITIONS = {("draft", "submit"): "pending", ("pending", "approve"): "approved", ("pending", "reject"): "rejected",
               ("pending", "return"): "draft", ("approved", "track"): "tracking", ("tracking", "reconcile"): "reconciled",
               ("approved", "reconcile"): "reconciled"}
LOCKED = ("approved", "tracking", "reconciled")
REVIEW_CATS = ["装配 / 做工", "本品类关键部件", "柜体材料", "结构 / 设计", "运输", "服务", "不明"]


class IllegalTransition(Exception):
    pass


class NumbersReadOnly(Exception):
    pass


def transition(card: Card, action: str) -> str:
    nxt = TRANSITIONS.get((card.status, action))
    if nxt is None:
        raise IllegalTransition(f"决策卡当前为“{STATUS_NAMES.get(card.status, card.status)}”，不能执行该操作")
    card.status = nxt
    card.updated_at = now()
    return nxt


def log(s, card_id, kind, text, user_id=None):
    s.add(CardEvent(card_id=card_id, kind=kind, text=text, user_id=user_id))


def card_name(c) -> str:
    """卡名：取值 · 框（尺寸 拆装 · 形态），例：树脂一体 · 30″ 拆装 · 落地式。"""
    f = c.frame.split(" · ")
    fr = f"{f[0]} {f[1]} · {f[2]}" if len(f) == 3 else c.frame
    return f"{c.value} · {fr}"


# ---------------------------------------------------------------- 模型与偏差
def latest_run(s):
    return s.scalar(select(ModelRun).order_by(ModelRun.id.desc()).limit(1))


def validity_statement(run, data_month: str, today=None) -> dict:
    """工作台与决策卡顶部共用的有效性表述（AC-F19-04）：一律以最新 ModelRun 的数据截至月与重算时间为准。

    “本月”指重算发生在当前自然月；未通过时照 AC-F19-04 原文。basis 是同一句依据：版本 · 数据截至月 · 重算日期。
    data_month 晚于数据截至月时另给 pending（该月数据尚未纳入重算），不改变通过与否的说法。
    """
    if run is None:
        return dict(kind="none")
    today = today or datetime.now().date()
    this_month = run.created_at.strftime("%Y-%m") == today.strftime("%Y-%m")
    if not run.valid:
        kind, title = "fail", "市场评分本月未通过有效性检验"
    elif this_month:
        kind, title = "pass", "市场评分本月通过有效性检验"
    else:
        kind, title = "stale", f"本月尚未重算，以下沿用数据截至 {run.month} 的结论"
    basis = f"{run.version}，数据截至 {run.month}，{run.created_at:%Y-%m-%d} 重算"
    pending = f"{data_month} 数据尚未纳入重算" if data_month and run.month < data_month else ""
    return dict(kind=kind, title=title, basis=basis, msg="" if run.valid_msg == "市场评分本月未通过有效性检验" else (run.valid_msg or ""), pending=pending, month=run.month)


def model_bias(run) -> float | None:
    """当月"模型偏差"（新品层近批预测 − 实际），按概率单位返回。newlayer 里按每 10 个记（如 1.2）时换算成 0.12。"""
    if run is None:
        return None
    nl = run.newlayer or {}
    b = nl.get("bias")
    if isinstance(b, dict):  # 分析组写法：{pred, actual, bias = pred − actual, n, ...}，概率单位
        b = b.get("bias")
    if b is None:
        return None
    b = float(b)
    return b / 10 if abs(b) > 1 else b  # 兼容按"每 10 个"记的写法（如 1.2）


def _fisher_p(a, n1, b, n2):
    """双侧 Fisher 精确检验（框内含该取值的新家族做到率 vs 同框其他）。"""
    if not n1 or not n2:
        return None
    from scipy.stats import fisher_exact
    return float(fisher_exact([[a, n1 - a], [b, n2 - b]])[1])


# ---------------------------------------------------------------- 工具
def pop(**kw) -> str:
    """数字来源浮层（app.js 的 data-pop 格式：键=值;键=值）。"""
    return ";".join(f"{k}={v}" for k, v in kw.items() if v not in (None, ""))


def _q(m: str) -> str:
    return f"{m[:4]}Q{(int(m[5:7]) - 1) // 3 + 1}"


def add_months(m: str, n: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + n
    return f"{y + mm // 12}-{mm % 12 + 1:02d}"


def _wa(pairs):
    pairs = [(v, w) for v, w in pairs if v is not None and w]
    sw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / sw if sw else None


def quarters(ts: list) -> list:
    """逐月 → 逐季：月销取季内月均，份额 = 季内单元销量 ÷ 框销量，价格 / 溢价 / 评分 / 新品占比按销量加权。"""
    out = {}
    for r in ts:
        out.setdefault(_q(r["month"]), []).append(r)
    rows = []
    for q, rs in sorted(out.items()):
        u = sum(r["units"] or 0 for r in rs)
        fu = sum(_frame_units(r) for r in rs)
        rows.append(dict(
            q=q + ("*" if any(r.get("star") for r in rs) else ""), months=[r["month"] for r in rs],
            units=u / len(rs), share=u / fu if fu else None,
            median_price=_wa((r.get("median_price"), r["units"]) for r in rs),
            premium=_wa((r.get("premium"), r["units"]) for r in rs),
            rating=_wa((r.get("rating"), r["units"]) for r in rs),
            frame_rating=_wa((r.get("frame_rating"), _frame_units(r)) for r in rs),
            newshare=_wa((r.get("newshare"), r["units"]) for r in rs),
            frame_newshare=_wa((r.get("frame_newshare"), _frame_units(r)) for r in rs),
            families=max((r.get("families") or 0) for r in rs)))
    return rows


def _frame_units(r):
    if r.get("frame_units") is not None:
        return r["frame_units"]
    return (r["units"] or 0) / r["share"] if r.get("share") else 0


def _period(ts, months):
    rs = [r for r in ts if r["month"] in months]
    if not rs:
        return {}
    u = sum(r["units"] or 0 for r in rs)
    fu = sum(_frame_units(r) for r in rs)
    return dict(units=u / len(months), share=u / fu if fu else None, frame_units=fu / len(months),
                newshare=_wa((r.get("newshare"), r["units"]) for r in rs),
                frame_newshare=_wa((r.get("frame_newshare"), _frame_units(r)) for r in rs),
                rating=_wa((r.get("rating"), r["units"]) for r in rs),
                frame_rating=_wa((r.get("frame_rating"), _frame_units(r)) for r in rs),
                median_price=_wa((r.get("median_price"), r["units"]) for r in rs),
                premium=_wa((r.get("premium"), r["units"]) for r in rs),
                families=max((r.get("families") or 0) for r in rs))


def spark_points(vals, w=96, h=26, pad=4):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, x in enumerate(vals):
        if x is None:
            continue
        pts.append(f"{pad + i * (w - 2 * pad) / (n - 1):.1f},{h - pad - (x - lo) / rng * (h - 2 * pad):.1f}")
    return " ".join(pts)


def _direction(prev, now_):
    if prev is None or now_ is None:
        return None
    if now_ > prev:
        return "涨"
    if now_ < prev:
        return "跌"
    return "平"


# ---------------------------------------------------------------- 生成数字
def _opp(s, ch, frame, attr, value):
    return s.scalar(select(Opportunity).where(Opportunity.channel == ch, Opportunity.frame == frame, Opportunity.attr == attr,
                                              Opportunity.value == value).order_by(Opportunity.month.desc()).limit(1))


def _score(s, run, ch, frame, attr, value):
    if run is None:
        return None
    return s.scalar(select(UnitScore).where(UnitScore.run_id == run.id, UnitScore.channel == ch, UnitScore.frame == frame,
                                            UnitScore.attr == attr, UnitScore.value == value).limit(1))


def build_numbers(channel: str, frame: str, attr: str, value: str) -> dict:
    """生成一张卡全部数字（含每个数字的来源）。不含任何外部调用（NFR-010）。"""
    t0 = time.time()
    pa.clear_cache()
    cfg_v, cfg = catconfig.current()
    scan = cfg.get("scan", {})
    min_fu, min_vu = scan.get("min_frame_units", 200), scan.get("min_value_units", 10)
    unit_label = f"{attr}：{value}"
    with session() as s:
        run = latest_run(s)
        bias = model_bias(run)
        run_info = dict(id=run.id, month=run.month, version=run.version, valid=run.valid, valid_msg=run.valid_msg,
                        at=run.created_at.strftime("%Y-%m-%d")) if run else None
        chans, prim = [], None
        for ch in CHANNELS:
            opp = _opp(s, ch, frame, attr, value)
            sc = _score(s, run, ch, frame, attr, value)
            om = (opp.metrics or {}) if opp else {}
            ts = pa.unit_timeseries(ch, frame, attr, value)
            months = [r["month"] for r in ts]
            recent, prev = months[-6:], months[-12:-6]
            pr, pp = _period(ts, recent), _period(ts, prev)
            qs = quarters(ts)
            share_now = om.get("share", pr.get("share"))
            share_prev = om.get("share_prev", pp.get("share"))
            units = om.get("units", pr.get("units"))
            fam = om.get("families", pr.get("families"))
            fu = om.get("frame_units", pr.get("frame_units"))
            has = bool(ts) or opp is not None
            sample_ok = has and (fu or 0) >= min_fu and (units or 0) >= min_vu
            sd = (sc.data or {}) if sc else {}
            d = _direction(share_prev, share_now) if sample_ok else None
            grade = sd.get("grade") if sample_ok else None
            if not has or not sample_ok:
                verdict = "不上"
            elif d == "跌":
                verdict = "不上"
            elif d == "涨" and ch == "amazon" and grade in ("A", "B"):
                verdict = "上"
            else:
                verdict = "观察"
            per = f"{recent[0]} 至 {recent[-1]}" if recent else ""
            per0 = f"{prev[0]} 至 {prev[-1]}" if prev else ""
            est = ch != "amazon"
            src = pop(框=frame, 取值=unit_label, 月份=(f"{prev[0] if prev else recent[0]} 至 {recent[-1]}" if recent else "本月无数据"), 前期=per0, 近期=per,
                      样本数=f"{fam or 0} 个家族，近期月均 {units or 0:,.0f} 件",
                      口径=(f"VP × 系数 + 非 VP × 系数（参数 v{cfg_v}），按评论 ID 去重，只在 {CHANNEL_NAMES[ch]} 内比较" if est else "卖家精灵子体月销"),
                      来源=(f"机会扫描 {opp.month}" if opp else "月度快照"),
                      说明=("" if sample_ok or not has else f"框月销 {fu or 0:,.0f} 件，不到 {min_fu} 件，不扫描"))
            row = dict(channel=ch, name=CHANNEL_NAMES[ch], has_data=has, sample_ok=sample_ok, estimated=est,
                       share_prev=share_prev, share_now=share_now, units=units, families=fam, frame_units=fu,
                       direction=d, grade=grade, grasp=sd.get("grasp"), verified=not est, verdict=verdict,
                       spark=spark_points([q["share"] for q in qs[-4:]]), src=src,
                       recent=recent, prev=prev, quarters=qs,
                       skus=pa.unit_skus(ch, frame, attr, value, top=None) if has else [],  # 全部子体，页面分页显示
                       bands=pa.price_bands(ch, frame, attr, value) if has else [],
                       opp=dict(kind=opp.kind, evidence=opp.evidence, month=opp.month, metrics=om) if opp else None,
                       score=dict(sd, run_id=run.id) if sc else None, period=pr)
            row["n_skus"] = len(row["skus"])
            chans.append(row)
            if ch == channel:
                prim = row
        # 多渠道印证 / 渠道分歧（AC-F29-04）：只看样本够的渠道
        dirs = {c["channel"]: c["direction"] for c in chans if c["direction"] in ("涨", "跌")}
        main_dir = dirs.get(channel) or (max(("涨", "跌"), key=lambda x: list(dirs.values()).count(x)) if dirs else None)
        agree = [CHANNEL_NAMES[k] for k, v in dirs.items() if v == main_dir]
        diverge = [CHANNEL_NAMES[k] for k, v in dirs.items() if v != main_dir]
        marks = dict(dir=main_dir, agree=agree if len(agree) >= 2 else [], diverge=diverge if main_dir else [])

        # 同框其他取值（大数据层"近期框内各取值"）与同取值其他框（分框决策 / 被放弃的选项）
        latest = s.scalar(select(Opportunity.month).where(Opportunity.channel == channel).order_by(Opportunity.month.desc()).limit(1))
        frame_values, other_frames = [], []
        if latest:
            for o in s.scalars(select(Opportunity).where(Opportunity.channel == channel, Opportunity.month == latest,
                                                         Opportunity.frame == frame, Opportunity.attr == attr)):
                m = o.metrics or {}
                frame_values.append(dict(value=o.value, units=m.get("units"), share=m.get("share"), families=m.get("families"),
                                         premium=m.get("premium"), rating=m.get("rating"), me=o.value == value))
            for o in s.scalars(select(Opportunity).where(Opportunity.channel == channel, Opportunity.month == latest,
                                                         Opportunity.attr == attr, Opportunity.value == value, Opportunity.frame != frame)):
                m = o.metrics or {}
                other_frames.append(dict(frame=o.frame, kind=o.kind, share_prev=m.get("share_prev"), share=m.get("share"),
                                         newfam=m.get("newfam"), newmade=m.get("newmade"), units=m.get("units")))
        frame_values.sort(key=lambda r: -(r["units"] or 0))
        other_frames.sort(key=lambda r: -(r["units"] or 0))
        star_months = sorted({m for (m,) in s.execute(select(Batch.month).where(Batch.channel == channel, Batch.star.is_(True)))})

    p = prim or chans[0]
    om = (p["opp"] or {}).get("metrics", {}) if p["opp"] else {}
    sd = p["score"] or {}
    pr = p["period"]
    per = f"{p['recent'][0]} 至 {p['recent'][-1]}" if p["recent"] else ""
    # 新品做到概率：原值与扣当月模型偏差后的值（AC-F21-03）
    raw = sd.get("prob_raw")
    raws = raw if isinstance(raw, list) else ([raw] if raw is not None else [])
    adjs = [max(0.0, r - bias) for r in raws] if bias is not None else [a for a in ([sd.get("prob_adj")] if sd.get("prob_adj") is not None else [])]
    # 框内历史做到率
    nf, nm = om.get("newfam"), om.get("newmade")
    fnf, fnm = om.get("frame_newfam"), om.get("frame_newmade")
    other_n = (fnf - nf) if (fnf is not None and nf is not None) else None
    other_m = (fnm - nm) if (fnm is not None and nm is not None) else None
    made_p = sd.get("made_p")
    if made_p is None and None not in (nf, nm, other_n, other_m):
        made_p = _fisher_p(nm, nf, other_m, other_n)
    bands = p["bands"]
    span = f"{p['quarters'][0]['months'][0]} 至 {p['recent'][-1]}" if p["quarters"] and p["recent"] else per
    top_bands = sorted(bands, key=lambda b: -(b.get("obs") or 0))[:2]
    top_bands.sort(key=lambda b: b.get("lo") or 0)
    rating = om.get("rating", pr.get("rating"))
    frame_rating = om.get("frame_rating", pr.get("frame_rating"))
    med_price = (p["quarters"][-1]["median_price"] if p["quarters"] else None) or om.get("median_price") or pr.get("median_price")
    price = int(round(med_price / 10) * 10) if med_price else None
    money = _money(channel, frame, attr, value, bands, price)
    skus = p["skus"]
    recent_ratio = None
    rr = [s_["series"][-1].get("price_ratio") for s_ in skus[:3] if s_.get("series") and s_["series"][-1].get("price_ratio")]
    if rr:
        recent_ratio = min(rr)
    stop = [dict(kind="rating_below", value=round((frame_rating or 4.25) - 0.05, 1), text="前 3 个月评分 < {v}"),
            dict(kind="units_below", value=int(round((money["general"] or 25) * 1.6 / 10) * 10) or 40, text="第 2–3 个月月销 < {v} 件"),
            dict(kind="price_ratio_below", value=0.75, now=recent_ratio,
                 text="同框竞品把价格压到同框中位价 {v} 倍以下" + (f"（现在 {recent_ratio:.2f}）" if recent_ratio else ""))]
    abandoned = []
    for o in other_frames[:4]:
        grow = (o["share"] or 0) > (o["share_prev"] or 0)
        abandoned.append(dict(option=f"同取值做 {o['frame']}", action="观察" if grow else "放弃",
                              why=f"份额 {_pct(o['share_prev'])} → {_pct(o['share'])}" + (f"，新家族 {o['newfam']} 个做到 {o['newmade']} 个" if o.get("newfam") else "")))
    if bands:
        best = max((b.get("median_units") or 0) for b in bands)
        for b in bands:
            if (b.get("obs") or 0) >= 20 and (b.get("median_units") or 0) < best / 2:
                abandoned.append(dict(option=f"{b['band']} 价位", action="放弃",
                                      why=f"{b['obs']} 个子体 × 月，月销中位只有 {b['median_units']:.0f} 件，不到最好价位带的一半",
                                      src=pop(框=frame, 取值=unit_label, 价格带=b["band"], 月份=span, 样本数=f"{b.get('skus')} 个子体、{b['obs']} 个子体 × 月")))
    dom = [fv for fv in frame_values if not fv["me"] and (fv["share"] or 0) >= 0.5]
    if dom:
        abandoned.append(dict(option=f"{dom[0]['value']}（同框主流）", action="放弃",
                              why=f"占 {_pct(dom[0]['share'])}、{dom[0]['families']} 个家族，款式同质、靠价格竞争"))
    for c in chans:
        if c["channel"] != channel and c["verdict"] == "不上":
            why = "样本不足" if not c["sample_ok"] else f"份额在跌（{_pct(c['share_prev'])} → {_pct(c['share_now'])}）"
            abandoned.append(dict(option=f"{c['name']} 同步上", action="放弃", why=why if c["has_data"] else "该渠道本月无数据"))
    cfg_ch = cfg.get("channels", {})
    tracking = [dict(when="前 3 个月", what="评分、家族月销、小类排名",
                     target=f"评分 ≥ {round((frame_rating or 4.25) + 0.05, 1)}，月销 ≥ {int(round((money['general'] or 25) * 2.4 / 10) * 10)} 件，进小类前 100")]
    am = cfg_ch.get("amazon", {}).get("success", {})
    tracking.append(dict(when="6 个月（Amazon）", what="做到判定", target=f"任一月小类 BSR ≤ {am.get('bsr_top', 50)} 或 SPU 月销售额 ≥ ${am.get('spu_revenue', 100000):,.0f}"))
    for c in chans:
        if c["channel"] != "amazon" and c["verdict"] in ("上", "观察"):
            sc_ = cfg_ch.get(c["channel"], {}).get("success", {})
            tracking.append(dict(when=f"6 个月（{c['name']}，{c['verdict']}）", what="做到判定",
                                 target=f"类目榜前 {sc_.get('rank_top', 50)}，或估算月销 ≥ {sc_.get('units', '—')} 件（同系列合并）"))
    if recent_ratio:
        tracking.append(dict(when="一直", what="同框低价竞品的价格", target="不低于同框中位价 0.75 倍"))
    limits = [f"{value}是{attr}标签；标签缺失或“信息不足”的商品未计入份额分母。"]
    if star_months:
        limits.append(f"{'、'.join(star_months)} 为带 * 并入的月份（核对异常），这几个月的变化要打折看。")
    limits.append(f"Home Depot / Lowe's / Wayfair 月销是评论换算估算（品类配置参数 v{cfg_v}），分级规则在这些渠道未回测；只在渠道内比较。")
    for c in chans:
        if c["has_data"] and not c["sample_ok"]:
            limits.append(f"{c['name']} 这个框样本不足（框月销 {c['frame_units'] or 0:,.0f} 件）。")
        if not c["has_data"]:
            limits.append(f"{c['name']} 本月无该单元数据。")
    limits.append("“为消费者解决了什么问题”是推测，待问答验证。")
    return dict(
        meta=dict(channel=channel, frame=frame, attr=attr, value=value, unit=unit_label, data_month=p["recent"][-1] if p["recent"] else "",
                  first_month=(p["quarters"][0]["months"][0] if p["quarters"] else ""), recent=p["recent"], prev=p["prev"],
                  run=run_info, bias=bias, cfg_version=cfg_v, star_months=star_months, fallback=pa.using_fallback()),
        channels=chans, marks=marks,
        bet=dict(kind=(p["opp"] or {}).get("kind") if p["opp"] else None, evidence=(p["opp"] or {}).get("evidence") if p["opp"] else None,
                 share_prev=p["share_prev"], share_now=p["share_now"], newshare=om.get("newshare", pr.get("newshare")),
                 frame_newshare=om.get("frame_newshare", pr.get("frame_newshare")),
                 src_share=pop(框=frame, 取值=unit_label, 月份=span, 前期=f"{p['prev'][0]} 至 {p['prev'][-1]}" if p["prev"] else "", 近期=per,
                               样本数=f"{p['families'] or 0} 个在榜家族", 新品="上架 ≤ 6 个月"),
                 score=dict(grasp=sd.get("grasp"), grade=sd.get("grade"), pred=sd.get("pred_share"), lo=sd.get("pred_lo"), hi=sd.get("pred_hi"),
                            now=sd.get("share_now", p["share_now"]), k=sd.get("k_months"),
                            src=pop(框=(sd.get("sources") or {}).get("frame", frame), 单元=unit_label, 月份=(sd.get("sources") or {}).get("months", per),
                                    样本数=(sd.get("sources") or {}).get("n", sd.get("n_families")),
                                    规则=f"{run_info['version']}，{run_info['at']} 重算" if run_info else "")) if sd else None,
                 prob=dict(raw=raws, adj=adjs, bias=bias,
                           src=pop(框=frame, 月份=(f"{run_info['month']}（{run_info['version']}）" if run_info else per), 模型="新品层，只用开发能定的属性", 模型偏差=(f"{bias * 10:+.1f}（每 10 个，{run_info['at']}）" if bias is not None and run_info else "无"),
                                   单元=unit_label, 样本数=sd.get("n_families"))) if raws else None,
                 made=dict(n=nf, made=nm, other_n=other_n, other_made=other_m, p=made_p,
                           src=pop(框=frame, 月份=f"{p['quarters'][0]['months'][0] if p['quarters'] else ''} 至 {p['recent'][-1] if p['recent'] else ''}，已走完 6 个月观察期的新家族",
                                   样本数=f"{nf} + {other_n} = {(nf or 0) + (other_n or 0)} 个新家族" if nf is not None and other_n is not None else "",
                                   做到="6 个月内任一月小类 BSR ≤ 50 或 SPU 月销售额 ≥ $10 万", 检验="Fisher 精确检验")) if nf is not None else None,
                 bands=[dict(b, src=pop(框=frame, 取值=unit_label, 价格带=b["band"], 月份=f"{p['quarters'][0]['months'][0] if p['quarters'] else ''} 至 {p['recent'][-1] if p['recent'] else ''}",
                                        样本数=f"{b.get('skus')} 个子体、{b.get('obs')} 个子体 × 月")) for b in top_bands],
                 rating=rating, frame_rating=frame_rating,
                 src_rating=pop(框=frame, 月份=per, 样本数=f"{p['families'] or 0} 个家族（按销量加权）")),
        price=price, money=money, stop=stop, abandoned=abandoned, frame_values=frame_values, other_frames=other_frames,
        tracking=tracking, limits=limits, gen_seconds=round(time.time() - t0, 2), generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))


def _pct(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def _money(channel, frame, attr, value, bands, price):
    """钱：一般（拟定价位所在价格带子体 × 月中位）、做到（含该取值、做到的家族第 4–6 个月中位）、好（最好家族峰值月）。"""
    general = None
    band = None
    for b in bands:
        if price is not None and (b.get("lo") or 0) <= price < (b.get("hi") or 1e12):
            general, band = b.get("median_units"), b
    df = pa.load_panel(channel)
    made = good = None
    good_txt = ""
    n_made = 0
    if not df.empty and attr in df.columns:
        d = df[(df["frame"] == frame) & pa._has(df[attr], value)]
        if not d.empty:
            fm = d.groupby(["family_key", "month"]).agg(units=("units", "sum"), age=("age_months", "min"), rank=("rank", "min"), brand=("brand", "first")).reset_index()
            okfam = set(fm[(fm["age"] <= 6) & (fm["rank"] <= 50)]["family_key"])
            n_made = len(okfam)
            v = fm[fm["family_key"].isin(okfam) & fm["age"].between(4, 6)]["units"]
            made = float(v.median()) if len(v) else None
            top = fm.sort_values("units", ascending=False).iloc[0]
            good, good_txt = float(top["units"]), f"{top['brand']} {top['month']}：家族合计"
    return dict(price=price, general=general, general_band=band["band"] if band else None, general_obs=band.get("obs") if band else None,
                made=made, made_n=n_made, good=good, good_txt=good_txt)


# ---------------------------------------------------------------- 生成、编辑、另存
def default_narrative(numbers: dict) -> dict:
    m, p = numbers["meta"], numbers
    prim = next((c for c in p["channels"] if c["channel"] == m["channel"]), p["channels"][0])
    price = p["price"]
    rt = round((p["bet"].get("frame_rating") or p["bet"].get("rating") or 4.25) + 0.05, 1)
    plan = f"{m['frame']}：{'$' + str(price - 10) + '–' + str(price + 20) if price else '价位待定'}，首月 ≥ 2 色、≥ 4 子体，评分目标 ≥ {rt}"
    reason = (f"份额 {_pct(prim['share_prev'])} → {_pct(prim['share_now'])}"
              + (f"，{prim['grade']} 档、把握 {prim['grasp'] * 100:.0f}%" if prim.get("grasp") is not None and prim.get("grade") else ""))
    launch = add_months(m["data_month"], 8) if m.get("data_month") else ""
    chans = [c["channel"] for c in p["channels"] if c["verdict"] in ("上", "观察")] or [m["channel"]]
    return dict(plan=plan, reason=reason, consumer="", consumer_ai=False, price=price, launch_month=launch,
                launch_channels=chans, stop=[dict(kind=s_["kind"], value=s_["value"]) for s_ in p["stop"]], abandon_note="", limits_note="")


def generate(channel: str, frame: str, attr: str, value: str, user_id=None) -> int:
    numbers = build_numbers(channel, frame, attr, value)
    with session() as s:
        c = Card(channel=channel, frame=frame, attr=attr, value=value, status="draft", version=1, numbers=numbers,
                 narrative=default_narrative(numbers), data_month=numbers["meta"]["data_month"], created_by=user_id)
        s.add(c)
        s.flush()
        log(s, c.id, "create", f"从机会扫描生成草稿 · 用时 {numbers['gen_seconds']} 秒", user_id)
        return c.id


def save_as_new(card_id: int, user_id=None) -> int:
    """已批准（或驳回）的卡另存为新草稿：用最新数据重新生成数字，原版本不变（AC-F25-02）。"""
    with session() as s:
        old = s.get(Card, card_id)
        if old.status not in LOCKED + ("rejected",):
            raise IllegalTransition("只有已批准或已驳回的卡可以另存为新草稿")
        ch, fr, at, va, narr, ver = old.channel, old.frame, old.attr, old.value, copy.deepcopy(old.narrative), old.version
    numbers = build_numbers(ch, fr, at, va)
    narr.pop("submit_note", None)
    with session() as s:
        c = Card(channel=ch, frame=fr, attr=at, value=va, status="draft", version=ver + 1, numbers=numbers, narrative=narr,
                 data_month=numbers["meta"]["data_month"], parent_id=card_id, created_by=user_id)
        s.add(c)
        s.flush()
        log(s, c.id, "save_as", f"由第 {ver} 版另存为新草稿（第 {ver + 1} 版），用最新数据重新生成数字", user_id)
        log(s, card_id, "save_as", f"已另存为新草稿（第 {ver + 1} 版）", user_id)
        return c.id


NARR_TEXT = ("plan", "reason", "consumer", "abandon_note", "limits_note")


def update_narrative(card_id: int, form: dict, user_id=None) -> dict:
    """只更新叙述与决策输入；表单里出现数字字段一律拒绝（AC-F21-02）。"""
    bad = [k for k in form if k.startswith("numbers") or k in ("snapshot", "status")]
    with session() as s:
        c = s.get(Card, card_id)
        if c.status != "draft":
            raise NumbersReadOnly("只有草稿可以编辑；已提交或已批准的卡只读" + ("，可另存为新草稿" if c.status in LOCKED else ""))
        if bad:
            raise NumbersReadOnly("数字由系统计算，不能直接修改，只能改叙述")
        n = copy.deepcopy(c.narrative or {})
        changed = []
        for k in NARR_TEXT:
            if k in form and (form[k] or "") != (n.get(k) or ""):
                n[k] = form[k]
                changed.append(k)
                if k == "consumer":
                    n["consumer_ai"] = False  # wen 编辑后去掉"AI 草稿"标记（AC-F21-06）
        if "price" in form and str(form["price"]).strip():
            n["price"] = int(float(form["price"]))
            changed.append("price")
        if "launch_month" in form and form["launch_month"]:
            n["launch_month"] = form["launch_month"][:7]
            changed.append("launch_month")
        if "launch_channels" in form:
            n["launch_channels"] = [x for x in form["launch_channels"] if x in CHANNELS] or [c.channel]
            changed.append("launch_channels")
        for i, st in enumerate(n.get("stop", [])):
            k = f"stop_{i}"
            if k in form and str(form[k]).strip():
                st["value"] = float(form[k])
                changed.append(k)
        if changed:
            c.narrative = n
            c.updated_at = now()
            n["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            log(s, c.id, "edit", "编辑叙述", user_id)
        return n


def set_ai_draft(card_id: int, text: str):
    with session() as s:
        c = s.get(Card, card_id)
        n = copy.deepcopy(c.narrative or {})
        n["consumer"] = text
        n["consumer_ai"] = True
        n["consumer_ai_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.narrative = n
        c.updated_at = now()
        log(s, c.id, "draft", "大模型起草“为消费者解决了什么问题”（AI 草稿）")


def missing_items(c: Card) -> list:
    """提交前检查十项齐全（PAGE-F21-02 §8.2）：数字部分由系统生成，叙述部分检查是否填写。"""
    miss = []
    n = c.narrative or {}
    if not (n.get("plan") or "").strip():
        miss.append("分框决策的方案")
    if not (n.get("consumer") or "").strip():
        miss.append("“为消费者解决了什么问题”")
    if not n.get("launch_month"):
        miss.append("预计上架月份")
    return miss


# ---------------------------------------------------------------- 快照与展示
def profit_view(s, c: Card):
    if not c.profit_plan_id:
        return None
    p = s.get(ProfitPlan, c.profit_plan_id)
    if not p or not p.result:
        return None
    return dict(p.result, plan_id=p.id, plan_name=p.name, saved_at=p.updated_at.strftime("%Y-%m-%d %H:%M"))


def take_snapshot(s, c: Card):
    """批准时的数字快照：数字 + 利润回写 + 差评占比（AC-F25-02）。"""
    from .reviews import summary
    c.snapshot = dict(numbers=copy.deepcopy(c.numbers), profit=profit_view(s, c), reviews=summary(s, c.id, c.value),
                      narrative=copy.deepcopy(c.narrative), at=datetime.now().strftime("%Y-%m-%d %H:%M"))


def has_new_data(s, c: Card) -> list:
    """已批准后依据的数据是否更新：新并入月份、模型重算、关联利润方案再次保存。"""
    if c.status not in LOCKED or not c.snapshot:
        return []
    at = datetime.strptime(c.snapshot["at"], "%Y-%m-%d %H:%M")
    out = []
    b = s.scalar(select(Batch).where(Batch.status == "merged", Batch.merged_at > at).order_by(Batch.merged_at.desc()).limit(1))
    if b:
        out.append(f"{b.month} {CHANNEL_NAMES.get(b.channel, b.channel)} 月度数据已并入（{b.merged_at:%Y-%m-%d}）")
    r = s.scalar(select(ModelRun).where(ModelRun.created_at > at).order_by(ModelRun.id.desc()).limit(1))
    if r:
        out.append(f"模型已重算（{r.version}，{r.created_at:%Y-%m-%d}）")
    if c.profit_plan_id:
        p = s.get(ProfitPlan, c.profit_plan_id)
        if p and p.updated_at > at:
            out.append(f"关联利润方案“{p.name}”已更新（{p.updated_at:%Y-%m-%d %H:%M}）")
    return out


def as_float(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 大模型起草叙述（AC-F21-06）
def _draft_prompt(c: Card) -> str:
    n = c.numbers or {}
    b = n.get("bet", {})
    fv = "、".join(f"{x['value']} {_pct(x['share'])}" for x in (n.get("frame_values") or [])[:5])
    return (f"你是浴室柜品类的产品经理。请用简体中文写 3–4 句，回答“{card_name(c)} 为消费者解决了什么问题”，"
            f"只依据下面的数据推测，最后注明“（推测，待问答验证）”。\n"
            f"框：{c.frame}；取值：{c.attr}：{c.value}\n"
            f"份额 {_pct(b.get('share_prev'))} → {_pct(b.get('share_now'))}；新品占比 {_pct(b.get('newshare'))}（同框 {_pct(b.get('frame_newshare'))}）\n"
            f"评分 {b.get('rating') or '—'}，同框 {b.get('frame_rating') or '—'}；拟定售价 ${(c.narrative or {}).get('price') or '—'}\n"
            f"同框各取值份额：{fv or '—'}\n")


def _est_draft(p):
    return dict(service="llm", calls=1, usd_lo=0.02, usd_hi=0.05, minutes=0.5, note="用大模型起草“为消费者解决了什么问题”，约 6,000 tokens")


def _run_draft(ctx):
    cid = int(ctx.target.split(":")[1])
    with session() as s:
        c = s.get(Card, cid)
        if c.status != "draft":
            raise IllegalTransition("只有草稿可以起草叙述")
        prompt = _draft_prompt(c)
    llm = services.client("llm")
    ctx.allow("llm", amount=0.0)
    text, usd = llm.complete(prompt)
    ctx.charge("llm", qty=1, amount=usd, task="起草叙述")
    set_ai_draft(cid, text.strip())


costgate.register("llm_draft", "起草叙述", _est_draft, _run_draft)

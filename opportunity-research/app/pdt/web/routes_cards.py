"""决策卡（PAGE-F21-01 列表、PAGE-F21-02 详情）、差评归类（F22）、分渠道并排（F29）。API-F21-01 / 02、API-F22-01、API-F29-01。"""
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from .. import costgate, services
from ..auth import any_user, approver_only, operator_only
from ..config import CHANNELS
from ..db import session
from ..models import Approval, Card, Forecast, User
from ..models_decision import CardEvent
from ..core import approval as apcore
from ..core import card as cardcore
from ..core import reviews as rvcore
from .ui import redirect, render

router = APIRouter()


def _wants_json(request: Request) -> bool:
    return request.headers.get("accept", "").startswith("application/json")


def _err(request: Request, url: str, msg: str, code=400):
    if _wants_json(request):
        return JSONResponse({"detail": msg}, status_code=code)
    return redirect(url, msg, "error")


async def _form(request: Request) -> dict:
    f = await request.form()
    d = {}
    for k in f.keys():
        vals = f.getlist(k)
        d[k] = vals if k == "launch_channels" else vals[-1]
    return d


# ---------------------------------------------------------------- 列表
@router.get("/cards")
def cards_list(request: Request, channel: str = "amazon", user=any_user):
    channel = channel if channel in CHANNELS else "amazon"
    with session() as s:
        rows = []
        for c in s.scalars(select(Card).where(Card.channel == channel).order_by(Card.updated_at.desc())):
            n = (c.snapshot or {}).get("numbers") if c.snapshot else c.numbers
            kind = ((n or {}).get("bet") or {}).get("kind") or ""
            sub = [kind or "无机会类型", f"第 {c.version} 版"]
            narr = c.narrative or {}
            if c.status == "draft" and narr.get("consumer_ai"):
                sub.append("叙述含 AI 草稿")
            if c.status == "pending":
                a = s.scalar(select(Approval).where(Approval.obj_type == "card", Approval.obj_id == c.id, Approval.status == "pending"))
                u = s.get(User, a.submitted_by) if a and a.submitted_by else None
                sub.append(f"提交人 {u.name if u else '—'}")
            if c.status in cardcore.LOCKED:
                sub.append("已登记预测台账")
            if c.status == "rejected":
                a = s.scalar(select(Approval).where(Approval.obj_type == "card", Approval.obj_id == c.id, Approval.decision == "reject").order_by(Approval.id.desc()))
                if a:
                    sub.append(f"意见：“{a.comment}”")
            rows.append(dict(c=c, name=f"{c.attr}：{c.value}", sub=" · ".join(sub), new=bool(cardcore.has_new_data(s, c)),
                             fkey=c.frame.replace(" · ", "-").replace("″", "")))
        counts = {k: sum(1 for r in rows if r["c"].status == k) for k in cardcore.STATUS_NAMES}
        frames = sorted({r["c"].frame for r in rows})
    return render(request, "cards.html", "PAGE-F21-01", "决策卡", rows=rows, counts=counts, frames=frames, channel=channel,
                  status_names=cardcore.STATUS_NAMES, channels=CHANNELS)


@router.post("/cards")
async def cards_create(request: Request, user=operator_only):
    f = await _form(request)
    ch, fr, at, va = f.get("channel", "amazon"), f.get("frame", ""), f.get("attr", ""), f.get("value", "")
    if ch not in CHANNELS or not fr or not at or not va:
        return _err(request, "/scan", "缺少渠道、框或属性取值，无法生成决策卡")
    cid = cardcore.generate(ch, fr, at, va, user.id)
    if _wants_json(request):
        return {"id": cid, "url": f"/cards/{cid}"}
    return redirect(f"/cards/{cid}", "已生成决策卡草稿")


# ---------------------------------------------------------------- 详情
def chart(points, ref=None, pct=True, ref_line=None, label=""):
    """逐季折线图几何（原型 PAGE-F21-02 的 SVG 画法：viewBox 320×140，横轴 40–300，纵轴 108 为底）。"""
    vals = [v for _, v in points if v is not None] + [v for v in (ref or []) if v is not None] + ([ref_line] if ref_line else [])
    if len(points) < 2 or not vals:
        return None
    lo = 0.0 if pct else min(vals) * 0.95
    hi = max(vals) * 1.15 or 1
    if not pct and ref_line:
        lo, hi = min(lo, ref_line * 0.95), max(hi, ref_line * 1.05)
    n = len(points)
    X = lambda i: 40 + i * 260 / (n - 1)
    Y = lambda v: 108 - (v - lo) / ((hi - lo) or 1) * 88
    fmt = (lambda v: f"{v * 100:.0f}%") if pct else (lambda v: f"{v:.2f}")
    fmt1 = (lambda v: f"{v * 100:.1f}%") if pct else (lambda v: f"{v:.2f}")
    ticks = [lo + (hi - lo) * k / 2.4 for k in range(3)]
    xl = [i for i in range(n) if i % 2 == 0 or i == n - 1]
    if n - 2 in xl and n - 1 in xl and n > 2:
        xl.remove(n - 2)
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(points) if v is not None)
    refl = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ref or []) if v is not None) if ref else ""
    dots = [dict(x=f"{X(i):.1f}", y=f"{Y(v):.1f}", tip=f"{fmt1(v)}|{q} · {label}" + (f"|同框 {fmt(ref[i])}" if ref and ref[i] is not None else ""))
            for i, (q, v) in enumerate(points) if v is not None]
    last = next(((X(i), Y(v), v) for i, (_, v) in reversed(list(enumerate(points))) if v is not None), None)
    return dict(grid=[dict(y=f"{Y(t):.1f}", ty=f"{Y(t) + 3:.1f}", t=fmt(t)) for t in ticks],
                xlabels=[dict(x=f"{X(i):.1f}", t=points[i][0][2:]) for i in xl], line=line, ref=refl, dots=dots,
                last=dict(x=f"{last[0]:.1f}", y=f"{last[1] - 9:.1f}", t=fmt1(last[2])) if last else None,
                ref_y=f"{Y(ref_line):.1f}" if ref_line else None, ref_ty=f"{Y(ref_line) - 4:.1f}" if ref_line else None)


def _view(s, c: Card, user):
    locked = c.status in cardcore.LOCKED
    snap = c.snapshot if (locked and c.snapshot) else None
    numbers = snap["numbers"] if snap else c.numbers
    profit = snap["profit"] if snap else cardcore.profit_view(s, c)
    reviews = snap["reviews"] if snap else rvcore.summary(s, c.id, c.value)
    narr = snap["narrative"] if snap else (c.narrative or {})
    prim = next((x for x in numbers["channels"] if x["channel"] == c.channel), numbers["channels"][0])
    charts = {}
    for ch in numbers["channels"]:
        qs = ch["quarters"]
        pts = lambda k: [(q["q"], q.get(k)) for q in qs]
        charts[ch["channel"]] = dict(
            share=chart(pts("share"), label=f"{c.value}份额"),
            newshare=chart(pts("newshare"), ref=[q.get("frame_newshare") for q in qs], label=c.value),
            premium=chart(pts("premium"), pct=False, ref_line=1.0, label="溢价"))
    events = []
    for e in s.scalars(select(CardEvent).where(CardEvent.card_id == c.id).order_by(CardEvent.at.desc(), CardEvent.id.desc())):
        u = s.get(User, e.user_id) if e.user_id else None
        events.append(dict(kind=e.kind, text=e.text, at=e.at.strftime("%Y-%m-%d %H:%M"), who=u.name if u else ""))
    pend = s.scalar(select(Approval).where(Approval.obj_type == "card", Approval.obj_id == c.id, Approval.status == "pending"))
    last_ok = s.scalar(select(Approval).where(Approval.obj_type == "card", Approval.obj_id == c.id, Approval.decision == "approve").order_by(Approval.id.desc()))
    fc = s.scalar(select(Forecast).where(Forecast.card_id == c.id))
    run = cardcore.latest_run(s)
    stop_defs = {x["kind"]: x for x in numbers.get("stop", [])}
    stops = [dict(st, text=stop_defs.get(st["kind"], {}).get("text", "").replace("{v}", f"{st['value']:g}"), i=i)
             for i, st in enumerate(narr.get("stop", []))]
    sub_by = s.get(User, pend.submitted_by) if pend and pend.submitted_by else None
    approver = s.get(User, last_ok.decided_by) if last_ok and last_ok.decided_by else None
    bmax = {ch["channel"]: max([b.get("obs") or 0 for b in ch["bands"]] + [1]) for ch in numbers["channels"]}
    rv_max = max([x["n"] for x in reviews["cats"]] + [1])
    return dict(card=c, name=cardcore.card_name(c), n=numbers, bmax=bmax, rv_max=rv_max, prim=prim, narr=narr, profit=profit, rv=reviews, charts=charts,
                events=events, pending=pend, pending_by=sub_by.name if sub_by else "", approved=last_ok, approver=approver.name if approver else "",
                forecast=fc, run=run, new_data=cardcore.has_new_data(s, c), stops=stops, locked=locked,
                can_edit=user.role == "operator" and c.status == "draft",
                can_approve=user.role == "approver" and c.status == "pending" and pend is not None,
                is_op=user.role == "operator", status_name=cardcore.STATUS_NAMES.get(c.status, c.status),
                cats=cardcore.REVIEW_CATS, llm_on=services.connected("llm"), missing=cardcore.missing_items(c),
                rv_estimate=rvcore.card_items(c))


@router.get("/cards/{card_id}")
def card_detail(request: Request, card_id: int, user=any_user):
    with session() as s:
        c = s.get(Card, card_id)
        if not c:
            raise HTTPException(404, "决策卡不存在")
        ctx = _view(s, c, user)
    return render(request, "card.html", "PAGE-F21-02", ctx["name"], **ctx, channels=CHANNELS)


@router.post("/cards/{card_id}/narrative")
async def card_narrative(request: Request, card_id: int, user=operator_only):
    f = await _form(request)
    try:
        n = cardcore.update_narrative(card_id, f, user.id)
    except cardcore.NumbersReadOnly as e:
        return _err(request, f"/cards/{card_id}", str(e), 409)
    if _wants_json(request):
        return {"ok": True, "saved_at": n.get("saved_at"), "consumer_ai": n.get("consumer_ai")}
    return redirect(f"/cards/{card_id}", "叙述已保存")


@router.post("/cards/{card_id}/numbers")
async def card_numbers(request: Request, card_id: int, user=operator_only):
    """数字不可直接修改（AC-F21-02）；已批准后改数字是非法迁移（技术方案 §5.1），只能另存为新草稿。"""
    with session() as s:
        c = s.get(Card, card_id)
        locked = c.status in cardcore.LOCKED
    msg = "已批准的卡不能改数字，只能另存为新草稿" if locked else "数字由系统计算，不能直接修改，只能改叙述"
    return _err(request, f"/cards/{card_id}", msg, 409)


@router.post("/cards/{card_id}/submit")
async def card_submit(request: Request, card_id: int, user=operator_only):
    f = await _form(request)
    try:
        apcore.submit_card(card_id, user.id, f.get("note", ""))
    except (apcore.ApprovalError, cardcore.IllegalTransition) as e:
        return _err(request, f"/cards/{card_id}", str(e))
    return {"ok": True} if _wants_json(request) else redirect(f"/cards/{card_id}", "已提交审批，等待老板处理；叙述已锁定")


@router.post("/cards/{card_id}/decide")
async def card_decide(request: Request, card_id: int, user=approver_only):
    f = await _form(request)
    with session() as s:
        a = s.scalar(select(Approval).where(Approval.obj_type == "card", Approval.obj_id == card_id, Approval.status == "pending"))
        aid = a.id if a else None
    if aid is None:
        return _err(request, f"/cards/{card_id}", "这条已处理")
    try:
        res = apcore.decide(aid, f.get("decision", ""), f.get("comment", ""), user.id, request.client.host if request.client else "")
    except (apcore.ApprovalError, cardcore.IllegalTransition) as e:
        return _err(request, f"/cards/{card_id}", str(e))
    msg = {"approve": f"已批准，卡片锁定为只读版本并登记预测台账 {res.get('ledger_code', '')}", "reject": "已驳回，已记录审批人、时间和意见",
           "return": "已退回修改，卡片回到草稿"}[f["decision"]]
    return {"ok": True, **res} if _wants_json(request) else redirect(f"/cards/{card_id}", msg)


@router.post("/cards/{card_id}/save-as-new")
def card_save_as(request: Request, card_id: int, user=operator_only):
    try:
        nid = cardcore.save_as_new(card_id, user.id)
    except cardcore.IllegalTransition as e:
        return _err(request, f"/cards/{card_id}", str(e))
    return {"id": nid} if _wants_json(request) else redirect(f"/cards/{nid}", "已另存为新草稿，用最新数据重新生成数字")


@router.post("/cards/{card_id}/draft")
def card_draft(request: Request, card_id: int, user=operator_only):
    """AI 起草：先估算（费用闸门），页面弹费用确认后 POST /jobs/{id}/confirm。"""
    j = costgate.estimate("llm_draft", {}, user.id, target=f"card:{card_id}")
    return {"job_id": j.id, "estimate": j.estimate}


@router.post("/cards/{card_id}/reviews/pull")
def card_reviews_pull(request: Request, card_id: int, user=operator_only):
    j = costgate.estimate("amazon_reviews", {}, user.id, target=f"card:{card_id}")
    return {"job_id": j.id, "estimate": j.estimate}


@router.post("/reviews/{review_id}/category")
async def review_category(request: Request, review_id: int, user=operator_only):
    f = await _form(request)
    try:
        cid = rvcore.set_reason(review_id, f.get("reason", ""), user.id)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except PermissionError as e:
        return JSONResponse({"detail": str(e)}, status_code=409)
    with session() as s:
        c = s.get(Card, cid)
        sm = rvcore.summary(s, cid, c.value)
    return {"ok": True, "cats": sm["cats"], "manual": sm["manual"], "classified": sm["classified"]}


@router.get("/cards/{card_id}/channels")
def card_channels(card_id: int, user=any_user):
    """API-F29-01：分渠道并排与多渠道印证 / 渠道分歧。"""
    with session() as s:
        c = s.get(Card, card_id)
        if not c:
            raise HTTPException(404, "决策卡不存在")
        n = c.snapshot["numbers"] if (c.status in cardcore.LOCKED and c.snapshot) else c.numbers
    keep = ("channel", "name", "has_data", "sample_ok", "share_prev", "share_now", "direction", "grade", "grasp", "verified",
            "families", "units", "verdict", "estimated")
    return {"channels": [{k: ch.get(k) for k in keep} for ch in n["channels"]], "marks": n["marks"]}


@router.get("/cards/{card_id}/export")
def card_export(card_id: int, user=any_user):
    from openpyxl import Workbook
    with session() as s:
        c = s.get(Card, card_id)
        n = c.snapshot["numbers"] if (c.status in cardcore.LOCKED and c.snapshot) else c.numbers
        rv = rvcore.summary(s, c.id, c.value)
        name = cardcore.card_name(c)
    wb = Workbook()
    ws = wb.active
    ws.title = "分框决策"
    ws.append(["渠道", "框内份额（前）", "框内份额（近）", "趋势", "分级", "把握", "家族数", "月销（近期月均）", "这个渠道"])
    for ch in n["channels"]:
        ws.append([ch["name"], ch["share_prev"], ch["share_now"], ch["direction"] or "样本不足", ch["grade"] or "", ch["grasp"],
                   ch["families"], ch["units"], ch["verdict"]])
    ws2 = wb.create_sheet("大数据层")
    ws2.append(["季度", "月销", "框内份额", "中位价", "溢价", "评分", "框评分", "新品占比", "框新品占比", "在榜家族"])
    prim = next(x for x in n["channels"] if x["channel"] == c.channel)
    for q in prim["quarters"]:
        ws2.append([q["q"], q["units"], q["share"], q["median_price"], q["premium"], q["rating"], q["frame_rating"], q["newshare"], q["frame_newshare"], q["families"]])
    ws3 = wb.create_sheet("SKU 层")
    ws3.append(["商品", "品牌", "规格", "首次在榜", "在榜月数", "峰值月", "峰值月销", "最好排名", "首次进前 50", "链接"])
    for k in prim["skus"]:
        ws3.append([k["item_id"], k["brand"], k["spec"], k["first_month"], k["months_listed"], k["peak_month"], k["peak_units"], k["best_rank"], k["first_top50"], k["link"]])
    ws4 = wb.create_sheet("差评归类")
    ws4.append(["原因", "条数", "占比"])
    for x in rv["cats"]:
        ws4.append([x["label"], x["n"], x["pct"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"决策卡_{name.replace(' ', '').replace('·', '_')}_v{c.version}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}"})


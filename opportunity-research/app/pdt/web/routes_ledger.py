"""预测台账（PAGE-F26-01，API-F26-01）。对账由数据并入流程调用 core.ledger.reconcile_due()。"""
import io
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from .. import catconfig
from ..auth import any_user, operator_only
from ..config import CHANNEL_NAMES, CHANNELS
from ..db import session
from ..models import Card, Forecast
from ..core import card as cardcore
from ..core import ledger as lg
from .ui import redirect, render

router = APIRouter()
CH_KEY = {"amazon": "amz", "homedepot": "hd", "lowes": "lw", "wayfair": "wf"}


def _rows(s):
    out = []
    for f in s.scalars(select(Forecast).order_by(Forecast.registered_at.desc(), Forecast.id.desc())):
        c = s.get(Card, f.card_id)
        res = f.result or {}
        judge = []
        for ch in f.channels:
            r = res.get(ch) or {}
            st = r.get("status") or ("观察中" if f.status != "unlinked" else "数据不全")
            judge.append(dict(channel=ch, name=CHANNEL_NAMES[ch], status=st, reason=r.get("reason", ""), r=r))
        stops = res.get("_stop") or []
        out.append(dict(f=f, card=c, name=cardcore.card_name(c), judge=judge, stops=stops,
                        stop_hit=any(x.get("triggered") for x in stops), chkeys=" ".join(CH_KEY[c_] for c_ in f.channels)))
    return out


@router.get("/ledger")
def ledger_page(request: Request, user=any_user):
    v, cfg = catconfig.current()
    lg.reconcile_due()  # "待关联"随日历变化，打开页面时顺带检查；已对账条目不会重判
    with session() as s:
        rows = _rows(s)
        counts = lg.counts(s)
        summ = lg.summary(s)
    unlinked = [r for r in rows if r["f"].status == "unlinked"]
    meta = {r["f"].id: dict(name=r["name"], code=r["f"].code, launch=r["f"].launch_month, channels=r["f"].channels) for r in rows}
    return render(request, "ledger.html", "PAGE-F26-01", "预测台账", rows=rows, rows_meta=meta, counts=counts, summ=summ, unlinked=unlinked,
                  cfg=cfg, cfg_version=v, is_op=user.role == "operator", status_names=lg.STATUS_NAMES, channels=CHANNELS)


@router.post("/ledger/{fid}/link-asin")
async def ledger_link(request: Request, fid: int, user=operator_only):
    f = await request.form()
    others = {ch: f.get(f"items_{ch}", "") for ch in CHANNELS if ch != "amazon"}
    try:
        lg.link_items(fid, f.get("asins", ""), f.get("actual_month", ""), others, user.id)
    except lg.LedgerError as e:
        if request.headers.get("accept", "").startswith("application/json"):
            return JSONResponse({"detail": str(e)}, status_code=400)
        return redirect("/ledger", str(e), "error")
    lg.reconcile_due()
    if request.headers.get("accept", "").startswith("application/json"):
        return {"ok": True}
    return redirect("/ledger", "已关联自家商品，从实际上架月起算 6 个月对账")


@router.get("/ledger/export")
def ledger_export(user=any_user):
    from openpyxl import Workbook
    with session() as s:
        rows = _rows(s)
    wb = Workbook()
    ws = wb.active
    ws.title = "预测台账"
    ws.append(["编号", "决策卡", "版本", "登记时间", "分级", "把握", "份额区间低", "份额区间高", "做到概率原值", "做到概率扣偏差", "预计上架", "状态"]
              + [f"{CHANNEL_NAMES[c]}判定" for c in CHANNELS] + ["停止条件触发"])
    for r in rows:
        f = r["f"]
        jd = {j["channel"]: j["status"] for j in r["judge"]}
        ws.append([f.code, r["name"], f.card_version, f.registered_at.strftime("%Y-%m-%d %H:%M"), f.grade, f.grasp, f.share_lo, f.share_hi,
                   f.prob_raw, f.prob_adj, f.launch_month, lg.STATUS_NAMES.get(f.status, f.status)] + [jd.get(c, "") for c in CHANNELS]
                  + ["是" if r["stop_hit"] else "否"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote("预测台账.xlsx")})

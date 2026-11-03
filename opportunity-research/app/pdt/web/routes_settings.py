"""密钥与大模型（PAGE-F16-01，API-F16-01）、预算与费用记录（PAGE-F16-02，API-F16-02 / API-F16-04）。仅操作者可用。

密钥只写不读：页面和接口只回传后 4 位；审计只记后 4 位（AC-F16-01、AC-F16-05、NFR-008）。
"""
import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select

from .. import auth, catconfig, costgate, services
from ..auth import operator_only
from ..config import SECRET_SLOTS, SERVICES
from ..db import session
from ..models import Budget, CostRecord, Job, Secret, now
from .ui import redirect, render

router = APIRouter()

# 各槽位依赖的功能（删除弹窗、未连接说明用）
DEPS = {
    "sellersprite": "Amazon 月度数据拉取、Amazon 差评拉取",
    "brightdata": "评论 VP 追踪的 Lowe's / Wayfair 页面采集（只采 Home Depot）",
    "apify": "评论 VP 追踪的 Lowe's / Wayfair 评论采集（只采 Home Depot）",
    "llm_claude": "看图打元素、差评归类、叙述草稿",
    "llm_openai": "看图打元素、差评归类、叙述草稿",
}
USES = {
    "sellersprite": "Amazon 月度数据拉取、Amazon 差评拉取",
    "brightdata": "评论 VP 追踪：Lowe's / Wayfair 页面采集",
    "apify": "评论 VP 追踪：Lowe's / Wayfair 评论采集",
}
STATUS_NAME = {"ok": "可用", "auth": "认证失败", "network": "网络", "quota": "额度", "error": "错误"}
PROVIDERS = {"claude": "Claude", "openai": "OpenAI"}
DEFAULT_UNIT = {"sellersprite": "calls", "brightdata": "usd", "apify": "usd", "llm": "usd"}
SOURCE_LINK = {  # 费用记录“来源”列：任务类型 → 页面
    "amazon_pull": ("Amazon 月度数据", "/data/amazon"), "tagging": ("打标确认", "/tagging"), "vision": ("打标确认", "/tagging"),
    "reviews": ("决策卡", "/cards"), "classify": ("决策卡", "/cards"), "llm_draft": ("决策卡", "/cards"),
    "vp_collect": ("评论 VP 追踪", "/tools/vp"),
}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _wants_json(request: Request) -> bool:
    return request.headers.get("accept", "").startswith("application/json")


def _llm_settings() -> dict:
    v = services.get_setting("llm", {}) or {}
    v.setdefault("provider", "claude")
    for p in PROVIDERS:
        v.setdefault(p, {})
    return v


def _slot_or_404(slot: str):
    if slot not in SECRET_SLOTS:
        raise HTTPException(404, "未知服务")


def _secret_view(slot: str):
    with session() as s:
        r = s.get(Secret, slot)
        if not r:
            return None
        return dict(last4=r.last4, updated_at=r.updated_at, test_status=r.test_status, test_msg=r.test_msg, tested_at=r.tested_at)


def _client_for(slot: str):
    """测试用客户端：大模型非当前提供方时直接用该槽位的密钥建客户端，其余走 services.client（可被假服务替换）。"""
    if slot.startswith("llm_") and slot != services.llm_slot():
        from .. import clients
        key = services.secret(slot)
        if not key:
            raise services.NotConnected("llm")
        return clients.make(slot, key, _llm_settings())
    return services.client("llm" if slot.startswith("llm_") else slot)


def _run_test(slot: str) -> tuple[str, str]:
    try:
        st, msg = _client_for(slot).test()
    except services.NotConnected as e:
        return "error", str(e)
    except Exception as e:  # 客户端构造失败等：只记类型名，不转述原文，避免带出密钥
        st, msg = "error", f"测试失败（{type(e).__name__}）"
    if st not in STATUS_NAME:
        st = "error"
    with session() as s:
        r = s.get(Secret, slot)
        if r:
            r.test_status, r.test_msg, r.tested_at = st, msg, now()
    return st, msg


# ---------------------------------------------------------------- 密钥与大模型
@router.get("/settings/keys")
def keys_page(request: Request, user=operator_only):
    llm = _llm_settings()
    cards = [dict(slot=k, name=SECRET_SLOTS[k], use=USES[k], deps=DEPS[k], sec=_secret_view(k)) for k in ("sellersprite", "brightdata", "apify")]
    slots = [dict(slot=f"llm_{p}", provider=p, name=n, deps=DEPS[f"llm_{p}"], sec=_secret_view(f"llm_{p}"), cfg=llm.get(p, {})) for p, n in PROVIDERS.items()]
    return render(request, "settings_keys.html", "PAGE-F16-01", "密钥与大模型", cards=cards, slots=slots, llm=llm,
                  providers=PROVIDERS, status_name=STATUS_NAME)


@router.post("/settings/keys/{slot}")
def save_key(request: Request, slot: str, value: str = Form(""), user=operator_only):
    _slot_or_404(slot)
    value = value.strip()
    if not value:
        return _keys_reply(request, slot, "请填写密钥", "error")
    old = _secret_view(slot)
    services.save_secret(slot, value)
    new4 = value[-4:]
    if old:
        content = f"更换 {SECRET_SLOTS[slot]} 密钥（••••{old['last4']} → ••••{new4}）"
    else:
        content = f"保存 {SECRET_SLOTS[slot]} 密钥 ••••{new4}"
    auth.audit("key", content, user.id, _ip(request))
    st, msg = _run_test(slot)  # 保存后自动测试一次
    return _keys_reply(request, slot, f"已保存，页面只显示后 4 位：••••{new4}；测试结果：{STATUS_NAME[st]}", "ok" if st == "ok" else "warn")


@router.post("/settings/keys/{slot}/test")
def test_key(request: Request, slot: str, user=operator_only):
    _slot_or_404(slot)
    if not _secret_view(slot):
        return _keys_reply(request, slot, f"{SECRET_SLOTS[slot]} 未连接：请先填写密钥", "error")
    st, msg = _run_test(slot)
    return _keys_reply(request, slot, f"{SECRET_SLOTS[slot]} 测试{'可用' if st == 'ok' else '失败：' + STATUS_NAME[st] + '，' + msg}",
                       "ok" if st == "ok" else "error")


@router.post("/settings/keys/{slot}/delete")
def delete_key(request: Request, slot: str, user=operator_only):
    _slot_or_404(slot)
    old = _secret_view(slot)
    if not old:
        return _keys_reply(request, slot, f"{SECRET_SLOTS[slot]} 本来就未连接", "warn")
    services.delete_secret(slot)
    auth.audit("key", f"删除 {SECRET_SLOTS[slot]} 密钥 ••••{old['last4']}", user.id, _ip(request))
    return _keys_reply(request, slot, f"已删除 {SECRET_SLOTS[slot]} 密钥，依赖功能显示“未连接”")


@router.post("/settings/llm")
def save_llm(request: Request, provider: str = Form(""), claude_base_url: str = Form(""), claude_model: str = Form(""),
             openai_base_url: str = Form(""), openai_model: str = Form(""), openai_price_in: str = Form(""),
             openai_price_out: str = Form(""), user=operator_only):
    llm = _llm_settings()
    old_provider = llm["provider"]
    if provider:
        if provider not in PROVIDERS:
            return redirect("/settings/keys", "提供方只能是 Claude 或 OpenAI", "error")
        llm["provider"] = provider
    llm["claude"] = dict(llm["claude"], base_url=claude_base_url.strip(), model=claude_model.strip())
    llm["openai"] = dict(llm["openai"], base_url=openai_base_url.strip(), model=openai_model.strip(),
                         price_in=openai_price_in.strip(), price_out=openai_price_out.strip())
    services.put_setting("llm", llm)
    p = llm["provider"]
    if p != old_provider:
        auth.audit("key", f"大模型提供方由 {PROVIDERS[old_provider]} 改为 {PROVIDERS[p]}", user.id, _ip(request))
        if not _secret_view(f"llm_{p}"):
            return redirect("/settings/keys", f"{PROVIDERS[p]} 尚未填写密钥，大模型功能将显示未连接", "warn")
        return redirect("/settings/keys", f"大模型提供方已改为 {PROVIDERS[p]}，看图打标、差评归类、叙述草稿都将使用 {PROVIDERS[p]}")
    auth.audit("key", "修改大模型接口地址 / 模型名", user.id, _ip(request))
    return redirect("/settings/keys", "已保存大模型设置")


def _keys_reply(request: Request, slot: str, msg: str, kind: str = "ok"):
    if _wants_json(request):
        sec = _secret_view(slot)
        return JSONResponse(dict(slot=slot, detail=msg, connected=bool(sec), last4=sec["last4"] if sec else "",
                                 test_status=sec["test_status"] if sec else "", test_msg=sec["test_msg"] if sec else ""),
                            status_code=400 if kind == "error" and not sec else 200)
    return redirect("/settings/keys", msg, kind)


# ---------------------------------------------------------------- 预算与费用记录
def service_usage(svc: str, month: str | None = None) -> dict:
    """单个服务本月花费与上限状态（工作台、预算页共用）。状态词按 DEC-104：≥ 80% 接近上限，≥ 100% 已达上限。"""
    cap, unit = costgate.budget(svc)
    amt, qty = costgate.spent(svc, month)
    unit = unit or DEFAULT_UNIT[svc]
    used = qty if unit == "calls" else amt
    ratio = (used / cap) if cap else None
    warn = (catconfig.current()[1].get("budget_warn_pct") or 80) / 100
    connected = services.connected(svc)
    if not connected:
        status = "nc"
    elif cap is None:
        status = "nocap"
    elif ratio >= 1 - 1e-9:
        status = "cap"
    elif ratio >= warn:
        status = "warn"
    else:
        status = "ok"
    name = SERVICES[svc]
    if svc == "llm":
        name = f"大模型 · {PROVIDERS[_llm_settings()['provider']]}"
    return dict(service=svc, name=name, cap=cap, unit=unit, spent_usd=amt, spent_qty=qty, used=used, ratio=ratio,
                pct=None if ratio is None else int(round(ratio * 100)), status=status, connected=connected)


def _ledger_detail(month: str, svc: str):
    with session() as s:
        q = select(CostRecord).order_by(CostRecord.at.desc(), CostRecord.id.desc())
        if month:
            q = q.where(CostRecord.month == month)
        if svc in SERVICES:
            q = q.where(CostRecord.service == svc)
        recs = list(s.scalars(q))
        kinds = {j.id: j.kind for j in s.scalars(select(Job).where(Job.id.in_({r.job_id for r in recs if r.job_id})))}
        out = []
        for r in recs:
            kind = kinds.get(r.job_id, "")
            label, href = SOURCE_LINK.get(kind, (r.source or (costgate.KINDS[kind].label if kind in costgate.KINDS else "—"), ""))
            out.append(dict(id=r.id, at=r.at, month=r.month, service=r.service, service_name=SERVICES.get(r.service, r.service),
                            task=r.task, qty=r.qty, amount=r.amount, source=r.source or label, source_href=href, job_id=r.job_id))
        return out


def _ledger_monthly():
    with session() as s:
        rows = s.execute(select(CostRecord.month, CostRecord.service, func.sum(CostRecord.amount))
                         .group_by(CostRecord.month, CostRecord.service)).all()
    by = {}
    for m, svc, amt in rows:
        by.setdefault(m, {})[svc] = float(amt or 0)
    out = []
    for m in sorted(by, reverse=True):
        d = by[m]
        out.append(dict(month=m, services={k: d.get(k) for k in SERVICES}, total=round(sum(d.values()), 6)))
    return out


@router.get("/settings/budget")
def budget_page(request: Request, tab: str = "detail", svc: str = "all", month: str = "", user=operator_only):
    cur = costgate.month_key()
    month = month or cur
    usage = [service_usage(k) for k in SERVICES]
    with session() as s:
        months = sorted({m for (m,) in s.execute(select(CostRecord.month).distinct())} | {cur}, reverse=True)
    detail = _ledger_detail(month, svc)
    return render(request, "settings_budget.html", "PAGE-F16-02", "预算与费用记录", usage=usage, services=SERVICES,
                  detail=detail[:50], detail_total=len(detail), detail_sum=sum(r["amount"] for r in detail),
                  monthly=_ledger_monthly(), month=month, cur_month=cur, months=months, fsvc=svc if svc in SERVICES else "all",
                  tab="month" if tab == "month" else "detail", llm_provider=PROVIDERS[_llm_settings()["provider"]],
                  warn_pct=catconfig.current()[1].get("budget_warn_pct") or 80, now_dt=datetime.now())


@router.post("/settings/budget")
async def save_budget(request: Request, user=operator_only):
    form = await request.form()
    changes, warns = [], []
    for svc in SERVICES:
        raw = str(form.get(f"cap_{svc}", "")).strip().replace(",", "")
        unit = str(form.get(f"unit_{svc}", DEFAULT_UNIT[svc]))
        if unit not in ("usd", "calls"):
            return redirect("/settings/budget", "计费单位只能是美元或调用次数", "error")
        if raw == "":
            continue
        try:
            cap = float(raw)
        except ValueError:
            return redirect("/settings/budget", f"{SERVICES[svc]}：请填写大于 0 的上限", "error")
        if not cap > 0:
            return redirect("/settings/budget", f"{SERVICES[svc]}：请填写大于 0 的上限", "error")
        if unit == "calls" and cap != int(cap):
            return redirect("/settings/budget", f"{SERVICES[svc]}：调用次数需为整数", "error")
        changes.append((svc, cap, unit))
    with session() as s:
        for svc, cap, unit in changes:
            b = s.get(Budget, svc)
            if b:
                b.cap, b.unit = cap, unit
            else:
                s.add(Budget(service=svc, cap=cap, unit=unit))
    for svc, cap, unit in changes:
        u = service_usage(svc)
        if u["used"] >= cap:
            spent = f"${u['spent_usd']:,.2f}" if unit == "usd" else f"{u['spent_qty']:,.0f} 次"
            warns.append(f"{SERVICES[svc]} 本月已花 {spent}，不低于新上限，已立即停止其新调用")
    if warns:
        return redirect("/settings/budget", "已保存上限。" + "；".join(warns), "warn")
    return redirect("/settings/budget", "已保存上限，立即生效")


@router.get("/settings/ledger")
def ledger_json(month: str = "", svc: str = "all", user=operator_only):
    """费用记录（API-F16-04）：明细与按月汇总。"""
    detail = _ledger_detail(month, svc)
    for r in detail:
        r["at"] = r["at"].strftime("%Y-%m-%d %H:%M:%S")
    return dict(detail=detail, monthly=_ledger_monthly(), usage=[service_usage(k) for k in SERVICES])


@router.get("/settings/ledger/export")
def ledger_export(view: str = "detail", month: str = "", svc: str = "all", user=operator_only):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    if view == "month":
        ws.title = "按月汇总"
        ws.append(["月份"] + list(SERVICES.values()) + ["合计（美元）"])
        for r in _ledger_monthly():
            ws.append([r["month"]] + [r["services"][k] for k in SERVICES] + [r["total"]])
        fn = "费用按月汇总.xlsx"
    else:
        ws.title = "费用明细"
        ws.append(["时间", "服务", "任务", "数量", "金额（美元）", "来源"])
        for r in _ledger_detail(month, svc):
            ws.append([r["at"].strftime("%Y-%m-%d %H:%M:%S"), r["service_name"], r["task"], r["qty"], r["amount"], r["source"]])
        fn = f"费用明细_{month or '全部'}.xlsx"
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}"})


# 预算页“预览费用评估弹窗”演示：零费用估算、执行时不发起任何外部调用，也不记账。
def _demo_estimate(params):
    return dict(service="sellersprite", calls=0, usd_lo=0, usd_hi=0, minutes=0,
                note="演示：本任务不会发起任何外部调用，也不产生费用")


def _demo_run(ctx):
    ctx.progress(note="演示任务，未发起调用")


costgate.register("cost_demo", "费用评估弹窗演示（不发起调用）", _demo_estimate, _demo_run)

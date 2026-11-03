"""工作台（PAGE-F15-02，API-F15-04，DEC-101）。只汇总其他模块已有的状态，按角色只读取并渲染可见区块。"""
from datetime import date

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from ..auth import any_user
from ..config import CHANNEL_NAMES, CHANNELS, SERVICES
from ..db import session
from ..models import Approval, Batch, Card, Forecast, Job, ModelRun, Strategy, Tag, User
from .ui import render

router = APIRouter()

# Batch.status → (状态词, 徽章样式, 图标)
BATCH_STATUS = {
    "suspect_month": ("疑似月份错误", "block", "warning-octagon"),
    "anomaly": ("核对异常待确认", "warn", "warning"),
    "ok": ("核对通过，待并入", "warn", "hourglass"),
    "merged": ("已并入", "ok", "check-circle"),
    "rejected": ("已退回", "miss", "prohibit"),
}
CHANNEL_PAGE = {"amazon": "/data/amazon"}


def _ym_add(ym: str, n: int) -> str:
    y, m = map(int, ym.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _data_month(today: date) -> str:
    """本月处理上月数据（PRD §3.2.1）。"""
    return _ym_add(today.strftime("%Y-%m"), -1)


def _validity(data_month: str):
    with session() as s:
        r = s.scalar(select(ModelRun).order_by(ModelRun.created_at.desc(), ModelRun.id.desc()).limit(1))
        if not r:
            return dict(kind="none")
        d = dict(month=r.month, msg=r.valid_msg, at=r.created_at)
    if not r.valid:
        d["kind"] = "fail"
    elif r.month < data_month:
        d["kind"] = "stale"
    else:
        d["kind"] = "pass"
    return d


def _data_status(data_month: str):
    rows = []
    with session() as s:
        any_batch = s.scalar(select(func.count()).select_from(Batch)) or 0
        running = {j.kind: j for j in s.scalars(select(Job).where(Job.status.in_(["running", "queued"])))}
        for ch in CHANNELS:
            b = s.scalar(select(Batch).where(Batch.channel == ch).order_by(Batch.month.desc(), Batch.created_at.desc(), Batch.id.desc()).limit(1))
            merged = s.scalar(select(Batch).where(Batch.channel == ch, Batch.status == "merged").order_by(Batch.month.desc()).limit(1))
            row = dict(channel=ch, name=CHANNEL_NAMES[ch], href=CHANNEL_PAGE.get(ch, "/data/channels"))
            job = running.get("amazon_pull") if ch == "amazon" else None
            if job:
                pct = (job.progress or {}).get("pct")
                row.update(month=job.month, label=f"拉取中{f' {pct:.0f}%' if isinstance(pct, (int, float)) else ''}", tone="warn",
                           icon="hourglass", note=(job.progress or {}).get("step", "正在拉取"), at=job.confirmed_at, action=False)
            elif not b or b.month < data_month:
                row.update(month=data_month, label="本月无数据" if b else "未拉取", tone="nodata", icon="link-simple",
                           note=f"上一批：{b.month}" if b else "", at=b.created_at if b else None, action=True)
            else:
                label, tone, icon = BATCH_STATUS.get(b.status, (b.status, "", "info"))
                if b.status == "merged" and b.star:
                    label += "*"
                note = b.anomaly_reason or (f"{b.rows:,} 行" if b.rows else "")
                row.update(month=b.month, label=label, tone=tone, icon=icon, note=note, at=b.merged_at or b.created_at,
                           action=b.status in ("suspect_month", "anomaly", "ok"))
            row["last_merged"] = (merged.month + ("*" if merged.star else "")) if merged and merged.month != row["month"] else ""
            rows.append(row)
    return rows, any_batch == 0


def _tags():
    with session() as s:
        total = s.scalar(select(func.count()).select_from(Tag).where(Tag.status == "queued")) or 0
        by_ch = dict(s.execute(select(Tag.channel, func.count()).where(Tag.status == "queued").group_by(Tag.channel)).all())
        elem = s.scalar(select(func.count()).select_from(Tag).where(Tag.status == "queued", Tag.tag == "元素")) or 0
        groups = s.scalar(select(func.count(func.distinct(Tag.img_group))).where(Tag.status == "queued", Tag.img_group != "")) or 0
    return dict(total=total, by_channel=[(CHANNEL_NAMES[c], by_ch.get(c, 0)) for c in CHANNELS], elem=elem, low=total - elem, groups=groups)


def _approvals(user):
    with session() as s:
        q = select(Approval).where(Approval.status == "pending").order_by(Approval.submitted_at.desc())
        if user.role == "operator":
            q = q.where(Approval.submitted_by == user.id)
        names = {u.id: u.name for u in s.scalars(select(User))}
        out = []
        for a in s.scalars(q):
            if a.obj_type == "card":
                c = s.get(Card, a.obj_id)
                title = f"{c.frame}｜{c.attr} = {c.value}" if c else f"决策卡 #{a.obj_id}"
                out.append(dict(icon="cards", title=title, href=f"/cards/{a.obj_id}",
                                desc=f"决策卡立项 · {names.get(a.submitted_by, '—')} 提交于 {a.submitted_at:%m-%d %H:%M}"
                                     + (f" · 主渠道 {CHANNEL_NAMES.get(c.channel, c.channel)}" if c else "")))
            else:
                st = s.get(Strategy, a.obj_id)
                out.append(dict(icon="stack", title=st.title if st else f"策略 #{a.obj_id}", href="/strategies",
                                desc=f"策略库申请改为“已验证” · {names.get(a.submitted_by, '—')} 提交于 {a.submitted_at:%m-%d %H:%M}"))
    return out


def _due():
    with session() as s:
        rows = list(s.scalars(select(Forecast).where(Forecast.status.in_(["due", "unlinked"])).order_by(Forecast.code)))
    out = []
    for f in rows:
        head = f"{f.code} · {f.frame}｜{f.attr} = {f.value}"
        if f.status == "unlinked":
            out.append(dict(icon="link-simple", tone="warn", title=head,
                            desc=f"待关联：预计上架 {f.launch_month}，已超 3 个月仍未关联自家商品"))
            continue
        parts = [f"满 6 个月：{_ym_add(f.launch_month, 5)}"]
        res = f.result or {}
        for ch in f.channels or CHANNELS:
            r = res.get(ch)
            nm = CHANNEL_NAMES.get(ch, ch)
            if not r:
                parts.append(f"{nm} 等待数据")
            elif r.get("made") is None:
                parts.append(f"{nm} 等待数据" + (f"（{r['basis']}）" if r.get("basis") else ""))
            else:
                parts.append(f"{nm} 已自动对账：{'做到' if r['made'] else '未做到'}" + (f"（{r['basis']}）" if r.get("basis") else ""))
        tone = "ok" if res and all((res.get(ch) or {}).get("made") is not None for ch in (f.channels or [])) else "warn"
        out.append(dict(icon="check-circle" if tone == "ok" else "hourglass", tone=tone, title=head, desc=" · ".join(parts)))
    return out


def _links():
    with session() as s:
        cards = dict(s.execute(select(Card.status, func.count()).group_by(Card.status)).all())
        fc = dict(s.execute(select(Forecast.status, func.count()).group_by(Forecast.status)).all())
        sts = dict(s.execute(select(Strategy.status, func.count()).group_by(Strategy.status)).all())
    nc = sum(cards.values())
    return dict(
        cards=f"{nc} 张 · 草稿 {cards.get('draft', 0)}、待审批 {cards.get('pending', 0)}、跟踪中 {cards.get('tracking', 0)}" if nc else "还没有决策卡",
        ledger=f"{sum(fc.values())} 条登记 · 已对账 {fc.get('reconciled', 0)}" if fc else "还没有登记",
        strategies=f"{sum(sts.values())} 条结论 · 已验证 {sts.get('已验证', 0)}" if sts else "还没有结论")


@router.get("/")
def home(request: Request, user=any_user):
    from .routes_settings import service_usage  # 与预算页共用状态口径
    today = date.today()
    dm = _data_month(today)
    role = user.role
    ctx = dict(data_month=dm, validity=_validity(dm), links=_links(), due=_due())
    if role == "operator":
        ctx["data_rows"], ctx["no_data"] = _data_status(dm)
        ctx["tags"] = _tags()
        ctx["spend"] = [service_usage(k) for k in SERVICES]
    if role in ("operator", "approver"):
        ctx["approvals"] = _approvals(user)
    return render(request, "home.html", "PAGE-F15-02", "工作台", **ctx)

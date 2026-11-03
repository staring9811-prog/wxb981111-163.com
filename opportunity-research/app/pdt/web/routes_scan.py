"""机会扫描（PAGE-F20-01，API-F20-01）：读预计算的 Opportunity 表（NFR-009）；历史月份没有算过时当场算一次并保存。"""
import time

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from ..auth import any_user
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, Card, Opportunity
from ..models_data import ScanMeta
from ..core import pipeline
from ..core.scan import KINDS
from .ui import render

router = APIRouter()
TYPE_KEYS = {'growth': '增长型', 'rating': '评分缺口型', 'price': '价格缺口型', 'pit': '坑'}
GRADE_KEYS = {'bt': '经回测', 'obs': '历史观察', 'un': '未验证'}
ATTR_KEYS = {'tm': '台面材质', 'el': '元素', 'color': '主色', 'body': '柜体材质'}
ICON = {'增长型': 'trend-up', '评分缺口型': 'chart-bar', '价格缺口型': 'scales', '坑': 'trend-down'}


def _meta(channel, month):
    with session() as s:
        q = select(ScanMeta).where(ScanMeta.channel == channel)
        if month:
            q = q.where(ScanMeta.month == month)
        m = s.scalar(q.order_by(ScanMeta.month.desc(), ScanMeta.id.desc()).limit(1))
        if m is not None:
            s.expunge(m)
        return m


@router.get('/scan')
def scan_page(request: Request, channel: str = 'amazon', month: str = '', frame: str = '', vars: list[str] = Query(default=[]),
              type: list[str] = Query(default=[]), grade: list[str] = Query(default=[]), user=any_user):
    t0 = time.time()
    if channel not in CHANNEL_NAMES:
        channel = 'amazon'
    meta = _meta(channel, month or None)
    if meta is None:
        with session() as s:
            has = s.scalar(select(Batch.id).where(Batch.channel == channel, Batch.status == 'merged', *( [Batch.month == month] if month else [])).limit(1))
        if has:
            pipeline.rescan(channel, month or None)
            meta = _meta(channel, month or None)
    rows, frames_all, summary = [], [], []
    vars_ = [ATTR_KEYS[v] for v in vars if v in ATTR_KEYS] or list(ATTR_KEYS.values())
    types = [TYPE_KEYS[t] for t in type if t in TYPE_KEYS]
    grades = [GRADE_KEYS[g] for g in grade if g in GRADE_KEYS]
    if meta is not None:
        with session() as s:
            ops = list(s.scalars(select(Opportunity).where(Opportunity.channel == channel, Opportunity.month == meta.month)))
            cards = {}
            for c in s.scalars(select(Card).where(Card.channel == channel)):
                cards.setdefault((c.frame, c.attr, c.value), c.id)
                cards.setdefault(('*', c.attr, c.value), c.id)
        fu = {f['frame']: f['units'] for f in meta.meta.get('frames', [])}
        frames_all = [f['frame'] for f in meta.meta.get('frames', [])]
        # 按框汇总（全部单元）
        agg = {}
        for o in ops:
            a = agg.setdefault(o.frame, {k: 0 for k in KINDS})
            for k in KINDS:
                a[k] += int(bool((o.metrics or {}).get('flags', {}).get(k)))
        summary = [dict(frame=f, units=fu.get(f, 0), **agg.get(f, {k: 0 for k in KINDS})) for f in frames_all]
        for o in ops:
            m = o.metrics or {}
            flags = [k for k in KINDS if m.get('flags', {}).get(k)]
            if not flags:
                continue
            if o.attr not in vars_ or (frame and o.frame != frame):
                continue
            if types and not set(flags) & set(types):
                continue
            ev = o.evidence
            if grades and ev not in grades:
                continue
            rows.append(dict(id=o.id, frame=o.frame, attr=o.attr, value=o.value, flags=flags, evidence=ev, m=m, frame_units=fu.get(o.frame, 0),
                             card=cards.get((o.frame, o.attr, o.value)), related=cards.get(('*', o.attr, o.value))))
        order = {f: i for i, f in enumerate(frames_all)}
        rows.sort(key=lambda r: (order.get(r['frame'], 999), min(KINDS.index(k) for k in r['flags']), -(r['m'].get('units') or 0)))
    months = pipeline.scan_months(channel)
    with session() as s:
        merged = [m for (m,) in s.execute(select(Batch.month).where(Batch.channel == channel, Batch.status == 'merged').distinct().order_by(Batch.month.desc()))]
    from ..core.channels import channel_cfg
    cfg = channel_cfg(channel) if channel != 'amazon' else None
    return render(request, 'scan.html', 'PAGE-F20-01', '机会扫描', channel=channel, meta=meta, rows=rows, summary=summary, frames=frames_all, frame=frame,
                  vars=[k for k, v in ATTR_KEYS.items() if v in vars_], types=type, grades=grade, months=sorted(set(months) | set(merged), reverse=True),
                  month=meta.month if meta else month, cfg=cfg, icon=ICON, type_keys=TYPE_KEYS, grade_keys=GRADE_KEYS, attr_keys=ATTR_KEYS,
                  elapsed=round(time.time() - t0, 2))

"""Amazon 月度数据（PAGE-F17-01，API-F17-01～03）与其他渠道数据（PAGE-F28-01，API-F28-01）。"""
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .. import services
from ..auth import any_user, operator_only
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, Job, Snapshot
from ..models_data import DataNote
from ..core import channels as chm
from ..core import ingest, pipeline
from ..core.families import mi, ms
from .routes_jobs import _job_json
from .ui import redirect, render

router = APIRouter()

STATUS = {'checking': ('核对中', 'watch'), 'suspect_month': ('疑似月份错误', 'block'), 'anomaly': ('核对异常', 'warn'), 'ok': ('核对通过', 'ok'),
          'merged': ('已并入', 'ok'), 'rejected': ('已放弃', 'insufficient'), 'superseded': ('已被新版本替换', 'insufficient'), 'reference': ('只作参考', 'incomplete')}
SOURCE = {'api': '卖家精灵接口', 'upload': '手动上传', 'v2': '第二轮导入', 'tracker': '评论 VP 追踪'}


def last_month() -> str:
    t = date.today()
    return ms(t.year * 12 + t.month - 1 - 1)


def _batch_view(b: Batch, total=None) -> dict:
    st, kind = STATUS.get(b.status, (b.status, 'insufficient'))
    src = (b.checks or {}).get('source') if b.source == 'v2' else None
    return dict(id=b.id, month=b.month, source=src or SOURCE.get(b.source, b.source), rows=b.rows, status=b.status, status_name=st + ('*' if b.star and b.status == 'merged' else ''),
                kind='warn' if b.star and b.status == 'merged' else kind, star=b.star, reason=b.anomaly_reason, merged_at=b.merged_at, created_at=b.created_at,
                checks=b.checks or {}, total=total, job_id=b.job_id)


def _check_total(b: Batch):
    return next((i.get('cur_total') for i in (b.checks or {}).get('items') or [] if i.get('key') == 'total_change'), None)


@router.get('/data/amazon')
def amazon_page(request: Request, batch: int | None = None, user=operator_only):
    with session() as s:
        bs = list(s.scalars(select(Batch).where(Batch.channel == 'amazon').order_by(Batch.month.desc(), Batch.id.desc())))
        totals = dict(s.execute(select(Snapshot.batch_id, func.sum(Snapshot.units)).where(Snapshot.channel == 'amazon').group_by(Snapshot.batch_id)).all())
        jobs = list(s.scalars(select(Job).where(Job.kind == 'amazon_pull').order_by(Job.id.desc()).limit(10)))
        for j in jobs:
            s.expunge(j)
        notes = {n.batch_id: n.text for n in s.scalars(select(DataNote).where(DataNote.kind == 'anomaly_confirm'))}
        # 品类总月销：本批快照合计；未并入批次同样显示（与核对表“品类总月销变化”的本批数同一口径），没有快照时取核对结果
        views = [_batch_view(b, totals.get(b.id) if totals.get(b.id) is not None else _check_total(b)) for b in bs]
    for v in views:
        v['note'] = notes.get(v['id'], '')
    # 当前批次：指定的；否则最新一个待处理（核对中 / 疑似 / 异常 / 通过）；否则最近并入的
    cur = next((v for v in views if v['id'] == batch), None) if batch else None
    if cur is None:
        cur = next((v for v in views if v['status'] in ('checking', 'suspect_month', 'anomaly', 'ok')), None)
    if cur is None:
        cur = next((v for v in views if v['status'] == 'merged'), None)
    latest = {}
    for j in jobs:  # 每个月份只看最近一次拉取任务（已确认过的）
        if j.status not in ('estimated', 'cancelled') and j.month not in latest:
            latest[j.month] = j
    active = next((j for j in latest.values() if j.status in ('running', 'queued', 'paused', 'stopped_cap', 'failed')
                   and not (j.progress or {}).get('batch_id') and not (j.progress or {}).get('duplicate')), None)
    # 历史：每月显示最新的非替换版本
    hist, seen = [], set()
    for v in views:
        if v['month'] in seen or v['status'] == 'superseded':
            continue
        seen.add(v['month'])
        hist.append(v)
    cur_month = cur['month'] if cur else last_month()
    segs = ingest.pull_segments(active.month if active else cur_month)
    months = [ms(mi(last_month()) - i) for i in range(36)]
    return render(request, 'data_amazon.html', 'PAGE-F17-01', 'Amazon 月度数据', cur=cur, hist=hist, active=_job_json(active) if active else None,
                  segs=segs, default_month=last_month(), months=months, connected=services.connected('sellersprite'), n_hist=len(hist))


@router.post('/data/amazon/pull')
def pull(request: Request, month: str = Form(''), user=operator_only):
    """API-F17-01：按月份发起拉取（估算，返回任务；确认走 /jobs/{id}/confirm）。同月重复发起返回同一任务。"""
    month = month or last_month()
    try:
        j = ingest.start_pull(month, user.id)
    except services.NotConnected as e:
        return JSONResponse({'detail': str(e)}, status_code=400)
    return _job_json(j)


@router.post('/data/amazon/upload')
async def upload(request: Request, month: str = Form(...), file: UploadFile = File(...), user=operator_only):
    """API-F17-02：手动上传卖家精灵导出（后备）。"""
    content = await file.read()
    try:
        bid = ingest.upload(month, file.filename or 'upload.xlsx', content)
    except ingest.FileFormatError as e:
        return redirect('/data/amazon', str(e), 'error')
    with session() as s:
        b = s.get(Batch, bid)
        st = STATUS.get(b.status, (b.status,))[0]
    return redirect(f'/data/amazon?batch={bid}', f'已上传 {file.filename}，{month} 核对结果：{st}', 'warn' if b.status != 'ok' else 'ok')


@router.get('/data/batches')
def batches(channel: str = 'amazon', user=any_user):
    """API-F17-03：批次与核对结果。"""
    with session() as s:
        return [dict(id=b.id, channel=b.channel, month=b.month, source=b.source, status=b.status, star=b.star, reason=b.anomaly_reason,
                     rows=b.rows, checks=b.checks, merged_at=str(b.merged_at or ''))
                for b in s.scalars(select(Batch).where(Batch.channel == channel).order_by(Batch.month.desc(), Batch.id.desc()))]


@router.post('/data/batches/{batch_id}/merge')
def merge(batch_id: int, confirm: int = Form(0), note: str = Form(''), user=operator_only):
    ok, msg = ingest.merge(batch_id, user.id, note.strip(), confirm_anomaly=bool(confirm))
    return redirect(f'/data/amazon?batch={batch_id}', msg, 'ok' if ok else 'error')


@router.post('/data/batches/{batch_id}/reject')
def reject(batch_id: int, user=operator_only):
    ok = ingest.reject(batch_id, user.id)
    return redirect('/data/amazon', '已放弃本批，原始数据保留' if ok else '该批次不能放弃', 'ok' if ok else 'error')


# ---------------- 其他渠道 ----------------
@router.get('/data/channels')
def channels_page(request: Request, ch: str = 'homedepot', user=operator_only):
    summ = chm.summary()
    if ch not in CHANNEL_NAMES or ch == 'amazon':
        ch = 'homedepot'
    with session() as s:
        recent = list(s.scalars(select(Batch).where(Batch.channel.in_(['homedepot', 'lowes', 'wayfair'])).order_by(Batch.created_at.desc(), Batch.id.desc()).limit(60)))
        page_tot = {}
        for c, m, v, n in s.execute(select(Snapshot.channel, Snapshot.month, func.sum(Snapshot.vp), func.sum(Snapshot.nonvp))
                                    .join(Batch, Batch.id == Snapshot.batch_id).where(Batch.status == 'merged', Snapshot.channel != 'amazon')
                                    .group_by(Snapshot.channel, Snapshot.month)):
            page_tot[(c, m)] = (v or 0) + (n or 0)
    imports = {}
    for b in recent:
        k = (b.source, b.file_path, b.created_at.strftime('%Y-%m-%d %H:%M'))
        d = imports.setdefault(k, dict(source=SOURCE.get(b.source, b.source), file=b.file_path.split('/')[-1] if b.file_path else '', at=k[2], channels=set(), months=set(), reference=set()))
        d['channels'].add(CHANNEL_NAMES[b.channel])
        (d['reference'] if b.status == 'reference' else d['months']).add(b.month)
    months = sorted({m['month'] for v in summ.values() for m in v['months'] if m['complete']})
    dedup = {}
    for c, v in summ.items():
        if v['last']:
            last = next(m for m in v['months'] if m['month'] == v['last'])
            dedup[c] = dict(month=v['last'], page=page_tot.get((c, v['last']), 0), dedup=last['reviews'])
    return render(request, 'data_channels.html', 'PAGE-F28-01', '其他渠道数据', summ=summ, ch=ch, months=months, imports=list(imports.values())[:6],
                  compare=chm.compare(ch, 20) if ch in summ else [], dedup=dedup)


@router.post('/data/channels/import')
async def channels_import(request: Request, file: UploadFile = File(...), user=operator_only):
    """API-F28-01：上传评论 VP 追踪器导出（含“商品月度明细”表）。"""
    content = await file.read()
    p = chm.save_upload(file.filename or 'vp.xlsx', content)
    try:
        st = chm.import_excel(p, 'upload')
    except ValueError as e:
        return redirect('/data/channels', str(e), 'error')
    for c in ('homedepot', 'lowes', 'wayfair'):
        if c in st:
            pipeline.after_merge(c, '')
    parts = [f"{CHANNEL_NAMES[c]} {v['months']} 个完整月" + (f"、{v['reference']} 个月只作参考" if v['reference'] else '') for c, v in st.items() if not c.startswith('_')]
    return redirect('/data/channels', '已并入：' + '；'.join(parts) + '。评论按 ID 去重，新商品已规则打标')


@router.get('/data/channels/estimate')
def channels_estimate(channel: str = 'homedepot', method: str = 'review', user=any_user):
    """两种估算方法对照（JSON）。"""
    if channel not in ('homedepot', 'lowes', 'wayfair'):
        raise HTTPException(404, '未知渠道')
    fit, why, n = chm.rank_fit(channel)
    return dict(channel=channel, method=method, cfg=chm.channel_cfg(channel), rank_available=fit is not None, reason=why, anchors=n, rows=chm.compare(channel, 200))

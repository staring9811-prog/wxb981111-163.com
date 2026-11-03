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
from ..models_data import ChannelFamily, ChannelPageSpec, DataNote
from ..core import channels as chm
from ..core import backfill, ingest, pipeline
from ..core.families import mi, ms
from .routes_jobs import _job_json
from .ui import redirect, render

router = APIRouter()

STATUS = {'checking': ('核对中', 'watch'), 'suspect_month': ('疑似月份错误', 'block'), 'anomaly': ('核对异常', 'warn'), 'ok': ('核对通过', 'ok'),
          'merged': ('已并入', 'ok'), 'rejected': ('已放弃', 'insufficient'), 'superseded': ('已被新版本替换', 'insufficient'), 'reference': ('只作参考', 'incomplete')}
SOURCE = {'api': '卖家精灵接口', 'upload': '手动上传', 'v2': '第二轮导入', 'tracker': '评论 VP 追踪', 'backfill': '历史回补重建'}


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


@router.post('/data/amazon/pull/{job_id}/abandon')
def abandon(job_id: int, user=operator_only):
    """拉取中 / 已暂停时“放弃本批”（二次确认后提交）：任务记为已取消，已拉分片保留在原始文件目录，不并入。"""
    ok, msg = ingest.abandon_pull(job_id, user.id)
    return redirect('/data/amazon', msg, 'ok' if ok else 'error')


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
def channels_page(request: Request, ch: str = 'homedepot', fp: int = 1, user=operator_only):
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
        fn = b.file_path.split('/')[-1] if b.file_path else ''
        if b.source == 'backfill':  # 回补缓存目录以渠道键命名，显示中文渠道名
            fn = f"{CHANNEL_NAMES.get(fn, fn)} 回补缓存" if fn else ''
        d = imports.setdefault(k, dict(source=SOURCE.get(b.source, b.source), file=fn, at=k[2], channels=set(), months=set(), reference=set()))
        d['channels'].add(CHANNEL_NAMES[b.channel])
        (d['reference'] if b.status == 'reference' else d['months']).add(b.month)
    months = sorted({m['month'] for v in summ.values() for m in v['months'] if m['complete']})[-12:]  # 月度并入状态只列近 12 个月（历史重建另列）
    # 页面副标题按实际数据范围（各渠道完整月的最早至最晚）；月度表“所列月份合计”只加表中所列月份
    span = (min(v['first'] for v in summ.values() if v['first']), max(v['last'] for v in summ.values() if v['last'])) if any(v['first'] for v in summ.values()) else None
    listed_total = {c: sum(m['reviews'] for m in v['months'] if m['complete'] and m['month'] in months) for c, v in summ.items()}
    dedup = {}
    for c, v in summ.items():
        if v['last']:
            last = next(m for m in v['months'] if m['month'] == v['last'])
            dedup[c] = dict(month=v['last'], page=page_tot.get((c, v['last']), 0), dedup=last['reviews'])
    rebuild = {c: backfill.last_rebuild(c) for c in ('homedepot', 'lowes', 'wayfair')}
    fam_ch = next((c for c in ([ch] + list(rebuild)) if rebuild.get(c)), None)
    fams, n_fams, fpages = _families(fam_ch, fp) if fam_ch else ([], 0, 1)
    return render(request, 'data_channels.html', 'PAGE-F28-01', '其他渠道数据', summ=summ, ch=ch, months=months, span=span, listed_total=listed_total,
                  imports=list(imports.values())[:6],
                  compare=chm.compare(ch, 20) if ch in summ else [], dedup=dedup, rebuild=rebuild, fam_ch=fam_ch, fams=fams, n_fams=n_fams,
                  fp=min(max(1, fp), fpages), fpages=fpages, fam_per=FAM_PER)


FAM_PER = 50


def _families(channel: str, page: int):
    """评论家族列表（按起始月以来评论数排，每页 50 个）与成员商品页（家族抽屉）。"""
    with session() as s:
        rows = list(s.scalars(select(ChannelFamily).where(ChannelFamily.channel == channel)
                              .order_by(ChannelFamily.reviews_window.desc(), ChannelFamily.best_rank)))
        pages = max(1, -(-len(rows) // FAM_PER))
        page = min(max(1, page), pages)
        cur = rows[(page - 1) * FAM_PER:page * FAM_PER]
        ids = [p for f in cur for p in f.members]
        spec = {r.item_id: r for r in s.scalars(select(ChannelPageSpec).where(ChannelPageSpec.channel == channel, ChannelPageSpec.item_id.in_(ids)))} if ids else {}
        out = []
        for f in cur:
            out.append(dict(key=f.family_key, brand=f.brand, title=f.title, members=f.members, n_variants=len(f.variants or []), best_rank=f.best_rank,
                            first=f.first_review, status=f.status, sharded=f.sharded, complete_to=f.complete_to, note=f.note,
                            reviews=f.reviews_window, vp=(f.vp_window / f.reviews_window) if f.reviews_window else None,
                            member_rows=[dict(item_id=p, title=(spec[p].title if p in spec else ''), rank=(spec[p].rank if p in spec else None),
                                              entry=(spec[p].entry if p in spec else ''), price=(spec[p].price if p in spec else None)) for p in f.members]))
    return out, len(rows), pages


@router.post('/data/channels/{channel}/rebuild')
def channels_rebuild(channel: str, user=operator_only):
    """API-F28-02：用已有回补缓存重建历史（参数取品类配置当前版本）。"""
    if channel not in ('homedepot', 'lowes', 'wayfair'):
        raise HTTPException(404, '未知渠道')
    try:
        st = backfill.rebuild_from_cache(channel, log=lambda *a: None)
    except ValueError as e:
        return redirect('/data/channels#rebuild', str(e), 'error')
    return redirect(f'/data/channels?ch={channel}#rebuild', f"已重建 {CHANNEL_NAMES[channel]} {st['start']} 至 {st['end']}：{st['pages_listed']} 个商品页、"
                    f"{st['families']} 个评论家族、评论 {st['reviews_window']:,} 条")


@router.get('/data/channels/{channel}/history')
def channels_history(channel: str, user=any_user):
    """API-F28-02：重建历史的月份范围、商品页 / 家族 / 评论数、截断、覆盖估计、前 50 重合率、季度历史。"""
    if channel not in ('homedepot', 'lowes', 'wayfair'):
        raise HTTPException(404, '未知渠道')
    rb = backfill.last_rebuild(channel)
    if not rb:
        return JSONResponse({'detail': f'{CHANNEL_NAMES[channel]} 还没有历史重建（未回补 · 未验证）'}, status_code=404)
    return dict(channel=channel, at=rb['at'], params=rb['params'], **rb['stats'])


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

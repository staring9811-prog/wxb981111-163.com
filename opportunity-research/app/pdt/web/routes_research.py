"""渠道调研（PAGE-F30-01 框列表、PAGE-F30-02 框详情：API-F30-02；PAGE-F30-03 渠道调研导入：API-F30-01）。"""
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ..auth import any_user, operator_only
from ..config import CHANNEL_NAMES
from ..core import research as R
from .ui import redirect, render

router = APIRouter()

READ = {'small': ('样本少，只作参考', 'insufficient', 'info'), 'ok': ('可读', 'pass', 'check-circle'), 'notrend': ('趋势不下结论', 'unverified', 'warning'), 'noconc': ('不下结论', 'insufficient', 'prohibit')}
TREND = {'抢份额': 'hit', '丢份额': 'miss', '随框': 'watch', '新出现': 'accent'}


def _wants_json(request: Request) -> bool:
    return request.headers.get('accept', '').startswith('application/json') or request.query_params.get('format') == 'json'


def _ctx(channel: str):
    st = R.status_all()
    r = R.result(channel)
    data = r.data if r is not None and st[channel]['state'] != 'none' else None
    return st, r, data


@router.get('/research')
def research_page(request: Request, channel: str = '', readable: int = 0, user=any_user):
    ch = channel if channel in R.CHANNELS else 'homedepot'
    st, r, data = _ctx(ch)
    if _wants_json(request):
        return JSONResponse(dict(channel=ch, status={k: dict(state=v['state'], readable=v.get('readable'), big=v.get('big'), pending=v.get('pending'))
                                                     for k, v in st.items()},
                                 data=data, computed_at=str(r.computed_at) if r is not None and r.computed_at else None,
                                 recompute_status=r.status if r is not None else None, error=r.error if r is not None else ''))
    frames = (data or {}).get('frames', [])
    shown = [f for f in frames if f['read'] == 'ok'] if readable else frames
    pend_imp = R.pending_import() if user.role == 'operator' else None
    ver = st[ch].get('version')
    return render(request, 'research.html', 'PAGE-F30-01', '渠道调研', ch=ch, st=st, res=r, data=data, frames=shown, n_frames=len(frames),
                  readable=readable, READ=READ, ver=ver, pend_imp=pend_imp, slug=R.slug, records=None)


@router.get('/research/{channel}/frame/{key}')
def frame_page(request: Request, channel: str, key: str, attr: str = '', user=any_user):
    if channel not in R.CHANNELS:
        return redirect('/research', '没有这个渠道', 'error')
    st, r, data = _ctx(channel)
    frames = (data or {}).get('frames', [])
    idx = next((i for i, f in enumerate(frames) if f['slug'] == key), None)
    if idx is None:
        if _wants_json(request):
            return JSONResponse({'detail': '这个框没有达到月均 200 件的门槛'}, status_code=404)
        return render(request, 'research_frame.html', 'PAGE-F30-02', '渠道调研 · 框详情', ch=channel, st=st, res=r, data=data, f=None, key=key)
    f = frames[idx]
    units = data['units'].get(f['frame'], [])
    marks = R.backtest_marks(channel)
    for u in units:
        m = marks.get(f"{f['frame']}|{u['attr']}|{u['value']}")
        u['backtest'] = m
    if _wants_json(request):
        return JSONResponse(dict(channel=channel, frame=f, units=units, trend_ok=data.get('trend_ok'), summary=data['summary']))
    shown = [u for u in units if not attr or u['attr'] == attr]
    return render(request, 'research_frame.html', 'PAGE-F30-02', f"渠道调研 · {f['frame']}", ch=channel, st=st, res=r, data=data, f=f, units=shown,
                  n_units=len(units), attr=attr if attr in R.ATTRS else '', attrs=R.ATTRS, READ=READ, TREND=TREND, key=key,
                  prev=frames[idx - 1]['slug'] if idx > 0 else None, next=frames[idx + 1]['slug'] if idx + 1 < len(frames) else None)


# ---------------- 导入（PAGE-F30-03，仅操作者） ----------------
def _import_page(request: Request, problems=None, files=None, status_code: int = 200):
    imp = R.pending_import()
    resp = render(request, 'data_research.html', 'PAGE-F30-03', '渠道调研导入', imp=imp, problems=problems, files=files or {},
                  records=R.records(), st=R.status_all())
    resp.status_code = status_code
    return resp


@router.get('/data/research')
def import_page(request: Request, user=operator_only):
    return _import_page(request)


@router.post('/data/research/check')
async def import_check(request: Request, products: UploadFile = File(...), monthly: UploadFile = File(...), user=operator_only):
    pb, mb = await products.read(), await monthly.read()
    probs, iid = R.start_import(products.filename or '商品表.csv', pb, monthly.filename or '月销表.csv', mb, user.id)
    if probs:
        if _wants_json(request):
            return JSONResponse({'detail': '未导入，当前调研数据不变', 'problems': probs}, status_code=400)
        return _import_page(request, problems=probs, files=dict(products=products.filename, monthly=monthly.filename), status_code=400)
    if _wants_json(request):
        imp = R.pending_import()
        return JSONResponse({'import_id': iid, 'summary': imp.summary})
    return redirect('/data/research', '检查通过，请核对摘要后确认导入')


@router.post('/data/research/{import_id}/confirm')
async def import_confirm(request: Request, import_id: int, user=operator_only):
    form = await request.form()
    chs = [c for c in form.getlist('channels') if c in R.CHANNELS]
    try:
        done = R.confirm_import(import_id, chs, user.id)
    except ValueError as e:
        if _wants_json(request):
            return JSONResponse({'detail': str(e)}, status_code=400)
        return redirect('/data/research', str(e), 'error')
    pend = sum(R.pending_count(c) for c in done)
    names = '、'.join(CHANNEL_NAMES[c] for c in done)
    if _wants_json(request):
        return JSONResponse({'imported': done, 'pending': pend})
    return redirect(f'/research?channel={done[0]}', f'已导入 {names}；分框待确认 {pend} 条已进打标确认')


@router.post('/data/research/{import_id}/abandon')
def import_abandon(request: Request, import_id: int, user=operator_only):
    ok = R.abandon(import_id)
    if _wants_json(request):
        return JSONResponse({'abandoned': ok}, status_code=200 if ok else 400)
    return redirect('/data/research', '已放弃本次导入，当前调研数据不变' if ok else '这次导入已确认或已放弃', 'ok' if ok else 'error')


@router.get('/data/research/log')
def import_log(user=operator_only):
    return [dict(r, at=r['at'].strftime('%Y-%m-%d %H:%M')) for r in R.records()]


# ---------------- 分框确认（打标确认页的"分框未知（渠道调研）"条目，AC-F30-28、AC-F30-29） ----------------
@router.post('/tagging/research/confirm')
def research_confirm(request: Request, channel: str = Form(...), pid: str = Form(...), tag: str = Form(...), value: str = Form(''),
                     back: str = Form('/tagging?reason=frame'), user=operator_only):
    if channel not in R.CHANNELS:
        return redirect(back, '没有这个渠道', 'error')
    try:
        ok, err = R.confirm(channel, pid, tag, value.strip(), user.id)
    except ValueError as e:
        if _wants_json(request):
            return JSONResponse({'detail': str(e)}, status_code=400)
        return redirect(back, str(e), 'error')
    r = R.result(channel)
    at = r.computed_at.strftime('%H:%M') if r is not None and r.computed_at else ''
    if _wants_json(request):
        return JSONResponse({'recomputed': ok, 'error': err, 'computed_at': str(r.computed_at) if r and r.computed_at else None})
    if not ok:
        return redirect(back, f'已确认；{CHANNEL_NAMES[channel]} 渠道调研重算出错：{err}，渠道调研显示的是上次结果', 'error')
    return redirect(back, f'已把 {pid} 的{tag}确认为 {value}；{CHANNEL_NAMES[channel]} 渠道调研已重算（{at}），此确认也用于机会扫描')

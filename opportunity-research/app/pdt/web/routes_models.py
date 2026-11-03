"""模型与回测（PAGE-F19-01，API-F19-01）。重算是本地计算，不花钱、不弹费用评估；同一时间只跑一个。"""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from ..auth import any_user, operator_only, roles
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, ModelRun
from ..core import pipeline, tagging
from .ui import redirect, render

router = APIRouter()
NAMES = {'b6': '份额斜率（近 6 个月每月对数变化）', 'x5': '新品占比（近 6 个月新上架家族的销量占比 − 品类整体）', 'x3': '搜索同比',
         'x4': '体量（ln 月均销，中心化）', 'x2': '新进家族（相对增长）'}


def prerequisites():
    with session() as s:
        last = {ch: s.scalar(select(func.max(Batch.month)).where(Batch.channel == ch, Batch.status == 'merged')) for ch in CHANNEL_NAMES}
        merged_at = s.scalar(select(func.max(Batch.merged_at)).where(Batch.channel == 'amazon', Batch.status == 'merged'))
    pending = tagging.pending_for_month('amazon', last['amazon']) if last['amazon'] else 0
    return dict(last=last, merged_at=merged_at, pending=pending)


@router.get('/models')
def page(request: Request, user=roles('operator', 'approver')):
    run = pipeline.latest_run()
    pre = prerequisites()
    st = pipeline.rescore_state()
    reason = ''
    if not pre['last']['amazon']:
        reason = '还没有已并入的 Amazon 数据'
    elif pre['pending']:
        reason = f"{pre['last']['amazon']} 还有 {pre['pending']} 条标签待确认，确认完才能重算"
    elif st['running']:
        reason = '正在重算'
    bt = (run.backtest or {}) if run else {}
    side = {}
    for r in bt.get('side', []):
        if r['k'] == 6:
            side.setdefault(r['T0'], {})[r['ver']] = r
    return render(request, 'models.html', 'PAGE-F19-01', '模型与回测', run=run, bt=bt, pre=pre, state=st, reason=reason, names=NAMES, side=side,
                  newlayer=(run.newlayer or {}) if run else {}, market=(run.market or {}) if run else {})


@router.post('/models/rescore')
def rescore(request: Request, user=operator_only):
    """API-F19-01：重算评分（含滚动回测）。前置：最新月标签无待确认。"""
    pre = prerequisites()
    if not pre['last']['amazon']:
        return redirect('/models', '还没有已并入的 Amazon 数据', 'error')
    if pre['pending']:
        return redirect('/models', f"{pre['last']['amazon']} 还有 {pre['pending']} 条标签待确认，确认完才能重算", 'error')
    ok, msg = pipeline.start_rescore(user.id)  # 重算内含该月机会扫描的预计算
    st = pipeline.rescore_state()
    if st['error']:
        return redirect('/models', '重算失败：' + st['error'], 'error')
    return redirect('/models', msg if not ok or st['running'] else '重算完成', 'ok' if ok else 'warn')


@router.post('/models/backtest')
def backtest(request: Request, user=operator_only):
    return rescore(request, user)


@router.get('/models/runs/{run_id}')
def run_json(run_id: int, user=any_user):
    with session() as s:
        r = s.get(ModelRun, run_id)
        if r is None:
            raise HTTPException(404, '没有这次重算')
        return dict(id=r.id, month=r.month, version=r.version, created_at=str(r.created_at), valid=r.valid, valid_msg=r.valid_msg,
                    market=r.market, newlayer=r.newlayer, backtest=r.backtest)


@router.get('/models/state')
def state(user=any_user):
    st = pipeline.rescore_state()
    return dict(running=st['running'], step=st['step'], error=st['error'], last_run=st['last_run'])

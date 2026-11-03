"""模型与回测（PAGE-F19-01，API-F19-01）。重算是本地计算，不花钱、不弹费用评估；同一时间只跑一个。"""
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from ..auth import any_user, operator_only, roles
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, ModelRun, UnitScore
from ..core import pipeline, tagging
from .ui import redirect, render

router = APIRouter()
NAMES = {'b6': '份额斜率（近 6 个月每月对数变化）', 'x5': '新品占比（近 6 个月新上架家族的销量占比 − 品类整体）', 'x3': '搜索同比',
         'x4': '体量（ln 月均销，中心化）', 'x2': '新进家族（相对增长）'}


# 未并入批次状态 → 前置清单里的说明
UNMERGED = {'suspect_month': '疑似月份错误 / 待确认', 'anomaly': '核对异常 / 待确认', 'ok': '核对通过 / 待并入', 'checking': '核对中'}


def prerequisites():
    """重算前置。最新已并入月份已算过、且有更新月份的批次未并入时，blocked 说明原因（不再重算已算过的月份）。"""
    with session() as s:
        last = {ch: s.scalar(select(func.max(Batch.month)).where(Batch.channel == ch, Batch.status == 'merged')) for ch in CHANNEL_NAMES}
        merged_at = s.scalar(select(func.max(Batch.merged_at)).where(Batch.channel == 'amazon', Batch.status == 'merged'))
        newer = None
        if last['amazon']:
            newer = s.scalar(select(Batch).where(Batch.channel == 'amazon', Batch.month > last['amazon'], Batch.status.in_(list(UNMERGED)))
                             .order_by(Batch.month.desc(), Batch.id.desc()).limit(1))
        done = bool(last['amazon']) and (s.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.month == last['amazon'])) or 0) > 0
        unmerged = dict(month=newer.month, label=UNMERGED[newer.status]) if newer is not None else None
    pending = tagging.pending_for_month('amazon', last['amazon']) if last['amazon'] else 0
    # 其他渠道的待确认标签不影响 Amazon 市场层重算，但要在前置清单里如实写出，不能只写“无待确认”
    other_pending = max(0, tagging.queued_count() - pending)
    blocked = f"{unmerged['month']} 未并入（{unmerged['label']}），并入后才能重算" if unmerged and done else ''
    return dict(last=last, merged_at=merged_at, pending=pending, other_pending=other_pending, unmerged=unmerged, done=done, blocked=blocked,
                next=unmerged['month'] if blocked else last['amazon'])


@router.get('/models')
def page(request: Request, user=roles('operator', 'approver')):
    run = pipeline.latest_run()
    pre = prerequisites()
    st = pipeline.rescore_state()
    reason = ''
    if not pre['last']['amazon']:
        reason = '还没有已并入的 Amazon 数据'
    elif pre['blocked']:
        reason = pre['blocked']
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
    if pre['blocked']:
        return redirect('/models', pre['blocked'], 'error')
    if pre['pending']:
        return redirect('/models', f"{pre['last']['amazon']} 还有 {pre['pending']} 条标签待确认，确认完才能重算", 'error')
    ok, msg = pipeline.start_rescore(user.id)  # 重算内含该月机会扫描的预计算
    st = pipeline.rescore_state()
    if st['error']:
        return redirect('/models', '重算失败：' + st['error'], 'error')
    return redirect('/models', msg if not ok or st['running'] else '重算完成', 'ok' if ok else 'warn')


@router.get('/models/export')
def export(user=roles('operator', 'approver')):
    """导出本次评分与回测结果（与页面各表同列）。"""
    from openpyxl import Workbook
    run = pipeline.latest_run()
    if run is None:
        return redirect('/models', '还没有重算结果，无可导出', 'error')
    bt, nl, market = run.backtest or {}, run.newlayer or {}, run.market or {}
    with session() as s:
        units = list(s.scalars(select(UnitScore).where(UnitScore.run_id == run.id).order_by(UnitScore.channel, UnitScore.frame, UnitScore.attr, UnitScore.value)))
    wb = Workbook()
    ws = wb.active
    ws.title = '本次评分'
    ws.append(['渠道', '分框', '属性', '取值', '把握', '分级', '当前份额', '预测份额', '80%区间低', '80%区间高', '预计多卖（件/月）', '预测窗口（月）',
               '做到概率原值', '做到概率扣偏差'])
    for u in units:
        d = u.data or {}
        ws.append([CHANNEL_NAMES.get(u.channel, u.channel), u.frame, u.attr, u.value, d.get('grasp'), d.get('grade'), d.get('share_now'), d.get('pred_share'),
                   d.get('pred_lo'), d.get('pred_hi'), d.get('extra_units'), d.get('k_months'), d.get('prob_raw'), d.get('prob_adj')])
    ws = wb.create_sheet('分级回测')
    ws.append(['分级', '本次单元数', '回测单元数', '实际变大比例', '实际多卖合计', '实际多卖中位'])
    for g in bt.get('grades') or []:
        ws.append([g.get('grade'), (market.get('grades') or {}).get(g.get('grade'), 0), g.get('n'), g.get('up'), g.get('extra'), g.get('median')])
    ws = wb.create_sheet('系数')
    ws.append(['特征', '意思', 'b（k = 0）', 'c（每多 3 个月）', 'k = 6 合计', 'k = 8 合计'])
    for x in ['b6', 'x5', 'x3', 'x4', 'x2', '截距']:
        cf = (bt.get('coef') or {}).get(x)
        if cf:
            ws.append([x, NAMES.get(x, 'a / θ；另按（体量档, k）纠偏'), cf.get('b'), cf.get('c'), cf.get('k6'), cf.get('k8')])
    ws = wb.create_sheet('把握分档')
    ws.append(['把握分档', '单元数', '其中 ≥ 300 件', '实际变大比例', '实际多卖（件/月）'])
    for g in bt.get('grasp_bins') or []:
        ws.append([g.get('bin'), g.get('n'), g.get('n300'), g.get('up'), g.get('extra')])
    ws = wb.create_sheet('新品层')
    ws.append(['立项时点 T0', '训练新家族', '检验新家族', '实际每 10 个做到', 'AUC', '打分前 30%', '打分后 30%', '模型平均 (a)', '模型平均 (b)', '模型平均 (c)', '用途'])
    for r in nl.get('rows') or []:
        ws.append([r.get('T0'), r.get('n_train'), r.get('n_test'), r.get('actual'), r.get('auc'), r.get('top30'), r.get('bottom30'),
                   r.get('mean_a'), r.get('mean_b'), r.get('mean_c'), r.get('use')])
    ws = wb.create_sheet('与第八版并排')
    ws.append(['时点', '版本', '结果月份', '秩相关（全部）', '秩相关（≥ 300 件）', '方向对（≥ 300 件）', '80% 区间覆盖', '把握 ≥ 70% 之后变大', 'n', '把握 ≤ 30% 之后变大', 'n'])
    for r in sorted(bt.get('side') or [], key=lambda r: (r.get('T0') or '', r.get('ver') or 0)):
        if r.get('k') != 6:
            continue
        hi, lo = r.get('hi') or [None, 0], r.get('lo') or [None, 0]
        ws.append([r.get('T0'), f"第{'八' if r.get('ver') == 8 else '九'}版", r.get('window'), r.get('rho'), r.get('rho300'), r.get('dirn'), r.get('cov'),
                   hi[0], hi[1], lo[0], lo[1]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"模型与回测_{run.version}_{run.month}.xlsx"
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(fn)})


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

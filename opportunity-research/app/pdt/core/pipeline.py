"""本地计算编排（不花钱，不经费用闸门）：重算评分（市场层 + 新品层 + 回测）、预计算机会扫描、按单元查评分。

- 重算与扫描都可指定“数据截至月”：先把行截到该月再算，所以历史月份可重放，结果与当时保存的一致（RULE-07、NFR-012）。
- 同一时间只跑一个重算（防重复）；测试环境（PDT_SYNC_JOBS=1）同步执行，其他情况后台线程执行。
"""
import os
import threading
import time
import traceback

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sqlalchemy import delete, select

from .. import catconfig
from ..db import session
from ..models import ModelRun, Opportunity, UnitScore, now
from ..models_data import ScanMeta, SearchVolume
from . import backtest as bt
from . import families as fm
from . import market as mkm
from . import newlayer as nl
from . import panel
from . import scan as sc

_state = dict(running=False, started=None, error='', last_run=None, step='')
_run_lock = threading.Lock()
_scan_lock = threading.Lock()


def _spawn(fn, *a):
    if os.environ.get('PDT_SYNC_JOBS') == '1':
        fn(*a)
    else:
        threading.Thread(target=fn, args=a, daemon=True).start()


def truncated(channel: str, month: str | None):
    """截至某月的分析底表（families.build 重新跑，保证历史月份可重放）。"""
    an = panel.analysis(channel)
    if an.A.empty or month is None or fm.mi(month) >= an.END:
        return an
    raw = an.raw[an.raw['month'] <= month].reset_index(drop=True)
    return panel.Analysis(channel, raw)


def search_frame() -> pd.DataFrame:
    with session() as s:
        rows = list(s.scalars(select(SearchVolume)))
    return mkm.ks_frame(rows) if rows else pd.DataFrame(columns=['kw', 'm', 'v', '值', '维度', '来源'])


# ---------------- 重算评分 ----------------
def rescore_state() -> dict:
    return dict(_state)


def start_rescore(user_id: int | None, month: str | None = None) -> tuple[bool, str]:
    with _run_lock:
        if _state['running']:
            return False, '正在重算，请等这次完成'
        _state.update(running=True, started=now(), error='', step='准备数据')
    _spawn(_rescore_safe, user_id, month)
    return True, '已开始重算（本地计算，不花钱）'


def _rescore_safe(user_id, month):
    try:
        rid = rescore(user_id, month)
        _state.update(last_run=rid)
    except Exception as e:  # 失败要在页面可见
        _state['error'] = f'{type(e).__name__}: {e}'
        traceback.print_exc()
    finally:
        _state.update(running=False, step='')


def rescore(user_id: int | None = None, month: str | None = None) -> int:
    """市场层第九版评分 → UnitScore；新品层做到概率与模型偏差；滚动回测与有效性检验 → ModelRun。"""
    an = truncated('amazon', month)
    if an.A.empty:
        raise ValueError('还没有已并入的 Amazon 数据')
    _state['step'] = '机会扫描'
    rescan('amazon', fm.ms(an.END))
    ver, _cfg = catconfig.current()
    END = an.END
    _state['step'] = '市场层'
    mk = mkm.Market(an.A, search_frame(), 9, end=END)
    T0 = END + 1
    D, m, cols, q, Tr = mk.predict(T0)
    coef = pd.Series(m.coef_, index=cols)
    market = dict(T0=fm.ms(T0), n_units=int(len(D)), n_train=int(len(Tr)), train_T=[fm.ms(Tr['T'].min()), fm.ms(Tr['T'].max())],
                  coef={x: dict(b=float(coef[x]), c=float(coef[x + '·k'])) for x in mk.XS}, intercept=float(m.intercept_), theta=float(coef['k']),
                  grades={g: int((D['分级'] == g).sum()) for g in 'ABCD'})
    _state['step'] = '新品层'
    try:
        rows, bias = nl.table(an.U, an.TK, END)
        cal, tr, params = nl.newlayer9(an.U, an.TK, T0, 'a')
        newlayer = dict(params=params, bias=bias, rows=rows, avg=float(np.mean(cal(list(tr.index)))) if len(tr) else None)
    except ValueError as e:  # 新家族太少（如回看很早的月份）：新品层不出分
        rows, bias = [], {}
        newlayer = dict(params=None, bias={}, rows=[], avg=None, reason=f'新家族样本不足：{e}')
    _state['step'] = '滚动回测'
    back = bt.run(mk, newlayer_rows=rows, bias=bias)
    valid = bool(back['valid'])
    with session() as s:
        run = ModelRun(month=fm.ms(END), version='第九版', created_by=user_id, config_version=ver, market=market, newlayer=newlayer,
                       backtest=back, valid=valid, valid_msg='' if valid else bt.INVALID_MSG)
        s.add(run)
        s.flush()
        rid = run.id
        s.bulk_insert_mappings(UnitScore, [dict(run_id=rid, channel='amazon', frame='全品类', attr=r['attr'], value=r['value'], data=r['data'])
                                           for r in mkm.unit_score_rows(D, T0, mk.BASE)])
    frame_unit_scores(rid, fm.ms(END))
    return rid


def frame_unit_scores(run_id: int, month: str, channel: str = 'amazon') -> int:
    """决策卡按“框 × 属性取值”读 UnitScore：为该月扫描里的每个单元写一行（数据来自 unit_lookup：最接近的第九版单元 + 新品层做到概率
    原值 / 扣偏差 + 框内新家族做到率与 p 值），frame 为真实框键。"""
    with session() as s:
        units = [(o.frame, o.attr, o.value) for o in s.scalars(select(Opportunity).where(Opportunity.channel == channel, Opportunity.month == month))]
    rows = []
    for fr, at, v in units:
        d = unit_lookup(fr, at, v, run_id, channel)
        if d is not None:
            d['sources'] = dict(d.get('sources') or {}, frame=fr, months=d.get('sources', {}).get('months', ''))
            rows.append(dict(run_id=run_id, channel=channel, frame=fr, attr=at, value=v, data=d))
    with session() as s:
        s.bulk_insert_mappings(UnitScore, rows)
    return len(rows)


def latest_run(month: str | None = None):
    with session() as s:
        q = select(ModelRun).order_by(ModelRun.id.desc())
        if month:
            q = q.where(ModelRun.month == month)
        r = s.scalar(q.limit(1))
        if r is not None:
            s.expunge(r)
        return r


def previous_run(run_id: int):
    with session() as s:
        r = s.scalar(select(ModelRun).where(ModelRun.id < run_id).order_by(ModelRun.id.desc()).limit(1))
        if r is not None:
            s.expunge(r)
        return r


ATTR2DIM = {'台面材质': '台面', '元素': '元素', '主色': '主色', '柜体材质': '材质'}


def unit_lookup(frame: str, attr: str, value: str, run_id: int | None = None, channel: str = 'amazon') -> dict | None:
    """决策卡用：框 × 属性取值 → 市场层评分（第九版单元不分框，取“尺寸 × 该属性”格子，没有时取该属性单维），
    加新品层做到概率（原值 / 扣偏差后，AC-F21-03）与框内新家族做到率和 p 值。返回 UnitScore.data 结构。"""
    run = latest_run() if run_id is None else None
    with session() as s:
        if run_id is not None:
            run = s.get(ModelRun, run_id)
        if run is None:
            return None
        size, zhuang, form = (frame.split(' · ') + ['', '', ''])[:3]
        dim = ATTR2DIM.get(attr, attr)
        v2 = fm.top_type(value, '') if attr == '台面材质' else value
        cand = [(f'尺寸 × {dim}', f'{size} × {v2}'), (f'{dim} × 尺寸', f'{v2} × {size}'), (dim, v2)]
        us = None
        for a, v in cand:
            us = s.scalar(select(UnitScore).where(UnitScore.run_id == run.id, UnitScore.attr == a, UnitScore.value == v))
            if us is not None:
                break
        data = dict(us.data) if us is not None else dict(grasp=None, grade=None, share_now=None, pred_share=None, pred_lo=None, pred_hi=None,
                                                         extra_units=None, k_months='6–10', sources=dict(frame='全品类', months='', n=None))
        if us is not None:
            data['sources'] = dict(data.get('sources') or {}, unit=f'{us.attr}：{us.value}', run_id=run.id, run_month=run.month)
        params = (run.newlayer or {}).get('params')
        bias = ((run.newlayer or {}).get('bias') or {}).get('bias')
        toks = [f'尺寸={size}', f'装={zhuang}', f'形态={form}', '颜色≥2', '子体≥4']
        if attr == '台面材质':
            toks.append(f'台面={v2}')
        elif attr == '元素':
            toks.append(f'元素={value}')
        elif attr == '主色':
            toks.append(f'主色={value}')
        p = nl.prob_for_tokens(params, toks)
        data['prob_raw'] = p
        data['prob_adj'] = None if p is None or bias is None else max(0.0, p - bias)
        data['bias'] = bias
        data['prob_tokens'] = toks
        opp = s.scalar(select(Opportunity).where(Opportunity.channel == channel, Opportunity.frame == frame, Opportunity.attr == attr,
                                                 Opportunity.value == value).order_by(Opportunity.month.desc(), Opportunity.id.desc()).limit(1))
        if opp is not None:
            mt = opp.metrics or {}
            n, k = mt.get('newfam') or 0, mt.get('newmade') or 0
            fn_, fk = mt.get('frame_newfam') or 0, mt.get('frame_newmade') or 0
            data['n_families'] = n
            data['made_rate'] = (k / n) if n else None
            data['frame_made_rate'] = (fk / fn_) if fn_ else None
            data['made_p'] = float(binomtest(k, n, fk / fn_).pvalue) if n and fn_ and 0 < fk < fn_ else None
        return data


# ---------------- 机会扫描（预计算存 Opportunity） ----------------
def rescan(channel: str = 'amazon', month: str | None = None) -> dict:
    """计算并保存一次扫描。month = 数据截至月（含）；默认最新。返回 ScanMeta.meta。"""
    with _scan_lock:
        t = time.time()
        an = truncated(channel, month)
        if an.A.empty:
            return {}
        END = an.END
        ver, cfg = catconfig.current()
        rules = cfg.get('scan') or {}
        attrs = [a['attr'] for a in cfg.get('scan_attrs', []) if a.get('scan', True)] or None
        X = sc.scan(an.A, an.U if channel == 'amazon' else None, END, rules, attrs)
        mname = fm.ms(END)
        stars = an.star_months()
        R6 = X.attrs.get('R6') or (fm.ms(END - 5), mname)
        P6 = X.attrs.get('P6') or (fm.ms(END - 11), fm.ms(END - 6))
        recent = [fm.ms(m) for m in range(END - 5, END + 1)]
        with session() as s:
            s.execute(delete(Opportunity).where(Opportunity.channel == channel, Opportunity.month == mname))
            s.execute(delete(ScanMeta).where(ScanMeta.channel == channel, ScanMeta.month == mname))
            objs = []
            for _, r in X.iterrows():
                mt = sc.to_metrics(r)
                mt['recent'], mt['prev'] = list(R6), list(P6)
                flags = [k for k in sc.KINDS if mt['flags'][k]]
                objs.append(dict(month=mname, channel=channel, frame=r['框'], attr=r['属性'], value=str(r['取值']), kind='|'.join(flags),
                                 evidence=sc.evidence_for(channel, mt['flags']) or '—', metrics=mt, config_version=ver))
            if objs:
                s.bulk_insert_mappings(Opportunity, objs)
            frames = X.drop_duplicates('框')[['框', '框月销']].sort_values('框月销', ascending=False)
            meta = dict(recent=list(R6), prev=list(P6), n_units=int(len(X)), n_frames=int(len(frames)), seconds=round(time.time() - t, 1),
                        frames=[dict(frame=f, units=float(u)) for f, u in zip(frames['框'], frames['框月销'])],
                        star_months={m: stars[m] for m in recent if m in stars}, end=mname)
            s.add(ScanMeta(channel=channel, month=mname, config_version=ver, meta=meta))
        return meta


def scan_months(channel: str) -> list[str]:
    with session() as s:
        return [m for (m,) in s.execute(select(ScanMeta.month).where(ScanMeta.channel == channel).order_by(ScanMeta.month.desc()))]


def after_merge(channel: str, month: str):
    """并入后：检查到期台账并对账（SEQ-F26-01），再预计算该渠道最新月份的扫描（后台）。评分重算由操作者在模型页发起（需标签确认完）。"""
    from . import ledger
    ledger.reconcile_due()

    def _go():
        try:
            rescan(channel)
        except Exception:
            traceback.print_exc()
    _spawn(_go)

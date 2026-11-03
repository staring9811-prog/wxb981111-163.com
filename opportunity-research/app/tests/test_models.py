"""模型与回测（PAGE-F19-01）：第九版市场层、新品层与模型偏差、滚动回测与有效性检验。期望值读第二轮结果文件 回归预测_回测_第九版.md。"""
import re

import pytest
from sqlalchemy import func, select

from conftest import login_as, make_user
from v2fixture import v2  # noqa: F401

from pdt.config import PROJECT_DIR
from pdt.db import session
from pdt.models import Batch, ModelRun, Snapshot, Tag, UnitScore

MD = PROJECT_DIR / 'solution-v2' / '开发建议' / '回归预测_回测_第九版.md'


def _num(s):
    s = s.strip().replace('−', '-').replace(',', '').replace('+', '')
    return float(s[:-1]) / 100 if s.endswith('%') else float(s)


def _table(text, header_start):
    """取以 header_start 开头的表格的数据行（单元格列表）。"""
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(header_start))
    out = []
    for l in lines[i + 2:]:
        if not l.startswith('|'):
            break
        out.append([c.strip() for c in l.strip('|').split('|')])
    return out


def _latest_run():
    with session() as s:
        r = s.scalar(select(ModelRun).order_by(ModelRun.id.desc()).limit(1))
        s.expunge(r)
        return r


def test_rescore_matches_v9_backtest(v2):
    """FLOW-09 / FLOW-10：用 2024-10 至 2026-09 数据点“重算”，市场层系数、把握分档、分级、第八版 / 第九版并排、新品层与模型偏差与第二轮结果一致。"""
    if not MD.exists():
        pytest.skip('缺第二轮结果文件 回归预测_回测_第九版.md')
    md = MD.read_text(encoding='utf-8')
    with session() as s:
        n0 = s.scalar(select(func.count()).select_from(ModelRun))
    r = v2.post('/models/rescore', follow_redirects=True)
    assert r.status_code == 200 and '重算完成' in r.text
    run = _latest_run()
    assert run.id > n0 and run.month == '2026-09' and run.valid and run.version == '第九版'
    bt = run.backtest
    # 1. 回归式系数（站在 2026-01）
    assert bt['n_train'] == int(re.search(r'训练样本 ([\d,]+) 个', md).group(1).replace(',', ''))
    for row in _table(md, '| 特征 | 意思 | b（k = 0）'):
        if row[0] == '截距':
            a = re.search(r'a = ([+\-−][\d.]+)', row[2]).group(1)
            th = re.search(r'θ = ([+\-−][\d.]+)', row[3]).group(1)
            assert abs(bt['coef']['截距']['b'] - _num(a)) < 6e-4 and abs(bt['coef']['截距']['c'] - _num(th)) < 6e-4
            continue
        cf = bt['coef'][row[0]]
        for k, j in (('b', 2), ('c', 3), ('k6', 4), ('k8', 5)):
            assert abs(cf[k] - _num(row[j])) < 6e-4, (row[0], k)
    # 2. 各时点第八版 / 第九版并排
    side = {(x['T0'], x['k'], x['ver']): x for x in bt['side']}
    rows = _table(md, '| 时点 | 窗口（立项后）')
    assert len(rows) == len(side) == 10
    for row in rows:
        k = int(re.search(r'第 (\d+)–', row[1]).group(1))
        x = side[(row[0], k, 8 if row[2] == '第八版' else 9)]
        rho, rho3 = [_num(v) for v in row[3].split('/')]
        assert abs(x['rho'] - rho) < 0.0051 and abs(x['rho300'] - rho3) < 0.0051
        assert abs(x['dirn'] - _num(row[4])) < 0.0051 and abs(x['cov'] - _num(row[5])) < 0.0051
        for col, key in ((6, 'hi'), (7, 'lo')):
            pct, n = re.match(r'(\S+)（(\d+)）', row[col]).groups()
            assert x[key][1] == int(n) and abs(x[key][0] - _num(pct)) < 0.0051
    # 3. 把握分档、相关性、分级（主时点 2026-01，立项后第 6–8 个月）
    bins = {b['bin']: b for b in bt['grasp_bins']}
    for row in _table(md, '| 把握 | 单元数 | 其中 ≥ 300 件'):
        b = bins[row[0]]
        assert (b['n'], b['n300']) == (int(row[1]), int(row[2])) and abs(b['up'] - _num(row[3])) < 0.0051 and abs(b['extra'] - _num(row[4])) < 1
    m = re.search(r'把握 vs 实际份额变化 ([+\-−][\d.]+)（≥ 300 件 ([+\-−][\d.]+)）；预计多卖 vs 实际多卖 ([+\-−][\d.]+)（≥ 300 件 ([+\-−][\d.]+)）', md)
    for key, v in zip(('grasp', 'grasp300', 'extra', 'extra300'), m.groups()):
        assert abs(bt['rho'][key] - _num(v)) < 0.0051
    grades = {g['grade']: g for g in bt['grades']}
    for row in _table(md, '| 分级 | 单元数 | 实际变大的比例'):
        g = grades[row[0]]
        assert g['n'] == int(row[1]) and abs(g['up'] - _num(row[2])) < 0.0051 and abs(g['extra'] - _num(row[3])) < 1 and abs(g['median'] - _num(row[4])) < 1
    # 5. 新品层：立项时点 T0 的新品；校准方式与模型偏差
    nl = {x['T0']: x for x in run.newlayer['rows']}
    for row in _table(md, '| T0 | 训练新家族'):
        x = nl[row[0]]
        assert (x['n_train'], x['n_test']) == (int(row[1]), int(row[2])) and x['actual'] == _num(row[3]) and abs(x['auc'] - _num(row[4])) < 0.0051
        top, bot = [_num(v) for v in row[5].split('/')]
        a, b, c = [_num(v) for v in row[6].split('/')]
        assert (x['top30'], x['bottom30'], x['mean_a'], x['mean_b'], x['mean_c'], x['use']) == (top, bot, a, b, c, row[7])
    mae = re.search(r'\(a\) ([\d.]+)、\(b\) ([\d.]+)、\(c\) ([\d.]+)，选 \*\*\((\w)\)\*\*', md)
    bias = run.newlayer['bias']
    assert [round(bias['mae'][h] * 10, 1) for h in 'abc'] == [float(v) for v in mae.groups()[:3]] and bias['chosen'] == mae.group(4)
    # 模型偏差 = 选择段（2025-06 至 08）模型平均 − 实际，每 10 个：(4.7 + 4.5 + 5.1) / 3 − (3.5 + 3.5 + 3.8) / 3 ≈ 1.2
    assert round(bias['bias'] * 10, 1) == 1.2
    # UnitScore：每个单元都有把握、分级、立项后 6–10 个月份额预测与 80% 区间
    with session() as s:
        us = list(s.scalars(select(UnitScore).where(UnitScore.run_id == run.id)))
    v9 = [u for u in us if u.frame == '全品类']
    assert len(v9) == run.market['n_units'] > 500
    for u in v9:
        d = u.data
        assert 0 <= d['grasp'] <= 1 and d['grade'] in 'ABCD' and d['pred_lo'] <= d['pred_share'] <= d['pred_hi'] and d['k_months'] == '6–10'
    fr = [u for u in us if u.frame != '全品类']
    assert fr and all(u.data['prob_adj'] is None or abs(u.data['prob_adj'] - max(0, u.data['prob_raw'] - bias['bias'])) < 1e-9 for u in fr)
    html = v2.get('/models').text
    assert '市场评分本月通过有效性检验' in html and '和上一版（第八版）并排' in html and '模型偏差（预测 − 实际）' in html and '+1.2' in html


def test_rescore_needs_tags_confirmed(v2):
    """FLOW-09（前置）：当月还有待确认标签时，“重算”不可点并说明原因，直接提交也被拒绝。"""
    with session() as s:
        item = s.scalar(select(Snapshot.item_id).join(Batch, Batch.id == Snapshot.batch_id).where(Batch.channel == 'amazon', Batch.month == '2026-09').limit(1))
        t = s.scalar(select(Tag).where(Tag.channel == 'amazon', Tag.item_id == item, Tag.tag == '元素'))
        t.status = 'queued'
        n = s.scalar(select(func.count()).select_from(ModelRun))
    html = v2.get('/models').text
    assert 'id="btn-recalc" disabled' in html and '还有 1 条标签待确认' in html
    v2.post('/models/rescore')
    with session() as s:
        assert s.scalar(select(func.count()).select_from(ModelRun)) == n


def test_validity_rule():
    """FLOW-10 / AC-F19-04（规则）：D 档之后变大 > 30% 或把握分档不再逐档上升 → 未通过。"""
    from pdt.core.backtest import validity
    ok = dict(grades=[dict(grade='D', up=0.19, n=89)], grasp_bins=[dict(up=u) for u in (0.25, 0.44, 0.60, 0.63)])
    assert validity(ok)[0]
    assert not validity(dict(ok, grades=[dict(grade='D', up=0.34, n=89)]))[0]
    assert not validity(dict(ok, grasp_bins=[dict(up=u) for u in (0.25, 0.44, 0.40, 0.63)]))[0]


def test_invalid_run_flag(v2, monkeypatch):
    """FLOW-10（第二种数据）：回测里 D 档之后变大比例被人为改到 > 30% 时，ModelRun.valid=False，提示“市场评分本月未通过有效性检验”。"""
    from pdt.core import backtest, pipeline
    real = backtest.run

    def tampered(mk, **kw):
        out = real(mk, **kw)
        for g in out['grades']:
            if g['grade'] == 'D':
                g['up'] = 0.41  # 人为：D 档之后有 41% 变大
        out['valid'], out['valid_detail'] = backtest.validity(out)
        return out
    monkeypatch.setattr(pipeline.bt, 'run', tampered)
    rid = pipeline.rescore(None)
    with session() as s:
        r = s.get(ModelRun, rid)
        assert not r.valid and r.valid_msg == '市场评分本月未通过有效性检验'
    html = v2.get('/models').text
    assert 'banner banner--block' in html and '市场评分本月未通过有效性检验' in html and '41%' in html


def test_models_page_roles(client):
    """PAGE-F19-01 权限：只读无入口；审批者能看但没有重算按钮。"""
    make_user('zhaoli', '赵立', 'approver')
    login_as(client, 'zhaoli', '密码-123456')
    r = client.get('/models')
    assert r.status_code == 200 and 'btn-recalc' not in r.text
    make_user('lixiaomei', '李晓梅', 'readonly')
    login_as(client, 'lixiaomei', '密码-123456')
    assert client.get('/models').status_code == 403


def _batches_with_blocked_october(run_month):
    with session() as s:
        s.add(Batch(channel='amazon', month='2026-09', source='api', status='merged', rows=2948))
        s.add(Batch(channel='amazon', month='2026-10', source='api', status='suspect_month', rows=2961,
                    anomaly_reason='与上月小类排名完全相同的 ASIN 占 99.9%（阈值 10%）'))
        s.add(ModelRun(month=run_month, valid=True, valid_msg='D 档之后变大 19%，阈值 ≤ 30%；把握分档逐档上升。',
                       backtest={'T0': '2025-12', 'window': '2026-06–2026-08',
                                 'grades': [{'grade': 'A', 'n': 21, 'up': 0.62, 'extra': 1840, 'median': 35}, {'grade': 'D', 'n': 89, 'up': 0.19, 'extra': -2210, 'median': -12}],
                                 'grasp_bins': [{'bin': '< 30%', 'n': 64, 'n300': 18, 'up': 0.25, 'extra': -980}, {'bin': '≥ 70%', 'n': 27, 'n300': 11, 'up': 0.63, 'extra': 1520}],
                                 'coef': {'b6': {'b': 0.412, 'c': -0.031, 'k6': 0.35, 'k8': 0.33}}, 'side': [], 'rho': {'grasp': 0.31, 'grasp300': 0.36, 'extra': 0.28, 'extra300': 0.33}, 'valid_detail': {}},
                       market={'n_units': 2, 'grades': {'A': 1, 'D': 1}}, newlayer={'rows': [], 'bias': {'bias': 0.03, 'pred': 0.31, 'actual': 0.28, 'n': 140, 'parts': [], 'mae': {'a': 0.04, 'b': 0.06, 'c': 0.07}, 'chosen': 'a'}}))
        s.flush()
        rid = s.scalar(select(func.max(ModelRun.id)))
        s.add(UnitScore(run_id=rid, frame='30″ · 拆装 · 落地式', attr='元素', value='竖棱',
                        data={'grasp': 0.74, 'grade': 'A', 'share_now': 0.083, 'pred_share': 0.121, 'pred_lo': 0.09, 'pred_hi': 0.15, 'extra_units': 312, 'k_months': 6}))


def test_rescore_blocked_when_newer_batch_unmerged(wen):
    """DESIGN-09 / FLOW-09（前置）：2026-09 已重算、2026-10 被判“疑似月份错误”未并入时，前置清单写明“2026-10 未并入…并入后才能重算”，
    重算按钮不可点并给出原因，直接提交也被拒绝；2026-09 尚未重算时照常可点“重算（含 2026-09）”。"""
    _batches_with_blocked_october('2026-09')
    html = wen.get('/models').text
    assert '下一次重算：2026-10' in html and '2026-10 未并入（疑似月份错误 / 待确认），并入后才能重算' in html
    assert re.search(r'id="btn-recalc" disabled aria-disabled="true" title="2026-10 未并入（疑似月份错误 / 待确认），并入后才能重算"', html)
    assert '重算（含 2026-10）' in html and '重算（含 2026-09）' not in html and '可重算</span>' not in html
    r = wen.post('/models/rescore', follow_redirects=True)
    assert '2026-10 未并入（疑似月份错误 / 待确认），并入后才能重算' in r.text
    with session() as s:
        assert s.scalar(select(func.count()).select_from(ModelRun)) == 1
        s.query(ModelRun).update({ModelRun.month: '2026-08'})  # 最新已并入的 2026-09 还没算过
    html = wen.get('/models').text
    assert '下一次重算：2026-09' in html and '重算（含 2026-09）' in html and 'id="btn-recalc" disabled' not in html and '未并入' not in html


def test_models_export(wen):
    """DESIGN-09（补）：页头“导出 Excel”导出本次评分与回测结果。"""
    import io
    from openpyxl import load_workbook
    _batches_with_blocked_october('2026-09')
    assert 'href="/models/export"' in wen.get('/models').text
    r = wen.get('/models/export')
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['content-type']
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ['本次评分', '分级回测', '系数', '把握分档', '新品层', '与第八版并排']
    rows = list(wb['本次评分'].values)
    assert rows[1][:6] == ('Amazon', '30″ · 拆装 · 落地式', '元素', '竖棱', 0.74, 'A')
    assert list(wb['分级回测'].values)[2] == ('D', 1, 89, 0.19, -2210, -12)
    assert list(wb['系数'].values)[1][:3] == ('b6', '份额斜率（近 6 个月每月对数变化）', 0.412)

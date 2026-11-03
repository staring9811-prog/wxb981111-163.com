"""机会扫描（PAGE-F20-01）：四类机会与 2026-10 前瞻全量 CSV 一致、框内比较、筛选、分渠道、计时。"""
import random
import time

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import insert, select

from conftest import login_as, make_user
from v2fixture import v2  # noqa: F401

from pdt.config import PROJECT_DIR
from pdt.db import session
from pdt.models import Batch, Card, Opportunity, Product, Snapshot, Tag

CSV = PROJECT_DIR / 'solution-v2' / '开发建议' / '机会扫描_202610_全量.csv'
KINDS = ['增长型', '评分缺口型', '价格缺口型', '坑']


def test_scan_matches_v2_csv_and_filters(v2):
    """FLOW-11：Amazon 2026-10 前瞻扫描与 机会扫描_202610_全量.csv 一致（单元集合、四类标记、月销、份额）；只扫近 6 个月 ≥ 200 件的框；
    证据等级；勾选属性 / 框 / 类型后只剩符合条件的行；“做决策卡”按钮带 channel、frame、attr、value，只对操作者显示。"""
    if not CSV.exists():
        pytest.skip('缺第二轮结果文件 机会扫描_202610_全量.csv')
    ref = pd.read_csv(CSV)
    t = time.time()
    html = v2.get('/scan').text
    assert time.time() - t < 10
    assert '近期 2026-04 至 2026-09，前期 2025-10 至 2026-03' in html and f'{len(ref)} 个单元进全量表' in html
    with session() as s:
        ops = list(s.scalars(select(Opportunity).where(Opportunity.channel == 'amazon', Opportunity.month == '2026-09')))
    got = pd.DataFrame([dict(属性=o.attr, 框=o.frame, 取值=o.value, 月销=o.metrics['units'], 份额=o.metrics['share'], 份额前=o.metrics['share_prev'],
                             evidence=o.evidence, **{k: o.metrics['flags'][k] for k in KINDS}) for o in ops])
    ref['取值'] = ref['取值'].astype(str)
    m = ref.merge(got, on=['属性', '框', '取值'], how='outer', suffixes=('', '_x'), indicator=True)
    assert (m['_merge'] == 'both').all() and len(m) == len(ref) == 324
    for k in KINDS:
        assert (m[k] == m[k + '_x']).all(), k
    for c in ('月销', '份额', '份额前'):
        assert np.allclose(m[c], m[c + '_x'], rtol=1e-9), c
    assert ref.groupby('框')['框月销'].first().min() >= 200
    # 证据等级：增长型 / 坑 = 经回测；只有评分缺口 / 价格缺口 = 历史观察
    for _, r in m.iterrows():
        on = [k for k in KINDS if r[k]]
        if not on:
            continue
        assert r['evidence'] == ('经回测' if set(on) & {'增长型', '坑'} else '历史观察')
    # 筛选：属性“台面材质”、框“30″ · 拆装 · 落地式”、类型“增长型”
    fr = '30″ · 拆装 · 落地式'
    exp = ref[(ref['属性'] == '台面材质') & (ref['框'] == fr) & ref['增长型']]
    h = v2.get('/scan', params={'vars': 'tm', 'frame': fr, 'type': 'growth'}).text
    rows = [l for l in h.split('<tr data-frame=')[1:]]
    assert len(rows) == len(exp) > 0
    for l in rows:
        assert l.startswith(f'"{fr}" data-attr="台面材质"') and '增长型' in l.split('data-grade')[0]
    v = exp.iloc[0]['取值']
    assert f'name="frame" value="{fr}"' in h and 'name="attr" value="台面材质"' in h and f'name="value" value="{v}"' in h and 'name="channel" value="amazon"' in h
    # 点“做决策卡”：以该单元为目标建草稿（决策卡由组 C 实现，接口存在时一并验证）
    r = v2.post('/cards', data={'channel': 'amazon', 'frame': fr, 'attr': '台面材质', 'value': v}, follow_redirects=False)
    if r.status_code in (302, 303) and '/cards/' in r.headers.get('location', ''):
        with session() as s:
            c = s.scalar(select(Card).order_by(Card.id.desc()).limit(1))
            assert (c.channel, c.frame, c.attr, c.value, c.status) == ('amazon', fr, '台面材质', v, 'draft')
        assert '查看决策卡' in v2.get('/scan', params={'vars': 'tm', 'frame': fr, 'type': 'growth'}).text
    # 只读角色看不到“做决策卡”
    make_user('lixiaomei', '李晓梅', 'readonly')
    login_as(v2, 'lixiaomei', '密码-123456')
    h = v2.get('/scan').text
    assert '做决策卡' not in h and 'class="table__divider"' in h


def test_channel_scan_uses_own_data(v2):
    """FLOW-26（扫描部分）/ AC-F29-01 / 02：切到 Wayfair 只用 Wayfair 数据、同样的框与四类规则，证据一律“未验证”，月销为估算、只在渠道内比较。"""
    from pdt.core import panel
    from pdt.core.scan import scan as do_scan
    from pdt.core.families import mi
    html = v2.get('/scan', params={'channel': 'wayfair'}).text
    assert '机会扫描 · <span>Wayfair</span>' in html and '估算月销，只在本渠道内比较' in html and 'Verified Purchase' in html
    with session() as s:
        ops = list(s.scalars(select(Opportunity).where(Opportunity.channel == 'wayfair')))
    assert ops and all(o.evidence in ('未验证', '—') for o in ops)
    assert all(o.evidence == '未验证' for o in ops if o.kind)
    # 重算一次：结果只取决于 Wayfair 的面板（与 Amazon 数据无关）
    an = panel.analysis('wayfair')
    X = do_scan(an.A, None, an.END)
    assert len(X) == len([o for o in ops if o.month == ops[0].month])
    fr_units = an.A[an.A['m'].between(an.END - 5, an.END)]
    assert set(X['框']) <= set(fr_units['尺寸段'].dropna().astype(str) + ' · ' + fr_units['装'] + ' · ' + fr_units['形态'])
    xs = {(r['框'], r['属性'], str(r['取值'])): r['月销'] for _, r in X.iterrows()}
    for o in ops:
        assert o.metrics['units'] == pytest.approx(xs[(o.frame, o.attr, o.value)])  # 存的结果 = 只用 Wayfair 面板重算的结果


def _frame_rows(frame_form, value, prev, recent, other, fams=4, new_value=False):
    """合成同一尺寸、同一拆装、不同形态的行：value 前 6 个月月均 prev、近 6 个月 recent；同框另一取值（夏克式）每月 other。"""
    from pdt.core.families import mi
    rows = []
    for m in range(mi('2025-10'), mi('2026-10')):
        rec = m >= mi('2026-04')
        for v, units, new in ((value, recent if rec else prev, new_value and rec), ('夏克式', other, False)):
            for f in range(fams):
                rows.append(dict(m=m, c=units / fams, 家族键=f'{frame_form}-{v}-{f}', 单位=f'{frame_form}-{v}-{f}', 尺寸段='24″', 装='拆装', 形态=frame_form,
                                 评分=4.3, 价格=289.0, 月龄=3 if new else 30, D8台面材质='陶瓷', 元素一=[v], 主色='白', 柜体材质='MDF'))
    return rows


def test_frames_scanned_separately():
    """RULE-05：同一取值（竖棱）同时出现在 24″ 拆装悬浮与 24″ 拆装落地两个框、趋势相反时分别给结论；份额分母只来自同框；
    同一机会在 Amazon 与 Wayfair 分别计算、互不作分母。"""
    from pdt.core.families import mi
    from pdt.core.scan import scan as do_scan
    A = pd.DataFrame(_frame_rows('悬浮式', '竖棱', 60, 160, 200, new_value=True) + _frame_rows('落地式', '竖棱', 300, 110, 300))
    X = do_scan(A, None, mi('2026-09'))
    el = X[X['属性'] == '元素'].set_index(['框', '取值'])
    up, down = el.loc[('24″ · 拆装 · 悬浮式', '竖棱')], el.loc[('24″ · 拆装 · 落地式', '竖棱')]
    assert up['增长型'] and not up['坑'] and down['坑'] and not down['增长型']
    assert up['份额'] == pytest.approx(160 / (160 + 200)) and down['份额'] == pytest.approx(110 / (110 + 300))
    assert up['份额前'] == pytest.approx(60 / (60 + 200)) and down['框月销'] == pytest.approx(410)
    for fr, g in el.groupby(level=0):
        assert g['份额'].sum() == pytest.approx(1.0)  # 分母只来自同框
    # 两个渠道：同一取值在各自渠道的数据里分别算
    W = A.copy()
    W['c'] = W['c'] * 0.1
    Y = do_scan(W, None, mi('2026-09'), rules={'min_frame_units': 20, 'min_value_units': 1})
    wy = Y[Y['属性'] == '元素'].set_index(['框', '取值']).loc[('24″ · 拆装 · 悬浮式', '竖棱')]
    assert wy['份额'] == pytest.approx(up['份额']) and wy['月销'] == pytest.approx(up['月销'] * 0.1)


SIZES = ['24″', '30″', '36″', '48″', '60″', '30″', '36″']
ELS = ['夏克式', '竖棱', '农场风装饰饰条', '纯色', '横板条', '玻璃门']
COLORS = ['白', '黑', '原木', '灰', '深木']
TOPS = [('陶瓷', '陶瓷盆'), ('树脂', '树脂盆'), ('岗石', '陶瓷盆'), ('木板', '玻璃盆')]


def test_scan_open_within_10s(wen):
    """RULE-06 / NFR-009：24 个月约 5 万行子体 × 月（合成），预计算后打开机会扫描 ≤ 10 秒（测 3 次取最大）。"""
    from pdt.core import pipeline
    from pdt.core.families import ms, mi
    random.seed(7)
    months = [ms(i) for i in range(mi('2024-10'), mi('2026-10'))]
    n_items = 2100
    with session() as s:
        s.execute(insert(Product), [dict(channel='amazon', item_id=f'B0PERF{i:04d}', family_key=f'F{i // 3:04d}', brand=['Yaheetech', 'ARIEL', 'eclife', 'VEVOR'][i % 4],
                                         title=f'测试 {SIZES[i % 7]} 浴室柜 {i}', listed_at='2024-08-01' if i % 5 else '2026-05-10') for i in range(n_items)])
        tags = []
        for i in range(n_items):
            t, b = TOPS[i % 4]
            for k, v in (('尺寸段', SIZES[i % 7]), ('装', '整装' if i % 3 == 0 else '拆装'), ('形态', '悬浮式' if i % 4 == 0 else '落地式'), ('台面材质', t),
                         ('台盆材质', b), ('元素', ELS[i % 6]), ('主色', COLORS[i % 5]), ('柜体材质', 'MDF' if i % 2 else '含胶合板')):
                tags.append(dict(channel='amazon', item_id=f'B0PERF{i:04d}', tag=k, value=v, auto_value=v, confidence=0.9, source='rule', status='auto', candidates=[], month=''))
        s.execute(insert(Tag), tags)
        for mo in months:
            b = Batch(channel='amazon', month=mo, source='upload', status='merged', rows=n_items)
            s.add(b)
            s.flush()
            s.execute(insert(Snapshot), [dict(batch_id=b.id, channel='amazon', month=mo, item_id=f'B0PERF{i:04d}', price=150 + (i % 40) * 10, units=random.uniform(1, 40),
                                              rank=(i % 400) + 1, rating=3.8 + (i % 12) / 10, raw=dict(family_key=f'F{i // 3:04d}', fam_units=90.0)) for i in range(n_items)])
    with session() as s:
        assert s.query(Snapshot).count() == 50400
    t = time.time()
    meta = pipeline.rescan('amazon')
    pre = time.time() - t
    assert meta['n_units'] > 0
    worst = 0
    for _ in range(3):
        t = time.time()
        r = wen.get('/scan')
        worst = max(worst, time.time() - t)
        assert r.status_code == 200 and 'table__divider' in r.text
    print(f'预计算 {pre:.1f} 秒；打开扫描页最慢 {worst:.2f} 秒')
    assert worst <= 10

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
    # v8（AC-F18-08）：Wayfair 样本只有标题，“装”没有依据的进确认队列、不进框；这里模拟 wen 在确认队列里把它们确认后再扫描
    from pdt.core import pipeline, tagging
    from pdt.models import Tag
    with session() as s:
        unk = [t.id for t in s.scalars(select(Tag).where(Tag.channel == 'wayfair', Tag.tag == '装', Tag.value == ''))]
    assert unk
    for tid in unk:
        tagging.confirm_item(tid, '拆装', 1)
    panel.clear_cache()
    pipeline.rescan('wayfair')
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
    from pdt.core import pipeline, tagging
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


def _seed_scan():
    from pdt.models_data import ScanMeta
    fr = '30″ · 拆装 · 落地式'
    with session() as s:
        s.add(ScanMeta(channel='amazon', month='2026-09', meta={'recent': ['2026-04', '2026-09'], 'prev': ['2025-10', '2026-03'], 'n_frames': 1, 'n_units': 3,
                                                                'frames': [{'frame': fr, 'units': 5320}]}))
        base = dict(families=6, per_family_ratio=1.12, rating=4.31, frame_rating=4.42, premium=1.08, median_price=329.0, newshare=0.38, frame_newshare=0.21,
                    newfam=4, newmade=2, frame_newfam=19, frame_newmade=6)
        s.add(Opportunity(month='2026-09', channel='amazon', frame=fr, attr='元素', value='竖棱', kind='增长型', evidence='经回测',
                          metrics=dict(base, units=812, share=0.153, share_prev=0.094, flags={'增长型': True})))
        s.add(Opportunity(month='2026-09', channel='amazon', frame=fr, attr='台面材质', value='岗石', kind='价格缺口型', evidence='历史观察',
                          metrics=dict(base, units=241, share=0.045, share_prev=0.051, premium=1.41, flags={'价格缺口型': True})))
        s.add(Opportunity(month='2026-09', channel='amazon', frame=fr, attr='主色', value='白', kind='', evidence='—',
                          metrics=dict(base, units=2210, share=0.415, share_prev=0.43, flags={})))
        s.add(Card(channel='amazon', frame='36″ · 拆装 · 落地式', attr='元素', value='竖棱', status='draft'))
    return fr


def test_scan_export_and_action_cell(wen):
    """DESIGN-10（补）：页头“导出 Excel”导出当前渠道、当前筛选下的结果（列同页面表格）；“做决策卡”与“有相关卡”上下排列在同一格，不挤出列宽。"""
    import io
    import re
    from openpyxl import load_workbook
    fr = _seed_scan()
    html = wen.get('/scan', params={'channel': 'amazon', 'vars': 'el'}).text
    assert 'href="/scan/export?channel=amazon&amp;vars=el"' in html
    cell = re.search(r'<div class="cell-actions">(.*?)</div></td>', html, re.S).group(1)
    assert cell.index('做决策卡') < cell.index('有相关卡') and 'style="display:inline"' not in cell
    r = wen.get('/scan/export', params={'channel': 'amazon', 'vars': 'el'})
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['content-type']
    rows = list(load_workbook(io.BytesIO(r.content)).active.values)
    assert rows[0][:10] == ('框', '框月销', '机会类型', '属性', '取值', '需求范围', '月销', '份额（前期）', '份额（近期）', '在卖的款数')  # r10：需求范围列
    assert rows[1:] == [(fr, 5320, '增长型', '元素', '竖棱', '细分需求', 812, 0.094, 0.153, 6, 1.12, 4.31, 4.42, 1.08, 329, 0.38, 0.21, 2, 4, 6, 19, '经回测')]
    all_rows = list(load_workbook(io.BytesIO(wen.get('/scan/export', params={'channel': 'amazon'}).content)).active.values)
    assert sorted(x[4] for x in all_rows[1:]) == ['岗石', '竖棱']  # 无机会标记的“白”不导出，与页面一致


def test_scan_action_column_sticky_when_all_columns(wen):
    """DESIGN-10：“显示全部列”后表格变宽，操作列（做决策卡）固定在右侧，不被挤出可视区。"""
    import re
    _seed_scan()
    html = wen.get('/scan', params={'channel': 'amazon'}).text
    assert 'data-cols-toggle=".scan-table .table-wrap"' in html
    assert re.search(r'<th class="col-op"><span class="visually-hidden">操作</span></th></tr></thead>', html)
    assert re.search(r'<td class="t-nowrap col-op"><div class="cell-actions">.*?做决策卡', html, re.S)
    css = re.search(r'\.scan-table \.table \.col-op \{([^}]*)\}', html).group(1)
    assert 'position: sticky' in css and 'right: 0' in css and 'background: var(--surface)' in css


def test_design10_no_frames_empty_state_and_value_column(wen):
    """DESIGN-10（v8 复核）：Wayfair 商品“装”都看不出（规格、标题都没写）时没有可扫描的框——空状态写明“没有可扫描的框：N 个商品‘装’未知”
    并链接到打标确认补上，不再显示误导的“没有符合筛选条件的单元”；“属性：取值”列有最小宽度，取值整词不断开。"""
    from pdt.core import channels
    titles = ["Wade Logan Arlo 30'' Free-standing Single Bathroom Vanity with Ceramic Top",
              "Andover Mills Kinsley 36'' Single Bathroom Vanity with Engineered Stone Top",
              "Birch Lane Hartwell 48'' Single Bathroom Vanity with Carrara Marble Top"]
    rows = [{'平台': 'Wayfair', '商品ID': f'W00{4918260 + i}', '品牌': titles[i % 3].split()[0], '标题': titles[i % 3], '排名': i + 1, '价格': 459 + i,
             'reviews': [{'评论ID': f'wf{i}-{m}-{k}', '评论日期': f'2026-{m:02d}-1{k}', 'VP状态': 'VP', '评分': 5} for m in range(1, 11) for k in range(3)]}
            for i in range(6)]
    channels.ingest_tracker_month(rows, collected_on='2026-11-03')
    with session() as s:
        unknown = {t.item_id for t in s.scalars(select(Tag).where(Tag.channel == 'wayfair', Tag.tag == '装')) if t.value == ''}
    assert len(unknown) == 6
    html = wen.get('/scan', params={'channel': 'wayfair'}).text
    body = html.split('<tbody>')[1].split('</tbody>')[0]
    assert '没有可扫描的框：6 个商品"装"未知、不进框' in body and 'href="/tagging?channel=wayfair&reason=assembly"' in body
    assert '没有符合筛选条件的单元' not in body and '不到 200 件，不扫描' in body
    assert '<th class="col-val">属性：取值</th>' in html and '.scan-table .col-val { min-width: 11em; }' in html

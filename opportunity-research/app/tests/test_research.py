"""渠道调研（F30，revision 9）：FLOW-33～40、RULE-10、RULE-11，DESIGN-02 / 08 / 19～21 的行为部分。

样本：wen 本机产出的 `input/data_v2/渠道关键词/大词/三平台_商品表.csv`、`三平台_月销表.csv`（不入库，本机没有时跳过）。
期望值：`solution-v2/trial/小平台调研_单元指标.py` 在同一样本上的输出（`input/data_v2/渠道调研/小平台调研_按框_*_全量.csv`、
`小平台调研_待人工确认.csv`）与报告 `小平台调研_单元×指标_HD_Lowes_Wayfair.md` 的数字；价格、评分、Amazon 对照按 AC-F30-15 / 16 在测试里独立计算。
不用被测函数生成期望。

样本说明（2026-11-04 补数后的最终表）：商品表里 Lowe's pid 5018243355 出现在两个父体下（两行），按 AC-F30-03 整次拒绝
（test_flow33_real_sample_duplicate_rejected 证明）；其余用例用去掉其中没有月销行的那一行（父体 6003479666）的副本。
"""
import html as htmllib
import io
import re
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import login_as, make_user
from v2fixture import v2  # noqa: F401  （第二轮数据夹具）

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'input' / 'data_v2' / '渠道关键词' / '大词'
REF = ROOT / 'input' / 'data_v2' / '渠道调研'
DUP = ("Lowe's", '5018243355', '6003479666')
OLD = REF / '估算版样本'  # 2026-11-04 上午版样本副本（Wayfair 168 个 listing 只有评论总数），只用于估算规则
_S = {}


def _need_sample():
    if not (SAMPLE / '三平台_商品表.csv').exists() or not (SAMPLE / '三平台_月销表.csv').exists():
        pytest.skip(f'本机没有调研样本 {SAMPLE}（原始数据不入库），跳过')


def _need_ref():
    if not (REF / '小平台调研_按框_框_全量.csv').exists():
        pytest.skip(f'本机没有小试全量表 {REF}（由 solution-v2/trial/小平台调研_单元指标.py 生成，不入库），跳过')


def sample():
    """(商品表 DataFrame, 月销表 DataFrame)，均为字符串列；商品表已去掉重复 pid 的那一行（见模块说明）。"""
    _need_sample()
    if 'p' not in _S:
        p = pd.read_csv(SAMPLE / '三平台_商品表.csv', dtype=str, keep_default_na=False)
        m = pd.read_csv(SAMPLE / '三平台_月销表.csv', dtype=str, keep_default_na=False)
        _S['raw_p'] = p
        _S['p'] = p[~((p['渠道'] == DUP[0]) & (p['pid'] == DUP[1]) & (p['fam'] == DUP[2]))].reset_index(drop=True)
        _S['m'] = m
    return _S['p'].copy(), _S['m'].copy()


def csvb(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode('utf-8')


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    """导入日固定为 2026-11-04（最近一个完整月 2026-10），与样本采集日一致。"""
    from pdt.core import research
    monkeypatch.setattr(research, 'today', lambda: date(2026, 11, 4))


class _R:
    """响应包装：text 做 HTML 反转义，便于按页面上看到的文字断言。"""
    def __init__(self, r):
        self.status_code, self.headers, self.text = r.status_code, r.headers, htmllib.unescape(r.text)


def upload(c, p, m, names=('三平台_商品表.csv', '三平台_月销表.csv')):
    return _R(c.post('/data/research/check', files={'products': (names[0], csvb(p)), 'monthly': (names[1], csvb(m))}, follow_redirects=False))


def pending_id():
    from pdt.core import research
    imp = research.pending_import()
    return imp.id if imp else None


def import_channels(c, chs, p=None, m=None):
    if p is None:
        p, m = sample()
    r = upload(c, p, m)
    assert r.status_code == 303, r.text[:2000]
    r = c.post(f'/data/research/{pending_id()}/confirm', data={'channels': chs}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].startswith('/research'), r.text[:500]


def rjson(c, ch):
    r = c.get(f'/research?channel={ch}&format=json')
    assert r.status_code == 200
    return r.json()


def research_state():
    """调研相关表的全部内容（用于"当前数据不变"的比较）。"""
    from pdt.db import session
    from pdt.models_research import ResearchImport, ResearchMonthly, ResearchProduct, ResearchResult, ResearchVersion
    with session() as s:
        return dict(versions=[(v.id, v.channel, v.status, v.no) for v in s.scalars(select(ResearchVersion).order_by(ResearchVersion.id))],
                    imports=[(i.id, i.status) for i in s.scalars(select(ResearchImport).where(ResearchImport.status != 'pending').order_by(ResearchImport.id))],
                    products=s.scalar(select(func.count()).select_from(ResearchProduct)), monthly=s.scalar(select(func.count()).select_from(ResearchMonthly)),
                    results=[(r.channel, r.version_id, str(r.computed_at)) for r in s.scalars(select(ResearchResult).order_by(ResearchResult.id))])


def ref_frames(ch):
    _need_ref()
    F = pd.read_csv(REF / '小平台调研_按框_框_全量.csv')
    F = F[F['渠道'] == ch]
    if F.empty:
        pytest.skip(f'小试全量表里没有 {ch}')
    return F.set_index('框')


def ref_units(ch):
    U = pd.read_csv(REF / '小平台调研_按框_单元指标_全量.csv')
    return U[U['渠道'] == ch]


def page_pct(v, nd=0):
    return f'{v * 100:.{nd}f}%'


def page_share(v):
    return f'{v * 100:.1f}%' if v < 0.1 else f'{v * 100:.0f}%'


def wq(x, w, q):
    x, w = np.asarray(x, float), np.asarray(w, float)
    k = ~np.isnan(x) & (w > 0)
    x, w = x[k], w[k]
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return x[o][min(np.searchsorted(c, c[-1] * q), len(x) - 1)]


# =============================================================== FLOW-33 导入拒绝
def test_flow33_real_sample_duplicate_rejected(wen):
    """FLOW-33（AC-F30-03）：真实样本里 Lowe's 同一 pid 出现在两个父体下 → 整次拒绝，列出问题类型、行数与示例；当前数据不变。"""
    sample()
    p = _S['raw_p']
    if not ((p['渠道'] == DUP[0]) & (p['pid'] == DUP[1])).sum() > 1:
        pytest.skip('样本里已没有这对重复 pid')
    before = research_state()
    r = upload(wen, p, _S['m'])
    assert r.status_code == 400
    assert '商品表同一渠道 + pid 出现多行' in r.text and "Lowe's 5018243355" in r.text and '未导入，当前调研数据不变' in r.text
    assert research_state() == before


def test_flow33_five_bad_copies_rejected(wen):
    """FLOW-33：已有一版 Home Depot 生效；5 组有问题的副本每次都整次拒绝并列出原因；页面、导入记录与库内当前版本与上传前完全相同。"""
    import_channels(wen, ['homedepot'])
    p, m = sample()
    before = research_state()
    page_before = wen.get('/research?channel=homedepot&format=json').json()
    log_before = wen.get('/data/research/log').json()
    # 1 商品表删去"装"列
    r = upload(wen, p.drop(columns=['装']), m)
    assert r.status_code == 400 and '商品表缺少列' in r.text and re.search(r'<td class="small">装</td>', r.text)
    # 2 月销表某行"月"写成 2026/03
    m2 = m.copy()
    i = int(m2.index[m2['月'] == '2026-03'][0])
    m2.loc[i, '月'] = '2026/03'
    r = upload(wen, p, m2)
    assert r.status_code == 400 and '月销表"月"不是 YYYY-MM' in r.text and f'第 {i + 2:,} 行 月：2026/03' in r.text
    # 3 12 行渠道写成 Amazon（商品表最后 12 行）
    p3 = p.copy()
    p3.loc[p3.index[-12:], '渠道'] = 'Amazon'
    r = upload(wen, p3, m)
    assert r.status_code == 400 and '商品表渠道值不认识' in r.text and '"Amazon"：12 行' in r.text
    assert f'第 {len(p3) - 10:,}–{len(p3) + 1:,} 行' in r.text
    # 4 商品表同一 Home Depot pid 出现两行
    p4 = pd.concat([p, p[p['渠道'] == 'Home Depot'].head(1)], ignore_index=True)
    pid = p4.iloc[-1]['pid']
    r = upload(wen, p4, m)
    assert r.status_code == 400 and '商品表同一渠道 + pid 出现多行' in r.text and f'Home Depot {pid}' in r.text
    # 5 月销表 3 个 Wayfair pid 在商品表里不存在
    m5 = m.copy()
    idx = m5.index[m5['渠道'] == 'Wayfair'][:3]
    m5.loc[idx, 'pid'] = ['W009360680', 'W009360681', 'W009360682']
    r = upload(wen, p, m5)
    assert r.status_code == 400 and '月销表的商品在商品表里找不到' in r.text
    for x in ('W009360680', 'W009360681', 'W009360682'):
        assert f'Wayfair {x}' in r.text
    assert research_state() == before
    assert wen.get('/research?channel=homedepot&format=json').json() == page_before
    assert wen.get('/data/research/log').json() == log_before


# =============================================================== FLOW-34 摘要、放弃、按渠道替换、再导入保留确认
def test_flow34_summary_abandon_confirm_replace_keep_confirm(wen):
    """FLOW-34（AC-F30-04、05、07、30）：含 2026-11 行的真实样本：摘要数值与报告一致、2026-11 只作参考；放弃不变；只导入 Home Depot；
    确认 1 个 Home Depot 形态后重传，新版本保留确认、该商品不再进队列、旧版标"已替换"。"""
    p, m = sample()
    nov = m[m['月'] == '2026-10'].copy()
    nov['月'] = '2026-11'
    m11 = pd.concat([m, nov], ignore_index=True)
    n11 = int((nov['渠道'] == 'Home Depot').sum())
    r = upload(wen, p, m11)
    assert r.status_code == 303
    html = wen.get('/data/research').text
    from pdt.core import research
    hd = research.pending_import().summary['homedepot']['summary']
    assert hd['window'][0] == '2026-01' and hd['window'][-1] == '2026-10' and hd['n_months'] == 10
    assert round(hd['sales']) == 206750 and round(hd['sales_monthly']) == 206750          # 报告：Home Depot 窗口销量 206,750
    assert f"{hd['framed_share'] * 100:.1f}" == '99.3' and hd['pending_products'] == 36   # 报告：已落框 99.3%、待确认 36
    assert hd['monthly_share'] == 1.0 and hd['reference'] == {'2026-11': n11}
    assert hd['n_products'] == 1545 and hd['n_families'] == 218
    card = html.split('data-channel="homedepot"')[1].split('</article>')[0]
    assert '206,750 件' in card and '99.3%' in card and '36 个' in card and f'2026-11：{n11:,} 行（未完整月），不计入' in card
    assert '2026-01 至 2026-10（10 个月）' in card
    # 放弃
    r = wen.post(f'/data/research/{pending_id()}/abandon', follow_redirects=False)
    assert r.status_code == 303
    assert research_state()['versions'] == [] and rjson(wen, 'homedepot')['data'] is None
    assert any(x['status'] == '已放弃' and x['channel'] == 'homedepot' for x in wen.get('/data/research/log').json())
    # 重传、只勾 Home Depot
    import_channels(wen, ['homedepot'], p, m11)
    log = wen.get('/data/research/log').json()
    cur = [x for x in log if x['status'] == '当前']
    assert [(x['channel'], x['no'], x['n_products'], x['months'], x['by']) for x in cur] == [('homedepot', 'v1', 1545, ['2026-01', '2026-10'], 'wen')]
    assert cur[0]['files'] == {'products': '三平台_商品表.csv', 'monthly': '三平台_月销表.csv'}
    assert rjson(wen, 'wayfair')['data'] is None and rjson(wen, 'lowes')['data'] is None
    hdj = rjson(wen, 'homedepot')['data']
    assert round(hdj['summary']['sales']) == 206750  # 2026-11 不计入任何指标
    # 打标确认 1 个 Home Depot 形态
    e = next(x for x in research.pending_entries('homedepot') if x['tag'] == '形态')
    r = wen.post('/tagging/research/confirm', data={'channel': 'homedepot', 'pid': e['pid'], 'tag': '形态', 'value': '落地式'}, follow_redirects=False)
    assert r.status_code == 303 and '渠道调研已重算' in r.headers['location'] or 'msg=' in r.headers['location']
    left = {x['pid'] for x in research.pending_entries('homedepot')}
    assert e['pid'] not in left and len(left) < 36  # 同家族已知形态会补到同家族其他未知商品（小试口径），待确认可能一次少多个
    n_after = rjson(wen, 'homedepot')['data']['summary']['pending_products']
    # 再导入同一样本并确认
    import_channels(wen, ['homedepot'], p, m11)
    log = wen.get('/data/research/log').json()
    hdlog = sorted([x for x in log if x['channel'] == 'homedepot' and x['no'] != '—'], key=lambda x: x['no'])
    assert [(x['no'], x['status']) for x in hdlog] == [('v1', '已替换'), ('v2', '当前')]
    assert e['pid'] not in {x['pid'] for x in research.pending_entries('homedepot')}
    assert rjson(wen, 'homedepot')['data']['summary']['pending_products'] == n_after


# =============================================================== FLOW-35 与已有渠道数据冲突
def _merged_batches(channel, counts: dict):
    """前置：库里已并入该渠道各月评论 VP 数据（F28 批次，去重条数 = counts[月]）。"""
    from pdt.db import session
    from pdt.models import Batch, now
    with session() as s:
        for mth, n in counts.items():
            s.add(Batch(channel=channel, month=mth, source='tracker', status='merged', rows=1, merged_at=now(),
                        checks=dict(dedup=dict(vp=float(n), nonvp=0.0), complete=True, items=1)))


def _cat_counts(p, m, name):
    """独立计算：类目节点 / 两者商品所在家族当月 VP + 非VP。"""
    pc, mc = p[p['渠道'] == name], m[m['渠道'] == name]
    fams = set(pc.loc[pc['来源'].isin(['类目节点', '两者']), 'fam'])
    x = mc[mc['fam'].isin(fams)]
    return (x['VP'].astype(float) + x['非VP'].astype(float)).groupby(x['月']).sum().to_dict()


def test_flow35_conflict_needs_tick(wen):
    """FLOW-35（AC-F30-06）：Wayfair 2026-03 差 6.8%、其余 ≤ 3%；Home Depot 某月已并入为 0 而导入 > 0 → 两渠道标"与已有数据不一致"并逐月对照；
    未勾选不导入，勾选才导入。"""
    p, m = sample()
    wf = _cat_counts(p, m, 'Wayfair')
    hd = _cat_counts(p, m, 'Home Depot')
    _merged_batches('wayfair', {k: (round(v / 1.068) if k == '2026-03' else round(v / 1.02)) for k, v in wf.items()})
    _merged_batches('homedepot', {k: (0 if k == '2026-05' else round(v)) for k, v in hd.items()})
    r = upload(wen, p, m)
    assert r.status_code == 303
    from pdt.core import research
    S = research.pending_import().summary
    assert S['wayfair']['conflict'] and S['homedepot']['conflict'] and not S['lowes']['conflict']
    bad = {x['month']: x for x in S['wayfair']['conflicts'] if x['bad']}
    assert list(bad) == ['2026-03'] and abs(bad['2026-03']['diff'] - 0.068) < 0.002
    assert all(abs(x['diff']) <= 0.03 for x in S['wayfair']['conflicts'] if x['month'] != '2026-03')
    hbad = [x for x in S['homedepot']['conflicts'] if x['bad']]
    assert [(x['month'], x['merged'], x['imported'] > 0) for x in hbad] == [('2026-05', 0.0, True)]
    html = wen.get('/data/research').text
    wcard = html.split('data-channel="wayfair"')[1].split('</article>')[0]
    assert '与已有数据不一致' in wcard and '2026-03' in wcard and '+6.8%' in wcard and '&gt; 5%' in wcard
    assert 'name="channels" value="wayfair" data-pick="Wayfair"' in wcard and 'checked' not in wcard.split('name="channels"')[1].split('>')[0]
    hcard = html.split('data-channel="homedepot"')[1].split('</article>')[0]
    assert '与已有数据不一致' in hcard and '已并入为 0' in hcard
    # 只勾 Lowe's：Wayfair、Home Depot 不导入
    wen.post(f'/data/research/{pending_id()}/confirm', data={'channels': ['lowes']}, follow_redirects=False)
    assert [v[1] for v in research_state()['versions']] == ['lowes']
    # 再传一次，勾选 Wayfair 才导入
    upload(wen, p, m)
    wen.post(f'/data/research/{pending_id()}/confirm', data={'channels': ['wayfair']}, follow_redirects=False)
    assert sorted(v[1] for v in research_state()['versions'] if v[2] == 'current') == ['lowes', 'wayfair']


# =============================================================== FLOW-36 指标数值回归（Home Depot）
def test_flow36_hd_frames_units_match_trial(v2):
    """FLOW-36（AC-F30-10～16）：Home Depot 达门槛 20 框（其中样本少 5 框）、231 个单元（revision 10 门槛 100），框与单元的体量、份额、趋势、供给与小试全量表一致；
    价格带、溢价、评分差、Amazon 对照与按 AC-F30-15 / 16 独立计算的期望一致；"无"与"Amazon 无"。"""
    F = ref_frames('Home Depot')
    U = ref_units('Home Depot')
    import_channels(v2, ['homedepot'])
    d = rjson(v2, 'homedepot')['data']
    # revision 10：小平台框门槛 100（AC-F30-35），月均 100–200 的框标"样本少，只作参考"（AC-F30-34）；参考表由数据侧按同口径（28″、开放式、门槛 100）重跑
    big = F[F['框月均'] >= 100]
    assert d['state'] == 'ok' and len(d['frames']) == len(big) == 20
    assert d['summary']['small_n'] == len(F) - 20 == 18 and round(d['summary']['small_units']) == round(F[F['框月均'] < 100]['框月均'].sum())
    assert {f['frame'] for f in d['frames'] if f['read'] == 'small'} == set(big[big['框月均'] < 200].index)
    tot = F['框月均'].sum()
    for f in d['frames']:
        r = F.loc[f['frame']]
        assert round(f['units']) == round(r['框月均']) and page_share(f['channel_share']) == page_share(r['框月均'] / tot)
        assert f'{f["ratio"]:.2f}' == f"{r['近3'] / r['前3']:.2f}" and f['families'] == r['家族'] and round(f['per_family']) == round(r['单款月均'])
        assert f'{f["cover"] * 100:.1f}' == f"{r['分框覆盖_期望'] * 100:.1f}" and f['read'] == ('small' if r['可读性'] == '样本少，只作参考' else 'ok')
    UU = U[U['框'].isin(big.index) & (U['月均'] >= 20)]
    got = {(fr, u['attr'], u['value']): u for fr, us in d['units'].items() for u in us}
    assert len(got) == len(UU) == 231  # revision 10：门槛 100 后多 5 个"样本少"框（旧口径 216）
    for r in UU.itertuples():
        u = got[(r.框, r.属性, str(r.取值))]
        assert round(u['units']) == round(r.月均) and page_share(u['share']) == page_share(r.份额)
        assert f"{u['diff_pp']:+.1f}" == f'{r.份额差pp:+.1f}' and f"{u['slope_pp']:+.2f}" == f'{r.斜率pp:+.2f}' and f"{u['cv']:.2f}" == f'{r.CV:.2f}'
        assert u['families'] == r.家族 and f"{u['per_family_ratio']:.2f}" == f'{r.单款比:.2f}'
    # 报告的例子（revision 10 新口径重跑：28″ 分出后 30″ 框变小）：30″ · 整装 · 落地式 卡拉拉大理石 月均 266、份额 7.6%、近 3 − 前 3 −6.3 pp；
    # Cultured Marble 44%（旧口径 285、7.5%、−6.0 pp、40%）
    k = got[('30″ · 整装 · 落地式', '台面材质', '卡拉拉大理石')]
    assert round(k['units']) == 266 and page_share(k['share']) == '7.6%' and f"{k['diff_pp']:+.1f}" == '-6.3' and k['trend'] == '丢份额'
    assert page_share(got[('30″ · 整装 · 落地式', '台面材质', 'Cultured Marble')]['share']) == '44%'
    # 价格 / 评分（AC-F30-15）独立计算：30″ · 整装 · 落地式 的月销行 × 商品表价格、评分（评分按页面评论数 × 销量 ÷ 家族销量加权）
    p, m = sample()
    p, m = p[p['渠道'] == 'Home Depot'].copy(), m[m['渠道'] == 'Home Depot'].copy()
    for c in ('价格', '评分', '页面评论数'):
        p[c] = pd.to_numeric(p[c], errors='coerce')
    m['c'] = m['销量'].astype(float)
    m = m.merge(p[['pid', '价格', '评分', '页面评论数', '台面材质']], on='pid', how='left')
    famt = m.groupby('fam')['c'].transform('sum')
    m['w'] = (m['页面评论数'].fillna(0) * m['c'] / famt).where(m['评分'] > 0, 0).fillna(0)
    # 同家族补形态（小试口径，research.build_rows）：形态未知的行按同家族销量最大的已知形态补（新表有 163 行形态"未知"）
    kn = m[m['形态'] != '未知'].groupby(['fam', '形态'])['c'].sum().reset_index().sort_values('c').drop_duplicates('fam', keep='last').set_index('fam')['形态']
    unk = m['形态'] == '未知'
    m.loc[unk, '形态'] = m.loc[unk, 'fam'].map(kn).fillna('未知')
    fr = m[(m['尺寸段'] == '30″') & (m['装'] == '整装') & (m['形态'] == '落地式')]
    gr = fr[fr['台面材质'] == '岗石']
    g = got[('30″ · 整装 · 落地式', '台面材质', '岗石')]
    assert round(g['p25']) == round(wq(gr['价格'], gr['c'], .25)) and round(g['p75']) == round(wq(gr['价格'], gr['c'], .75))
    assert f"{g['premium']:.2f}" == f"{wq(gr['价格'], gr['c'], .5) / wq(fr['价格'], fr['c'], .5):.2f}"
    rate = (gr['评分'].fillna(0) * gr['w']).sum() / gr['w'].sum()
    frate = (fr['评分'].fillna(0) * fr['w']).sum() / fr['w'].sum()
    assert f"{g['rating']:.2f}" == f'{rate:.2f}' and f"{g['rating_diff']:+.2f}" == f'{rate - frate:+.2f}'
    # Amazon 同框对照（AC-F30-16）独立计算：最近 6 个完整月、30″ · 落地式（不分拆装）、岗石
    from pdt.core import panel, richness
    B = richness.amazon_rows(panel.analysis('amazon').A)
    ms_ = sorted(B['m'].unique())[-6:]
    B = B[B['m'].isin(ms_) & (B['尺寸段'] == '30″') & (B['形态'] == '落地式')]
    u = B[B['台面材质'] == '岗石']
    pre = u[u['m'].isin(ms_[:3])]['c'].sum() / B[B['m'].isin(ms_[:3])]['c'].sum()
    rec = u[u['m'].isin(ms_[3:])]['c'].sum() / B[B['m'].isin(ms_[3:])]['c'].sum()
    w = u[u['c'] > 0]
    az = g['amazon']
    assert az['fam'] == w['fam'].nunique() and az['pb'] == pd.cut(w['价格'], [0, 200, 300, 450, 650, 900, 1300, np.inf], right=False).nunique()
    assert page_share(az['pre']) == page_share(pre) and page_share(az['rec']) == page_share(rec)
    ln = np.log((rec + 0.002) / (pre + 0.002))
    assert az['dir'] == ('↑' if ln >= 0.2 else '↓' if ln <= -0.2 else '→')
    # 页面
    html = v2.get('/research/homedepot/frame/30-整装-落地式').text
    row = html.split('data-value="卡拉拉大理石"')[1].split('</tr>')[0]
    assert '>266<' in row and '7.6%' in row and '-6.3 pp' in row and 'badge--miss">丢份额' in row  # revision 10 新口径
    assert 'Amazon 无' in html or all(u['amazon'] for us in d['units'].values() for u in us)
    assert '新款按页面累计评论数 ≤ 窗口内评论数（商品表没有首评月）判定' in html or '新家族按页面累计评论数 ≤ 窗口内评论数（商品表没有首评月）判定' in html
    assert '把握' not in html and '上 / 不上' not in html.replace('"上 / 不上"', '')


# =============================================================== FLOW-37 估算与可读性（Wayfair）
def test_flow37_wayfair_estimate_and_readability(v2):
    """FLOW-37（AC-F30-17～21）：Wayfair 无月度 listing 按评论数档估算；24″ · 拆装 · 落地式 5,456 估算 / 低估计 4,010；30″ · 整装 · 悬浮式 低估计
    122 标"低估计未达门槛"；可读框与小试相同；不下结论整行降灰只显示体量份额；30″ · 整装 · 落地式 趋势不下结论（有月度 33%）；只看可读框。
    样本：最终表的 Wayfair 已全部补到逐月评论、没有估算对象，估算规则用 2026-11-04 上午版样本副本（OLD，168 个 listing 只有评论总数）验证，
    期望 = 小试脚本在该副本上的输出与报告上午版数字。"""
    if not (OLD / '三平台_商品表.csv').exists() or not (OLD / '小平台调研_按框_框_Wayfair.csv').exists():
        pytest.skip(f'本机没有估算版样本副本 {OLD}（不入库），跳过')
    F = pd.read_csv(OLD / '小平台调研_按框_框_Wayfair.csv').set_index('框')
    op = pd.read_csv(OLD / '三平台_商品表.csv', dtype=str, keep_default_na=False)
    om = pd.read_csv(OLD / '三平台_月销表.csv', dtype=str, keep_default_na=False)
    w = op[(op['渠道'] == 'Wayfair') & (op['浴室柜'].str.lower() != 'false')]
    assert (w['月度来源'] == '无（只有评论总数）').sum() == 168
    from pdt import catconfig
    _, cfg = catconfig.current()
    cfg['research']['frame_min']['wayfair'] = 200  # 上午版副本的参考表按门槛 200 产出（revision 10 前），这里按同门槛核对估算规则
    catconfig.save(cfg, None)
    import_channels(v2, ['wayfair'], op, om)
    d = rjson(v2, 'wayfair')['data']
    big = F[F['框月均'] >= 200]
    fr = {f['frame']: f for f in d['frames']}
    assert set(fr) == set(big.index) and len(fr) == 23
    f = fr['24″ · 拆装 · 落地式']
    assert round(f['units']) == 5456 and round(f['units_low']) == 4010 and f['estimated'] and f['read'] == 'noconc'
    f = fr['30″ · 整装 · 悬浮式']
    assert round(f['units_low']) == 122 and f['low_below']
    ref_read = {k for k, r in big.iterrows() if r['可读性'] == '可读'}
    assert {k for k, f in fr.items() if f['read'] == 'ok'} == ref_read
    assert {'30″ · 拆装 · 落地式', '72″+ · 拆装 · 落地式'} <= ref_read
    for k, f in fr.items():
        assert f'{f["cover"] * 100:.1f}' == f"{big.loc[k, '分框覆盖_期望'] * 100:.1f}" and round(f['units']) == round(big.loc[k, '框月均'])
        assert (f['read'] == 'noconc') == (big.loc[k, '分框覆盖_期望'] < 0.95)
    f = fr['30″ · 整装 · 落地式']
    assert f['read'] == 'notrend' and page_pct(f['monthly_share']) == '33%'
    html = v2.get('/research?channel=wayfair').text
    row = html.split('data-frame="24″ · 拆装 · 落地式"')[0].rsplit('<tr', 1)[1] + html.split('data-frame="24″ · 拆装 · 落地式"')[1].split('</tr>')[0]
    assert 'rd-noconc' in row and f'不下结论（分框覆盖 {fr["24″ · 拆装 · 落地式"]["cover"] * 100:.1f}%）' in row and '5,456' in row and '估算' in row and '低估计 4,010' in row
    assert row.count('<span class="muted">—</span>') == 8
    row = html.split('data-frame="30″ · 整装 · 落地式"')[1].split('</tr>')[0]
    assert '趋势不下结论（有月度 33%）' in row
    assert '低估计 122 · <span class="badge badge--unverified">低估计未达门槛</span>' in html
    ro = v2.get('/research?channel=wayfair&readable=1').text
    assert ro.count('data-read="ok"') == len(ref_read) and f'显示 <b class="num">{len(ref_read)}</b> / 23 个框' in ro
    # 框详情：不下结论只剩单元与体量份额；趋势不下结论的趋势、新品为"—"
    h = v2.get('/research/wayfair/frame/24-拆装-落地式').text
    assert 'data-mode-note="no-conc"' in h and '<th scope="colgroup">Amazon 同框对照</th>' not in h and '框内份额' in h and '>趋势（只用有月度销量）<' not in h
    h = v2.get('/research/wayfair/frame/30-整装-落地式').text
    assert 'data-mode-note="no-trend"' in h and '—（有月度 33%）' in h and 'Amazon 同框对照' in h and '>趋势（只用有月度销量）<' in h


# =============================================================== FLOW-38 尚未导入 / 数据不足
def test_flow38_not_imported_and_insufficient(client):
    """FLOW-38（AC-F30-22、23）：空库三渠道"尚未导入"（操作者有"去导入"，只读"等操作者导入"）；只导入 Lowe's（尺寸段改成多尺寸未拆的副本，
    模拟补数前已落框约 1%）→"数据不足"、已落框占比与原因构成、待确认数，不显示框列表；工作台同步显示。"""
    login_as(client)
    make_user('lixiaomei', '李晓梅', 'readonly')
    ro = login_as(TestClient(client.app), 'lixiaomei', '密码-123456')
    for ch in ('homedepot', 'lowes', 'wayfair'):
        h = client.get(f'/research?channel={ch}').text
        assert '尚未导入' in h and '去导入' in h and 'class="table rs-table"' not in h
        h = ro.get(f'/research?channel={ch}').text
        assert '尚未导入，等操作者导入' in h and '去导入' not in h and '导入调研数据' not in h
    p, m = sample()
    p = p[p['渠道'] == "Lowe's"].copy()
    m = m[m['渠道'] == "Lowe's"].copy()
    tot = m.assign(c=m['销量'].astype(float)).groupby('pid')['c'].sum()
    keep = tot[tot > 0].sort_values().index[:3]  # 留 3 个小商品能落框（已落框约 1%），其余改成多尺寸未拆
    m.loc[~m['pid'].isin(keep), '尺寸段'] = '多尺寸未拆'
    p.loc[~p['pid'].isin(keep), '尺寸段'] = ''
    p.loc[~p['pid'].isin(keep), '多尺寸段'] = 'True'
    dup = m.duplicated(['渠道', 'pid', '尺寸段', '月'], keep='first')
    agg = m.groupby(['渠道', 'fam', 'pid', '尺寸段', '装', '形态', '月'], as_index=False)[['VP', '非VP', '销量']].agg(lambda s: s.astype(float).sum())
    m = agg if dup.any() else m
    import_channels(client, ['lowes'], p, m)
    d = rjson(client, 'lowes')['data']
    sm = d['summary']
    assert d['state'] == 'insufficient' and sm['framed_share'] < 0.05 and sm['reasons']['多尺寸未拆'] > 0.9
    h = client.get('/research?channel=lowes').text
    assert '数据不足' in h and 'class="table rs-table"' not in h and f'{sm["framed_share"] * 100:.1f}%' in h
    for k in ('尺寸段未知', '多尺寸未拆', '装未知', '形态未知'):
        assert f'data-reason="{k}"' in h
    assert f'分框待确认 {sm["pending_products"]} 个' in h
    assert '数据不足' in ro.get('/research?channel=lowes').text
    home = htmllib.unescape(client.get('/').text)
    row = home.split('data-channel="research"')[1].split('</tr>')[0]
    assert "Lowe's 数据不足" in row and 'Home Depot 尚未导入' in row and 'Wayfair 尚未导入' in row and '历史观察 · 不进机会扫描' in row


# =============================================================== FLOW-39 历史观察与回测标记
def test_flow39_history_label_and_backtest_mark(tmp_path, tmp_path_factory, monkeypatch):
    """FLOW-39（AC-F30-24、25）：Home Depot 渠道回测"经回测（打折）"→ 有分级的单元另列"回测"标记并链到机会扫描该框；Wayfair 未回测，没有回测内容；
    页面与每个框标"历史观察"并有口径说明，不出现把握 / 分级 / 上不上。"""
    import test_channel_model as tcm
    tcm._need_cache()
    c = tcm._client(tcm._hd_base(tmp_path_factory, True), tmp_path, monkeypatch)
    from pdt.core import channel_model
    run = channel_model.latest('homedepot')
    assert run is not None and run.evidence == channel_model.EVIDENCE_OK
    import_channels(c, ['homedepot', 'wayfair'])
    d = rjson(c, 'homedepot')['data']
    units = {(fr, u['attr'], u['value']) for fr, us in d['units'].items() for u in us}
    graded = {k: v for k, v in (run.units or {}).items() if v.get('grade') and tuple(k.split('|')) in units}
    assert graded, '当前回测没有任何与调研单元重合的分级单元'
    key = '30″ · 整装 · 落地式|台面材质|岗石' if '30″ · 整装 · 落地式|台面材质|岗石' in graded else next(iter(graded))
    fr, att, val = key.split('|')
    h = c.get(f'/research/homedepot/frame/{fr.replace("″+", "p").replace("″", "").replace(" · ", "-")}').text
    row = h.split(f'data-value="{val}"')[1].split('</tr>')[0]
    assert f'回测：经回测（打折） · {graded[key]["grade"]}' in row.replace('·', ' · ').replace('  ', ' ') or f'回测：经回测（打折）· {graded[key]["grade"]}' in row
    assert '/scan?channel=homedepot&amp;frame=' in row
    for ch in ('homedepot', 'wayfair'):
        page = c.get(f'/research?channel={ch}').text
        assert '历史观察：不给把握、分级和"上 / 不上"，不进机会扫描' in page and '口径说明' in page
        for kw in ('自然位前 300', 'VP × 50 + 非 VP × 20', '采集日价', '评论家族', '幸存者偏差', '只在同渠道、同框内比较'):
            assert kw in page
        assert page.count('>历史观察<') + page.count('历史观察</span>') >= 1
    wf = rjson(c, 'wayfair')['data']
    f0 = wf['frames'][0]
    h = c.get(f'/research/wayfair/frame/{f0["slug"]}').text
    assert '回测：' not in h
    # 读到 Wayfair 回测标记的接口为空（未回测）
    from pdt.core import research
    assert research.backtest_marks('wayfair') == {}


# =============================================================== FLOW-40 打标确认联动
def test_flow40_queue_confirm_recompute(wen):
    """FLOW-40（AC-F30-26～29）：Wayfair 分框待确认进打标确认（预筛渠道 + 原因、按窗口销量降序、带原值）；多尺寸未拆候选 = 选项段 + 不进框；
    一个指定 30″、一个不进框、一个形态确认为落地式 → 30 秒内重算，30″ 框与覆盖、待确认数（减 3）更新，"不进框"销量单列。"""
    _need_ref()
    import_channels(wen, ['wayfair'])
    from pdt.core import research
    ents = research.pending_entries('wayfair')
    P = pd.read_csv(REF / '小平台调研_待人工确认.csv', dtype={'pid': str})
    assert len({e['pid'] for e in ents}) == P[P['渠道'] == 'Wayfair']['pid'].nunique()
    assert [e['sales'] for e in ents] == sorted([e['sales'] for e in ents], reverse=True)
    h = wen.get('/tagging?channel=wayfair&reason=frame&from=research').text
    assert '从渠道调研进来：已筛 Wayfair · 分框未知（渠道调研）' in h and '返回渠道调研' in h
    assert 'aria-pressed="true">分框未知（渠道调研）' in h and 'aria-pressed="true">Wayfair' in h
    first = ents[0]
    assert h.index(first['pid']) < h.index(ents[1]['pid']) and '调研导入' in h and '窗口销量' in h and '此确认也用于机会扫描' in h
    single = {pid for pid, n in pd.Series([e['pid'] for e in ents]).value_counts().items() if n == 1}
    multi = [e for e in ents if e['reason'] == '多尺寸未拆' and e['pid'] in single]
    m30 = next(e for e in multi if '30″' in e['candidates'])
    opts = [s for s in m30['raw']['选项段'].split('、') if s]
    assert m30['candidates'] == opts + ['不进框']
    m_no = next(e for e in multi if e['pid'] != m30['pid'])
    form = next(e for e in ents if e['reason'] == '形态未知' and e['pid'] in single and e['pid'] not in (m30['pid'], m_no['pid']))
    before = rjson(wen, 'wayfair')
    b30 = {f['frame']: f for f in before['data']['frames'] if f['size'] == '30″'}
    n0 = before['data']['summary']['pending_products']
    t0 = time.time()
    for e, v in ((m30, '30″'), (m_no, '不进框'), (form, '落地式')):
        r = wen.post('/tagging/research/confirm', data={'channel': 'wayfair', 'pid': e['pid'], 'tag': e['tag'], 'value': v,
                                                         'back': '/tagging?channel=wayfair&reason=frame&from=research'}, follow_redirects=False)
        assert r.status_code == 303 and 'kind=ok' in r.headers['location']
    assert time.time() - t0 < 30 * 3
    after = rjson(wen, 'wayfair')
    assert after['data']['summary']['pending_products'] == n0 - 3
    assert after['computed_at'] != before['computed_at']
    a30 = {f['frame']: f for f in after['data']['frames'] if f['size'] == '30″'}
    assert any(round(a30[k]['units']) != round(b30[k]['units']) or a30[k]['cover'] != b30[k]['cover'] for k in a30 if k in b30)
    left = {e['pid'] for e in research.pending_entries('wayfair')}
    assert not {m30['pid'], m_no['pid'], form['pid']} & left
    assert after['data']['summary']['noframe_share'] > 0
    # 分框确认同时作用于机会扫描的标签（RA-120）：写成人工确认的 Tag
    from pdt.db import session
    from pdt.models import Tag
    with session() as s:
        t = s.scalar(select(Tag).where(Tag.channel == 'wayfair', Tag.item_id == m30['pid'], Tag.tag == '尺寸段'))
        assert t.value == '30″' and t.status == 'confirmed'
    # 打标确认页计数与侧栏角标一致
    h = wen.get('/tagging?channel=wayfair&reason=frame').text
    assert f'分框未知（渠道调研） <span class="count">{research.pending_count()}</span>' in h


# =============================================================== RULE-10 NFR-014 计时
def test_rule10_timing(wen):
    """RULE-10（NFR-014）：真实样本规模，各 3 次取最大：上传到核对摘要 ≤ 60 秒、框列表 ≤ 5 秒、框详情 ≤ 3 秒、确认一个分框标签到重算完成 ≤ 30 秒。"""
    p, m = sample()
    up, lst, det, rec = [], [], [], []
    for i in range(3):
        t = time.time()
        r = upload(wen, p, m)
        wen.get('/data/research')
        up.append(time.time() - t)
        assert r.status_code == 303
        if i == 0:
            wen.post(f'/data/research/{pending_id()}/confirm', data={'channels': ['homedepot', 'wayfair', 'lowes']}, follow_redirects=False)
    for i in range(3):
        t = time.time()
        assert wen.get('/research?channel=wayfair').status_code == 200
        lst.append(time.time() - t)
        t = time.time()
        assert wen.get('/research/homedepot/frame/30-整装-落地式').status_code == 200
        det.append(time.time() - t)
    from pdt.core import research
    for i in range(3):
        e = next(x for x in research.pending_entries('wayfair') if x['tag'] == '形态')
        t = time.time()
        r = wen.post('/tagging/research/confirm', data={'channel': 'wayfair', 'pid': e['pid'], 'tag': '形态', 'value': '落地式'}, follow_redirects=False)
        rec.append(time.time() - t)
        assert r.status_code == 303 and 'kind=ok' in r.headers['location']
    print(f'RULE-10 计时（秒，最大）：上传到摘要 {max(up):.1f}、框列表 {max(lst):.2f}、框详情 {max(det):.2f}、确认到重算 {max(rec):.1f}')
    assert max(up) <= 60 and max(lst) <= 5 and max(det) <= 3 and max(rec) <= 30


# =============================================================== RULE-11 不改分析库 + 权限
def _analysis_state():
    from pdt.db import Base, session
    names = ['batch', 'snapshot', 'opportunity', 'unit_score', 'model_run', 'card', 'forecast', 'channel_model_run', 'product', 'tag']
    out = {}
    with session() as s:
        for t in Base.metadata.sorted_tables:
            if t.name in names:
                rows = s.execute(select(t)).all()
                out[t.name] = (len(rows), hash(tuple(sorted(map(str, rows)))))
    return out


def test_rule11_import_leaves_analysis_and_permissions(v2):
    """RULE-11（AC-F30-08、09）：导入并确认真实样本后 F28 批次 / 快照、机会扫描、回测、决策卡、台账逐项不变；只读与审批者对导入检查、确认、放弃、
    分框确认的请求全部"无权限"、调研数据不变；三类角色都能打开渠道调研与框详情。"""
    v2.get('/scan?channel=amazon')
    before = _analysis_state()
    scan_before = v2.get('/scan?channel=amazon').text
    import_channels(v2, ['homedepot', 'wayfair', 'lowes'])
    assert _analysis_state() == before
    def main(t):  # 只比主区内容；去掉“用时 x 秒”
        return re.sub(r'用时 [\d.]+ 秒', '', t.split('<main')[1])
    assert main(v2.get('/scan?channel=amazon').text) == main(scan_before)
    p, m = sample()
    upload(v2, p, m)
    iid = pending_id()
    from pdt.core import research
    e = research.pending_entries('wayfair')[0]
    state = research_state()
    make_user('lixiaomei', '李晓梅', 'readonly')
    make_user('zhoujianguo', '周建国', 'approver')
    for u in ('lixiaomei', 'zhoujianguo'):
        c = login_as(TestClient(v2.app), u, '密码-123456')
        h = {'accept': 'application/json'}
        reqs = [c.post('/data/research/check', files={'products': ('a.csv', csvb(p)), 'monthly': ('b.csv', csvb(m))}, headers=h),
                c.post(f'/data/research/{iid}/confirm', data={'channels': ['wayfair']}, headers=h),
                c.post(f'/data/research/{iid}/abandon', headers=h),
                c.post('/tagging/research/confirm', data={'channel': 'wayfair', 'pid': e['pid'], 'tag': e['tag'], 'value': e['candidates'][0]}, headers=h)]
        for r in reqs:
            assert r.status_code == 403 and r.json()['detail'] == '无权限'
        assert c.get('/data/research').status_code == 403
        page = c.get('/research?channel=wayfair')
        assert page.status_code == 200 and '导入调研数据' not in page.text and 'data-pending-bar' not in page.text and '去打标确认' not in page.text
        assert c.get('/research/homedepot/frame/30-整装-落地式').status_code == 200
    assert research_state() == state
    assert v2.get('/research/homedepot/frame/30-整装-落地式').status_code == 200

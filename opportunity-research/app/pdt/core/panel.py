"""分析面板（开发约定 `pdt/core/panel.py`，决策卡组调用）。

- `load_panel(channel)`：行 = 月 × 商品，列 month, item_id, parent, family_key, series, brand, title, image_url, link, listed_at, price, units,
  revenue, rank, rating, ratings_count, age_months, frame 及各标签列（尺寸段、装、形态、台面材质、台盆材质、台面、元素、主色、柜体材质）。
- `unit_timeseries / unit_skus / price_bands`：口径移植第二轮 `决策卡.py`、`决策卡_SKU.py`，一律只在同一渠道、同一“尺寸 × 拆装 × 形态”框内比。

数据只取已并入（merged）批次；被标“不是本品类”的商品（Product.excluded）与不纳入分析的行不进入任何分析。
标签取值：已确认值优先；其次是该行并入时的标签（第二轮导入的逐月标签）；再次是当前自动值（含待确认）。
其他渠道月销 = VP × vp_coef + 非 VP × nonvp_coef（品类配置当前版本），VP / 非 VP 条数已按评论 ID 去重（见 channels.py）。
"""
import json
import threading

import numpy as np
import pandas as pd
from sqlalchemy import text

from ..config import CATEGORY, data_dir
from ..db import engine
from . import families as fm

TAGS = ['尺寸段', '装', '形态', '台面材质', '台盆材质', '元素', '主色', '柜体材质']
UNKNOWN_VALUES = {'', '未知', '信息不足', '待图片核验', 'None', 'nan'}
_cache: dict = {}
_lock = threading.Lock()


# ---------------- 读库 ----------------
def signature() -> tuple:
    """数据版本：批次、标签、排除、品类配置变化都会改变它（缓存键）。"""
    with engine().connect() as c:
        row = c.execute(text(
            "select (select coalesce(max(id),0) || ':' || count(*) from batch where status='merged' and category=:c),"
            " (select count(*) || ':' || coalesce(max(id),0) || ':' || coalesce(max(confirmed_at),'') || ':' || coalesce(sum(length(value)),0) from tag where category=:c),"
            " (select count(*) || ':' || coalesce(max(excluded_at),'') from product where excluded=1 and category=:c),"
            " (select coalesce(max(version),0) from category_config where category=:c),"
            " (select count(*) || ':' || coalesce(max(id),0) from snapshot where category=:c),"
            " (select coalesce(max(value),'') from setting where key='data_version')"), dict(c=CATEGORY)).one()
    return (str(data_dir()),) + tuple(row)


def bump():
    """数据被改写但行数不变时（如重算排名平滑、改标签）调用，使缓存失效。"""
    from .. import services
    services.put_setting('data_version', (services.get_setting('data_version', 0) or 0) + 1)


def config():
    from .. import catconfig
    return catconfig.current()[1]


def raw_frame(channel: str = 'amazon') -> pd.DataFrame:
    """已并入的行（月 × 商品），标签已按优先级取值；不含被排除的商品和不纳入分析的行。按入库顺序排列。"""
    eng = engine()
    snaps = pd.read_sql(text(
        "select s.id as sid, s.month, s.item_id, s.price, s.units, s.revenue, s.rank, s.rating, s.ratings_count, s.vp, s.nonvp, s.raw, "
        "b.star, b.anomaly_reason from snapshot s join batch b on b.id = s.batch_id "
        "where b.status = 'merged' and s.channel = :ch and s.category = :c order by s.id"), eng, params=dict(ch=channel, c=CATEGORY))
    prods = pd.read_sql(text("select item_id, parent, family_key, series, brand, title, image_url, link, listed_at, excluded from product "
                             "where channel = :ch and category = :c"), eng, params=dict(ch=channel, c=CATEGORY)).set_index('item_id')
    tags = pd.read_sql(text("select item_id, tag, value, status from tag where channel = :ch and category = :c"), eng, params=dict(ch=channel, c=CATEGORY))
    cols = ['month', 'item_id', 'family_key', 'parent', 'series', 'brand', 'title', 'image_url', 'link', 'listed_at', 'price', 'units', 'fam_units',
            'child_units', 'revenue', 'rank', 'rating', 'ratings_count', 'vp', 'nonvp', 'star', 'anomaly_reason'] + TAGS
    if snaps.empty:
        return pd.DataFrame(columns=cols)
    raw = [json.loads(r) if isinstance(r, str) else (r or {}) for r in snaps['raw']]
    snaps = snaps.drop(columns=['raw'])
    ex = set(prods.index[prods['excluded'].astype(bool)])
    keep = np.array([(r.get('in_scope', True) is not False) for r in raw]) & ~snaps['item_id'].isin(ex).values
    snaps = snaps[keep].reset_index(drop=True)
    raw = [r for r, k in zip(raw, keep) if k]
    P = prods.reindex(snaps['item_id'])

    def pick(key, pcol):
        pv = P[pcol].values
        return [r.get(key) if r.get(key) not in (None, '') else (p if isinstance(p, str) else '') for r, p in zip(raw, pv)]
    out = pd.DataFrame({'month': snaps['month'], 'item_id': snaps['item_id']})
    out['family_key'] = pick('family_key', 'family_key')
    out['family_key'] = [f or i for f, i in zip(out['family_key'], out['item_id'])]
    for k, pc in (('parent', 'parent'), ('series', 'series'), ('brand', 'brand'), ('title', 'title'), ('image_url', 'image_url'), ('link', 'link'), ('listed_at', 'listed_at')):
        out[k] = pick(k, pc)
    for k in ('price', 'units', 'revenue', 'rank', 'rating', 'ratings_count', 'vp', 'nonvp'):
        out[k] = pd.to_numeric(snaps[k], errors='coerce')
    out['fam_units'] = pd.to_numeric(pd.Series([r.get('fam_units') for r in raw]), errors='coerce')
    out['child_units'] = pd.to_numeric(pd.Series([r.get('child_units') for r in raw]), errors='coerce')
    out['star'] = snaps['star'].astype(bool).values
    out['anomaly_reason'] = snaps['anomaly_reason'].fillna('').values
    # 标签：确认值 > 并入时标签 > 当前自动值
    conf = tags[tags['status'] == 'confirmed'].set_index(['item_id', 'tag'])['value'].to_dict()
    auto = tags[tags['status'] != 'confirmed'].set_index(['item_id', 'tag'])['value'].to_dict()
    for t in TAGS:
        vals = []
        for i, r in zip(out['item_id'], raw):
            v = conf.get((i, t))
            if v is None:
                v = (r.get('tags') or {}).get(t)
            if v is None:
                v = auto.get((i, t), '')
            vals.append(v or '')
        out[t] = vals
    if channel != 'amazon':
        cfg = (config().get('channels') or {}).get(channel) or {}
        vp_c, nv_c = float(cfg.get('vp_coef', 50)), float(cfg.get('nonvp_coef', 20))
        vpd = pd.to_numeric(pd.Series([r.get('vp_d') for r in raw]), errors='coerce').fillna(out['vp'].fillna(0))
        nvd = pd.to_numeric(pd.Series([r.get('nonvp_d') for r in raw]), errors='coerce').fillna(out['nonvp'].fillna(0))
        out['units'] = vpd * vp_c + nvd * nv_c  # 评论换算法；VP / 非 VP 已按评论 ID 去重分摊
        if cfg.get('method') == 'rank':  # 排名平滑法（AC-F28-04）：有拟合值的行用拟合值
            ur = pd.to_numeric(pd.Series([r.get('units_rank') for r in raw]), errors='coerce')
            out['units'] = np.where(ur.notna(), ur, out['units'])
        out['fam_units'] = out['units']
    return out[cols]


# ---------------- 分析对象（缓存） ----------------
class Analysis:
    """一个渠道的分析底表：A（第二轮口径的行级表）、U（新家族）、feat、TK、END（数据截至月序号）。"""

    def __init__(self, channel, raw):
        self.channel = channel
        self.raw = raw
        if raw.empty:
            self.A, self.U, self.feat, self.TK, self.END = pd.DataFrame(), pd.DataFrame(), {}, {}, None
            return
        if channel == 'amazon':
            self.A, self.U, self.feat, self.TK = fm.build(raw)
        else:
            self.A, self.U, self.feat, self.TK = channel_frame(raw), pd.DataFrame(columns=['L', 'y']), {}, {}
        self.A['star'] = raw['star'].values
        self.A['anomaly_reason'] = raw['anomaly_reason'].values
        for k in ('series', 'parent', 'ratings_count', 'revenue', 'rank', 'listed_at', 'title', 'image_url', 'link', 'brand'):
            self.A['_' + k] = raw[k].values
        self.A['台盆材质_'] = raw['台盆材质'].values
        self.END = int(self.A['m'].max())

    @property
    def months(self):
        return [] if self.A.empty else sorted(self.A['月份'].unique())

    def star_months(self) -> dict:
        if self.A.empty:
            return {}
        s = self.A[self.A['star']].drop_duplicates('月份')
        return dict(zip(s['月份'], s['anomaly_reason']))


def channel_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """其他渠道：同一套列，家族 = 系列（没有系列用商品 ID），月龄 = 上架日期起算（缺上架日期用首次出现月）。"""
    A = pd.DataFrame({'月份': raw['month'].values, '子ASIN': raw['item_id'].values,
                      '家族键': [s or i for s, i in zip(raw['series'], raw['item_id'])], '品牌': raw['brand'].values,
                      '价格': pd.to_numeric(raw['price'], errors='coerce').values, '小类BSR': pd.to_numeric(raw['rank'], errors='coerce').values,
                      '评分': pd.to_numeric(raw['rating'], errors='coerce').values, '家族月销': raw['units'].values, '上架日期': raw['listed_at'].values,
                      '标题': raw['title'].values, '主图500': raw['image_url'].values, '商品链接': raw['link'].values,
                      'D8台面材质': raw['台面材质'].values, 'D8台盆材质': raw['台盆材质'].values})
    A['m'] = A['月份'].map(fm.mi)
    A['c'] = pd.to_numeric(raw['units'], errors='coerce').fillna(0).clip(lower=0).values
    A['尺寸段'] = raw['尺寸段'].replace('', None).values
    A['装'] = np.where(raw['装'].eq('整装').values, '整装', '拆装')
    A['柜体材质'] = raw['柜体材质'].map(lambda v: v or '未知').values
    A['台面类型'] = [fm.top_type(t, s) for t, s in zip(A['D8台面材质'], A['D8台盆材质'])]
    A['元素一'] = raw['元素'].map(fm.elements_from_tag).values
    A['主色'] = raw['主色'].map(lambda v: v or '未知').values
    A['形态'] = raw['形态'].map(lambda v: v or '落地式').values
    A['单位'] = A['家族键']
    up = pd.to_datetime(A['上架日期'].replace('', None), errors='coerce')
    first = A.groupby('子ASIN')['m'].transform('min')
    L = np.where(up.notna(), up.dt.year * 12 + up.dt.month - 1, first)
    A['L'] = L
    A['月龄'] = A['m'] - A['L'] + 1
    return A


def analysis(channel: str = 'amazon') -> Analysis:
    sig = signature()
    key = (channel,)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == sig:
            return hit[1]
    an = Analysis(channel, raw_frame(channel))
    with _lock:
        _cache[key] = (sig, an)
    return an


def clear_cache():
    with _lock:
        _cache.clear()


# ---------------- 开发约定接口 ----------------
def load_panel(channel: str = 'amazon') -> pd.DataFrame:
    an = analysis(channel)
    A = an.A
    cols = ['month', 'item_id', 'parent', 'family_key', 'series', 'brand', 'title', 'image_url', 'link', 'listed_at', 'price', 'units', 'revenue',
            'rank', 'rating', 'ratings_count', 'age_months', 'frame', 'star'] + ['尺寸段', '装', '形态', '台面材质', '台盆材质', '台面', '元素', '主色', '柜体材质']
    if A.empty:
        return pd.DataFrame(columns=cols)
    form_ok = A['尺寸段'].notna() & A['形态'].isin(['落地式', '悬浮式'])
    out = pd.DataFrame({
        'month': A['月份'], 'item_id': A['子ASIN'], 'parent': A['_parent'], 'family_key': A['家族键'], 'series': A['_series'], 'brand': A['品牌'],
        'title': A['标题'], 'image_url': A['主图500'], 'link': A['商品链接'], 'listed_at': A['_listed_at'], 'price': A['价格'], 'units': A['c'],
        'revenue': A['_revenue'], 'rank': A['小类BSR'], 'rating': A['评分'], 'ratings_count': A['_ratings_count'], 'age_months': A['月龄'],
        'frame': np.where(form_ok, A['尺寸段'].astype(str) + ' · ' + A['装'].astype(str) + ' · ' + A['形态'].astype(str), None), 'star': A['star'],
        '尺寸段': A['尺寸段'], '装': A['装'], '形态': A['形态'], '台面材质': A['D8台面材质'], '台盆材质': A['D8台盆材质'], '台面': A['台面类型'],
        '元素': A['元素一'].map(lambda t: '|'.join(t)), '主色': A['主色'], '柜体材质': A['柜体材质']})
    return out.reset_index(drop=True)


ATTR_COL = {'台面材质': 'D8台面材质', '元素': '元素一', '主色': '主色', '柜体材质': '柜体材质', '台面': '台面类型', '尺寸段': '尺寸段'}


def _frame_attr(channel, frame, attr):
    """框内、属性已知的行（元素按多值展开），加 值、价比（÷ 同月同框中位价）、评分、新品。"""
    from .scan import frame_rows
    an = analysis(channel)
    if an.A.empty:
        return an, pd.DataFrame()
    B = frame_rows(an.A)
    d = B[B['框'] == frame]
    col = ATTR_COL.get(attr, attr)
    d = d.assign(值=d[col])
    if col == '元素一':
        d = d.explode('值')
    d = d[d['值'].notna() & ~d['值'].map(fm.UNK) & ~d['值'].isin(['信息不足', '不适用（不含台面）'])]
    return an, d


def _stats(d):
    from .scan import wmed
    if d.empty:
        return dict(units=0.0, families=0, median_price=None, premium=None, rating=None, newshare=None)
    rr = d.dropna(subset=['r'])
    nz = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
    return dict(units=float(d['c'].sum()), families=int(d['家族键'].nunique()), median_price=nz(wmed(d['价格'], d['c'])), premium=nz(wmed(d['价比'], d['c'])),
                rating=nz((rr['r'] * rr['c']).sum() / rr['c'].sum()) if rr['c'].sum() > 0 else None,
                newshare=nz(d.loc[d['新'], 'c'].sum() / d['c'].sum()) if d['c'].sum() > 0 else None)


def unit_timeseries(channel, frame, attr, value) -> list[dict]:
    """逐月：该取值在框内的月销、份额（÷ 框内该属性已知的销量）、新品占比、溢价、中位价、评分，以及同框对照；star = 该月为带 * 的异常月。"""
    an, d = _frame_attr(channel, frame, attr)
    if d.empty:
        return []
    stars = an.star_months()
    out = []
    for m, dm in d.groupby('m'):
        t = dm[dm['值'] == value]
        s, f = _stats(t), _stats(dm)
        month = fm.ms(m)
        out.append(dict(month=month, units=s['units'], share=(s['units'] / f['units']) if f['units'] else None, families=s['families'],
                        newshare=s['newshare'], frame_newshare=f['newshare'], premium=s['premium'], median_price=s['median_price'],
                        rating=s['rating'], frame_rating=f['rating'], frame_units=f['units'], star=month in stars, star_reason=stars.get(month, '')))
    return out


def unit_skus(channel, frame, attr, value, top=20) -> list[dict]:
    """框内该取值的子体：峰值月、最好排名、首次进前 50、逐月价格 / 价比 / 评分 / 月销 / 排名（AC-F21-04）。"""
    an, d = _frame_attr(channel, frame, attr)
    if d.empty:
        return []
    d = d[d['值'] == value].drop_duplicates(['子ASIN', 'm'])
    rows = []
    for a, g in d.groupby('子ASIN'):
        g = g.sort_values('m')
        pk = g.loc[g['c'].idxmax()]
        rk = pd.to_numeric(g['小类BSR'], errors='coerce')
        f50 = g[rk <= 50]
        last = g.iloc[-1]
        spec = ' · '.join(x for x in [str(last['D8台面材质'] or ''), '、'.join(last['元素一']) if isinstance(last['元素一'], list) else '', str(last['主色'] or '')] if x)
        rows.append(dict(item_id=a, link=last['商品链接'] or '', image_url=last['主图500'] or '', brand=last['品牌'] or '', title=last['标题'] or '', spec=spec,
                         family_key=last['家族键'], first_month=fm.ms(g['m'].min()), months_listed=int(g['m'].nunique()), peak_month=fm.ms(pk['m']),
                         peak_units=float(pk['c']), peak_price=None if pd.isna(pk['价格']) else float(pk['价格']),
                         best_rank=None if rk.isna().all() else float(rk.min()),
                         first_top50=fm.ms(f50['m'].min()) if len(f50) else None,
                         first_top50_age=int(f50['m'].min() - g['m'].min()) + 1 if len(f50) else None,
                         series=[dict(month=fm.ms(r['m']), price=None if pd.isna(r['价格']) else float(r['价格']),
                                      price_ratio=None if pd.isna(r['价比']) else float(r['价比']), rating=None if pd.isna(r['r']) else float(r['r']),
                                      units=float(r['c']), rank=None if pd.isna(r['小类BSR']) else float(r['小类BSR'])) for _, r in g.iterrows()]))
    rows.sort(key=lambda r: -r['peak_units'])
    return rows[:top]


PRICE_BANDS = [0, 200, 250, 300, 400, 1e9]
BAND_LABELS = ['< $200', '$200–250', '$250–300', '$300–400', '≥ $400']


def price_bands(channel, frame, attr, value) -> list[dict]:
    """价格带（子体 × 月算一次）：子体数、子体 × 月、月销中位 / 最高、评分中位、该带月销占比与逐季构成（AC-F21-05）。"""
    an, d = _frame_attr(channel, frame, attr)
    if d.empty:
        return []
    d = d[d['值'] == value].drop_duplicates(['子ASIN', 'm'])
    d = d.assign(带=pd.cut(d['价格'], PRICE_BANDS, labels=BAND_LABELS, right=False))
    tot = d['c'].sum()
    d['季度'] = d['m'].map(lambda m: f"{fm.ms(m)[:4]}Q{(int(fm.ms(m)[5:]) - 1) // 3 + 1}")
    qt = d.groupby('季度')['c'].sum()
    out = []
    for b, g in d.groupby('带', observed=True):
        q = g.groupby('季度')['c'].sum()
        out.append(dict(band=str(b), skus=int(g['子ASIN'].nunique()), sku_months=int(len(g)), units_median=float(g['c'].median()),
                        units_max=float(g['c'].max()), rating_median=None if g['r'].isna().all() else float(g['r'].median()),
                        units_total=float(g['c'].sum()), share=float(g['c'].sum() / tot) if tot else None,
                        quarters={k: float(v / qt[k]) if qt.get(k) else None for k, v in q.items()}))
    return out

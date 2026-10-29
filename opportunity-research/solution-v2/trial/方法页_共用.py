"""方法页核对脚本共用的读数：1–5 月分析用表 + 6–9 月 df.pkl（TRIAL_DUMP），尺寸分段与关键词逐月搜索量。"""
import os, glob, json, re, numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
S = os.environ['TRIAL_DUMP']; KW = os.path.join(ROOT, 'input/data_v2/keywords_20261028')
Q15 = os.path.join(ROOT, 'input/data_v2/202601-202605_打标/BathroomVanities_202601-202605_分析用.pkl')
SIZE = [(18, 15, 21), (24, 21, 27), (30, 27, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]  # wen 矩阵：±3 寸归段
ORDER = ['18″', '24″', '30″', '36″', '42″', '48″', '60″', '72″+']

def band(x):
    try: x = float(x)
    except (TypeError, ValueError): return None
    if np.isnan(x): return None
    for c, lo, hi in SIZE:
        if lo <= x < hi: return f'{c}″'
    return '72″+' if x >= 66 else None

def rows():
    """1–9 月子体行：月、父体、子体、父体月销、家族 BSR、宽度、子体销量、上架日、品牌。"""
    q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
    a = pd.DataFrame({'m': q['目标月份'], 'p': q['核验父ASIN'], 'k': q['子ASIN'], 'ps': q['父体月销量'].astype(float), 'bsr': pd.to_numeric(q['小类BSR'], errors='coerce'),
                      'w': q['D9宽(in)'], 'c': q['子体月销量（父体全分给导出子体）'], 'up': pd.to_datetime(q['上架日期'], errors='coerce'), 'brand': q['品牌']})
    d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
    v = pd.DataFrame({'m': d['月'].str[:4] + '-' + d['月'].str[4:], 'p': d['核验父ASIN'], 'k': d['子ASIN'], 'ps': d['父体月销量预测'].astype(float), 'bsr': d['BSR'],
                      'w': d['D9宽(in)'], 'c': pd.to_numeric(d['最终SKU月销量估算'], errors='coerce'), 'up': pd.to_datetime(d['上架日期'], errors='coerce'), 'brand': d['品牌']})
    return pd.concat([a, v], ignore_index=True)

def top150(x):
    """每月只留父体月销量前 150 个家族，避开每月名单深浅不同。"""
    t = x.groupby(['m', 'p'])['ps'].first().groupby(level=0, group_keys=False).nlargest(150).reset_index()[['m', 'p']]
    return x.merge(t, on=['m', 'p'])

def searches():
    """关键词逐月搜索量（原始回包），附宽度段。"""
    tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv'); b = tag.set_index('关键词')['宽度（英寸）'].map(band)
    out = []
    for f in sorted(glob.glob(f'{KW}/数据/02_Amazon历史趋势/raw/*.json')):
        j = json.load(open(f, encoding='utf-8'))
        for r in json.loads(j['response']['content'][0]['text'])['data']:
            y, m = re.match(r'(\d{4})年(\d{2})月', r['time']).groups(); out.append((j['keyword'], f'{y}-{m}', r['search']))
    k = pd.DataFrame(out, columns=['kw', 'm', 's']); k['band'] = k.kw.map(b)
    return k

TAGS = {'D2安装方式': '装', 'D1产品形态': '形态', 'D4台面形态': '台盆位置', 'D3盆数': '盆数', 'D8台面材质': '台面材质', 'D8台盆材质': '台盆材质',
        'D7柜体材质': '柜体材质', 'D5元素': '元素', 'D6柜体颜色': '颜色'}
UNK = {'信息不足', '待图片核验', '未知', '待核实', '未提及', 'nan', ''}

def tagged():
    """1–9 月子体行，带打标维度（未知标签记为 None）、价格、评分、上架日、品牌、尺寸段、精确尺寸、家族月龄（age）和家族当月最好 BSR（fbsr）。"""
    q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
    a = pd.DataFrame({'m': q['目标月份'], 'p': q['核验父ASIN'], 'k': q['子ASIN'], 'c': pd.to_numeric(q['子体月销量（父体全分给导出子体）'], errors='coerce'),
                      'bsr': pd.to_numeric(q['小类BSR'], errors='coerce'), 'price': pd.to_numeric(q['商品价格'], errors='coerce'), 'rt': pd.to_numeric(q['评分'], errors='coerce'),
                      'up': pd.to_datetime(q['上架日期'], errors='coerce'), 'brand': q['品牌'], 'w': pd.to_numeric(q['D9宽(in)'], errors='coerce'), **{v: q[k] for k, v in TAGS.items()}})
    d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
    b = pd.DataFrame({'m': d['月'].str[:4] + '-' + d['月'].str[4:], 'p': d['核验父ASIN'], 'k': d['子ASIN'], 'c': pd.to_numeric(d['最终SKU月销量估算'], errors='coerce'),
                      'bsr': pd.to_numeric(d['BSR'], errors='coerce'), 'price': pd.to_numeric(d['商品价格'], errors='coerce'), 'rt': pd.to_numeric(d['商品评分'], errors='coerce'),
                      'up': pd.to_datetime(d['上架日期'], errors='coerce'), 'brand': d['品牌'], 'w': pd.to_numeric(d['D9宽(in)'], errors='coerce'), **{v: d[k] for k, v in TAGS.items()}})
    x = pd.concat([a, b], ignore_index=True)
    for c in TAGS.values():
        x[c] = x[c].astype(object).where(x[c].notna(), None).map(lambda s: None if s is None or str(s) in UNK else str(s))
    x['尺寸段'] = x['w'].map(band); x['精确尺寸'] = x['w'].round().map(lambda v: None if pd.isna(v) else f'{int(v)}″')
    x = x.dropna(subset=['尺寸段', 'price']).reset_index(drop=True)
    x['c'] = x['c'].clip(lower=0).fillna(0)
    mi = lambda s: int(s[:4]) * 12 + int(s[5:7])
    x['age'] = x['m'].map(mi) - x['p'].map(x.groupby('p')['up'].min().map(lambda t: t.year * 12 + t.month if pd.notna(t) else np.nan)) + 1
    x['fbsr'] = x.groupby(['m', 'p'])['bsr'].transform('min')
    return x

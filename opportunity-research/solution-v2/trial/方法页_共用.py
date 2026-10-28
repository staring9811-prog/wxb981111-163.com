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

"""按"基准阶梯 + 模式信号"模拟 wen 给的 5 个案例：Fluted（冒头）、岗石台面（需求被验证但没做好）、Shaker mix（天花板被突破）、42″ 与 28″（空档）。
数据：2026-01 至 09 每月父体月销 ≥ 60 的家族（6–9 月价格、评分是采集时快照）。
基准阶梯：全品类 → 同尺寸段 → + 整装/拆装 → + 柜体材质 → + 台面材质；比哪个维度就跳过哪一层；格子里要有候选、且其他家族 ≥ 3 家才算。
信号（每月）：份额、增长比（近 3 月 ÷ 前 3 月）、新进入家族（上架 ≤ 3 个月）及其中进前 100 的、进入倾斜（新家族里选这个取值的比例 ÷ 现有家族里的比例）、
溢价、评分差、单位 ASIN 贡献、破顶销量占比（这个取值本月卖出的件数里，价格高过它自己同尺寸段以前各月按件数算的前 10% 价格的比例；至少 3 个月历史）、关键词缺口。
"比平均高"：同月所有候选（维度 × 取值，同尺寸段基准下 ≥ 3 个家族）里的百分位，100 = 最高。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 模拟_案例.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import KW, searches, tagged

LADDER = ['尺寸段', '装', '柜体材质', '台面材质']  # 同尺寸后按对价格影响从大到小；台面材质影响最大但一半没标签，暂放最后
DIMS = ['尺寸段', '精确尺寸', '装', '形态', '台盆位置', '盆数', '台面材质', '台盆材质', '柜体材质', '元素', '颜色']
MIN_OTHER = 3
pd.set_option('display.width', 250)

x = tagged()
MONTHS = sorted(x.m.unique())

MEM = {}
for dim in DIMS:  # 每行属于这个维度的哪个取值；元素可以有几个（Fluted；Farmhouse）
    s = x[dim].dropna()
    MEM[dim] = s.str.split('；').explode().str.strip() if dim == '元素' else s

def wmean(v, w):
    ok = v.notna(); v, w = v[ok], w[ok]
    if len(v) == 0: return np.nan
    return np.average(v, weights=w) if w.sum() > 0 else v.mean()

def rung(dim, r):
    """阶梯第 r 层的分格维度（0 = 全品类）；比哪个维度就跳过哪一层，比尺寸时不按尺寸段分格。"""
    return [k for k in LADDER[:r] if k != dim and not (dim in ('尺寸段', '精确尺寸') and k == '尺寸段')]

def signals(dim, val, keys, m):
    xm = x[x.m == m]
    if keys: xm = xm.dropna(subset=keys)
    mem = MEM[dim]; xm = xm.assign(cand=xm.index.isin(mem[mem == val].index))
    u_c = u_all = f_c = f_all = n_c = n_all = 0.0; lr, gap, wt = [], [], []
    for _, cell in (xm.groupby(keys) if keys else [(None, xm)]):
        cf = set(cell.loc[cell.cand, 'p']); of = set(cell.loc[~cell.cand, 'p']) - cf
        if not cf or len(of) < MIN_OTHER: continue
        cc, oo = cell[cell.cand], cell[~cell.cand & ~cell.p.isin(cf)]
        u_c += cc.c.sum(); u_all += cc.c.sum() + oo.c.sum(); f_c += len(cf); f_all += len(cf) + len(of)
        n_c += cc.loc[cc.age <= 3, 'p'].nunique(); n_all += cc.loc[cc.age <= 3, 'p'].nunique() + oo.loc[oo.age <= 3, 'p'].nunique()
        lr.append(wmean(np.log(cc.price), cc.c) - wmean(np.log(oo.price), oo.c))
        gap.append(wmean(cc.rt, cc.c) - wmean(oo.rt, oo.c)); wt.append(cc.c.sum() + 1e-9)
    if f_c == 0: return None
    share = u_c / u_all if u_all else np.nan
    lr, gap, wt = np.array(lr), np.array(gap), np.array(wt)
    ok = ~np.isnan(gap)
    return {'家族': int(f_c), '份额': share, '单位ASIN贡献': share / (f_c / f_all) if f_all else np.nan,
            '溢价': float(np.exp(np.average(lr, weights=wt))), '评分差': float(np.average(gap[ok], weights=wt[ok])) if ok.any() else np.nan,
            '进入倾斜': (n_c / n_all) / (f_c / f_all) if n_all else np.nan}

def entrants(dim, val, m):
    mem = MEM[dim]; r = x[(x.m == m) & x.index.isin(mem[mem == val].index) & (x.age <= 3)]
    return r.p.nunique(), r.loc[r.fbsr <= 100, 'p'].nunique()

def wq(v, w, p):
    """按件数加权的分位价。"""
    o = np.argsort(v.values); v, cw = v.values[o], np.cumsum(w.values[o])
    return v[np.searchsorted(cw, p * cw[-1])]

def ceiling(dim, val, m):
    """破顶销量占比：同尺寸段里，这个取值本月卖出的件数中，价格高过它自己以前各月按件数算的前 10% 价格（P90）的比例。
    用子体自己的件数，不用家族 BSR（家族排名会把同家族的高价弱子体带好）；以前至少 3 个月有销量才算。"""
    mem = MEM[dim]; r = x[x.index.isin(mem[mem == val].index) & (x.c > 0)]
    hit = tot = 0.0
    for _, g in r.groupby('尺寸段'):
        now, before = g[g.m == m], g[g.m < m]
        if now.empty or before.m.nunique() < 3: continue
        hit += now.loc[now.price > wq(before.price, before.c, 0.9), 'c'].sum(); tot += now.c.sum()
    return hit / tot if tot else np.nan

# ---- 所有候选在"同尺寸段"基准下的逐月信号，用来算百分位 ----
rows = []
for dim in DIMS:
    for val in MEM[dim].value_counts().index:
        for m in MONTHS:
            s = signals(dim, val, rung(dim, 1), m)
            if s is None or s['家族'] < MIN_OTHER: continue
            ne, nt = entrants(dim, val, m)
            rows.append({'维度': dim, '取值': val, 'm': m, **s, '新进入': ne, '新进入进前100': nt, '破顶销量占比': ceiling(dim, val, m)})
allc = pd.DataFrame(rows).sort_values(['维度', '取值', 'm'])
allc['增长比'] = allc.groupby(['维度', '取值'])['份额'].transform(lambda s: s.rolling(3).mean() / s.shift(3).rolling(3).mean())
SIG = ['份额', '增长比', '进入倾斜', '单位ASIN贡献', '溢价', '评分差', '破顶销量占比']
for c in SIG: allc[c + '分位'] = allc.groupby('m')[c].rank(pct=True).mul(100).round()
print(f'候选（维度 × 取值）每月 {allc.groupby("m").size().median():.0f} 个（同尺寸段基准下 ≥ 3 个家族）')

def show(dim, val, cols):
    t = allc[(allc.维度 == dim) & (allc.取值 == val)].set_index('m')
    print(t[[c for c in cols]].round(2).T.to_string())

# ---- 关键词：按尺寸段、精确尺寸的搜索份额 − 销量份额 ----
k = searches().rename(columns={'band': '尺寸段'}); tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv').set_index('关键词')['宽度（英寸）']
k['精确尺寸'] = k.kw.map(tag).map(lambda v: None if pd.isna(v) else f'{int(round(v))}″')
def kgap(col):
    s = k.dropna(subset=[col]).groupby(['m', col])['s'].sum(); s = s / s.groupby(level=0).transform('sum')
    u = x.groupby(['m', col])['c'].sum(); u = u / u.groupby(level=0).transform('sum')
    g = (s - u.reindex(s.index).fillna(0)).rename('缺口').reset_index()
    g = g[g.m.isin(MONTHS)]; g['分位'] = g.groupby('m')['缺口'].rank(pct=True).mul(100).round()
    return g

print('\n==== 1. Fluted（元素）· 冒头 ====')
show('元素', 'Fluted', ['家族', '份额', '增长比', '增长比分位', '新进入', '新进入进前100', '进入倾斜', '进入倾斜分位', '溢价', '溢价分位'])
fl = k[k.kw == 'fluted bathroom vanity'].set_index('m')['s']
print('"fluted bathroom vanity" 月搜索量：', {m: int(fl.get(m, 0)) for m in ['2025-03', '2025-06', '2025-09', '2025-12'] + MONTHS})

print('\n==== 2. 岗石台面 · 需求被验证但没做好 ====')
show('台面材质', '岗石', ['家族', '份额', '单位ASIN贡献', '单位ASIN贡献分位', '溢价', '溢价分位', '评分差', '评分差分位', '新进入', '新进入进前100', '进入倾斜分位'])
print('溢价沿阶梯（每月中位）：', {('全品类' if r == 0 else ' + '.join(rung('台面材质', r))): round(float(np.nanmedian([
    (signals('台面材质', '岗石', rung('台面材质', r), m) or {'溢价': np.nan})['溢价'] for m in MONTHS])), 2) for r in range(4)})
g = x[x.index.isin(MEM['台面材质'][MEM['台面材质'] == '岗石'].index)]
top = g[g.fbsr <= 100].groupby('p').m.agg(['min', 'max']); last = g.groupby('p').m.max()
gone = top[(last.reindex(top.index) < MONTHS[-1])]
alltop = x[x.fbsr <= 100].groupby('p').m.max(); allgone = (x.groupby('p').m.max().reindex(alltop.index) < MONTHS[-1]).mean()
print(f'到过前 100 的岗石家族 {len(top)} 个，其中 9 月前已从表里消失的 {len(gone)} 个（{len(gone) / len(top):.0%}；全部到过前 100 的家族里这个比例是 {allgone:.0%}）')

print('\n==== 3. Shaker mix · 天花板被突破 ====')
show('元素', 'Shaker', ['家族', '份额', '溢价', '破顶销量占比', '破顶销量占比分位'])
for asin in ['B0GSQMHWBJ', 'B0GLX1F7C6']:
    r = x[(x.k == asin) | (x.p == asin)]
    for m, g in r.groupby('m'):
        row = g.iloc[0]; out = []
        for keys in (['尺寸段'], ['尺寸段', '装'], ['尺寸段', '装', '柜体材质']):
            base = x[(x.m < m) & (x.c > 0)]
            for kk in keys: base = base[base[kk] == row[kk]]
            out.append(f'{"×".join(keys)}：以前卖出的件数里 {base.c[base.price < row.price].sum() / base.c.sum():.0%} 比它便宜')
        print(f'  {asin} {m} {row.尺寸段} {row.装} {row.柜体材质} 元素={row.元素} 价格 {row.price:.0f} 家族 BSR {row.fbsr:.0f} 子体月销 {row.c:.0f}；', '；'.join(out))

print('\n==== 4. 42″（尺寸段）· 空档 ====')
show('尺寸段', '42″', ['家族', '份额', '单位ASIN贡献', '单位ASIN贡献分位', '新进入', '新进入进前100', '溢价'])
gb = kgap('尺寸段'); print(gb[gb.尺寸段 == '42″'].set_index('m')[['缺口', '分位']].round(3).T.to_string())

print('\n==== 5. 28″（精确尺寸）· 空档 ====')
show('精确尺寸', '28″', ['家族', '份额', '单位ASIN贡献', '单位ASIN贡献分位', '新进入', '新进入进前100', '溢价'])
ge = kgap('精确尺寸'); print(ge[ge.精确尺寸 == '28″'].set_index('m')[['缺口', '分位']].round(3).T.to_string())
print('9 月关键词缺口最大的精确尺寸：', ge[ge.m == MONTHS[-1]].nlargest(5, '缺口')[['精确尺寸', '缺口']].round(3).to_dict('records'))

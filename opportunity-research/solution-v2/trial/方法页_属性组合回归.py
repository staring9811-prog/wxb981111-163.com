"""属性和属性组合影不影响销量、和新品成功有没有关系。
A. 销量：1–9 月每月前 150 个家族的全部子体，结果 = log(1 + 子体月销量)。逐层比较：月份 → +尺寸段 → +全部单个属性 → +每一对搭配（单独加入）→ +全部两两搭配 → +三个属性的搭配。
   每层都在没参与计算的家族上算 R²（按家族分 5 折）；再用 1–6 月算、7–9 月验一次。搭配用"组合格子"表示，岭回归把样本少的格子往单属性的结果收（样本越少收得越多，不设硬门槛）。
B. 新品：2026-01 至 07 上架、上架后 3 个月内进过表的父体（粗算，不做换父体合并），结果 = 程度分 ln(50 ÷ 窗口内最好家族 BSR)。
   用 A 里学到的关系（训练时排除这些新品的家族）给每个新品算预测分，看和实际程度分的相关、预测前 20% 的新品成功率。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 方法页_属性组合回归.py"""
import os, sys, itertools, warnings, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import S, Q15, band
warnings.filterwarnings('ignore')
TAGS = {'D1产品形态': '形态', 'D3盆数': '盆数', 'D4台面形态': '台面形态', 'D5元素': '元素', 'D6柜体颜色': '颜色', 'D7柜体材质': '柜体材质', 'D8台面材质': '台面材质'}
q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
a = q.assign(m=q['目标月份'], p=q['核验父ASIN'], ps=q['父体月销量'].astype(float), c=q['子体月销量（父体全分给导出子体）'], price=pd.to_numeric(q['商品价格'], errors='coerce'),
             bsr=pd.to_numeric(q['小类BSR'], errors='coerce'), up=pd.to_datetime(q['上架日期'], errors='coerce'))
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
v = d.assign(m=d['月'].str[:4] + '-' + d['月'].str[4:], p=d['核验父ASIN'], ps=d['父体月销量预测'].astype(float), c=pd.to_numeric(d['最终SKU月销量估算'], errors='coerce'),
             price=pd.to_numeric(d['商品价格'], errors='coerce'), bsr=d['BSR'], up=pd.to_datetime(d['上架日期'], errors='coerce'))
cols = ['m', 'p', 'ps', 'c', 'price', 'bsr', 'up', 'D9宽(in)'] + list(TAGS)
allx = pd.concat([a[cols], v[cols]], ignore_index=True).rename(columns=TAGS)
allx['尺寸段'] = allx['D9宽(in)'].map(band).fillna('未知')
def tier(g):
    lo, hi = g.quantile([1 / 3, 2 / 3]); return pd.Series(np.where(g.isna(), '未知', np.where(g <= lo, '低价档', np.where(g <= hi, '中价档', '高价档'))), index=g.index)
allx['价档'] = allx.groupby(['m', '尺寸段'])['price'].transform(tier)  # 同月、同尺寸里的价格高低
ATTR = ['尺寸段', '形态', '盆数', '台面形态', '元素', '颜色', '柜体材质', '台面材质', '价档']
for c in ATTR:
    s = allx[c].astype(object).where(allx[c].notna(), '未知').astype(str).replace({'nan': '未知', '待核实': '未知', '': '未知'})
    vc = s.value_counts(); allx[c] = s.where(s.map(vc) >= 30, '其他')
top = allx.groupby(['m', 'p'])['ps'].first().groupby(level=0, group_keys=False).nlargest(150).reset_index()[['m', 'p']]
x = allx.merge(top, on=['m', 'p']).dropna(subset=['c']).reset_index(drop=True)
x['y'] = np.log1p(x['c'].clip(lower=0))
print('A. 子体×月 行数', len(x), ' 家族', x.p.nunique(), ' 月份', x.m.nunique())
print('各属性取值数', {c: x[c].nunique() for c in ATTR})

def feats(df, spec):
    f = pd.DataFrame({'月': df['m'].values})
    for g in spec:
        f['|'.join(g)] = df[list(g)].astype(str).agg('|'.join, axis=1).values if len(g) > 1 else df[g[0]].values
    return f
gkf = GroupKFold(n_splits=5)
ALPHAS = [1.0, 10.0, 100.0, 1000.0]
def score(spec):
    """在没参与计算的家族上算 R²：岭回归强度从 ALPHAS 里挑分折效果最好的，同一强度再做 1–6 月算、7–9 月验。返回（分折 R²，7–9 月 R²，强度）。"""
    f = feats(x, spec); enc = OneHotEncoder(handle_unknown='ignore')
    best = None
    for alpha in ALPHAS:
        r2 = []
        for tr, te in gkf.split(f, x.y, x.p):
            X = enc.fit_transform(f.iloc[tr]); m = Ridge(alpha=alpha).fit(X, x.y.iloc[tr])
            pr = m.predict(enc.transform(f.iloc[te])); yt = x.y.iloc[te].values
            r2.append(1 - ((yt - pr) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())
        if best is None or np.mean(r2) > best[0]: best = (np.mean(r2), alpha)
    tr = (x.m <= '2026-06').values; te = ~tr
    X = enc.fit_transform(f[tr]); m = Ridge(alpha=best[1]).fit(X, x.y[tr]); pr = m.predict(enc.transform(f[te])); yt = x.y[te].values
    return best[0], 1 - ((yt - pr) ** 2).sum() / ((yt - yt.mean()) ** 2).sum(), best[1]
main = [(c,) for c in ATTR]
pairs = list(itertools.combinations(ATTR, 2))
TRI = [('柜体材质', '价档', '台面材质'), ('台面材质', '价档', '盆数'), ('柜体材质', '价档', '盆数'), ('台面材质', '价档', '尺寸段'), ('柜体材质', '价档', '尺寸段'), ('元素', '价档', '尺寸段')]
res = [('只有月份', *score([])), ('+ 尺寸段', *score([('尺寸段',)]))]
b = score(main); res.append(('+ 全部单个属性', *b))
one = []
for pr_ in pairs:
    r = score(main + [pr_]); one.append((' × '.join(pr_), r[0] - b[0], r[1] - b[1]))
one = pd.DataFrame(one, columns=['搭配', '分折 R² 提升', '7–9 月 R² 提升']).sort_values('分折 R² 提升', ascending=False)
pp = score(main + pairs); res.append(('+ 全部两两搭配', *pp))
tt = score(main + pairs + TRI); res.append(('+ 6 个三属性搭配', *tt))
print(pd.DataFrame(res, columns=['模型', '分折 R²（没参与计算的家族）', '1–6 月算、7–9 月验 R²', '岭回归强度']).round(3).to_string(index=False))
print('\n每一对搭配单独加入（在"全部单个属性"之上）的提升：')
print(one.round(4).to_string(index=False))

# ---- B. 新品：A 里学到的关系能不能预测新品 3 个月程度分 ----
fam_up = allx.groupby('p')['up'].min()
newp = fam_up[(fam_up >= '2026-01-01') & (fam_up < '2026-08-01')].index
nx = allx[allx.p.isin(newp)].copy()
nx['lm'] = nx.p.map(fam_up).dt.to_period('M'); nx['age'] = (pd.PeriodIndex(nx.m, freq='M') - nx.lm).map(lambda z: z.n + 1)
nx = nx[nx.age.between(1, 3) & (nx.groupby(['m', 'p'])['ps'].transform('first') >= 60)]
out = nx.groupby('p').agg(best=('bsr', 'min'), lm=('lm', 'first'))
out = out.dropna(subset=['best']); out['程度分'] = np.log(50 / out.best); out['成功'] = out.best <= 50
print(f'\nB. 新品父体 {len(out)} 个（上架 2026-01 至 07，3 个月内进过表、有 BSR），其中 BSR ≤ 50 的 {int(out.成功.sum())} 个')
train = x[~x.p.isin(newp)]
for name, spec, alpha in [('只用单个属性', main, b[2]), ('单个属性 + 两两搭配', main + pairs, pp[2])]:
    enc = OneHotEncoder(handle_unknown='ignore'); m = Ridge(alpha=alpha).fit(enc.fit_transform(feats(train, spec)), train.y)
    pred = pd.Series(m.predict(enc.transform(feats(nx, spec))), index=nx.index).groupby(nx.p).mean()
    o = out.join(pred.rename('预测'), how='inner')
    rho, pv = spearmanr(o.预测, o.程度分)
    t20 = o[o.预测 >= o.预测.quantile(0.8)]
    print(f'  {name}：预测与实际程度分的等级相关 {rho:.2f}（p={pv:.3f}，n={len(o)}）；预测前 20% 的新品成功率 {t20.成功.mean():.0%}（{int(t20.成功.sum())}/{len(t20)}），全部 {o.成功.mean():.0%}')

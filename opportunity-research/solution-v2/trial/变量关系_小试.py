"""小试：变量、变量组合 与 新品结果 之间的关系（现有 2026-06 至 09 数据，不带任何人的经验）。
单位：父 ASIN 家族，最早子体上架在 2026-01 至 07。只用上架后第 1–6 个月、且落在 6–9 月观察窗内的月份。
结果口径三种并列：R_rel 跑赢同宽度新品中位（主）；R_bsr 任一月子体小类 BSR ≤ 50（样本只含头部商品，偏高）；R_100k 任一月家族销售额 ≥ $100k。
每张表都写 n；只做描述与留月检验，不下因果结论。"""
import json, re, itertools, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import roc_auc_score
warnings.filterwarnings('ignore')
D = '/home/user/wxb981111-163.com/opportunity-research/input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v2'
OUT = '/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/变量关系_小试结论.md'
a = json.load(open(D + '.analysis.json', encoding='utf-8'))
keep = {(r['month'], r['childASIN']) for r in a['rowManifest'] if r['includeInBathroomAnalysis']}
df = pd.read_excel(D + '.xlsx', sheet_name='SKU估算明细')
df['月'] = df['目标月份'].astype(str).str.replace('-', '').str[:6]
df = df[[(m, c) in keep for m, c in zip(df['月'], df['子ASIN'])]].copy()
df['销量'] = pd.to_numeric(df['最终SKU月销量估算'], errors='coerce'); df['价格'] = pd.to_numeric(df['商品价格'], errors='coerce')
df['BSR'] = pd.to_numeric(df['目标月校验小类BSR'], errors='coerce'); df['BSR有效'] = df['BSR校验状态'] == '未发现排序异常'
df['上架'] = pd.to_datetime(df['上架日期'], errors='coerce'); df['月期'] = pd.PeriodIndex(df['月'], freq='M')
df['销售额'] = df['销量'] * df['价格']; df['FBA'] = df['配送方式'].astype(str).str.contains('FBA|Amazon', case=False)
def wb(v):
    try: w = float(v)
    except: return None
    for lo, hi, lab in [(0, 26, '≤25″'), (26, 33, '26–32″'), (33, 40, '33–39″'), (40, 47, '40–46″'), (47, 55, '47–54″'), (55, 66, '55–65″'), (66, 200, '≥66″')]:
        if lo <= w < hi: return lab
df['宽度段'] = df['D9宽(in)'].map(wb)
ATTR = {'形态': 'D1产品形态', '安装': 'D2安装方式', '盆数': 'D3盆数', '台面形态': 'D4台面形态', '元素': 'D5元素', '颜色': 'D6柜体颜色', '柜体材质': 'D7柜体材质', '台面材质': 'D8台面材质'}
for k, v in ATTR.items():
    s = df[v].astype(str).str.split(r'[;；、,]').str[0].str.replace('（父体候选）', '').str.strip()
    s[s.str.contains('信息不足|待|未知|nan|冲突|^$', na=True)] = '未知'
    df[k] = s
# 家族表
fam = df.groupby('核验父ASIN')
F = pd.DataFrame({'上架': fam['上架'].min(), '子体数': fam['子ASIN'].nunique(), '品牌': fam['品牌'].first()})
F['上架月'] = F['上架'].dt.to_period('M')
new = F[(F['上架'] >= '2026-01-01') & (F['上架'] <= '2026-07-31')].copy()
df = df.merge(new[['上架月']], left_on='核验父ASIN', right_index=True, how='left')
df['月龄'] = (df['月期'] - df['上架月']).apply(lambda x: x.n + 1 if pd.notna(x) else np.nan)
obs = df[df['核验父ASIN'].isin(new.index) & df['月龄'].between(1, 6)]
g = obs.groupby('核验父ASIN')
new['观察月数'] = g['月'].nunique(); new = new[new['观察月数'] >= 1]
new['月均销量'] = g['销量'].sum() / new['观察月数']
fm = obs.groupby(['核验父ASIN', '月'])['销售额'].sum()
new['R_100k'] = fm.groupby(level=0).max().reindex(new.index) >= 100000
new['R_bsr'] = obs[obs['BSR有效'] & (obs['BSR'] <= 50)].groupby('核验父ASIN').size().reindex(new.index).fillna(0) > 0
def mode(s):
    s = s[s != '未知']; return s.mode().iloc[0] if len(s) else '未知'
for k in ATTR: new[k] = g[k].agg(mode)
new['宽度段'] = g['宽度段'].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else '未知')
new['颜色数'] = g['颜色'].nunique(); new['尺寸数'] = g['宽度段'].nunique()
w = obs.assign(w=obs['销量'].where(obs['价格'].notna(), 0))
new['加权价'] = w.groupby('核验父ASIN').apply(lambda x: np.average(x['价格'].fillna(0), weights=x['w']) if x['w'].sum() > 0 else np.nan)
band_med = df.groupby('宽度段')['价格'].median()
new['价格位置'] = new['加权价'] / new['宽度段'].map(band_med)
new['定价'] = pd.cut(new['价格位置'], [0, .85, 1.15, 99], labels=['低于同尺寸', '持平', '高于同尺寸']).astype(str)
new['变体'] = pd.cut(new['子体数'], [0, 1, 3, 6, 999], labels=['1', '2–3', '4–6', '7+']).astype(str)
new['配送'] = np.where(g['FBA'].mean().reindex(new.index) >= .5, 'FBA为主', '非FBA为主')
hot_old = df[~df['核验父ASIN'].isin(new.index) & df['BSR有效'] & (df['BSR'] <= 50)]['品牌'].unique()
new['品牌'] = np.where(new['品牌'].isin(hot_old), '已有热销款', '无')
new['上架月份'] = new['上架月'].astype(str)
# 主结果：跑赢同宽度新品中位
med = new.groupby('宽度段')['月均销量'].transform(lambda s: s.median() if len(s) >= 5 else new['月均销量'].median())
new['销量指数'] = new['月均销量'] / med; new['R_rel'] = new['销量指数'] >= 1
Y = 'R_rel'; base = new[Y].mean()
L = [f'# 变量关系小试结论（{len(new)} 个 2026-01 至 07 上架的新品家族，数据 2026-06 至 09）', '',
     f'三种结果口径的比例：跑赢同宽度新品中位 {base:.1%}；任一月子体 BSR ≤ 50 {new["R_bsr"].mean():.1%}（样本只含头部商品，偏高）；任一月家族销售额 ≥ $100k {new["R_100k"].mean():.1%}。',
     '以下关系都以"跑赢同宽度新品中位"为结果。销量为父体分摊估算，价格为快照。', '']
DIMS = ['宽度段'] + list(ATTR) + ['定价', '变体', '配送', '品牌', '上架月份']
# 1 单变量
L += ['## 1. 单变量：每个取值的跑赢比例（n ≥ 8）', '', '| 变量 | 取值 | n | 跑赢比例 | 相对整体 |', '| :--- | :--- | :--- | :--- | :--- |']
uni = []
for d in DIMS:
    t = new.groupby(d)[Y].agg(['size', 'mean']); t = t[t['size'] >= 8]
    for lv, r in t.iterrows():
        uni.append((d, lv, int(r['size']), r['mean'], r['mean'] / base))
for d, lv, n, m, lift in sorted(uni, key=lambda x: -abs(x[4] - 1)):
    L.append(f'| {d} | {lv} | {n} | {m:.0%} | {lift:.2f}× |')
# 2 两两组合
L += ['', '## 2. 两两组合：跑赢比例最高和最低的组合（n ≥ 8，且在 1–3 月与 4–7 月两段上架批次里方向一致才标"稳"）', '', '| 组合 | n | 跑赢比例 | 相对整体 | 稳定 |', '| :--- | :--- | :--- | :--- | :--- |']
half = new['上架月'].apply(lambda p: '早' if p.month <= 3 else '晚')
combos = []
for d1, d2 in itertools.combinations(DIMS, 2):
    for (v1, v2), grp in new.groupby([d1, d2]):
        if len(grp) < 8 or '未知' in (v1, v2): continue
        m = grp[Y].mean(); sub = grp.groupby(half.loc[grp.index])[Y].mean()
        stable = len(sub) == 2 and ((sub >= base).all() if m >= base else (sub <= base).all())
        combos.append((f'{d1}={v1} 且 {d2}={v2}', len(grp), m, m / base, '稳' if stable else ''))
combos.sort(key=lambda x: -x[3])
for c in combos[:10] + combos[-5:]:
    L.append(f'| {c[0]} | {c[1]} | {c[2]:.0%} | {c[3]:.2f}× | {c[4]} |')
# 3 决策树
X = pd.get_dummies(new[DIMS].astype(str)); y = new[Y].astype(int)
tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, random_state=0).fit(X, y)
L += ['', '## 3. 决策树自动找到的组合（深度 3，每叶至少 10 个家族）', '', '```', export_text(tree, feature_names=list(X.columns), show_weights=True), '```']
# 4 逻辑回归 + 留月检验
oof = pd.Series(np.nan, index=new.index)
for m_ in new['上架月份'].unique():
    tr, te = new['上架月份'] != m_, new['上架月份'] == m_
    lr = LogisticRegression(C=.5, max_iter=2000).fit(X[tr], y[tr]); oof[te] = lr.predict_proba(X[te])[:, 1]
auc = roc_auc_score(y, oof); top = new.loc[oof.sort_values(ascending=False).index[:max(1, len(new) // 5)], Y].mean()
lr = LogisticRegression(C=.5, max_iter=2000).fit(X, y)
coef = pd.Series(lr.coef_[0], index=X.columns).sort_values()
L += ['', '## 4. 逻辑回归（全部变量一起，留一个上架月份检验）', '',
      f'- 留月检验 AUC = {auc:.2f}（0.5 等于乱猜，0.7 以上才算有信号）；模型打分最高 20% 的家族跑赢比例 {top:.0%}，是整体 {base:.0%} 的 {top / base:.2f} 倍。',
      '- 关联最强的变量（系数为正=提高跑赢概率，负=降低；只列绝对值最大的 12 个）：', '', '| 变量取值 | 系数 |', '| :--- | :--- |']
for k_, v_ in pd.concat([coef.head(6), coef.tail(6)]).sort_values(ascending=False).items(): L.append(f'| {k_} | {v_:+.2f} |')
# 5 溢价示例：同宽度同元素下的台面材质
L += ['', '## 5. "同尺寸、同元素下的材质溢价"是什么：派生的市场统计量，示例', '',
      '在每个（宽度段 × 元素）语境里，算每种台面材质的销量加权价相对语境加权价的溢价（用全部商品，6–9 月），再看该语境里用该材质的新品家族跑赢比例。', '',
      '| 语境 | 台面材质 | 全部商品 ASIN 数 | 溢价 | 新品家族 n | 新品跑赢比例 |', '| :--- | :--- | :--- | :--- | :--- | :--- |']
allp = df[df['宽度段'].notna() & (df['元素'] != '未知') & (df['台面材质'] != '未知')].assign(w=lambda x: x['销量'].where(x['价格'].notna(), 0))
rows = []
for (band, el), ctx in allp.groupby(['宽度段', '元素']):
    if ctx['子ASIN'].nunique() < 30: continue
    cp = np.average(ctx['价格'].fillna(0), weights=ctx['w']) if ctx['w'].sum() > 0 else np.nan
    for mat, mg in ctx.groupby('台面材质'):
        if mg['子ASIN'].nunique() < 8: continue
        mp = np.average(mg['价格'].fillna(0), weights=mg['w']) if mg['w'].sum() > 0 else np.nan
        nf = new[(new['宽度段'] == band) & (new['元素'] == el) & (new['台面材质'] == mat)]
        rows.append((f'{band} × {el}', mat, mg['子ASIN'].nunique(), mp / cp - 1, len(nf), nf[Y].mean() if len(nf) >= 3 else np.nan))
for r in sorted(rows, key=lambda x: -abs(x[3]))[:12]:
    L.append(f'| {r[0]} | {r[1]} | {r[2]} | {r[3]:+.0%} | {r[4]} | {"—" if np.isnan(r[5]) else f"{r[5]:.0%}"} |')
L += ['', '## 6. 局限', '', '- 只有 4 个月、只有头部商品、没有未起量的新品，跑赢比例是"卖起来的里面谁更好"。', '- 1–3 月上架的只能看到第 4–6 个月，6–7 月上架的只能看到第 1–3 个月，月龄不齐。', '- 销量为估算、价格为快照；元素、台面材质未知占比高，"未知"档已排除出组合。', f'- 样本 {len(new)} 个家族，两两组合 n 多在 8–30，结论只能当线索。']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
# 供举例脚本复用的中间结果（临时目录，不入库）
import os
_S = os.environ.get('TRIAL_DUMP')
if _S:
    new.to_pickle(_S + '/new.pkl'); obs.to_pickle(_S + '/obs.pkl'); band_med.to_pickle(_S + '/band_med.pkl'); df.to_pickle(_S + '/df.pkl')
    pd.Series(lr.coef_[0], index=X.columns).to_pickle(_S + '/coef.pkl'); pd.Series({'intercept': lr.intercept_[0], 'pairs': len(combos)}).to_pickle(_S + '/meta.pkl')

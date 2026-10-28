"""两个补充小试（v11，160 个新品家族）：
A. 结果不用 0/1，用连续的 log(销量指数)，岭回归 + 留月检验，看有没有信号。
B. 按月龄累计成功率曲线（成功=子体任一月小类 BSR ≤ 50，样本只含头部商品，比例偏高，只示范方法）：
   每个家族只在自己被观察到的月龄区间里进入"风险集"，解决观察窗不齐的问题。"""
import os, numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from scipy.stats import spearmanr
S = os.environ['TRIAL_DUMP']
new = pd.read_pickle(S + '/new.pkl'); obs = pd.read_pickle(S + '/obs.pkl')
DIMS = ['宽度段', '形态', '安装', '盆数', '台面形态', '元素', '颜色', '柜体材质', '台面材质', '定价', '变体', '配送', '品牌']
M = new[DIMS].astype(str).copy()
for d in DIMS:
    vc = M[d].value_counts(); M[d] = M[d].replace(vc[vc < 8].index.tolist(), '其他')
X = pd.get_dummies(M, drop_first=True).astype(float); y = np.log(new['销量指数'].clip(lower=0.05))
L = ['# 连续结果与月龄曲线小试（v11）', '', '## A. 连续结果：log(销量指数)，岭回归（alpha=5），留一个上架月份检验', '']
oof = pd.Series(np.nan, index=new.index)
for m_ in new['上架月份'].unique():
    tr, te = new['上架月份'] != m_, new['上架月份'] == m_
    oof[te] = Ridge(alpha=5).fit(X[tr], y[tr]).predict(X[te])
rho, p = spearmanr(oof, y); r2 = 1 - ((y - oof) ** 2).sum() / ((y - y.mean()) ** 2).sum()
k20 = len(new) // 5; top_idx = oof.sort_values(ascending=False).index[:k20]
L += [f'- 留出预测与实际的等级相关 Spearman ρ = {rho:.2f}（p = {p:.2f}；0 等于无关）；留出 R² = {r2:.2f}（负数表示比"猜平均值"还差）。',
      f'- 预测最高的 {k20} 个家族，实际销量指数中位 {new.loc[top_idx, "销量指数"].median():.2f}，全体中位 {new["销量指数"].median():.2f}。',
      '- 结论：换成连续结果后仍无可推广的信号。']
# B. 月龄累计成功率（左截断 + 右删失）
obs = obs.copy(); obs['hit'] = obs['BSR有效'] & (obs['BSR'] <= 50)
L += ['', '## B. 按月龄累计成功率曲线（成功 = 任一月子体小类 BSR ≤ 50；头部样本，仅示范方法）', '',
      '算法：对月龄 m = 1…6，风险集 = 观察窗覆盖 m 且在 m 之前（窗内）未成功的家族；当月成功率 h(m) = 当月首次成功数 ÷ 风险集；累计成功率 S(m) = 1 − Π(1 − h)。每个家族只在自己被看到的月龄进入风险集，上架早晚不再造成假象。', '']
def km(sub):
    rows = []; done = set(); surv = 1.0
    for m in range(1, 7):
        at = sub[sub['月龄'] == m]; fams = set(at['核验父ASIN']) - done
        hits = set(at[at['hit']]['核验父ASIN']) - done
        h = len(hits) / len(fams) if fams else np.nan
        if fams: surv *= (1 - h)
        rows.append((m, len(fams), len(hits), h, 1 - surv)); done |= hits
    return pd.DataFrame(rows, columns=['月龄', '风险集家族数', '当月首次成功', '当月成功率', '累计成功率'])
L += ['全部新品家族：', '', km(obs).round(3).to_markdown(index=False)]
for band, grp in new.groupby('宽度段'):
    if len(grp) < 20: continue
    t = km(obs[obs['核验父ASIN'].isin(grp.index)])
    L += ['', f'宽度段 {band}（{len(grp)} 个家族）：第 6 个月累计成功率 {t["累计成功率"].iloc[-1]:.0%}', '', t.round(3).to_markdown(index=False)]
L += ['', '读法：第 6 个月的累计成功率就是"进入这个格子的新品 6 个月内成功的比例"，各格子可直接比较；风险集家族数就是样本量，少于 20 不下结论。']
open('连续结果与月龄曲线_小试结论.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

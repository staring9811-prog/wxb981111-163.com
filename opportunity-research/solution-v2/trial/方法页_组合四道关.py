"""方法页第 4 题：6–9 月 44 个走完观察期的新品，枚举 1–5 元属性组合，依次过四道关（频次够、比整体强、比子组合强、过碰巧线），看"被成功命中"的组合最后剩几条；打乱成败 1000 次看碰巧水平。
用法：TRIAL_DUMP=<放 df.pkl 与 success_window3_replace_all_parent.json 的目录> python3 -I 方法页_组合四道关.py"""
import os, json, itertools, numpy as np, pandas as pd
from scipy.stats import hypergeom
S = os.environ['TRIAL_DUMP']
j = json.load(open(S + '/success_window3_replace_all_parent.json', encoding='utf-8'))
fam = [f for f in j['families'] if f['状态'] in ('成功', '未成功')]
p2u = {p: f['单位'] for f in fam for p in f['父ASIN']}
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN']); d = d[d['核验父ASIN'].isin(p2u)]; d['单位'] = d['核验父ASIN'].map(p2u)
ATTR = ['宽度段', '形态', '安装', '盆数', '台面形态', '元素', '颜色', '柜体材质', '台面材质']
def mode(s):
    s = s.dropna().astype(str); s = s[~s.isin(['未知', 'nan', '', '待核实'])]
    return s.mode().iloc[0] if len(s) else None
U = d.groupby('单位').agg({**{c: mode for c in ATTR}, '价格': 'median'})
lo, hi = U['价格'].quantile([1 / 3, 2 / 3]); U['价档'] = np.where(U['价格'] <= lo, '低价档', np.where(U['价格'] <= hi, '中价档', '高价档'))
ATTR += ['价档']
ok = {f['单位']: f['状态'] == '成功' for f in fam}
U = U.loc[[f['单位'] for f in fam]]; y = np.array([ok[u] for u in U.index], dtype=float)
items = [sorted((c, U.at[u, c]) for c in ATTR if pd.notna(U.at[u, c])) for u in U.index]
print('单位', len(U), '成功', int(y.sum()), '每个单位已知属性数中位', int(np.median([len(i) for i in items])))
combos = {}
for ui, it in enumerate(items):
    for r in range(1, 6):
        for c in itertools.combinations(it, r): combos.setdefault(c, []).append(ui)
keys = list(combos); C = len(keys); idx = {c: i for i, c in enumerate(keys)}
M = np.zeros((C, len(U)), dtype=np.float32)
for i, c in enumerate(keys): M[i, combos[c]] = 1
n = M.sum(1); size = np.array([len(c) for c in keys])
sub = np.full((C, 5), -1)
for i, c in enumerate(keys):
    if len(c) > 1:
        for t, s in enumerate(itertools.combinations(c, len(c) - 1)): sub[i, t] = idx[s]
base = y.mean()
def stages(yy):
    k = M @ yy; rate = k / n; b = yy.mean()
    s0 = k >= 1
    s1 = s0 & (n >= 5) & (k >= 2)
    s2 = s1 & (rate > b)
    rs = np.where(sub >= 0, rate[np.clip(sub, 0, None)], -1).max(1); rs = np.where(size == 1, b, rs)
    s3 = s2 & (rate > rs)
    return k, rate, s0, s1, s2, s3
k, rate, s0, s1, s2, s3 = stages(y)
print('枚举出的 1–5 元组合', C)
print('S0 至少被 1 个成功产品命中', int(s0.sum()), ' 其中只被 1 个命中', int(((k == 1)).sum()))
print('S1 至少 5 个新品带它、其中至少 2 个成功', int(s1.sum()))
print('S2 成功率高于整体', int(s2.sum()))
print('S3 比它的每个子组合都高（不是沾单个属性的光）', int(s3.sum()))
rng = np.random.default_rng(20261028); R = 1000
cnt = np.array([[x.sum() for x in stages(rng.permutation(y))[2:]] for _ in range(R)])
for name, real, col in [('S0', s0.sum(), 0), ('S1', s1.sum(), 1), ('S2', s2.sum(), 2), ('S3', s3.sum(), 3)]:
    print(f'{name} 真实 {int(real)}  打乱后中位 {int(np.median(cnt[:, col]))}  95% 分位 {int(np.quantile(cnt[:, col], 0.95))}  打乱后不少于真实的比例 {(cnt[:, col] >= real).mean():.2f}')
# 每条通过 S3 的组合：超几何检验 + 多重比较校正（BH），看有没有单条站得住
N, K = len(y), int(y.sum())
pv = np.array([hypergeom.sf(int(k[i]) - 1, N, K, int(n[i])) for i in range(C)])
tested = np.where(s1)[0]; p = pv[tested]; order = np.argsort(p); m = len(p)
bh = np.minimum.accumulate((p[order] * m / (np.arange(m) + 1))[::-1])[::-1]
q = np.empty(m); q[order] = np.minimum(bh, 1)
print('S1 里做检验的组合', m, ' 单条 p<0.05 的', int((p < 0.05).sum()), ' 校正后 q<0.1 的', int((q < 0.1).sum()))
top = sorted([i for i in np.where(s3)[0]], key=lambda i: pv[i])[:8]
for i in top: print('  ', ' + '.join(f'{a}={v}' for a, v in keys[i]), f'n={int(n[i])} k={int(k[i])} 成功率={rate[i]:.0%} p={pv[i]:.3f}')

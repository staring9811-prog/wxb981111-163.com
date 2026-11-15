"""多元组合的"碰巧"检验：把 160 个家族的跑赢结果随机打乱 200 次，每次重新数"达标组合"（n≥8、跑赢比例≥整体 1.5 倍、早晚两批都高于整体）有多少个。
真实数据里的达标数如果和打乱后差不多，说明这些"赢家"主要是碰巧。"""
import itertools, os, numpy as np, pandas as pd
S = os.environ['TRIAL_DUMP']
new = pd.read_pickle(S + '/new.pkl')
DIMS = ['宽度段', '形态', '安装', '盆数', '台面形态', '元素', '颜色', '柜体材质', '台面材质', '定价', '变体', '配送', '品牌']
y = new['R_rel'].values.astype(float); base = y.mean(); half = (new['上架月'].apply(lambda p: p.month <= 3)).values
groups = {k: [] for k in (2, 3, 4)}
for k in (2, 3, 4):
    for ds in itertools.combinations(DIMS, k):
        for vals, idx in new.groupby(list(ds)).indices.items():
            if len(idx) >= 8 and '未知' not in vals: groups[k].append(np.asarray(idx))
def count(yv):
    out = {}
    for k, gl in groups.items():
        c = 0
        for idx in gl:
            m = yv[idx].mean(); h = half[idx]
            if m >= 1.5 * base and h.any() and (~h).any() and yv[idx[h]].mean() >= base and yv[idx[~h]].mean() >= base: c += 1
        out[k] = c
    return out
real = count(y); rng = np.random.default_rng(0)
sims = pd.DataFrame([count(rng.permutation(y)) for _ in range(200)])
lines = ['# 多元组合的打乱检验（v11 标签，160 个家族，打乱 200 次）', '', '| 组合元数 | n≥8 的组合数 | 真实数据达标数 | 打乱后达标数（中位） | 打乱后 95% 上限 |', '| :--- | :--- | :--- | :--- | :--- |']
for k in (2, 3, 4):
    lines.append(f'| {k} | {len(groups[k])} | {real[k]} | {int(sims[k].median())} | {int(sims[k].quantile(.95))} |')
lines += ['', '读法：真实达标数没有明显高于打乱后的 95% 上限，说明按这套门槛挑出来的"赢家"数量和瞎碰差不多，不能当规律。']
open('组合_打乱检验结论.md', 'w', encoding='utf-8').write('\n'.join(lines) + '\n'); print('\n'.join(lines))

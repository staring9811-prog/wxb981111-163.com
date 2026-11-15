"""留出检验（做法见 solution-v2/留出检验_预登记.md）：用冻结的第三版模型和三档名单，给 2026-04 起上架、6 个月观察期已走完的新家族打分并评估。
单位、分母、成功、特征都沿用 回归_新家族.py（跑到第 5 节，WITH_HOLD=1 时多留"留出"段）；模型参数只从冻结文件读，不重新拟合。
用法：python3 -I 留出检验.py；FROZEN（冻结文件，默认 solution-v2/留出检验_冻结_第三版.json）、REPORT_MD（默认 solution-v2/留出检验_结果.md）可改。"""
import os, json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
FROZEN = os.environ.get('FROZEN', os.path.join(ROOT, 'solution-v2/留出检验_冻结_第三版.json'))
REPORT = os.environ.get('REPORT_MD', os.path.join(ROOT, 'solution-v2/留出检验_结果.md'))
os.environ['WITH_HOLD'] = '1'
P = os.path.join(HERE, '回归_新家族.py'); src = open(P, encoding='utf-8').read(); ns = {'__file__': P, '__name__': 'hold'}
exec(compile(src[:src.index('# ---------- 6. 两把尺')], P, 'exec'), ns)
U, feat, tok_main, tok_combo, has, ref_group, ms, DIMS = (ns[k] for k in ('U', 'feat', 'tok_main', 'tok_combo', 'has', 'ref_group', 'ms', 'DIMS'))
FZ = json.load(open(FROZEN, encoding='utf-8'))
H = U[U['段'] == '留出'].copy()
y = H['y'].values

def score(m):
    sp = m['spec']; toks = {u: set(tok_main(u) + ([f'格={U.at[u, "格"]}'] if sp.get('cells') else []) + tok_combo(u, [tuple(c) for c in sp.get('combos', [])])) for u in H.index}
    X = np.zeros((len(H), len(m['columns'])))
    for j, c in enumerate(m['columns']):
        if c in m['cont']:
            v = H[c].astype(float)
            if c.startswith('信号'): v = np.log(v.clip(0.05, 20))
            elif c in ('_品牌力', '_变体', '_颜色数'): v = np.log1p(v)
            p = m['cont'][c]; X[:, j] = ((v.fillna(p['median']) - p['mean']) / p['sd']).values
        elif c.startswith('缺·'):
            d = c[2:]; X[:, j] = H[[s for s in m['cont'] if s.startswith(f'信号·{d}')]].isna().all(axis=1).astype(float).values
        else: X[:, j] = [1.0 if c in toks[u] else 0.0 for u in H.index]
    return 1 / (1 + np.exp(-(X @ np.array(m['coef']) + m['intercept'])))
def lift(y, s, q=0.2):
    rng = np.random.default_rng(0); o = np.lexsort((rng.random(len(s)), -np.asarray(s))); k = max(1, int(round(q * len(s))))
    return float(np.asarray(y)[o[:k]].mean() / np.mean(y))
def metrics(s):
    if y.min() == y.max(): return None
    rng = np.random.default_rng(1); A_, L_ = [], []
    for _ in range(1000):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max(): continue
        A_.append(roc_auc_score(y[i], s[i])); L_.append(lift(y[i], s[i]))
    return dict(auc=roc_auc_score(y, s), lift=lift(y, s), auc_ci=np.percentile(A_, [2.5, 97.5]), lift_ci=np.percentile(L_, [2.5, 97.5]))
COL = {'价格位置（比同格中位价贵多少）': '_价位', '品牌力（同品牌其他家族数）': '_品牌力', '变体数': '_变体', '颜色数': '_颜色数'}
def ind_col(name): return COL.get(name) or ('信号·' + name.replace('上架前 ', '') if name.startswith('上架前 ') else None)

# 发现：留出批次自己的比较框（主尺寸段 × 价格档 × 上架批次）里，品牌一票同格差
kn = ~H['比较框'].str.contains('未知')
BR = pd.Series(np.where(H['品牌键'].ne(''), H['品牌键'], H.index), index=H.index)
def gap(inm, refm):
    d = H[kn].assign(有=inm[kn.values], 对=refm[kn.values], 品牌=BR[kn]); num = den = 0; nb = [0, 0]
    for _, g in d.groupby('比较框'):
        v1 = g[g['有']].groupby('品牌')['y'].mean(); v0 = g[g['对']].groupby('品牌')['y'].mean()
        if len(v1) and len(v0): w = len(v1) * len(v0) / (len(v1) + len(v0)); num += w * (v1.mean() - v0.mean()); den += w; nb[0] += len(v1); nb[1] += len(v0)
    return (num / den if den else np.nan), nb
rows = []
for f in FZ['发现']:
    c = f['特征']
    if f['连续']:
        v = H[c].astype(float); q1, q2 = f['三分点']; inm, refm = (v >= q2).values, (v <= q1).values
    else:
        inm = np.array([has(u, c) for u in H.index]); refm = np.array([ref_group(u, c) for u in H.index])
    g, nb = gap(inm, refm)
    rows.append(dict(特征=c, 档=f['档'], 冻结=(f['同格差学习'], f['同格差检验']), 留出=g, 品牌=nb, 有它家族=int(inm.sum()), 对照家族=int(refm.sum())))

batch = sorted(H['L'].unique()); bname = '、'.join(ms(b) for b in batch) if len(batch) else '（无）'
L = [f'## {bname} 上架批（数据到 {ms(ns["LAST"])}；{pd.Timestamp.now(tz="UTC"):%Y-%m-%d %H:%M} UTC 算）', '',
     f'- 冻结文件：{os.path.relpath(FROZEN, ROOT)}（{FZ["版本"]}，{FZ["生成"]} 生成，用 {FZ["拟合家族"]} 个新家族拟合）。',
     f'- 留出人群：{len(H)} 个新家族（口径同回归：观察期 6 个月走完、进分母），起来 {int(y.sum())} 个（{y.mean():.0%}）。', '',
     '| 模型 / 指标 | AUC（95% 区间） | 前 20% 是平均的几倍（95% 区间） |', '| :--- | :--- | :--- |']
for name, m in FZ['模型'].items():
    r = metrics(score(m)); tag = '（主）' if name.startswith('完整') else '（次：看过检验段才挑的）'
    L.append(f'| {name}{tag} | ' + ('—' if r is None else f"{r['auc']:.2f}（{r['auc_ci'][0]:.2f}–{r['auc_ci'][1]:.2f}） | {r['lift']:.2f} 倍（{r['lift_ci'][0]:.2f}–{r['lift_ci'][1]:.2f}）") + ' |')
for name, d in FZ['单指标方向'].items():
    c = ind_col(name)
    if c is None or c not in H or H[c].notna().sum() < 5 or y.min() == y.max(): continue
    s = H[c].astype(float).fillna(H[c].astype(float).median()).values * (1 if d == '越高越好' else -1)
    L.append(f'| 单指标：{name}（{d}） | {roc_auc_score(y, s):.2f} | {lift(y, s):.2f} 倍 |')
L += ['', '- 标准：前 20% 起来的比例 ≥ 平均的 2 倍，并且好过每个单指标。留出人群小，区间很宽，一批的结果只记下来，不单独下结论；以后每批照此滚动累计。', '',
      '发现（冻结的三档名单，在留出批次的比较框里按品牌一票算同格差；人群小，只看方向和大小）：', '',
      '| 档 | 发现 | 冻结时同格差 前段 / 后段 | 留出批次同格差 | 方向一致 | 格内能对上的品牌 有 / 对照 | 有它 / 对照家族 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
for r in rows:
    s0 = np.sign(r['冻结'][0]); ok = '—' if np.isnan(r['留出']) else ('是' if np.sign(r['留出']) == s0 else '否')
    L.append(f"| {r['档']} | {ns['fname'](r['特征']) if 'fname' in ns else r['特征']} | {r['冻结'][0] * 100:+.0f} / {r['冻结'][1] * 100:+.0f} | "
             + ('—（格里对不上）' if np.isnan(r['留出']) else f"{r['留出'] * 100:+.0f}") + f" | {ok} | {r['品牌'][0]} / {r['品牌'][1]} | {r['有它家族']} / {r['对照家族']} |")
ev = [r for r in rows if not np.isnan(r['留出'])]
L += ['', f"能算的 {len(ev)} 条里，方向和冻结时一致的 {sum(np.sign(r['留出']) == np.sign(r['冻结'][0]) for r in ev)} 条。", '']
head = ['# 留出检验结果', '', '> 由 `trial/留出检验.py` 生成。做法见 留出检验_预登记.md：模型和名单在看留出结果之前冻结并提交（solution-v2/留出检验_冻结_第三版.json），这里只打分、不改口径。每批结果追加在下面，不挑批次。', '']
old = open(REPORT, encoding='utf-8').read() if os.path.exists(REPORT) else '\n'.join(head) + '\n'
sec = f'## {bname} 上架批'   # 同一批重算时替换这一节
if sec in old: old = old[:old.index(sec)].rstrip() + '\n'
open(REPORT, 'w', encoding='utf-8').write(old + '\n' + '\n'.join(L) + '\n')
print('\n'.join(L))

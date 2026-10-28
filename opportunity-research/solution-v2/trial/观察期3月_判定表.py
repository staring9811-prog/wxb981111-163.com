"""观察期 = 3 个月的成功率判定表（v11）。
成功：观察期内任一月，任一子体小类 BSR ≤ 50（校验正常的行），或家族月销售额 ≥ $100,000。
新品家族：最早子体上架在 2026-01 至 09。按月龄累计成功率（每个家族只在被看到的月龄进入风险集）。"""
import os, json, numpy as np, pandas as pd
S = os.environ['TRIAL_DUMP']; N = int(os.environ.get('WINDOW', 3))
df = pd.read_pickle(S + '/df.pkl')
fam = df.groupby('核验父ASIN')['上架'].min().rename('上架F')
df = df.drop(columns=[c for c in ['上架月', '月龄'] if c in df]).join(fam, on='核验父ASIN')
df['上架月'] = df['上架F'].dt.to_period('M')
df = df[(df['上架F'] >= '2026-01-01') & (df['上架F'] <= '2026-09-30')]
df['月龄'] = (df['月期'] - df['上架月']).apply(lambda x: x.n + 1)
df = df[df['月龄'].between(1, N)]
fm = df.groupby(['核验父ASIN', '月龄']).agg(rev=('销售额', 'sum'), bsr=('BSR', lambda s: s[df.loc[s.index, 'BSR有效']].min()))
fm['hit'] = (fm['rev'] >= 100000) | (fm['bsr'] <= 50)
fm = fm.reset_index()
def mode(s):
    s = s[s != '未知']; return s.mode().iloc[0] if len(s) else '未知'
attr = df.groupby('核验父ASIN').agg(宽度段=('宽度段', lambda s: s.dropna().mode().iloc[0] if s.notna().any() else '未知'), 形态=('形态', mode), 台面材质=('台面材质', mode), 上架月=('上架月', 'first'), 品牌=('品牌', 'first'))
fm = fm.join(attr, on='核验父ASIN')
def km(sub):
    done = set(); surv = 1.0; rows = []
    for m in range(1, N + 1):
        at = sub[sub['月龄'] == m]; risk = set(at['核验父ASIN']) - done; hits = set(at[at['hit']]['核验父ASIN']) - done
        if risk: surv *= 1 - len(hits) / len(risk)
        rows.append(dict(月龄=m, 风险集=len(risk), 首次成功=len(hits), 累计=1 - surv)); done |= hits
    return rows
def cell(sub):
    r = km(sub); n = sub['核验父ASIN'].nunique(); k = sub[sub['hit']]['核验父ASIN'].nunique()
    eff = min(x['风险集'] for x in r if x['风险集'] > 0) if any(x['风险集'] for x in r) else 0
    p = r[-1]['累计']; z = 1.645
    lo = max(0, p - z * np.sqrt(p * (1 - p) / max(eff, 1))); hi = min(1, p + z * np.sqrt(p * (1 - p) / max(eff, 1)))
    return dict(n=n, k=k, p=p, lo=lo, hi=hi, eff=eff, curve=r)
out = {'window': N, 'total': cell(fm), 'by_width': {}, 'grid': {}, 'launch': fm.groupby('上架月')['核验父ASIN'].nunique().astype(int).rename(lambda p: str(p)).to_dict()}
for w, g in fm.groupby('宽度段'): out['by_width'][w] = cell(g)
for (w, f), g in fm.groupby(['宽度段', '形态']): out['grid'][f'{w}|{f}'] = cell(g)
# 下钻：选中格子（默认 26–32″ · 落地式），台面拆分与锦囊对比都在同一语境内
CW, CF = os.environ.get('CELL', '26–32″|落地式').split('|')
c = fm[(fm['宽度段'] == CW) & (fm['形态'] == CF)]
out['cell'] = f'{CW}|{CF}'
out['split'] = {t: cell(g) for t, g in c.groupby('台面材质')}
# 锦囊示例：动作 = 台面用陶瓷；默认 A0 = 同语境内其余已标台面；未知单列，不并入任何一边
A = c[c['台面材质'] == '陶瓷']; A0 = c[~c['台面材质'].isin(['陶瓷', '未知'])]
out['kit'] = {'A': cell(A), 'A0': cell(A0), 'unknown': int(c[c['台面材质'] == '未知']['核验父ASIN'].nunique())}
fl = c.groupby('核验父ASIN').agg(品牌=('品牌', 'first'), 上架月=('上架月', lambda s: str(s.iloc[0])), 台面=('台面材质', 'first'),
    月龄=('月龄', lambda s: '、'.join(str(int(x)) for x in sorted(s))), 最好BSR=('bsr', 'min'), 最高月销售额=('rev', 'max'), 成功=('hit', 'any')).reset_index()
fl = fl.sort_values(['成功', '最好BSR'], ascending=[False, True], na_position='last')
out['families'] = fl.assign(最好BSR=fl['最好BSR'].astype(object).where(fl['最好BSR'].notna(), None)).to_dict('records')
# 第 1 个月可见性：只算理论上能在数据里看到第 1 个月的家族（上架月在数据首月及以后）
first = df['月期'].min(); can1 = fm[fm['上架月'] >= first]['核验父ASIN'].nunique()
out['age1'] = {'可见': int(fm[fm['月龄'] == 1]['核验父ASIN'].nunique()), '理论可见': int(can1), '数据首月': str(first)}
json.dump(out, open(S + f'/window{N}.json', 'w', encoding='utf-8'), ensure_ascii=False, default=float, indent=1)
print('总体', {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out['total'].items() if k != 'curve'}); print('曲线', out['total']['curve'])
print('上架月家族数', out['launch'])
for w, v in out['by_width'].items(): print(w, v['n'], v['k'], round(v['p'], 2), 'eff', v['eff'], [x['风险集'] for x in v['curve']])
for k_, v in out['grid'].items():
    if v['n'] >= 8: print(k_, v['n'], round(v['p'], 2), 'eff', v['eff'])
print(out['cell'], 'split', {t: (v['n'], v['k'], round(v['p'], 2), v['eff']) for t, v in out['split'].items()})
print('锦囊', {k: (v if isinstance(v, int) else (v['n'], v['k'], round(v['p'], 3), v['eff'])) for k, v in out['kit'].items()})
print('第1月', out['age1']); print('家族', len(out['families']), sum(f['成功'] for f in out['families']))

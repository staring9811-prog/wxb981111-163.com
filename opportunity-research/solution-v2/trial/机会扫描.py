"""机会扫描：每个"同尺寸段 × 同拆装 × 同形态"框里，台面材质 / 元素 / 主色 / 柜体材质 的每个取值，近 6 个月对前 6 个月。
分四类：增长型、评分缺口型（老板假设：评分低于同框、单款销量不低于同框）、价格缺口型（只有高价款且有成交）、坑。
输出 solution-v2/开发建议/机会扫描_<日期>.md 和 全量 CSV。证据等级：增长型的信号（份额斜率、新品占比）经回测显著；评分缺口、价格缺口是历史观察。"""
import os, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('FEAT = {T')], P, 'exec'), G); A, U, ms, END, ROOT, UNK = (G[k] for k in ('A', 'U', 'ms', 'END', 'ROOT', 'UNK'))
R6, P6 = list(range(END - 5, END + 1)), list(range(END - 11, END - 5))
B = A[A['尺寸段'].notna() & A['装'].notna() & A['形态'].isin(['落地式', '悬浮式'])].copy(); B['框'] = B['尺寸段'].astype(str) + ' · ' + B['装'].astype(str) + ' · ' + B['形态'].astype(str)
B['r'] = pd.to_numeric(B['评分'], errors='coerce').where(lambda x: x.between(1, 5))
B['价比'] = (B['价格'] / B.groupby(['m', '框'])['价格'].transform('median')).where(B['价格'] > 0); B['新'] = B['月龄'] <= 6
def wmed(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float); k = ~np.isnan(x) & (w > 0); x, w = x[k], w[k]
    if not len(x): return np.nan
    o = np.argsort(x); c = np.cumsum(w[o]); return x[o][np.searchsorted(c, c[-1] / 2)]
ATT = {'台面材质': 'D8台面材质', '元素': '元素一', '主色': '主色', '柜体材质': '柜体材质'}
kf = A.drop_duplicates('单位').set_index('单位')['家族键']; Ue = U[U['L'] + 5 <= END].copy(); Ue['家族键'] = kf.reindex(Ue.index).values
famfr = B.groupby('家族键')['框'].agg(lambda x: x.value_counts().index[0]); Ue['框'] = famfr.reindex(Ue['家族键']).values
rows = []
for att, col in ATT.items():
    d = B.assign(值=B[col])
    if att == '元素': d = d.explode('值')
    d = d[d['值'].notna() & ~d['值'].map(UNK) & ~d['值'].isin(['信息不足', '不适用（不含台面）'])]
    famv = d.groupby('家族键')['值'].agg(set)
    for fr, df in d.groupby('框'):
        r6, p6 = df[df['m'].isin(R6)], df[df['m'].isin(P6)]
        if r6['c'].sum() / 6 < 200: continue
        F = dict(月销=r6['c'].sum() / 6, 家族=r6['家族键'].nunique(), 评分=(r6['r'] * r6['c']).sum() / r6.loc[r6['r'].notna(), 'c'].sum(), 新品=r6.loc[r6['新'], 'c'].sum() / r6['c'].sum(), 月销前=p6['c'].sum() / 6)
        F['单款'] = F['月销'] / max(F['家族'], 1)
        uf = Ue[Ue['框'] == fr]
        for v, dv in r6.groupby('值'):
            pv = p6[p6['值'] == v]; s = dv['c'].sum() / 6
            if s < 10: continue
            rr = dv.dropna(subset=['r']); fam = dv['家族键'].nunique()
            ufv = uf.loc[np.array([v in famv.get(k, set()) for k in uf['家族键']], dtype=bool)]
            rows.append(dict(属性=att, 框=fr, 取值=v, 月销=s, 份额=s / F['月销'], 份额前=(pv['c'].sum() / 6) / max(F['月销前'], 1e-9), 家族=fam, 单款=s / fam, 框单款=F['单款'],
                             评分=(rr['r'] * rr['c']).sum() / rr['c'].sum() if rr['c'].sum() else np.nan, 框评分=F['评分'], 溢价=wmed(dv['价比'], dv['c']), 中位价=wmed(dv['价格'], dv['c']),
                             新品=dv.loc[dv['新'], 'c'].sum() / dv['c'].sum(), 框新品=F['新品'], 框月销=F['月销'],
                             新家族=len(ufv), 新做到=int(ufv['y'].sum()), 框新家族=len(uf), 框新做到=int(uf['y'].sum())))
X = pd.DataFrame(rows); X['份额变化'] = np.log((X['份额'] + 0.002) / (X['份额前'] + 0.002)); X['新品差'] = X['新品'] - X['框新品']
X['评分差'] = X['评分'] - X['框评分']; X['单款比'] = X['单款'] / X['框单款']
X['增长型'] = (X['份额变化'] >= 0.3) & (X['月销'] >= 100) & (X['新品差'] > 0)
X['评分缺口型'] = (X['评分差'] <= -0.15) & (X['单款比'] >= 1.0) & (X['月销'] >= 50)
X['价格缺口型'] = (X['溢价'] >= 1.3) & (X['月销'] >= 20)
X['坑'] = (X['份额变化'] <= -0.3) & (X['月销'] >= 100)
out = os.path.join(ROOT, 'solution-v2/开发建议'); X.to_csv(os.path.join(out, '机会扫描_202610_全量.csv'), index=False, encoding='utf-8-sig')
pct = lambda x: f'{x:.1%}'
L = ['# 机会扫描：站在 2026-10，每个"同尺寸段 × 同拆装 × 同形态"框里的机会点', '',
     f'> 由 `trial/机会扫描.py` 生成。近期 = {ms(R6[0])} 至 {ms(R6[-1])}，前期 = {ms(P6[0])} 至 {ms(P6[-1])}。框 = 尺寸段 × 拆装 × 形态（落地式 / 悬浮式；柱状盆、转角式量太小不扫）。只扫近期月销 ≥ 200 件的框；单元 = 框 × 属性取值（台面材质、元素、主色、柜体材质），近期月销 ≥ 10 件的全部进 CSV（`机会扫描_202610_全量.csv`，{len(X)} 个）。',
     '> 2026-06 至 09 来自 v11 表，家族键月间一致性较低，份额变化要打折看。', '',
     '| 类型 | 规则 | 证据等级 |', '| :--- | :--- | :--- |',
     '| 增长型 | 份额 ln(近期 ÷ 前期) ≥ 0.3、月销 ≥ 100、新品占比高于同框 | 份额走势和新品占比经回测显著（第九版、全链路验证 §2） |',
     '| 评分缺口型 | 评分比同框低 ≥ 0.15、单款月销 ≥ 同框单款、月销 ≥ 50 | 老板假设；历史观察（全链路验证 §1：低分不低销的形态需求会延续，p = 0.005；"做好就起量"未验证） |',
     '| 价格缺口型 | 溢价 ≥ 1.3 倍、月销 ≥ 20 | 历史观察（岗石 30″ 拆装案例）；溢价对份额的作用不显著 |',
     '| 坑 | 份额 ln 变化 ≤ −0.3、月销 ≥ 100 | 份额走势经回测显著 |', '']
def tab(df, cols):
    h = '| 框 | 属性：取值 | 月销 | 份额 前 → 近 | 家族 | 单款 ÷ 同框 | 评分（同框） | 溢价 / 中位价 | 新品占比（同框） | 新家族做到（同框） |'
    out = [h, '| :--- | :--- | ---: | :--- | ---: | ---: | :--- | :--- | :--- | :--- |']
    for r in df.itertuples():
        out.append(f"| {r.框} | {r.属性}：{r.取值} | {r.月销:,.0f} | {pct(r.份额前)} → {pct(r.份额)} | {r.家族} | {r.单款比:.2f} | {r.评分:.2f}（{r.框评分:.2f}） | {r.溢价:.2f} / ${r.中位价:,.0f} | {r.新品:.0%}（{r.框新品:.0%}） | "
                   f"{r.新做到}/{r.新家族}（{r.框新做到}/{r.框新家族}） |".replace('nan', '—'))
    return out
for typ, key in (('增长型', lambda d: d['月销'] * d['份额变化']), ('评分缺口型', lambda d: d['月销'] * (-d['评分差'])), ('价格缺口型', lambda d: d['月销']), ('坑', lambda d: d['月销'] * (-d['份额变化']))):
    d = X[X[typ]].assign(_k=key).sort_values('_k', ascending=False)
    L += [f'## {typ}（{len(d)} 个，列前 15）', ''] + tab(d.head(15), None) + ['']
# 每个框的小结
L += ['## 按框汇总：每个框里各类机会的个数', '', '| 框 | 框月销 | 增长型 | 评分缺口型 | 价格缺口型 | 坑 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for fr, d in X.groupby('框'):
    L.append(f"| {fr} | {d['框月销'].iloc[0]:,.0f} | {int(d['增长型'].sum())} | {int(d['评分缺口型'].sum())} | {int(d['价格缺口型'].sum())} | {int(d['坑'].sum())} |")
open(os.path.join(out, '机会扫描_202610.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

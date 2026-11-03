"""决策卡数据（样板：竖棱、岗石）。硬规则：一律在"同尺寸段 × 同拆装"的框里和同框其他取值比（wen 2026-11-03）。
CARD=竖棱 / 岗石。输出 solution-v2/机会判定卡/决策卡_<CARD>_数据.md 与每个主要框一张图；叙述与决策写在 决策卡_<CARD>.md。"""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
HERE = os.path.dirname(os.path.abspath(__file__)); CARD = os.environ.get('CARD', '竖棱')
os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('# ---------- 回测')], P, 'exec'), G); globals().update({k: v for k, v in G.items() if not k.startswith('__')})
fp = [f for f in font_manager.findSystemFonts() if 'wqy-zenhei' in f]
if fp: font_manager.fontManager.addfont(fp[0]); plt.rcParams['font.family'] = font_manager.FontProperties(fname=fp[0]).get_name()
OUTD = os.path.join(ROOT, 'solution-v2/机会判定卡'); f0 = lambda x: '—' if pd.isna(x) else f'{x:,.0f}'; p0 = lambda x: '—' if pd.isna(x) else f'{x:.0%}'; p1 = lambda x: '—' if pd.isna(x) else f'{x:.1%}'
# ---------- 行级：框、属性取值 ----------
B = A[A['尺寸段'].notna() & A['装'].notna()].copy(); B['框'] = B['尺寸段'].astype(str) + ' · ' + B['装'].astype(str)
B['r'] = pd.to_numeric(B['评分'], errors='coerce').where(lambda x: x.between(1, 5))
B['基准'] = B.groupby(['m', '框'])['价格'].transform('median'); B['价比'] = (B['价格'] / B['基准']).where(B['价格'] > 0)
if CARD == '竖棱':
    TARGET, ATTN = '竖棱', '元素'; B = B.assign(值=B['元素一']).explode('值'); B = B[B['值'].notna() & ~B['值'].map(UNK)]
    tok_t = '元素=竖棱'; tops = ('台面=陶瓷一体', '台面=树脂一体', '台面=石材台面')
else:
    TARGET, ATTN = '岗石', '台面材质'; B['值'] = B['D8台面材质']; B = B[B['值'].notna() & ~B['值'].isin(['信息不足', '不适用（不含台面）'])]
    tok_t = '台面=石材台面'; tops = ('台面=石材台面',)
B['新'] = B['月龄'] <= 6
E6, R6 = list(range(M0, M0 + 6)), list(range(END - 5, END + 1))
def wmed(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float); k = ~np.isnan(x); x, w = x[k], w[k]
    if not len(x) or w.sum() <= 0: return np.nan
    o = np.argsort(x); x, w = x[o], w[o]; c = np.cumsum(w); return x[np.searchsorted(c, c[-1] / 2)]
def stats(d, months):
    d = d[d['m'].isin(months)]
    if d.empty: return dict(月销=0.0, 家族=0, 中位价=np.nan, 溢价=np.nan, 评分=np.nan, 新品占比=np.nan)
    rr = d.dropna(subset=['r'])
    return dict(月销=d['c'].sum() / len(months), 家族=d['家族键'].nunique(), 中位价=wmed(d['价格'], d['c']), 溢价=wmed(d['价比'], d['c']),
                评分=(rr['r'] * rr['c']).sum() / rr['c'].sum() if rr['c'].sum() > 0 else np.nan, 新品占比=d.loc[d['新'], 'c'].sum() / d['c'].sum())
# ---------- 1. 全部框总览 ----------
rows = []
for fr, d in B.groupby('框'):
    t = d[d['值'] == TARGET]
    if t.empty: continue
    e, r = stats(t, E6), stats(t, R6); fe, frc = stats(d, E6), stats(d, R6)
    # 信号（站在 2026-10）：框内各取值的 6 个月份额斜率、新品占比差，按 全链路验证 2.2 的系数 0.824·b6 + 0.857·x5，减去同框各取值的销量加权平均
    sh = d[d['m'].isin(R6)].groupby(['值', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=R6, fill_value=0); sh = sh / sh.sum()
    xc = np.arange(6) - 2.5; b6 = (np.log(sh + 0.002) * xc).sum(axis=1) / (xc ** 2).sum()
    dn = d[d['m'].isin(R6)]; x5 = dn[dn['新']].groupby('值')['c'].sum().reindex(sh.index, fill_value=0) / dn.groupby('值')['c'].sum() - dn.loc[dn['新'], 'c'].sum() / dn['c'].sum()
    w = dn.groupby('值')['c'].sum(); pred = 0.824 * b6 + 0.857 * x5; rel = pred - (pred * w).sum() / w.sum()
    rows.append(dict(框=fr, 框月销=frc['月销'], 早_月销=e['月销'], 早_份额=e['月销'] / max(fe['月销'], 1e-9), 近_月销=r['月销'], 近_份额=r['月销'] / max(frc['月销'], 1e-9), 近_家族=r['家族'],
                     近_中位价=r['中位价'], 框中位价=frc['中位价'], 近_溢价=r['溢价'], 近_评分=r['评分'], 框评分=frc['评分'], 近_新品=r['新品占比'], 框新品=frc['新品占比'],
                     b6=b6.get(TARGET, np.nan), x5=x5.get(TARGET, np.nan), 相对预测=rel.get(TARGET, np.nan)))
OV = pd.DataFrame(rows).sort_values('近_月销', ascending=False)
# 新家族（进分母、走完观察期）按框
fam_fr = B.groupby('家族键')['框'].agg(lambda x: x.value_counts().index[0]); fam_t = B.groupby('家族键')['值'].agg(lambda x: TARGET in set(x))
keyfam = A.drop_duplicates('单位').set_index('单位')['家族键']; Ue = U[U['L'] + 5 <= END].copy(); Ue['家族键'] = keyfam.reindex(Ue.index).values
Ue['框'] = fam_fr.reindex(Ue['家族键']).values; Ue['含'] = fam_t.reindex(Ue['家族键']).fillna(False).values
nf = Ue.groupby(['框', '含'])['y'].agg(['size', 'sum'])
L = [f'# 决策卡数据：{TARGET}（按"同尺寸段 × 同拆装"分框）', '',
     f'> 由 `trial/决策卡.py`（CARD={CARD}）生成，数据 2024-10 至 2026-09。每一项都只和**同一个框（尺寸段 × 拆装）里的其他{ATTN}**比：份额 = {TARGET}销量 ÷ 框内{ATTN}已知的销量；溢价 = 价格 ÷ 同月同框中位价；新品 = 上架 ≤ 6 个月。',
     f'> 早期 = {ms(E6[0])} 至 {ms(E6[-1])}；近期 = {ms(R6[0])} 至 {ms(R6[-1])}。"相对预测"= 0.824 × 份额斜率 + 0.857 × 新品占比差（系数来自 全链路验证 2.2 的同框回归），减去同框其他{ATTN}的加权平均：> 0 表示预计在这个框里份额比别的{ATTN}涨得多。', '',
     '## 1. 所有出现过的框', '',
     f'| 框 | 框月销（近期） | {TARGET}月销 早期 → 近期 | 框内份额 早期 → 近期 | 近期在榜家族 | {TARGET}中位价 / 框中位价 | 溢价 | 评分 {TARGET} / 框 | 新品占比 {TARGET} / 框 | 相对预测 | 新家族（含{TARGET}）做到 / 家族 | 框内其他新家族 做到 / 家族 |',
     '| :--- | ---: | :--- | :--- | ---: | :--- | ---: | :--- | :--- | ---: | :--- | :--- |']
for r in OV.itertuples():
    a_ = nf.loc[(r.框, True)] if (r.框, True) in nf.index else None; b_ = nf.loc[(r.框, False)] if (r.框, False) in nf.index else None
    L.append(f"| {r.框} | {f0(r.框月销)} | {f0(r.早_月销)} → {f0(r.近_月销)} | {p1(r.早_份额)} → {p1(r.近_份额)} | {r.近_家族} | ${f0(r.近_中位价)} / ${f0(r.框中位价)} | {r.近_溢价:.2f} | "
             f"{r.近_评分:.2f} / {r.框评分:.2f} | {p0(r.近_新品)} / {p0(r.框新品)} | {r.相对预测:+.2f} | "
             f"{(f'{int(a_.iloc[1])} / {int(a_.iloc[0])}' if a_ is not None else '—')} | {(f'{int(b_.iloc[1])} / {int(b_.iloc[0])}' if b_ is not None else '—')} |".replace('nan', '—'))
MAIN = OV[OV['近_月销'] >= 15].assign(装=lambda d: d['框'].str.split(' · ').str[1]).groupby('装', sort=False).head(2)['框'].tolist()   # 每种拆装方式各取近期销量前 2 个框
# ---------- 2. 主要框：同框各取值对比 + 季度走势 + 代表产品 ----------
q_ = lambda m: f"{ms(m)[:4]}Q{(int(ms(m)[5:]) - 1) // 3 + 1}"
for fr in MAIN:
    d = B[B['框'] == fr]
    L += ['', f'## 2. 框：{fr}', '', f'### 2.1 近期（{ms(R6[0])} 至 {ms(R6[-1])}）框内各{ATTN}对比', '', f'| {ATTN} | 月销 | 份额 | 在榜家族 | 中位价 | 溢价 | 评分 | 新品占比 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    tot = stats(d, R6)['月销']
    for v, dv in sorted(d.groupby('值'), key=lambda kv: -kv[1].loc[kv[1]['m'].isin(R6), 'c'].sum())[:8]:
        s = stats(dv, R6)
        if s['月销'] < 5: continue
        L.append(f"| {'**' + v + '**' if v == TARGET else v} | {f0(s['月销'])} | {p1(s['月销'] / tot)} | {s['家族']} | ${f0(s['中位价'])} | {s['溢价']:.2f} | {s['评分']:.2f} | {p0(s['新品占比'])} |".replace('nan', '—'))
    L += ['', f'### 2.2 按季度：{TARGET}在这个框里怎么走过来', '', f'| 季度 | {TARGET}月销 | 框内份额 | {TARGET}中位价 | 溢价 | 评分 {TARGET} / 框 | 新品占比 {TARGET} / 框 | 在榜家族 |', '| :--- | ---: | ---: | ---: | ---: | :--- | :--- | ---: |']
    for qq in sorted({q_(m) for m in MONTHS}):
        ms_ = [m for m in MONTHS if q_(m) == qq]; s, sf = stats(d[d['值'] == TARGET], ms_), stats(d, ms_)
        L.append(f"| {qq} | {f0(s['月销'])} | {p1(s['月销'] / sf['月销'] if sf['月销'] else np.nan)} | ${f0(s['中位价'])} | {s['溢价']:.2f} | {s['评分']:.2f} / {sf['评分']:.2f} | {p0(s['新品占比'])} / {p0(sf['新品占比'])} | {s['家族']} |".replace('nan', '—'))
    # 代表产品：框内目标家族，近期销量前 3 + 最早进入的 1 个
    t = d[d['值'] == TARGET]; fam = t.groupby('家族键').agg(近=('c', lambda x: x[t.loc[x.index, 'm'].isin(R6)].sum()), 首=('m', 'min'))
    reps = list(dict.fromkeys(fam.sort_values('近', ascending=False).head(3).index.tolist() + fam.sort_values('首').head(1).index.tolist()))
    L += ['', f'### 2.3 代表产品（{fr}，近期销量前 3 + 最早在榜的 1 个）', '']
    fig, ax = plt.subplots(len(reps), 1, figsize=(10, 2.2 * len(reps)), sharex=True); ax = np.atleast_1d(ax)
    for i, k in enumerate(reps):
        g = t[t['家族键'] == k].drop_duplicates(['子ASIN', 'm']); top = g.sort_values('c', ascending=False).iloc[0]
        gm = g.groupby('m').agg(月销=('c', 'sum'), 价格=('价格', 'median'), 价比=('价比', 'median'), 评分=('r', 'median'), 排名=('小类BSR', 'min'), 子体=('子ASIN', 'nunique'))
        L += [f"**{top['品牌']} · {k}**  <img src=\"{top['主图500']}\" width=\"120\">  [商品链接]({top['商品链接']})  ",
              f"{fr} · 台面 {top['台面类型']}（{top['D8台面材质']}）· 元素 {'、'.join(top['元素一']) if isinstance(top['元素一'], list) else '—'} · 主色 {top['主色']} · 上架 {str(top['上架日期'])[:10]} · 首次在榜 {ms(int(g['m'].min()))}", '',
              '| 月 | 月销 | 价格 | 价比（÷ 同框中位） | 评分 | 小类排名 | 在榜子体 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
        L += [f"| {ms(m)} | {f0(r.月销)} | ${f0(r.价格)} | {r.价比:.2f} | {r.评分:.1f} | {f0(r.排名)} | {r.子体:.0f} |".replace('nan', '—') for m, r in gm.iterrows()] + ['']
        a = ax[i]; a.bar([ms(m) for m in MONTHS], gm['月销'].reindex(MONTHS).values, color='#2a6fdb'); a.spines[['top', 'right']].set_visible(False)
        a.set_title(f"{top['品牌']} · {k} · 价比中位 {gm['价比'].median():.2f}", fontsize=9, loc='left'); a.set_ylabel('月销')
    plt.xticks(rotation=60, fontsize=7); fig.tight_layout(); fn = f"决策卡_{CARD}_{fr.replace(' · ', '_')}_代表产品.png"; fig.savefig(os.path.join(OUTD, fn), dpi=110); plt.close(fig)
    L.insert(L.index(f'### 2.3 代表产品（{fr}，近期销量前 3 + 最早在榜的 1 个）') + 2, f'![{fr} 代表产品]({fn})\n')
    # 新品方案（这个框的尺寸与拆装固定）
    s_, z_ = fr.split(' · '); tr = U[U['L'] + 5 <= END]; sc_ = newprod(END + 1, False); lg = lambda p: np.log(p / (1 - p))
    rec = tr[tr['L'] >= tr['L'].max() - 5]; shift = lg(rec['y'].mean()) - lg(sc_(list(rec.index)).mean()); cand = []
    for dd in ('低', '中', '高'):
        for cc in ('白', '黑', '原木', '深木', '灰'):
            for tp in tops:
                kk = f'卡|{fr}|{dd}|{cc}|{tp}'; TK[kk] = [f'尺寸={s_}', f'档={dd}', tp, f'主色={cc}', f'装={z_}', '形态=落地式', '颜色≥2', '子体≥4'] + (['元素=竖棱'] if CARD == '竖棱' else [])
                cand.append((f"{dd}档 · {tp.split('=')[1]} · 主色{cc}", kk))
    pc = 1 / (1 + np.exp(-(lg(sc_([k for _, k in cand])) + shift))); o = np.argsort(-pc)
    L += [f'### 2.4 新品方案打分（{fr}，落地式、首月 ≥ 2 色 ≥ 4 子体；模型偏高约每 10 个 1 个）', '', '前 4：' + '；'.join(f"{cand[i][0]} {pc[i] * 10:.1f}" for i in o[:4]) + '。最低 2：' + '；'.join(f"{cand[i][0]} {pc[i] * 10:.1f}" for i in o[-2:]) + '。', '']
open(os.path.join(OUTD, f'决策卡_{CARD}_数据.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

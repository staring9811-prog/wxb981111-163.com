"""决策卡展开项：框内具体 SKU（子 ASIN）在什么情况下达成了什么。CARD=岗石 / 竖棱，FRAMES=逗号分隔的框。
输出 solution-v2/机会判定卡/决策卡_<CARD>_SKU.md。同框、同拆装比较（wen 硬规则）。"""
import os, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); CARD = os.environ.get('CARD', '岗石')
FRAMES = os.environ.get('FRAMES', '30″ · 拆装,48″ · 整装').split(',')
os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('FEAT = {T')], P, 'exec'), G); A, ms, ROOT, END = G['A'], G['ms'], G['ROOT'], G['END']
B = A[A['尺寸段'].notna() & A['装'].notna() & A['形态'].isin(['落地式', '悬浮式'])].copy(); B['框'] = B['尺寸段'].astype(str) + ' · ' + B['装'].astype(str) + ' · ' + B['形态'].astype(str)
B['基准'] = B.groupby(['m', '框'])['价格'].transform('median'); B['价比'] = B['价格'] / B['基准']
B['r'] = pd.to_numeric(B['评分'], errors='coerce'); B['rk'] = pd.to_numeric(B['小类BSR'], errors='coerce')
B['目标'] = B['元素一'].map(lambda t: '竖棱' in t) if CARD == '竖棱' else B['D8台面材质'].eq({'岗石': '岗石', '树脂': '树脂'}[CARD])
L = [f'# 决策卡展开：{CARD}的具体 SKU（子 ASIN）', '', '> 由 `trial/决策卡_SKU.py` 生成。月销 = 卖家精灵估算的子体月销；价比 = 价格 ÷ 同月同框中位价；排名 = 小类 BSR。',
     '> **2026-06 至 09 来自 v11 表**（家族键月间一致性低），这几个月的数字可能有来源切换的影响，表里标 *。', '']
for fr in FRAMES:
    d = B[(B['框'] == fr) & B['目标']]
    rows = []
    for a, g in d.groupby('子ASIN'):
        g = g.sort_values('m'); pk = g.loc[g['c'].idxmax()]; f50 = g[g['rk'] <= 50]
        rows.append(dict(子ASIN=a, 品牌=g['品牌'].iloc[0], 家族=g['家族键'].iloc[0], 链接=g['商品链接'].iloc[0], 图=g['主图500'].iloc[0], 上架=str(g['上架日期'].iloc[0])[:10],
                         首月=int(g['m'].min()), 在榜月=g['m'].nunique(), 价格=f"${g['价格'].min():,.0f}–{g['价格'].max():,.0f}" if g['价格'].min() != g['价格'].max() else f"${g['价格'].iloc[0]:,.0f}",
                         价比=g['价比'].median(), 评分=f"{g['r'].min():.1f}–{g['r'].max():.1f}" if g['r'].notna().any() else '—', 峰值月=int(pk['m']), 峰值销=pk['c'], 峰值价=pk['价格'], 峰值评分=pk['r'],
                         最好排名=g['rk'].min(), 进前50=f"{ms(int(f50['m'].min()))}（第 {int(f50['m'].min() - g['m'].min()) + 1} 个在榜月）" if len(f50) else '没进', 合计=g['c'].sum(),
                         台面=g['D8台面材质'].iloc[0], 元素='、'.join(g['元素一'].iloc[0]) if isinstance(g['元素一'].iloc[0], list) else '', 主色=g['主色'].iloc[0]))
    R = pd.DataFrame(rows).sort_values('峰值销', ascending=False)
    star = lambda m: ms(m) + ('*' if m >= END - 3 else '')
    L += [f'## {fr}（{len(R)} 个子 ASIN，按峰值月销排）', '',
          '| 子 ASIN | 品牌 | 规格 | 价格（价比） | 评分 | 首次在榜 / 在榜月数 | 峰值：月份、月销、当时价格与评分 | 峰值月销售额 | 最好排名 / 首次进前 50 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |']
    for r in R.head(15).itertuples():
        spec = f"{r.台面}{' · ' + r.元素 if r.元素 else ''} · {r.主色}"
        L.append(f"| [{r.子ASIN}]({r.链接}) | {r.品牌} | {spec} | {r.价格}（{r.价比:.2f}） | {r.评分} | {star(r.首月)} / {r.在榜月} | {star(r.峰值月)}：{r.峰值销:,.0f} 件，${r.峰值价:,.0f}，{r.峰值评分:.1f} 分 | ${r.峰值销 * r.峰值价:,.0f} | {('—' if pd.isna(r.最好排名) else f'{r.最好排名:,.0f}')} / {r.进前50} |".replace('nan 分', '— 分'))
    # 价格带
    d2 = d.assign(带=pd.cut(d['价格'], [0, 200, 250, 300, 400, 1e9], labels=['< $200', '$200–250', '$250–300', '$300–400', '≥ $400'], right=False))
    pb = d2.groupby('带', observed=True).agg(子体=('子ASIN', 'nunique'), 月份数=('m', 'size'), 月销中位=('c', 'median'), 月销最高=('c', 'max'), 评分=('r', 'median'))
    L += ['', f'**{fr} 按价格带**（每个子体 × 月算一次）', '', '| 价格带 | 子体数 | 子体 × 月 | 月销中位 | 月销最高 | 评分中位 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
    L += [f"| {k} | {r.子体} | {r.月份数} | {r.月销中位:,.0f} | {r.月销最高:,.0f} | {r.评分:.1f} |" for k, r in pb.iterrows()] + ['']
out = os.path.join(ROOT, f'solution-v2/机会判定卡/决策卡_{CARD}_SKU.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

"""小试：把 wen 的"维度 × 维度"透视表做法自动化。
对每一对维度（行 × 列）的每个格子，计算 ASIN 数、月销量、单位 ASIN 贡献、销量加权价格、加权评分、新品占比；
和"同一行"（行维度同值，如同尺寸）的整体比较，按 wen 的判断逻辑标出机会格子，并看 6–9 月是否每月都成立。
数据：input/data_v2（未入库）。只做描述性信号，不代表已验证能预测新品成败。"""
import json, re, itertools, sys
import pandas as pd, numpy as np

D = '/home/user/wxb981111-163.com/opportunity-research/input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v2'
a = json.load(open(D + '.analysis.json', encoding='utf-8'))
keep = {(r['month'], r['childASIN']) for r in a['rowManifest'] if r['includeInBathroomAnalysis']}
df = pd.read_excel(D + '.xlsx', sheet_name='SKU估算明细')
df['月'] = df['目标月份'].astype(str).str.replace('-', '').str[:6]
df = df[[(m, c) in keep for m, c in zip(df['月'], df['子ASIN'])]].copy()
df['销量'] = pd.to_numeric(df['最终SKU月销量估算'], errors='coerce')
df = df[df['销量'].notna()]
df['价格'] = pd.to_numeric(df['商品价格'], errors='coerce')
df['评分'] = pd.to_numeric(df['商品评分'], errors='coerce')
up = pd.to_datetime(df['上架日期'], errors='coerce')
mstart = pd.to_datetime(df['月'] + '01', format='%Y%m%d')
df['新品'] = (mstart - up).dt.days.between(0, 183)

def width_bin(v):
    try: w = float(v)
    except: return None
    for lo, hi, lab in [(0, 26, '≤25″'), (26, 33, '26–32″'), (33, 40, '33–39″'), (40, 47, '40–46″'), (47, 55, '47–54″'), (55, 66, '55–65″'), (66, 200, '≥66″')]:
        if lo <= w < hi: return lab
df['宽度'] = df['D9宽(in)'].map(width_bin)
df['价格段'] = pd.cut(df['价格'], [0, 200, 300, 450, 650, 1000, 1e9], labels=['<$200', '$200–300', '$300–450', '$450–650', '$650–1000', '≥$1000'])
dims = {'台面材质': 'D8台面材质', '柜体材质': 'D7柜体材质', '形态': 'D1产品形态', '安装方式': 'D2安装方式', '盆数': 'D3盆数', '元素': 'D5元素', '颜色': 'D6柜体颜色'}
for k, v in dims.items():
    df[k] = df[v].astype(str).str.split(r'[;；、,]').str[0].str.replace('（父体候选）', '').str.strip()
    df.loc[df[k].str.contains('信息不足|待|未知|nan|冲突', na=True), k] = None

def cell_stats(g):
    n = g['子ASIN'].nunique(); s = g['销量'].sum()
    w = g['销量'].where(g['价格'].notna(), 0)
    price = np.average(g['价格'].fillna(0), weights=w) if w.sum() > 0 else np.nan
    wr = g['销量'].where(g['评分'].notna(), 0)
    rating = np.average(g['评分'].fillna(0), weights=wr) if wr.sum() > 0 else np.nan
    per = g.groupby('子ASIN')['销量'].sum().sort_values(ascending=False)
    top1 = per.iloc[0] / s if s > 0 else np.nan
    return pd.Series({'头部1个占比': top1, '品牌数': g['品牌'].nunique(), 'ASIN数': n, '月销量': s, '单位贡献': s / n if n else np.nan, '加权价格': price, '加权评分': rating,
                      '新品数': g.loc[g['新品'], '子ASIN'].nunique(), '新品单位贡献': g.loc[g['新品'], '销量'].sum() / max(g.loc[g['新品'], '子ASIN'].nunique(), 1)})

rows = []
row_dims = ['宽度', '价格段']
col_dims = list(dims)
for rd, cd in itertools.product(row_dims, col_dims):
    for m, mg in df.groupby('月'):
        base = mg[mg[rd].notna()].groupby(rd, observed=True).apply(cell_stats)
        cells = mg[mg[rd].notna() & mg[cd].notna()].groupby([rd, cd], observed=True).apply(cell_stats)
        for (rv, cv), c in cells.iterrows():
            b = base.loc[rv]
            rows.append(dict(视图=f'{rd} × {cd}', 行=rv, 列=cv, 月=m, **c.to_dict(),
                             贡献指数=c['单位贡献'] / b['单位贡献'], 溢价=c['加权价格'] / b['加权价格'] - 1,
                             评分差=c['加权评分'] - b['加权评分'], 新品贡献指数=c['新品单位贡献'] / max(b['新品单位贡献'], 1e-9) if c['新品数'] else np.nan))
R = pd.DataFrame(rows)
last = R[R['月'] == '202609'].copy()
stab = R.groupby(['视图', '行', '列']).apply(lambda g: pd.Series({
    '贡献高的月数': int((g['贡献指数'] >= 1.3).sum()), '溢价且好卖月数': int(((g['溢价'] >= .15) & (g['贡献指数'] >= 1)).sum()),
    '评分低还好卖月数': int(((g['评分差'] <= -.15) & (g['贡献指数'] >= 1)).sum()), '观察月数': g['月'].nunique()}))
last = last.merge(stab, on=['视图', '行', '列'])
last = last[(last['ASIN数'] >= 8) & (last['品牌数'] >= 4)]  # 样本闸门：至少 8 个 ASIN、4 个品牌
last['集中'] = last['头部1个占比'] >= .4  # 头部 1 个 ASIN 占 40% 以上，视为爆款撑起来的
fmt = lambda d: d[['视图', '行', '列', 'ASIN数', '品牌数', '头部1个占比', '月销量', '单位贡献', '贡献指数', '加权价格', '溢价', '加权评分', '评分差', '新品数', '贡献高的月数', '溢价且好卖月数', '评分低还好卖月数']].round(2).to_string(index=False)
print('有效格子（9 月，ASIN≥8）:', len(last), '；总视图数', R['视图'].nunique())
print('\n## A 供不应求：单位贡献 ≥ 同行 1.3 倍，4 个月里至少 3 个月成立，不是单个爆款撑起')
A = last[(last['贡献指数'] >= 1.3) & (last['贡献高的月数'] >= 3)]
print(fmt(A[~A['集中']].sort_values('贡献指数', ascending=False).head(12))); print('（被剔除的爆款格子：', len(A[A['集中']]), '个）')
print('\n## B 能溢价：加权价格高于同行 15% 以上、单位贡献不低于同行，至少 3 个月成立')
B = last[(last['溢价'] >= .15) & (last['贡献指数'] >= 1) & (last['溢价且好卖月数'] >= 3)]
print(fmt(B[~B['集中']].sort_values('溢价', ascending=False).head(10))); print('（被剔除的爆款格子：', len(B[B['集中']]), '个）')
print('\n## C 有痛点：评分比同行低 0.15 以上但单位贡献不低于同行，至少 3 个月成立')
C = last[(last['评分差'] <= -.15) & (last['贡献指数'] >= 1) & (last['评低还好卖月数'] >= 3)] if '评低还好卖月数' in last else last[(last['评分差'] <= -.15) & (last['贡献指数'] >= 1) & (last['评分低还好卖月数'] >= 3)]
print(fmt(C[~C['集中']].sort_values('评分差').head(10))); print('（被剔除的爆款格子：', len(C[C['集中']]), '个）')
R.to_csv('/tmp/claude-0/-home-user/119403ec-8cb8-5bf0-b7f2-ffc89791de93/scratchpad/格子全量.csv', index=False)

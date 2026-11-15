"""回放 wen 的"26 年产品规划表"（11 个 SPU，约 2025-11 依据 2025-09 数据定）：这些方向在 2026 年 1–9 月的市场里怎样。
每个 SPU 翻成标签规则，只看规划的尺寸段：
  1. 这类产品有几个家族、销量占这几个尺寸段多少（1–3 月 → 7–9 月）；
  2. 2025-10 以后上架的同类新家族，到过前 100、前 50 的比例，和同尺寸段全部新家族比；
  3. 7–9 月单位 ASIN 贡献（销量 ÷ 子体数，wen 原表公式）÷ 同尺寸段平均；
  4. 实际中位价 ÷ 规划售价；子体月销（7–9 月，中位、前 25%、前 10%）对规划的单 SKU 预估月销。
规划表放在 input/data_v2/feishu_vanity/26年产品规划表.json（不入库）；成本、利润不读。
近似：大理石纹台面 = 岗石、卡拉拉大理石、Cultured Marble、岩板；"自然木纹""纯色" = 元素没打出且颜色为木色 / 黑白；SPC 用标题含 waterproof 代替（很粗）。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 回放_26年规划.py"""
import os, sys, json, re, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import tagged, ROOT
pd.set_option('display.width', 250)
NEW_FROM = '2025-10-01'

x = tagged()
els = x['元素'].fillna('').str.split('；')
has = lambda e: els.map(lambda l: e in l)
plain = x['元素'].isna()                       # 元素没打出（多为待图片核验），近似"没有装饰元素"
MARBLE = {'岗石', '卡拉拉大理石', 'Cultured Marble', '岩板'}
WOOD, BW = {'原木色', '胡桃木色'}, {'白色', '黑色'}
RULE = {
    'SPU1': ('Pedestal+fluted', (x.形态 == '柱状盆') & has('Fluted')),
    'SPU2': ('大理石纹台面+fluted', x.台面材质.isin(MARBLE) & has('Fluted')),
    'SPU3': ('大理石纹台面+夏克式', x.台面材质.isin(MARBLE) & has('Shaker')),
    'SPU4': ('大理石纹台面+自然木纹', x.台面材质.isin(MARBLE) & plain & x.颜色.isin(WOOD)),
    'SPU5': ('陶瓷一体盆+fluted', (x.台面材质 == '陶瓷') & has('Fluted')),
    'SPU6': ('陶瓷一体盆+自然木纹', (x.台面材质 == '陶瓷') & plain & x.颜色.isin(WOOD)),
    'SPU7': ('壁挂+自然木纹', (x.形态 == '悬浮式') & plain & x.颜色.isin(WOOD)),
    'SPU8': ('壁挂+纯色', (x.形态 == '悬浮式') & plain & x.颜色.isin(BW)),
    'SPU9': ('SPC+纯色（近似）', x.title.astype(str).str.contains('waterproof', case=False) & x.颜色.isin(BW)),
    'SPU10': ('石英石台面+自然木纹', (x.台面材质 == '石英石') & plain & x.颜色.isin(WOOD)),
    'SPU11': ('陶瓷一体+藤编', (x.台面材质 == '陶瓷') & has('Rattan')),
}

# 规划表：每行一个 SKU（尺寸 × 颜色），取尺寸、售价、预估月销量
cells = json.load(open(os.path.join(ROOT, 'input/data_v2/feishu_vanity/26年产品规划表.json'), encoding='utf-8'))
plan = []
for r in range(2, 60):
    if f'A{r}' not in cells: continue
    plan.append({'spu': cells[f'A{r}'], '尺寸段': cells.get(f'F{r}', '').replace('in', '″'),
                 '售价': float(cells.get(f'H{r}', 'nan')), '预估月销': float(cells.get(f'G{r}', 'nan'))})
plan = pd.DataFrame(plan)

fam_up = x.groupby('p').up.min()
x['新家族'] = x.p.map(fam_up) >= NEW_FROM
x['季'] = x.m.map(lambda m: f'Q{(int(m[5:]) - 1) // 3 + 1}')
rows = []
for spu, (name, rule) in RULE.items():
    pl = plan[plan.spu == spu]; sizes = sorted(set(pl['尺寸段']))
    inS = x['尺寸段'].isin(sizes); hit = inS & rule
    q = {qq: (x[hit & (x.季 == qq)].p.nunique(), x.loc[hit & (x.季 == qq), 'c'].sum() / x.loc[inS & (x.季 == qq), 'c'].sum()) for qq in ['Q1', 'Q3']}
    nf = x[hit & x.新家族].groupby('p').fbsr.min(); base = x[inS & x.新家族].groupby('p').fbsr.min()
    q3, q3all = x[hit & (x.季 == 'Q3')], x[inS & (x.季 == 'Q3')]
    eff = (q3.c.sum() / q3.k.nunique()) / (q3all.c.sum() / q3all.k.nunique()) if len(q3) else np.nan
    price = [q3.loc[q3.尺寸段 == s, 'price'].median() / pl.loc[pl.尺寸段 == s, '售价'].mean() for s in sizes if (q3.尺寸段 == s).any()]
    cm = q3.groupby(['k', 'm']).c.sum()
    rows.append({'SPU': f'{spu} {name}', '规划尺寸': '/'.join(sizes),
                 '家族数 Q1→Q3': f'{q["Q1"][0]}→{q["Q3"][0]}', '销量占比 Q1→Q3': f'{q["Q1"][1]:.1%}→{q["Q3"][1]:.1%}',
                 '新家族': len(nf), '进前100': f'{(nf <= 100).mean():.0%}' if len(nf) else '—', '进前50': f'{(nf <= 50).mean():.0%}' if len(nf) else '—',
                 '同尺寸新家族 前100/前50': f'{(base <= 100).mean():.0%}/{(base <= 50).mean():.0%}（{len(base)}）',
                 '单位ASIN贡献÷平均 Q3': round(eff, 2), '中位价÷规划价 Q3': '/'.join(f'{v:.2f}' for v in price) or '—',
                 '子体月销 Q3 中位/前25%/前10%': f'{cm.median():.0f}/{cm.quantile(0.75):.0f}/{cm.quantile(0.9):.0f}' if len(cm) else '—',
                 '规划单SKU月销': '/'.join(f'{v:.0f}' for v in pl.groupby('尺寸段')['预估月销'].mean())})
out = pd.DataFrame(rows).set_index('SPU')
print(f'新家族 = {NEW_FROM} 以后上架；前 100、前 50 = 2026-01 至 09 任一月家族最好 BSR')
print(out.T.to_string())

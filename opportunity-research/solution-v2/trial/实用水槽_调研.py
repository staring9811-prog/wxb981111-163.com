"""实用水槽调研（wen 待办第 4 条，2026-11-05）：utility / laundry / portable sink 一类，在我们浴室柜数据里有多少、卖得怎样。
读统一打标表（Amazon 浴室柜节点，2024-10 至 2026-10，含被剔除的行）、v11 表的五点、关键词研究包、三平台商品表。
结果表：input/data_v2/专题调研_20261105/实用水槽_*.csv；报告：solution-v2/开发建议/实用水槽_调研.md。"""
import os, re, html
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
D = os.path.join(ROOT, 'input/data_v2'); OUT = os.path.join(D, '专题调研_20261105'); os.makedirs(OUT, exist_ok=True)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 120); pd.set_option('display.max_rows', 300)
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1

A = pd.read_pickle(os.path.join(D, '统一打标/统一打标_分析用.pkl'))
A['标题'] = A['标题'].fillna('').map(html.unescape); A['SKU'] = A['SKU'].fillna('').astype(str).map(html.unescape)
A['m'] = A['月份'].map(mi); A['价格'] = pd.to_numeric(A['价格'], errors='coerce')
A['家族月销'] = pd.to_numeric(A['家族月销'], errors='coerce')

# ---------- 1. 圈出实用水槽 ----------
UT = re.compile(r"utility sink|laundry sink|laundry tub|utility tub|portable sink|wash station|no plumbing|mop sink|slop sink|garage sink|outdoor sink", re.I)
A['实用'] = A['标题'].str.contains(UT)
def kind(t):
    t = t.lower()
    if re.search(r'portable|wash station|no plumbing', t): return '免接水管移动水槽' if 'kid' not in t else '儿童移动洗手台'
    if re.search(r'laundry sink|utility sink|laundry tub', t): return '洗衣房水槽柜'
    return '其他'
S = A[A['实用']].copy(); S['类'] = S['标题'].map(kind)
print('实用水槽行', len(S), '款（家族键）', S['家族键'].nunique(), '；纳入浴室柜分析', S['纳入浴室柜分析'].value_counts().to_dict())
fam = S.groupby('家族键').agg(类=('类', 'first'), 品牌=('品牌', 'first'), 标题=('标题', 'first'), 首月=('月份', 'min'), 末月=('月份', 'max'), 在榜月数=('月份', 'nunique'),
                            子体数=('子ASIN', 'nunique'), 价低=('价格', 'min'), 价高=('价格', 'max'), 最好BSR=('小类BSR', 'min'), 评分=('评分', 'last'), 评分数=('评分数', 'max'),
                            上架=('上架日期', 'min'), 尺寸=('尺寸文本', lambda s: '; '.join(sorted(set(map(str, s.dropna()))))[:60]),
                            颜色=('SKU', lambda s: '; '.join(sorted(set(s)))[:120]), 纳入=('纳入浴室柜分析', 'first'), 剔除类=('非浴室柜类别', 'first'))
fm = S.groupby(['家族键', '月份'])['家族月销'].first().unstack()
fam = fam.join(fm.mean(axis=1).rename('在榜月平均月销')).join(fm.iloc[:, -1].rename('2026-10月销'))
print(fam.to_string())
fam.to_csv(os.path.join(OUT, '实用水槽_款清单.csv'), encoding='utf-8-sig')
print('\n== 逐款逐月家族月销（父体口径） =='); print(fm.T.to_string())
fm.T.to_csv(os.path.join(OUT, '实用水槽_逐月月销.csv'), encoding='utf-8-sig')

# 近 12 个月合计 vs 浴室柜节点
L12 = [f'{y}-{m:02d}' for y, m in [(2025, 11), (2025, 12)] + [(2026, k) for k in range(1, 11)]]
tot = A[A['纳入浴室柜分析']].groupby(['月份', '家族键'])['家族月销'].first().groupby('月份').sum()
ut = S.groupby(['月份', '家族键'])['家族月销'].first().groupby(['月份']).sum()
bytype = S.groupby(['月份', '类', '家族键'])['家族月销'].first().groupby(['月份', '类']).sum().unstack(fill_value=0)
T = pd.DataFrame({'实用水槽月销': ut.reindex(L12).fillna(0), '浴室柜节点月销': tot.reindex(L12)}).join(bytype.reindex(L12).fillna(0))
T['占比'] = T['实用水槽月销'] / T['浴室柜节点月销']
print('\n== 近 12 个月 =='); print(T.round(4).to_string())
T.to_csv(os.path.join(OUT, '实用水槽_近12月.csv'), encoding='utf-8-sig')

# ---------- 2. Splishkin 各子体 ----------
sp = A[A['家族键'] == 'B0FCCJL4QS'][['月份', '子ASIN', '标题', '价格', '小类BSR', '评分', '评分数', '上架日期', '尺寸文本', '子体月销（2026 原流程估算）']].sort_values(['子ASIN', '月份'])
print('\n== Splishkin 子体 =='); print(sp.to_string(index=False))
v11 = pd.read_excel(os.path.join(D, 'BathroomVanities_202606-202609_SKU销量预估_已打标_v11.xlsx'), sheet_name=0)
b = v11[v11['品牌'].astype(str).eq('Splishkin')]
print('Splishkin 五点：'); print(b['五点描述'].dropna().iloc[0][:400]); print('SKU属性：', b['SKU属性'].dropna().unique(), '重量：', b['商品重量'].dropna().unique())

# LUCKWIND 洗衣房水槽柜：同系列的尺寸、颜色、价格
lk = A[A['标题'].str.contains('Laundry Sink Cabinet Set', case=False)]
print('\n== LUCKWIND 洗衣房水槽柜 =='); print(lk.groupby(['家族键', '月份']).agg(子体=('子ASIN', 'nunique'), 价=('价格', 'median'), 家族月销=('家族月销', 'first'), BSR=('小类BSR', 'min'),
                                                                    评分=('评分', 'last'), 评分数=('评分数', 'max'), SKU=('SKU', lambda s: '; '.join(sorted(set(s)))[:150])).to_string())

# ---------- 3. 参照：浴室柜小尺寸框里，多颜色 / 多尺寸 / 低价的款是不是卖得多（只作参照，不是实用水槽本身） ----------
B = A[A['纳入浴室柜分析'] & A['m'].ge(mi('2026-01'))].copy()
B['w'] = pd.to_numeric(B['D9宽(in)'], errors='coerce')
B = B[B['w'].between(15, 26) & B['D2安装方式'].ne('整装') & B['形态（怎么装）'].eq('落地式') & B['柜体结构'].ne('开放式')]
B['尺寸段'] = np.where(B['w'] < 21, '18″', '24″')
B['色'] = B['SKU'].str.extract(r'Colou?r: ([^|]+)')[0].str.strip().str.lower()
f = B.groupby(['尺寸段', '家族键']).agg(c=('家族月销', lambda s: s.groupby(B.loc[s.index, 'm']).first().mean()), 色数=('色', 'nunique'), 宽数=('w', lambda s: s.round().nunique()),
                                         价=('价格', 'median'), 月数=('m', 'nunique')).reset_index()
f['多色'] = np.where(f['色数'] >= 3, '≥3 色', np.where(f['色数'] == 2, '2 色', '1 色'))
allw = A[A['m'].ge(mi('2026-01'))].assign(w=lambda d: pd.to_numeric(d['D9宽(in)'], errors='coerce').round()).groupby('家族键')['w'].nunique()
f['宽数'] = f['家族键'].map(allw)   # 整条链接（含其他尺寸段的子体）有几个宽度
f['多尺寸'] = np.where(f['宽数'] >= 2, '≥2 个尺寸', '1 个尺寸')
f['价档'] = f.groupby('尺寸段')['价'].transform(lambda s: pd.qcut(s, 3, labels=['便宜三分之一', '中间三分之一', '贵三分之一']))
for col in ['多色', '多尺寸', '价档']:
    g = f.groupby(['尺寸段', col], observed=True).agg(款=('家族键', 'size'), 单款月销中位=('c', 'median'), 价中位=('价', 'median'))
    print(f'\n== 参照（18″/24″ 拆装落地式浴室柜，2026-01 至 10）：{col} =='); print(g.round(1).to_string())
f.to_csv(os.path.join(OUT, '实用水槽_参照_小尺寸浴室柜款.csv'), index=False, encoding='utf-8-sig')

# ---------- 4. 关键词、小平台 ----------
K0 = pd.read_csv(os.path.join(D, 'keywords_20261028/数据/01_关键词词库/tables/keywords_unified.csv'))
kw = K0[K0['关键词'].str.contains(r'utility|laundry|portable|wash station|garage|outdoor sink|mop', case=False)].sort_values('月搜索量', ascending=False)
print('\n== 关键词研究包里的相关词 =='); print(kw[['关键词', '月搜索量', '处理状态', '判定依据']].to_string(index=False))
kw.to_csv(os.path.join(OUT, '实用水槽_相关搜索词.csv'), index=False, encoding='utf-8-sig')
seeds = pd.read_csv(os.path.join(D, 'keywords_20261028/数据/01_关键词词库/tables/seeds.csv')); print('种子词：', seeds.iloc[:, 0].tolist())
T3 = pd.read_csv(os.path.join(D, '渠道关键词/大词/三平台_商品表.csv'))
print('\n== 三平台商品表 =='); print(T3[T3['title'].fillna('').str.contains(UT.pattern + r'|laundry', case=False)][['渠道', 'title', '价格', '尺寸段', '浴室柜']].to_string(index=False))

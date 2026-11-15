"""小试⑤：同一父体家族内，各属性是否一致？——检验"同一链接产品类型相同，只有颜色尺寸不同"。
只用明确标签（剔除"信息不足/待图片核验/父体候选"），统计在至少 2 个子体有明确值的家族里，出现 ≥2 种取值的比例。"""
import pandas as pd
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].drop_duplicates(['核验父ASIN', '子ASIN'])
cols = ['D1产品形态', 'D2安装方式', 'D3盆数', 'D4台面形态', 'D5元素', 'D7柜体材质', 'D8台面材质', 'D8台盆材质', 'D6柜体颜色', 'D9宽(in)']
for c in cols:
    v = b[c].astype(str)
    ok = ~(v.isin(['nan', 'None']) | v.str.contains('信息不足|待图片核验|父体候选'))
    x = b[ok].assign(val=v[ok])
    g = x.groupby('核验父ASIN')['val'].agg(['nunique', 'size'])
    g = g[g['size'] >= 2]
    print(f"{c}: 可比家族 {len(g)}，家族内取值不一致 {int((g['nunique'] > 1).sum())}（{(g['nunique'] > 1).mean():.0%}）")

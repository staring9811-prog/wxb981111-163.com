"""推演：只勾选想看的变量去和命中率比较，能不能得到正确结论？
用"答案已知"的模拟数据：真实规律是我们设定的，看各种用法估出来的和真相差多少。
模拟只能检验方法，不能代表浴室柜的真实业务效果。"""
import numpy as np, pandas as pd, statsmodels.formula.api as smf, warnings
warnings.filterwarnings('ignore')

def make(n, rng):
    price = rng.choice(['低价', '中价', '高价'], n, p=[.4, .4, .2])
    strong = rng.random(n) < np.where(price == '高价', .5, np.where(price == '中价', .3, .15))  # 强品牌偏爱高价
    width = np.where(rng.random(n) < np.where(price == '低价', .15, .45), '≥48', '<48')       # 大尺寸多在中高价
    p_slate = np.select([price == '低价', price == '中价', price == '高价'], [.10, .35, .70])  # 岩板集中在高价
    top = np.where(rng.random(n) < p_slate, '岩板', np.where(rng.random(n) < .5, '石英', '陶瓷'))
    double = np.where(rng.random(n) < np.where(width == '≥48', .7, .05), '双盆', '单盆')      # 双盆跟着大尺寸
    color = rng.choice(['白', '木纹', '黑'], n)
    month = rng.integers(1, 13, n)
    return pd.DataFrame(dict(price=price, strong=strong.astype(int), width=width, top=top,
                             double=double, color=color, month=month))

def true_logit(d):
    # 真实规律（我们设定的答案）：
    #   价格：高价 +0.6，中价 +0.3；强品牌 +1.0；≥48″ +0.5
    #   岩板：只在中价带有用 +0.6，低价、高价没用；石英：处处 +0.15
    #   双盆、颜色：没有任何作用
    x = -2.0 + .3 * (d.price == '中价') + .6 * (d.price == '高价') + 1.0 * d.strong + .5 * (d.width == '≥48')
    x += .6 * ((d.top == '岩板') & (d.price == '中价')) + .15 * (d.top == '石英')
    return x

def sample(n, rng):
    d = make(n, rng)
    d['hit'] = (rng.random(n) < 1 / (1 + np.exp(-true_logit(d)))).astype(int)
    return d

def true_effect(d, a, b, mask=None):
    """真相：同一批商品，假如全换成 a 和全换成 b，命中率差多少个百分点"""
    s = d if mask is None else d[mask]
    pa = 1 / (1 + np.exp(-true_logit(s.assign(top=a))))
    pb = 1 / (1 + np.exp(-true_logit(s.assign(top=b))))
    return 100 * (pa.mean() - pb.mean())

def model_effect(m, d, a, b, mask=None):
    s = d if mask is None else d[mask]
    return 100 * (m.predict(s.assign(top=a)).mean() - m.predict(s.assign(top=b)).mean())

def run(n, rng):
    d = sample(n, rng)
    r = {}
    g = d.groupby('top').hit.mean() * 100
    r['A 只勾选台面'] = g['岩板'] - g['陶瓷']
    gd = d.groupby('double').hit.mean() * 100
    r['A 只勾选盆数（双盆-单盆）'] = gd['双盆'] - gd['单盆']
    mid = d[d.price == '中价']; gm = mid.groupby('top').hit.mean() * 100
    r['B 固定中价带再勾选台面'] = gm.get('岩板', np.nan) - gm.get('陶瓷', np.nan)
    m = smf.logit('hit ~ C(top, Treatment("陶瓷")) + C(price) + strong + C(width) + C(double) + C(color) + month', d).fit(disp=0)
    r['C 勾选台面 + 自动控制其他'] = model_effect(m, d, '岩板', '陶瓷')
    p = m.pvalues.get('C(double)[T.双盆]', np.nan); r['C 盆数被判"有用"(p<0.1)'] = float(p < .1)
    mi = smf.logit('hit ~ C(top, Treatment("陶瓷")) * C(price) + strong + C(width) + C(double) + C(color) + month', d).fit(disp=0)
    for band in ['低价', '中价', '高价']:
        r[f'D 加交互·{band}带'] = model_effect(mi, d, '岩板', '陶瓷', d.price == band)
    truth = {'A 只勾选台面': true_effect(d, '岩板', '陶瓷'), 'C 勾选台面 + 自动控制其他': true_effect(d, '岩板', '陶瓷'),
             'B 固定中价带再勾选台面': true_effect(d, '岩板', '陶瓷', d.price == '中价'),
             'A 只勾选盆数（双盆-单盆）': 0.0, 'C 盆数被判"有用"(p<0.1)': 0.1}
    for band in ['低价', '中价', '高价']:
        truth[f'D 加交互·{band}带'] = true_effect(d, '岩板', '陶瓷', d.price == band)
    return r, truth

for n in (600, 200):
    rng = np.random.default_rng(7)
    rows, truths = [], []
    for _ in range(300):
        try:
            r, t = run(n, rng); rows.append(r); truths.append(t)
        except Exception:
            pass
    R, T = pd.DataFrame(rows), pd.DataFrame(truths)
    out = pd.DataFrame({'估计均值': R.mean(), '真相均值': T.mean(), '估计的波动(标准差)': R.std()}).round(1)
    print(f'\n=== 样本 {n} 个起量新品，重复 {len(R)} 次 ===')
    print(out.to_string())

"""看图补标：合并 A、B 两组代理的读图结果和 wen 的复核，写出统一打标脚本要读的 看图标签.json（按家族键）。
规则（wen 2026-10-30 定边界，state.json S2-51）：
- 元素：两组一致、且至少一组把握为"高"的自动采用；其余进复核清单（按累计销量排），wen 选了的用 wen 的，没选的留空。
- 竖棱：fluted、reeded 看图不分；标题只写了 fluted 的拆成 fluted，只写了 reeded 的拆成 reeded，其余仍为竖棱（"纯色+竖棱"同理）。
- 开放层板、腿离地、壁挂、一体盆台：两组一致（是 / 否）才采用，其余留空。
输入目录 IN（默认 input/data_v2/看图补标，不入库）：清单_含链接.csv（图片、家族键、子ASIN、品牌、标题、累计销量）、
结果/A/*.csv 与 结果/B/*.csv（图片,元素,把握,开放层板,腿离地,壁挂,一体盆台）、wen复核.json（{"k017": "夏克式", ...}，可缺）。
用法：python3 -I 看图标签_合并.py"""
import os, re, glob, json, html, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
IN = os.environ.get('IN_DIR', os.path.join(ROOT, 'input/data_v2/看图补标'))
OUT = os.environ.get('OUT_JSON', os.path.join(ROOT, 'input/data_v2/统一打标/看图标签.json'))
YN = ['开放层板', '腿离地', '壁挂', '一体盆台']

L = pd.read_csv(f'{IN}/清单_含链接.csv', encoding='utf-8-sig')
def load(g):
    d = pd.concat([pd.read_csv(f, encoding='utf-8-sig', dtype=str) for f in sorted(glob.glob(f'{IN}/结果/{g}/*.csv'))])
    return d.drop_duplicates('图片', keep='last').set_index('图片').add_prefix(g)
M = L.set_index('图片').join(load('A')).join(load('B'))
WEN = json.load(open(f'{IN}/wen复核.json', encoding='utf-8')) if os.path.exists(f'{IN}/wen复核.json') else {}

def split(e, title):
    if e not in ('竖棱', '纯色+竖棱'): return e
    t = html.unescape(str(title)).lower()
    f, r = bool(re.search(r'\bflut', t)), bool(re.search(r'\breed', t))
    return e.replace('竖棱', 'fluted' if f and not r else ('reeded' if r and not f else '竖棱'))
M['两组判完'] = M['A元素'].notna() & M['B元素'].notna()
M['自动采用'] = M['两组判完'] & M['A元素'].eq(M['B元素']) & (M['A把握'].eq('高') | M['B把握'].eq('高')) & M['A元素'].ne('看不出')
M['复核'] = [WEN.get('k' + i[1:4]) for i in M.index]
rows = []
for img, r in M.iterrows():
    if r['自动采用']: e, how = split(r['A元素'], r['标题']), '两组一致（至少一组把握高）'
    elif r['复核'] and r['复核'] != '看不出': e, how = split(r['复核'], r['标题']), 'wen 复核'
    else: e, how = None, ('待 wen 复核' if r['两组判完'] else '没判完')
    rows.append(dict(家族键=r['家族键'], 代表子体=r['子ASIN'], 图片=img, 元素=e, 元素来源=how,
                     **{k: (r[f'A{k}'] if r[f'A{k}'] == r[f'B{k}'] and r[f'A{k}'] in ('是', '否') else None) for k in YN}))
R = pd.DataFrame(rows)
json.dump(rows, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
n, tot = len(R), M['累计销量'].sum()
print(f'{n} 个家族键：', R['元素来源'].value_counts().to_dict())
print('元素：', R['元素'].value_counts().to_dict())
for k in YN: print(f'{k}：两组一致可用 {int(R[k].notna().sum())}（是 {int(R[k].eq("是").sum())}）')
q = M[M['两组判完'] & ~M['自动采用']]
print(f'复核清单 {len(q)} 个，占这批累计销量 {q["累计销量"].sum() / tot:.0%}；wen 已选 {int(q["复核"].notna().sum())} 个')

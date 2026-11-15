"""交叉看板图：任意两个维度的市场格局表，黄框标出我们的位置。

输入一张商品表（CSV / XLSX / JSON 列表），每行一个商品，至少有：
  sales（月销）、rating（评分）、price（售价）、brand（品牌），以及作为行 / 列的字段（如 尺寸、台面）。
列名不同时用 --map 映射，例如 --map sales=月销 --map price=售价。

输出 <out>.html 和 <out>.png（PNG 需要 node + playwright；没有则只出 HTML）。

例：
  python cross_matrix.py --input hd.csv --filter "拆装=整装" --filter "尺寸in18″,24″,28″,30″" \
    --rows price --price-bins 0,200,300,400,600,900 --cols 台面 --our "280:陶瓷" \
    --title "Home Depot 小尺寸整装：价格 × 台面" --source "搜索前 150，按评论推算" --out hd
  python cross_matrix.py --input amz.csv --filter "形态=悬浮式" --rows 尺寸 --cols 台面 --show-price \
    --our "24″:岗石" --our "30″:岗石" --our-col-values "24″=$245,30″=$299" --out amz_float

--our 的行值：行是 price 时写一个价格（自动落到所在价格带），否则写行的取值；可重复。
"""
import argparse, csv, html, json, os, shutil, subprocess, sys, tempfile


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        return json.load(open(path, encoding='utf-8'))
    if ext in ('.xlsx', '.xlsm'):
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True, read_only=True).active
        it = ws.iter_rows(values_only=True)
        head = [str(h).strip() if h is not None else '' for h in next(it)]
        return [dict(zip(head, r)) for r in it]
    return list(csv.DictReader(open(path, encoding='utf-8-sig')))


def num(x):
    try:
        return float(str(x).replace('$', '').replace(',', '').strip())
    except (TypeError, ValueError):
        return 0.0


def bands(edges):
    e = [float(x) for x in edges.split(',')]
    out = []
    for i, lo in enumerate(e):
        hi = e[i + 1] if i + 1 < len(e) else float('inf')
        if lo == 0:
            lb = f'<${hi:,.0f}'
        elif hi == float('inf'):
            lb = f'≥${lo:,.0f}'
        else:
            lb = f'${lo:,.0f}–{hi - 1:,.0f}'
        out.append((lo, hi, lb))
    return out


def band_of(p, bs):
    for lo, hi, lb in bs:
        if lo <= p < hi:
            return lb


def keep(r, flt):
    for f in flt:
        if 'in' in f and '=' not in f.split('in')[0]:
            k, v = f.split('in', 1)
            if str(r.get(k.strip(), '')).strip() not in [x.strip() for x in v.split(',')]:
                return False
        elif '!=' in f:
            k, v = f.split('!=', 1)
            if str(r.get(k.strip(), '')).strip() == v.strip():
                return False
        else:
            k, v = f.split('=', 1)
            if str(r.get(k.strip(), '')).strip() != v.strip():
                return False
    return True


CSS = '''body{margin:0;font-family:"Microsoft YaHei","WenQuanYi Zen Hei",sans-serif;background:#fff;color:#222}
.w{display:inline-block;padding:18px 20px}h2{margin:0 0 4px;font-size:20px}.s{font-size:12.5px;color:#666;margin-bottom:10px}
table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #d9d9d9;padding:5px 7px;text-align:right;white-space:nowrap}
th{font-weight:700;text-align:center}td.sz{text-align:center;font-weight:700;background:#f4f6f8}.g{border-left:2px solid #555}
.lo{color:#c62828;font-weight:700}.e{color:#ccc;text-align:center}.hd{text-align:left;font-size:11.5px;color:#444}
.note{font-size:12px;color:#555;margin-top:8px;line-height:1.6}tr.ourrow td.sz{background:#fff4c2}
.tag{display:inline-block;background:#f5b700;color:#222;border-radius:3px;font-size:11px;padding:0 4px;margin-left:4px}
td.ours{outline:3px solid #f5b700;outline-offset:-3px}.tot td{font-weight:700;background:#fafafa}
td.ourv{background:#fff4c2;font-weight:700;text-align:center}'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--input', required=True)
    ap.add_argument('--map', action='append', default=[], help='标准名=表头，如 sales=月销')
    ap.add_argument('--filter', action='append', default=[], help='字段=值 / 字段!=值 / 字段in值1,值2')
    ap.add_argument('--rows', required=True, help='行字段；price 表示按价格分箱')
    ap.add_argument('--cols', required=True, help='列字段')
    ap.add_argument('--row-order', help='行顺序，逗号分隔（不在其中的行丢弃）')
    ap.add_argument('--col-order', help='列顺序，逗号分隔（不在其中的列排在后面）')
    ap.add_argument('--col-label', action='append', default=[], help='列显示名，如 陶瓷=陶瓷盆')
    ap.add_argument('--col-map', action='append', default=[], help='归并/改名列取值，如 Cultured Marble=人造大理石、木板=木板/其他；我们的差异列不要并')
    ap.add_argument('--row-map', action='append', default=[], help='归并/改名行取值（行不是 price 时）')
    ap.add_argument('--price-bins', default='0,200,300,400,600,900')
    ap.add_argument('--our', action='append', default=[], help='我们的格子 行值:列值，可重复')
    ap.add_argument('--our-note', default='', help='副标题里关于我们的说明')
    ap.add_argument('--our-col-values', help='右侧"我们"列：行值=文字，逗号分隔')
    ap.add_argument('--our-col-title', default='我们<br>售价')
    ap.add_argument('--show-price', action='store_true', help='格内加"加权均价"（价格不是轴时用）')
    ap.add_argument('--no-top', action='store_true', help='不显示"销量第一"')
    ap.add_argument('--shade', choices=['sales', 'per'], default='sales', help='底色按月销或单款月销')
    ap.add_argument('--unit', default='款', help='款 / ASIN')
    ap.add_argument('--min-sales', type=float, default=0, help='只统计月销大于此值的商品')
    ap.add_argument('--title', required=True)
    ap.add_argument('--subtitle', default='近 3 个月月均')
    ap.add_argument('--source', default='')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    mp = dict(m.split('=', 1) for m in a.map)
    g = lambda r, k: r.get(mp.get(k, k))
    rows_raw = [r for r in load(a.input) if keep(r, a.filter)]
    bs = bands(a.price_bins) if a.rows == 'price' else None
    collabel = dict(x.split('=', 1) for x in a.col_label)
    cmap = dict(x.split('=', 1) for x in a.col_map)
    rmap = dict(x.split('=', 1) for x in a.row_map)

    def rkey(r):
        if bs: return band_of(num(g(r, 'price')), bs)
        v = str(g(r, a.rows) or '未标').strip()
        return rmap.get(v, v)

    cell, noprice = {}, []
    for r in rows_raw:
        s = num(g(r, 'sales'))
        if s <= a.min_sales and a.min_sales:
            continue
        if bs and num(g(r, 'price')) <= 0:
            noprice.append(r); continue
        cv = str(g(r, a.cols) or '未标').strip()
        cell.setdefault((rkey(r), cmap.get(cv, cv)), []).append(r)

    ours = []
    for o in a.our:
        rv, cv = o.rsplit(':', 1)
        ours.append((band_of(num(rv), bs) if bs else rv.strip(), cv.strip()))
    our_rows = {x[0] for x in ours}

    if bs:
        present = {k[0] for k in cell} | our_rows
        rows = [lb for _, _, lb in bs if lb in present]
    elif a.row_order:
        rows = [x.strip() for x in a.row_order.split(',') if any(k[0] == x.strip() for k in cell) or x.strip() in our_rows]
    else:
        rows = sorted({k[0] for k in cell} | our_rows, key=lambda x: (num(x) == 0, num(x), x))
    allc = {k[1] for k in cell} | {x[1] for x in ours}
    order = [x.strip() for x in a.col_order.split(',')] if a.col_order else []
    cols = [c for c in order if c in allc] + sorted(c for c in allc if c not in order)

    def stats(v):
        s = sum(num(g(r, 'sales')) for r in v)
        rv = [r for r in v if num(g(r, 'rating')) > 0]
        ws = sum(num(g(r, 'sales')) for r in rv)
        wr = (sum(num(g(r, 'sales')) * num(g(r, 'rating')) for r in rv) / ws) if ws else (
            sum(num(g(r, 'rating')) for r in rv) / len(rv) if rv else 0)
        pv = [r for r in v if num(g(r, 'price')) > 0]
        wsp = sum(num(g(r, 'sales')) for r in pv)
        wp = (sum(num(g(r, 'sales')) * num(g(r, 'price')) for r in pv) / wsp) if wsp else (
            sum(num(g(r, 'price')) for r in pv) / len(pv) if pv else 0)
        top = max(v, key=lambda r: num(g(r, 'sales')))
        return s, len(v), wr, wp, top

    st = {k: stats(v) for k, v in cell.items()}
    shade_v = {k: (x[0] if a.shade == 'sales' else x[0] / x[1]) for k, x in st.items()}
    mx = max(shade_v.values()) if shade_v else 1
    mx = mx or 1
    sub = ['月销', f'{a.unit}数', f'单{a.unit}<br>月销'] + (['加权<br>均价'] if a.show_price else []) + ['加权<br>评分'] + ([] if a.no_top else ['销量第一'])
    n = len(sub)
    pal = ['#dff3ef', '#fbe1ec']
    ourv = dict(x.split('=', 1) for x in a.our_col_values.split(',')) if a.our_col_values else None
    rowname = '价格带' if bs else a.rows

    h = [f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><div class="w"><h2>{html.escape(a.title)}</h2>']
    shade_txt = '月销越高底色越深' if a.shade == 'sales' else f'单{a.unit}月销越高底色越深'
    h.append(f'<div class="s">{html.escape(a.subtitle)} · {shade_txt} · 评分低于 4.0 标红' +
             ((' · 黄色行 / 黄框为我们' + (f'（{html.escape(a.our_note)}）' if a.our_note else '')) if ours else '') + '</div>')
    h.append(f'<table><tr><th rowspan="2" style="background:#f4f6f8">{html.escape(rowname)}</th>')
    for i, c in enumerate(cols):
        h.append(f'<th colspan="{n}" class="g" style="background:{pal[i % 2]}">{html.escape(collabel.get(c, c))}</th>')
    h.append('<th rowspan="2" class="g" style="background:#eef1f5">合计<br>月销</th>')
    if ourv:
        h.append(f'<th rowspan="2" class="g ourv">{a.our_col_title}</th>')
    h.append('</tr><tr>')
    for i, _ in enumerate(cols):
        h.append(''.join(f'<th{" class=g" if j == 0 else ""} style="background:{pal[i % 2]}">{t}</th>' for j, t in enumerate(sub)))
    h.append('</tr>')
    coltot = {c: 0 for c in cols}
    for rw in rows:
        isour = rw in our_rows
        h.append(f'<tr class="{"ourrow" if isour else ""}"><td class="sz">{html.escape(rw)}{"<span class=tag>我们</span>" if isour else ""}</td>')
        rt = 0
        for c in cols:
            oc = ' ours' if (rw, c) in ours else ''
            if (rw, c) not in st:
                h.append(f'<td class="g e{oc}">—</td>' + ''.join(f'<td class="e{oc}">{"我们" if oc and j == n - 2 else ""}</td>' for j in range(n - 1)))
                continue
            s, k, wr, wp, top = st[(rw, c)]
            rt += s; coltot[c] += s
            al = 0.12 + 0.6 * (shade_v[(rw, c)] / mx) ** 0.5
            cells = [f'<td class="g{oc}"{"" if a.shade == "per" else f" style=background:rgba(27,175,122,{al:.2f})"}>{s:,.0f}</td>',
                     f'<td class="{oc}">{k}</td>',
                     f'<td class="{oc}"{f" style=background:rgba(27,175,122,{al:.2f})" if a.shade == "per" else ""}>{s / k:,.1f}</td>']
            if a.show_price:
                cells.append(f'<td class="{oc}">{"$" + format(wp, ",.0f") if wp else "—"}</td>')
            cells.append(f'<td class="{("lo" if 0 < wr < 4 else "") + oc}">{f"{wr:.2f}" if wr else "—"}</td>')
            if not a.no_top:
                b = html.escape(str(g(top, 'brand') or '')[:16])
                cells.append(f'<td class="hd{oc}">{b} ${num(g(top, "price")):,.0f} · {num(g(top, "sales")):,.0f}</td>')
            h.append(''.join(cells))
        h.append(f'<td class="g" style="font-weight:700">{rt:,.0f}</td>')
        if ourv:
            h.append(f'<td class="g ourv">{html.escape(ourv.get(rw, ""))}</td>')
        h.append('</tr>')
    tot = sum(coltot.values()) or 1
    h.append('<tr class="tot"><td class="sz">合计</td>' + ''.join(
        f'<td class="g">{coltot[c]:,.0f}</td><td colspan="{n - 1}" style="text-align:left;font-weight:400">占 {coltot[c] / tot * 100:.0f}%</td>' for c in cols) +
        f'<td class="g">{sum(coltot.values()):,.0f}</td>' + ('<td class="g"></td>' if ourv else '') + '</tr></table>')
    notes = [f'单{a.unit}月销 = 月销 ÷ {a.unit}数' + ('' if a.no_top else '；"销量第一"为该格月销最高的链接：品牌 售价 · 月销') + '。']
    if noprice:
        notes.append(f'另有 {len(noprice)} 款无价格未计入（' + '、'.join(
            f'{html.escape(str(g(r, "brand") or ""))} 月销 {num(g(r, "sales")):,.0f}' for r in noprice[:6]) + '）。')
    if a.source:
        notes.append('数据：' + html.escape(a.source))
    h.append('<div class="note">' + '<br>'.join(notes) + '</div></div>')
    open(a.out + '.html', 'w', encoding='utf-8').write(''.join(h))
    print('html:', a.out + '.html')

    if shutil.which('node'):
        js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();"
              "const p=await b.newPage({viewport:{width:3200,height:1000},deviceScaleFactor:2});"
              f"await p.goto('file://'+{json.dumps(os.path.abspath(a.out + '.html'))});await p.waitForTimeout(300);"
              f"await (await p.$('.w')).screenshot({{path:{json.dumps(os.path.abspath(a.out + '.png'))}}});await b.close()}})();")
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
            f.write(js)
        r = subprocess.run(['node', f.name], capture_output=True, text=True)
        os.unlink(f.name)
        print('png:', a.out + '.png' if r.returncode == 0 else '失败：' + r.stderr[-300:])
    else:
        print('未找到 node，PNG 未生成；用浏览器打开 HTML 截图')


if __name__ == '__main__':
    sys.exit(main())

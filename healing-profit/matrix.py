# -*- coding: utf-8 -*-
"""Market-layout matrices (rows = size / config, column groups = material / feature) from SellerSprite
Amazon child listings (mkt/*.csv). Parent sales are counted once: SellerSprite repeats the parent's monthly
units on every child, so each parent's units are split evenly across its children in the sample."""
import csv, html, os, re, json
from collections import defaultdict

E = html.escape

def load(path):
    rows, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = r.get("asin")
            if not a or a in seen:
                continue
            seen.add(a)
            def num(k):
                try: return float(r.get(k) or "")
                except ValueError: return None
            r["price"], r["units"], r["rating"] = num("price"), num("units") or 0.0, num("rating")
            r["t"] = html.unescape((r.get("title") or "") + " " + (r.get("sku") or "")).lower()
            rows.append(r)
    return rows

def split_parent_units(rows):
    """Each child carries the parent's units; give every child units / children."""
    by_p = defaultdict(list)
    for r in rows:
        by_p[r.get("parent") or r["asin"]].append(r)
    for kids in by_p.values():
        u = max(k["units"] for k in kids)
        for k in kids:
            k["u"] = u / len(kids)
    return rows

# ---------------- classifiers ----------------
def sauna_keep(t):
    if re.search(r"tent|blanket|\bpod\b|portable|dome|sauna box|\bbag\b|\bmat\b|steam|traditional|barrel|stove", t):
        return False
    if re.search(r"heater", t) and not re.search(r"person|room|cabin", t):
        return False
    return bool(re.search(r"infrared|full spectrum|far ir|far-ir|carbon|ceramic|red light", t)) and bool(re.search(r"person|people|sauna room|indoor sauna|outdoor sauna|home sauna", t))

WORDN = {"one": 1, "single": 1, "two": 2, "double": 2, "three": 3, "four": 4, "five": 5, "six": 6}
def sauna_cap(t):
    t2 = re.sub(r"\b(one|single|two|double|three|four|five|six)\b", lambda m: str(WORDN[m.group(1)]), t)
    m = re.search(r"(\d)\s*(?:-|to|~|–|or)\s*(\d)\s*(?:person|people|persons)", t2)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a == 1 and b == 2: return "1-2 人"
        if a == 2 and b == 3: return "2-3 人"
        if a == 3 and b == 4: return "3-4 人"
        return "4 人+" if a >= 4 else ("3-4 人" if a == 3 else f"{a}-{b} 人")
    m = re.search(r"(\d)\s*(?:person|people|persons|-person)", t2)
    if m:
        n = int(m.group(1))
        return {1: "1 人", 2: "2 人", 3: "3-4 人"}.get(n, "4 人+")
    return "未注明"
SAUNA_ROWS = ["1 人", "1-2 人", "2 人", "2-3 人", "3-4 人", "4 人+", "未注明"]
def sauna_wood(t):
    if "hemlock" in t: return "铁杉"
    if "cedar" in t: return "雪松"
    if re.search(r"spruce|pine|\bfir\b", t): return "云杉 / 松木 / 冷杉"
    return "其他 / 未注明"
SAUNA_COLS = ["铁杉", "雪松", "云杉 / 松木 / 冷杉", "其他 / 未注明"]

def tandem_keep(t):
    if not re.search(r"tandem|two people|2 people|couples|for two|2 person|double shower head", t):
        return False
    return not re.search(r"valve|faucet set|rough-in|trim kit|thermostatic|body jet|shower system faucet", t)
def tandem_cfg(t):
    if re.search(r"triple|3 shower head|three shower|3-way tandem|3 heads", t): return "三头（含手持）"
    if re.search(r"hand ?held|hand-held|handheld", t): return "双头 + 手持"
    return "双头"
TANDEM_COLS = ["双头", "双头 + 手持", "三头（含手持）"]
def band(p, edges, labels):
    for e, l in zip(edges, labels):
        if p < e: return l
    return labels[-1]
TANDEM_ROWS = ["< $80", "$80–120", "$120–180", "$180–250", "$250+"]
def tandem_row(p): return band(p, [80, 120, 180, 250], TANDEM_ROWS)

def thermo_keep(t, p):
    if p is None or p > 2500: return False
    if not re.search(r"system|set|combo|kit", t): return False
    if re.search(r"valve only|trim only|replacement|cartridge only|body spray trim", t): return False
    return bool(re.search(r"thermostatic|body jet|body spray|jets", t))
def thermo_jets(t):
    m = re.search(r"(\d+)\s*(?:pcs|pieces|x)?\s*(?:-|\s)?(?:body\s*)?(?:spray\s*)?(?:massage\s*)?jets?\b", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = int(m.group(1)); return "6 个及以上" if n >= 6 else "2–4 个"
    if re.search(r"(?:six|6)\s*(?:pcs)?\s*body", t): return "6 个及以上"
    if re.search(r"(?:four|4)\s*(?:pcs)?\s*body", t): return "2–4 个"
    if re.search(r"body jet|body spray|jets", t): return "有侧喷（数量未注明）"
    return "无侧喷"
THERMO_COLS = ["无侧喷", "2–4 个", "6 个及以上", "有侧喷（数量未注明）"]
def thermo_top(t):
    if re.search(r"(\d{2})\s*(?:\"|inch|in\.?)?\s*[x×\*]\s*(\d{2})", t): return "方形大顶喷（14×20″ 等）"
    sizes = [int(x) for x in re.findall(r"(\d{1,2})(?:\"|''|”|\s?-?inch|\s?in\b)", t) if 4 <= int(x) <= 30]
    if not sizes: return "未注明"
    s = max(sizes)
    if s <= 10: return "≤10″"
    if s <= 13: return "12″"
    if s <= 18: return "16″"
    return "20″+"
THERMO_ROWS = ["≤10″", "12″", "16″", "20″+", "方形大顶喷（14×20″ 等）", "未注明"]

def build(rows, rowf, colf, row_names, col_names):
    cell = defaultdict(lambda: {"u": 0.0, "n": 0, "pu": 0.0, "ru": 0.0, "rw": 0.0, "pn": 0.0})
    for r in rows:
        k = (rowf(r), colf(r)); c = cell[k]
        c["u"] += r["u"]; c["n"] += 1
        w = max(r["u"], 0.01)
        if r["price"]: c["pu"] += r["price"] * w; c["pn"] += w
        if r["rating"]: c["ru"] += r["rating"] * w; c["rw"] += w
    out = {}
    for k, c in cell.items():
        out[k] = dict(u=c["u"], n=c["n"], per=c["u"] / c["n"] if c["n"] else 0,
                      price=c["pu"] / c["pn"] if c["pn"] else None, rating=c["ru"] / c["rw"] if c["rw"] else None)
    rows_used = [r for r in row_names if any((r, c) in out for c in col_names)]
    cols_used = [c for c in col_names if any((r, c) in out for r in row_names)]
    return out, rows_used, cols_used

def render(title, sub, data, rows, cols, ours, row_label="尺寸", footnote=""):
    """ours: {row: {"cells": [col,...], "price": str, "margin": str, "cls": "good|warn|bad"}}"""
    out = data
    maxper = max((v["per"] for v in out.values()), default=1) or 1
    tot = sum(v["u"] for v in out.values()) or 1
    h1 = f'<th rowspan="2" class="rh">{row_label}</th>' + "".join(f'<th colspan="5" class="g g{i%2}">{E(c)}</th>' for i, c in enumerate(cols)) + \
         '<th rowspan="2" class="tot">合计<br>月销</th><th rowspan="2" class="our">我们<br>售价</th><th rowspan="2" class="our">我们<br>利润率</th>'
    h2 = "".join(f'<th class="s g{i%2}">月销</th><th class="s g{i%2}">ASIN数</th><th class="s g{i%2}">单ASIN<br>月销</th><th class="s g{i%2}">加权<br>均价</th><th class="s g{i%2}">加权<br>评分</th>' for i, _ in enumerate(cols))
    body = []
    for r in rows:
        o = ours.get(r)
        cls = ' class="mine"' if o else ""
        tag = ' <span class="chip">我们</span>' if o else ""
        tds = []
        for i, c in enumerate(cols):
            v = out.get((r, c)); box = o and c in o["cells"]
            b = " box" if box else ""
            if not v:
                tds.append(f'<td class="dash first{b}">—</td><td class="{b.strip()}"></td><td class="{b.strip()}"></td><td class="{b.strip()}"></td><td class="last{b}"></td>')
                continue
            a = 0.08 + 0.62 * (v["per"] / maxper)
            rt = v["rating"]
            rcls = "low" if rt is not None and rt < 4.0 else ""
            tds.append(f'<td class="first{b}">{v["u"]:,.0f}</td><td class="{b.strip()}">{v["n"]}</td>'
                       f'<td class="heat{b}" style="--a:{a:.2f}">{v["per"]:,.1f}</td>'
                       f'<td class="{b.strip()}">{"$" + format(v["price"], ",.0f") if v["price"] else "—"}</td>'
                       f'<td class="last{b} {rcls}">{f"{rt:.2f}" if rt else "—"}</td>')
        rt = sum(out[(r, c)]["u"] for c in cols if (r, c) in out)
        mp = f'<td class="our">{o["price"]}</td><td class="our"><span class="pill {o["cls"]}">{o["margin"]}</span></td>' if o else '<td class="our"></td><td class="our"></td>'
        body.append(f'<tr{cls}><th scope="row" class="rh">{E(r)}{tag}</th>{"".join(tds)}<td class="tot">{rt:,.0f}</td>{mp}</tr>')
    foot = []
    for i, c in enumerate(cols):
        cu = sum(out[(r, c)]["u"] for r in rows if (r, c) in out)
        foot.append(f'<td class="first">{cu:,.0f}</td><td colspan="4" class="last share">占 {cu/tot*100:.0f}%</td>')
    body.append(f'<tr class="sum"><th scope="row" class="rh">合计</th>{"".join(foot)}<td class="tot">{tot:,.0f}</td><td class="our"></td><td class="our"></td></tr>')
    return (f'<figure class="mx-fig"><figcaption><b>{E(title)}</b><span>{E(sub)}</span></figcaption>'
            f'<div class="tw mxw"><table class="mx"><thead><tr>{h1}</tr><tr>{h2}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<p class="note">单ASIN月销 = 月销 ÷ ASIN数，越高底色越深；评分低于 4.0 标红；黄色行 / 橙框为我们的产品落点。{footnote}</p></figure>')

MX_CSS = """
.mx-fig{margin:0;display:grid;gap:8px;width:min(1480px,calc(100vw - 32px));position:relative;left:50%;transform:translateX(-50%)}
.mx-fig figcaption{display:grid;gap:2px} .mx-fig figcaption b{font-size:16px} .mx-fig figcaption span{font-size:12.5px;color:var(--muted)}
table.mx{font-size:12.5px;border-collapse:separate;border-spacing:0}
table.mx th,table.mx td{padding:6px 7px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.mx thead th{text-align:center;font-weight:500;color:var(--fg);font-size:12px}
table.mx th.g0{background:var(--g0)} table.mx th.g1{background:var(--g1)}
table.mx th.rh{text-align:center;background:var(--bg);font-weight:500;position:sticky;left:0;z-index:1}
table.mx td.first{border-left:2px solid var(--line)}
table.mx td.dash{color:var(--muted);text-align:center}
table.mx td.heat{background:color-mix(in srgb,var(--heat) calc(var(--a)*100%),transparent)}
table.mx td.low{color:var(--bad);font-weight:600}
table.mx td.tot,table.mx th.tot{border-left:2px solid var(--line);font-weight:600}
table.mx td.our,table.mx th.our{background:var(--mine-bg)}
table.mx tr.mine>th.rh,table.mx tr.mine>td{background-color:var(--mine-bg)}
table.mx tr.mine>td.heat{background:color-mix(in srgb,var(--heat) calc(var(--a)*100%),var(--mine-bg))}
table.mx td.box{outline:2px solid var(--box);outline-offset:-2px}
table.mx tr.sum td,table.mx tr.sum th{background:var(--bg);font-weight:600} table.mx td.share{text-align:left;color:var(--muted);font-weight:400}
.chip{display:inline-block;font-size:10.5px;background:var(--box);color:#fff;border-radius:4px;padding:0 5px;margin-left:4px;vertical-align:1px}
"""

# -*- coding: utf-8 -*-
"""Build the healing-category profit report (index.html) and a v1.14 calculator import file.
Inputs: calc_out.json (v1.14 calcProduct output, via run.js), summary.json (break-even / max cost)."""
import json, os, html
HERE = os.path.dirname(os.path.abspath(__file__))
calc = json.load(open(os.path.join(HERE, "calc_out.json"), encoding="utf-8"))
summ = json.load(open(os.path.join(HERE, "summary.json"), encoding="utf-8"))
scen = json.load(open(os.path.join(HERE, "scen.json"), encoding="utf-8"))
R = {(r["sku"], r["tier"]): r for r in calc["res"]}
HC = {}
for r in json.load(open(os.path.join(HERE, "calc_hc103.json"), encoding="utf-8"))["res"]:
    HC[(r["sku"], r["tier"])] = r

def wx_table():
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    def row(name, get):
        cells = []
        for t, _ in TIERS:
            price, profit, m = get(t)
            cells.append(f'<td><div class="cell"><span class="price">{usd(price)}</span><span class="profit {"neg" if profit < 0 else ""}">{usd(profit)}</span>{pill(m)}</div></td>')
        return f'<tr><th scope="row">{name}</th>{"".join(cells)}</tr>'
    amz = lambda k: (lambda t: (HC[(k, t)]["amzPrice"], HC[(k, t)]["fbm"], HC[(k, t)]["fbm"] / HC[(k, t)]["amzPrice"]))
    pl = lambda k, c: (lambda t: (HC[(k, t)]["plat"][c]["retail"], HC[(k, t)]["plat"][c]["profit"], HC[(k, t)]["plat"][c]["margin"]))
    rows = [
        row("对照：SAD6221-1 珠三角 ¥6,270 · Amazon FBM", lambda t: (R[("SAD6221-1", t)]["amzPrice"], R[("SAD6221-1", t)]["fbm"], R[("SAD6221-1", t)]["fbm"] / R[("SAD6221-1", t)]["amzPrice"])),
        row("SMT-HC103 包装 +10% · Amazon FBM", amz("SMT-HC103")),
        row("SMT-HC103 包装 +10% · Home Depot", pl("SMT-HC103", "hd")),
        row("SMT-HC103 包装 +10% · Lowe's SC", pl("SMT-HC103", "lowesSC")),
        row("SMT-HC103 包装 +10% · Wayfair", pl("SMT-HC103", "wf")),
        row("参考：SMT-HC103 原包装 · Amazon FBM", amz("SMT-HC103-orig")),
    ]
    return (f'<div class="tw"><table class="pt"><thead><tr><th>方案（单人房）</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')
S = {(r["sku"], r["tier"]): r for r in summ}
E = html.escape

def usd(v, d=0):
    s = f"{abs(v):,.{d}f}"
    return ("−$" if v < 0 else "$") + s

def pill(m):
    if m is None:
        return '<span class="pill na">无同类</span>'
    cls = "good" if m >= 0.15 else ("warn" if m >= 0 else "bad")
    lab = "达标" if m >= 0.15 else ("微利" if m >= 0 else "亏损")
    return f'<span class="pill {cls}" title="{lab}">{m*100:.0f}%</span>'

CH = [("amzFBA", "Amazon FBA"), ("amzFBM", "Amazon FBM（自发货）"), ("hd", "Home Depot"),
      ("lowesVC", "Lowe's VC"), ("lowesSC", "Lowe's SC"), ("wf", "Wayfair")]
TIERS = [("low", "低价带"), ("mid", "中价带"), ("high", "高价带")]

def profit_table(sku, order):
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    body = []
    for k, name in order:
        cells = []
        for t, _ in TIERS:
            v = S[(sku, t)].get(k)
            if not v:
                cells.append('<td class="na-cell"><span class="pill na">无同类</span></td>')
                continue
            cells.append(
                f'<td><div class="cell"><span class="price">{usd(v["price"], 2 if v["price"] < 300 else 0)}</span>'
                f'<span class="profit {"neg" if v["profit"] < 0 else ""}">{usd(v["profit"])}</span>{pill(v["margin"])}</div></td>')
        body.append(f'<tr><th scope="row">{name}</th>{"".join(cells)}</tr>')
    return (f'<div class="tw"><table class="pt"><thead><tr><th>渠道</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>'
            '<p class="note">Amazon 低 / 中 / 高 = 同细分销量加权 25 / 50 / 75 分位；Home Depot / Lowe\'s / Wayfair 没有逐条销量，用搜索页标价参考，不与 Amazon 分位一一对应。每格：前台售价 · 单件利润 · 利润率。Amazon 利润率 = 利润 ÷ 售价；Home Depot / Lowe\'s / Wayfair = 利润 ÷ 平台结算价（前台价 ÷ 加价倍率）。'
            '颜色：<span class="pill good">≥15% 达标</span> <span class="pill warn">0–15% 微利</span> <span class="pill bad">亏损</span></p>')

def need_table(sku, chans):
    rows = []
    for k, name in chans:
        be = S[(sku, "mid")][k]["breakeven"]
        mx = [S[(sku, t)].get(k) for t, _ in TIERS]
        cells = "".join(
            f'<td>{"—" if not v else ("<span class=neg>无解</span>" if v["maxCostRMB"] <= 0 else "¥" + format(v["maxCostRMB"], ",d"))}</td>' for v in mx)
        rows.append(f'<tr><th scope="row">{name}</th><td>{usd(be)}</td>{cells}</tr>')
    return ('<div class="tw"><table class="nt"><thead><tr><th>渠道</th><th>保本前台价</th>'
            '<th>低价带下最高采购价</th><th>中价带下最高采购价</th><th>高价带下最高采购价</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')

def bar(label, price, parts, profit):
    total = sum(v for _, v, _ in parts)
    scale = max(total, price)
    segs = "".join(
        f'<span class="seg s{i+1}" style="width:{v/scale*100:.2f}%" title="{n} {usd(v)}"></span>' for i, (n, v, _) in enumerate(parts))
    mark = price / scale * 100
    legend = "".join(f'<li><i class="sw s{i+1}"></i>{n}<b>{usd(v)}</b><em>{d}</em></li>' for i, (n, v, d) in enumerate(parts))
    res = f'<b class="{"neg" if profit < 0 else "pos"}">{"利润" if profit >= 0 else "亏损"} {usd(profit)}（{profit/price*100:.0f}%）</b>'
    return (f'<div class="bar"><div class="bar-h"><span>{label}</span><span>售价 {usd(price, 2 if price < 300 else 0)} · 成本合计 {usd(total)} · {res}</span></div>'
            f'<div class="track"><div class="fill">{segs}</div><span class="pricemark" style="left:{mark:.2f}%"><span>售价</span></span></div>'
            f'<ul class="lg">{legend}</ul></div>')

def parts_amz(r, ship_key, ship_name):
    return [("采购成本", r["cost"], "出厂价换美元"), ("头程海运", r["sea"], "按体积分摊整柜"),
            (ship_name, r[ship_key], "尾程 / 配送"),
            ("平台费用", r["fees"], f'佣金 {usd(r["comm"])} + 广告 {usd(r["promo"])} + 退款 {usd(r["refund"])} + 汇损 {usd(r["fx"])}')]

d_mid, s1_mid, s2_mid = R[("DUAL", "mid")], R[("SAD6221-1", "mid")], R[("SAD6221-2", "mid")]
_old_bars = (bar("双人淋浴花洒 · Amazon FBA · 中位价", d_mid["amzPrice"], parts_amz(d_mid, "fbaShip", "FBA 配送费"), d_mid["fba"]) +
        bar("SAD6221-1 单人桑拿房 · Amazon FBM · 中位价", s1_mid["amzPrice"], parts_amz(s1_mid, "fbmShip", "LTL 尾程"), s1_mid["fbm"]) +
        bar("SAD6221-2 1-2 人桑拿房 · Amazon FBM · 中位价", s2_mid["amzPrice"], parts_amz(s2_mid, "fbmShip", "LTL 尾程"), s2_mid["fbm"]))

# ---------------- price-tier content (curated from channel pages + SellerSprite, 2026-11) ----------------
DUAL_TIERS = [
 ("低价带", "$60–95", [
   ("Amazon", "Nuodan 6\" 双头滑杆淋浴", "$74.99", "月销约 160"),
   ("Amazon", "Voolan 双头滑杆淋浴", "$79.99", "月销约 140"),
   ("Amazon", "TRIPHIL 16\" 宽杆双头", "$69.99", ""),
   ("Wayfair", "SR SUN RISE 双人横杆淋浴", "$92.99", "")],
  ["花洒头 ABS 电镀，横杆铝或薄不锈钢", "2 个固定头，无手持或塑料手持", "3–8 种出水模式", "免打孔、租房友好，靠低价走量"]),
 ("中价带", "$120–190", [
   ("Amazon", "OURBAOFU 双头 + 手持（采购参考款）", "$139.99–189.99", "月销约 320，4.4★"),
   ("Amazon", "KES 原创可调滑杆 7 模式", "$159.99–169.99", "Home Depot $159.99 / Wayfair $163.99"),
   ("Amazon", "Novast / SOOVOW 双头系统", "$119.99–159.98", ""),
   ("Lowe's", "Justincity 双人滑杆淋浴", "$177.98", "")],
  ["不锈钢滑杆 + 2 个头 + 手持，三出水", "三通分水阀，可单独或同时出水", "7 种左右出水模式，高度/角度可调", "部分带过滤芯；多色饰面（黑/镍/金）"]),
 ("高价带", "$220–400", [
   ("Amazon", "BOONA Tandem Shower（Shark Tank 款）", "$220–319", "月销约 525，4.8★ 1,228 评"),
   ("Lowe's", "ITOPFOX 三头全金属双人系统", "$297–387", ""),
   ("Lowe's", "LAIFUCAM 双人淋浴杆 5 模式", "$397.48", "")],
  ["全金属（黄铜 / 不锈钢）机身与滑杆", "专利滑杆结构，单手调距", "品牌背书 + 大量高分评价", "礼品化包装（情侣 / 家庭场景）"]),
]
SAUNA_TIERS = [
 ("低价带", "$700–1,000", [
   ("Amazon", "Albott 1 人低 EMF 红外桑拿", "$899.99", "月销约 160（父体）"),
   ("Amazon", "Homsido 1 人铁杉 900W", "$749–949", "月销约 100（父体）"),
   ("Home Depot", "Spygo 1 人欧洲白杨木 6 板", "$979", ""),
   ("Wayfair", "Sauna Pro 1 人奥克曼木", "$995.99（原价 $2,049.99）", "4.7★")],
  ["智利松 / 云杉 / 白杨或基础铁杉", "900–1,050W 碳纤维板 4–6 片", "5–6mm 钢化玻璃，矮款 59–67\"", "蓝牙 + LCD 面板，无红光、无 App"]),
 ("中价带", "$1,100–1,500", [
   ("Amazon", "Dynamic Saunas Elite 1 人", "$1,299–1,499", "704 评，4.6★"),
   ("Amazon", "Homsido 1 人红光美容灯款", "$1,149–1,399", ""),
   ("Home Depot", "SaunaSpa S13HD 1 人铁杉触控", "$1,441", "65 评，5★"),
   ("Wayfair", "Holaki 1 人远红外", "$1,399", "")],
  ["加拿大铁杉", "1,200–1,450W 低 EMF 碳板", "7 色光疗 + 红光美容灯 / 负离子", "触控面板 + 蓝牙，高度 67–75\""]),
 ("高价带", "$1,700–2,800", [
   ("Home Depot", "Backyard Discovery Rylan 1 人雪松", "$1,799", "104 评，4.9★"),
   ("Amazon", "Dynamic Saunas Barcelona 1-2 人", "$1,799.99", "781 评，4.6★"),
   ("Home Depot", "Maxxus 全光谱红光 1 人", "$2,055", ""),
   ("Lowe's", "LOVMOR 1 人红雪松", "$2,818.90", "")],
  ["红雪松或品牌铁杉", "全光谱：远红外 + 近红外 660/850nm 红光", "App / WiFi 控制，户外防水款", "美国品牌（Dynamic、Backyard Discovery、Sunray）+ 大量评价"]),
]

def tier_cards(tiers, ours_tier):
    out = []
    for name, rng, prods, feats in tiers:
        ours = '<span class="ours">我方定位</span>' if name == ours_tier else ""
        pr = "".join(f'<li><span class="ch">{E(c)}</span><span class="pn">{E(n)}</span><span class="pp">{E(p)}</span>'
                     f'{f"<span class=pm>{E(m)}</span>" if m else ""}</li>' for c, n, p, m in prods)
        ft = "".join(f"<li>{E(f)}</li>" for f in feats)
        out.append(f'<article class="tier"><header><h4>{name}</h4><span class="rng">{rng}</span>{ours}</header>'
                   f'<div class="tier-b"><div><h5>代表产品</h5><ul class="prods">{pr}</ul></div>'
                   f'<div><h5>功能 / 材质特征</h5><ul class="feats">{ft}</ul></div></div></article>')
    return f'<div class="tiers">{"".join(out)}</div>'

def price_grid(sku):
    t = next(s for s in scen["skus"] if s["id"] == sku)["tiers"]
    rows = []
    for k, name in [("amz", "Amazon"), ("hd", "Home Depot"), ("wf", "Wayfair"), ("lw", "Lowe's")]:
        cells = "".join(f'<td>{usd(t[x][k], 2 if t[x][k] < 300 else 0) if t[x][k] else "—"}</td>' for x, _ in TIERS)
        rows.append(f"<tr><th scope=row>{name}</th>{cells}</tr>")
    return ('<div class="tw"><table class="pg"><thead><tr><th>测算用前台价（Amazon = 销量加权分位）</th><th>低</th><th>中</th><th>高</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


# ---------------- thermostatic shower systems (procurement quotes, estimated packaging) ----------------
TH = json.load(open(os.path.join(HERE, "calc_thermo.json"), encoding="utf-8"))["res"]
TS = json.load(open(os.path.join(HERE, "scen_thermo.json"), encoding="utf-8"))["skus"]
_pct = (calc["params"]["promo"] + calc["params"]["fx"] + calc["params"]["refund"] + calc["params"]["comm"]) / 100
def th_rows(sku):
    return {r["tier"]: r for r in TH if r["sku"] == sku}
def th_summary():
    head = ('<tr><th>型号</th><th>报价</th><th>包装（估）</th><th>Amazon FBA 低</th><th>Amazon FBA 中</th><th>Amazon FBA 高</th>'
            '<th>HD 中</th><th>Lowe\'s SC 中</th><th>Wayfair 中</th><th>Amazon 保本价</th></tr>')
    body = []
    for s in TS:
        r = th_rows(s["id"]); g = s["pkgs"][0]
        def amz(t):
            x = r[t]; return f'<td><div class="cell"><span class="price">{usd(x["amzPrice"])}</span><span class="profit {"neg" if x["fba"]<0 else ""}">{usd(x["fba"])}</span>{pill(x["fba"]/x["amzPrice"])}</div></td>'
        def plat(k):
            v = r["mid"]["plat"][k]
            if not v["priced"]: return '<td class="na-cell"><span class="pill na">无同类</span></td>'
            return f'<td><div class="cell"><span class="price">{usd(v["retail"])}</span><span class="profit {"neg" if v["profit"]<0 else ""}">{usd(v["profit"])}</span>{pill(v["margin"])}</div></td>'
        be = (r["mid"]["cost"] + r["mid"]["sea"] + r["mid"]["fbaShip"]) / (1 - _pct)
        body.append(f'<tr><th scope="row">{s["id"]}</th><td>¥{s["cost"]:,}</td><td>{g[0]:.0f}×{g[1]:.0f}×{g[2]:.0f}cm · {g[3]}kg</td>'
                    f'{amz("low")}{amz("mid")}{amz("high")}{plat("hd")}{plat("lowesSC")}{plat("wf")}<td>{usd(be)}</td></tr>')
    return f'<div class="tw"><table class="pt"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'
def th_detail(sku):
    r = th_rows(sku)
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    rows = []
    def cell(price, profit, m):
        return f'<td><div class="cell"><span class="price">{usd(price)}</span><span class="profit {"neg" if profit<0 else ""}">{usd(profit)}</span>{pill(m)}</div></td>'
    rows.append('<tr><th scope="row">Amazon FBA</th>' + "".join(cell(r[t]["amzPrice"], r[t]["fba"], r[t]["fba"]/r[t]["amzPrice"]) for t,_ in TIERS) + '</tr>')
    rows.append('<tr><th scope="row">Amazon FBM</th>' + "".join(cell(r[t]["amzPrice"], r[t]["fbm"], r[t]["fbm"]/r[t]["amzPrice"]) for t,_ in TIERS) + '</tr>')
    for k, name in [("hd","Home Depot"),("lowesVC","Lowe's VC"),("lowesSC","Lowe's SC"),("wf","Wayfair")]:
        cs = []
        for t,_ in TIERS:
            v = r[t]["plat"][k]
            cs.append(cell(v["retail"], v["profit"], v["margin"]) if v["priced"] else '<td class="na-cell"><span class="pill na">无同类</span></td>')
        rows.append(f'<tr><th scope="row">{name}</th>{"".join(cs)}</tr>')
    return f'<div class="tw"><table class="pt"><thead><tr><th>渠道</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
TH_TIERS = [
 ("低价带", "$250–420", [
   ("Amazon", "Oupukle 恒温 12\" 顶喷 + 6 侧喷", "$360.99", ""),
   ("Wayfair", "CASAINC 12\" 吸顶恒温 + 6 侧喷", "$362.50", "4.9★ 41 评"),
   ("Home Depot", "Boyel Living 恒温 12\" + 6 侧喷", "$291.29", ""),
   ("Lowe's", "Yichuhaoxi 12\" LED 顶喷 + 4 侧喷", "$421.98", "5★ 16 评")],
  ["12\" 方 / 圆顶喷 + 4–6 个侧喷 + 手持", "基础恒温阀或压力平衡阀，按键 / 旋钮分水", "侧喷多为塑料或锌壳，顶喷 ABS 或薄不锈钢", "以中国卖家白牌为主"]),
 ("中价带", "$450–870", [
   ("Amazon", "JetsBath 16\" 恒温 + 6 侧喷", "$489.99", ""),
   ("Amazon", "Dasan 恒温双头（16\" + 6\"）+ 6 侧喷", "$599–670", "月销约 80"),
   ("Wayfair", "EVERSTEIN 12\" 双雨淋 + 6 侧喷", "$477", "5★"),
   ("Home Depot", "Modland 16\" 恒温 + 6 侧喷", "$867.64", "")],
  ["16\" 顶喷或双顶喷（雨淋 + 6\" 壁喷）", "6 个可调侧喷，各出水可同时开", "黄铜恒温阀体，3–4 路分水", "多色饰面（黑 / 镍 / 金）"]),
 ("高价带", "$740–1,500", [
   ("Amazon", "NPYSVSSS 14×20\" 吸顶 LED 恒温 + 侧喷", "$739.99", ""),
   ("Amazon", "RomceBath 16×24\" 三合一（雨淋 / 瀑布 / 喷雾）", "$899.99", ""),
   ("Wayfair", "EVERSTEIN 16\" 双雨淋 + 6 侧喷", "$1,118.55", "4.7★ 187 评"),
   ("Home Depot", "GRANDJOY 16\" RGB LED + 6 侧喷", "$1,439.10", "")],
  ["大尺寸嵌顶顶喷，多功能（雨淋 + 瀑布 + 喷雾）", "LED 灯 / 数显温度 / 蓝牙音乐", "全铜阀体，5–6 路分水", "品牌店铺（EVERSTEIN、GRANDJOY）+ 较多评价"]),
]
TH2_TIERS = [
 ("低价带", "$160–180", [("Amazon", "Gabrylly 10\" 恒温花洒 + 浴缸龙头", "$179.99", "月销约 560"), ("Amazon", "VEVOR 恒温吸顶 + 6\" 壁喷 + 手持", "$158.99", "")],
  ["10–12\" 顶喷 + 手持，两功能", "基础恒温阀", "顶喷 ABS，手持塑料"]),
 ("中价带", "$340–550", [("Amazon", "SHOYELA 恒温 12\" + 6\" 双头", "$339.99", "4.3★ 196 评"), ("Amazon", "VANFOXLE 恒温花洒套装", "$349.99", ""), ("Home Depot", "EVERSTEIN 恒温壁挂 12\" + 6\"", "$548", ""), ("Lowe's", "GRANDJOY 恒温 12\" 双头 + 3 侧喷", "$479", "")],
  ["12\" 顶喷 + 6\" 壁喷 + 手持", "按键分水，可同时出水", "黄铜阀体"]),
 ("高价带", "$460–830", [("Amazon", "JetsBath 16\" 恒温双雨淋", "$459.99", ""), ("Home Depot", "YAWWALK 恒温 12\" + 6\" 7 种出水", "$669", "4.9★"), ("Wayfair", "EVERSTEIN 恒温 12\"（含预埋阀）", "$825.75", "4.8★ 106 评")],
  ["16\" 大顶喷或品牌款", "含预埋阀，安装配套齐", "品牌 + 较多评价"]),
]

# ---------------- market-layout matrices (Amazon, SellerSprite 2026-10) ----------------
import matrix as MX
MX_ITEMS = {}
MX_ROWS = {}
Q = json.load(open(os.path.join(HERE, "quartiles.json"), encoding="utf-8"))
def _mx(name, keep, rf, cf, R, C):
    rows = [r for r in MX.load(os.path.join(HERE, "mkt", name + ".csv")) if keep(r)]
    MX.split_parent_units(rows)
    order = [r["asin"] for r in sorted(rows, key=lambda r: -r["u"])]
    sp, _ = MX.make_sprite(order, os.path.join(HERE, "img"), os.path.join(HERE, f"sprite_{name}.jpg"))
    MX_ITEMS.update(MX.cell_items(rows, rf, cf, name, MX.load_meta(os.path.join(HERE, "mkt", name + "_meta.csv")), sp))
    MX_ROWS[name] = rows
    return MX.build(rows, rf, cf, R, C), len(rows)
(_sd, _sn) = _mx("sauna", lambda r: MX.sauna_keep(r["t"]), lambda r: MX.sauna_cap(r["t"]), lambda r: MX.sauna_wood(r["t"]), MX.SAUNA_ROWS, MX.SAUNA_COLS)
_TD = MX.load_tandem_detail(os.path.join(HERE, "mkt", "tandem_detail.jsonl"))
def _tdg(r):
    v = _TD.get(r.get("parent")) or _TD.get(r["asin"]) or ("未注明", "未注明", None, "")
    if "ex" not in r:
        r["ex"] = ([f"材质：{v[3][:60]}"] if v[3] else []) + ([f"可调宽度至 {v[2]:g}″"] if v[2] else []) + [MX.tandem_cfg(r["t"])]
    return v
(_td, _tn) = _mx("tandem", lambda r: MX.tandem_keep(r["t"]) and r["price"] and _tdg(r), lambda r: _tdg(r)[0], lambda r: _tdg(r)[1], MX.TANDEM2_ROWS, MX.TANDEM2_COLS)
(_hd, _hn) = _mx("thermo", lambda r: MX.thermo_keep(r["t"], r["price"]), lambda r: MX.thermo_top(r["t"]), lambda r: MX.thermo_jets(r["t"]), MX.THERMO_ROWS, MX.THERMO_COLS)
def _m(x): return f"{x*100:.0f}%"
def _c(x): return "good" if x >= 0.15 else ("warn" if x >= 0 else "bad")
_t = lambda sku, t, ch: (lambda r: r[ch] / r["amzPrice"])(next(x for x in TH if x["sku"] == sku and x["tier"] == t))
s1m = R[("SAD6221-1", "mid")]["fbm"] / R[("SAD6221-1", "mid")]["amzPrice"]
hcm = HC[("SMT-HC103", "mid")]["fbm"] / HC[("SMT-HC103", "mid")]["amzPrice"]
s2m = R[("SAD6221-2", "mid")]["fbm"] / R[("SAD6221-2", "mid")]["amzPrice"]
dmm = R[("DUAL", "mid")]["fba"] / R[("DUAL", "mid")]["amzPrice"]
MX_SAUNA = (
  MX.render("Amazon 红外桑拿房（木质房体）：容量 × 木材", f"2026-10 · 卖家精灵 {_sn} 个子体 · 父体月销按子体平均分摊",
            _sd[0], _sd[1], _sd[2],
            {"1 人": {"cells": ["铁杉"], "price": usd(R[("SAD6221-1", "mid")]["amzPrice"]), "margin": f"SAD6221-1 {_m(s1m)}<br>SMT-HC103 {_m(hcm)}", "cls": "bad"},
             "1-2 人": {"cells": ["铁杉"], "price": usd(R[("SAD6221-2", "mid")]["amzPrice"]), "margin": f"SAD6221-2 {_m(s2m)}", "cls": _c(s2m)}},
            mid="sauna", row_label="容量", footnote="容量、木材按标题识别，标题没写木材的归“其他 / 未注明”；已剔除帐篷 / 便携 / 蒸汽 / 桶形款。我方售价 = 1 人 / 1-2 人款 Amazon 销量加权中位价。利润率为 Amazon FBM，SMT-HC103 按包装 +10%。")
)
MX_DUAL = (
  MX.render("Amazon 双人淋浴花洒：可调宽度 × 材质", f"2026-10 · 卖家精灵 {_tn} 个子体（tandem / two people / couples 词组匹配）· 已剔除带阀门的淋浴系统",
            _td[0], _td[1], _td[2],
            {"61–80″": {"cells": ["ABS + 不锈钢 / 金属"], "price": usd(R[("DUAL", "mid")]["amzPrice"], 2), "margin": _m(dmm), "cls": _c(dmm)}},
            mid="tandem", row_label="可调宽度", footnote="材质取商品详情页的 Material 字段，可调宽度取卖点里写的最大适配宽度（如 fits 48–78 inch），按父体取一个代表 ASIN 的详情（49 个父体）。我方按 OURBAOFU 同款规格（ABS 花洒头 + 304 不锈钢杆，48–78″）落点。我方售价 = 双人款 Amazon 销量加权中位价。利润率为 Amazon FBA，成本 ¥190（参考价）。")
)
MX_THERMO = (
  MX.render("Amazon 恒温 / 侧喷淋浴系统：顶喷尺寸 × 侧喷数量", f"2026-10 · 卖家精灵 {_hn} 个子体（thermostatic / body jets 词组匹配）",
            _hd[0], _hd[1], _hd[2],
            {"≤10″": {"cells": ["无侧喷"], "price": usd(next(x for x in TH if x["sku"]=="FFS223" and x["tier"]=="mid")["amzPrice"]), "margin": f"FFS223 {_m(_t('FFS223','mid','fba'))}", "cls": _c(_t('FFS223','mid','fba'))},
             "12″": {"cells": ["2–4 个"], "price": usd(next(x for x in TH if x["sku"]=="F00F40" and x["tier"]=="mid")["amzPrice"]), "margin": f"F00F40 {_m(_t('F00F40','mid','fba'))}", "cls": _c(_t('F00F40','mid','fba'))},
             "16″": {"cells": ["6 个及以上"], "price": usd(next(x for x in TH if x["sku"]=="F00F42" and x["tier"]=="mid")["amzPrice"]), "margin": f"F00F42 {_m(_t('F00F42','mid','fba'))}<br>F00F41 {_m(_t('F00F41','mid','fba'))}", "cls": "warn"}},
            mid="thermo", row_label="顶喷尺寸", footnote="顶喷尺寸、侧喷数按标题识别。我方落点：F00F41 / F42 的 400mm 顶喷约 16″；FFS223、F00F40 报价未写顶喷尺寸，暂按 ≤10″、12″ 放置，待采购确认。我方售价 = 对应细分（无侧喷 / 2–4 侧喷 / 6 侧喷+ 恒温款）Amazon 销量加权中位价。利润率为 Amazon FBA。")
)

_br = lambda n: MX.load_meta(os.path.join(HERE, "mkt", n + "_meta.csv"))
_thr = [r for r in MX_ROWS["thermo"] if "thermostatic" in r["t"]]
DUAL_TIER_HTML = MX.tier_bands(MX_ROWS["tandem"], Q["dual"], MX.tagger("tandem", lambda r: [_tdg(r)[1], MX.tandem_cfg(r["t"])]), _br("tandem"))
SAUNA_TIER_HTML = MX.tier_bands([r for r in MX_ROWS["sauna"] if MX.sauna_cap(r["t"]) == "1 人"], Q["sauna_1"], MX.tagger("sauna", lambda r: [MX.sauna_wood(r["t"])]), _br("sauna"))
TH0_TIER_HTML = MX.tier_bands([r for r in _thr if MX.thermo_jets(r["t"]) == "无侧喷"], Q["th_nojet"], MX.tagger("thermo", lambda r: ["顶喷 " + MX.thermo_top(r["t"])]), _br("thermo"))
TH6_TIER_HTML = MX.tier_bands([r for r in _thr if MX.thermo_jets(r["t"]) == "6 个及以上"], Q["th_6"], MX.tagger("thermo", lambda r: ["顶喷 " + MX.thermo_top(r["t"])]), _br("thermo"))
def _fba(sku, t):
    r = next(x for x in TH if x["sku"] == sku and x["tier"] == t); return r["fba"] / r["amzPrice"]
def _maxrmb_th(sku, t):
    r = next(x for x in TH if x["sku"] == sku and x["tier"] == t); return (r["cost"] + r["fba"] - 0.15 * r["amzPrice"]) * 6.8 * 1.13
_hcm = HC[("SMT-HC103", "mid")]; _hch = HC[("SMT-HC103", "high")]
HC_BE = (_hcm["cost"] + _hcm["sea"] + _hcm["fbmShip"]) / (1 - _pct)
HC_MAX_H = (_hch["cost"] + _hch["fbm"] - 0.15 * _hch["amzPrice"]) * 6.8 * 1.13
MX_DATA = json.dumps(MX_ITEMS, ensure_ascii=False).replace('</', '<\\/')
CHANGELOG = json.load(open(os.path.join(HERE, "changelog.json"), encoding="utf-8"))
import datetime as _dt
BUILD_TIME = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
VERSION = f"v{len(CHANGELOG)}"
CHANGELOG_HTML = "".join(f"<li><b>{E(d)}</b> {E(t)}</li>" for d, t in reversed(CHANGELOG))
P = calc["params"]
s1 = S[("SAD6221-1", "mid")]; s1h = S[("SAD6221-1", "high")]
dm = S[("DUAL", "mid")]; dl = S[("DUAL", "low")]

d_l, d_m, d_h = R[("DUAL", "low")], R[("DUAL", "mid")], R[("DUAL", "high")]
d_mm, d_hm = d_m["fba"] / d_m["amzPrice"], d_h["fba"] / d_h["amzPrice"]
s1_h = R[("SAD6221-1", "high")]; hc_h = HC[("SMT-HC103", "high")]
BAR_DUAL = '<div class="bars">' + bar(f"双人淋浴花洒 · Amazon FBA · 按中位价", d_m["amzPrice"], parts_amz(d_m, "fbaShip", "FBA 配送费"), d_m["fba"]) + '</div>'
BAR_SAUNA = '<div class="bars">' + bar("珠三角 SAD6221-1 · ¥6,270", s1_h["amzPrice"], parts_amz(s1_h, "fbmShip", "卡车尾程"), s1_h["fbm"]) + bar("合肥 SMT-HC103 · ¥3,842（包装 +10%）", hc_h["amzPrice"], parts_amz(hc_h, "fbmShip", "卡车尾程"), hc_h["fbm"]) + '</div>'
page = f"""<title>疗愈品类利润摸底</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
/* Layout: single reading column, summary first, then one section per category (market → price tiers → profit) */
:root{{
  --bg:#f6f7f5; --panel:#ffffff; --fg:#1b2420; --muted:#5d6a64; --line:#dde3df; --accent:#1f5f55; --accent-soft:#e3efec;
  --good:#1d7a3e; --good-bg:#e2f3e7; --warn:#8a5a00; --warn-bg:#fbf0d6; --bad:#b3261e; --bad-bg:#fbe5e3; --na:#7b8580; --na-bg:#eef1ef;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --g0:#e1f3ee; --g1:#fbe4ee; --heat:#3aa57f; --mine-bg:#fff4c7; --box:#e8a10a;
  --f-body:"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif; --f-num:"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{
  --bg:#121614; --panel:#1a201d; --fg:#e7ece9; --muted:#9aa7a1; --line:#2c3531; --accent:#6cc2b1; --accent-soft:#1f2f2b;
  --good:#6fd38f; --good-bg:#16301f; --warn:#f0c15a; --warn-bg:#352a10; --bad:#ff8a80; --bad-bg:#3a1a18; --na:#93a09a; --na-bg:#232a27;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --g0:#1d3a33; --g1:#3e2330; --heat:#2f9a73; --mine-bg:#3a3214; --box:#e0a020; color-scheme:dark}}}}
:root[data-theme="dark"]{{
  --bg:#121614; --panel:#1a201d; --fg:#e7ece9; --muted:#9aa7a1; --line:#2c3531; --accent:#6cc2b1; --accent-soft:#1f2f2b;
  --good:#6fd38f; --good-bg:#16301f; --warn:#f0c15a; --warn-bg:#352a10; --bad:#ff8a80; --bad-bg:#3a1a18; --na:#93a09a; --na-bg:#232a27;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --g0:#1d3a33; --g1:#3e2330; --heat:#2f9a73; --mine-bg:#3a3214; --box:#e0a020; color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:15px;line-height:1.65}}
.wrap{{max-width:1080px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;grid-template-columns:minmax(0,1fr);gap:36px}}
h1,h2,h3,h4,h5{{text-wrap:balance;margin:0;line-height:1.3}}
h1{{font-size:28px}} h2{{font-size:21px;padding-bottom:8px;border-bottom:2px solid var(--accent)}} h3{{font-size:17px}} h4{{font-size:16px}} h5{{font-size:12px;letter-spacing:.06em;color:var(--muted);font-weight:500;margin-bottom:6px}}
p{{margin:0}} .sub{{color:var(--muted);font-size:13.5px}}
section{{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;min-width:0}}
.num,.price,.profit,td,.pp,.rng,.bar-h,.lg b{{font-variant-numeric:tabular-nums}}
.verdict{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}}
.vc{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:grid;gap:8px;align-content:start;border-top:4px solid var(--c)}}
.vc.ok{{--c:var(--good)}} .vc.no{{--c:var(--bad)}}
.vc .big{{font-family:var(--f-num);font-size:26px;font-weight:600}}
.vc ul{{margin:0;padding-left:18px;display:grid;gap:4px}}
.mkt{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.mkt article{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:grid;gap:10px;align-content:start;min-width:0}}
.kv{{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:14px}}
.kv dt{{color:var(--muted)}} .kv dd{{margin:0}}
.decision{{background:var(--accent-soft);border-radius:8px;padding:10px 14px;font-size:14px}}
.tiers{{display:grid;gap:12px}}
.tier{{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
.tier header{{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;padding:10px 16px;border-bottom:1px solid var(--line)}}
.rng{{font-family:var(--f-num);font-weight:600;color:var(--accent)}}
.ours{{font-size:12px;background:var(--accent);color:var(--bg);border-radius:20px;padding:1px 10px}}
.tier-b{{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;padding:12px 16px}}
.tier-b>div{{min-width:0}}
@media (max-width:700px){{.tier-b{{grid-template-columns:1fr}}}}
.prods,.feats{{list-style:none;margin:0;padding:0;display:grid;gap:6px;font-size:14px}}
.prods li{{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}}
.ch{{font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 6px}}
.pn{{flex:1 1 180px}} .pp{{font-family:var(--f-num);font-weight:600}} .pm{{font-size:12px;color:var(--muted);flex-basis:100%;padding-left:2px}}
.feats li{{padding-left:14px;position:relative}} .feats li::before{{content:"";position:absolute;left:2px;top:.7em;width:6px;height:6px;border-radius:50%;background:var(--accent)}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}
thead th{{font-size:12.5px;color:var(--muted);font-weight:500;background:var(--bg)}}
tbody tr:last-child>*{{border-bottom:0}}
tbody th{{font-weight:500}}
.cell{{display:flex;gap:10px;align-items:center}}
.price{{color:var(--muted);font-size:13px;min-width:62px}} .profit{{font-family:var(--f-num);font-weight:600;min-width:60px;text-align:right}}
.neg{{color:var(--bad)}} .pos{{color:var(--good)}}
.pill{{display:inline-block;font-size:12px;font-family:var(--f-num);font-weight:600;border-radius:20px;padding:1px 9px}}
.pill.good{{color:var(--good);background:var(--good-bg)}} .pill.warn{{color:var(--warn);background:var(--warn-bg)}} .pill.bad{{color:var(--bad);background:var(--bad-bg)}} .pill.na{{color:var(--na);background:var(--na-bg);font-family:var(--f-body);font-weight:400}}
.note{{font-size:12.5px;color:var(--muted)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media (max-width:760px){{.two{{grid-template-columns:1fr}}}}
.two>*{{min-width:0}}
.bars{{display:grid;gap:18px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.bar{{display:grid;gap:6px}}
.bar-h{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;font-size:13.5px}}
.bar-h span:first-child{{font-weight:500}}
.track{{position:relative;height:22px}}
.fill{{display:flex;gap:2px;height:100%}}
.seg{{height:100%}} .seg:first-child{{border-radius:4px 0 0 4px}} .seg:last-child{{border-radius:0 4px 4px 0}}
.s1{{background:var(--s1)}} .s2{{background:var(--s2)}} .s3{{background:var(--s3)}} .s4{{background:var(--s4)}}
.pricemark{{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--fg)}}
.pricemark span{{position:absolute;top:-17px;left:50%;transform:translateX(-50%);font-size:11px;color:var(--muted);white-space:nowrap}}
.lg{{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:var(--muted)}}
.lg li{{display:flex;gap:5px;align-items:center}} .lg b{{color:var(--fg);font-weight:600;font-family:var(--f-num)}} .lg em{{font-style:normal;display:none}}
.sw{{width:10px;height:10px;border-radius:2px;display:inline-block}}
.callout{{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:12px 16px;display:grid;gap:6px;font-size:14px}}

.rules{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;font-size:13.5px}}
.rules div{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px}}
.rules ul{{margin:6px 0 0;padding-left:18px;display:grid;gap:3px}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}} details>summary{{cursor:pointer;font-weight:500}} details .tw{{margin-top:10px}}
{MX.MX_CSS}
.ver{{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:12.5px;color:var(--muted)}} .vtag{{font-family:var(--f-num);font-weight:600;color:var(--bg);background:var(--accent);border-radius:20px;padding:1px 9px}} .ver details{{flex-basis:100%;padding:6px 10px}} .ver ul{{margin:6px 0 0;padding-left:18px;display:grid;gap:3px}}
.todo{{margin:0;padding-left:20px;display:grid;gap:6px}}
table.mtg td,table.mtg th{{white-space:normal;vertical-align:top;min-width:160px}}
table.mtg tbody th{{white-space:nowrap}}
</style>
<style>
.concl th,.concl td{{white-space:normal;vertical-align:top}}
.concl td:nth-child(2){{white-space:nowrap;font-weight:600}}
.concl .go{{color:var(--good)}} .concl .hold{{color:var(--warn)}} .concl .stop{{color:var(--bad)}}
.plain{{margin:0;padding-left:20px;display:grid;gap:6px;font-size:14.5px}}
.lead{{font-size:15px;max-width:72ch}}
h2{{border-bottom:1px solid var(--line)!important;padding-bottom:6px}}
h3{{margin-top:6px}}
</style>
<div class="wrap">
<header style="display:grid;gap:8px">
  <h1>疗愈拓展品类利润摸底</h1>
  <p class="lead">这次要定的是三条线怎么推进：双人淋浴花洒、恒温花洒系统、单人光波房（红外桑拿房）。售价看 Amazon 同类产品的实际成交分布，成本用采购报价，费用按利润测算台 v1.14 的默认参数算。</p>
  <div class="ver"><span class="vtag">{VERSION}</span><span>更新于 {BUILD_TIME}（北京时间）。这个链接始终是最新版。</span>
    <details><summary>更新记录</summary><ul>{CHANGELOG_HTML}</ul></details></div>
</header>

<section aria-labelledby="c1">
  <h2 id="c1">一、结论和需要拍板的事</h2>
  <div class="tw"><table class="concl"><thead><tr><th>产品线</th><th>建议</th><th>依据（Amazon，按销量加权的价位）</th><th>下一步</th></tr></thead><tbody>
    <tr><th scope="row">双人淋浴花洒</th><td class="go">做，走高配</td>
      <td>市场两头大、中间小：低于 $87 的占月销 42%，高于 $127 的占 40%。按中位价 {usd(d_m['amzPrice'],2)} 卖只有 {_m(d_mm)}；按高位价 {usd(d_h['amzPrice'],2)} 卖有 {_m(d_hm)}。我们对标的 OURBAOFU 卖 $140–190，属于高价带。</td>
      <td>按不锈钢杆 + 手持 / 三头规格，用竞品链接反查供应商，拿正式报价和样品</td></tr>
    <tr><th scope="row">恒温花洒 FFS223</th><td class="go">做</td>
      <td>同类（无侧喷恒温款）中位价 $250 时 {_m(_fba('FFS223','mid'))}，$360 时 {_m(_fba('FFS223','high'))}</td>
      <td>拿实测箱规、毛重，确认报价是否含税</td></tr>
    <tr><th scope="row">恒温花洒 F00F40</th><td class="hold">先确认定位</td>
      <td>同类（2–4 侧喷）中位价 $400 时 {_m(_fba('F00F40','mid'))}；但这类产品 Amazon 每月只卖 49 件，价格参考性弱</td>
      <td>确认它到底对标哪类产品，再决定</td></tr>
    <tr><th scope="row">恒温花洒 F00F41 / F00F42</th><td class="hold">谈价后再定，只留 F00F42</td>
      <td>同类（6 侧喷及以上）中位价 $630 时只有 {_m(_fba('F00F41','mid'))} / {_m(_fba('F00F42','mid'))}。F00F42 比 F00F41 便宜 ¥200，还多一路功能</td>
      <td>F00F42 含税谈到约 ¥{round(_maxrmb_th('F00F42','mid')/50)*50:,.0f}</td></tr>
    <tr><th scope="row">单人光波房</th><td class="stop">暂不下单</td>
      <td>Amazon 单人款主要卖 $800–1,300。按 $1,300 算，珠三角报价亏 {_m(-s1_h['fbm']/s1_h['amzPrice'])}，合肥报价亏 {_m(-hc_h['fbm']/hc_h['amzPrice'])}。海运 + 尾程 + 平台费用就占了售价约 74%，问题在物流和渠道，不只是采购价。Lowe's 自发货按 $2,089 算，合肥款能赚 {_m(hc_h['plat']['lowesSC']['margin'])}</td>
      <td>让合肥厂报 1.35 米矮款 + 纸箱减重方案；按 Lowe's / Home Depot 价格重算</td></tr>
  </tbody></table></div>
  <div class="two">
    <div><h3>需要老板拍板</h3><ol class="plain">
      <li>双人花洒按高配推进，FFS223 同步推进，拿报价和样品</li>
      <li>光波房暂不下单，给两周拿矮款和减重包装方案，下次会上定做不做；渠道以 Lowe's / Home Depot 为主</li>
      <li>认证预算：花洒 cUPC 首次约 ¥10 万以上，光波房整机 ETL，都要用我们自己的公司主体申请</li>
      <li>F00F41 / F00F42 只留 F00F42，按约 ¥{round(_maxrmb_th('F00F42','mid')/50)*50:,.0f} 去谈</li></ol></div>
    <div><h3>两周内要做的</h3><div class="tw"><table><thead><tr><th>谁</th><th>做什么</th></tr></thead><tbody>
      <tr><td>采购</td><td style="white-space:normal">双人花洒高配款：反查供应商，拿报价、样品、实测箱规</td></tr>
      <tr><td>采购</td><td style="white-space:normal">FFS223、F00F42：实测箱规和毛重，报价是否含税</td></tr>
      <tr><td>采购</td><td style="white-space:normal">合肥厂：1.35 米矮款、碳晶板配置、纸箱减重方案，跌落测试结果，一柜装多少台</td></tr>
      <tr><td>合规</td><td style="white-space:normal">工厂现有认证能不能转到我们主体，不能的话费用和周期</td></tr>
      <tr><td>数据</td><td style="white-space:normal">拿到新报价后重算；光波房交叉表改用详情页材质</td></tr></tbody></table></div></div>
  </div>
</section>

<section aria-labelledby="c2">
  <h2 id="c2">二、前面四次会议定了什么</h2>
  <div class="tw"><table class="mtg"><thead><tr><th>会议</th><th>定了什么</th><th>这次的对应</th></tr></thead><tbody>
    <tr><th scope="row">6/25 开品方向</th><td>从人群出发：仪式疗愈型最多，变美型约 35%，健康投资型约 10%。淋浴和泡澡是最重要的场景，水和光是载体</td><td>花洒走水，光波房走光，都在这个方向里</td></tr>
    <tr><th scope="row">7/17 筛选规则</th><td>用积分卡（体量、进入难度、竞争、场景延展），不做 30 美元以下的小件，收敛到 1–3 个方向</td><td>三条线都远高于 30 美元</td></tr>
    <tr><th scope="row">8/6 二选一</th><td>排除马桶、浴缸、便携桑拿。用体量、头部垄断、评分、粗略利润、品牌锚点五个维度在光波房和花洒里选。光波房试水价定在 Amazon $1,000–1,500</td><td>这次补上“粗略利润”：花洒能赚，光波房在 $1,000–1,500 按现有报价做不出利润</td></tr>
    <tr><th scope="row">10/10 供应链调研</th><td>光波房：珠三角单人房含税 ¥6,000–7,000，皖徐不含税 ¥3,400–4,000；Amazon 主流款高约 1.35 米。花洒：cUPC 首次约 ¥10 万+，Amazon 要求认证主体和店铺一致；行业转向不锈钢；先用竞品链接反查供应商、先选工厂现有带认证的款</td><td>两家光波房报价分别对应这两档价位；花洒的推进方式照会上定的走</td></tr>
  </tbody></table></div>
  <p class="note">来源：飞书智能纪要（AI 生成，个别数字以原始录音为准）。</p>
</section>

<section aria-labelledby="c3">
  <h2 id="c3">三、市场概况</h2>
  <div class="mkt">
    <article><h3>花洒</h3>
      <dl class="kv">
        <dt>规模</dt><dd>美国花洒市场 $20 亿（2024），年增 7.1%；手持款增长最快（7.8%），线上渠道年增 8.0%</dd>
        <dt>搜索</dt><dd>rain shower head 每月 9.3 万；双人相关词（tandem、dual for two、couples）合计约 2.3 万，2022 年前几乎没有，今年比去年 +11%</dd>
        <dt>竞争</dt><dd>没有大牌垄断，以中国卖家为主；双人款只有 BOONA 做成了品牌</dd>
      </dl></article>
    <article><h3>光波房（红外桑拿房）</h3>
      <dl class="kv">
        <dt>规模</dt><dd>美国桑拿市场 $2.06 亿（2025），年增 5.4%；红外类增长最快，约 7.5%</dd>
        <dt>搜索</dt><dd>home sauna 每月 5.6 万；近 12 个月 infrared sauna 搜索热度 +140%</dd>
        <dt>热度</dt><dd>Reddit 讨论量是花洒的 9 倍，更适合做品牌锚点</dd>
        <dt>渠道</dt><dd>Amazon 上 82% 是便携帐篷款；木质房主要在 Wayfair、Home Depot、Lowe's，中位价 $3,300 / $2,570 / $1,999</dd>
      </dl></article>
  </div>
  <p class="note">来源：Grand View Research、Mordor Intelligence、卖家精灵、Google Trends、四渠道桑拿属性报告、Reddit 讨论分析。</p>
</section>

<section aria-labelledby="c4">
  <h2 id="c4">四、双人淋浴花洒</h2>
  <h3>市场格局：按可调宽度和材质</h3>
  {MX_DUAL}
  <h3>每个价位卖的是什么</h3>
  <p class="sub">按 Amazon 销量加权，把价格分成低 / 中 / 高三段，每段列卖得最好的产品，以及这一段里常见的配置（百分比是该配置占这一段月销的比例）。</p>
  {DUAL_TIER_HTML}
  <h3>利润</h3>
  <div class="two">{price_grid("DUAL")}<div class="callout"><b>成本怎么算的</b><span>采购 ¥190（品类筛选表里的参考价，还没拿到正式报价），约 $27.94；海运 $4.03；FBA 配送 $12.04（包装按 70×22×12cm、4kg 估算）；平台费用占售价 34%（佣金 15%、广告 10%、退款 8%、汇损 1%）。</span></div></div>
  {profit_table("DUAL", CH)}
  {BAR_DUAL}
  <ul class="plain">
    <li>中位价 {usd(d_m['amzPrice'],2)} 时要赚 15%，采购价最多 ¥{S[('DUAL','mid')]['amzFBM']['maxCostRMB']}。现在用的 ¥190 余量很小，正式报价一定要压在这以内。</li>
    <li>高价带（≥ $127）占月销 40%，以 BOONA、OURBAOFU、JFJIARUI 为主，多是不锈钢杆、双头或带手持。我们按这一档的配置做，才有 35% 以上。</li>
    <li>Home Depot、Wayfair、Lowe's 上真正的双人款很少，价格只作参考。</li></ul>
</section>

<section aria-labelledby="c5">
  <h2 id="c5">五、恒温花洒系统（采购已报价的 4 款）</h2>
  <p class="lead">采购报价：FFS223 ¥640、F00F40 ¥1,289、F00F42 ¥2,600、F00F41 ¥2,800（按含税处理）。包装尺寸和毛重是估算的，等采购给实测数据。</p>
  <h3>市场格局：按顶喷尺寸和侧喷数量</h3>
  {MX_THERMO}
  <h3>每个价位卖的是什么</h3>
  <p class="sub">无侧喷恒温款（对标 FFS223）</p>
  {TH0_TIER_HTML}
  <p class="sub">6 个及以上侧喷的恒温款（对标 F00F41 / F00F42）</p>
  {TH6_TIER_HTML}
  <p class="note">F00F40 对应的 2–4 侧喷恒温款，Amazon 每月只卖 49 件、9 个链接，不单独列。</p>
  <h3>利润</h3>
  {th_summary()}
  <p class="note">Amazon 低 / 中 / 高 = 同类恒温款按销量加权的 25 / 50 / 75 分位。其他渠道是搜索页标价，只作参考。</p>
  <ul class="plain">
    <li>FFS223：卖到同类中位价 $250 有 {_m(_fba('FFS223','mid'))}，卖到 $360 有 {_m(_fba('FFS223','high'))}。$180 以下就只剩个位数，不打低价。</li>
    <li>F00F40：中位价时 {_m(_fba('F00F40','mid'))}，勉强过线，但同类几乎没有量，要先想清楚卖给谁。</li>
    <li>F00F41 / F00F42：中位价 $630 时 {_m(_fba('F00F41','mid'))} / {_m(_fba('F00F42','mid'))}，卖到 $790 也只有 {_m(_fba('F00F41','high'))} / {_m(_fba('F00F42','high'))}。只留 F00F42，含税谈到约 ¥{round(_maxrmb_th('F00F42','mid')/50)*50:,.0f}。</li>
    <li>风险：恒温和复杂水路的售后风险高（10/10 会上提过）；cUPC 认证约 ¥10 万以上，还没算进单件成本。</li></ul>
  {"".join(f"<details><summary>{s['id']} 各渠道明细</summary>{th_detail(s['id'])}</details>" for s in TS)}
</section>

<section aria-labelledby="c6">
  <h2 id="c6">六、单人光波房（红外桑拿房）</h2>
  <h3>市场格局：按人数和木材</h3>
  {MX_SAUNA}
  <h3>每个价位卖的是什么（Amazon 单人款）</h3>
  {SAUNA_TIER_HTML}
  <h3>两家报价</h3>
  <div class="tw"><table><thead><tr><th>型号</th><th>厂家</th><th>报价</th><th>规格</th><th>包装</th></tr></thead><tbody>
    <tr><td>SAD6221-1</td><td>中山（珠三角）</td><td>¥6,270 含税</td><td style="white-space:normal">800×900×2100mm，加拿大铁杉，远红外云母板，8mm 玻璃，负离子，机械面板，无蓝牙 / 彩光 / 红光</td><td style="white-space:normal">3 箱，0.76m³，220kg</td></tr>
    <tr><td>SMT-HC103</td><td>合肥</td><td>¥3,842 含税</td><td style="white-space:normal">900×900×1900mm，铁杉，陶瓷加热，蓝牙 + 双音箱，氧吧，阅读灯</td><td style="white-space:normal">4 箱，按要求各边加 10%：1.14m³，121kg</td></tr>
    <tr><td>SAD6221-2</td><td>中山（珠三角）</td><td>¥8,618 含税</td><td style="white-space:normal">900×1200×2100mm，1–2 人款，配置同 SAD6221-1</td><td style="white-space:normal">3 箱，0.89m³，250kg</td></tr>
  </tbody></table></div>
  <h3>为什么两家都没利润</h3>
  <p class="lead">按 Amazon 单人款 75 分位 $1,300、自发货算：</p>
  {BAR_SAUNA}
  <ul class="plain">
    <li>合肥款采购比珠三角便宜 $316，但箱子更大，海运 + 尾程反而要 $518，占售价 40%。</li>
    <li>平台费用再占 34%。两项加起来 74%，采购价就算是 0，最多也只有 26%。</li>
    <li>Amazon 单人款主要卖 $800–1,300，价格上不去。8/6 定的试水价 $1,000–1,500 已经在市场上沿。</li></ul>
  <h3>各渠道利润（合肥款 SMT-HC103）</h3>
  {wx_table()}
  <ul class="plain">
    <li>Lowe's、Home Depot 上木质房价格高得多：Lowe's 自发货按 $2,089 算，合肥款能赚 {_m(hc_h['plat']['lowesSC']['margin'])}；Home Depot 按 $1,799 算是 {_m(hc_h['plat']['hd']['margin'])}。这几个渠道没有销量数据，价格是搜索页标价。</li>
    <li>要稳定做到 15%，两件事都要做：一是降物流，Amazon 主流单人款高约 1.35 米，我们是 1.9–2.1 米、110–220kg；二是渠道以 Lowe's / Home Depot 为主，配置补到碳晶板、彩光、红光，撑住 $1,800–2,100。</li>
    <li>Amazon 差评集中在“加热不够”。用好的碳晶板（每套 ¥1,000 以上）加 5–6 年质保，是讲得通的卖点。</li></ul>
  <details><summary>SAD6221-1 / SAD6221-2 各渠道明细</summary>
    <h4>SAD6221-1</h4>{price_grid("SAD6221-1")}{profit_table("SAD6221-1", [CH[1], CH[0]] + CH[2:])}
    <h4>SAD6221-2</h4>{price_grid("SAD6221-2")}{profit_table("SAD6221-2", [CH[1], CH[0]] + CH[2:])}
    <h4>SAD6221-1 保本价和最高采购价</h4>{need_table("SAD6221-1", [CH[1], CH[2], CH[3], CH[4], CH[5]])}
    <p class="note">“无解”：采购价为 0 也到不了 15%。</p></details>
</section>

<section aria-labelledby="c7">
  <h2 id="c7">七、测算口径和待确认</h2>
  <div class="rules">
    <div><b>价格</b><ul>
      <li>Amazon：卖家精灵 2026-10 子体月销，按销量加权取 25 / 50 / 75 分位，作为低 / 中 / 高价位</li>
      <li>Home Depot、Lowe's、Wayfair：没有逐条销量，用 2026-11-13 搜索页标价参考</li>
      <li>交叉表的尺寸、材质、配置按标题和详情页识别</li></ul></div>
    <div><b>费用（利润测算台 v1.14 默认）</b><ul>
      <li>汇率 {P['rate']}；Amazon 佣金 {P['comm']}%、广告 {P['promo']}%、退款 {P['refund']}%、汇损 {P['fx']}%</li>
      <li>含税报价 ÷ 1.{P['tax']} ÷ 汇率；花洒参考价按未税</li>
      <li>海运：整柜 ¥100,891 / 68m³ 按体积分摊；卡车尾程按 $92.5 + $0.43/lb + $54/m³ 估</li>
      <li>Home Depot ÷ 1.6、Lowe's VC ÷ 1.7、Wayfair ÷ 2.1 换算结算价，再扣各自费率</li></ul></div>
    <div><b>待确认</b><ol class="todo">
      <li>双人花洒正式报价（中位价下上限 ¥{S[('DUAL','mid')]['amzFBM']['maxCostRMB']}）和实测包装</li>
      <li>恒温 4 款的实测包装、毛重，报价是否含税</li>
      <li>合肥厂矮款、减重包装、碳晶板配置的报价，跌落测试结果，一柜装多少台</li>
      <li>光波房报价是否含税；ETL 认证费用和周期</li>
      <li>花洒工厂现有认证能否转到我们主体</li></ol></div>
  </div>
</section>
<script type="application/json" id="mxdata">{MX_DATA}</script>
{MX.MX_JS}
</div>
"""
open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(page)

# ---------------- import file for 利润测算台 v1.14（打开方案 .json） ----------------
import random, string
uid = lambda: "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
prods = []
for s in scen["skus"]:
    for t, tn in TIERS:
        tp = s["tiers"][t]
        prices = {k: {"promo": tp[m]} for k, m in [("lowesVC", "lw"), ("lowesSC", "lw"), ("hd", "hd"), ("wf", "wf")] if tp[m]}
        prods.append({"id": uid(), "name": f'{s["id"]} {tn}', "desc": s["name"], "supplier": "", "category": "其他", "peak": "非旺季",
                      "price": tp["amz"], "cost": s["cost"], "costCur": s["costCur"], "adj": 0, "pack": s["pack"], "prices": prices,
                      "pkgs": [{"l": g[0], "w": g[1], "h": g[2], "kg": g[3]} for g in s["pkgs"]]})
json.dump({"products": prods}, open(os.path.join(HERE, "疗愈品类_利润测算台导入.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", len(page))

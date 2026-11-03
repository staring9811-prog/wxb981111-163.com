"""工具：评论 VP 追踪（FLOW-16）与利润测算（FLOW-17、FLOW-18）。
- FLOW-16：Bright Data / Apify 用假服务；导出与原工具（tools/评论月度VP追踪器/reviewkit）对同一批明细的导出逐格比对。
- FLOW-17：利润数字的基准由原工具 tools/利润测算台/index.html 的 JS 在 node 里算出，与并入版 engine.js 逐项比对。"""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

import decision_seed as ds
from conftest import login_as, make_user
from pdt import costgate, services
from pdt.config import PROJECT_DIR
from pdt.db import session
from pdt.models import Budget, Card, CostRecord, Job, ProfitPlan

J = {"accept": "application/json"}
TOOL = PROJECT_DIR / "tools" / "评论月度VP追踪器"
PROFIT_HTML = PROJECT_DIR / "tools" / "利润测算台" / "index.html"
ENGINE = Path(__file__).resolve().parent.parent / "pdt" / "static" / "profit" / "engine.js"


# ================================================================ FLOW-16 评论 VP 追踪
N_PROD = 12
BADGES = ["Verified Purchase", "Verified Purchase", "Incentivized Review", "Wayfair Professional", "Verified Purchase"]


def _reviews(i):
    """第 i 个商品的评论：2026-01 至 2026-10 每月 1 条（徽章轮换）+ 2026-11 未完整月 1 条 + 2025-12 窗口外 1 条。"""
    out = []
    for m in range(1, 11):
        out.append(dict(reviewId=f"wf{i:02d}-{m:02d}", date=f"{m:02d}/15/2026", rating=(m % 5) + 1, text=f"Vanity review {m}", badge=BADGES[(i + m) % 5]))
    out.append(dict(reviewId=f"wf{i:02d}-11", date="11/02/2026", rating=4, text="new", badge="Verified Purchase"))
    out.append(dict(reviewId=f"wf{i:02d}-00", date="12/20/2025", rating=5, text="old", badge="Verified Purchase"))
    return list(reversed(out))  # 原样按最新在前


def _expected_vp():
    """期望值由测试数据直接数出：窗口 2026-01-01 至 2026-10-31 内 Verified Purchase 计 VP，其余徽章计非 VP。"""
    vp = sum(1 for i in range(N_PROD) for m in range(1, 11) if BADGES[(i + m) % 5] == "Verified Purchase")
    return vp, N_PROD * 10 - vp


class FakeBD:
    def __init__(self):
        self.calls = []

    def fetch(self, url, poll=15, max_wait=1200):
        self.calls.append(url)
        cards = []
        for i in range(30):
            meta = json.dumps({"metadata": {"displayListingId": f"W1000{i:03d}", "firstPriceValue": 229 + i, "averageRating": 4.2, "totalReviewCount": 120}})
            cards.append(f'<div data-tracking-metadata="{html.escape(meta)}" data-clio-id="ListingCardContents::{i}">'
                         f'<a href="https://www.wayfair.com/bed-bath/pdp/latitude-run-30-single-bathroom-vanity-w1000{i:03d}.html">x</a></div>')
        return 200, ("<html>" + "".join(cards) + "</html>").encode()


class FakeApify:
    def __init__(self, pause_first=False):
        self.calls = []
        self.pause_first = pause_first

    def run(self, actor, run_input, max_charge_usd=3, timeout_s=3600, poll=20):
        self.calls.append([u.split("-w")[-1].split(".")[0].upper() for u in run_input["urls"]])
        if self.pause_first and len(self.calls) == 1:  # 模拟 wen 在第一批进行中点“暂停”
            with session() as s:
                jid = s.query(Job).filter_by(kind="vp_collect", status="running").one().id
            costgate.pause(jid)
        items = []
        for u in run_input["urls"]:
            sku = "W" + u.split("-w")[-1].split(".")[0]
            items.append(dict(sku=sku, name=f"Latitude Run 30'' Single Bathroom Vanity {sku}", brand="Latitude Run", reviews=_reviews(int(sku[-3:]))))
        return items, 0.05


@pytest.fixture()
def vp(wen, monkeypatch):
    from pdt.core import vp as vpcore
    from pdt.reviewkit import wayfair
    monkeypatch.setattr(wayfair.reviews_batch, "__defaults__", (10, 1))  # 每批 10 个、串行，便于在两批之间暂停
    vpcore.projects()  # 首次打开：复制原工具全部项目设置
    cfg = vpcore.load("浴室柜_2026")
    assert len(cfg["entries"]) == 6 and cfg["window"] == {"start": "2026-01-01", "full_end": "2026-10-31", "include_partial": True}
    cfg["entries"] = [dict(e, top_n=N_PROD) for e in cfg["entries"] if e["name"] == "Wayfair主类目"]
    r = wen.post("/tools/vp/project", data={"cfg": json.dumps(cfg, ensure_ascii=False)}, headers=J)
    assert r.json()["name"] == "浴室柜_2026"
    services.save_secret("brightdata", "bd-测试密钥-7f3a")
    services.save_secret("apify", "apify-测试密钥-k29Q")
    bd = FakeBD()
    services.set_fake("brightdata", bd)
    return wen, bd, vpcore


def _job(wen, kind):
    j = wen.post("/jobs/estimate", data={"kind": kind, "target": "vp:浴室柜_2026"}).json()
    assert j["status"] == "estimated", j
    return j


def test_flow16_four_steps_pause_resume_and_same_export_as_original(vp, tmp_path):
    """FLOW-16：① 采集列表 → ② 评估费用 → ③ 采集评论（中途暂停后继续，不重复采集）→ ④ 导出 Excel；调用使用设置页密钥，费用进同一费用记录；
    导出的 VP / 非 VP 与原工具对同一批明细的导出一致（Wayfair 只有 Verified Purchase 计 VP）。"""
    wen, bd, vpcore = vp
    ap = FakeApify(pause_first=True)
    services.set_fake("apify", ap)
    page = wen.get("/tools/vp?name=浴室柜_2026").text
    for step in ("① 采集列表", "② 评估费用", "③ 采集评论", "④ 导出 Excel"):
        assert step in page
    assert "Bright Data 已连接" in page and "···· 7f3a" in page and "1. 项目与时间窗" in page and "5. 本项目预算（美元）" in page
    j = _job(wen, "vp_lists")
    assert bd.calls == []  # 先确认费用
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done"
    assert len(bd.calls) == 1
    est = wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J).json()
    assert est["平台"]["Wayfair"]["商品数"] == N_PROD and est["合计"]["Apify费用"] > 0
    j = _job(wen, "vp_collect")
    assert ap.calls == []
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "paused" and len(ap.calls) == 1 and len(ap.calls[0]) == 10  # 第一批 10 个已采并保存
    j = wen.post(f"/jobs/{j['id']}/confirm").json()  # 继续
    assert j["status"] == "done" and len(ap.calls) == 2 and len(ap.calls[1]) == 2  # 只采剩下 2 个，不重复
    with session() as s:
        recs = {(r.service, r.amount) for r in s.query(CostRecord)}
        assert ("brightdata", 0.0015) in recs and ("apify", 0.05) in recs
        assert s.query(CostRecord).filter_by(service="apify").count() == 2
    st = vpcore.state("浴室柜_2026")
    assert st["progress"]["Wayfair"] == [N_PROD, N_PROD] and st["ledger"]["apify_wayfair_usd"] == 0.1
    files = wen.post("/tools/vp/export?name=浴室柜_2026", headers=J).json()["files"]
    mine = vpcore.rk_ctx("浴室柜_2026").path("exports", next(f for f in files if f.startswith("Wayfair")))
    # 原工具对同一批明细导出
    sys.path.insert(0, str(TOOL))
    try:
        from reviewkit import common as o_common, export as o_export
        octx = o_common.Ctx(vpcore.load("浴室柜_2026"), data_dir=vpcore.rk_ctx("浴室柜_2026").data)
        theirs = str(tmp_path / "原工具_Wayfair.xlsx")
        o_export.export(octx, "Wayfair", theirs)
    finally:
        sys.path.remove(str(TOOL))
    a, b = load_workbook(mine), load_workbook(theirs)
    assert a.sheetnames == b.sheetnames == ["月度趋势", "入口月度汇总", "商品", "评论明细"]
    for name in a.sheetnames:
        assert [list(r) for r in a[name].iter_rows(values_only=True)] == [list(r) for r in b[name].iter_rows(values_only=True)], name
    ws = a["入口月度汇总"]
    head = [c.value for c in ws[1]]
    row = [c.value for c in ws[2]]
    vp_n, non = _expected_vp()
    assert row[head.index("完整月 VP合计")] == vp_n and row[head.index("完整月 非VP合计")] == non
    assert row[head.index("2026-11（未完整） 合计")] == N_PROD  # 未完整月单列


def test_flow16_monthly_cap_stops_and_keeps_data(vp):
    """FLOW-16：系统设置页 Apify 月度上限低于本次费用 → 达到上限即停止，已采数据保留；调高上限后续跑不重复。"""
    wen, bd, vpcore = vp
    ap = FakeApify()
    services.set_fake("apify", ap)
    with session() as s:
        s.add(Budget(service="apify", cap=0.055, unit="usd"))
    j = _job(wen, "vp_lists")
    wen.post(f"/jobs/{j['id']}/confirm")
    wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J)
    j = _job(wen, "vp_collect")
    assert j["estimate"]["warnings"]  # 预计超过本月上限
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "stopped_cap" and len(ap.calls) == 1
    raw = Path(vpcore.rk_ctx("浴室柜_2026").path("wayfair", "apify"))
    assert len(list(raw.glob("*.json"))) == 10  # 第一批 10 个商品的评论已保存（原工具的采集缓存），续跑不再调用
    assert "已达上限，已采数据已保存" in wen.get("/tools/vp?name=浴室柜_2026").text
    with session() as s:
        s.get(Budget, "apify").cap = 60
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done" and len(ap.calls) == 2 and len(ap.calls[1]) == 2


def test_flow16_project_budget_either_first(vp):
    """AC-F23-02：原工具项目自身预算也保留，与月度上限“任一先到即停”。"""
    wen, bd, vpcore = vp
    ap = FakeApify()
    services.set_fake("apify", ap)
    cfg = vpcore.load("浴室柜_2026")
    cfg["budget"]["apify_wayfair_usd"] = 0.05
    wen.post("/tools/vp/project", data={"cfg": json.dumps(cfg, ensure_ascii=False)}, headers=J)
    wen.post(f"/jobs/{_job(wen, 'vp_lists')['id']}/confirm")
    wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J)
    wen.post(f"/jobs/{_job(wen, 'vp_collect')['id']}/confirm")
    st = vpcore.state("浴室柜_2026")
    assert len(ap.calls) == 1 and len(list(Path(vpcore.rk_ctx("浴室柜_2026").path("wayfair", "apify")).glob("*.json"))) == 10
    assert any("达到预算上限，已停止" in line for line in st["log"]) and st["ledger"]["apify_wayfair_usd"] == 0.05


def test_flow16_vp_rules_unchanged_from_original():
    """AC-F23-01：口径不变——采集与导出代码（VP 判定、去重、导出、估算、品类筛选）与原工具逐字相同，只改了密钥与记账（services.py）和停止传递（pipeline.py）。"""
    mine = Path(__file__).resolve().parent.parent / "pdt" / "reviewkit"
    for f in ("hdp.py", "lowes.py", "wayfair.py", "export.py", "estimate.py", "classify.py", "common.py"):
        assert (mine / f).read_bytes() == (TOOL / "reviewkit" / f).read_bytes(), f
    assert 'VP" if badge == "Verified Purchase" else "non_VP"' in (mine / "wayfair.py").read_text(encoding="utf-8")


def test_vp_page_operator_only(client):
    make_user("lixiaomei", "李晓梅", "readonly")
    ro = login_as(client, "lixiaomei", "密码-123456")
    assert ro.get("/tools/vp").status_code == 403


# ================================================================ FLOW-17 / 18 利润测算
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="需要 node 计算原工具基准")


def _calc_blocks(src: str) -> list:
    """原工具脚本里的默认参数段与计算段（中间的状态初始化两行是并入时唯一改动的地方）。"""
    a = src.index("/* ---------------- defaults ---------------- */")
    b = src.index("/* ---------------- state ---------------- */")
    c = src.index("/* ---------------- calculation (mirrors the original workbook) ---------------- */")
    d = src.index("/* ---------------- bulk: set platform list prices from the Amazon price ---------------- */")
    return [src[a:b], src[c:d]]


def _node(code: str, tmp_path, name):
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    r = subprocess.run([NODE, str(p)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


HARNESS = """
var window = {}; var PDT = undefined; var localStorage = {getItem: function(){ return null; }, setItem: function(){}};
%s
var R = products.map(function(p){ var r = calcProduct(p); return {name: p.name, cost: r.cost, price: r.price, sc: r.sc, fbmShip: r.fbmShip, cgShip: r.cgShip, fbaShip: r.fbaShip,
  plat: Object.fromEntries(Object.entries(r.plat).map(function(kv){ var x = kv[1]; return [kv[0], {list: x.list, promo: x.promo, sc: x.sc}]; })),
  rows: chanList().map(function(ch){ var v = chanVal(r, ch, 0); return {channel: ch.name, profit: v.ok ? v.profit : null}; })}; });
console.log(JSON.stringify({params: P, products: products, R: R}));
"""


def _script(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        s = s[s.index('"use strict";'):s.rindex("</script>")]
    return s


def _head(src: str) -> str:
    """默认参数 + 状态 + 计算 + 渠道列表（chanList / chanVal），足够在 node 里算利润表。"""
    a = src.index("/* All visible channels in one list")
    b = src.index("const DETAIL_OPTS")
    return src[:src.index("/* ---------------- bulk")] + src[a:b]


@needs_node
def test_flow17_profit_numbers_match_original_tool(tmp_path, wen, client):
    """FLOW-17：每个利润数字与原工具基准一致（原 index.html 的 JS 在 node 里算同一组输入）；原工具导出的方案 .json 可导入；
    方案存服务端，另一台电脑（只读账号）能看到同一份。"""
    orig, eng = _script(PROFIT_HTML), _script(ENGINE)
    for blk in _calc_blocks(orig):
        assert blk in eng  # 默认参数与计算逻辑逐字保留
    base = _node(HARNESS % _head(orig), tmp_path, "orig.js")
    got = _node(HARNESS % _head(eng), tmp_path, "mine.js")
    assert got["R"] == base["R"] and len(base["R"]) == 5
    fbm = base["R"][0]["sc"][0]["fbm"]
    assert isinstance(fbm, float) and base["R"][0]["name"] == "24寸 单包"
    # 原工具导出的方案 .json（格式 {version, params, products}）导入为服务端方案
    js = json.dumps({"version": 1, "params": base["params"], "products": base["products"]}, ensure_ascii=False)
    r = wen.post("/tools/profit/import", files={"file": ("利润测算方案_20261101.json", js.encode("utf-8"), "application/json")})
    assert r.status_code == 200 and r.json()["count"] == 5 and r.json()["name"] == "利润测算方案_20261101"
    pid = r.json()["id"]
    assert wen.post("/tools/profit/import", files={"file": ("坏.json", b"{bad", "application/json")}).status_code == 400
    # 另一台电脑、只读账号：看到同一份方案，页面只读
    make_user("lixiaomei", "李晓梅", "readonly")
    ro = login_as(TestClient(client.app), "lixiaomei", "密码-123456")
    items = ro.get("/tools/profit/plans").json()["items"]
    assert [x["id"] for x in items] == [pid] and items[0]["products"] == base["products"] and items[0]["by"] == "wen"
    page = ro.get(f"/tools/profit?plan={pid}").text
    assert '"readonly": true' in page and "/static/profit/engine.js" in page and "导入报价表" in page and "利润测算表" in page and "历史库" in page
    assert ro.post("/tools/profit/plans", json={"name": "x", "products": [{}]}).status_code == 403
    # 历史库：保存新版本、改名、删除
    n2 = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "params": base["params"], "products": base["products"][:2]}).json()
    assert n2["count"] == 2
    assert wen.post(f"/tools/profit/plans/{n2['id']}", json={"name": "树脂一体30寸_v2"}).json()["name"] == "树脂一体30寸_v2"
    wen.post(f"/tools/profit/plans/{n2['id']}/delete")
    assert [x["id"] for x in wen.get("/tools/profit/plans").json()["items"]] == [pid]
    assert Path(__file__).resolve().parent.parent.joinpath("pdt/static/vendor/xlsx.full.min.js").exists()  # 导出 Excel 不依赖外网


@needs_node
def test_flow18_card_prefill_and_writeback(tmp_path, wen):
    """FLOW-18：从决策卡“测算利润”打开时预填尺寸与拟定售价；保存并回写后卡片“钱”一节显示各渠道单件利润、利润率、保本价；方案改售价再保存，卡片随之更新。"""
    ds.seed_all()
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    with session() as s:
        price = s.get(Card, cid).narrative["price"]
    assert f'href="/tools/profit?card={cid}"' in wen.get(f"/cards/{cid}").text
    page = wen.get(f"/tools/profit?card={cid}").text
    pdt = json.loads(page.split("window.PDT = ")[1].split(";</script>")[0])
    assert pdt["card"]["price"] == price and pdt["card"]["size"] == "30″" and pdt["card"]["id"] == cid
    assert "已从卡片带入：尺寸 30″、拟定售价 $" + str(price) in page
    assert "保存并回写决策卡" in page
    head = _head(_script(ENGINE))

    def result(p):
        prod = {"id": "c1", "name": "30″ 树脂（决策卡）", "desc": "", "supplier": "", "category": "家具", "peak": "非旺季", "price": p, "cost": 130,
                "costCur": "USD", "adj": 0, "prices": {}, "pkgs": [{"l": 93, "w": 57, "h": 40, "kg": 47}]}  # 原工具示例“30寸 单包”的包装
        code = "var window = {PDT: {init: {products: [%s]}}}; var PDT = window.PDT; var localStorage = {getItem: function(){ return null; }, setItem: function(){}};\n%s\n" % (json.dumps(prod), head)
        code += """var r = calcProduct(products[0]);
console.log(JSON.stringify({product: products[0].name, rows: chanList().map(function(ch){ var v = chanVal(r, ch, 0);
  if (ch.amz) return {channel: ch.name, price: r.price, profit: v.profit, margin: v.profit / r.price, breakeven: null};
  var x = r.plat[ch.plat]; return {channel: ch.name, price: x.promo, profit: x.sc[0].promo.profit, margin: x.sc[0].promo.margin, breakeven: x.sc[0].breakeven}; })}));"""
        return _node(code, tmp_path, f"r{p}.js")

    r1 = result(price)
    plan = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "params": {}, "products": [{"name": "30″ 树脂（决策卡）"}], "card_id": cid, "result": r1}).json()
    sec8 = html.unescape(wen.get(f"/cards/{cid}").text.split('id="s8"')[1].split('id="s9"')[0])
    for row in r1["rows"]:
        assert row["channel"] in sec8
        p = row["profit"]
        assert f"{'−' if p < 0 else ''}${abs(p):.2f}" in sec8 and f"{row['margin'] * 100:.1f}%" in sec8
    assert "方案“树脂一体30寸_v1”" in sec8 and "随方案更新" in sec8
    fbm1 = next(r for r in r1["rows"] if r["channel"] == "Amazon FBM")["profit"]
    r2 = result(price + 30)
    wen.post(f"/tools/profit/plans/{plan['id']}", json={"products": [{"name": "30″ 树脂（决策卡）"}], "result": r2})
    sec8 = html.unescape(wen.get(f"/cards/{cid}").text.split('id="s8"')[1].split('id="s9"')[0])
    fbm2 = next(r for r in r2["rows"] if r["channel"] == "Amazon FBM")["profit"]
    money = lambda v: f"{'−' if v < 0 else ''}${abs(v):.2f}"
    assert fbm2 > fbm1 and money(fbm2) in sec8 and money(fbm1) not in sec8
    with session() as s:
        assert s.get(Card, cid).profit_plan_id == plan["id"] and s.get(ProfitPlan, plan["id"]).card_id == cid

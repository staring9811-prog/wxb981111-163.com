"""预测台账与对账（PAGE-F26-01，SEQ-F26-01）：FLOW-21、FLOW-22、AC-F26-03 汇总与有效标准。"""
import pytest
from fastapi.testclient import TestClient

import decision_seed as ds
from conftest import login_as, make_user
from pdt.core import ledger
from pdt.db import session
from pdt.models import Batch, Card, Forecast, Product, Snapshot, now

J = {"accept": "application/json"}


def _approved(wen, boss, value):
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": value}, headers=J).json()["id"]
    wen.post(f"/cards/{cid}/narrative", data={"consumer": f"{value}（推测，待问答验证）"}, headers=J)
    wen.post(f"/cards/{cid}/submit", data={"note": ""}, headers=J)
    assert boss.post(f"/cards/{cid}/decide", data={"decision": "approve", "comment": "同意"}, headers=J).status_code == 200
    with session() as s:
        return s.query(Forecast).filter_by(card_id=cid).one().id, cid


def _batch(s, ch, month):
    b = Batch(channel=ch, month=month, source="api" if ch == "amazon" else "tracker", status="merged", merged_at=now(), rows=1)
    s.add(b)
    s.flush()
    return b.id


@pytest.fixture()
def team(wen, client):
    ds.seed_all()
    make_user("laoban", "老板", "approver")
    boss = login_as(TestClient(client.app), "laoban", "密码-123456")
    return wen, boss


def test_flow21_reconcile_amazon_and_unlinked(team):
    """FLOW-21：A 预计上架 2026-04 且关联了自家 ASIN（2026-06 小类 BSR 38）→ 并入 2026-10 后自动判定“做到”并写回，依据与停止条件可见；
    B 预计上架 2026-07、至今未关联 → “待关联”并提示；汇总按分级与做到概率分档显示并标有效标准。"""
    wen, boss = team
    fa, ca = _approved(wen, boss, "树脂")
    fb, cb = _approved(wen, boss, "陶瓷")
    own = "B0HQ7M2K4D"
    with session() as s:
        s.get(Forecast, fa).launch_month = "2026-04"
        s.get(Forecast, fa).channels = ["amazon"]  # A 只上 Amazon
        s.get(Forecast, fb).launch_month = "2026-07"
        s.add(Product(channel="amazon", item_id=own, family_key="自家-B0HQ7M2K4D", brand="自家品牌", title="30 inch resin top vanity"))
        bid = {m: s.query(Batch).filter_by(channel="amazon", month=m).one().id for m in ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09")}
        for m, rk, u, r in (("2026-04", 160, 30, 4.4), ("2026-05", 90, 55, 4.4), ("2026-06", 38, 88, 4.3), ("2026-07", 61, 70, 4.3), ("2026-08", 75, 64, 4.4), ("2026-09", 80, 60, 4.4)):
            s.add(Snapshot(batch_id=bid[m], channel="amazon", month=m, item_id=own, price=240, units=u, revenue=240 * u, rank=rk, rating=r))
    # ASIN 格式校验
    r = wen.post(f"/ledger/{fa}/link-asin", data={"asins": "A12345", "actual_month": "2026-04"}, headers=J)
    assert r.status_code == 400 and "ASIN 格式不对：10 位，以 B0 开头" in r.json()["detail"]
    # 预计 2026-04，实际 2026-05 上架：6 个月窗口 2026-05 至 10，要等 10 月并入
    assert wen.post(f"/ledger/{fa}/link-asin", data={"asins": own, "actual_month": "2026-05"}, headers=J).status_code == 200
    with session() as s:
        assert s.get(Card, ca).status == "tracking"
        _batch(s, "amazon", "2026-10")  # 并入 2026-10 数据
    st = ledger.reconcile_due("2026-11")
    assert st["reconciled"] == 1 and st["unlinked"] == 1
    with session() as s:
        a, b = s.get(Forecast, fa), s.get(Forecast, fb)
        assert a.status == "reconciled" and a.result["amazon"]["made"] is True
        assert a.result["amazon"]["basis"] == "2026-06 小类 BSR 38 ≤ 50" and a.result["amazon"]["window"] == "2026-05 至 2026-10"
        stops = {x["text"]: x for x in a.result["_stop"]}
        assert stops["前 3 个月评分 < 4.2"]["triggered"] is False  # 2026-05 至 07 评分 4.4 / 4.3 / 4.3
        units = next(x for t, x in stops.items() if t.startswith("第 2–3 个月月销 <"))
        limit = float(units["text"].split("<")[1].split("件")[0])
        assert units["triggered"] is (70 < limit) and "70" in units["why"]  # 第 2–3 个月（06、07）月销 88、70 件
        assert b.status == "unlinked"
        assert s.get(Card, ca).status == "reconciled"
    assert ledger.unlinked_alerts()[0]["card"] == "陶瓷 · 30″ 拆装 · 落地式"  # 工作台提示用
    h = wen.get("/ledger").text
    assert "1 条待关联：陶瓷 · 30″ 拆装 · 落地式" in h and "预计 2026-07 上架" in h
    assert "2026-06 小类 BSR 38 ≤ 50" in h and "未触发" in h and "已对账" in h
    assert "市场层 · 按分级" in h and "新品层 · 按做到概率分档（扣偏差后）" in h and "数据不全" in h
    with session() as s:
        summ = ledger.summary(s)
    g = {x["grade"]: x for x in summ["grades"]}
    assert g["B"]["n"] == 1 and (g["B"]["made"], g["B"]["made_n"]) == (1, 1)
    assert summ["bins"][0]["label"] == "≥ 50%" and (summ["bins"][0]["n"], summ["bins"][0]["made"]) == (1, 1)


def test_flow22_per_channel_success_lines(team):
    """FLOW-22：登记渠道 Amazon + Home Depot + Wayfair；Home Depot 同系列两商品估算月销合计 260 件（单个都 < 250）→ 做到（合并计算）；
    Wayfair 估算 100 件且未进前 50 → 未做到；Amazon 按 Amazon 成功线；三个渠道分别显示、不合并。"""
    wen, boss = team
    fid, cid = _approved(wen, boss, "树脂")
    with session() as s:
        f = s.get(Forecast, fid)
        f.channels = ["amazon", "homedepot", "wayfair"]
        f.launch_month = "2026-04"
        s.add(Product(channel="amazon", item_id="B0HQ7M2K4D", family_key="自家-B0HQ7M2K4D", brand="自家品牌"))
        s.add(Product(channel="homedepot", item_id="331020551", series="自家-Rhodes-30", brand="自家品牌"))
        s.add(Product(channel="homedepot", item_id="331020552", series="自家-Rhodes-30", brand="自家品牌"))
        s.add(Product(channel="wayfair", item_id="W115230881", series="自家-W30", brand="自家品牌"))
        ab = {m: s.query(Batch).filter_by(channel="amazon", month=m).one().id for m in ds.MONTHS[-6:]}
        hb = {m: s.query(Batch).filter_by(channel="homedepot", month=m).one().id for m in ds.MONTHS[-6:]}
        wb = {m: _batch(s, "wayfair", m) for m in ds.MONTHS[-6:]}
        for m in ds.MONTHS[-6:]:
            s.add(Snapshot(batch_id=ab[m], channel="amazon", month=m, item_id="B0HQ7M2K4D", price=240, units=60, revenue=14400, rank=120, rating=4.4))
            for it in ("331020551", "331020552"):
                s.add(Snapshot(batch_id=hb[m], channel="homedepot", month=m, item_id=it, price=249, units=130 if m == "2026-07" else 90, rank=80))
            s.add(Snapshot(batch_id=wb[m], channel="wayfair", month=m, item_id="W115230881", price=229, units=100 if m == "2026-08" else 70, rank=60))
    r = wen.post(f"/ledger/{fid}/link-asin", data={"asins": "B0HQ7M2K4D", "actual_month": "2026-04", "items_homedepot": "331020551"}, headers=J)
    assert r.status_code == 400 and "Wayfair" in r.json()["detail"]
    r = wen.post(f"/ledger/{fid}/link-asin", data={"asins": "B0HQ7M2K4D", "actual_month": "2026-04", "items_homedepot": "331020551",
                                                    "items_wayfair": "W115230881"}, headers=J)
    assert r.status_code == 200
    ledger.reconcile_due("2026-11")
    with session() as s:
        res = s.get(Forecast, fid).result
    assert res["homedepot"]["status"] == "做到" and "2026-07 估算月销 260 件 ≥ 250 件" in res["homedepot"]["basis"] and "同系列 2 个商品合并" in res["homedepot"]["basis"]
    assert res["wayfair"]["status"] == "未做到" and res["wayfair"]["nature"] == "估算"
    assert res["amazon"]["status"] == "未做到" and res["amazon"]["line"] == "小类 BSR ≤ 50 或 SPU 月销售额 ≥ $100,000"
    h = wen.get("/ledger").text
    row = h.split("TZ-")[1]
    assert row.count('class="ch"') == 3 and "做到" in row and "未做到" in row


def test_ac_f26_03_summary_criteria(wen):
    """AC-F26-03：按分级与做到概率分档显示实际做到比例，标出是否达到方案书有效标准（D 档之后变大 ≤ 30% 且逐档上升；新品层前 20% 做到率 ≥ 平均 2 倍）。"""
    ds.seed_all()
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    grew = {"A": [True, True], "B": [True, False], "C": [True, False, False], "D": [False, False, False]}
    probs = [(0.62, True), (0.55, False), (0.46, False), (0.41, False), (0.33, False)]
    with session() as s:
        k = 0
        for g, gs in grew.items():
            for x in gs:
                p, made = probs[k % 5]
                k += 1
                s.add(Forecast(code=f"TZ-2025-{k:02d}", card_id=cid, card_version=1, frame=ds.FRAME, attr="台面材质", value="树脂", grade=g,
                               prob_raw=p + 0.05, prob_adj=p, launch_month="2025-03", channels=["amazon"], status="reconciled",
                               result={"amazon": {"status": "做到" if made else "未做到", "made": made}, "_market": {"grew": x}}))
    with session() as s:
        summ = ledger.summary(s)
    g = {x["grade"]: x for x in summ["grades"]}
    assert (g["A"]["grew"], g["A"]["grew_n"], g["D"]["grew"], g["D"]["grew_n"]) == (2, 2, 0, 3)
    assert summ["d_ok"] is True and summ["mono"] is True
    assert summ["top_ok"] is True and summ["top_ratio"] >= 2
    h = wen.get("/ledger").text
    assert "D 档之后变大比例 ≤ 30%" in h and "达标 · 0%（0/3）" in h and "打分前 20% 做到率 ≥ 平均的 2 倍" in h

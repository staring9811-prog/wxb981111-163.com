"""审批（PAGE-F25-01）与策略库（PAGE-F25-02）：FLOW-19、FLOW-20。"""
import pytest
from fastapi.testclient import TestClient

import decision_seed as ds
from conftest import login_as, make_user
from pdt.db import session
from pdt.models import Approval, Audit, Card, Forecast, Strategy, StrategyVersion

J = {"accept": "application/json"}


@pytest.fixture()
def team(wen, client):
    ds.seed_all()
    make_user("laoban", "老板", "approver")
    boss = login_as(TestClient(client.app), "laoban", "密码-123456")
    return wen, boss


def _submit(wen, value):
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": value}, headers=J).json()["id"]
    wen.post(f"/cards/{cid}/narrative", data={"consumer": f"{value}：同价位给出不一样的样子（推测，待问答验证）"}, headers=J)
    assert wen.post(f"/cards/{cid}/submit", data={"note": "按上次意见补了差评归类"}, headers=J).status_code == 200
    return cid


def test_flow19_submit_approve_reject_return(team):
    """FLOW-19：老板对三张卡分别批准、驳回、退回修改并留意见；记录审批人、时间、结论、意见；批准的卡只读并自动登记台账；
    驳回与退回意见必填；退回的卡回到草稿。"""
    wen, boss = team
    a, b, c = _submit(wen, "树脂"), _submit(wen, "陶瓷"), _submit(wen, "木板")
    h = boss.get("/approvals").text
    assert "待我审批 <span class=\"count\">3</span>" in h and "树脂 · 30″ 拆装 · 落地式" in h and "做到概率 64% / 52%（扣偏差）" in h
    assert wen.post(f"/cards/{a}/decide", data={"decision": "approve"}, headers=J).status_code == 403  # 操作者不能审批
    with session() as s:
        ids = {x.obj_id: x.id for x in s.query(Approval).filter_by(status="pending")}
    # 驳回、退回修改意见必填
    r = boss.post(f"/approvals/{ids[b]}/decide", data={"decision": "reject", "comment": " "}, headers=J)
    assert r.status_code == 400 and r.json()["detail"] == "驳回或退回修改时请填写意见"
    r = boss.post(f"/approvals/{ids[c]}/decide", data={"decision": "return", "comment": ""}, headers=J)
    assert r.status_code == 400
    r = boss.post(f"/approvals/{ids[a]}/decide", data={"decision": "approve", "comment": "先做 30″，24″ 等结果。盆的排水孔必须是标准件。"}, headers=J)
    assert r.status_code == 200 and r.json()["ledger_code"].startswith("TZ-")
    assert boss.post(f"/approvals/{ids[b]}/decide", data={"decision": "reject", "comment": "拟定价位成交观测太少"}, headers=J).status_code == 200
    assert boss.post(f"/approvals/{ids[c]}/decide", data={"decision": "return", "comment": "补差评归类和钱"}, headers=J).status_code == 200
    assert boss.post(f"/approvals/{ids[a]}/decide", data={"decision": "approve"}, headers=J).json()["detail"] == "这条已处理"
    with session() as s:
        recs = {x.obj_id: x for x in s.query(Approval).all()}
        for cid, dec, com in ((a, "approve", "先做 30″"), (b, "reject", "拟定价位成交观测太少"), (c, "return", "补差评归类和钱")):
            x = recs[cid]
            assert x.decision == dec and x.decided_by is not None and x.decided_at is not None and com in x.comment
        ca, cb, cc = s.get(Card, a), s.get(Card, b), s.get(Card, c)
        assert (ca.status, cb.status, cc.status) == ("approved", "rejected", "draft")
        assert ca.snapshot and ca.snapshot["numbers"]["bet"]["score"]["grasp"] == 0.57
        assert cc.version == 2  # 退回后再提交是下一版
        assert s.query(Audit).filter_by(kind="approve").count() == 3
        f = s.query(Forecast).filter_by(card_id=a).one()
        assert f.card_version == 1 and f.registered_at is not None and f.frame == ds.FRAME and f.value == "树脂"
        assert (f.grade, f.grasp, f.share_lo, f.share_hi) == ("B", 0.57, 0.096, 0.174)
        assert f.prob_raw == 0.64 and abs(f.prob_adj - 0.52) < 1e-9
        assert f.launch_month == "2027-05" and [x["kind"] for x in f.stop_conditions] == ["rating_below", "units_below", "price_ratio_below"]
        assert f.stop_conditions[0]["text"] == "前 3 个月评分 < 4.2"
        assert s.query(Forecast).filter_by(card_id=b).count() == 0
    assert wen.post(f"/cards/{a}/narrative", data={"consumer": "改"}, headers=J).status_code == 409  # 批准后只读
    assert wen.post(f"/cards/{c}/narrative", data={"consumer": "按意见补齐"}, headers=J).status_code == 200  # 退回后可改
    h = wen.get("/approvals").text
    assert "已处理 <span class=\"count\">3</span>" in h and "补差评归类和钱" in h and "老板" in h
    led = wen.get("/ledger").text
    assert "树脂 · 30″ 拆装 · 落地式" in led and "B · 9.6%–17.4%" in led and "64% / 52%" in led and "2027-05" in led


def test_flow20_strategy_versions_and_verified_approval(team):
    """FLOW-20：新增“首月 ≥2 色 ≥4 子体”（历史观察），修改一次，再申请改为“已验证”；批准前状态不变，老板批准后才变为已验证。"""
    wen, boss = team
    h = wen.get("/strategies").text  # 首次打开预置第二轮结论
    assert "老板：老品评分差，新品把评分做好就起量" in h and "未验证经验" in h and "分框信号：取值的新品占比高于同框" in h
    assert wen.post("/strategies", data={"title": "改成已验证", "kind": "经验", "status": "已验证", "basis": "x"}, headers=J).status_code == 400
    r = wen.post("/strategies", data={"title": "首月 ≥2 色 ≥4 子体", "kind": "条件表", "status": "历史观察",
                                      "basis": "2026-01 至 04 上架的新家族核对", "body": "全部框"}, headers=J)
    assert r.status_code == 200
    with session() as s:
        st = s.query(Strategy).filter_by(title="首月 ≥2 色 ≥4 子体").one()
        sid = st.id
        assert (st.status, st.version) == ("历史观察", 1)
    r = wen.post(f"/strategies/{sid}", data={"title": "首月 ≥2 色 ≥4 子体", "status": "历史观察", "basis": "新家族 214 个：满足条件 38%（n=61），不满足 17%（n=153）",
                                             "body": "全部框", "note": "补上做到率依据"}, headers=J)
    assert r.json()["version"] == 2
    assert wen.post(f"/strategies/{sid}", data={"status": "已验证", "note": "直接改"}, headers=J).status_code == 400
    v = wen.get(f"/strategies/{sid}/versions").json()["versions"]
    assert [x["version"] for x in v] == [2, 1] and v[1]["basis"] == "2026-01 至 04 上架的新家族核对"
    assert wen.post(f"/strategies/{sid}/apply-verified", data={"basis": "台账已对账 3 条，满足条件的 2 条都做到"}, headers=J).status_code == 200
    assert wen.post(f"/strategies/{sid}/apply-verified", data={"basis": "再申请"}, headers=J).json()["detail"] == "已有待审批申请"
    h = wen.get("/strategies").text
    assert "申请已验证 · 待老板审批" in h
    with session() as s:
        assert s.get(Strategy, sid).status == "历史观察"
        aid = s.query(Approval).filter_by(obj_type="strategy", obj_id=sid).one().id
    assert "策略库改为已验证" in boss.get("/approvals").text
    assert boss.post(f"/approvals/{aid}/decide", data={"decision": "approve", "comment": ""}, headers=J).status_code == 200
    with session() as s:
        st = s.get(Strategy, sid)
        assert (st.status, st.version) == ("已验证", 3)
        assert [x.status for x in s.query(StrategyVersion).filter_by(strategy_id=sid).order_by(StrategyVersion.version)] == ["历史观察", "历史观察", "已验证"]
    assert boss.post("/strategies", data={"title": "x", "kind": "经验", "status": "未验证经验", "basis": "x"}, headers=J).status_code == 403

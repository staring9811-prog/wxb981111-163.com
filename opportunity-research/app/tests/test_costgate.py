"""费用闸门：先估算后确认、到上限即停、续跑不重复计费（AC-F16-06/07，NFR-011）。"""
from pdt import costgate
from pdt.db import session
from pdt.models import Budget, CostRecord, Job

CALLS = []


def _est(p):
    return dict(service="sellersprite", calls=10, usd_lo=0.1, usd_hi=0.1, minutes=1, note="测试 10 个分片")


def _run(ctx):
    for i in range(10):
        k = f"分片{i}"
        if ctx.shard_done(k):
            continue
        ctx.allow("sellersprite", qty=1)
        CALLS.append(k)
        ctx.charge("sellersprite", qty=1, amount=0.01, task="测试拉取")
        ctx.mark_shard(k)


costgate.register("test_pull", "测试拉取", _est, _run)


def test_estimate_confirm_cap_resume(wen):
    CALLS.clear()
    with session() as s:
        s.add(Budget(service="sellersprite", cap=5, unit="calls"))
    j = wen.post("/jobs/estimate", data={"kind": "test_pull", "month": "2026-10"}).json()
    assert j["status"] == "estimated" and j["estimate"]["calls"] == 10 and CALLS == []
    assert j["estimate"]["warnings"]  # 预计超过上限
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "stopped_cap" and len(CALLS) == 5
    with session() as s:
        s.get(Budget, "sellersprite").cap = 100
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "done" and len(CALLS) == 10 and len(set(CALLS)) == 10
    with session() as s:
        assert s.query(CostRecord).count() == 10


def test_cancel_no_calls(wen):
    CALLS.clear()
    j = wen.post("/jobs/estimate", data={"kind": "test_pull", "month": "2026-09"}).json()
    wen.post(f"/jobs/{j['id']}/cancel")
    with session() as s:
        assert s.get(Job, j["id"]).status == "cancelled"
    assert CALLS == []

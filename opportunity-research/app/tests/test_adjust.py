"""数据审核: proposals (Codex API / by hand) apply only after a person confirms; the package rows never change."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from sqlalchemy import text

from oppo import service as SV
from oppo.core import adjust as ADJ
from oppo.core import compute as CMP
from oppo.core import data as DATA
from oppo.core import packages as PK
from tests.conftest import Live, open_dir


def _pick(app: SV.App) -> dict[str, Any]:
    with app.engine.begin() as conn:
        pkg = PK.current_package(conn, app.category_id(), "history")
        child, month, units, launch = conn.execute(text(
            "SELECT child, month, child_units, launch_date FROM raw_c1 WHERE package_id=:p AND child_units > 0 "
            "ORDER BY child, month LIMIT 1"), {"p": pkg["id"]}).first()
        form = conn.execute(text("SELECT value, status FROM raw_c4 WHERE package_id=:p AND child=:c AND dim='形态'"),
                            {"p": pkg["id"], "c": child}).first()
    return {"pkg": pkg, "child": child, "month": month, "units": units, "launch": launch, "form": form}


def _raw_dump(app: SV.App, pid: int) -> list[tuple]:
    with app.engine.begin() as conn:
        a = conn.execute(text("SELECT * FROM raw_c1 WHERE package_id=:p ORDER BY row_no"), {"p": pid}).all()
        b = conn.execute(text("SELECT * FROM raw_c4 WHERE package_id=:p ORDER BY child, dim"), {"p": pid}).all()
    return [tuple(r) for r in a] + [tuple(r) for r in b]


def test_confirm_edit_reject_revoke_without_touching_the_package(clone, h1a_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_done))
    x = _pick(app)
    pid, cid = x["pkg"]["id"], app.category_id()
    before = _raw_dump(app, pid)
    new_form = "悬浮式" if x["form"][0] != "悬浮式" else "落地式"
    res = SV.adjust_propose(app, pid, [
        {"file": "C4", "child": x["child"], "field": "形态", "value": new_form, "reason": "主图为壁挂"},
        {"file": "C1", "child": x["child"], "month": x["month"].replace("-", ""), "field": "子体月销量", "value": "7"},
        {"file": "C1", "child": x["child"], "field": "上架日期", "value": "2025-01-05"},
        {"file": "C1", "child": "B000NOSUCH", "field": "上架日期", "value": "2025-01-05"},
        {"file": "C4", "child": x["child"], "field": "形态证据状态", "value": "大概吧"},
        {"file": "C5", "child": x["child"], "field": "关键词", "value": "x"},
    ], "Codex")
    assert len(res["created"]) == 3 and [e["index"] for e in res["errors"]] == [3, 4, 5]
    a_form, a_units, a_launch = res["created"]
    with app.engine.begin() as conn:
        # nothing applies while pending
        b = DATA.load(conn, pid, None)
        assert b.c4[(b.c4.child == x["child"]) & (b.c4.dim == "形态")]["value"].iloc[0] == x["form"][0]
        rows = ADJ.listing(conn, cid, package_id=pid, status=ADJ.PENDING)
        assert {r["code"]: r["old_value"] for r in rows}[a_units] == str(int(x["units"]))
    SV.adjust_decide(app, [a_form], "confirm")
    SV.adjust_decide(app, [a_units], "confirm", values={a_units: "9"})  # edited before confirming
    SV.adjust_decide(app, [a_launch], "reject")
    with app.engine.begin() as conn:
        b = DATA.load(conn, pid, None)
        assert b.c4[(b.c4.child == x["child"]) & (b.c4.dim == "形态")]["value"].iloc[0] == new_form
        row = b.c1[(b.c1.child == x["child"]) & (b.c1.month == x["month"])].iloc[0]
        assert row["child_units"] == 9 and row["launch_date"] == x["launch"]
        assert "数据审核的已确认调整有变化" in CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, "history"))
        got = {r["code"]: r for r in ADJ.listing(conn, cid, package_id=pid)}
        assert got[a_units]["final_value"] == "9" and got[a_launch]["status"] == ADJ.REJECTED
        eff = ADJ.effective_rows(conn, pid, "C1", child=x["child"], month=x["month"])
        assert eff["rows"][0]["values"]["子体月销量"] == "9"
        assert eff["rows"][0]["imported_if_changed"]["子体月销量"] == str(int(x["units"]))
        logs = conn.execute(text("SELECT COUNT(*) FROM change_log WHERE object='数据调整'")).scalar()
        assert logs >= 6
    assert _raw_dump(app, pid) == before  # the imported rows are untouched
    SV.adjust_revoke(app, [a_form, a_units])
    with app.engine.begin() as conn:
        b = DATA.load(conn, pid, None)
        assert b.c4[(b.c4.child == x["child"]) & (b.c4.dim == "形态")]["value"].iloc[0] == x["form"][0]
        assert ADJ.adjust_hash(conn, pid) == ""
        assert not [r for r in CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, "history")) if "数据审核" in r]


def test_new_proposal_replaces_pending_and_confirm_supersedes(clone, h1a_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_done))
    x = _pick(app)
    pid = x["pkg"]["id"]
    item = {"file": "C4", "child": x["child"], "field": "颜色", "value": "白色"}
    first = SV.adjust_propose(app, pid, [item], "Codex")["created"][0]
    second = SV.adjust_propose(app, pid, [{**item, "value": "黑色"}], "Codex")["created"][0]
    with app.engine.begin() as conn:
        st = {r["code"]: r["status"] for r in ADJ.listing(conn, app.category_id(), package_id=pid)}
    assert st == {first: ADJ.WITHDRAWN, second: ADJ.PENDING}
    SV.adjust_decide(app, [second], "confirm")
    third = SV.adjust_propose(app, pid, [{**item, "value": "灰色"}], "手工")["created"][0]
    SV.adjust_decide(app, [third], "confirm")
    with app.engine.begin() as conn:
        st = {r["code"]: r["status"] for r in ADJ.listing(conn, app.category_id(), package_id=pid)}
        b = DATA.load(conn, pid, None)
    assert st[second] == ADJ.REVOKED and st[third] == ADJ.CONFIRMED
    assert b.c4[(b.c4.child == x["child"]) & (b.c4.dim == "颜色")]["value"].iloc[0] == "灰色"


def test_recompute_uses_confirmed_values(clone, h1a_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_done))
    x = _pick(app)
    pid, cid = x["pkg"]["id"], app.category_id()
    code = SV.adjust_propose(app, pid, [{"file": "C4", "child": x["child"], "field": "形态证据状态",
                                         "value": "信息不足"}], "Codex")["created"][0]
    SV.adjust_decide(app, [code], "confirm")
    SV.recompute(app)
    with app.engine.begin() as conn:
        run = CMP.latest_run(conn, cid, "history")
        assert run["adjust_hash"] == ADJ.adjust_hash(conn, pid) != ""
        assert CMP.stale_reasons(conn, cid, run) == []


# ---- local API --------------------------------------------------------------------------------


def _call(live: Live, method: str, path: str, body: Any = None, token: str | None = "api") -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {live.app.settings.api_token() if token == 'api' else token}"
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(live.u(path), data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode()


def test_api_reads_proposes_and_cannot_confirm(live_server, clone, h1a_done):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    x = _pick(live.app)
    label = x["pkg"]["label"]
    assert _call(live, "GET", "/api/v1/info", token=None)[0] == 401
    assert _call(live, "GET", "/api/v1/info", token="wrong")[0] == 401
    assert _call(live, "GET", "/api/v1/info", token=live.token)[0] == 401  # the page token is not the API token
    st, info = _call(live, "GET", "/api/v1/info")
    assert st == 200 and info["packages"][0]["package"] == label and "形态证据状态" in info["adjustable_fields"][label]["C4"]
    st, rows = _call(live, "GET", f"/api/v1/packages/{label}/rows?file=C4&child={x['child']}")
    assert st == 200 and rows["total"] == 1 and rows["rows"][0]["values"]["形态"] == x["form"][0]
    st, flt = _call(live, "GET", f"/api/v1/packages/{label}/rows?file=C4&limit=5&filter="
                    + urllib.request.quote(f"形态:{x['form'][0]}"))
    assert st == 200 and flt["total"] >= 1 and all(r["values"]["形态"] == x["form"][0] for r in flt["rows"])
    st, res = _call(live, "POST", f"/api/v1/packages/{label}/adjustments", {
        "source": "Codex", "items": [{"file": "C4", "child": x["child"], "field": "形态", "value": "悬浮式",
                                      "reason": "测试"}, {"file": "C4", "child": "NOPE", "field": "形态", "value": "x"}]})
    assert st == 200 and len(res["created"]) == 1 and res["errors"][0]["index"] == 1 and res["status"] == "待审核"
    code = res["created"][0]
    st, rows = _call(live, "GET", f"/api/v1/packages/{label}/rows?file=C4&child={x['child']}")
    assert rows["rows"][0]["pending"][0]["code"] == code and rows["rows"][0]["values"]["形态"] == x["form"][0]
    st, lst = _call(live, "GET", "/api/v1/adjustments?status=" + urllib.request.quote("待审核"))
    assert [i["code"] for i in lst["items"]] == [code]
    for path in (f"/api/v1/adjustments/{code}/confirm", "/api/v1/adjustments/confirm"):
        assert _call(live, "POST", path, {"codes": [code]})[0] in (404, 405)
    st, wd = _call(live, "POST", "/api/v1/adjustments/withdraw", {"codes": [code]})
    assert st == 200 and wd["done"] == [code]
    assert _call(live, "POST", f"/api/v1/packages/{label}/adjustments", {"items": "x"})[0] == 400


def test_review_page_confirm_and_edit(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    x = _pick(live.app)
    pid = x["pkg"]["id"]
    res = SV.adjust_propose(live.app, pid, [
        {"file": "C4", "child": x["child"], "field": "形态", "value": "悬浮式", "reason": "主图壁挂"},
        {"file": "C1", "child": x["child"], "field": "上架日期", "value": "2025-02-01"}], "Codex")
    a1, a2 = res["created"]
    page.goto(live.u("/review"))
    assert page.locator("h1").inner_text() == "数据审核"
    assert page.locator(".nav__item[aria-current=page] .nav__count").inner_text() == "2"
    assert page.locator("#adj-table tbody tr").count() == 2
    page.locator(f'tr[data-code="{a2}"] [data-adj-code]').click()
    page.locator("#edit-modal input[name=value_edit]").fill("2025-13-01")
    page.locator("#edit-modal button[type=submit]").click()
    page.locator('#edit-modal [data-error-for="value_edit"]').filter(has_text="不是日期").wait_for()
    page.locator("#edit-modal input[name=value_edit]").fill("2025-02-03")
    page.locator("#edit-modal button[type=submit]").click()
    page.wait_for_url("**toast=*")
    page.locator(f'tr[data-code="{a1}"] button[data-arg-decision="confirm"]').click()
    page.wait_for_function("() => !document.querySelector('#adj-table')")
    with live.app.engine.begin() as conn:
        got = {r["code"]: r for r in ADJ.listing(conn, live.app.category_id(), package_id=pid)}
    assert got[a1]["status"] == got[a2]["status"] == ADJ.CONFIRMED and got[a2]["final_value"] == "2025-02-03"
    page.goto(live.u("/review?tab=confirmed"))
    assert page.locator("#adj-table tbody tr").count() == 2
    assert page.locator(".banner--stale").is_visible()
    page.locator(f'tr[data-code="{a1}"] [data-post="/review/revoke"]').click()
    page.wait_for_url("**tab=confirmed*toast=*")
    assert page.locator("#adj-table tbody tr").count() == 1
    assert not page.js_errors


def test_cli_adjust(clone, h1a_done, tmp_path, capsys):  # type: ignore[no-untyped-def]
    from oppo import cli

    d = clone(h1a_done)
    app = open_dir(d)
    x = _pick(app)
    f = tmp_path / "items.json"
    f.write_text(json.dumps({"source": "Codex", "items": [
        {"file": "C4", "child": x["child"], "field": "盆数", "value": "2"}]}, ensure_ascii=False), encoding="utf-8")
    argv = ["--data-dir", str(d)]
    assert cli.main(argv + ["adjust", "propose", "--file", str(f)]) == 0
    code = json.loads(capsys.readouterr().out)["created"][0]
    assert cli.main(argv + ["adjust", "confirm", "--codes", code, "--value", "1"]) == 0
    assert "确认 1 条" in capsys.readouterr().out
    assert cli.main(argv + ["adjust", "list", "--status", "已确认"]) == 0
    assert code in capsys.readouterr().out
    assert cli.main(argv + ["api-token"]) == 0
    assert capsys.readouterr().out.strip() == app.settings.api_token()


@pytest.mark.parametrize("value,ok", [("子体确认", True), ("确认", False)])
def test_status_values(value, ok):  # type: ignore[no-untyped-def]
    if ok:
        assert ADJ.parse_value(value, "文本", "形态证据状态") == value
    else:
        with pytest.raises(ADJ.AdjustError):
            ADJ.parse_value(value, "文本", "形态证据状态")

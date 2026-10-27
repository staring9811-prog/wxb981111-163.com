"""RULE-08 (backup to a read-only directory, then restore), FLOW-01 (a blocked package is refused by the API and
the command line), FLOW-04 (no 五点描述 → 无数据 in the comparison) and RULE-03 (every judgment, ranking row and
kit traces back to package / contract / config versions and source keys)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import text

from oppo import db as D
from oppo import service as SV
from oppo.core import backup as BK
from oppo.core import categories as CAT
from oppo.core import contract as CT
from oppo.core import ledger as LG
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from tests.conftest import APP_ROOT, _prepared, fixture_pkg, open_dir


def _close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _immutable(path: Path, on: bool) -> bool:
    """A read-only directory that holds even for root (the container runs as root): chattr ±i."""
    r = subprocess.run(["chattr", "+i" if on else "-i", str(path)], capture_output=True)
    return r.returncode == 0


def _table_rows(db: Path, table: str) -> list[tuple]:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in c.execute(f'PRAGMA table_info("{table}")')]
        order = "id" if "id" in cols else cols[0]
        return [tuple(r) for r in c.execute(f'SELECT * FROM "{table}" ORDER BY {order}')]
    finally:
        c.close()


def test_rule08_readonly_backup_dir_then_restore(clone, h1a_done, tmp_path) -> None:  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    app = open_dir(d)
    bdir = tmp_path / "备份"
    with app.engine.begin() as conn:
        assert BK.set_directory(conn, str(bdir), "wen")[0]
        cid = app.category_id()
    first = SV.job_result(app, SV.export(app))["result"]
    assert first["backup"]["status"] == "success"
    first_path = Path(first["backup"]["path"])
    before = {p.name: _sha(p) for p in bdir.iterdir()}
    with app.engine.begin() as conn:
        last_ok = BK.last_success(conn)["created_at"]
    if not _immutable(bdir, True):
        pytest.skip("chattr +i not available: cannot make a directory read-only for root")
    try:
        second = SV.job_result(app, SV.export(app))["result"]
    finally:
        _immutable(bdir, False)
    # the export itself succeeded; the backup failed with a reason; older backups are untouched; no partial files
    assert Path(second["xlsx_path"]).exists() and Path(second["html_path"]).exists()
    assert second["backup"]["status"] == "failed" and second["backup"]["error"]
    assert second["backup"]["last_success"] == last_ok
    assert {p.name: _sha(p) for p in bdir.iterdir()} == before
    with app.engine.begin() as conn:
        exp = conn.execute(text("SELECT backup_id FROM export_record ORDER BY id DESC")).scalar()
        rec = conn.execute(text("SELECT status, error FROM backup_record WHERE id=:i"), {"i": exp}).first()
    assert rec[0] == "failed"

    # later changes: a decision, a rule edit, a new contract version and a new config version
    with app.engine.begin() as conn:
        snap = RK.latest_snapshot(conn, cid, "history")
        top = snap["content"]["rows"][0]
        LG.record_decision(conn, cid, "wen", "立项", top["segment_key"], top["segment"], "恢复测试", snap["id"])
        r = RULES.list_current(conn, cid)[0]
        RULES.edit(conn, r["rule_id"], r["conds"], r["action"], "只改理由", "wen")
        item = next(i for i in CT.draft_items(conn, cid) if i["status"] == "confirmed")
        CT.update_draft(conn, cid, item["file_code"], item["field"], {"meaning": "恢复测试改过的含义"}, True, "逐项")
        CT.save_version(conn, cid, "wen", "恢复测试")
        cfg = CAT.current_version(conn, cid)["config"]
        cfg["health_thresholds"]["dup_key"] = 9
        CAT.save_version(conn, cid, cfg, "wen", "恢复测试")
    with pytest.raises(BK.RestoreError):
        BK.restore(app, first_path, confirm=False)  # 二次确认
    out = BK.restore(app, first_path, confirm=True)
    assert out["pre_backup"]["status"] == "success" and Path(out["pre_backup"]["path"]).exists()
    for t in D.BACKUP_TABLES:
        if t in ("export_record", "run_step", "snapshot_export"):
            continue  # export bookkeeping after the backup is part of the restored state as well; compared below
        assert _table_rows(d / "oppo.sqlite3", t) == _table_rows(first_path, t), t
    for t in ("export_record", "snapshot_export"):
        assert _table_rows(d / "oppo.sqlite3", t) == _table_rows(first_path, t), t
    with app.engine.begin() as conn:
        rr = BK.last_restore(conn)
    assert rr["backup_path"] == str(first_path) and rr["backup_time"]
    _close(app)


def _post(url: str, token: str) -> dict:
    req = urllib.request.Request(url, data=b"", method="POST", headers={"X-Oppo-Token": token})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def test_flow01_blocked_package_is_refused(live_server, data_dir) -> None:  # type: ignore[no-untyped-def]
    p = subprocess.run([sys.executable, "-m", "oppo.cli", "--data-dir", str(data_dir), "import",
                        str(fixture_pkg("H1-坏行11"))], cwd=str(APP_ROOT), capture_output=True, text=True)
    assert p.returncode == 2 and "阻断" in p.stdout
    c = subprocess.run([sys.executable, "-m", "oppo.cli", "--data-dir", str(data_dir), "compute"],
                       cwd=str(APP_ROOT), capture_output=True, text=True)
    assert c.returncode != 0 and c.stderr.strip()
    b = subprocess.run([sys.executable, "-m", "oppo.cli", "--data-dir", str(data_dir), "backtest"],
                       cwd=str(APP_ROOT), capture_output=True, text=True)
    assert b.returncode != 0
    live = live_server(data_dir)
    res = _post(live.u("/jobs/compute"), live.token)
    assert res.get("ok") is False and res.get("error")
    with live.app.engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM compute_run")).scalar() == 0


def test_flow04_no_bullets_comparison_shows_nodata(live_server, tmp_path_factory, clone, page) -> None:  # type: ignore[no-untyped-def]
    d = _prepared(tmp_path_factory, "nobul", ("import:H1-无五点", "confirm"))
    live = live_server(clone(d))
    page.goto(live.u("/spu/merge"))
    page.evaluate("document.querySelectorAll('#pending-table details').forEach(x => x.open = true)")
    rows = page.locator("#pending-table details tr", has_text="五点摘要")
    assert rows.count() >= 1
    assert all("无数据" in rows.nth(i).inner_text() for i in range(rows.count()))
    assert page.locator('#panel-pending .chip:has-text("五点描述相同")').inner_text().strip().endswith("0")


def test_rule03_every_result_is_traceable(h1a_done: Path) -> None:
    db = sqlite3.connect(f"file:{h1a_done / 'oppo.sqlite3'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    run = db.execute("SELECT * FROM compute_run WHERE mode='history' ORDER BY id DESC").fetchone()
    assert run["package_id"] and run["contract_version_id"] and run["config_version_id"]
    pkg = db.execute("SELECT label, fingerprint FROM package WHERE id=?", (run["package_id"],)).fetchone()
    assert pkg["label"] and pkg["fingerprint"]
    spus = db.execute("SELECT s.spu_key, s.source_keys_json, j.status FROM spu s JOIN judgment j "
                      "ON j.run_id=s.run_id AND j.spu_key=s.spu_key WHERE s.run_id=?", (run["id"],)).fetchall()
    assert spus
    for s in spus:
        keys = json.loads(s["source_keys_json"])
        assert keys["package"] == pkg["label"] and keys["children"], s["spu_key"]
    snap = db.execute("SELECT * FROM snapshot ORDER BY id DESC").fetchone()
    content = json.loads(snap["content_json"])
    v = content["versions"]
    assert v["package"] == pkg["label"] and v["contract"] and v["config"] and v["compute_run"] == run["id"]
    assert snap["card_id"] and snap["backtest_id"] and snap["sha256"]
    bt = db.execute("SELECT * FROM backtest_run WHERE id=?", (snap["backtest_id"],)).fetchone()
    assert bt["package_id"] == run["package_id"] and bt["contract_version_id"] and bt["config_version_id"]
    for row in content["rows"]:
        for tip in row["tips"]:
            rv = db.execute("SELECT v.basis_json FROM rule r JOIN rule_version v ON v.rule_id=r.id "
                            "WHERE r.code=? AND v.version_no=?", (tip["rule"], tip["version"])).fetchone()
            basis = json.loads(rv["basis_json"])
            assert basis.get("backtest") == bt["code"] and basis.get("n"), tip
    db.close()

"""Risk acceptance: point-in-time truncation (RULE-01), reproducibility (RULE-02), local-only access (RULE-06),
append-only records (RULE-07) and the single background task with rollback (RULE-09)."""

from __future__ import annotations

import csv
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import text

from oppo import db as D
from oppo import service as SV
from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import jobs
from oppo.core import ranking as RK
from tests.conftest import APP_ROOT, _prepared, fixture_pkg, open_dir

X = "30–48″|落地式|$500–900"


def _close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


# ---- RULE-01 point-in-time --------------------------------------------------------------------


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def _write(path: Path, cols: list[str], rows: list[dict[str, str]]) -> None:
    path.chmod(0o644)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _variant(tmp: Path, name: str, edit) -> Path:  # type: ignore[no-untyped-def]
    dst = tmp / name
    shutil.copytree(fixture_pkg("H1-A"), dst)
    for p in dst.iterdir():
        p.chmod(0o644)
    edit(dst)
    return dst


def _signals_T(pkg: Path, d: Path) -> tuple[list[tuple], list[tuple]]:
    app = open_dir(d)
    SV.import_package(app, pkg)
    SV.contract_confirm(app)
    SV.compute(app)
    with app.engine.begin() as conn:
        run_ = CMP.latest_run(conn, app.category_id(), "history")
        assert run_["t_month"] == "2026-03"
        sig = conn.execute(text("SELECT segment_key, signal, value, num, den, cnt, flag FROM signal_value "
                                "WHERE run_id=:r AND t_month='2026-03' ORDER BY segment_key, signal"),
                           {"r": run_["id"]}).all()
        seg = conn.execute(text("SELECT segment_key, child_count, backfill_share, sample FROM segment_info "
                                "WHERE run_id=:r AND t_month='2026-03' ORDER BY segment_key"), {"r": run_["id"]}).all()
    _close(app)
    return [tuple(r) for r in sig], [tuple(r) for r in seg]


def _after_T(dst: Path) -> None:
    """Change only data dated 2026-03-01 or later: big value changes and added rows."""
    c1 = dst / "C1_月度类目商品.csv"
    cols, rows = _rows(c1)
    extra = []
    for r in rows:
        if r["月份"] == "202602":
            n = dict(r, 月份="202603")
            n["子体月销量"] = str(int(float(r["子体月销量"] or 0)) * 10 + 7)
            n["子体月销售额"] = str(int(float(r["子体月销售额"] or 0)) * 10 + 7)
            extra.append(n)
    _write(c1, cols, rows + extra)
    c5 = dst / "C5_关键词月度.csv"
    cols, rows = _rows(c5)
    add = [dict(r, 月份="202603", 月搜索量="99999") for r in rows if r["月份"] == "202602"]
    _write(c5, cols, rows + add)
    c6 = dst / "C6_评论痛点.csv"
    cols, rows = _rows(c6)
    for r in rows:
        if r["评论日期"] >= "2026-03-01":
            r["是否结构类痛点"] = "否" if r["是否结构类痛点"] == "是" else "是"
            r["星级"] = "5"
    asin = next(r["ASIN"] for r in rows if r["评论日期"] == "2026-03-01")
    add6 = [dict(rows[0], 评论ID=f"RX{i:09d}", ASIN=asin, 评论日期=f"2026-03-{1 + i % 9:02d}", 是否结构类痛点="是",
                 星级="1") for i in range(40)]
    _write(c6, cols, rows + add6)


def _delete_after_T(dst: Path) -> None:
    c6 = dst / "C6_评论痛点.csv"
    cols, rows = _rows(c6)
    _write(c6, cols, [r for r in rows if r["评论日期"] < "2026-03-01"])


def _before_T(dst: Path) -> None:
    """One 2026-02 keyword value and one 2026-02-28 structural review on the X child that has the 03-01 review."""
    c5 = dst / "C5_关键词月度.csv"
    cols, rows = _rows(c5)
    for r in rows:
        if r["关键词"] == "36 inch bathroom vanity with sink" and r["月份"] == "202602":
            r["月搜索量"] = str(int(r["月搜索量"]) * 3)
    _write(c5, cols, rows)
    c6 = dst / "C6_评论痛点.csv"
    cols, rows = _rows(c6)
    asin = next(r["ASIN"] for r in rows if r["评论日期"] == "2026-03-01")
    rows.append(dict(rows[0], 评论ID="RB000000001", ASIN=asin, 归属级别="子体", 评论日期="2026-02-28", 是否结构类痛点="是"))
    _write(c6, cols, rows)


def test_rule01_point_in_time(tmp_path: Path) -> None:
    base_sig, base_seg = _signals_T(fixture_pkg("H1-A"), tmp_path / "d0")
    pain_x = next(r for r in base_sig if r[0] == X and r[1] == "pain")
    assert (pain_x[3], pain_x[4]) == (25, 200)
    for name, edit in (("after", _after_T), ("deleted", _delete_after_T)):
        sig, seg = _signals_T(_variant(tmp_path, name, edit), tmp_path / f"d_{name}")
        assert sig == base_sig, name
        assert seg == base_seg, name
    sig, _ = _signals_T(_variant(tmp_path, "before", _before_T), tmp_path / "d_before")
    assert sig != base_sig
    demand_x = next(r for r in sig if r[0] == X and r[1] == "demand")
    base_demand_x = next(r for r in base_sig if r[0] == X and r[1] == "demand")
    assert demand_x[2] != base_demand_x[2]
    pain_x2 = next(r for r in sig if r[0] == X and r[1] == "pain")
    assert (pain_x2[3], pain_x2[4]) == (26, 201)  # 2026-02-28 counted, 2026-03-01 still not


# ---- RULE-02 reproducibility ----------------------------------------------------------------------

TABLES = {
    "spu": "SELECT * FROM spu WHERE run_id=:r ORDER BY spu_key",
    "judgment": "SELECT * FROM judgment WHERE run_id=:r ORDER BY spu_key",
    "signal_value": "SELECT * FROM signal_value WHERE run_id=:r ORDER BY t_month, segment_key, signal",
    "segment_info": "SELECT * FROM segment_info WHERE run_id=:r ORDER BY t_month, segment_key",
}


def _dump(d: Path) -> dict[str, object]:
    app = open_dir(d)
    out: dict[str, object] = {}
    with app.engine.begin() as conn:
        cid = app.category_id()
        run_ = CMP.latest_run(conn, cid, "history")
        for t, q in TABLES.items():
            out[t] = [tuple(x for k, x in r._mapping.items() if k != "run_id") for r in conn.execute(text(q), {"r": run_["id"]})]
        bt = BT.latest(conn, cid, "history")
        out["backtest"] = (bt["conclusion"], D.dumps(bt["result"]))
        out["card"] = [(r["label"], r["status"], r["signals_json"], r["basis_json"]) for r in
                       conn.execute(text("SELECT * FROM decision_card ORDER BY id")).mappings()]
        out["rules"] = [(r["code"], r["version_no"], r["action"], r["status"], r["condition_json"], r["basis_json"]) for r in
                        conn.execute(text("SELECT r.code, v.* FROM rule r JOIN rule_version v ON v.rule_id=r.id "
                                          "ORDER BY r.code, v.version_no")).mappings()]
        snap = RK.latest_snapshot(conn, cid, "history")
        out["snapshot"] = (snap["sha256"], snap["content_json"])
    _close(app)
    return out


def test_rule02_two_fresh_databases_identical(tmp_path_factory, h1a_done: Path, clone) -> None:  # type: ignore[no-untyped-def]
    other = _prepared(tmp_path_factory, "h1a_again", ("import:H1-A", "confirm", "compute", "backtest"))
    a, b = _dump(h1a_done), _dump(other)
    for k in a:
        assert a[k] == b[k], k
    # the two exported workbooks match cell by cell apart from generation times and their own paths
    from tests.test_rule04_cli_vs_web import _sheets

    books = []
    for d in (clone(h1a_done), clone(other)):
        app = open_dir(d)
        books.append((SV.job_result(app, SV.export(app))["result"]["xlsx_path"], d))
        _close(app)
    sa, sb = _sheets(books[0][0], books[0][1]), _sheets(books[1][0], books[1][1])
    assert list(sa) == list(sb) and len(sa) == 9
    for title in sa:
        assert sa[title] == sb[title], title


# ---- RULE-06 local only -----------------------------------------------------------------------------


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _lan_ip() -> str | None:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent for UDP connect
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()
    return ip if ip and not ip.startswith("127.") else None


def _listening(port: int) -> list[str]:
    """Local addresses in LISTEN state for `port`, read from /proc/net/tcp{,6}."""
    import ipaddress

    out = []
    for name, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        try:
            lines = Path(name).read_text().splitlines()[1:]
        except OSError:
            continue
        for ln in lines:
            parts = ln.split()
            local, state = parts[1], parts[3]
            host, p = local.split(":")
            if state != "0A" or int(p, 16) != port:
                continue
            raw = bytes.fromhex(host)
            if v6:
                raw = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
                out.append(str(ipaddress.IPv6Address(raw)))
            else:
                out.append(str(ipaddress.IPv4Address(raw[::-1])))
    return out


def _http(url: str, method: str = "GET", headers: dict[str, str] | None = None, data: bytes | None = None) -> int:
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_rule06_listen_host_token_origin(tmp_path: Path) -> None:
    port = _free_port()
    env = {"OPPO_DATA_DIR": str(tmp_path / "data"), "OPPO_NO_BROWSER": "1", "PATH": "/usr/bin:/bin"}
    proc = subprocess.Popen([sys.executable, "-m", "oppo.cli", "serve", "--no-browser", "--port", str(port)],
                            cwd=str(APP_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                if _http(f"http://127.0.0.1:{port}/") == 200:
                    break
            except OSError:
                time.sleep(0.1)
        assert _http(f"http://127.0.0.1:{port}/") == 200
        addrs = _listening(port)
        assert addrs == ["127.0.0.1"], addrs
        lan = _lan_ip()
        if lan:
            with pytest.raises(OSError):
                urllib.request.urlopen(f"http://{lan}:{port}/", timeout=3)
        assert _http(f"http://127.0.0.1:{port}/", headers={"Host": "evil.example"}) == 400
        db = tmp_path / "data" / "oppo.sqlite3"
        before = sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM job").fetchone()[0]
        assert _http(f"http://127.0.0.1:{port}/jobs/compute", "POST", data=b"") == 403
        assert _http(f"http://127.0.0.1:{port}/jobs/compute", "POST", data=b"",
                     headers={"Origin": "http://evil.example", "X-Oppo-Token": "guess"}) == 403
        after = sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM job").fetchone()[0]
        assert before == after
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# ---- RULE-07 append-only ---------------------------------------------------------------------------


def test_rule07_append_only_tables(clone, h1a_done: Path) -> None:  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    app = open_dir(d)
    with app.engine.begin() as conn:
        cid = app.category_id()
        from oppo.core import ledger as LG

        snap = RK.latest_snapshot(conn, cid, "history")
        top = snap["content"]["rows"][0]
        LG.record_decision(conn, cid, "wen", "立项", top["segment_key"], top["segment"], "需求在涨最高", snap["id"])
    _close(app)
    db = sqlite3.connect(str(d / "oppo.sqlite3"))
    sha_before = db.execute("SELECT sha256, content_json FROM snapshot ORDER BY id").fetchall()
    for table in ("snapshot", "decision_record", "rule_version", "contract_version", "contract_item",
                  "category_version", "decision_card", "change_log"):
        n = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n > 0, table
        col = [r[1] for r in db.execute(f"PRAGMA table_info({table})")][1]
        with pytest.raises(sqlite3.DatabaseError, match="只追加"):
            db.execute(f"UPDATE {table} SET {col} = {col}")
        with pytest.raises(sqlite3.DatabaseError, match="只追加"):
            db.execute(f"DELETE FROM {table}")
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == n
    assert db.execute("SELECT sha256, content_json FROM snapshot ORDER BY id").fetchall() == sha_before
    for sha, content in sha_before:
        import hashlib

        assert hashlib.sha256(content.encode("utf-8")).hexdigest() == sha
    db.close()


# ---- RULE-09 jobs -----------------------------------------------------------------------------------


def test_rule09_single_job_and_rollback(clone, h1a_done: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    app = open_dir(d)
    gate = threading.Event()

    def slow_work(conn, report):  # type: ignore[no-untyped-def]
        report("等待", 0.1)
        gate.wait(10)
        return {"ok": True}

    with app.engine.begin() as conn:
        cid = app.category_id()
    jid = jobs.run(app.engine, cid, "compute", "wen", slow_work, background=True)
    try:
        with pytest.raises(jobs.JobBusy, match="正在运行"):
            SV.compute(app)
    finally:
        gate.set()
    for _ in range(100):
        with app.engine.begin() as conn:
            if not jobs.running(conn):
                break
        time.sleep(0.05)

    def counts() -> dict[str, int]:
        with app.engine.begin() as conn:
            return {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in
                    ("backtest_run", "decision_card", "snapshot", "rule_version", "compute_run", "signal_value")}

    before = counts()
    monkeypatch.setenv("OPPO_FAIL_AT", "backtest:after-evaluate")
    with pytest.raises(jobs.InjectedFailure):
        SV.backtest(app)
    monkeypatch.delenv("OPPO_FAIL_AT")
    assert counts() == before
    with app.engine.begin() as conn:
        last = jobs.latest(conn)
    assert last["status"] == "failed" and "注入的异常" in last["error"]

    # config change → 需重算, not recomputed automatically; 全部重算 clears it
    with app.engine.begin() as conn:
        cfg = CAT.current_version(conn, cid)["config"]
        cfg["success"]["bsr_max"] = 40
        CAT.save_version(conn, cid, cfg, "wen", "测试")
        run_ = CMP.latest_run(conn, cid, "history")
        assert any("品类配置" in r for r in CMP.stale_reasons(conn, cid, run_))
        n_runs = conn.execute(text("SELECT COUNT(*) FROM compute_run")).scalar()
    time.sleep(0.5)
    with app.engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM compute_run")).scalar() == n_runs
    SV.recompute(app)
    with app.engine.begin() as conn:
        assert CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, "history")) == []
        snaps = RK.snapshot_rows(conn, cid, "history")
    assert [s["seq"] for s in snaps][:2] == [2, 1]
    _close(app)
    assert jid

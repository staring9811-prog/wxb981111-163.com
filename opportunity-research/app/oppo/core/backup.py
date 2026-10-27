"""Automatic backup after export and restore (REQ-F10-04, AC-F10-06..08, NFR-002, DEC-008/024/033).

A backup is a SQLite file holding the ledger, strategy library, field contract, category config and all
confirmation records. It is written to a temporary name and renamed when complete, so a failure never leaves
a half-written file and never touches existing backups.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D

PREFIX = "机会判定台备份_"
SCOPE = ["台账", "策略库", "字段约定", "品类配置", "确认记录"]


def setting(conn: Connection) -> dict[str, Any] | None:
    row = conn.execute(select(D.backup_setting).where(D.backup_setting.c.id == 1)).mappings().first()
    return dict(row) if row else None


def free_space(path: str) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def check_writable(path: str) -> tuple[bool, str]:
    """Can a backup be written here? Creates the folder when its parent exists (NFR-002)."""
    p = Path(path)
    if not str(path).strip():
        return False, "请填写备份目录"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"不能写入：目录不存在且无法创建（{exc.strerror or exc}）。请换一个目录，或检查该目录的权限"
    if not p.is_dir():
        return False, "不能写入：这不是一个文件夹。请换一个目录"
    probe = p / f".oppo-probe-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        reason = "拒绝访问" if isinstance(exc, PermissionError) else (exc.strerror or str(exc))
        return False, f"不能写入：{reason}。请换一个目录，或检查该目录的权限"
    free = free_space(str(p))
    if free is not None and free < 50 * 1024 * 1024:
        return False, "不能写入：可用空间不足 50 MB。请换一个目录"
    return True, "可以写入"


def set_directory(conn: Connection, path: str, operator: str) -> tuple[bool, str]:
    """Save the backup folder after checking it again; a folder that cannot be written is not saved."""
    path = (path or "").strip()
    if not path:
        return False, "请填写备份目录"
    ok, msg = check_writable(path)
    if not ok:
        return False, msg
    now = clock.now_iso()
    conn.execute(text("DELETE FROM backup_setting WHERE id=1"))
    conn.execute(D.backup_setting.insert().values(id=1, directory=path, writable=1, checked_at=now,
                                                  updated_by=operator, updated_at=now))
    return True, msg


def records(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.backup_record).order_by(D.backup_record.c.id.desc())).mappings().all()
    return [dict(r) | {"scope": D.loads(r["scope_json"], []), "fps": D.loads(r["package_fps_json"], [])} for r in rows]


def last_success(conn: Connection) -> dict[str, Any] | None:
    row = conn.execute(select(D.backup_record).where(D.backup_record.c.status == "success")
                       .order_by(D.backup_record.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def last_attempt(conn: Connection) -> dict[str, Any] | None:
    row = conn.execute(select(D.backup_record).order_by(D.backup_record.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def _package_fps(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(text("SELECT label, fingerprint, kind FROM package WHERE conclusion != 'block' ORDER BY id"))
    return [{"label": r[0], "fingerprint": r[1], "kind": r[2]} for r in rows]


def run_backup(db_path: Path, conn: Connection, trigger: str, operator: str, category_id: int | None) -> dict[str, Any]:
    """Write a backup file. `conn` is used only to read settings and record the outcome."""
    st = setting(conn)
    now = clock.now()
    fps = _package_fps(conn)
    if not st or not st["directory"]:
        return _record(conn, category_id, None, None, trigger, fps, "failed", "未设置备份目录，请在“备份与恢复”中设置", operator)
    target_dir = Path(st["directory"])
    stamp = now.strftime("%Y%m%d_%H%M%S")
    final = target_dir / f"{PREFIX}{stamp}.sqlite"
    n = 1
    while final.exists():
        final = target_dir / f"{PREFIX}{stamp}_{n}.sqlite"
        n += 1
    tmp = target_dir / f".{final.name}.{uuid.uuid4().hex}.tmp"
    try:
        if not target_dir.is_dir():
            raise OSError("备份目录不存在")
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(tmp))
            try:
                src.backup(dst)
                keep = set(D.BACKUP_TABLES) | {"alembic_version"}
                names = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                for name in names:
                    if name not in keep and not name.startswith("sqlite_"):
                        dst.execute(f'DROP TABLE IF EXISTS "{name}"')
                dst.execute("CREATE TABLE backup_meta (key TEXT PRIMARY KEY, value TEXT)")
                dst.execute("INSERT INTO backup_meta VALUES ('created_at', ?)", (now.isoformat(sep=" "),))
                dst.execute("INSERT INTO backup_meta VALUES ('package_fingerprints', ?)", (D.dumps(fps),))
                dst.execute("INSERT INTO backup_meta VALUES ('trigger', ?)", (trigger,))
                dst.commit()
                dst.execute("VACUUM")
            finally:
                dst.close()
        finally:
            src.close()
        os.replace(tmp, final)
    except Exception as exc:  # noqa: BLE001 - recorded as the failure reason
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        reason = getattr(exc, "strerror", None) or str(exc)
        if isinstance(exc, (PermissionError, sqlite3.OperationalError)):
            reason = f"备份目录不可写（{reason}）"
        return _record(conn, category_id, None, None, trigger, fps, "failed", reason, operator)
    return _record(conn, category_id, str(final), final.stat().st_size, trigger, fps, "success", None, operator)


def _record(conn: Connection, category_id: int | None, path: str | None, size: int | None, trigger: str,
            fps: list[dict[str, Any]], status: str, error: str | None, operator: str) -> dict[str, Any]:
    now = clock.now_iso()
    bid = conn.execute(D.backup_record.insert().values(
        category_id=category_id, path=path, size=size, trigger=trigger, scope_json=D.dumps(SCOPE),
        package_fps_json=D.dumps(fps), status=status, error=error, created_by=operator, created_at=now,
    )).inserted_primary_key[0]
    last = last_success(conn)
    return {"id": int(bid), "status": status, "path": path, "size": size, "error": error, "time": now,
            "last_success": last["created_at"] if last else None}


def list_files(conn: Connection) -> list[dict[str, Any]]:
    """Backups found in the directory (newest first) joined with their records."""
    st = setting(conn)
    recs = {r["path"]: r for r in records(conn) if r["path"]}
    out = []
    if st and st["directory"] and Path(st["directory"]).is_dir():
        for f in sorted(Path(st["directory"]).glob(f"{PREFIX}*.sqlite"), reverse=True):
            r = recs.get(str(f))
            created = None
            try:
                c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
                created = c.execute("SELECT value FROM backup_meta WHERE key='created_at'").fetchone()[0]
                c.close()
            except sqlite3.Error:
                pass
            out.append({"path": str(f), "name": f.name, "size": f.stat().st_size, "created_at": created,
                        "trigger": r["trigger"] if r else "—", "fps": r["fps"] if r else []})
    return out


CONFIRM_SQL = ("SELECT (SELECT count(*) FROM change_log) + (SELECT count(*) FROM health_ack) + "
               "(SELECT count(*) FROM merge_suggestion WHERE status IN ('confirmed','rejected'))")


def _stats(scalar: Any) -> dict[str, Any]:
    """The five backed-up kinds of content, summarised the way the restore dialog compares them."""
    def q(sql: str) -> Any:
        try:
            return scalar(sql)
        except Exception:  # noqa: BLE001 - a table missing from an older backup counts as empty
            return None
    return {
        "snapshots": q("SELECT count(*) FROM snapshot") or 0,
        "decisions": q("SELECT count(*) FROM decision_record") or 0,
        "rules": q("SELECT count(*) FROM rule") or 0,
        "rule_updated": (q("SELECT max(created_at) FROM rule_version") or "")[:10] or None,
        "contract": q("SELECT max(version_no) FROM contract_version"),
        "config": q("SELECT max(version_no) FROM category_version"),
        "confirmations": q(CONFIRM_SQL) or 0,
    }


def current_stats(conn: Connection) -> dict[str, Any]:
    return _stats(lambda sql: conn.execute(text(sql)).scalar())


def file_stats(path: str | Path) -> dict[str, Any] | None:
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        return _stats(lambda sql: c.execute(sql).fetchone()[0])
    finally:
        c.close()


class RestoreError(Exception):
    pass


def restore(app: Any, backup_path: Path, confirm: bool) -> dict[str, Any]:
    """DEC-008: back up the current state first, then replace the backed-up tables with the backup's rows."""
    if not confirm:
        raise RestoreError("恢复需要二次确认")
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise RestoreError("备份文件不存在")
    try:
        bk = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        created = bk.execute("SELECT value FROM backup_meta WHERE key='created_at'").fetchone()[0]
        bk.close()
    except sqlite3.Error as exc:
        raise RestoreError(f"不是有效的备份文件：{exc}") from exc
    from oppo.core import jobs

    with app.engine.begin() as conn:
        cur = jobs.running(conn)
        if cur:
            raise RestoreError(f"{jobs.JOB_LABELS.get(cur['kind'], cur['kind'])}正在运行，完成后再试")
    with app.engine.begin() as conn:
        pre = run_backup(app.settings.db_path, conn, "恢复前", app.operator, None)
    if pre["status"] != "success":
        raise RestoreError(f"恢复前备份当前状态失败，未恢复：{pre['error']}")
    checked = 0
    # One explicit SQLite transaction on the driver connection: dropping and recreating the append-only
    # triggers, replacing the tables, the row-by-row check and the restore record either all happen or none do.
    with app.engine.connect() as conn:
        raw = conn.connection.driver_connection
        old_level = raw.isolation_level
        raw.isolation_level = None
        raw.execute("ATTACH DATABASE ? AS bk", (str(backup_path),))
        try:
            raw.execute("BEGIN IMMEDIATE")
            try:
                raw.execute("PRAGMA defer_foreign_keys=ON")  # references are checked once, at COMMIT
                for stmt in D.drop_trigger_sql():
                    raw.execute(stmt)
                for t in D.BACKUP_TABLES:
                    cols = [r[1] for r in raw.execute(f'PRAGMA bk.table_info("{t}")')]
                    raw.execute(f'DELETE FROM main."{t}"')
                    if cols:
                        collist = ", ".join(f'"{c}"' for c in cols)
                        raw.execute(f'INSERT INTO main."{t}" ({collist}) SELECT {collist} FROM bk."{t}"')
                for t in D.BACKUP_TABLES:  # NFR-002: check row by row before declaring success
                    cols = [r[1] for r in raw.execute(f'PRAGMA bk.table_info("{t}")')]
                    if not cols:
                        continue
                    collist = ", ".join(f'"{c}"' for c in cols)
                    n_main = raw.execute(f'SELECT count(*) FROM main."{t}"').fetchone()[0]
                    n_bk = raw.execute(f'SELECT count(*) FROM bk."{t}"').fetchone()[0]
                    diff = raw.execute(f'SELECT count(*) FROM (SELECT {collist} FROM main."{t}" EXCEPT '
                                       f'SELECT {collist} FROM bk."{t}")').fetchone()[0]
                    diff2 = raw.execute(f'SELECT count(*) FROM (SELECT {collist} FROM bk."{t}" EXCEPT '
                                        f'SELECT {collist} FROM main."{t}")').fetchone()[0]
                    if n_main != n_bk or diff or diff2:
                        raise RestoreError(f"恢复后核对不一致（{t}），已撤销恢复，当前数据保持恢复前的状态")
                    checked += n_bk
                for stmt in D.trigger_sql():
                    raw.execute(stmt)
                raw.execute("INSERT INTO restore_record (backup_path, backup_time, pre_backup_id, created_by, created_at)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (str(backup_path), created, pre["id"], app.operator, clock.now_iso()))
                raw.execute("COMMIT")
            except Exception as exc:
                raw.execute("ROLLBACK")
                if isinstance(exc, RestoreError):
                    raise
                raise RestoreError(f"恢复失败，已撤销，当前数据保持恢复前的状态：{exc}") from exc
        finally:
            raw.execute("DETACH DATABASE bk")
            raw.isolation_level = old_level
    return {"restored_from": str(backup_path), "backup_time": created, "pre_backup": pre, "checked_rows": checked}


def last_restore(conn: Connection) -> dict[str, Any] | None:
    row = conn.execute(select(D.restore_record).order_by(D.restore_record.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def parse_time(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None

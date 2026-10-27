"""Field contract (F02: REQ-F02-01..03, AC-F02-01..07, DEC-021)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import spec as S

ATTRS = ("meaning", "grain", "timing", "snapshot_date", "nature", "usage", "rule_text", "dtype", "status", "source")
ATTR_LABELS = {"meaning": "含义", "grain": "粒度", "timing": "时点", "snapshot_date": "快照日期", "nature": "性质",
               "usage": "建议用法", "rule_text": "规则", "dtype": "类型", "status": "确认状态", "source": "确认来源"}
FILE_ORDER = {c: i for i, c in enumerate(("C1", "C2", "C3", "C4", "C5", "C6", "C7"))}


class ContractError(Exception):
    pass


def contract_code(file_code: str) -> str:
    return S.CONTRACT_FILE.get(file_code, file_code)


def current_version(conn: Connection, category_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.contract_version).where(D.contract_version.c.category_id == category_id)
                       .order_by(D.contract_version.c.version_no.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def version_items(conn: Connection, version_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.contract_item).where(D.contract_item.c.version_id == version_id)).mappings().all()
    return [dict(r) for r in rows]


def _key(item: dict[str, Any]) -> tuple[str, str]:
    return item["file_code"], item["field"]


def draft_items(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.contract_draft_item).where(D.contract_draft_item.c.category_id == category_id)
                        ).mappings().all()
    items = [dict(r) for r in rows]
    items.sort(key=lambda i: (0 if i["status"] == "pending" else 1, 0 if i["change_kind"] else 1,
                              FILE_ORDER.get(i["file_code"], 9), i["id"]))
    return items


def on_import(conn: Connection, category_id: int, package_id: int, operator: str) -> dict[str, list[str]]:
    """Refresh the draft for a newly imported package: only changed fields become pending (AC-F02-06)."""
    cur = current_version(conn, category_id)
    base = {(_key(i)): i for i in version_items(conn, cur["id"])} if cur else {}
    existing = {(_key(i)): i for i in draft_items(conn, category_id)}
    pkg_fields = conn.execute(select(D.package_field.c.file_code, D.package_field.c.field, D.package_field.c.dtype)
                              .where(D.package_field.c.package_id == package_id)).all()
    seen: dict[tuple[str, str], str] = {}
    for fc, fname, dtype in pkg_fields:
        seen[(contract_code(fc), fname)] = dtype
    present_files = {k[0] for k in seen}
    changes: dict[str, list[str]] = {"新增": [], "类型改变": [], "缺少": []}
    now = clock.now_iso()
    wanted: dict[tuple[str, str], dict[str, Any]] = {}
    for key, dtype in seen.items():
        if key in base and base[key]["dtype"] == dtype:
            src = existing.get(key) if existing.get(key) and existing[key]["dtype"] == dtype else base[key]
            item = {a: src.get(a) for a in ATTRS}
            item["confirmed_in"] = src.get("confirmed_in")
            item["change_kind"] = src.get("change_kind") if src is existing.get(key) else None
        elif key in base:
            item = {**S.default_draft(key[0], key[1], dtype), "status": "pending", "source": None,
                    "snapshot_date": None, "confirmed_in": None, "change_kind": "类型改变"}
            changes["类型改变"].append(f"{key[0]} {key[1]}")
        else:
            prev = existing.get(key)
            if prev and prev["dtype"] == dtype:
                item = {a: prev.get(a) for a in ATTRS}
                item["confirmed_in"] = prev.get("confirmed_in")
                item["change_kind"] = prev.get("change_kind") or ("新增" if cur else None)
            else:
                item = {**S.default_draft(key[0], key[1], dtype), "status": "pending", "source": None,
                        "snapshot_date": None, "confirmed_in": None, "change_kind": "新增" if cur else None}
            if cur:
                changes["新增"].append(f"{key[0]} {key[1]}")
        if item.get("timing") == "快照" and not item.get("snapshot_date"):
            item["snapshot_date"] = None
        wanted[key] = item
    # "缺少" compares with the previous package of the same type, so a cross-section package does not
    # flag history-only optional fields (DEC-021 shares one contract between both types).
    kind = conn.execute(select(D.package.c.kind).where(D.package.c.id == package_id)).scalar()
    prev = conn.execute(select(D.package.c.id).where(
        D.package.c.category_id == category_id, D.package.c.kind == kind, D.package.c.id < package_id,
        D.package.c.conclusion != "block").order_by(D.package.c.id.desc()).limit(1)).scalar()
    prev_fields: set[tuple[str, str]] = set()
    if prev:
        prev_fields = {(contract_code(fc), f) for fc, f in conn.execute(
            select(D.package_field.c.file_code, D.package_field.c.field).where(D.package_field.c.package_id == prev))}
    for key, bitem in base.items():
        if key in wanted:
            continue
        if key[0] in present_files and key in prev_fields:
            item = {a: bitem.get(a) for a in ATTRS}
            item.update(status="pending", source=None, change_kind="缺少", confirmed_in=bitem.get("confirmed_in"))
            changes["缺少"].append(f"{key[0]} {key[1]}")
        else:
            prev = existing.get(key, bitem)
            item = {a: prev.get(a) for a in ATTRS}
            item.update(confirmed_in=prev.get("confirmed_in"), change_kind=prev.get("change_kind"))
        wanted[key] = item
    # Draft fields that only exist in a package of the other type (e.g. C6 when a cross-section package is
    # imported before the history contract is saved) stay in the draft with their own package and evidence.
    kinds = dict(conn.execute(select(D.package.c.id, D.package.c.kind).where(D.package.c.category_id == category_id)).all())
    for key, ex in existing.items():
        if key in wanted:
            continue
        if key[0] not in present_files or kinds.get(ex["package_id"]) != kind:
            item = {a: ex.get(a) for a in ATTRS}
            item.update(confirmed_in=ex.get("confirmed_in"), change_kind=ex.get("change_kind"), _pkg=ex["package_id"],
                        _updated=ex.get("updated_at"))
            wanted[key] = item
    conn.execute(text("DELETE FROM contract_draft_item WHERE category_id=:c"), {"c": category_id})
    for (fc, fname), item in wanted.items():
        pkg_of = item.pop("_pkg", package_id)
        updated = item.pop("_updated", None) or now
        conn.execute(D.contract_draft_item.insert().values(
            category_id=category_id, file_code=fc, field=fname, package_id=pkg_of, updated_at=updated, **item))
    return changes


def _field_index(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(_key(i)): i for i in items}


def update_draft(conn: Connection, category_id: int, file_code: str, fieldname: str, values: dict[str, Any],
                 confirm: bool, source: str) -> None:
    row = conn.execute(select(D.contract_draft_item).where(
        D.contract_draft_item.c.category_id == category_id, D.contract_draft_item.c.file_code == file_code,
        D.contract_draft_item.c.field == fieldname)).mappings().first()
    if row is None:
        raise ContractError(f"没有字段 {file_code} {fieldname}")
    upd = {k: v for k, v in values.items() if k in ATTRS and k not in ("status", "source", "dtype")}
    if "meaning" in upd and not (upd["meaning"] or "").strip():
        raise ContractError("请填写含义")
    timing = upd.get("timing", row["timing"])
    if timing == "快照" and not (upd.get("snapshot_date", row["snapshot_date"]) or "").strip():
        raise ContractError("请填写快照日期")
    if timing != "快照":
        upd["snapshot_date"] = None
    if confirm:
        upd["status"] = "confirmed"
        upd["source"] = source
    upd["updated_at"] = clock.now_iso()
    conn.execute(D.contract_draft_item.update().where(D.contract_draft_item.c.id == row["id"]).values(**upd))


def batch_confirm(conn: Connection, category_id: int, keys: list[tuple[str, str]] | None = None,
                  suggested_only: bool = False) -> int:
    """按建议批量确认 (AC-F02-03). keys=None means every pending field; returns count confirmed."""
    items = draft_items(conn, category_id)
    n = 0
    wanted = set(keys) if keys is not None else None
    for it in items:
        if it["status"] == "confirmed":
            continue
        if wanted is not None and _key(it) not in wanted:
            continue
        if suggested_only and it["usage"] != "直接用":
            continue
        conn.execute(D.contract_draft_item.update().where(D.contract_draft_item.c.id == it["id"]).values(
            status="confirmed", source="批量确认", updated_at=clock.now_iso()))
        n += 1
    return n


def draft_changes(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    cur = current_version(conn, category_id)
    base = _field_index(version_items(conn, cur["id"])) if cur else {}
    out = []
    for it in draft_items(conn, category_id):
        b = base.get(_key(it))
        if b is None:
            if it["status"] == "confirmed" or not cur:
                out.append({"key": _key(it), "before": None, "after": {a: it[a] for a in ATTRS}, "new": True})
            continue
        diff = {a: (b.get(a), it.get(a)) for a in ATTRS if (b.get(a) or None) != (it.get(a) or None)}
        if diff:
            out.append({"key": _key(it), "before": {a: v[0] for a, v in diff.items()},
                        "after": {a: v[1] for a, v in diff.items()}, "new": False})
    return out


def save_version(conn: Connection, category_id: int, operator: str, note: str = "") -> int:
    """Save the draft as a new contract version (AC-F02-02); returns the version number."""
    from oppo.core import jobs

    if jobs.running(conn):
        raise ContractError("计算任务正在运行，完成后再保存")
    changes = draft_changes(conn, category_id)
    if not changes:
        raise ContractError("草稿没有修改")
    cur = current_version(conn, category_id)
    no = (cur["version_no"] if cur else 0) + 1
    now = clock.now_iso()
    vid = conn.execute(D.contract_version.insert().values(
        category_id=category_id, version_no=no, package_id=_draft_package(conn, category_id), note=note or None,
        created_by=operator, created_at=now)).inserted_primary_key[0]
    changed_keys = {c["key"] for c in changes}
    for it in draft_items(conn, category_id):
        confirmed_in = it["confirmed_in"]
        if it["status"] == "confirmed" and (_key(it) in changed_keys or confirmed_in is None):
            confirmed_in = no
        conn.execute(D.contract_item.insert().values(
            version_id=vid, file_code=it["file_code"], field=it["field"],
            **{a: it[a] for a in ATTRS}, confirmed_in=confirmed_in if it["status"] == "confirmed" else None,
            created_by=operator, created_at=now))
        conn.execute(D.contract_draft_item.update().where(D.contract_draft_item.c.id == it["id"]).values(
            confirmed_in=confirmed_in if it["status"] == "confirmed" else None,
            change_kind=None if it["status"] == "confirmed" else it["change_kind"]))
    for ch in changes:
        fc, fname = ch["key"]
        conn.execute(D.change_log.insert().values(
            category_id=category_id, object="字段约定", object_id=f"v{no}", action="保存新版本",
            item=f"{fc} {fname}", before=D.dumps(ch["before"]) if ch["before"] is not None else D.dumps("新增字段"),
            after=D.dumps(ch["after"]), created_by=operator, created_at=now))
    return no


def _draft_package(conn: Connection, category_id: int) -> int | None:
    row = conn.execute(select(D.contract_draft_item.c.package_id).where(
        D.contract_draft_item.c.category_id == category_id).order_by(D.contract_draft_item.c.package_id.desc())
        .limit(1)).first()
    return row[0] if row else None


def history(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    vers = conn.execute(select(D.contract_version).where(D.contract_version.c.category_id == category_id)
                        .order_by(D.contract_version.c.version_no.desc())).mappings().all()
    out = []
    for v in vers:
        logs = conn.execute(select(D.change_log).where(
            D.change_log.c.category_id == category_id, D.change_log.c.object == "字段约定",
            D.change_log.c.object_id == f"v{v['version_no']}").order_by(D.change_log.c.id)).mappings().all()
        out.append({**dict(v), "changes": [dict(lg) for lg in logs]})
    return out


def usable_fields(conn: Connection, category_id: int, package_id: int) -> dict[str, Any]:
    """Confirmed fields, excluded (unconfirmed) fields and snapshot fields for one computation."""
    cur = current_version(conn, category_id)
    items = _field_index(version_items(conn, cur["id"])) if cur else {}
    pkg_fields = conn.execute(select(D.package_field.c.file_code, D.package_field.c.field)
                              .where(D.package_field.c.package_id == package_id)).all()
    confirmed: set[tuple[str, str]] = set()
    excluded: list[dict[str, str]] = []
    snapshot: list[dict[str, str]] = []
    for fc, fname in pkg_fields:
        key = (contract_code(fc), fname)
        it = items.get(key)
        if it is None or it["status"] != "confirmed":
            excluded.append({"file": key[0], "field": fname, "file_label": S.FILE_NAMES.get(key[0], key[0])})
            continue
        confirmed.add(key)
        if it.get("timing") == "快照":
            snapshot.append({"file": fc, "field": fname, "file_label": S.FILE_NAMES.get(fc, fc),
                             "note": it.get("meaning") or ""})
    return {"version": cur, "confirmed": confirmed, "excluded": excluded, "snapshot": snapshot}


REQUIRED_FOR_COMPUTE = {
    "history": [("C1", "月份"), ("C1", "子ASIN"), ("C1", "子体月销量"), ("C1", "子体月销售额"), ("C1", "小类BSR"),
                ("C2", "子ASIN"), ("C2", "上架日期"), ("C3", "月份"), ("C3", "子ASIN"), ("C3", "子体月销量"),
                ("C3", "子体月销售额"), ("C3", "小类BSR")],
    "cross": [("C1", "月份"), ("C1", "子ASIN"), ("C1", "子体月销量"), ("C1", "子体月销售额"), ("C1", "小类BSR"),
              ("C2", "子ASIN"), ("C2", "上架日期"), ("C3", "月份"), ("C3", "子ASIN"), ("C3", "子体月销量"),
              ("C3", "子体月销售额"), ("C3", "小类BSR")],
}


def pending_count(conn: Connection, category_id: int) -> int:
    return sum(1 for it in draft_items(conn, category_id) if it["status"] != "confirmed")


def confirm_started_at(conn: Connection, category_id: int) -> str | None:
    """Start of the current 字段确认 step: the earliest draft change since the last saved version."""
    cur = current_version(conn, category_id)
    since = cur["created_at"] if cur else ""
    row = conn.execute(text("SELECT MIN(updated_at) FROM contract_draft_item WHERE category_id=:c AND updated_at > :s"),
                       {"c": category_id, "s": since or ""}).first()
    return row[0] if row and row[0] else None


def evidence(conn: Connection, package_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    """Field evidence recorded at import (non-null share, example, same-value-across-months share)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for fc, fname, dtype, ev in conn.execute(select(D.package_field.c.file_code, D.package_field.c.field,
                                                    D.package_field.c.dtype, D.package_field.c.evidence_json)
                                             .where(D.package_field.c.package_id == package_id)):
        out[(contract_code(fc), fname)] = {"dtype": dtype, "file": fc, **(D.loads(ev, {}) or {})}
    return out

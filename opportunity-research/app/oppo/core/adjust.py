"""Reviewed data adjustments over an imported package.

The package rows (raw_c1 … raw_c4) and the read-only copy stay exactly as imported. An adjustment names one
value — file, child (and month), field — and the value it should take. Proposals come from Codex through the
local API or from a person; they apply only after a person confirms them (as proposed or edited). Confirmed
adjustments are layered on when the package is read (DATA.load), so checks, computing and backtests see the
reviewed data while the source can always be compared and every adjustment withdrawn.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import data as DATA
from oppo.core import packages as PK
from oppo.core import spec as S

PENDING, CONFIRMED, REJECTED, WITHDRAWN, REVOKED = "待审核", "已确认", "已驳回", "已撤回", "已撤销"
STATUSES = (PENDING, CONFIRMED, REJECTED, WITHDRAWN, REVOKED)
STATUS_SUFFIX = "证据状态"
MAX_ITEMS = 5000

# contract file → raw table short name; files keyed by child × month take an optional month
FILES = {"C1": "c1", "S1": "c1", "C2": "c2", "S2": "c2", "C3": "c3", "S3": "c3", "C4": "c4"}
MONTHLY = {"C1", "S1", "C3", "S3"}
KIND_FILES = {"history": ("C1", "C2", "C3", "C4"), "cross": ("S1", "S2", "S3", "C4")}
_SPECS = {"c1": (S.C1_FIELDS, S.C1_OPTIONAL), "c2": (S.C2_FIELDS, S.C2_OPTIONAL), "c3": (S.C3_FIELDS, S.C3_OPTIONAL)}


class AdjustError(Exception):
    pass


# ---- fields ---------------------------------------------------------------------------------


def _col_of(short: str) -> dict[str, str]:
    """contract field name → raw column, for the adjustable (non-key) fields of a file."""
    return {fname: col for col, fname in DATA.FIELD_MAP[short].items() if col not in DATA.KEY_COLS}


def field_types(file_code: str, dims: list[str]) -> dict[str, str]:
    """Adjustable fields of a file and their contract types."""
    short = FILES[file_code]
    if short == "c4":
        out = {}
        for d in dims:
            out[d] = S.TEXT
            out[f"{d}{STATUS_SUFFIX}"] = S.TEXT
        return out
    req, opt = _SPECS[short]
    cols = _col_of(short)
    return {f: t for f, t in {**req, **opt}.items() if f in cols}


def _dims(conn: Connection, package_id: int) -> list[str]:
    rows = conn.execute(text("SELECT DISTINCT dim FROM raw_c4 WHERE package_id=:p"), {"p": package_id}).all()
    from oppo.core import categories as CAT

    pkg = PK.get(conn, package_id)
    cfg = CAT.current_version(conn, pkg["category_id"])["config"] if pkg else {}
    out = list(cfg.get("attribute_dims") or S.C4_DIMS)
    for (d,) in rows:
        if d and d not in out:
            out.append(d)
    return out


def files_of(conn: Connection, package_id: int) -> dict[str, dict[str, str]]:
    """{file_code: {field: type}} the package can be adjusted on."""
    pkg = PK.get(conn, package_id)
    if pkg is None:
        raise AdjustError("数据包不存在")
    dims = _dims(conn, package_id)
    return {fc: field_types(fc, dims) for fc in KIND_FILES[pkg["kind"]]}


def parse_value(raw: Any, dtype: str, field: str) -> Any:
    """Typed value as it is stored in the raw tables; '' / None clears the value."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    if field.endswith(STATUS_SUFFIX):
        if s not in S.EVIDENCE_STATES:
            raise AdjustError(f"“{field}”只能是 {' / '.join(S.EVIDENCE_STATES)}")
        return s
    parser = PK.PARSERS.get(dtype)
    if parser is None:
        return s
    v = parser(s)
    if v is None:
        raise AdjustError(f"“{field}”的值“{s}”不是{dtype}")
    return v


def _show(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---- source values --------------------------------------------------------------------------


def source_values(conn: Connection, package_id: int, file_code: str, child: str, month: str | None,
                  field: str) -> list[Any] | None:
    """The imported values a target covers (one per matching row); None when the row does not exist."""
    short = FILES[file_code]
    if short == "c4":
        if field.endswith(STATUS_SUFFIX):
            dim, col = field[: -len(STATUS_SUFFIX)], "status"
        else:
            dim, col = field, "value"
        exists = conn.execute(text("SELECT 1 FROM raw_c4 WHERE package_id=:p AND child=:c LIMIT 1"),
                              {"p": package_id, "c": child}).first()
        if not exists:
            return None
        row = conn.execute(text(f"SELECT {col} FROM raw_c4 WHERE package_id=:p AND child=:c AND dim=:d"),
                           {"p": package_id, "c": child, "d": dim}).first()
        return [row[0] if row else None]
    col = _col_of(short)[field]
    sql = f"SELECT {col} FROM raw_{short} WHERE package_id=:p AND child=:c"
    args: dict[str, Any] = {"p": package_id, "c": child}
    if month and file_code in MONTHLY:
        sql += " AND month=:m"
        args["m"] = month
    rows = conn.execute(text(sql), args).all()
    return [r[0] for r in rows] if rows else None


def _summary(values: list[Any]) -> str | None:
    shown = list(dict.fromkeys(_show(v) for v in values))
    if len(shown) == 1:
        return shown[0]
    return "多个值：" + "、".join(s if s is not None else "空" for s in shown[:5]) + ("…" if len(shown) > 5 else "")


# ---- writes ---------------------------------------------------------------------------------


def _next_code(conn: Connection, prefix: str, column: str) -> str:
    rows = conn.execute(text(f"SELECT {column} FROM data_adjustment WHERE {column} LIKE :p"),
                        {"p": f"{prefix}-%"}).all()
    n = max([int(r[0].split("-")[1]) for r in rows if r[0] and r[0].split("-")[1].isdigit()] or [0])
    return n + 1


def _log(conn: Connection, category_id: int, code: str, action: str, before: Any, after: Any, operator: str) -> None:
    conn.execute(D.change_log.insert().values(
        category_id=category_id, object="数据调整", object_id=code, action=action, item=code,
        before=D.dumps(before), after=D.dumps(after), created_by=operator, created_at=clock.now_iso()))


def _norm_month(m: Any) -> str | None:
    if m is None or str(m).strip() == "":
        return None
    v = PK.month_of(str(m).strip().replace("-", "").replace("/", ""))
    if v is None:
        raise AdjustError(f"月份“{m}”格式不对，用 YYYYMM 或 YYYY-MM")
    return v


def propose(conn: Connection, category_id: int, package_id: int, items: list[dict[str, Any]], source: str,
            operator: str) -> dict[str, Any]:
    """Record proposals as 待审核. Each item: file, child, month (optional), field, value, reason.

    A new proposal for the same value replaces the earlier pending one (that one becomes 已撤回). Items that fail
    validation are reported back with their index and are not recorded.
    """
    pkg = PK.get(conn, package_id)
    if pkg is None or pkg["category_id"] != category_id:
        raise AdjustError("数据包不存在")
    if not items:
        raise AdjustError("没有要提交的调整")
    if len(items) > MAX_ITEMS:
        raise AdjustError(f"一次最多提交 {MAX_ITEMS} 条，请分批提交")
    source = (str(source or "").strip() or "手工")[:32]
    files = files_of(conn, package_id)
    now = clock.now_iso()
    batch_no = _next_code(conn, "B", "batch")
    batch = f"B-{batch_no:04d}"
    n = _next_code(conn, "A", "code")
    created, errors = [], []
    for i, it in enumerate(items):
        try:
            fc = str(it.get("file") or "").strip().upper()
            if fc not in files:
                raise AdjustError(f"这个数据包不能调整文件“{fc}”，可调整：{'、'.join(files)}")
            child = str(it.get("child") or "").strip()
            if not child:
                raise AdjustError("缺少子 ASIN")
            month = _norm_month(it.get("month")) if fc in MONTHLY else None
            field = str(it.get("field") or "").strip()
            if field not in files[fc]:
                raise AdjustError(f"文件 {fc} 没有可调整字段“{field}”")
            value = parse_value(it.get("value"), files[fc][field], field)
            src = source_values(conn, package_id, fc, child, month, field)
            if src is None:
                raise AdjustError(f"{fc} 里没有子 ASIN {child}" + (f" 的 {month} 月数据" if month else ""))
            old = _summary(src)
            reason = str(it.get("reason") or "").strip() or None
            target = dict(package_id=package_id, file_code=fc, child=child, field=field)
            q = select(D.data_adjustment.c.id, D.data_adjustment.c.code).where(
                *[getattr(D.data_adjustment.c, k) == v for k, v in target.items()],
                D.data_adjustment.c.status == PENDING,
                D.data_adjustment.c.month.is_(None) if month is None else D.data_adjustment.c.month == month)
            code = f"A-{n:05d}"
            n += 1
            for prev in conn.execute(q).mappings().all():
                conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == prev["id"]).values(
                    status=WITHDRAWN, decided_by=operator, decided_at=now, decision_note=f"被 {code} 取代"))
                _log(conn, category_id, prev["code"], "撤回（被新提议取代）", PENDING, WITHDRAWN, operator)
            conn.execute(D.data_adjustment.insert().values(
                category_id=category_id, code=code, batch=batch, month=month, old_value=old,
                proposed_value=_show(value), reason=reason, source=source, status=PENDING,
                created_by=operator, created_at=now, **target))
            _log(conn, category_id, code, "提交", {"值": old}, {"值": _show(value), "来源": source}, operator)
            created.append(code)
        except AdjustError as exc:
            errors.append({"index": i, "error": str(exc)})
    return {"batch": batch if created else None, "created": created, "errors": errors}


def _rows(conn: Connection, ids: list[int] | None = None, codes: list[str] | None = None) -> list[dict[str, Any]]:
    q = select(D.data_adjustment)
    if ids is not None:
        q = q.where(D.data_adjustment.c.id.in_(ids))
    if codes is not None:
        q = q.where(D.data_adjustment.c.code.in_(codes))
    return [dict(r) for r in conn.execute(q.order_by(D.data_adjustment.c.id)).mappings().all()]


def decide(conn: Connection, category_id: int, codes: list[str], decision: str, operator: str,
           values: dict[str, Any] | None = None, note: str = "") -> dict[str, Any]:
    """People only: confirm (optionally with an edited value per code) or reject pending proposals."""
    if decision not in ("confirm", "reject"):
        raise AdjustError("操作无效")
    values = values or {}
    now = clock.now_iso()
    done, skipped, touched = [], [], set()
    for r in _rows(conn, codes=codes):
        if r["category_id"] != category_id or r["status"] != PENDING:
            skipped.append(r["code"])
            continue
        if decision == "reject":
            conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == r["id"]).values(
                status=REJECTED, decided_by=operator, decided_at=now, decision_note=note or None))
            _log(conn, category_id, r["code"], "驳回", PENDING, REJECTED, operator)
            done.append(r["code"])
            continue
        final = r["proposed_value"]
        edited = r["code"] in values
        if edited:
            dtype = files_of(conn, r["package_id"])[r["file_code"]][r["field"]]
            final = _show(parse_value(values[r["code"]], dtype, r["field"]))
        # an earlier confirmed value for the same target is superseded
        q = select(D.data_adjustment.c.id, D.data_adjustment.c.code).where(
            D.data_adjustment.c.package_id == r["package_id"], D.data_adjustment.c.file_code == r["file_code"],
            D.data_adjustment.c.child == r["child"], D.data_adjustment.c.field == r["field"],
            D.data_adjustment.c.status == CONFIRMED,
            D.data_adjustment.c.month.is_(None) if r["month"] is None else D.data_adjustment.c.month == r["month"])
        for prev in conn.execute(q).mappings().all():
            conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == prev["id"]).values(
                status=REVOKED, decision_note=f"被 {r['code']} 取代"))
            _log(conn, category_id, prev["code"], "撤销（被新确认取代）", CONFIRMED, REVOKED, operator)
        conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == r["id"]).values(
            status=CONFIRMED, final_value=final, decided_by=operator, decided_at=now,
            decision_note=(note or ("确认时改为“" + (final or "空") + "”" if edited else None))))
        _log(conn, category_id, r["code"], "确认（改值）" if edited else "确认", {"提议": r["proposed_value"]},
             {"生效": final}, operator)
        done.append(r["code"])
        touched.add(r["package_id"])
    return {"done": done, "skipped": skipped, "packages": sorted(touched)}


def revoke(conn: Connection, category_id: int, codes: list[str], operator: str, note: str = "") -> dict[str, Any]:
    """People only: take back confirmed adjustments; the imported value applies again."""
    now = clock.now_iso()
    done, skipped, touched = [], [], set()
    for r in _rows(conn, codes=codes):
        if r["category_id"] != category_id or r["status"] != CONFIRMED:
            skipped.append(r["code"])
            continue
        conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == r["id"]).values(
            status=REVOKED, decision_note=note or f"{operator} 于 {now[:16]} 撤销"))
        _log(conn, category_id, r["code"], "撤销", CONFIRMED, REVOKED, operator)
        done.append(r["code"])
        touched.add(r["package_id"])
    return {"done": done, "skipped": skipped, "packages": sorted(touched)}


def withdraw(conn: Connection, category_id: int, codes: list[str], operator: str) -> dict[str, Any]:
    """The proposer takes back proposals that are still pending."""
    now = clock.now_iso()
    done, skipped = [], []
    for r in _rows(conn, codes=codes):
        if r["category_id"] != category_id or r["status"] != PENDING:
            skipped.append(r["code"])
            continue
        conn.execute(D.data_adjustment.update().where(D.data_adjustment.c.id == r["id"]).values(
            status=WITHDRAWN, decided_by=operator, decided_at=now, decision_note="提议方撤回"))
        _log(conn, category_id, r["code"], "撤回", PENDING, WITHDRAWN, operator)
        done.append(r["code"])
    return {"done": done, "skipped": skipped}


# ---- reads ----------------------------------------------------------------------------------


def listing(conn: Connection, category_id: int, package_id: int | None = None, status: str | None = None,
            file_code: str | None = None, field: str | None = None, source: str | None = None,
            child: str | None = None, batch: str | None = None, limit: int | None = None,
            offset: int = 0) -> list[dict[str, Any]]:
    t = D.data_adjustment
    q = select(t).where(t.c.category_id == category_id)
    for col, v in ((t.c.package_id, package_id), (t.c.status, status), (t.c.file_code, file_code),
                   (t.c.field, field), (t.c.source, source), (t.c.child, child), (t.c.batch, batch)):
        if v not in (None, ""):
            q = q.where(col == v)
    q = q.order_by(t.c.id.desc())
    if limit:
        q = q.limit(limit).offset(offset)
    return [dict(r) for r in conn.execute(q).mappings().all()]


def counts(conn: Connection, category_id: int, package_id: int | None = None) -> dict[str, int]:
    sql = "SELECT status, COUNT(*) FROM data_adjustment WHERE category_id=:c"
    args: dict[str, Any] = {"c": category_id}
    if package_id is not None:
        sql += " AND package_id=:p"
        args["p"] = package_id
    got = dict(conn.execute(text(sql + " GROUP BY status"), args).all())
    return {s: int(got.get(s, 0)) for s in STATUSES}


def confirmed(conn: Connection, package_id: int) -> list[dict[str, Any]]:
    t = D.data_adjustment
    rows = conn.execute(select(t).where(t.c.package_id == package_id, t.c.status == CONFIRMED)
                        .order_by(t.c.decided_at, t.c.id)).mappings().all()
    return [dict(r) for r in rows]


def adjust_hash(conn: Connection, package_id: int) -> str:
    """'' when nothing is confirmed, so results computed before this feature existed stay current."""
    rows = confirmed(conn, package_id)
    if not rows:
        return ""
    body = D.dumps([[r["code"], r["final_value"]] for r in rows])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---- apply ----------------------------------------------------------------------------------


def apply(conn: Connection, package_id: int, frames: dict[str, pd.DataFrame], c4: pd.DataFrame) -> pd.DataFrame:
    """Layer confirmed adjustments onto freshly read package frames (in place); returns the C4 frame."""
    rows = confirmed(conn, package_id)
    if not rows:
        return c4
    types: dict[str, dict[str, str]] = {}
    add4: dict[tuple[str, str], dict[str, Any]] = {}  # (child, dim) rows the package did not label
    for r in rows:
        fc, field = r["file_code"], r["field"]
        if fc not in types:
            types[fc] = files_of(conn, package_id)[fc]
        dtype = types[fc].get(field)
        if dtype is None:
            continue
        value = parse_value(r["final_value"], dtype, field)
        short = FILES[fc]
        if short == "c4":
            is_status = field.endswith(STATUS_SUFFIX)
            dim = field[: -len(STATUS_SUFFIX)] if is_status else field
            col = "status" if is_status else "value"
            mask = (c4["child"] == r["child"]) & (c4["dim"] == dim) if len(c4) else None
            if mask is not None and mask.any():
                c4.loc[mask, col] = value
            else:
                row = add4.setdefault((r["child"], dim), {"package_id": package_id, "row_no": 0, "extra_json": None,
                                                          "child": r["child"], "dim": dim, "value": None,
                                                          "status": None})
                row[col] = value
            continue
        df = frames.get(short)
        if df is None or df.empty:
            continue
        col = _col_of(short)[field]
        mask = df["child"] == r["child"]
        if r["month"] and "month" in df.columns:
            mask &= df["month"] == r["month"]
        if col not in df.columns:
            df[col] = None
        if df[col].dtype != object and not isinstance(value, (int, float)):
            df[col] = df[col].astype(object)
        df.loc[mask, col] = value
    if add4:
        extra = pd.DataFrame(list(add4.values()))
        c4 = pd.concat([c4, extra], ignore_index=True) if len(c4) else extra
    return c4


def effective_rows(conn: Connection, package_id: int, file_code: str, child: str | None = None,
                   month: str | None = None, filters: dict[str, str] | None = None, limit: int = 100,
                   offset: int = 0) -> dict[str, Any]:
    """Rows of one file with imported and effective (after confirmed adjustments) values, for review and the API."""
    files = files_of(conn, package_id)
    if file_code not in files:
        raise AdjustError(f"这个数据包没有可读的文件“{file_code}”，可读：{'、'.join(files)}")
    short = FILES[file_code]
    limit = max(1, min(int(limit or 100), 1000))
    raw = DATA._read(conn, f"raw_{short}", package_id)
    adj = DATA._read(conn, f"raw_{short}", package_id)
    if short == "c4":
        eff = apply(conn, package_id, {}, adj)
        src = DATA.attr_table(raw)
        out_eff = DATA.attr_table(eff)
        def wide(t: pd.DataFrame) -> pd.DataFrame:
            t = t.rename(columns={c: (c[:-8] + STATUS_SUFFIX if c.endswith("__status") else c) for c in t.columns})
            return t.rename(columns={"child": "子ASIN"})
        src, out_eff = wide(src), wide(out_eff)
        key = ["子ASIN"]
    else:
        frames = {short: adj}
        apply(conn, package_id, frames, pd.DataFrame())
        names = {col: f for col, f in DATA.FIELD_MAP[short].items()}
        keep = [c for c in names if c in raw.columns]
        src = raw[keep].rename(columns=names)
        out_eff = frames[short][keep].rename(columns=names)
        key = ["子ASIN", "月份"] if "月份" in src.columns else ["子ASIN"]
    mask = pd.Series(True, index=out_eff.index)
    if child:
        mask &= out_eff["子ASIN"] == child
    if month and "月份" in out_eff.columns:
        mask &= out_eff["月份"] == (_norm_month(month) or month)
    for f, v in (filters or {}).items():
        if f not in out_eff.columns:
            raise AdjustError(f"没有字段“{f}”")
        if v in ("", "空"):
            mask &= out_eff[f].isna() | (out_eff[f].astype(str) == "")
        else:
            mask &= out_eff[f].map(_show) == v
    picked = out_eff[mask].sort_values(key)
    total = len(picked)
    page = picked.iloc[offset: offset + limit]
    src_idx = src.set_index(key)
    pend = {}
    for r in listing(conn, PK.get(conn, package_id)["category_id"], package_id=package_id, status=PENDING,
                     file_code=file_code):
        pend.setdefault((r["child"], r["month"]), []).append(
            {"code": r["code"], "field": r["field"], "value": r["proposed_value"], "source": r["source"]})
    rows = []
    for _, r in page.iterrows():
        k = tuple(r[c] for c in key)
        try:
            s_row = src_idx.loc[k if len(key) > 1 else k[0]]
            if isinstance(s_row, pd.DataFrame):
                s_row = s_row.iloc[0]
        except KeyError:
            s_row = None
        values, changed = {}, {}
        for c in out_eff.columns:
            if c in key:
                continue
            v = _show(r[c])
            values[c] = v
            o = _show(s_row[c]) if s_row is not None and c in s_row.index else None
            if o != v:
                changed[c] = o
        month_key = r["月份"] if "月份" in r.index else None
        rows.append({"key": {c: r[c] for c in key}, "values": values, "imported_if_changed": changed,
                     "pending": pend.get((r["子ASIN"], month_key), []) + (
                         pend.get((r["子ASIN"], None), []) if month_key else [])})
    return {"file": file_code, "total": total, "offset": offset, "limit": limit, "rows": rows}

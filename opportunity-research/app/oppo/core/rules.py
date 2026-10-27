"""Strategy library (F11: REQ-F11-01, AC-F11-01..06, DEC-013/025/029/032)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import signals as SIG

ACTIONS = ("立项候选", "观察", "放弃")
STATUSES = ("已验证", "历史观察", "未验证经验")
OPS = {">=": "≥", ">": ">", "<=": "≤", "<": "<", "=": "=", "!=": "≠"}
SIGNAL_OPS = (">=", ">", "<=", "<")
DIM_OPS = ("=", "!=")
SYSTEM = "系统"
PCT_SIGNALS = {"demand", "entry", "pain", "hslr", "premium", "low_score", "xprob"}
SIGNED = {"demand", "premium"}
SIGNAL_LABELS = {**SIG.LABELS, "xprob": "上架 6 个月内命中概率（截面）"}
DIM_LABELS = {"width": "宽度档", "form": "形态", "price": "价格带"}


class RuleError(Exception):
    """`fields` maps form field names (cond, cond_<i>, action, reason) to messages."""

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.fields = fields or {}


def fmt_value(key: str, v: Any) -> str:
    if isinstance(v, str):
        return v
    if key in PCT_SIGNALS:
        pct = v * 100
        txt = f"{pct:.0f}%" if abs(pct - round(pct)) < 1e-9 else f"{pct:.1f}%"
        return ("+" + txt) if key in SIGNED and pct > 0 else txt
    if key == "trend":
        return f"{v:+.1f} 个百分点"
    return f"{v:g}"


def cond_text(conds: list[dict[str, Any]]) -> str:
    parts = []
    for c in conds:
        if c["kind"] == "signal":
            label = SIGNAL_LABELS.get(c["key"], c["key"])
            parts.append(f"{label} {OPS[c['op']]} {fmt_value(c['key'], c['value'])}")
        elif c["kind"] == "dim":
            parts.append(f"{DIM_LABELS.get(c['key'], c['key'])} {OPS.get(c.get('op') or '=', '=')} {c['value']}")
        else:
            parts.append(f"{c['key']} {OPS.get(c.get('op') or '=', '=')} {c['value']}")
    return " 且 ".join(parts)


def _cmp(a: float, op: str, b: float) -> bool:
    return {">=": a >= b - 1e-12, ">": a > b, "<=": a <= b + 1e-12, "<": a < b, "=": abs(a - b) < 1e-12}[op]


def matches(conds: list[dict[str, Any]], seg_key: str, sig: dict[str, float | None], cfg: dict[str, Any]) -> bool:
    labels = dict(zip([d["key"] for d in cfg["segment_dims"]], seg_key.split("|"), strict=False))
    for c in conds:
        if c["kind"] == "signal":
            v = sig.get(c["key"])
            if v is None or not _cmp(float(v), c["op"], float(c["value"])):
                return False
        elif c["kind"] == "dim":
            if (labels.get(c["key"]) == c["value"]) != (c.get("op", "=") != "!="):
                return False
        # attribute conditions narrow the products inside a segment; segments stay applicable
    return True


def attr_note(conds: list[dict[str, Any]]) -> str | None:
    a = [c for c in conds if c["kind"] == "attr"]
    if not a:
        return None
    return "限" + "、".join(f"{c['key']}{'不为' if c.get('op') == '!=' else '为'}{c['value']}" for c in a) + "的商品"


def parse_value(key: str, raw: Any) -> float:
    """Signal thresholds as people type them: "+15%", "−5%", "40 件", "+1 个百分点". Percentage signals are
    stored as fractions (15% → 0.15); a bare number for them is read as a percentage."""
    if isinstance(raw, (int, float)):
        return float(raw)
    t = str(raw or "").strip().replace("−", "-").replace("–", "-").replace("＋", "+").replace("，", "")
    for suffix in ("个百分点", "百分点", "pp", "件", "%", "％"):
        t = t.replace(suffix, "")
    t = t.replace(",", "").strip()
    v = float(t)  # ValueError when not a number
    return v / 100 if key in PCT_SIGNALS else v


def check_conds(rows: list[dict[str, Any]], cfg: dict[str, Any], cfg_no: int | None = None,
                attr_values: dict[str, list[str]] | None = None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Validate the editor's rows (kind, key, op, value as typed). Returns (conditions, field errors)."""
    errors: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    dims = {d["key"]: [b["label"] for b in d["bins"]] for d in cfg.get("segment_dims") or []}
    rows = [r for r in rows if any(str(r.get(k) or "").strip() for k in ("key", "value"))]
    if not rows:
        return [], {"cond": "至少需要一条条件"}
    for i, r in enumerate(rows, start=1):
        kind, key, op, val = r.get("kind"), (r.get("key") or "").strip(), r.get("op"), str(r.get("value") or "").strip()
        if kind not in ("signal", "dim", "attr") or not key or not op or not val:
            errors[f"cond_{i}"] = "这条条件还没填完"
            continue
        if kind == "signal":
            if op not in SIGNAL_OPS:
                errors[f"cond_{i}"] = "信号条件的比较只能是 ≥、>、≤、<"
                continue
            try:
                num = parse_value(key, val)
            except ValueError:
                errors[f"cond_{i}"] = "请填数字，例如 +15%"
                continue
            out.append({"kind": kind, "key": key, "op": op, "value": num})
        else:
            if op not in DIM_OPS:
                errors[f"cond_{i}"] = "维度条件的比较只能是 = 或 ≠"
                continue
            if kind == "dim" and val not in dims.get(key, []):
                errors[f"cond_{i}"] = f"该分档不在品类配置 v{cfg_no} 中" if cfg_no else "该分档不在品类配置中"
                continue
            if kind == "attr" and attr_values is not None and key not in attr_values:
                errors[f"cond_{i}"] = "该属性不在当前数据的属性标签中"
                continue
            out.append({"kind": kind, "key": key, "op": op, "value": val})
    if not errors:
        seen: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for c in out:
            seen.setdefault((c["kind"], c["key"]), []).append(c)
        for (kind, key), cs in seen.items():
            if kind == "signal":
                continue
            eq = {c["value"] for c in cs if c["op"] == "="}
            ne = {c["value"] for c in cs if c["op"] == "!="}
            if len(eq) > 1 or (eq & ne):
                label = DIM_LABELS.get(key, key)
                errors["cond"] = f"条件互相矛盾：{label} 不能同时满足这些取值"
    return out, errors


def validate_conds(conds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in conds or []:
        kind, key, op, val = c.get("kind"), c.get("key"), c.get("op"), c.get("value")
        if kind not in ("signal", "dim", "attr") or not key or val in (None, ""):
            continue
        if kind == "signal":
            if op not in OPS:
                raise RuleError("比较方式不合法")
            try:
                val = float(val)
            except (TypeError, ValueError) as exc:
                raise RuleError("信号条件的值必须是数字") from exc
        else:
            op = op if op in DIM_OPS else "="
        out.append({"kind": kind, "key": key, "op": op, "value": val})
    return out


def _next_code(conn: Connection) -> str:
    n = conn.execute(select(func.count()).select_from(D.rule)).scalar() or 0
    return f"R-{n + 1:03d}"


def _content_errors(conds: list[dict[str, Any]], action: str, reason: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not conds:
        errors["cond"] = "至少需要一条条件"
    if action not in ACTIONS:
        errors["action"] = "请选择动作"
    if not (reason or "").strip():
        errors["reason"] = "请写明理由"
    return errors


def add(conn: Connection, category_id: int, conds: list[dict[str, Any]], action: str, reason: str, operator: str,
        origin: str = "人工", status: str = "未验证经验", basis: dict[str, Any] | None = None,
        cross: bool = False) -> int:
    """New rule v1. Rules written by a backtest are recorded as made by 系统 (NFR-004)."""
    conds = validate_conds(conds)
    errors = _content_errors(conds, action, reason)
    if errors:
        raise RuleError("；".join(errors.values()), errors)
    actor = SYSTEM if origin == "回测" else operator
    now = clock.now_iso()
    rid = conn.execute(D.rule.insert().values(category_id=category_id, code=_next_code(conn), origin=origin,
                                              cross_tag=int(cross), created_by=actor, created_at=now)
                       ).inserted_primary_key[0]
    note = "新增" if origin != "回测" else f"由回测 {(basis or {}).get('backtest') or ''} 生成".replace("  ", " ")
    conn.execute(D.rule_version.insert().values(
        rule_id=rid, version_no=1, condition_json=D.dumps({"conds": conds}), action=action, reason=reason.strip(),
        status=status, basis_json=D.dumps(basis) if basis else None, change_note=note, created_by=actor,
        created_at=now))
    return int(rid)


def edit(conn: Connection, rule_id: int, conds: list[dict[str, Any]], action: str, reason: str, operator: str,
         expected_version: int | None = None) -> int:
    """New version (AC-F11-04); changing condition or action resets the status (AC-F11-05)."""
    cur = current(conn, rule_id)
    if cur is None:
        raise RuleError("规则不存在")
    if expected_version is not None and cur["version_no"] != expected_version:
        raise RuleError(f"规则已有更新的版本 v{cur['version_no']}，请刷新后再改")
    conds = validate_conds(conds)
    errors = _content_errors(conds, action, reason)
    if errors:
        raise RuleError("；".join(errors.values()), errors)
    changed_logic = conds != cur["conds"] or action != cur["action"]
    if not changed_logic and reason.strip() == (cur["reason"] or ""):
        raise RuleError("没有修改：条件、动作和理由都与当前版本相同", {"reason": "请写明这次修改的理由"})
    status = "未验证经验" if changed_logic else cur["status"]
    no = cur["version_no"] + 1
    conn.execute(D.rule_version.insert().values(
        rule_id=rule_id, version_no=no, condition_json=D.dumps({"conds": conds}), action=action,
        reason=reason.strip(), status=status, basis_json=None if changed_logic else cur["basis_json"],
        change_note="修改条件或动作，状态重置为未验证经验" if changed_logic else "只改理由",
        created_by=operator, created_at=clock.now_iso()))
    return no


def upgrade(conn: Connection, rule_id: int, recon_month: str, multiple: float, snapshot_label: str,
            operator: str) -> int:
    cur = current(conn, rule_id)
    assert cur is not None
    no = cur["version_no"] + 1
    basis = dict(cur["basis"] or {})
    basis.update(recon_month=recon_month, rule_multiple=multiple, recon_snapshot=snapshot_label)
    conn.execute(D.rule_version.insert().values(
        rule_id=rule_id, version_no=no, condition_json=D.dumps({"conds": cur["conds"]}), action=cur["action"],
        reason=cur["reason"], status="已验证", basis_json=D.dumps(basis),
        change_note=f"{recon_month} 对账 {snapshot_label}：规则倍数 {multiple:.2f}×，升为已验证",
        created_by=SYSTEM, created_at=clock.now_iso()))
    return no


def _shape(rule_row: dict[str, Any], ver: dict[str, Any]) -> dict[str, Any]:
    cond = D.loads(ver["condition_json"], {"conds": []})["conds"]
    return {**rule_row, "rule_id": rule_row["id"], "version_no": ver["version_no"], "version_id": ver["id"],
            "conds": cond, "cond_text": cond_text(cond), "attr_note": attr_note(cond), "action": ver["action"],
            "reason": ver["reason"], "status": ver["status"], "basis": D.loads(ver["basis_json"]),
            "basis_json": ver["basis_json"], "change_note": ver["change_note"], "updated_by": ver["created_by"],
            "updated_at": ver["created_at"]}


def current(conn: Connection, rule_id: int) -> dict[str, Any] | None:
    r = conn.execute(select(D.rule).where(D.rule.c.id == rule_id)).mappings().first()
    if r is None:
        return None
    v = conn.execute(select(D.rule_version).where(D.rule_version.c.rule_id == rule_id)
                     .order_by(D.rule_version.c.version_no.desc()).limit(1)).mappings().first()
    return _shape(dict(r), dict(v))


def by_code(conn: Connection, code: str) -> dict[str, Any] | None:
    r = conn.execute(select(D.rule.c.id).where(D.rule.c.code == code)).first()
    return current(conn, r[0]) if r else None


def list_current(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    ids = [r[0] for r in conn.execute(select(D.rule.c.id).where(D.rule.c.category_id == category_id)
                                      .order_by(D.rule.c.id))]
    return [current(conn, i) for i in ids]  # type: ignore[misc]


def history(conn: Connection, rule_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.rule_version).where(D.rule_version.c.rule_id == rule_id)
                        .order_by(D.rule_version.c.version_no.desc())).mappings().all()
    out = []
    for v in rows:
        cond = D.loads(v["condition_json"], {"conds": []})["conds"]
        out.append({**dict(v), "conds": cond, "cond_text": cond_text(cond), "basis": D.loads(v["basis_json"])})
    return out


def version_at(conn: Connection, rule_id: int, when: str) -> dict[str, Any] | None:
    """The version in force at a moment (for "规则当时的状态")."""
    v = conn.execute(select(D.rule_version).where(D.rule_version.c.rule_id == rule_id,
                                                  D.rule_version.c.created_at <= when)
                     .order_by(D.rule_version.c.version_no.desc()).limit(1)).mappings().first()
    return dict(v) if v else None


def generated_or_reuse(conn: Connection, category_id: int, conds: list[dict[str, Any]], action: str,
                       reason: str, basis: dict[str, Any], operator: str, cross: bool) -> int:
    for r in list_current(conn, category_id):
        if r["origin"] == "回测" and bool(r["cross_tag"]) == cross and r["conds"] == conds and r["action"] == action \
                and r["status"] in ("历史观察", "已验证"):
            return int(r["rule_id"])
    return add(conn, category_id, conds, action, reason, operator, origin="回测", status="历史观察", basis=basis,
               cross=cross)

"""Decision cards (F08: REQ-F08-01, AC-F08-01..03; AC-F07-11/12, DEC-011)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import db as D

UNVERIFIED_TEXT = "未验证，不可作为立项结论"
CROSS_TEXT = "截面口径，待历史回测确认"
CROSS_LINE_TEXT = "截面口径（近似成功线）"


def _shape(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["signals"] = D.loads(row["signals_json"], [])
    d["basis"] = D.loads(row["basis_json"], {})
    return d


def current_card(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    row = conn.execute(select(D.decision_card).where(
        D.decision_card.c.category_id == category_id, D.decision_card.c.mode == mode)
        .order_by(D.decision_card.c.id.desc()).limit(1)).mappings().first()
    return _shape(row) if row else None


def all_cards(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.decision_card).where(D.decision_card.c.category_id == category_id)
                        .order_by(D.decision_card.c.id.desc())).mappings().all()
    return [_shape(r) for r in rows]


def get(conn: Connection, card_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.decision_card).where(D.decision_card.c.id == card_id)).mappings().first()
    return _shape(row) if row else None


def effective(conn: Connection, category_id: int) -> dict[str, Any]:
    """Card status for the category: the historical conclusion wins when both exist (AC-F07-12)."""
    hist = current_card(conn, category_id, "history")
    cross = current_card(conn, category_id, "cross")
    if hist:
        return {"status": hist["status"], "card": hist, "mode": "history", "cross_card": cross,
                "cross_superseded": cross is not None}
    if cross:
        return {"status": cross["status"], "card": cross, "mode": "cross", "cross_card": cross,
                "cross_superseded": False}
    return {"status": None, "card": None, "mode": None, "cross_card": None, "cross_superseded": False}


def banner(status: str | None) -> dict[str, str] | None:
    if status == "未验证":
        return {"kind": "warn", "title": UNVERIFIED_TEXT}
    if status == "达标（截面）":
        return {"kind": "cross", "title": CROSS_TEXT}
    if status == "已达标":
        return {"kind": "ok", "title": "已达标"}
    return None

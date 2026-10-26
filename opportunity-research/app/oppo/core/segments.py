"""Segment assignment and parent backfill (REQ-F06-01, REQ-F06-07, AC-F06-01/02/09/10, DEC-035)."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from oppo.core import data as DATA

UNKNOWN = "未知"


def effective_attrs(c4: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """child × dim effective values; '<dim>__bf' = 1 when the value is a parent backfill."""
    type_attrs = set(cfg.get("type_attributes") or [])
    wide = DATA.attr_table(c4)
    if wide.empty:
        return pd.DataFrame(columns=["child"])
    out = pd.DataFrame({"child": wide["child"]})
    for dim in cfg.get("attribute_dims") or []:
        if dim not in wide.columns:
            out[dim] = UNKNOWN
            out[f"{dim}__bf"] = 0
            continue
        vals = wide[dim].fillna("").astype(str)
        stat = wide.get(f"{dim}__status")
        stat = stat.fillna("") if stat is not None else pd.Series([""] * len(wide))
        eff, bf = [], []
        for v, s in zip(vals, stat):
            v = v.strip()
            if not v or v == UNKNOWN:
                eff.append(UNKNOWN)
                bf.append(0)
            elif s in ("", "子体确认"):
                eff.append(v)
                bf.append(0)
            elif dim in type_attrs and s in ("父体候选", "父体回填"):
                eff.append(v)
                bf.append(1)
            else:  # 信息不足 / 冲突, or variant dimensions (颜色、尺寸、盆数) without a child value
                eff.append(UNKNOWN)
                bf.append(0)
        out[dim] = eff
        out[f"{dim}__bf"] = bf
    bf_cols = [f"{d}__bf" for d in cfg.get("type_attributes") or [] if f"{d}__bf" in out.columns]
    out["any_bf"] = out[bf_cols].max(axis=1) if bf_cols else 0
    return out


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def bin_numeric(v: float | None, bins: list[dict[str, Any]]) -> str:
    if v is None:
        return UNKNOWN
    for b in bins:
        ok = True
        if "max" in b and not v <= b["max"]:
            ok = False
        if "gt" in b and not v > b["gt"]:
            ok = False
        if "lt" in b and not v < b["lt"]:
            ok = False
        if "min" in b and not v >= b["min"]:
            ok = False
        if ok:
            return b["label"]
    return UNKNOWN


def bin_category(v: Any, bins: list[dict[str, Any]]) -> str:
    if v is None or v == UNKNOWN or (isinstance(v, float) and pd.isna(v)):
        return UNKNOWN
    for b in bins:
        if str(v) in b.get("values", []):
            return b["label"]
    return UNKNOWN


def dim_labels(cfg: dict[str, Any]) -> list[str]:
    return [d["key"] for d in cfg["segment_dims"]]


def segment_of(attrs_row: dict[str, Any] | None, price: float | None, cfg: dict[str, Any]) -> tuple[str, list[str]]:
    labels = []
    for dim in cfg["segment_dims"]:
        if dim["kind"] == "price":
            labels.append(bin_numeric(price, dim["bins"]))
        elif dim["kind"] == "numeric":
            labels.append(bin_numeric(_num(attrs_row.get(dim["attr"])) if attrs_row else None, dim["bins"]))
        else:
            labels.append(bin_category(attrs_row.get(dim["attr"]) if attrs_row else None, dim["bins"]))
    return "|".join(labels), labels


def seg_name(key: str) -> str:
    return " · ".join(key.split("|"))


def all_segment_keys(cfg: dict[str, Any]) -> list[str]:
    import itertools

    lists = [[b["label"] for b in d["bins"]] for d in cfg["segment_dims"]]
    return ["|".join(p) for p in itertools.product(*lists)]


def adjacent_bins(key: str, cfg: dict[str, Any]) -> list[str]:
    """Neighbouring segments differing by one step in one ordered dimension (for merge hints)."""
    parts = key.split("|")
    out = []
    for i, dim in enumerate(cfg["segment_dims"]):
        labels = [b["label"] for b in dim["bins"]]
        if parts[i] not in labels or dim["kind"] == "category":
            continue
        j = labels.index(parts[i])
        for k in (j + 1, j - 1):
            if 0 <= k < len(labels):
                out.append("|".join(parts[:i] + [labels[k]] + parts[i + 1:]))
    return out

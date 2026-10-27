"""Category configuration (REQ-F13-01): template, versions, drafts and validation."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D

BATHROOM_TEMPLATE: dict[str, Any] = {
    "name": "浴室柜",
    "platform": "amazon",
    "site": "US",
    "site_label": "US · 美国",
    "node": "6810202011",
    "owner": "wen",
    "success": {"bsr_max": 50, "gmv_min": 100000, "window_months": 6},
    "rising_min_parent_units": 60,
    "segment_dims": [
        {"key": "width", "label": "宽度档", "attr": "尺寸", "kind": "numeric",
         "bins": [{"label": "≤30″", "max": 30}, {"label": "30–48″", "gt": 30, "lt": 48}, {"label": "≥48″", "min": 48}]},
        {"key": "form", "label": "形态", "attr": "形态", "kind": "category",
         "bins": [{"label": "落地式", "values": ["落地式"]}, {"label": "悬浮式", "values": ["悬浮式"]}]},
        {"key": "price", "label": "价格带", "attr": "价格", "kind": "price",
         "bins": [{"label": "<$500", "lt": 500}, {"label": "$500–900", "min": 500, "lt": 900}, {"label": "≥$900", "min": 900}]},
    ],
    "attribute_dims": ["尺寸", "颜色", "盆数", "形态", "安装方式", "元素", "台面形态", "柜体材质", "台面材质", "台盆材质"],
    "type_attributes": ["形态", "安装方式", "元素", "台面形态", "柜体材质", "台面材质", "台盆材质"],
    "keyword_mapping": {
        "width": {"tag": "尺寸", "rule": "≤30″：尺寸 ≤ 30 英寸；30–48″：大于 30、小于 48 英寸；≥48″：尺寸 ≥ 48 英寸"},
        "form": {"tag": "形态", "map": {"悬浮式": ["floating", "wall mounted"], "落地式": ["freestanding", "floor standing"]}},
        "price": {"rule": "不映射：关键词不带价格，计入其余维度一致的各价格带；泛词不计入细分信号"},
    },
    "signal_windows": {"demand_months": 4, "entry_lookback_months": 6},
    "backtest_split": {"rule": 2, "test": 1},
    "health_thresholds": {
        "first_review_early": 20.0,
        "family_span": 25.0,
        "below_bought": 10.0,
        "unknown_share": 40.0,
        "parent_change": 300,
        "dup_key": 0,
    },
}

HEALTH_LABELS = {
    "first_review_early": "首次评分早于上架超过 7 天的子体占比",
    "family_span": "同一父体内子体上架跨度超过 180 天的家族占比",
    "below_bought": "子体月销量低于“过去一个月购买”标签下界的比例",
    "unknown_share": "各属性维度“未知”占比（逐个维度比较）",
    "parent_change": "跨月父 ASIN 发生变化的子体数",
    "dup_key": "主键重复数",
}

# Ordered (group, path, label, kind) entries: drives the form, the required check and the diff.
CONFIG_FIELDS: list[tuple[str, str, str, str]] = [
    ("基本", "site", "站点", "text"),
    ("基本", "node", "类目节点", "text"),
    ("成功线", "success.bsr_max", "小类 BSR 阈值（≤）", "posnum"),
    ("成功线", "success.gmv_min", "月度 GMV 阈值（美元，≥）", "posnum"),
    ("成功线", "success.window_months", "判定窗口（个月）", "posint"),
    ("参照人群", "rising_min_parent_units", "起量门槛（件/月，≥）", "posnum"),
    ("细分维度与分档", "segment_dims.selected", "细分维度", "dims"),
    # the bins of each selected dimension are inserted here by config_fields(cfg)
    ("细分维度与分档", "type_attributes", "类型属性（缺失时可父体回填）", "list"),
    ("关键词映射规则", "keyword_mapping.width.rule", "宽度档 ← 尺寸标签", "text"),
    ("关键词映射规则", "keyword_mapping.form.map_text", "形态 ← 形态标签", "text"),
    ("关键词映射规则", "keyword_mapping.price.rule", "价格带", "text"),
    ("信号窗口与回看期", "signal_windows.demand_months", "需求动量窗口（个月）", "posint"),
    ("信号窗口与回看期", "signal_windows.entry_lookback_months", "新品进得去回看（个月）", "posint"),
    ("回测切分比例", "backtest_split.text", "定规则组 : 检验组", "split"),
    ("体检预警阈值", "health_thresholds.first_review_early", HEALTH_LABELS["first_review_early"] + "（%）", "pct"),
    ("体检预警阈值", "health_thresholds.family_span", HEALTH_LABELS["family_span"] + "（%）", "pct"),
    ("体检预警阈值", "health_thresholds.below_bought", HEALTH_LABELS["below_bought"] + "（%）", "pct"),
    ("体检预警阈值", "health_thresholds.unknown_share", HEALTH_LABELS["unknown_share"] + "（%）", "pct"),
    ("体检预警阈值", "health_thresholds.parent_change", HEALTH_LABELS["parent_change"] + "（个）", "count"),
    ("体检预警阈值", "health_thresholds.dup_key", HEALTH_LABELS["dup_key"] + "（条）", "count"),
]


BIN_FIELD_LABELS = {"width": "宽度档（取自尺寸）", "form": "形态", "price": "价格带"}
NUMERIC_DIMS = ("width", "price")  # bins are numeric ranges; every other dimension lists attribute values


def dim_candidates(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows of the 细分维度与分档 table in their fixed order: 宽度档 (from 尺寸), 形态, 价格带, then every other
    attribute of the data package; any of them can be a segment dimension (PAGE-F13-01 F-02, REQ-F13-01)."""
    out = [copy.deepcopy(d) for d in BATHROOM_TEMPLATE["segment_dims"]]
    used = {d["attr"] for d in out}
    for a in cfg.get("attribute_dims") or []:
        if a not in used:
            out.append({"key": a, "label": a, "attr": a, "kind": "category", "bins": []})
    return out


def config_fields(cfg: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """CONFIG_FIELDS plus one bins field per selected segment dimension."""
    out: list[tuple[str, str, str, str]] = []
    for f in CONFIG_FIELDS:
        out.append(f)
        if f[1] == "segment_dims.selected":
            out += [("细分维度与分档", f"bins.{d['key']}", BIN_FIELD_LABELS.get(d["key"], f"{d['label']}分档"), "bins")
                    for d in cfg.get("segment_dims") or []]
    return out


def _fields_of(*cfgs: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    seen, out = set(), []
    for c in cfgs:
        for f in config_fields(c):
            if f[1] not in seen:
                seen.add(f[1])
                out.append(f)
    return out


def bins_text(cfg: dict[str, Any], key: str) -> str:
    for dim in cfg["segment_dims"]:
        if dim["key"] == key:
            return " / ".join(b["label"] for b in dim["bins"])
    return ""


def form_map_text(cfg: dict[str, Any]) -> str:
    """Canonical text (in the form dimension's bin order) so that re-ordering is not seen as a change."""
    m = cfg["keyword_mapping"]["form"]["map"]
    order = [b["label"] for d in cfg.get("segment_dims") or [] if d["key"] == "form" for b in d["bins"]]
    keys = [k for k in order if k in m] + [k for k in m if k not in order]
    return "；".join(f"{k}：{'、'.join(m[k])}" for k in keys)


def get_path(cfg: dict[str, Any], path: str) -> Any:
    if path == "segment_dims.selected":
        dims = cfg.get("segment_dims") or []
        return " × ".join(d["label"] for d in dims) if dims else None
    if path.startswith("bins."):
        return bins_text(cfg, path.split(".", 1)[1])
    if path == "keyword_mapping.form.map_text":
        return form_map_text(cfg)
    if path == "backtest_split.text":
        s = cfg["backtest_split"]
        return f"{s['rule']}/{s['rule'] + s['test']} : {s['test']}/{s['rule'] + s['test']}"
    if path == "type_attributes":
        return "、".join(cfg["type_attributes"])
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _parse_bins(key: str, text_value: str) -> list[dict[str, Any]]:
    labels = [p.strip() for p in text_value.split("/") if p.strip()]
    if key not in NUMERIC_DIMS:  # attribute values, one bin each
        if len(set(labels)) != len(labels):
            raise ValueError("分档有重复取值")
        return [{"label": lab, "values": [lab]} for lab in labels]
    bins: list[dict[str, Any]] = []
    import re

    nums = []
    for lab in labels:
        found = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", lab)]
        nums.append(found)
    for i, (lab, found) in enumerate(zip(labels, nums, strict=False)):
        if not found:
            raise ValueError(f"分档“{lab}”缺少数值")
        if i == 0:
            bins.append({"label": lab, "lt" if key == "price" else "max": found[-1]})
        elif i == len(labels) - 1:
            bins.append({"label": lab, "min": found[0]})
        else:
            lo, hi = found[0], found[-1]
            if key == "price":
                bins.append({"label": lab, "min": lo, "lt": hi})
            else:
                bins.append({"label": lab, "gt": lo, "lt": hi})
    # Contiguity check: each bin must start where the previous ended (no overlap or gap).
    edges = []
    for b in bins:
        lo = b.get("min", b.get("gt"))
        hi = b.get("lt", b.get("max"))
        edges.append((lo, hi))
    for (_lo1, hi1), (lo2, _hi2) in zip(edges, edges[1:], strict=False):
        if hi1 is None or lo2 is None or abs(float(hi1) - float(lo2)) > 1e-9:
            raise ValueError("分档有重叠或空档")
    return bins


def set_path(cfg: dict[str, Any], path: str, value: Any) -> None:
    if path == "segment_dims.selected":
        keys = [x.strip() for x in str(value).replace(",", "、").split("、") if x.strip()]
        have = {d["key"]: d for d in cfg.get("segment_dims") or []}
        dims = [have.get(c["key"], c) for c in dim_candidates(cfg) if c["key"] in keys]
        if not dims:
            raise ValueError("至少选择一个细分维度")
        cfg["segment_dims"] = dims
        return
    if path.startswith("bins."):
        key = path.split(".", 1)[1]
        for dim in cfg["segment_dims"]:
            if dim["key"] == key:
                dim["bins"] = _parse_bins(key, str(value))
        return
    if path == "keyword_mapping.form.map_text":
        out: dict[str, list[str]] = {}
        for part in str(value).replace(";", "；").split("；"):
            if "：" in part:
                k, v = part.split("：", 1)
                out[k.strip()] = [x.strip() for x in v.replace(",", "、").split("、") if x.strip()]
        cfg["keyword_mapping"]["form"]["map"] = out
        return
    if path == "backtest_split.text":
        import re

        m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*:\s*(\d+)\s*/\s*(\d+)\s*$", str(value))
        if not m:
            raise ValueError("请按“2/3 : 1/3”格式填写")
        cfg["backtest_split"] = {"rule": int(m.group(1)), "test": int(m.group(3))}
        return
    if path == "type_attributes":
        cfg["type_attributes"] = [x.strip() for x in str(value).replace(",", "、").split("、") if x.strip()]
        return
    parts = path.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def validate_value(kind: str, raw: Any) -> tuple[Any, str | None]:
    """Return (parsed value, error message)."""
    s = "" if raw is None else str(raw).strip()
    if s == "":
        return None, "必填"
    if kind in ("posnum", "posint", "pct", "count"):
        try:
            v = float(s.replace(",", ""))
        except ValueError:
            return None, "请填正数"
        if kind == "pct" and not (0 <= v <= 100):
            return None, "请填 0–100 之间的数"
        if kind == "count" and (v < 0 or v != int(v)):
            return None, "请填非负整数"
        if kind in ("posnum", "posint") and v <= 0:
            return None, "请填正数"
        if kind == "posint" and v != int(v):
            return None, "请填正整数"
        return (int(v) if kind in ("posint", "count") or v == int(v) else v), None
    return s, None


def apply_form(base: dict[str, Any], form: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Apply submitted form values to a copy of base; return (config, errors by path)."""
    cfg = copy.deepcopy(base)
    errors: dict[str, str] = {}

    def apply(fields: list[tuple[str, str, str, str]]) -> None:
        for _group, path, _label, kind in fields:
            if path not in form:
                continue
            val, err = validate_value(kind, form[path])
            if err:
                errors[path] = err
                continue
            try:
                set_path(cfg, path, val)
            except ValueError as exc:
                errors[path] = str(exc)

    # the dimension choice first, so that the bins of a newly selected dimension are read as well
    apply([f for f in CONFIG_FIELDS if f[1] == "segment_dims.selected"])
    apply([f for f in config_fields(cfg) if f[1] != "segment_dims.selected"])
    return cfg, errors


def missing_required(cfg: dict[str, Any]) -> list[str]:
    out = []
    for _group, path, label, _kind in config_fields(cfg):
        v = get_path(cfg, path)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            out.append(label)
    return out


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    out = []
    for _group, path, label, _kind in _fields_of(old, new):
        a, b = get_path(old, path), get_path(new, path)
        if a != b:
            out.append((label, a, b))
    return out


# ---- persistence -------------------------------------------------------------------------


def ensure_default(conn: Connection, operator: str) -> int:
    """Create the bathroom-cabinet category with config v1 on first start."""
    row = conn.execute(select(D.category.c.id).order_by(D.category.c.id)).first()
    if row:
        return int(row[0])
    now = clock.now_iso()
    cid = conn.execute(
        D.category.insert().values(
            name=BATHROOM_TEMPLATE["name"], platform="amazon", site=BATHROOM_TEMPLATE["site"],
            node=BATHROOM_TEMPLATE["node"], owner=operator, created_by=operator, created_at=now,
        )
    ).inserted_primary_key[0]
    cfg = copy.deepcopy(BATHROOM_TEMPLATE)
    cfg["owner"] = operator
    conn.execute(
        D.category_version.insert().values(
            category_id=cid, version_no=1, config_json=D.dumps(cfg), note="浴室柜模板默认值（首跑）",
            created_by=operator, created_at=now,
        )
    )
    D.set_meta(conn, "current_category", str(cid))
    return int(cid)


def current_category_id(conn: Connection) -> int:
    v = D.get_meta(conn, "current_category")
    if v:
        return int(v)
    row = conn.execute(select(D.category.c.id).order_by(D.category.c.id)).first()
    return int(row[0])


def current_version(conn: Connection, category_id: int) -> dict[str, Any]:
    row = conn.execute(
        select(D.category_version).where(D.category_version.c.category_id == category_id)
        .order_by(D.category_version.c.version_no.desc()).limit(1)
    ).mappings().first()
    if row is None:
        raise LookupError("品类还没有配置版本")
    out = dict(row)
    out["config"] = D.loads(row["config_json"])
    return out


def versions(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        select(D.category_version).where(D.category_version.c.category_id == category_id)
        .order_by(D.category_version.c.version_no.desc())
    ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["config"] = D.loads(r["config_json"])
        out.append(d)
    return out


def get_draft(conn: Connection, category_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.category_draft).where(D.category_draft.c.category_id == category_id)).mappings().first()
    if not row:
        return None
    return {"config": D.loads(row["config_json"]), "base_version_no": row["base_version_no"], "updated_at": row["updated_at"]}


def save_draft(conn: Connection, category_id: int, cfg: dict[str, Any], base_no: int) -> None:
    conn.execute(text("DELETE FROM category_draft WHERE category_id=:c"), {"c": category_id})
    conn.execute(D.category_draft.insert().values(
        category_id=category_id, config_json=D.dumps(cfg), base_version_no=base_no, updated_at=clock.now_iso()))


def discard_draft(conn: Connection, category_id: int) -> None:
    conn.execute(text("DELETE FROM category_draft WHERE category_id=:c"), {"c": category_id})


class ConfigError(Exception):
    pass


def save_version(conn: Connection, category_id: int, cfg: dict[str, Any], operator: str, note: str = "") -> int:
    """Save cfg as a new config version (AC-F13-02). Returns the new version number."""
    from oppo.core import jobs

    if jobs.running(conn):
        raise ConfigError("计算任务正在运行，完成后再保存")
    miss = missing_required(cfg)
    if miss:
        raise ConfigError("必填项为空：" + "、".join(miss))
    try:
        cur = current_version(conn, category_id)
    except LookupError:
        cur = {"version_no": 0, "config": {}}
    changes = diff(cur["config"], cfg) if cur["config"] else [("全部配置项", None, "新建")]
    if not changes:
        raise ConfigError(f"与 v{cur['version_no']} 相比没有修改，不需要保存新版本")
    now = clock.now_iso()
    no = cur["version_no"] + 1
    conn.execute(D.category_version.insert().values(
        category_id=category_id, version_no=no, config_json=D.dumps(cfg), note=note or None,
        created_by=operator, created_at=now))
    for label, a, b in changes:
        conn.execute(D.change_log.insert().values(
            category_id=category_id, object="品类配置", object_id=f"v{no}", action="保存新版本", item=label,
            before=D.dumps(a), after=D.dumps(b), created_by=operator, created_at=now))
    conn.execute(D.category.update().where(D.category.c.id == category_id).values(
        site=cfg.get("site"), node=cfg.get("node"), is_draft=0))
    discard_draft(conn, category_id)
    return no


def create_category(conn: Connection, name: str, site: str, node: str, operator: str, copy_template: bool) -> int:
    name = (name or "").strip()
    if not name or not (site or "").strip() or not (node or "").strip():
        raise ConfigError("品类名称、站点、类目节点必填")
    exists = conn.execute(select(D.category.c.id).where(D.category.c.name == name)).first()
    if exists:
        raise ConfigError("已有同名品类")
    now = clock.now_iso()
    cid = conn.execute(D.category.insert().values(
        name=name, platform="amazon", site=site, node=node, owner=operator, is_draft=1,
        created_by=operator, created_at=now)).inserted_primary_key[0]
    if copy_template:
        cfg = copy.deepcopy(BATHROOM_TEMPLATE)
    else:
        cfg = {k: (copy.deepcopy(v) if k in ("segment_dims", "attribute_dims", "keyword_mapping") else None)
               for k, v in BATHROOM_TEMPLATE.items()}
        cfg["success"] = {"bsr_max": None, "gmv_min": None, "window_months": None}
        cfg["signal_windows"] = {"demand_months": None, "entry_lookback_months": None}
        cfg["backtest_split"] = {"rule": 2, "test": 1}
        cfg["health_thresholds"] = {k: None for k in BATHROOM_TEMPLATE["health_thresholds"]}
        cfg["type_attributes"] = list(BATHROOM_TEMPLATE["type_attributes"])
        for dim in cfg["segment_dims"]:
            dim["bins"] = []
    cfg["name"], cfg["site"], cfg["node"], cfg["owner"] = name, site, node, operator
    save_draft(conn, cid, cfg, 0)
    return int(cid)

"""新品与信号 pages: PAGE-F04-01 新品与 SPU, PAGE-F04-02 合并建议, PAGE-F05-01 SPU 成败明细,
PAGE-F06-01 信号 and its PAGE-F06-02 细分详情 drawer."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote, urlencode

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo import service as SV
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import jobs, runs
from oppo.core import judge as J
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import segments as SEG
from oppo.core import spu as SPU
from oppo.core.packages import add_months, month_range
from oppo.web import common as C

router = APIRouter()
PAGE_SIZE = 50
MINUS = "−"
SIMILAR_ATTRS = SPU.SIMILAR_ATTRS
BASIS_KEY = {SPU.BASES[0]: "stem", SPU.BASES[1]: "similar", SPU.BASES[2]: "bullets"}
BASIS_ICON = {"stem": "copy", "similar": "scales", "bullets": "rows"}
BASIS_DEF = {
    "stem": "标题主干相同|去掉尺寸、颜色、数字和通用词之后，标题完全相同",
    "similar": "标题主干高度相似且类型属性一致|标题主干相似度 ≥ 0.9，且形态、安装方式、台面形态、元素全部一致",
    "bullets": "五点描述相同|五点描述去掉格式后完全相同|来自约定 C1、C2 的可选字段，未提供时不生成",
}
HIST_RESULTS = (("hit", J.HIT), ("miss", J.MISS), ("watch", J.WATCH), ("incomplete", J.INCOMPLETE))
CROSS_RESULTS = (("xhit", J.X_HIT), ("xmiss", J.X_MISS), ("watch", J.WATCH), ("old", J.OLD))
SOURCES = (("number", "编号"), ("merged", "已确认建议"), ("parent", "暂按父体"))


# ---- formatting -------------------------------------------------------------------------------


def _isnum(v: Any) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def spct(v: Any, digits: int = 1) -> str:
    """Signed percentage with a true minus sign: +18.4% / −4.8%."""
    if not _isnum(v):
        return "无数据"
    s = f"{abs(v) * 100:.{digits}f}%"
    return ("+" if v > 0 else (MINUS if v < 0 else "")) + s


def upct(v: Any, digits: int = 1) -> str:
    return "无数据" if not _isnum(v) else f"{v * 100:.{digits}f}%".replace("-", MINUS)


def spp(v: Any) -> str:
    if not _isnum(v):
        return "无数据"
    return ("+" if v > 0 else (MINUS if v < 0 else "")) + f"{abs(v):.1f} 个百分点"


def money0(v: Any) -> str:
    return "无数据" if not _isnum(v) else f"${v:,.0f}"


def int0(v: Any) -> str:
    return "无数据" if not _isnum(v) else f"{v:,.0f}"


def bsr0(v: Any) -> str:
    return "无数据" if not _isnum(v) else f"{v:,.0f}"


def age_range(ages: list[int]) -> str:
    """[1, 2, 3, 5] → 第 1–3、5 个月."""
    if not ages:
        return ""
    ages = sorted(set(int(a) for a in ages))
    parts, start, prev = [], ages[0], ages[0]
    for a in ages[1:] + [None]:  # type: ignore[list-item]
        if a is not None and a == prev + 1:
            prev = a
            continue
        parts.append(f"{start}–{prev}" if prev > start else f"{start}")
        if a is not None:
            start = prev = a
    return "第 " + "、".join(parts) + " 个月"


C.env.filters["b_loads"] = lambda s: D.loads(s, []) or []
C.env.filters["b_key"] = lambda k: quote(str(k), safe=":")
C.env.globals.update(b_spct=spct, b_upct=upct, b_spp=spp, b_money=money0, b_int=int0, b_bsr=bsr0,
                     b_age_range=age_range)


def _url(request: Request, path: str | None = None, **updates: Any) -> str:
    params = dict(request.query_params)
    params.pop("toast", None)
    if "page" not in updates:
        params.pop("page", None)
    for k, v in updates.items():
        if v is None or v == "" or v == "all":
            params.pop(k, None)
        else:
            params[k] = str(v)
    qs = urlencode(params)
    return (path or request.url.path) + (("?" + qs) if qs else "")


def _pager(total: int, page: int) -> dict[str, Any]:
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(1, page), pages)
    lo = (page - 1) * PAGE_SIZE
    show: list[int | None] = []
    for p in range(1, pages + 1):
        if p in (1, pages) or abs(p - page) <= 2:
            show.append(p)
        elif show and show[-1] is not None:
            show.append(None)
    return {"page": page, "pages": pages, "lo": lo, "hi": min(total, lo + PAGE_SIZE), "total": total, "show": show}


def _version_row(conn: Connection, table: Any, vid: int | None) -> int | None:
    if not vid:
        return None
    return conn.execute(select(table.c.version_no).where(table.c.id == vid)).scalar()


def _versions(conn: Connection, run: dict[str, Any] | None) -> dict[str, Any]:
    if not run:
        return {}
    pkg = PK.get(conn, run["package_id"])
    return {"package": pkg["label"] if pkg else "—", "fingerprint": (pkg.get("fingerprint") or "")[:8] if pkg else "",
            "pkg_kind": pkg["kind"] if pkg else None, "months_from": pkg["months_from"] if pkg else None,
            "months_to": pkg["months_to"] if pkg else None,
            "contract": _version_row(conn, D.contract_version, run["contract_version_id"]),
            "config": _version_row(conn, D.category_version, run["config_version_id"]),
            "computed_at": (run.get("ended_at") or run.get("created_at") or "")[:16]}


def _busy(conn: Connection) -> str | None:
    cur = jobs.running(conn)
    return f"{jobs.JOB_LABELS.get(cur['kind'], cur['kind'])}正在运行，完成后再试" if cur else None


def _months_rows(raw: Any) -> list[dict[str, Any]]:
    return D.loads(raw, []) or []


def _missing_text(months: list[dict[str, Any]], missing: list[str]) -> str:
    parts = []
    for m in missing:
        row = next((r for r in months if r.get("month") == m), None)
        what = []
        if row is None or row.get("sales") is None:
            what.append("销量与销售额")
        if row is None or row.get("best_bsr") is None:
            what.append("小类 BSR")
        parts.append(f"{m} 的{'与'.join(what)}" if what else m)
    return "缺 " + "；".join(parts)


def _hit_text(r: Any, cross: bool = False) -> str:
    st = r["status"]
    if st in (J.HIT, J.X_HIT):
        bits = []
        if _isnum(r.get("hit_bsr")):
            bits.append(f"BSR · 第 {int(r['hit_age'])} 个月（{r['hit_month']}）· {bsr0(r['hit_bsr'])}")
        if _isnum(r.get("hit_amount")):
            bits.append(f"GMV · 第 {int(r['hit_age'])} 个月（{r['hit_month']}）· {money0(r['hit_amount'])}")
        return "；".join(bits)
    if st == J.WATCH:
        return f"还剩 {int(r['remaining'])} 个月" if _isnum(r.get("remaining")) else "观察中"
    if st == J.INCOMPLETE:
        return _missing_text(_months_rows(r.get("months_json")), D.loads(r.get("missing_months_json"), []) or [])
    if st == J.MISS:
        return "窗口内两项都未达标"
    return ""


def _age(batch: str, month: str) -> int:
    return len(month_range(batch, month)) if month >= batch else 0


def _cross_ages(batch: str, first_obs: str, last_obs: str) -> tuple[int, int]:
    return max(1, _age(batch, first_obs)), _age(batch, last_obs)


def _cross_text(r: Any, first_obs: str, last_obs: str, window: int) -> str:
    st = r["status"]
    if st == J.X_HIT:
        bits = []
        if _isnum(r.get("hit_amount")):
            bits.append(f"SPU 销售额 {money0(r['hit_amount'])}")
        if _isnum(r.get("hit_bsr")):
            bits.append(f"子 ASIN {r['hit_child']} 小类 BSR {bsr0(r['hit_bsr'])}")
        return f"{r['hit_month']} · 第 {int(r['hit_age'])} 个月 · " + "，".join(bits)
    if st == J.X_MISS:
        un = D.loads(r.get("unobserved_ages_json"), []) or []
        return f"未观察到{age_range(un)}" if un else "新品期观察月都有数据，均未达到"
    if st == J.WATCH:
        a2 = _age(r["batch"], last_obs)
        return f"还剩{age_range(list(range(a2 + 1, window + 1)))}" if a2 < window else "观察中"
    if st == J.OLD:
        return "观察月全部超出新品期，不做截面判定"
    return ""


def _source_text(r: Any) -> str:
    if r["source"] == "已确认建议":
        return f"已确认建议 {r['merge_code']}" if r.get("merge_code") else "已确认建议"
    return r["source"] or "—"


def _mode_pkg(conn: Connection, cid: int, mode: str) -> dict[str, Any] | None:
    return PK.current_package(conn, cid, mode)


def _base(request: Request) -> tuple[Any, int]:
    app = C.svc(request)
    return app, app.category_id()


def _pending_banner(conn: Connection, cid: int) -> dict[str, Any] | None:
    sugg = SPU.suggestions(conn, cid, "pending")
    if not sugg:
        return None
    return {"n": len(sugg), "kids": sum(int(s.get("child_count") or 0) for s in sugg)}


# ---- PAGE-F04-01 新品与 SPU ----------------------------------------------------------------


@router.get("/spu", response_class=HTMLResponse)
def spu_list(request: Request) -> HTMLResponse:
    app, cid = _base(request)
    qp = request.query_params
    page = int(qp.get("page") or 1) if (qp.get("page") or "1").isdigit() else 1
    with app.engine.begin() as conn:
        mode = C.mode_of(request, conn, cid)
        run = CMP.latest_run(conn, cid, mode)
        cfg_ver = CAT.current_version(conn, cid)
        cfg = cfg_ver["config"]
        ctx: dict[str, Any] = {"run": run, "cfg": cfg, "reference": RK.reference_text(cfg),
                               "pending": _pending_banner(conn, cid), "stale": C.stale_reasons(conn, cid),
                               "versions": _versions(conn, run), "pkg_mode": _mode_pkg(conn, cid, mode),
                               "filters": {k: qp.get(k) or "" for k in ("batch", "result", "flag", "source", "q",
                                                                         "segment", "sort", "dir")}}
        if run is not None:
            df = CMP.spus_frame(conn, run["id"])
            ctx.update(_spu_list_ctx(request, df, run, cfg, mode, page))
    return C.render(request, "pages/F04-01.html", "PAGE-F04-01", ctx)


def _apply_common_filters(df: pd.DataFrame, qp: Any) -> pd.DataFrame:
    if qp.get("batch"):
        df = df[df["batch"] == qp.get("batch")]
    if qp.get("segment"):
        df = df[df["segment_key"] == qp.get("segment")]
    src = dict(SOURCES).get(qp.get("source") or "")
    if src:
        df = df[df["source"] == src]
    q = (qp.get("q") or "").strip().lower()
    if q:
        hay = (df["display_id"].fillna("") + " " + df["brand"].fillna("") + " " + df["title"].fillna("") + " "
               + df["parents_json"].fillna("") + " " + df["source_keys_json"].fillna("") + " "
               + df["merge_code"].fillna("")).str.lower()
        df = df[hay.str.contains(q, regex=False)]
    return df


def _sorted(df: pd.DataFrame, sort: str, direction: str) -> pd.DataFrame:
    col = {"launch": "launch_date", "kids": "child_count", "bsr": "best_bsr", "sales": "max_sales"}.get(sort, "launch_date")
    asc = direction == "asc"
    return df.sort_values([col, "display_id"], ascending=[asc, True], na_position="last")


def _spu_list_ctx(request: Request, df: pd.DataFrame, run: dict[str, Any], cfg: dict[str, Any], mode: str,
                  page: int) -> dict[str, Any]:
    qp = request.query_params
    window = int(cfg["success"]["window_months"])
    out: dict[str, Any] = {}
    new = df[df["is_new"] == 1]
    rising = new[new["rising"] == 1]
    excluded = new[new["rising"] != 1]
    sort, direction = qp.get("sort") or "launch", qp.get("dir") or "desc"
    if mode == "history":
        overview = []
        batches = sorted(set(new["batch"].dropna()), reverse=True)
        fully = None
        for b in batches:
            g = rising[rising["batch"] == b]
            cnt = g["status"].value_counts().to_dict()
            row = {"batch": b, "n": int(len(g)), "hit": int(cnt.get(J.HIT, 0)), "miss": int(cnt.get(J.MISS, 0)),
                   "watch": int(cnt.get(J.WATCH, 0)), "incomplete": int(cnt.get(J.INCOMPLETE, 0)),
                   "excluded": int((excluded["batch"] == b).sum())}
            dec = row["hit"] + row["miss"]
            row["rate"] = row["hit"] / dec if dec else None
            row["dec"] = dec
            if fully is None and row["watch"] == 0 and row["n"]:
                fully = b
            overview.append(row)
        recent, older = overview[:6], overview[6:]
        summary = None
        if older:
            keys = ("n", "hit", "miss", "watch", "incomplete", "excluded")
            summary = {k: sum(r[k] for r in older) for k in keys}
            dec = summary["hit"] + summary["miss"]
            summary.update(rate=summary["hit"] / dec if dec else None, dec=dec, count=len(older),
                           first=older[-1]["batch"], last=older[0]["batch"])
        out.update(overview=recent, overview_older=summary, fully_batch=fully, batches=batches)
        base = _apply_common_filters(rising, qp)
        counts = {k: int((base["status"] == v).sum()) for k, v in HIST_RESULTS}
        flags = {"relaunch": int((base["relaunch"] == 1).sum()), "variant": int((base["new_variant_count"] > 0).sum())}
        rows = base
        res = dict(HIST_RESULTS).get(qp.get("result") or "")
        if res:
            rows = rows[rows["status"] == res]
        if qp.get("flag") == "relaunch":
            rows = rows[rows["relaunch"] == 1]
        elif qp.get("flag") == "variant":
            rows = rows[rows["new_variant_count"] > 0]
        rows = _sorted(rows, sort, direction)
        pg = _pager(len(rows), page)
        items = []
        for r in rows.iloc[pg["lo"]:pg["hi"]].to_dict("records"):
            r["hit_text"] = _hit_text(r)
            r["source_text"] = _source_text(r)
            items.append(r)
        out.update(items=items, pager=pg, counts=counts, flag_counts=flags, total_rising=int(len(rising)),
                   result_opts=HIST_RESULTS)
    else:
        out.update(_cross_list(request, df, rising, excluded, cfg, window, page, sort, direction))
    out["segment_name"] = SEG.seg_name(qp.get("segment")) if qp.get("segment") else None
    out["url"] = lambda **kw: _url(request, **kw)
    return out


def _cross_list(request: Request, df: pd.DataFrame, rising: pd.DataFrame, excluded: pd.DataFrame,
                cfg: dict[str, Any], window: int, page: int, sort: str, direction: str) -> dict[str, Any]:
    qp = request.query_params
    app, cid = _base(request)
    with app.engine.begin() as conn:
        pkg = PK.current_package(conn, cid, "cross")
    first_obs, last_obs = (pkg["months_from"], pkg["months_to"]) if pkg else ("", "")
    old = df[df["is_old"] == 1]
    overview = []
    for b in sorted(set(rising["batch"].dropna()), reverse=True):
        g = rising[rising["batch"] == b]
        cnt = g["status"].value_counts().to_dict()
        a1, a2 = _cross_ages(b, first_obs, last_obs)
        overview.append({"batch": b, "ages": age_range(list(range(a1, min(a2, window) + 1))), "n": int(len(g)),
                         "xhit": int(cnt.get(J.X_HIT, 0)), "xmiss": int(cnt.get(J.X_MISS, 0)),
                         "watch": int(cnt.get(J.WATCH, 0))})
    pop = pd.concat([rising, old], ignore_index=True)
    base = _apply_common_filters(pop, qp)
    counts = {k: int((base["status"] == v).sum()) for k, v in CROSS_RESULTS}
    rows = base
    res = dict(CROSS_RESULTS).get(qp.get("result") or "")
    if res:
        rows = rows[rows["status"] == res]
    rows = rows.assign(_old=(rows["status"] == J.OLD).astype(int))
    col = {"launch": "launch_date", "kids": "child_count"}.get(sort, "launch_date")
    rows = rows.sort_values(["_old", col, "display_id"], ascending=[True, direction == "asc", True])
    pg = _pager(len(rows), page)
    items = []
    for r in rows.iloc[pg["lo"]:pg["hi"]].to_dict("records"):
        a1, a2 = _cross_ages(r["batch"], first_obs, last_obs)
        r["ages_text"] = age_range(list(range(a1, a2 + 1))) if a2 >= a1 else "—"
        r["hit_text"] = _cross_text(r, first_obs, last_obs, window)
        items.append(r)
    return {"cross_overview": overview, "old_count": int(len(old)), "excluded_count": int(len(excluded)),
            "items": items, "pager": pg, "counts": counts, "total_rising": int(len(rising)),
            "total_xhit": int((rising["status"] == J.X_HIT).sum()), "result_opts": CROSS_RESULTS,
            "first_obs": first_obs, "last_obs": last_obs, "batches": sorted(set(pop["batch"].dropna()), reverse=True)}


# ---- PAGE-F05-01 SPU 成败明细 --------------------------------------------------------------


def _child_month_frame(conn: Connection, package_id: int, children: list[str], months: list[str] | None = None
                       ) -> pd.DataFrame:
    """child × month rows (C3 first, C1 fills the rest) for a few children."""
    if not children:
        return pd.DataFrame(columns=["child", "month", "child_units", "child_sales", "bsr", "parent_units", "src"])
    raw = conn.connection.driver_connection
    ph = ",".join("?" * len(children))
    cols = "child, month, child_units, child_sales, bsr, parent_units, file_code"
    c3 = pd.read_sql_query(f"SELECT {cols} FROM raw_c3 WHERE package_id = ? AND child IN ({ph})", raw,
                           params=(package_id, *children))
    c1 = pd.read_sql_query(f"SELECT {cols}, parent FROM raw_c1 WHERE package_id = ? AND child IN ({ph})", raw,
                           params=(package_id, *children))
    out = J.child_months(c1.drop(columns=["file_code"]), c3.drop(columns=["file_code"]))
    if months is not None:
        out = out[out["month"].isin(months)]
    return out


def _parent_units(conn: Connection, package_id: int, parents: list[str], kids: pd.DataFrame) -> dict[tuple[str, str], float]:
    raw = conn.connection.driver_connection
    out: dict[tuple[str, str], float] = {}
    if parents:
        ph = ",".join("?" * len(parents))
        x = pd.read_sql_query(f"SELECT parent, month, MAX(parent_units) AS pu FROM raw_c1 WHERE package_id = ? "
                              f"AND parent IN ({ph}) AND parent_units IS NOT NULL GROUP BY parent, month", raw,
                              params=(package_id, *parents))
        for p, m, v in x.itertuples(index=False):
            out[(p, m)] = max(out.get((p, m), 0.0), float(v))
    if len(kids):
        cm = _child_month_frame(conn, package_id, kids["child"].tolist())
        cp = dict(zip(kids["child"], kids["parent"], strict=False))
        for ch, m, v in cm[["child", "month", "parent_units"]].dropna().itertuples(index=False):
            p = cp.get(ch)
            if p:
                out[(p, m)] = max(out.get((p, m), 0.0), float(v))
    return out


def _spu_row(conn: Connection, run_id: int, key: str) -> dict[str, Any] | None:
    raw = conn.connection.driver_connection
    s = pd.read_sql_query("SELECT * FROM spu WHERE run_id = ? AND spu_key = ?", raw, params=(run_id, key))
    if s.empty:
        return None
    j = pd.read_sql_query("SELECT * FROM judgment WHERE run_id = ? AND spu_key = ?", raw, params=(run_id, key))
    row = s.iloc[0].to_dict()
    if len(j):
        jr = j.iloc[0].to_dict()
        jr.pop("rising", None)
        jr.pop("run_id", None)
        row.update(jr)
    else:
        row["status"] = None
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


@router.get("/spu/merge", response_class=HTMLResponse)
def merge_page(request: Request) -> HTMLResponse:
    return _merge_page(request)


@router.get("/spu/{spu_key}", response_class=HTMLResponse)
def spu_detail(request: Request, spu_key: str) -> HTMLResponse:
    app, cid = _base(request)
    with app.engine.begin() as conn:
        mode = C.mode_of(request, conn, cid)
        run = CMP.latest_run(conn, cid, mode)
        cfg = CAT.current_version(conn, cid)["config"]
        ctx: dict[str, Any] = {"key": spu_key, "run": run, "cfg": cfg, "reference": RK.reference_text(cfg),
                               "stale": C.stale_reasons(conn, cid), "versions": _versions(conn, run),
                               "pkg_mode": _mode_pkg(conn, cid, mode), "spu": None}
        if run is not None:
            r = _spu_row(conn, run["id"], spu_key)
            if r is None and ":" not in spu_key:
                found = _resolve_key(conn, run["id"], spu_key.strip())
                if found:
                    return RedirectResponse("/spu/" + quote(found, safe=":"), status_code=303)  # type: ignore[return-value]
            if r is not None:
                ctx.update(_detail_ctx(conn, cid, run, r, cfg, mode))
    return C.render(request, "pages/F05-01.html", "PAGE-F05-01", ctx)


def _resolve_key(conn: Connection, run_id: int, token: str) -> str | None:
    """An ASIN or a displayed SPU id → the SPU key in this run (lets wen paste a child or parent ASIN)."""
    raw = conn.connection.driver_connection
    row = raw.execute("SELECT spu_key FROM spu WHERE run_id = ? AND display_id = ? LIMIT 1", (run_id, token)).fetchone()
    if row is None:
        row = raw.execute("SELECT spu_key FROM spu_child WHERE run_id = ? AND (child = ? OR parent = ?) "
                          "ORDER BY child = ? DESC LIMIT 1", (run_id, token, token, token)).fetchone()
    return row[0] if row else None


def _detail_ctx(conn: Connection, cid: int, run: dict[str, Any], r: dict[str, Any], cfg: dict[str, Any],
                mode: str) -> dict[str, Any]:
    window = int(cfg["success"]["window_months"])
    rise_thr = float(cfg["rising_min_parent_units"])
    pkg = PK.get(conn, run["package_id"])
    first_obs, last_obs = (pkg["months_from"], pkg["months_to"]) if pkg else ("", "")
    latest = run["latest_month"]
    raw = conn.connection.driver_connection
    kids = pd.read_sql_query("SELECT * FROM spu_child WHERE run_id = ? AND spu_key = ? ORDER BY launch_date, child",
                             raw, params=(run["id"], r["spu_key"]))
    kids = kids.astype(object).where(kids.notna(), None)
    parents = D.loads(r["parents_json"], []) or []
    months_tbl = _months_rows(r.get("months_json"))
    batch = r["batch"]
    win_months = month_range(batch, add_months(batch, window - 1))
    # grid: ages 1..window
    by_month = {row["month"]: row for row in months_tbl}
    status = r.get("status")
    cross = mode == "cross"
    if cross and status == J.OLD or (cross and not months_tbl):
        obs = month_range(max(first_obs, batch), last_obs) if first_obs else []
        cm = _child_month_frame(conn, run["package_id"], kids["child"].tolist(), obs)
        cmb = {c: g.set_index("month") for c, g in cm.groupby("child")}
        months_tbl = J.spu_month_table(kids["child"].tolist(), cmb, obs)
        for row in months_tbl:
            row["age"] = _age(batch, row["month"])
        by_month = {row["month"]: row for row in months_tbl}
    pu = _parent_units(conn, run["package_id"], parents, kids)
    grid = []
    for age, m in enumerate(win_months, start=1):
        row = by_month.get(m)
        cell: dict[str, Any] = {"age": age, "month": m, "row": row}
        if cross:
            cell["state"] = "unobserved" if (m < first_obs or m > last_obs) else ("data" if row else "nodata")
        else:
            cell["state"] = "future" if m > latest else ("data" if row else "nodata")
        cell["first_hit"] = bool(row and status in (J.HIT, J.X_HIT) and m == r.get("hit_month"))
        cell["hit_bsr"] = bool(cell["first_hit"] and _isnum(r.get("hit_bsr")))
        cell["hit_gmv"] = bool(cell["first_hit"] and _isnum(r.get("hit_amount")))
        grid.append(cell)
    parent_rows = [{"parent": p, "cells": [pu.get((p, m)) for m in win_months]} for p in parents]
    # outside-window observed months (cross): listed, not judged
    outside = [row for row in months_tbl if cross and (row.get("age", 0) > window or row.get("age", 0) < 1)]
    # rising: first month any parent reaches the threshold (any observable month)
    rise = None
    for (p, m), v in sorted(pu.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if v >= rise_thr:
            rise = {"parent": p, "month": m, "units": v}
            break
    # month for the child table: the hit month, else the window month with the highest SPU sales
    focus = r.get("hit_month") if status in (J.HIT, J.X_HIT) else None
    if focus is None:
        cand = [row for row in months_tbl if row.get("sales") is not None and (not cross or 1 <= row.get("age", 0) <= window)]
        if cand:
            focus = max(cand, key=lambda x: (x["sales"], x["month"]))["month"]
    cm_focus = _child_month_frame(conn, run["package_id"], kids["child"].tolist(), [focus]) if focus else pd.DataFrame()
    fm = {c: g.iloc[0] for c, g in cm_focus.groupby("child")} if len(cm_focus) else {}
    ctab = []
    tot_u = tot_s = 0.0
    any_val = False
    for k in kids.to_dict("records"):
        attrs = D.loads(k.get("attrs_json"), {}) or {}
        tattrs = [(d, (attrs.get(d) or {}).get("value") or SEG.UNKNOWN, int((attrs.get(d) or {}).get("backfill") or 0))
                  for d in SIMILAR_ATTRS]
        bf = [d for d, _, b in tattrs if b]
        rec = {**k, "tattrs": tattrs, "backfill": bf, "units": None, "sales": None, "not_launched": False}
        if focus and k.get("launch_date") and k["launch_date"][:7] > focus:
            rec["not_launched"] = True
        elif k["child"] in fm:
            x = fm[k["child"]]
            rec["units"] = None if pd.isna(x["child_units"]) else float(x["child_units"])
            rec["sales"] = None if pd.isna(x["child_sales"]) else float(x["child_sales"])
            if rec["units"] is not None:
                tot_u += rec["units"]
                any_val = True
            if rec["sales"] is not None:
                tot_s += rec["sales"]
        ctab.append(rec)
    # relaunch reason
    fr = kids.dropna(subset=["first_review"]).sort_values(["first_review", "child"])
    first_child = fr.iloc[0]["child"] if len(fr) else None
    early_days = None
    if r.get("first_review_min") and r.get("launch_date"):
        early_days = (pd.Timestamp(r["launch_date"]) - pd.Timestamp(r["first_review_min"])).days
    # merge source
    merge = None
    pending_s = None
    if r["source"] == "已确认建议" and r.get("merge_code"):
        m = conn.execute(select(D.merge).where(D.merge.c.code == r["merge_code"])).mappings().first()
        if m:
            sug = conn.execute(select(D.merge_suggestion).where(D.merge_suggestion.c.id == m["suggestion_id"])
                               ).mappings().first() if m["suggestion_id"] else None
            merge = {"merge": dict(m), "suggestion": dict(sug) if sug else None,
                     "detail": D.loads(sug["detail_json"], []) if sug else [],
                     "history": _merge_history(conn, m["id"])}
    elif r["source"] == "暂按父体":
        for s in SPU.suggestions(conn, cid, "pending"):
            if set(s["parents"]) & set(parents):
                pending_s = s
                break
    kid_count_by_parent = kids.groupby("parent")["child"].count().to_dict() if len(kids) else {}
    hit_children = []
    if status in (J.HIT, J.X_HIT) and r.get("hit_month"):
        cmh = _child_month_frame(conn, run["package_id"], kids["child"].tolist(), [r["hit_month"]])
        hit_children = sorted(cmh.dropna(subset=["child_sales"])["child"].tolist())
    src_files = {"history": ("C1", "C2", "C3"), "cross": ("S1", "S2", "S3")}[mode]
    from oppo.core.spec import FILE_NAMES
    names = [FILE_NAMES[x] for x in src_files]
    return {
        "spu": r, "status": status, "kids": ctab, "grid": grid, "parent_rows": parent_rows, "window": window,
        "win_months": win_months, "rise": rise, "rise_thr": rise_thr, "focus": focus,
        "focus_total": {"units": tot_u if any_val else None, "sales": tot_s if any_val else None},
        "focus_age": _age(batch, focus) if focus else None, "first_child": first_child, "early_days": early_days,
        "merge": merge, "pending_s": pending_s, "kid_count_by_parent": kid_count_by_parent,
        "hit_children": hit_children, "file_names": names, "first_obs": first_obs, "last_obs": last_obs,
        "latest": latest, "outside": outside, "window_end": win_months[-1],
        "window_done": win_months[-1] <= latest, "missing": D.loads(r.get("missing_months_json"), []) or [],
        "unobserved": D.loads(r.get("unobserved_ages_json"), []) or [], "months_tbl": months_tbl,
        "observed_ages": sorted({row.get("age") for row in months_tbl if row.get("age")}),
        "missing_after_hit": [m for m in (D.loads(r.get("missing_months_json"), []) or [])
                              if r.get("hit_month") and m > r["hit_month"]],
        "best_row": min((row for row in months_tbl if row.get("best_bsr") is not None
                         and (not cross or 1 <= row.get("age", 0) <= window)),
                        key=lambda x: (x["best_bsr"], x["month"]), default=None),
        "pkg": pkg, "missing_text": _missing_text(months_tbl, D.loads(r.get("missing_months_json"), []) or []),
    }


def _merge_history(conn: Connection, merge_id: int) -> list[dict[str, Any]]:
    """Predecessor merges this one replaced (修改记录), newest first."""
    out = []
    cur = merge_id
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        prev = conn.execute(select(D.merge).where(D.merge.c.superseded_by == cur, D.merge.c.status == "revised")
                            .order_by(D.merge.c.id.desc())).mappings().first()
        if not prev:
            break
        now_row = conn.execute(select(D.merge).where(D.merge.c.id == cur)).mappings().first()
        out.append({"before": D.loads(prev["parents_json"], []), "after": D.loads(now_row["parents_json"], [])
                    if now_row else [], "by": prev["ended_by"], "at": prev["ended_at"], "code": prev["code"]})
        cur = prev["id"]
    return out


# ---- PAGE-F04-02 合并建议 ------------------------------------------------------------------


def _merge_page(request: Request) -> HTMLResponse:
    app, cid = _base(request)
    with app.engine.begin() as conn:
        pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
        info = SPU.parent_info(conn, pkg["id"]) if pkg else {}
        use_no = use_bul = False
        no_field_unconfirmed = False
        if pkg and CT.current_version(conn, cid):
            use_no, use_bul, _conf = SPU._fields_state(conn, cid, pkg["id"])
        if pkg:
            fields = {f for (f,) in conn.execute(select(D.package_field.c.field).where(
                D.package_field.c.package_id == pkg["id"]))}
            no_field_unconfirmed = "SPU编号" in fields and not use_no
        pending = SPU.suggestions(conn, cid, "pending")
        confirmed = SPU.suggestions(conn, cid, "confirmed")
        rejected = SPU.suggestions(conn, cid, "rejected")
        active = SPU.active_merges(conn, cid)
        sugg_by_id = {s["id"]: s for s in confirmed + rejected + pending}
        # SPUs currently computed as single parents (for "现为 SPU-xxx（暂按父体）")
        run = CMP.latest_run(conn, cid, "history") or CMP.latest_run(conn, cid, "cross")
        by_number = 0
        parent_spu: dict[str, str] = {}
        if run:
            raw = conn.connection.driver_connection
            sp = pd.read_sql_query("SELECT spu_key, display_id, source, parents_json FROM spu WHERE run_id = ?", raw,
                                   params=(run["id"],))
            by_number = int((sp["source"] == "编号").sum())
            for _k, disp, src, pj in sp.itertuples(index=False):
                if src == "暂按父体":
                    for p in D.loads(pj, []) or []:
                        parent_spu[p] = disp
        last_compute = run["ended_at"] if run else None
        busy = _busy(conn)
        stale = C.stale_reasons(conn, cid)
    for s in pending:
        s["key"] = BASIS_KEY.get(s["basis"], "stem")
        s["compare"] = _compare(s)
    act_rows = []
    for m in active:
        sug = sugg_by_id.get(m["suggestion_id"]) if m["suggestion_id"] else None
        hist = []
        with app.engine.begin() as conn:
            hist = _merge_history(conn, m["id"])
        for h in hist:
            h["kids_before"] = sum(info.get(p, {}).get("children", 0) for p in h["before"])
            h["kids_after"] = sum(info.get(p, {}).get("children", 0) for p in h["after"])
            h["recomputed"] = last_compute if last_compute and last_compute >= (h["at"] or "") else None
        brand = next((info[p]["brand"] for p in m["parents"] if p in info and info[p]["brand"]), "")
        via = (sug.get("source") if sug else None) or m["source"]
        act_rows.append({**m, "brand": brand, "kids": sum(info.get(p, {}).get("children", 0) for p in m["parents"]),
                         "suggestion": sug, "history": hist,
                         "via": "批量确认" if via == "批量确认" else ("逐条确认" if via in ("逐条", "逐条确认") else via),
                         "spu_key": f"M:{m['code']}",
                         "parent_kids": [(p, info.get(p, {}).get("children", 0)) for p in m["parents"]]})
    tab = request.query_params.get("tab") or "pending"
    counts = {"stem": 0, "similar": 0, "bullets": 0}
    for s in pending:
        counts[s["key"]] += 1
    ctx = {
        "pkg_cur": pkg, "pending": pending, "confirmed": confirmed, "rejected": rejected, "active": act_rows,
        "n_single": sum(1 for s in confirmed if s.get("source") in ("逐条", "逐条确认")),
        "n_batch": sum(1 for s in confirmed if s.get("source") == "批量确认"),
        "pending_kids": sum(int(s.get("child_count") or 0) for s in pending), "by_number": by_number,
        "use_no": use_no, "use_bullets": use_bul, "no_field_unconfirmed": no_field_unconfirmed,
        "parent_spu": parent_spu, "basis_counts": counts, "basis_def": BASIS_DEF, "basis_icon": BASIS_ICON,
        "basis_key": BASIS_KEY, "tab": tab if tab in ("pending", "active", "rejected") else "pending", "busy": busy,
        "stale": stale, "info": info, "bases": SPU.BASES, "edited_count": sum(1 for a in act_rows if a["history"]),
        "via_single": sum(1 for a in act_rows if a["via"] == "逐条确认"),
        "via_batch": sum(1 for a in act_rows if a["via"] == "批量确认"),
    }
    return C.render(request, "pages/F04-02.html", "PAGE-F04-02", ctx)


def _compare(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows of the "对照 n 个父体" table: values per parent, merged when equal, and a conclusion."""
    det = s["detail"] or []
    if not det:
        return []
    rows = []
    sizes = [f"{d.get('sizes') or '无数据'} · {d.get('children', 0)} 个" for d in det]
    same_size = len({d.get("sizes") for d in det}) == 1
    rows.append({"label": "尺寸 · 子体", "values": sizes, "merged": False,
                 "verdict": "尺寸相同" if same_size else "尺寸不同（同一 SPU 可含各尺寸）", "ok": None})
    stems = [d.get("stem") or "" for d in det]
    if len(set(stems)) == 1:
        rows.append({"label": "标题主干", "values": [stems[0] or "无数据"], "merged": True, "verdict": "相同", "ok": True,
                     "mono": True})
    else:
        from difflib import SequenceMatcher

        ratio = min(SequenceMatcher(None, a, b).ratio() for i, a in enumerate(stems) for b in stems[i + 1:])
        rows.append({"label": "标题主干", "values": stems, "merged": False, "mono": True,
                     "verdict": f"相似度 {ratio:.2f}" + ("" if ratio >= 0.9 else "，低于 0.9"), "ok": ratio >= 0.9})
    for a in SIMILAR_ATTRS:
        vals = [d.get(a) or "无数据" for d in det]
        vals = ["信息不足" if v in ("无数据", "", None) else v for v in vals]
        if "信息不足" in vals:
            rows.append({"label": a, "values": vals, "merged": False, "verdict": "无法比较", "ok": None})
        elif len(set(vals)) == 1:
            rows.append({"label": a, "values": [vals[0]], "merged": True, "verdict": "一致", "ok": True})
        else:
            rows.append({"label": a, "values": vals, "merged": False, "verdict": "不一致", "ok": False})
    bl = [d.get("bullets") or "无数据" for d in det]
    if s.get("basis") == SPU.BASES[2] and "无数据" not in bl:
        same = len({SPU.bullets_norm(b) for b in bl}) == 1
        rows.append({"label": "五点摘要", "values": [bl[0]] if same else bl, "merged": same,
                     "verdict": "相同" if same else "去掉格式后相同", "ok": True, "small": True})
    elif all(b == "无数据" for b in bl):
        rows.append({"label": "五点摘要", "values": ["无数据"], "merged": True, "verdict": "无法比较（未提供）", "ok": None,
                     "small": True})
    elif len(set(bl)) == 1:
        rows.append({"label": "五点摘要", "values": [bl[0]], "merged": True, "verdict": "相同", "ok": True, "small": True})
    else:
        rows.append({"label": "五点摘要", "values": bl, "merged": False, "verdict": "措辞不同", "ok": None, "small": True})
    return rows


def _ids(form: Any) -> list[int]:
    out = []
    for v in form.getlist("ids"):
        for x in str(v).split(","):
            x = x.strip()
            if x.isdigit():
                out.append(int(x))
    return out


@router.post("/spu/merge/decide")
async def merge_decide(request: Request) -> JSONResponse:
    app, cid = _base(request)
    form = await request.form()
    ids = _ids(form)
    decision = str(form.get("decision") or "")
    source = "批量确认" if str(form.get("source") or "") == "批量确认" else "逐条"
    if decision not in ("confirm", "reject"):
        return C.fail("操作无效")
    if not ids:
        return C.fail("请先勾选要确认的建议")
    with app.engine.begin() as conn:
        busy = _busy(conn)
        if busy:
            return C.fail(busy, status=409)
        sugg = {s["id"]: s for s in SPU.suggestions(conn, cid)}
    res = SV.merge_decide(app, ids, decision, source)
    picked = [sugg[i] for i in ids if i in sugg]
    if res["done"] == 0:
        return C.fail("所选建议已处理过，没有新的变动", status=409)
    if decision == "confirm":
        if source == "批量确认":
            toast = f"已批量确认 {res['done']} 条建议，来源记为“批量确认” · 成败、信号、回测已标为需重算"
        else:
            toast = f"已确认 {picked[0]['code']}（逐条确认）· 成败、信号、回测已标为需重算"
    else:
        s = picked[0]
        toast = f"已拒绝 {s['code']} · 涉及的 {int(s.get('child_count') or 0)} 个子 ASIN 继续按各自父 ASIN 计"
    if res["skipped"]:
        toast += f"（{res['skipped']} 条已处理过，跳过）"
    return C.ok(redirect="/spu/merge?tab=active" if decision == "confirm" and source == "批量确认" else "/spu/merge",
                toast=toast)


@router.post("/spu/merge/{code}/revise")
async def merge_revise(request: Request, code: str) -> JSONResponse:
    app, cid = _base(request)
    form = await request.form()
    keep = [str(x) for x in form.getlist("keep")]
    add = [x for x in str(form.get("add") or "").replace("，", " ").replace(",", " ").split() if x]
    started = clock.now_iso()
    with app.engine.begin() as conn:
        busy = _busy(conn)
        if busy:
            return C.fail(busy, status=409)
        pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
        try:
            new_code = SPU.revise(conn, cid, code, app.operator, keep_parents=keep, add_parents=add,
                                  package_id=pkg["id"] if pkg else None)
        except SPU.MergeError as exc:
            field = "add" if add and ("父 ASIN" in str(exc) and ("品牌" in str(exc) or "数据包" in str(exc)
                                                                  or "归并" in str(exc))) else None
            return C.fail(str(exc), fields={field: str(exc)} if field else None)
        runs.record_step(conn, cid, "SPU 审核", started, clock.now_iso(), app.operator,
                         result=f"修改归并 {code} → {new_code}", link="/spu/merge")
    return C.ok(redirect="/spu/merge?tab=active", toast="已保存修改 · 修改前后已记录，成败、信号、回测已标为需重算")


@router.post("/spu/merge/{code}/split")
async def merge_split(request: Request, code: str) -> JSONResponse:
    app, cid = _base(request)
    started = clock.now_iso()
    with app.engine.begin() as conn:
        busy = _busy(conn)
        if busy:
            return C.fail(busy, status=409)
        try:
            SPU.revise(conn, cid, code, app.operator, keep_parents=None)
        except SPU.MergeError as exc:
            return C.fail(str(exc))
        runs.record_step(conn, cid, "SPU 审核", started, clock.now_iso(), app.operator,
                         result=f"拆分归并 {code}", link="/spu/merge")
    return C.ok(redirect="/spu/merge?tab=active", toast="已拆分 · 拆分前后已记录，成败、信号、回测已标为需重算")


# ---- PAGE-F06-01 信号 / PAGE-F06-02 细分详情 -------------------------------------------------


def _sig_table(conn: Connection, run_id: int, T: str) -> dict[str, dict[str, dict[str, Any]]]:
    sig = CMP.signals_frame(conn, run_id, T)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in sig.to_dict("records"):
        r = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
        r["extra"] = D.loads(r.get("extra_json"), {}) or {}
        if r.get("cnt") is not None:
            r["cnt"] = int(r["cnt"])
        out.setdefault(r["segment_key"], {})[r["signal"]] = r
    return out


def _pop(*pairs: tuple[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in pairs if v is not None and v != ""}


@router.get("/signals", response_class=HTMLResponse)
def signals_page(request: Request) -> HTMLResponse:
    app, cid = _base(request)
    qp = request.query_params
    with app.engine.begin() as conn:
        mode = C.mode_of(request, conn, cid)
        run = CMP.latest_run(conn, cid, mode)
        cfg = CAT.current_version(conn, cid)["config"]
        busy = _busy(conn)
        pkg_cur = PK.current_package(conn, cid, mode)
        blocked = bool(pkg_cur and pkg_cur["conclusion"] == "block")
        ctx: dict[str, Any] = {"run": run, "cfg": cfg, "reference": RK.reference_text(cfg), "busy": busy,
                               "stale": C.stale_reasons(conn, cid), "versions": _versions(conn, run),
                               "pkg_mode": pkg_cur, "blocked": blocked,
                               "dims": [d["label"] for d in cfg["segment_dims"]]}
        if run is not None:
            ctx.update(_signals_ctx(conn, cid, run, cfg, mode, qp.get("month"), qp.get("segment")))
    return C.render(request, "pages/F06-01.html", "PAGE-F06-01", ctx)


def _signals_ctx(conn: Connection, cid: int, run: dict[str, Any], cfg: dict[str, Any], mode: str,
                 month: str | None, segment: str | None) -> dict[str, Any]:
    raw = conn.connection.driver_connection
    months = [m for (m,) in raw.execute("SELECT DISTINCT t_month FROM signal_value WHERE run_id = ? ORDER BY t_month DESC",
                                        (run["id"],))]
    T = month if month in months else run["t_month"]
    table = _sig_table(conn, run["id"], T)
    seginfo = CMP.segments_frame(conn, run["id"], T)
    info = {r["segment_key"]: {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
            for r in seginfo.to_dict("records")}
    snap = RK.latest_snapshot(conn, cid, mode)
    ranks: dict[str, int] = {}
    tips: dict[str, list[dict[str, Any]]] = {}
    if snap and snap["month"] == T:
        for r in snap["content"].get("rows", []):
            ranks[r["segment_key"]] = r["rank"]
            tips[r["segment_key"]] = r.get("tips") or []
    spus = CMP.spus_frame(conn, run["id"])
    new_rising = spus[(spus["is_new"] == 1) & (spus["rising"] == 1)]
    cross = mode == "cross"
    if cross:
        sample = new_rising.groupby("segment_key").size().to_dict()
    else:
        sample = {k: int(v.get("sample") or 0) for k, v in info.items()}
    keys = sorted(set(table) | set(info))
    n = int(cfg["signal_windows"]["demand_months"])
    prev = add_months(T, -1)
    recent = month_range(add_months(T, -n), prev)
    rows = []
    for k in keys:
        sig = table.get(k, {})
        inf = info.get(k, {})
        s_n = int(sample.get(k, 0))
        rows.append({"key": k, "name": SEG.seg_name(k), "rank": ranks.get(k), "sample": s_n,
                     "insufficient": s_n < RK.MIN_SAMPLE, "sig": sig, "backfill": inf.get("backfill_share"),
                     "old_n": ((sig.get("unit_asin") or {}).get("extra") or {}).get("old")})
    rows.sort(key=lambda r: (0 if r["rank"] is not None else 1, r["rank"] or 0, r["insufficient"], -r["sample"],
                             r["name"]))
    if not ranks:
        rows.sort(key=lambda r: (r["insufficient"], -r["sample"], r["name"]))
    excluded = CMP.excluded_fields(run)
    old_spus = int((spus["is_old"] == 1).sum()) if cross else 0
    has_c6 = any((r["sig"].get("pain") or {}).get("extra", {}).get("reason") != "数据包不含评论痛点（C6）"
                 for r in rows) if rows else False
    trend_na = all((r["sig"].get("trend") or {}).get("value") is None for r in rows) if rows else True
    ctx: dict[str, Any] = {
        "T": T, "months": months, "rows": rows, "excluded": excluded, "recent": recent,
        "prior": [add_months(m, -12) for m in recent], "t_first": f"{T}-01", "old_spus": old_spus,
        "entry_window": (add_months(T, -(int(cfg['success']['window_months']) + int(cfg['signal_windows']['entry_lookback_months']))),
                         add_months(T, -(int(cfg['success']['window_months']) + 1))),
        "has_c6": has_c6, "trend_na": trend_na, "snapshot_T": bool(ranks), "n_segments": len(rows),
        "drawer": None,
    }
    if segment:
        ctx["drawer"] = _drawer_ctx(conn, cid, run, cfg, mode, T, segment, table.get(segment, {}), info.get(segment, {}),
                                    ranks.get(segment), tips.get(segment, []), int(sample.get(segment, 0)), spus,
                                    months)
    return ctx


def _seg_def(cfg: dict[str, Any], key: str) -> list[tuple[str, str]]:
    parts = key.split("|")
    out = []
    for dim, val in zip(cfg["segment_dims"], parts, strict=False):
        if val == SEG.UNKNOWN:
            out.append((dim["label"], "未知：该维度缺失或无法归档的子体"))
            continue
        b = next((x for x in dim["bins"] if x["label"] == val), None)
        if dim["kind"] == "numeric" and b:
            cond = []
            if "gt" in b:
                cond.append(f"大于 {b['gt']:g}")
            if "min" in b:
                cond.append(f"不小于 {b['min']:g}")
            if "lt" in b:
                cond.append(f"小于 {b['lt']:g}")
            if "max" in b:
                cond.append(f"不大于 {b['max']:g}")
            out.append((dim["label"], f"{val}：{dim['attr']}{'、'.join(cond)} 英寸"))
        elif dim["kind"] == "price":
            out.append((dim["label"], f"{val}：子体最近一个有销量月份的销售额 ÷ 销量"))
        else:
            out.append((dim["label"], f"{val}（含父体回填的子体）"))
    return out


def _spark(points: list[tuple[str, float | None, str]], fmt_value: Any) -> dict[str, Any] | None:
    """Single-series sparkline geometry for 6 months (viewBox 260 × 78)."""
    vals = [v for _, v, _ in points if v is not None]
    if len(vals) < 2:
        return None
    lo, hi = min(vals + [0.0]), max(vals)
    if hi == lo:
        hi = lo + 1
    x0, x1, y_top, y_bot = 8.0, 232.0, 8.0, 56.0
    n = len(points)
    step = (x1 - x0) / max(1, n - 1)
    coords = []
    for i, (m, v, tip) in enumerate(points):
        x = round(x0 + i * step, 1)
        y = None if v is None else round(y_bot - (v - lo) / (hi - lo) * (y_bot - y_top), 1)
        coords.append({"x": x, "y": y, "m": m, "v": v, "tip": tip, "label": fmt_value(v)})
    seg = [c for c in coords if c["y"] is not None]
    line = " ".join(("M" if i == 0 else "L") + f"{c['x']},{c['y']}" for i, c in enumerate(seg))
    area = line + f" L{seg[-1]['x']},{y_bot} L{seg[0]['x']},{y_bot} Z"
    zero_y = round(y_bot - (0 - lo) / (hi - lo) * (y_bot - y_top), 1)
    last = seg[-1]
    hits = []
    for i, c in enumerate(coords):
        left = 0 if i == 0 else round((coords[i - 1]["x"] + c["x"]) / 2, 1)
        right = 260 if i == n - 1 else round((c["x"] + coords[i + 1]["x"]) / 2, 1)
        hits.append({**c, "hx": left, "hw": round(right - left, 1)})
    return {"line": line, "area": area, "last": last, "first_m": coords[0]["m"], "last_m": coords[-1]["m"],
            "zero_y": zero_y, "hits": hits, "aria": "、".join(f"{c['m']} {c['label']}" for c in coords)}


def _drawer_ctx(conn: Connection, cid: int, run: dict[str, Any], cfg: dict[str, Any], mode: str, T: str, key: str,
                sig: dict[str, Any], inf: dict[str, Any], rank: int | None, tips: list[dict[str, Any]], sample: int,
                spus: pd.DataFrame, months: list[str]) -> dict[str, Any]:
    raw = conn.connection.driver_connection
    trend_months = sorted([m for m in months if m <= T])[-6:]
    tv = pd.read_sql_query(
        "SELECT t_month, signal, value, num, den, cnt FROM signal_value WHERE run_id = ? AND segment_key = ? "
        "AND signal IN ('demand', 'entry')", raw, params=(run["id"], key))
    tmap = {(r.t_month, r.signal): r for r in tv.itertuples()}

    def val(m: str, s: str) -> float | None:
        r = tmap.get((m, s))
        return None if r is None or pd.isna(r.value) else float(r.value)

    demand_pts, entry_pts, trend_rows = [], [], []
    for m in trend_months:
        d, e = val(m, "demand"), val(m, "entry")
        dr, er = tmap.get((m, "demand")), tmap.get((m, "entry"))
        dcnt = int(dr.cnt) if dr is not None and pd.notna(dr.cnt) else None
        en = (int(er.num), int(er.den)) if er is not None and pd.notna(er.num) and pd.notna(er.den) and er.den else None
        demand_pts.append((m, d, f"{spct(d)}|{m}" + (f" · 关键词 {dcnt} 个" if dcnt else "")))
        entry_pts.append((m, e, f"{upct(e)}|{m}" + (f" · 命中 {en[0]} / 已判定 {en[1]}" if en else "")))
        trend_rows.append({"m": m, "d": d, "e": e, "en": en})
    pain = sig.get("pain") or {}
    codes = (pain.get("extra") or {}).get("codes") or {}
    tot_codes = sum(codes.values())
    pains = sorted(codes.items(), key=lambda kv: (-kv[1], kv[0]))
    top = pains[:4]
    rest = sum(v for _, v in pains[4:])
    bars = [{"label": c, "n": v, "share": v / tot_codes, "focus": True} for c, v in top]
    if rest:
        bars.append({"label": "其他结构类", "n": rest, "share": rest / tot_codes, "focus": False})
    mx = max([b["share"] for b in bars], default=1) or 1
    for b in bars:
        b["width"] = round(b["share"] / mx * 100, 1)
    window = int(cfg["success"]["window_months"])
    look = int(cfg["signal_windows"]["entry_lookback_months"])
    lo, hi = add_months(T, -(window + look)), add_months(T, -(window + 1))
    seg_spus = spus[(spus["segment_key"] == key) & (spus["is_new"] == 1) & (spus["rising"] == 1)]
    if mode == "cross":
        listed = seg_spus[seg_spus["status"].isin([J.X_HIT, J.X_MISS])].sort_values(["batch", "display_id"],
                                                                                  ascending=[False, True])
    else:
        listed = seg_spus[(seg_spus["batch"] >= lo) & (seg_spus["batch"] <= hi) &
                          seg_spus["status"].isin([J.HIT, J.MISS])].sort_values(["batch", "display_id"],
                                                                                ascending=[False, True])
    decided_all = int(seg_spus["status"].isin([J.HIT, J.MISS, J.X_HIT, J.X_MISS]).sum())
    watching = int((seg_spus["status"] == J.WATCH).sum())
    bfj = D.loads(inf.get("backfill_json"), {}) or {}
    bf_items = sorted(((a, v) for a, v in bfj.items() if v), key=lambda kv: -kv[1])
    adj = [SEG.seg_name(a) for a in SEG.adjacent_bins(key, cfg)] if sample < RK.MIN_SAMPLE else []
    return {
        "key": key, "name": SEG.seg_name(key), "rank": rank, "sample": sample, "sig": sig,
        "insufficient": sample < RK.MIN_SAMPLE, "definition": _seg_def(cfg, key),
        "backfill": inf.get("backfill_share"), "backfill_items": bf_items, "child_count": inf.get("child_count"),
        "demand_spark": _spark(demand_pts, spct), "entry_spark": _spark(entry_pts, upct), "trend_rows": trend_rows,
        "trend_from": trend_months[0] if trend_months else None, "trend_to": trend_months[-1] if trend_months else None,
        "pain_bars": bars, "pain_total": tot_codes, "spus": listed.head(6).to_dict("records"),
        "spus_more": max(0, len(listed) - 6), "lookback": (lo, hi), "decided_all": decided_all,
        "watching": watching, "tips": tips, "adjacent": adj,
    }

"""数据准备 pages: 数据包 (PAGE-F01-01), 校验报告 (PAGE-F01-02), 字段约定 (PAGE-F02-01), 数据体检 (PAGE-F03-02),
品类配置 (PAGE-F13-01) and 运行记录 (PAGE-F14-01)."""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo import service as SV
from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import health as H
from oppo.core import jobs, runs
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import spec as S
from oppo.core import spu as SPU
from oppo.web import common as C

router = APIRouter()

KIND_LABEL = {"history": "历史", "cross": "截面"}
CONTRACT_LABEL = {"history": "约定 v1", "cross": "约定 v1.1"}
CONCLUSION = {"pass": "通过", "warn": "有警告", "block": "阻断"}
RESULT_BADGE = {"pass": "通过", "warn": "警告", "block": "阻断"}
FORMATS = {S.MONTH: "月份 YYYYMM", S.DATE: "日期 YYYY-MM-DD", S.NUM: "数值", S.TEXT: "文本", S.BOOL: "是 / 否"}
FILE_SHORT = {k: v.split(" ", 1)[1] for k, v in S.FILE_NAMES.items()}


def _fp8(sha: str | None) -> str:
    return (sha or "")[:8] or "—"


def _fp_mid(sha: str | None) -> str:
    return f"{sha[:12]}…{sha[-4:]}" if sha else "—"


def _rlabel(r: str | None) -> str:
    return RESULT_BADGE.get(r or "", "不适用")


def _rbadge(r: str | None) -> str:
    return {"pass": "通过", "warn": "有警告", "block": "阻断"}.get(r or "", "不适用")


C.env.globals.update(fp8=_fp8, fp_mid=_fp_mid, FILE_NAMES=S.FILE_NAMES, rlabel=_rlabel)


def _invalid(error: str, fields: dict[str, str] | None = None) -> JSONResponse:
    """A form that did not validate is an answer, not an HTTP error: 200 with ok=false keeps the console clean."""
    return C.fail(error, fields, status=200)


def _app_cid(request: Request) -> tuple[SV.App, int]:
    app = C.svc(request)
    return app, app.category_id()


# =============================================================================================
# PAGE-F01-01 数据包
# =============================================================================================


def _staged_root(app: SV.App) -> Path:
    d = app.settings.data_dir / "tmp" / "staged"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cleanup_staged(app: SV.App, keep: str | None = None) -> None:
    """Uploaded copies older than a day are removed; a typed local path is never touched."""
    now = time.time()
    for d in _staged_root(app).iterdir():
        if d.name == keep or not d.is_dir():
            continue
        try:
            if now - d.stat().st_mtime > 86400:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _staged(app: SV.App, token: str | None) -> dict[str, Any] | None:
    if not token or not re.fullmatch(r"[0-9a-f]{16}", token):
        return None
    meta = _staged_root(app) / token / "meta.json"
    if not meta.exists():
        return None
    return json.loads(meta.read_text(encoding="utf-8"))


def _write_staged(app: SV.App, token: str, meta: dict[str, Any]) -> None:
    d = _staged_root(app) / token
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")


def _package_row(conn: Connection, p: dict[str, Any], cur_ids: set[int]) -> dict[str, Any]:
    files = [f for f in PK.files(conn, p["id"]) if f["file_code"] not in ("清单", "其他")]
    codes = [f["file_code"] for f in files]
    items = PK.validation(conn, p["id"])
    warns = [i for i in items if i["result"] == "warn"]
    blocks = [i for i in items if i["result"] == "block"]
    excluded = sum(int(i["affected_rows"] or 0) for i in warns if i["check_name"] in ("parse", "unique_key"))
    months = None
    if p["months_from"] and p["months_to"]:
        months = len(PK.month_range(p["months_from"], p["months_to"]))
    if p["conclusion"] == "warn":
        sub = f"可计算 · {len(warns)} 个警告" + (f"，排除 {excluded:,} 行" if excluded else "")
    elif p["conclusion"] == "block":
        sub = f"不可计算 · {len(blocks)} 个阻断项"
    else:
        sub = ""
    note = []
    if p["kind"] == "cross" and "C6" not in codes:
        note.append("无 C6，缺少痛点信号")
    return {**p, "codes_text": PK.file_codes_text(codes) if codes else "—", "n_files": len(files),
            "files_note": " · ".join(note), "months_n": months, "is_current": p["id"] in cur_ids,
            "conclusion_label": CONCLUSION.get(p["conclusion"], p["conclusion"]), "conclusion_sub": sub,
            "kind_label": KIND_LABEL.get(p["kind"] or "", "无法识别"), "contract_label": CONTRACT_LABEL.get(p["kind"] or "", "")}


@router.get("/packages", response_class=HTMLResponse)
def packages_page(request: Request, staged: str | None = None, error: str | None = None) -> HTMLResponse:
    app, cid = _app_cid(request)
    meta = _staged(app, staged)
    preview = None
    with app.engine.begin() as conn:
        hist = PK.current_package(conn, cid, "history")
        cross = PK.current_package(conn, cid, "cross")
        cur_ids = {p["id"] for p in (hist, cross) if p}
        rows = [_package_row(conn, p, cur_ids) for p in PK.list_packages(conn, cid)]
        if meta:
            src = Path(meta["src"])
            if not src.exists():
                meta, error = None, "所选的数据包已不在原位置，请重新选择"
            else:
                preview = PK.preview(conn, app.settings, cid, src)
                preview["size"] = meta.get("size") or preview.get("size")
        job = jobs.running(conn)
    importing = bool(job and job["kind"] == "import")
    counts = {"all": len(rows), "history": sum(1 for r in rows if r["kind"] == "history"),
              "cross": sum(1 for r in rows if r["kind"] == "cross")}
    return C.render(request, "pages/F01-01.html", "PAGE-F01-01", {
        "rows": rows, "counts": counts, "hist": hist, "cross": cross, "meta": meta, "preview": preview,
        "staged": staged if meta else None, "error": error, "importing": importing, "busy": job,
        "focus_import": request.query_params.get("import") == "1",
        "readonly_dir": str(app.settings.packages_dir),
    })


@router.post("/packages/stage")
async def packages_stage(request: Request) -> JSONResponse:
    """Accept a zip, a folder (several files with relative paths) or a typed local path; then preview."""
    app, _cid = _app_cid(request)
    form = await request.form()
    token = secrets.token_hex(8)
    path_text = str(form.get("path") or "").strip().strip('"')
    uploads = [f for f in form.getlist("files") if hasattr(f, "filename") and f.filename]
    if path_text:
        src = Path(path_text).expanduser()
        if not src.exists():
            return _invalid("找不到这个位置", {"path": "找不到这个文件或文件夹，请检查路径"})
        if src.is_file() and src.suffix.lower() != ".zip":
            return _invalid("请选择 zip 文件或数据包文件夹", {"path": "请选择 zip 文件或数据包文件夹"})
        size = src.stat().st_size if src.is_file() else sum(p.stat().st_size for p in src.iterdir() if p.is_file())
        _write_staged(app, token, {"src": str(src), "name": src.name, "size": size, "read_at": clock.now_iso(),
                                   "kind": "path"})
    elif uploads:
        rels = [str(r) for r in form.getlist("paths")]
        dest = _staged_root(app) / token
        dest.mkdir(parents=True, exist_ok=True)
        total = 0
        if len(uploads) == 1 and (uploads[0].filename or "").lower().endswith(".zip") and not rels:
            name = Path(uploads[0].filename or "数据包.zip").name
            target = dest / name
            with open(target, "wb") as out:
                while chunk := await uploads[0].read(1 << 20):
                    out.write(chunk)
                    total += len(chunk)
            src = target
        else:
            first = (rels[0] if rels else uploads[0].filename or "数据包").replace("\\", "/")
            folder = first.split("/")[0] if "/" in first else "数据包"
            root = dest / Path(folder).name
            root.mkdir(parents=True, exist_ok=True)
            for i, up in enumerate(uploads):
                rel = (rels[i] if i < len(rels) else up.filename or f"file{i}").replace("\\", "/")
                parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
                if len(parts) > 2:  # only files directly in the package folder
                    continue
                target = root / Path(parts[-1]).name
                with open(target, "wb") as out:
                    while chunk := await up.read(1 << 20):
                        out.write(chunk)
                        total += len(chunk)
            src = root
        _write_staged(app, token, {"src": str(src), "name": src.name, "size": total, "read_at": clock.now_iso(),
                                   "kind": "upload"})
    else:
        return _invalid("请选择 zip 或数据包文件夹", {"path": "请选择 zip、文件夹，或填写本机路径"})
    _cleanup_staged(app, keep=token)
    return C.ok(redirect=f"/packages?staged={token}")


@router.post("/packages/import")
async def packages_import(request: Request) -> JSONResponse:
    app, cid = _app_cid(request)
    form = await request.form()
    token = str(form.get("staged") or "")
    meta = _staged(app, token)
    if not meta or not Path(meta["src"]).exists():
        return _invalid("所选的数据包已不在原位置，请重新选择")
    src = Path(meta["src"])
    settings, operator = app.settings, app.operator

    def work(conn: Connection, report: Any) -> Any:
        report("读取清单、计算指纹并校验", 0.1)
        try:
            r = PK.import_package(conn, settings, cid, src, operator)
        except PK.ImportRejected as exc:
            return {"duplicate": exc.label, "staged": token}
        return {"package_id": r.package_id, "label": r.label, "conclusion": r.conclusion, "staged": token}

    try:
        jid = jobs.run(app.engine, cid, "import", app.operator, work, background=True)
    except jobs.JobBusy as exc:
        return C.fail(str(exc), status=409)  # keep: busy is a conflict
    return C.ok(job=jid, redirect=f"/packages/import-done?job={jid}")


@router.get("/packages/import-done")
def packages_import_done(request: Request, job: int) -> RedirectResponse:
    app, _cid = _app_cid(request)
    res = SV.job_result(app, job)
    out = res.get("result") or {}
    if res.get("status") == "failed":
        return RedirectResponse(f"/packages?error={quote(res.get('error') or '导入失败')}", status_code=303)
    if out.get("duplicate"):
        return RedirectResponse(f"/packages?staged={out.get('staged')}", status_code=303)
    pid = out.get("package_id")
    if not pid:
        return RedirectResponse("/packages", status_code=303)
    meta = _staged(app, out.get("staged"))
    if meta and meta.get("kind") == "upload":
        shutil.rmtree(_staged_root(app) / out["staged"], ignore_errors=True)
    toast = f"{out.get('label')} 校验完成：{CONCLUSION.get(out.get('conclusion') or '', '')}"
    return RedirectResponse(f"/packages/{pid}/report?toast={quote(toast)}", status_code=303)


# =============================================================================================
# PAGE-F01-02 校验报告
# =============================================================================================


def _resolve_package(conn: Connection, ref: str) -> dict[str, Any]:
    pkg = PK.by_label(conn, ref) if ref.upper().startswith("P-") else (PK.get(conn, int(ref)) if ref.isdigit() else None)
    if pkg is None:
        raise HTTPException(status_code=404, detail="数据包不存在")
    return pkg


def _parse_detail(item: dict[str, Any]) -> dict[str, Any]:
    note = item.get("affected_note") or ""
    if note.startswith("{"):
        return D.loads(note, {}) or {}
    return {}


def report_context(conn: Connection, pkg: dict[str, Any], settings: Any) -> dict[str, Any]:
    cfg = CAT.current_version(conn, pkg["category_id"])["config"]
    items = PK.validation(conn, pkg["id"])
    files = {f["file_code"]: f for f in PK.files(conn, pkg["id"])}
    manifest_items = [i for i in items if i["check_name"] == "manifest"]
    kind = pkg["kind"]
    dims = tuple(cfg.get("attribute_dims") or S.C4_DIMS)
    specs = (S.history_specs(dims) if kind == "history" else S.cross_specs(dims)) if kind else []
    pkg_fields = {(r[0], r[1]) for r in conn.execute(select(D.package_field.c.file_code, D.package_field.c.field)
                                                   .where(D.package_field.c.package_id == pkg["id"]))}
    matrix, tabs, warn_list, block_list = [], [], [], []
    excluded_by_file: dict[str, int] = {}
    for fs in specs:
        its = [i for i in items if i["file_code"] == fs.code]
        if not its:
            continue
        by = {}
        for i in its:
            by.setdefault(i["check_name"], []).append(i)
        rf = (by.get("required_file") or [None])[0]
        present = rf is not None and rf["result"] == "pass"
        req_items = by.get("required_field", [])
        parse = (by.get("parse") or [None])[0]
        uniq = (by.get("unique_key") or [None])[0]
        cov = (by.get("coverage") or [None])[0]
        pdet = _parse_detail(parse) if parse else {}
        req_pass = sum(1 for i in req_items if i["result"] == "pass")
        req_block = [i for i in req_items if i["result"] == "block"]
        row = {"code": fs.code, "label": S.FILE_NAMES.get(fs.code, fs.code), "key": " × ".join(fs.key),
               "optional": not fs.required_file, "present": present, "rows": files.get(fs.code, {}).get("row_count"),
               "file": rf, "missing": rf is not None and rf["result"] in ("block", "na"), "cells": {}}
        if row["missing"]:
            row["cells"]["file"] = (rf["result"], "缺失" if rf["result"] == "block" else "未提供（可选）")
        else:
            row["cells"]["file"] = ("pass", "可选 · 已提供" if not fs.required_file else "已提供")
            if req_items:
                rr = "block" if req_block else "pass"
                row["cells"]["fields"] = (rr, f"{req_pass} / {len(req_items)} 个 · " +
                                          ("整列" if req_block else "0 行"))
            if parse:
                fields = "、".join((pdet.get("by_field") or {}).keys()) or (parse["field"] or "")
                row["cells"]["parse"] = (parse["result"], f"{int(parse['affected_rows'] or 0):,} 行" +
                                         (f" · {fields}" if parse["affected_rows"] and fields else "")
                                         if parse["affected_note"] != "整个文件" else "整个文件")
            if uniq:
                row["cells"]["unique"] = (uniq["result"], f"{int(uniq['affected_rows'] or 0):,} 行重复")
            if cov:
                row["cells"]["cover"] = (cov["result"], (cov["affected_note"] or "") if cov["result"] != "warn"
                                         else (cov["message"] or cov["affected_note"] or ""))
        matrix.append(row)
        # problem details
        for i in its:
            if i["result"] not in ("warn", "block") or i["check_name"] == "manifest":
                continue
            entry = {"item": i, "file_label": S.FILE_NAMES.get(fs.code, fs.code), "rows_total": row["rows"],
                     "detail": _parse_detail(i) if i["check_name"] == "parse" else {}}
            n = int(i["affected_rows"] or 0)
            entry["share"] = (n / row["rows"]) if row["rows"] and i["check_name"] in ("parse", "unique_key") else None
            if i["result"] == "warn" and i["check_name"] in ("parse", "unique_key"):
                excluded_by_file[fs.code] = excluded_by_file.get(fs.code, 0) + n
            (block_list if i["result"] == "block" else warn_list).append(entry)
        # required-field tab
        if present:
            bad_fields = pdet.get("by_field") or {}
            legacy = [f for f in (parse["field"] or "").split("、") if f] if parse and not bad_fields else []
            frows = []
            for fname, dtype in fs.required.items():
                it = next((i for i in req_items if i["field"] == fname), None)
                if it and it["result"] == "block":
                    frows.append({"field": fname, "fmt": FORMATS.get(dtype, dtype), "result": "block",
                                  "rows": "整列", "note": "缺少必需字段"})
                    continue
                n = bad_fields.get(fname)
                if n is None and fname in legacy:
                    n = int(parse["affected_rows"] or 0) if len(legacy) == 1 else None
                if n or fname in legacy:
                    ex = "、".join((pdet.get("examples") or {}).get(fname, []))
                    frows.append({"field": fname, "fmt": FORMATS.get(dtype, dtype), "result": parse["result"],
                                  "rows": f"{n:,}" if n is not None else "见问题明细",
                                  "note": ("已排除" if parse["result"] == "warn" else "超过 1%，不能计算") +
                                          (f"；示例值 {ex}" if ex else "")})
                else:
                    frows.append({"field": fname, "fmt": FORMATS.get(dtype, dtype), "result": "pass", "rows": "0",
                                  "note": "存在，全部可解析"})
            opt = [f for f in fs.optional if (fs.code, f) in pkg_fields]
            known = set(fs.required) | set(fs.optional)
            extra = sorted(f for (fc, f) in pkg_fields if fc == fs.code and f not in known)
            tabs.append({"code": fs.code, "label": S.FILE_NAMES.get(fs.code, fs.code), "rows": frows,
                         "optional": opt, "extra": extra})
    blocks_total = sum(1 for i in items if i["result"] == "block")
    warns_total = sum(1 for i in items if i["result"] == "warn")
    for i in manifest_items:
        if i["result"] == "block":
            block_list.insert(0, {"item": i, "file_label": "清单文件", "rows_total": None, "share": None, "detail": {}})
    present_files = [m for m in matrix if not m["missing"]]
    req_specs = [fs for fs in specs if fs.required_file]
    opt_present = [m["code"] for m in matrix if m["optional"] and not m["missing"]]
    total_rows = sum(int(m["rows"] or 0) for m in present_files)
    excl_total = sum(excluded_by_file.values())
    # next-step card: changes against the previous package of the same type
    draft = CT.draft_items(conn, pkg["category_id"])
    mine = [d for d in draft if d["package_id"] == pkg["id"]]
    changed = {k: [d for d in mine if d["change_kind"] == k] for k in ("新增", "类型改变", "缺少")}
    pending = [d for d in draft if d["status"] != "confirmed"]
    prev = conn.execute(select(D.package.c.label).where(
        D.package.c.category_id == pkg["category_id"], D.package.c.kind == kind, D.package.c.id < pkg["id"],
        D.package.c.conclusion != "block").order_by(D.package.c.id.desc()).limit(1)).scalar()
    step = conn.execute(select(D.run_step.c.ended_at).where(
        D.run_step.c.step == "导入校验", D.run_step.c.link == f"/packages/{pkg['id']}/report")).scalar()
    cur_ids = {p["id"] for p in (PK.current_package(conn, pkg["category_id"], "history"),
                                 PK.current_package(conn, pkg["category_id"], "cross")) if p}
    no_c6 = kind == "cross" and not any(m["code"] == "C6" and not m["missing"] for m in matrix)
    return {
        "report_pkg": pkg, "kind_label": KIND_LABEL.get(kind or "", "无法识别"),
        "contract_label": CONTRACT_LABEL.get(kind or "", "无法选择约定"),
        "months_n": len(PK.month_range(pkg["months_from"], pkg["months_to"])) if pkg["months_from"] and pkg["months_to"] else None,
        "matrix": matrix, "tabs": tabs, "warn_list": warn_list, "block_list": block_list,
        "blocks_total": blocks_total, "warns_total": warns_total, "excluded_by_file": excluded_by_file,
        "excl_total": excl_total, "files_present": len(present_files),
        "files_expected": len(req_specs) + len([m for m in matrix if m["optional"]]),
        "req_total": len(req_specs), "req_present": sum(1 for m in matrix if not m["optional"] and not m["missing"]),
        "opt_present": opt_present, "total_rows": total_rows, "manifest_block": any(
            i["result"] == "block" for i in manifest_items), "manifest_items": manifest_items,
        "changed": changed, "pending": pending, "prev_label": prev, "first_contract": CT.current_version(
            conn, pkg["category_id"]) is None, "checked_at": step or pkg["created_at"], "is_current": pkg["id"] in cur_ids,
        "no_c6": no_c6, "field_total": len(mine) or len(draft),
        "req_field_total": sum(len(t["rows"]) for t in tabs),
        "req_field_pass": sum(1 for t in tabs for r in t["rows"] if r["result"] == "pass"),
    }


@router.get("/packages/{ref}/report", response_class=HTMLResponse)
def package_report(request: Request, ref: str) -> HTMLResponse:
    app, _cid = _app_cid(request)
    with app.engine.begin() as conn:
        pkg = _resolve_package(conn, ref)
        ctx = report_context(conn, pkg, app.settings)
    return C.render(request, "pages/F01-02.html", "PAGE-F01-02", ctx)


# =============================================================================================
# PAGE-F02-01 字段约定
# =============================================================================================

GRAINS = ("子体", "父体", "父体（疑似）", "SPU", "关键词", "评论", "立项")
NATURES = ("平台实测", "第三方估算", "推导", "人工标注")
TIMINGS = ("当月值", "快照")
USAGES = ("直接用", "按规则用", "回测不用")
HEALTH_FIELD = {("C1", "上架日期"): "family_span", ("C2", "上架日期"): "family_span",
                ("C1", "首次评分日期"): "first_review_early", ("C2", "首次评分日期"): "first_review_early",
                ("C1", "子体月销量"): "below_bought", ("C1", "当月父ASIN"): "parent_change"}


def _pct1(v: float | None) -> str:
    return "无数据" if v is None else f"{v:.1f}%"


def _status_text(status: str | None, source: str | None) -> str:
    if status == "confirmed":
        return f"已确认（{'批量' if source == '批量确认' else (source or '逐项')}）"
    return "未确认"


def _attr_text(attr: str, value: Any) -> str:
    if attr == "status":
        return "已确认" if value == "confirmed" else "未确认"
    if value in (None, ""):
        return "—"
    return str(value)


def _health_by_item(conn: Connection, cid: int, package_id: int | None) -> dict[str, dict[str, Any]]:
    if not package_id:
        return {}
    return {r["item"]: r for r in H.results(conn, cid, package_id)}


def _evidence_cell(key: tuple[str, str], it: dict[str, Any], ev: dict[str, Any] | None,
                   health: dict[str, dict[str, Any]], pkg_label: str) -> dict[str, Any]:
    """体检证据 column: text, n and the popover details (AC-F02-01; missing evidence → 无数据)."""
    hk = HEALTH_FIELD.get(key)
    if hk and hk in health and health[hk].get("value") is not None:
        h = health[hk]
        label = CAT.HEALTH_LABELS[hk]
        if hk == "parent_change":
            text_ = f"跨月换父体的子体 {int(h['numerator'] or 0):,} 个"
        elif hk == "family_span":
            text_ = f"同父体跨度 >180 天 {_pct1(h['value'])}"
        elif hk == "first_review_early":
            text_ = f"首评早于上架 >7 天 {_pct1(h['value'])}"
        else:
            text_ = f"低于购买标签下界 {_pct1(h['value'])}"
        st = {"warn": "预警，未标已知晓", "acked": "预警，已知晓", "normal": "正常"}.get(h["status"], "不适用")
        pop = {"体检项": label, "分子": f"{int(h['numerator'] or 0):,}", "分母": f"{int(h['denominator'] or 0):,}",
               "预警阈值": f"{h['threshold']:g}{'%' if hk in H.PCT_ITEMS else ' 个'}" if h["threshold"] is not None else "—",
               "状态": st, "数据包": pkg_label}
        return {"text": text_, "n": int(h["denominator"] or 0), "popd": pop}
    if not ev:
        return {"text": "无数据", "n": None, "popd": None}
    rows = int(ev.get("rows") or 0)
    share = ev.get("nonnull_share")
    pop = {"有值": f"{round((share or 0) * rows):,} 行（{(share or 0) * 100:.1f}%）"}
    if ev.get("same_all_months_share") is not None:
        pop["各月取值相同"] = f"{ev['same_all_months_share'] * 100:.1f}%（{ev.get('same_all_months_n', 0):,} 个子体）"
    if ev.get("example"):
        pop["示例值"] = ev["example"]
    pop["类型"] = ev.get("dtype") or "—"
    pop["数据包"] = pkg_label
    if it.get("timing") == "快照" and ev.get("same_all_months_share") is not None:
        return {"text": f"各月取值相同 {ev['same_all_months_share'] * 100:.1f}%", "n": int(ev.get("same_all_months_n") or 0),
                "popd": pop}
    if share is not None and share < 0.999:
        return {"text": f"有值 {share * 100:.1f}%", "n": rows, "popd": pop}
    return {"text": f"{rows:,} 行，全部有值", "n": rows, "popd": pop}


def _results_using_contract(conn: Connection, cid: int) -> list[tuple[str, str]]:
    out = []
    for mode in ("history", "cross"):
        run_ = CMP.latest_run(conn, cid, mode)
        if not run_:
            continue
        tag = "" if mode == "history" else "（截面）"
        out.append((f"成败判定{tag}", f"{(run_.get('ended_at') or run_.get('created_at') or '')[:16]} 计算"))
        out.append((f"信号{tag}", f"T = {run_['t_month']}，{(run_.get('ended_at') or run_.get('created_at') or '')[:16]} 计算"))
        bt = BT.latest(conn, cid, mode)
        if bt:
            out.append((f"回测{tag}", f"{bt['code']}，{(bt['ended_at'] or '')[:16]} 完成"))
        snap = RK.latest_snapshot(conn, cid, mode)
        if snap:
            out.append((f"排序{tag}", f"{snap['label']}，{(snap['created_at'] or '')[:16]} 生成"))
    return out


def _diff_lines(changes: list[dict[str, Any]]) -> list[tuple[str, str, str, bool]]:
    """(key, old, new, old_is_note) lines for the save modal."""
    lines = []
    ordered = sorted(changes, key=lambda c: 0 if (c["after"] or {}).get("status", "confirmed") == "confirmed" else 1)
    for ch in ordered:
        fc, fname = ch["key"]
        after = ch["after"]
        if ch["new"] or ch["before"] is None:
            lines.append((f"{fc} {fname} · 确认状态", "新增字段", _status_text(after.get("status"), after.get("source")), True))
            summary = " · ".join(str(after.get(a)) for a in ("grain", "timing", "nature", "usage") if after.get(a))
            if after.get("timing") == "快照" and after.get("snapshot_date"):
                summary = summary.replace("快照", f"快照 {after['snapshot_date']}")
            lines.append((f"{fc} {fname} · 约定内容", "草稿建议，未生效" if after.get("status") != "confirmed" else "新增字段",
                          summary, True))
            continue
        before = ch["before"]
        if "status" in after or "source" in after:
            lines.append((f"{fc} {fname} · 确认状态", _status_text(before.get("status", "confirmed"), before.get("source")),
                          _status_text(after.get("status", "confirmed"), after.get("source")), False))
        for a, v in after.items():
            if a in ("status", "source"):
                continue
            lines.append((f"{fc} {fname} · {CT.ATTR_LABELS.get(a, a)}", _attr_text(a, before.get(a)), _attr_text(a, v), False))
    return lines


def _history_lines(change: dict[str, Any]) -> list[tuple[str, str, str, bool]]:
    before = D.loads(change["before"], None)
    after = D.loads(change["after"], {}) or {}
    item = change["item"]
    lines = []
    if not isinstance(before, dict):
        lines.append((f"{item} · 确认状态", "新增字段", _status_text(after.get("status"), after.get("source"))
                      if after.get("status") == "confirmed" else "未确认，不参与计算", True))
        for a in ("timing", "usage"):
            if after.get(a) and (a != "timing" or after.get(a) == "快照"):
                v = after[a] + (f" · {after['snapshot_date']}" if a == "timing" and after.get("snapshot_date") else "")
                lines.append((f"{item} · {CT.ATTR_LABELS[a]}", "新增字段", v, True))
        return lines
    for a, v in after.items():
        if a == "source" and "status" in after:
            continue
        if a == "status":
            lines.append((f"{item} · 确认状态", _status_text(before.get("status", "confirmed"), before.get("source")),
                          _status_text(v, after.get("source", before.get("source"))), False))
            continue
        lines.append((f"{item} · {CT.ATTR_LABELS.get(a, a)}", _attr_text(a, before.get(a)), _attr_text(a, v), False))
    return lines


def fields_context(conn: Connection, cid: int, open_key: str | None) -> dict[str, Any]:
    items = CT.draft_items(conn, cid)
    cur = CT.current_version(conn, cid)
    pkg_ids = sorted({i["package_id"] for i in items if i["package_id"]})
    labels = {pid: (PK.get(conn, pid) or {}).get("label", "—") for pid in pkg_ids}
    evs = {pid: CT.evidence(conn, pid) for pid in pkg_ids}
    health_pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
    health = _health_by_item(conn, cid, health_pkg["id"] if health_pkg else None)
    draft_pkg = PK.get(conn, max(pkg_ids)) if pkg_ids else None
    rows = []
    for _i, it in enumerate(items):
        key = (it["file_code"], it["field"])
        ev = evs.get(it["package_id"], {}).get(key) if it["package_id"] else None
        if it["change_kind"] == "缺少":
            ev = None
        views = []
        if it["status"] != "confirmed":
            views.append("pending")
        if it["change_kind"]:
            views.append("changed")
        if it["timing"] == "快照":
            views.append("snap")
        if it["usage"] == "按规则用":
            views.append("rule")
        rid = f"f{it['id']}"
        rows.append({**it, "rid": rid, "views": " ".join(views), "ev": _evidence_cell(
            key, it, ev, health, labels.get(it["package_id"], "—")), "key": f"{it['file_code']}|{it['field']}",
            "file_label": S.FILE_NAMES.get(it["file_code"], it["file_code"]),
            "grains": GRAINS if it["grain"] in GRAINS else GRAINS + (it["grain"],)})
    if open_key:
        opened = next((r for r in rows if r["rid"] == open_key), None)
    else:
        opened = next((r for r in rows if r["status"] != "confirmed" and r["change_kind"]), None)
    total = len(rows)
    pending = [r for r in rows if r["status"] != "confirmed"]
    changed = {k: [r for r in rows if r["change_kind"] == k] for k in ("新增", "缺少", "类型改变")}
    snaps = [r for r in rows if r["timing"] == "快照"]
    snap_dates = sorted({r["snapshot_date"] for r in snaps if r["snapshot_date"]})
    changes = CT.draft_changes(conn, cid)
    hist = CT.history(conn, cid)
    for v in hist:
        lines = [ln for ch in v["changes"] for ln in _history_lines(ch)]
        v["lines"] = lines
        v["n_fields"] = len(v["changes"])
        v["package_label"] = (PK.get(conn, v["package_id"]) or {}).get("label") if v["package_id"] else None
        v["batch"] = sum(1 for ch in v["changes"] if (D.loads(ch["after"], {}) or {}).get("source") == "批量确认")
    return {
        "rows": rows, "opened": opened["rid"] if opened else None, "cur": cur, "total": total, "pending": pending,
        "changed": changed, "snaps": snaps, "snap_dates": snap_dates, "health": health,
        "health_pkg": health_pkg, "draft_pkg": draft_pkg, "changes": changes, "diff": _diff_lines(changes),
        "pending_after": sum(1 for r in rows if r["status"] != "confirmed"), "history": hist,
        "first_summary": {"confirmed": sum(1 for r in rows if r["status"] == "confirmed"),
                          "batch": sum(1 for r in rows if r["status"] == "confirmed" and r["source"] == "批量确认"),
                          "pending": len(pending)} if not cur else None,
        "results": _results_using_contract(conn, cid), "stale": C.stale_reasons(conn, cid),
        "counts": {"all": total, "pending": len(pending), "changed": sum(1 for r in rows if r["change_kind"]),
                   "snap": len(snaps), "rule": sum(1 for r in rows if r["usage"] == "按规则用")},
        "confirmed": total - len(pending), "grains": GRAINS, "natures": NATURES, "timings": TIMINGS, "usages": USAGES,
        "rule_snapshot": [r for r in rows if r["timing"] == "快照" and r["status"] == "confirmed"],
    }


@router.get("/fields", response_class=HTMLResponse)
def fields_page(request: Request, open: str | None = None) -> HTMLResponse:  # noqa: A002
    app, cid = _app_cid(request)
    with app.engine.begin() as conn:
        ctx = fields_context(conn, cid, open)
        ctx["busy"] = jobs.running(conn)
    return C.render(request, "pages/F02-01.html", "PAGE-F02-01", ctx)


@router.post("/fields/item")
async def fields_item(request: Request) -> JSONResponse:
    app, cid = _app_cid(request)
    form = await request.form()
    fc, fname = str(form.get("file_code") or ""), str(form.get("field") or "")
    action = str(form.get("action") or "edit")
    values: dict[str, Any] = {}
    if action == "edit":
        for a in ("meaning", "grain", "timing", "snapshot_date", "nature", "usage", "rule_text"):
            if a in form:
                values[a] = str(form.get(a) or "").strip()
        if values.get("timing") == "快照":
            values["usage"] = "回测不用"
        fields_err = {}
        if "meaning" in values and not values["meaning"]:
            fields_err["meaning"] = "请填写含义"
        if values.get("timing") == "快照" and not values.get("snapshot_date"):
            fields_err["snapshot_date"] = "请填写快照日期"
        if values.get("usage") == "按规则用" and not values.get("rule_text"):
            fields_err["rule_text"] = "按规则用时请写明规则"
        if fields_err:
            return _invalid("请补全后再确认", fields_err)
    try:
        with app.engine.begin() as conn:
            CT.update_draft(conn, cid, fc, fname, values, confirm=True, source="逐项")
            rid = conn.execute(select(D.contract_draft_item.c.id).where(
                D.contract_draft_item.c.category_id == cid, D.contract_draft_item.c.file_code == fc,
                D.contract_draft_item.c.field == fname)).scalar()
    except CT.ContractError as exc:
        return _invalid(str(exc))
    what = "按修改后的内容" if action == "edit" else "按建议"
    msg = quote(f"已在草稿中{what}确认 {fname}（逐项），保存为新版本后生效")
    return C.ok(redirect=f"/fields?open=f{rid}&toast={msg}#f{rid}")


@router.post("/fields/batch")
async def fields_batch(request: Request) -> JSONResponse:
    app, cid = _app_cid(request)
    form = await request.form()
    keys = [tuple(str(k).split("|", 1)) for k in form.getlist("keys") if "|" in str(k)]
    if not keys:
        return _invalid("请先勾选字段")
    only = form.get("suggested_only") in ("1", "on", "true")
    with app.engine.begin() as conn:
        n = CT.batch_confirm(conn, cid, keys, suggested_only=only)  # type: ignore[arg-type]
    if n == 0:
        return _invalid("所选字段都已确认，或没有建议为“直接用”的待确认字段")
    return C.ok(redirect="/fields", toast=f"已按建议确认 {n} 个字段（来源：批量确认），保存为新版本后生效")


@router.post("/fields/save")
async def fields_save(request: Request) -> JSONResponse:
    """Same steps as service.contract_save; the step starts at the first draft change (F14 timing)."""
    app, cid = _app_cid(request)
    form = await request.form()
    note = str(form.get("note") or "").strip()
    try:
        with app.engine.begin() as conn:
            started = CT.confirm_started_at(conn, cid) or clock.now_iso()
            no = CT.save_version(conn, cid, app.operator, note)
            pkgs = [p for p in (PK.current_package(conn, cid, "history"), PK.current_package(conn, cid, "cross")) if p]
            for p in pkgs:
                SPU.refresh_suggestions(conn, cid, p["id"], app.operator)
            pending = CT.pending_count(conn, cid)
            runs.record_step(conn, cid, "字段确认", started, clock.now_iso(), app.operator,
                             result=f"约定 v{no} 已保存" + (f" · {pending} 个字段待确认，不参与计算" if pending else ""),
                             link="/fields", package_id=pkgs[0]["id"] if pkgs else None)
            stale = bool(C.stale_reasons(conn, cid))
    except CT.ContractError as exc:
        return _invalid(str(exc))
    toast = f"已保存为字段约定 v{no}" + ("；成败、信号、回测和排序已标为需重算" if stale else "")
    return C.ok(redirect="/fields", toast=toast)


# =============================================================================================
# PAGE-F03-02 数据体检
# =============================================================================================

SAMPLE_COLS = {
    "first_review_early": ["子ASIN", "父ASIN", "上架日期", "首次评分日期", "早于上架（天）"],
    "family_span": ["父ASIN", "子体数", "最早上架", "最晚上架", "跨度（天）"],
    "below_bought": ["子ASIN", "月份", "子体月销量", "标签", "标签下界", "低于下界"],
    "unknown_share": ["子ASIN", "维度", "标签值"],
    "parent_change": ["子ASIN", "月份", "父ASIN 变化"],
    "dup_key": ["文件", "重复行号"],
}
NUM_COLS = {"早于上架（天）", "子体数", "跨度（天）", "子体月销量", "标签下界", "低于下界"}
MONO_COLS = {"子ASIN", "父ASIN", "父ASIN 变化", "标签"}
COL_TAG = {"子体月销量": "估算", "低于下界": "推导"}
HEALTH_DESC = {
    "first_review_early": "首评日期可能是父体共享口径：新子体挂在老父体下，会带上父体早年的评论。最早首评早于上架超过 7 天的 SPU 会标“疑似重新上架”。相关字段：C1、C2 的首次评分日期。",
    "family_span": "跨度大多是老父体陆续挂上新子体，或上架日期取的是最早时间。晚于 SPU 上架日的子体按“新变体”处理，不计为新品。",
    "below_bought": "子体月销量是第三方估算；低于亚马逊“过去一个月 x+ 购买”标签的下界，说明估算偏低。",
    "unknown_share": "“未知”的子体归入该维度的“未知”档，不进入具体细分。",
    "parent_change": "子体换了父体，可能影响 SPU 归并和类型属性的父体回填。",
    "dup_key": "主键重复的行按“无法解析的行”处理：保留首次出现的行，其余在计算中排除。",
}


def _health_item_view(r: dict[str, Any], total_rows: int) -> dict[str, Any]:
    item = r["item"]
    v, num_, den = r["value"], r["numerator"], r["denominator"]
    th = r["threshold"]
    parts: list[tuple[str, str, int | None]] = []  # (label, html-ish text, n tag)
    if r.get("na") or v is None:
        parts.append(("数值", "不适用", None))
    elif item == "first_review_early":
        parts += [("数值", f"{v:.1f}%", int(den or 0)), ("分子", f"{int(num_ or 0):,} 个子体", None),
                  ("分母", f"{int(den or 0):,} 个有首次评分日期的子体", None)]
    elif item == "family_span":
        parts += [("数值", f"{int(num_ or 0):,} 个家族，占 {v:.1f}%", int(den or 0)),
                  ("分母", f"{int(den or 0):,} 个有 2 个以上子体的家族", None)]
    elif item == "below_bought":
        parts += [("数值", f"{v:.1f}%", int(den or 0)), ("分子", f"{int(num_ or 0):,} 个子体-月", None),
                  ("分母", f"{int(den or 0):,} 个有标签的子体-月", None)]
    elif item == "unknown_share":
        parts += [("最高", f"{v:.1f}%（{(r.get('detail') or {}).get('max_dim', '')}）", int(den or 0)),
                  ("分母", f"{int(den or 0):,} 个子体（C4 属性标签）", None)]
    elif item == "parent_change":
        share = (num_ / den * 100) if den else None
        parts += [("数值", f"{int(num_ or 0):,} 个子体" + (f"，占 {share:.1f}%" if share is not None else ""), int(den or 0)),
                  ("分母", f"{int(den or 0):,} 个出现过的子体", None)]
    else:
        parts += [("数值", f"{int(num_ or 0):,} 行", None),
                  ("分母", f"{total_rows:,} 行（各文件按各自主键检查）", None)]
    if th is None:
        th_text = "未设置"
    elif item in H.PCT_ITEMS:
        th_text = f"{th:g}%" + ("（每个维度）" if item == "unknown_share" else "")
    elif item == "dup_key" and float(th) == 0:
        th_text = "出现 1 行即预警"
    else:
        th_text = f"{th:g} {'个子体' if item == 'parent_change' else '条'}"
    if th is None:
        th_short = "未设置"
    elif item in H.PCT_ITEMS:
        th_short = f"{th:g}%"
    else:
        th_short = f"{th:g} {'个子体' if item == 'parent_change' else '条'}"
    samples = []
    cols = SAMPLE_COLS[item]
    from oppo.core.health import _lower_bound

    for s in r["samples"] or []:
        row = dict(s)
        if item == "below_bought":
            lb = _lower_bound(row.get("标签"))
            row["标签下界"] = f"{lb:g}" if lb else "—"
            units = row.get("子体月销量")
            row["低于下界"] = f"{(1 - units / lb) * 100:.0f}%" if lb and units is not None else "—"
            row["子体月销量"] = f"{units:,} 件" if units is not None else "—"
        if "早于上架（天）" in row:
            row["早于上架（天）"] = f"{row['早于上架（天）']:,} 天"
        if "跨度（天）" in row:
            row["跨度（天）"] = f"{row['跨度（天）']:,} 天"
        samples.append([(c, row.get(c, "—")) for c in cols])
    dims = []
    if item == "unknown_share":
        all_dims = (r.get("detail") or {}).get("dims") or []
        scale = max(float(th or 40) / 0.8, max((d["占比"] for d in all_dims), default=0) or 1)
        for d in all_dims:
            if d["未知"] == 0 and len(dims) >= 4:
                continue
            dims.append({**d, "width": round(min(100.0, d["占比"] / scale * 100), 1),
                         "near": th is not None and d["占比"] > float(th) * 0.9 and d["占比"] <= float(th),
                         "over": th is not None and d["占比"] > float(th)})
        ref = round(float(th or 40) / scale * 100, 1)
    else:
        ref = None
    return {**r, "parts": parts, "th_text": th_text, "th_short": th_short, "cols": cols, "sample_rows": samples, "dims": dims, "ref": ref,
            "desc": HEALTH_DESC[item]}


@router.get("/health", response_class=HTMLResponse)
def health_page(request: Request, package: int | None = None) -> HTMLResponse:
    app, cid = _app_cid(request)
    with app.engine.begin() as conn:
        pkg = PK.get(conn, package) if package else (PK.current_package(conn, cid, "history")
                                                     or PK.current_package(conn, cid, "cross"))
        cfg_ver = CAT.current_version(conn, cid)
        cv = CT.current_version(conn, cid)
        ctx: dict[str, Any] = {"hpkg": pkg, "cfg_no": cfg_ver["version_no"], "cv": cv, "items": [], "fps": []}
        if pkg and pkg["conclusion"] != "block":
            total_rows = sum(int(f["row_count"] or 0) for f in PK.files(conn, pkg["id"]) if f["row_count"])
            rows = H.results(conn, cid, pkg["id"])
            ctx["items"] = [_health_item_view(r, total_rows) | {"no": i} for i, r in enumerate(rows, start=1)]
            ctx["fps"] = [f for f in H.fingerprint_rows(conn, pkg["id"])]
            step = conn.execute(select(D.run_step.c.started_at, D.run_step.c.ended_at).where(
                D.run_step.c.step == "数据体检", D.run_step.c.link == f"/health?package={pkg['id']}")
                .order_by(D.run_step.c.id.desc()).limit(1)).first()
            ctx["ran"] = (step[0], step[1]) if step else (rows[0]["created_at"], rows[0]["created_at"]) if rows else None
            ctx["import_at"] = pkg["created_at"]
            ctx["acks"] = {r["item"]: r["ack"] for r in rows if r["ack"]}
    warn = [i for i in ctx["items"] if i["status"] == "warn"]
    ctx.update(warn=warn, n_normal=sum(1 for i in ctx["items"] if i["status"] in ("normal", "acked")),
               fp_ok=bool(ctx["fps"]) and all(f["ok"] for f in ctx["fps"]))
    return C.render(request, "pages/F03-02.html", "PAGE-F03-02", ctx)


@router.post("/health/ack")
async def health_ack(request: Request) -> JSONResponse:
    app, cid = _app_cid(request)
    form = await request.form()
    try:
        pid = int(str(form.get("package_id") or "0"))
    except ValueError:
        pid = 0
    item, note = str(form.get("item") or ""), str(form.get("note") or "")
    if not note.strip():
        return _invalid("请填写说明", {"note": "请填写说明，说明会和操作人、时间一起记录"})
    try:
        with app.engine.begin() as conn:
            H.acknowledge(conn, cid, pid, item, note, app.operator)
    except H.AckError as exc:
        return _invalid(str(exc), {"note": str(exc)} if "说明" in str(exc) else None)
    return C.ok(redirect=f"/health?package={pid}", toast="已标为已知晓，首页不再提示这项预警")


# =============================================================================================
# PAGE-F13-01 品类配置
# =============================================================================================

SITES = [("US", "US · 美国"), ("CA", "CA · 加拿大"), ("UK", "UK · 英国"), ("DE", "DE · 德国")]
SPLITS = ("2/3 : 1/3", "3/4 : 1/4", "1/2 : 1/2")
FIELD_KIND = {path: kind for _g, path, _l, kind in CAT.CONFIG_FIELDS}
FIELD_LABEL = {path: label for _g, path, label, _k in CAT.CONFIG_FIELDS}


def _fmt_cfg(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if isinstance(v, int) and abs(v) >= 1000:
        return f"{v:,}"
    return str(v)


def _width_rules(cfg: dict[str, Any]) -> dict[str, str]:
    rule = ((cfg.get("keyword_mapping") or {}).get("width") or {}).get("rule") or ""
    out = {}
    for part in rule.replace(";", "；").split("；"):
        if "：" in part:
            k, v = part.split("：", 1)
            out[k.strip()] = v.strip()
    return out


def _form_values(form: Any, base: dict[str, Any]) -> dict[str, Any]:
    """Turn the posted page form into CONFIG_FIELDS paths (keyword rows and type-attribute checkboxes)."""
    values: dict[str, Any] = {}
    for _g, path, _l, _k in CAT.CONFIG_FIELDS:
        if path in form:
            values[path] = str(form.get(path) or "")
    if "ta_present" in form:
        values["type_attributes"] = "、".join(str(x) for x in form.getlist("ta"))
    wl = [(k[len("kw.width."):], str(v)) for k, v in form.multi_items() if k.startswith("kw.width.")]
    if wl:
        values["keyword_mapping.width.rule"] = "；".join(f"{k}：{v.strip()}" for k, v in wl if v.strip()) or ""
    fl = [(k[len("kw.form."):], str(v)) for k, v in form.multi_items() if k.startswith("kw.form.")]
    if fl:
        values["keyword_mapping.form.map_text"] = "；".join(f"{k}：{v.strip()}" for k, v in fl if v.strip()) or ""
    return values


def _target_category(conn: Connection, request: Request) -> int:
    q = request.query_params.get("category")
    if q and q.isdigit() and conn.execute(select(D.category.c.id).where(D.category.c.id == int(q))).first():
        return int(q)
    return CAT.current_category_id(conn)


def _cur_cfg(conn: Connection, cid: int) -> tuple[dict[str, Any], int, dict[str, Any] | None]:
    try:
        cur = CAT.current_version(conn, cid)
        return cur["config"], cur["version_no"], cur
    except LookupError:
        return {}, 0, None


def _apply(conn: Connection, cid: int, form: Any) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], int]:
    cur_cfg, cur_no, _ = _cur_cfg(conn, cid)
    draft = CAT.get_draft(conn, cid)
    base = draft["config"] if draft else cur_cfg
    values = _form_values(form, base)
    cfg, errors = CAT.apply_form(base, values)
    return cfg, errors, cur_cfg, cur_no


def _store_draft(conn: Connection, cid: int, cfg: dict[str, Any], cur_cfg: dict[str, Any], cur_no: int) -> None:
    if cur_cfg and not CAT.diff(cur_cfg, cfg):
        CAT.discard_draft(conn, cid)
    else:
        CAT.save_draft(conn, cid, cfg, cur_no)


def _diff_rows(old: dict[str, Any], new: dict[str, Any]) -> list[list[str]]:
    if not old:
        return [["全部配置项", "—", "新建，保存为 v1"]]
    return [[label, _fmt_cfg(a), _fmt_cfg(b)] for label, a, b in CAT.diff(old, new)]


def _health_now(conn: Connection, cid: int) -> dict[str, dict[str, Any]]:
    pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
    return ({"_pkg": pkg, **{r["item"]: r for r in H.results(conn, cid, pkg["id"])}} if pkg else {})


def _dependents(conn: Connection, cid: int, cfg_ver_id: int | None) -> list[dict[str, str]]:
    out = []
    for mode in ("history", "cross"):
        run_ = CMP.latest_run(conn, cid, mode)
        if not run_ or run_["config_version_id"] != cfg_ver_id:
            continue
        tag = "（截面）" if mode == "cross" else ""
        n = conn.execute(select(func.count()).select_from(D.spu).where(
            D.spu.c.run_id == run_["id"], D.spu.c.is_new == 1, D.spu.c.rising == 1)).scalar() or 0
        segs = conn.execute(select(func.count(D.signal_value.c.segment_key.distinct())).where(
            D.signal_value.c.run_id == run_["id"], D.signal_value.c.t_month == run_["t_month"])).scalar() or 0
        out.append({"icon": "cube", "title": f"成败判定{tag}", "desc": f"{n:,} 个起量新 SPU"})
        out.append({"icon": "chart-line-up", "title": f"信号{tag}", "desc": f"截至 {run_['t_month']} · {segs} 个细分"})
        bt = BT.latest(conn, cid, mode)
        if bt and bt["config_version_id"] == cfg_ver_id:
            from oppo.core import cards as CARD

            card = CARD.get(conn, bt["card_id"]) if bt.get("card_id") else None
            out.append({"icon": "flask", "title": f"回测{tag}",
                        "desc": f"{bt['code']}" + (f"，生成判定卡 {card['label']}" if card else "")})
    return out


@router.get("/settings/category", response_class=HTMLResponse)
def category_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = _target_category(conn, request)
        current_cid = CAT.current_category_id(conn)
        category = dict(conn.execute(select(D.category).where(D.category.c.id == cid)).mappings().first())
        cur_cfg, cur_no, cur = _cur_cfg(conn, cid)
        draft = CAT.get_draft(conn, cid)
        cfg = draft["config"] if draft else cur_cfg
        diff_rows = _diff_rows(cur_cfg, cfg) if draft else []
        modified = {label for label, *_ in diff_rows}
        versions = CAT.versions(conn, cid)
        logs = conn.execute(select(D.change_log).where(D.change_log.c.category_id == cid,
                                                       D.change_log.c.object == "品类配置")
                            .order_by(D.change_log.c.id)).mappings().all()
        by_ver: dict[str, list[dict[str, Any]]] = {}
        for lg in logs:
            by_ver.setdefault(lg["object_id"], []).append(dict(lg))
        for v in versions:
            v["changes"] = [[lg["item"], _fmt_cfg(D.loads(lg["before"])), _fmt_cfg(D.loads(lg["after"]))]
                            for lg in by_ver.get(f"v{v['version_no']}", [])]
        health = _health_now(conn, cid) if cid == current_cid else {}
        stale = [r for r in C.stale_reasons(conn, cid) if r.startswith("品类配置")] if cid == current_cid else []
        deps = _dependents(conn, cid, cur["id"] if cur else None) if cur else []
        bt = BT.latest(conn, cid, "history") if cid == current_cid else None
        categories = [dict(r) for r in conn.execute(select(D.category.c.id, D.category.c.name, D.category.c.is_draft)
                                                    .order_by(D.category.c.id)).mappings().all()]
        busy = jobs.running(conn)
    seg_dims = {d["key"]: d for d in (cfg.get("segment_dims") or [])}
    n_segments = 1
    for d in seg_dims.values():
        n_segments *= max(1, len(d.get("bins") or []))
    decided = len((bt or {}).get("result", {}).get("decided_batches") or []) if bt else 0
    split = cfg.get("backtest_split") or {"rule": 2, "test": 1}
    n_test = max(1, (decided * split["test"]) // (split["rule"] + split["test"])) if decided else 0
    missing = CAT.missing_required(cfg) if cfg else [lab for _g, _p, lab, _k in CAT.CONFIG_FIELDS]
    return C.render(request, "pages/F13-01.html", "PAGE-F13-01", {
        "category": category, "cid": cid, "is_current": cid == current_cid, "cfgv": cfg, "cur_cfg": cur_cfg,
        "cur_no": cur_no, "cur": cur, "draft": draft, "diff_rows": diff_rows, "modified": modified,
        "versions": versions, "health": health, "stale": stale, "deps": deps, "decided": decided, "n_test": n_test,
        "n_segments": n_segments, "seg_dims": seg_dims, "missing": missing, "categories": categories, "busy": busy,
        "sites": SITES, "splits": SPLITS, "get_path": CAT.get_path, "width_rules": _width_rules(cfg),
        "width_was": _width_rules(cur_cfg) if cur_cfg else {},
        "form_was": (((cur_cfg.get("keyword_mapping") or {}).get("form") or {}).get("map") or {}) if cur_cfg else {},
        "fmt_cfg": _fmt_cfg, "health_labels": CAT.HEALTH_LABELS, "pct_items": H.PCT_ITEMS,
    })


@router.post("/settings/category/draft")
async def category_draft(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    with app.engine.begin() as conn:
        cid = _target_category(conn, request)
        cfg, errors, cur_cfg, cur_no = _apply(conn, cid, form)
        _store_draft(conn, cid, cfg, cur_cfg, cur_no)
        n = len(_diff_rows(cur_cfg, cfg)) if (not cur_cfg or CAT.diff(cur_cfg, cfg)) else 0
    return JSONResponse({"ok": True, "fields": errors, "updated_at": clock.now_iso()[:16], "n_changes": n})


@router.post("/settings/category/preview")
async def category_preview(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    with app.engine.begin() as conn:
        cid = _target_category(conn, request)
        cfg, errors, cur_cfg, cur_no = _apply(conn, cid, form)
        _store_draft(conn, cid, cfg, cur_cfg, cur_no)
        busy = jobs.running(conn)
    if errors:
        return _invalid("有配置项不合法", errors)
    missing = CAT.missing_required(cfg)
    diff = _diff_rows(cur_cfg, cfg) if (not cur_cfg or CAT.diff(cur_cfg, cfg)) else []
    return JSONResponse({"ok": True, "diff": diff, "missing": missing,
                         "can_save": bool(diff) and not missing and not busy})


@router.post("/settings/category/save")
async def category_save(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    note = str(form.get("note") or "").strip()
    try:
        with app.engine.begin() as conn:
            cid = _target_category(conn, request)
            draft = CAT.get_draft(conn, cid)
            cur_cfg, cur_no, _ = _cur_cfg(conn, cid)
            if not draft:
                return _invalid(f"与 v{cur_no} 相比没有修改，不需要保存新版本")
            no = CAT.save_version(conn, cid, draft["config"], app.operator, note)
            stale = bool(C.stale_reasons(conn, cid))
    except CAT.ConfigError as exc:
        return _invalid(str(exc))
    toast = f"已保存为品类配置 v{no}" + (f"，依赖 v{cur_no} 的结果已标为需重算" if stale else "")
    q = f"?category={cid}&" if request.query_params.get("category") else "?"
    return C.ok(redirect=f"/settings/category{q}saved={no}", toast=toast)


@router.post("/settings/category/new")
async def category_new(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    name, site, node = (str(form.get(k) or "").strip() for k in ("name", "site", "node"))
    errs = {k: "必填" for k, v in (("name", name), ("site", site), ("node", node)) if not v}
    if errs:
        return _invalid("请填写必填项", errs)
    try:
        with app.engine.begin() as conn:
            cid = CAT.create_category(conn, name, site, node, app.operator, form.get("template") != "blank")
    except CAT.ConfigError as exc:
        return _invalid(str(exc), {"name": str(exc)} if "同名" in str(exc) else None)
    return C.ok(redirect=f"/settings/category?category={cid}", toast=f"已创建品类草稿“{name}”，逐项填写后保存为 v1")


# =============================================================================================
# PAGE-F14-01 运行记录
# =============================================================================================

STEP_LABEL = {"导入校验": ("导入", "读取清单与校验"), "数据体检": ("体检", "随导入自动运行")}


def _hm(mins: int | None) -> str:
    if mins is None:
        return "无数据"
    h, m = divmod(int(mins), 60)
    return f"{h} 小时 {m:02d} 分" if h else f"{m} 分钟"


def _step_result(s: dict[str, Any], conn: Connection, cid: int) -> tuple[str, str]:
    from oppo import fmt

    text_ = s["result"] or ""
    parts = [p.strip() for p in text_.split(" · ") if p.strip()]
    if s["step"] == "数据体检" and s["link"] and "package=" in s["link"]:
        try:
            pid = int(s["link"].split("package=")[1])
            warns = [r for r in H.results(conn, cid, pid) if r["status"] == "warn"]
            if warns:
                return f"{len(warns)} 项预警", "、".join(f"{w['label']}" for w in warns[:2]) + "，未标已知晓"
            return "正常", "6 项均未超过阈值"
        except (ValueError, IndexError):
            pass
    for i, p in enumerate(parts):
        if p in fmt.STATUS_BADGE or p in fmt.ACTION_BADGE:
            return p, " · ".join(parts[:i] + parts[i + 1:])
    return "完成", text_


@router.get("/settings/runs", response_class=HTMLResponse)
def runs_page(request: Request, month: str | None = None) -> HTMLResponse:
    app, cid = _app_cid(request)
    with app.engine.begin() as conn:
        summ = runs.summary(conn, cid)
        steps = runs.steps(conn, cid)
        pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
        cur_month = PK.add_months(pkg["months_to"], 1) if pkg and pkg.get("months_to") else None
        first = summ["first_run"]
        first_month = next((s["month"] for s in steps if s["step"] == "导入校验"), None)
        now = clock.now()
        monthly = []
        for m in reversed(summ["monthly"]):
            rec = dict(m)
            if rec["import"] is not None and rec["minutes"] is None:
                rec["live_minutes"] = int((now - rec["import"]).total_seconds() // 60)
            monthly.append(rec)
        cur = next((m for m in monthly if m["month"] == cur_month), None)
        table = [m for m in monthly if m["month"] != first_month and m["import"] is not None]
        done = [m for m in monthly if m["minutes"] is not None and m["month"] != first_month]
        last_done = done[0] if done else None
        months = sorted({s["month"] for s in steps if s["month"]}, reverse=True)
        sel = month if month in months else (cur_month if cur_month in months else (months[0] if months else None))
        rows = []
        for s in steps:
            if s["month"] != sel:
                continue
            mins = None
            if s["started_at"] and s["ended_at"]:
                mins = max(0, int((datetime.fromisoformat(s["ended_at"]) - datetime.fromisoformat(s["started_at"]))
                                  .total_seconds() // 60))
            badge_text, rest = _step_result(s, conn, cid)
            name, sub = STEP_LABEL.get(s["step"], (s["step"], ""))
            rows.append({**s, "name": name, "sub": sub, "mins": mins, "badge": badge_text, "rest": rest})
    days = sorted({(r["started_at"] or "")[:10] for r in rows})
    total_mins = sum(r["mins"] or 0 for r in rows)
    sel_rec = next((m for m in monthly if m["month"] == sel), None)
    return C.render(request, "pages/F14-01.html", "PAGE-F14-01", {
        "first": first, "first_month": first_month, "cur_month": cur_month, "cur": cur, "table": table,
        "done": done, "last_done": last_done, "months": months, "sel": sel, "rows": rows, "days": days,
        "total_mins": total_mins, "sel_rec": sel_rec, "target": runs.MONTHLY_TARGET_MIN,
        "first_target": runs.FIRST_RUN_TARGET_DAYS, "hm": _hm, "now": clock.now(),
        "ok_count": sum(1 for m in done[:5] if m["ok"]), "recent_n": len(done[:5]),
    })

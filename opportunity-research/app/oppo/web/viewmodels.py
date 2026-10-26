"""Page summaries that more than one page (and `oppo status`) read: the workbench state (PAGE-F03-01)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import backtest as BT
from oppo.core import backup as BK
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import health as H
from oppo.core import jobs
from oppo.core import ledger as LG
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import runs
from oppo.core import spu as SPU

STEP_NAMES = ("导入校验", "字段约定", "数据体检", "SPU 归并", "成败与信号", "回测", "判定卡与排序", "记录与导出")
STEP_LINKS = ("/packages", "/fields", "/health", "/spu/merge", "/signals", "/backtest", "/ranking", "/ranking?export=1")
PRIMARY = {1: ("导入数据包", "/packages?import=1", "upload-simple"), 2: ("确认字段约定", "/fields", "list-checks"),
           3: ("查看体检", "/health", "heartbeat"), 4: ("审核合并建议", "/spu/merge", "git-merge"),
           5: ("运行计算", "/signals", "play"), 6: ("运行回测", "/backtest", "flask"),
           7: ("查看本月排序", "/ranking", "list-numbers"), 8: ("导出本月报告", "/ranking?export=1", "export")}
STEP_ICON = {"done": "check", "attention": "warning", "block": "warning-octagon", "stale": "arrows-clockwise",
             "running": "circle-notch"}
STEP_WORD = {"done": "已完成", "current": "当前", "attention": "需处理", "block": "阻断", "todo": "未开始",
             "stale": "需重算", "running": "进行中"}


def _minutes(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    return max(0, int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60))


def _last_step(steps: list[dict[str, Any]], name: str, month: str | None) -> dict[str, Any] | None:
    cand = [s for s in steps if s["step"] == name and (month is None or s["month"] == month)]
    return cand[-1] if cand else None


def _dur_text(s: dict[str, Any] | None) -> str:
    if not s:
        return ""
    m = _minutes(s["started_at"], s["ended_at"])
    if m is None:
        return ""
    return f" · {m} 分钟" if m >= 1 else " · 不到 1 分钟"


def todo_items(conn: Connection, cid: int, mode: str) -> list[dict[str, Any]]:
    """待处理, in severity order: block → stale → health → fields → merges → reconciliation → backup."""
    out: list[dict[str, Any]] = []
    for kind in ("history", "cross"):
        pkg = PK.current_package(conn, cid, kind)
        if pkg and pkg["conclusion"] == "block":
            n = sum(1 for v in PK.validation(conn, pkg["id"]) if v["result"] == "block")
            out.append({"kind": "block", "icon": "warning-octagon", "tone": "danger",
                        "title": f"数据包 {pkg['label']} 有 {n or 1} 个阻断项，不能计算",
                        "desc": "阻断项修正后重新导入；阻断的包不会进入计算。",
                        "href": f"/packages/{pkg['id']}/report", "action": "看校验报告"})
    stale = []
    for m in ("history", "cross"):
        for r in CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, m)):
            if r not in stale:
                stale.append(r)
    if stale:
        out.append({"kind": "stale", "icon": "arrows-clockwise", "tone": "warn", "title": "结果需重算：" + "；".join(stale),
                    "desc": "受影响：成败判定、信号、回测、排序。点“全部重算”生成新的排序快照。",
                    "href": None, "action": "全部重算", "job": "/jobs/recompute"})
    for w in H.open_warnings(conn, cid):
        val = w["value"]
        th = w["threshold"]
        if w["item"] in H.PCT_ITEMS:
            vt, tt = f"{val * 100:.1f}%", f"{float(th):g}%"
        else:
            vt, tt = f"{val:g}", f"{float(th):g}"
        n = w["denominator"]
        out.append({"kind": "health", "icon": "warning", "tone": "warn",
                    "title": f"{w['label']} {vt}", "n": int(n) if n else None,
                    "pop": {"分子": w["numerator"], "分母": w["denominator"], "数据包": w["package_id"]},
                    "desc": f"超过预警阈值 {tt}，尚未标为“已知晓”。", "href": "/health", "action": "去体检"})
    pend = [it for it in CT.draft_items(conn, cid) if it["status"] != "confirmed"]
    if pend:
        names = "、".join(f"{it['field']}（{it['file_code']}）" for it in pend[:4]) + ("等" if len(pend) > 4 else "")
        out.append({"kind": "fields", "icon": "list-checks", "tone": "warn",
                    "title": f"{len(pend)} 个字段未确认：{names}",
                    "desc": "未确认的字段不参与任何计算，本月结果已排除它们。", "href": "/fields", "action": "去确认"})
    sugg = SPU.suggestions(conn, cid, "pending")
    if sugg:
        kids = sum(int(s.get("child_count") or 0) for s in sugg)
        out.append({"kind": "merges", "icon": "git-merge", "tone": "warn", "title": f"{len(sugg)} 条 SPU 合并建议待审",
                    "desc": (f"涉及 {kids} 个子 ASIN。" if kids else "") + "确认前，这些子体暂按各自父 ASIN 计为 SPU。",
                    "href": "/spu/merge", "action": "去审核"})
    recs = LG.reconciliations(conn, cid)
    if recs:
        r = recs[0]
        snap = r["snapshot"] or {}
        rate = r["top_hits"] / r["top_n"] if r["top_n"] else None
        avg = r["all_hits"] / r["all_n"] if r["all_n"] else None
        if r["mode"] == "cross":
            title = f"{r['batch']} 截面快照已到期对账，仅作参考：前 20% 细分实际 {_pct(rate)}（{r['top_hits']}/{r['top_n']}）"
        else:
            title = (f"{r['batch']} 快照已完成对账：前 20% 细分实际命中率 {_pct(rate)}（{r['top_hits']}/{r['top_n']}），"
                     f"倍数 {_mult(r['multiple'])}")
        ups = [x for x in r["rules"] if x["result"] == "升为已验证"]
        desc = f"全类目 {_pct(avg)}（{r['all_hits']}/{r['all_n']}）"
        if r["exp_lo"] is not None:
            desc += f"，回测预期区间 {r['exp_lo'] * 100:.0f}–{r['exp_hi'] * 100:.0f}%，{r['within'] or ''}"
        desc += "。" + ("；".join(f"规则 {x['code']} 已升为“已验证”" for x in ups) + "。" if ups else "")
        out.append({"kind": "recon", "icon": "seal-check", "tone": "ok", "title": title, "desc": desc,
                    "n": r["top_n"], "href": f"/ledger/reconcile/{r['id']}", "action": "看对账"})
    last = BK.last_attempt(conn)
    if last and last["status"] == "failed":
        ok = BK.last_success(conn)
        out.append({"kind": "backup", "icon": "warning-octagon", "tone": "danger", "title": "自动备份失败：" + (last["error"] or ""),
                    "desc": "上次成功备份：" + ((ok["created_at"] or "")[:16] if ok else "还没有成功的备份") +
                    "。导出文件本身不受影响。", "href": "/settings/backup", "action": "去处理"})
    return out


def _pct(v: Any) -> str:
    return "无数据" if v is None else f"{v * 100:.1f}%"


def _mult(v: Any) -> str:
    return "无数据" if v is None else f"{v:.2f}×"


def workbench_summary(conn: Connection, app: Any, mode: str = "history") -> dict[str, Any]:
    cid = CAT.current_category_id(conn)
    cfg_ver = CAT.current_version(conn, cid)
    cfg = cfg_ver["config"]
    pkg = PK.current_package(conn, cid, mode)
    other = PK.current_package(conn, cid, "cross" if mode == "history" else "history")
    any_pkg = pkg or other
    month = PK.add_months(pkg["months_to"], 1) if pkg and pkg.get("months_to") else None
    steps_rec = runs.steps(conn, cid)
    cv = CT.current_version(conn, cid)
    pending_fields = CT.pending_count(conn, cid)
    warns = H.open_warnings(conn, cid)
    sugg = SPU.suggestions(conn, cid, "pending")
    run_ = CMP.latest_run(conn, cid, mode)
    stale = CMP.stale_reasons(conn, cid, run_)
    bt = BT.latest(conn, cid, mode)
    card = CARD.current_card(conn, cid, mode)
    snap = RK.latest_snapshot(conn, cid, mode)
    job = jobs.running(conn)
    last_job = jobs.latest(conn)
    month_snaps = [s for s in RK.snapshot_rows(conn, cid, mode) if month and s["month"] == month]
    exported = [s for s in month_snaps if s["exported_at"]]

    st: list[dict[str, Any]] = []

    def add(status: str, meta: str) -> None:
        i = len(st)
        st.append({"no": i + 1, "name": STEP_NAMES[i], "href": STEP_LINKS[i], "status": status, "meta": meta})

    # 1 导入校验
    if pkg is None:
        add("todo", "还没有数据包")
    elif pkg["conclusion"] == "block":
        add("block", f"{pkg['label']} 有阻断项")
    else:
        add("done", f"{pkg['label']} · {'有警告' if pkg['conclusion'] == 'warn' else '通过'}"
            + _dur_text(_last_step(steps_rec, "导入校验", month)))
    blocked = pkg is not None and pkg["conclusion"] == "block"
    # 2 字段约定
    if pkg is None:
        add("todo", "导入后确认")
    elif cv is None:
        add("todo", f"{pending_fields} 个字段待确认")
    elif pending_fields:
        add("attention", f"v{cv['version_no']} · {pending_fields} 个未确认")
    else:
        add("done", f"v{cv['version_no']} · 全部已确认")
    # 3 数据体检
    if pkg is None:
        add("todo", "导入后自动体检")
    elif warns:
        add("attention", f"{len(warns)} 项预警待知晓")
    else:
        add("done", "没有未知晓的预警")
    # 4 SPU 归并
    if pkg is None or cv is None:
        add("todo", "确认字段后生成建议")
    elif sugg:
        add("attention", f"{len(sugg)} 条建议待审")
    else:
        add("done", f"已合并 {len(SPU.active_merges(conn, cid))} 组")
    # 5 成败与信号
    if job and job["kind"] in ("compute", "recompute"):
        p = jobs.progress(job["id"]).get("progress") or 0
        add("running", f"进行中 · {round(p * 100)}%")
    elif last_job and last_job["kind"] in ("compute", "recompute") and last_job["status"] == "failed":
        add("block", "上次计算失败：" + (last_job["error"] or "")[:40])
    elif blocked:
        add("block", "数据包有阻断项")
    elif run_ is None:
        add("todo", "待运行")
    elif stale:
        add("stale", "需重算")
    else:
        add("done", f"T={run_['t_month']}" + _dur_text(_last_step(steps_rec, "计算", month)))
    # 6 回测
    if job and job["kind"] == "backtest":
        p = jobs.progress(job["id"]).get("progress") or 0
        add("running", f"进行中 · {round(p * 100)}%")
    elif last_job and last_job["kind"] == "backtest" and last_job["status"] == "failed":
        add("block", "上次回测失败：" + (last_job["error"] or "")[:40])
    elif bt is None:
        add("todo", "待运行")
    elif run_ and bt["compute_run_id"] != run_["id"]:
        add("done", f"沿用判定卡 {card['label']}" if card else "沿用上次回测")
    else:
        mult = (bt["result"].get("test") or {}).get("multiple")
        add("done", f"{bt['conclusion']}" + (f" {mult:.2f}×" if mult is not None else "")
            + _dur_text(_last_step(steps_rec, "回测", month)))
    # 7 判定卡与排序
    if month_snaps:
        add("done", f"快照第 {month_snaps[0]['seq']} 版已保存")
    elif snap:
        add("todo", f"本月未生成（最近 {snap['label']}）")
    else:
        add("todo", "回测后生成")
    # 8 记录与导出
    if exported:
        add("done", f"已导出 · {exported[0]['exported_at'][5:16]}")
    elif month_snaps:
        add("todo", "待导出")
    else:
        add("todo", "排序后导出")

    current = next((s for s in st if s["status"] in ("todo", "block")), None)
    if current:
        if current["status"] == "todo":
            current["status"] = "current"
    primary_no = current["no"] if current else 7
    if exported and not current:
        primary_no = 7
    label, href, ic = PRIMARY[primary_no]

    rk = RK.build_rows(conn, cid, mode) if (card and run_) else None
    top5 = [r for r in (snap["content"]["rows"] if snap else []) if r["effective"]][:5] if snap else []
    top_meta = snap["content"] if snap else None
    summ = runs.summary(conn, cid)
    monthly = next((m for m in summ["monthly"] if m["month"] == month), None)
    now = clock.now()
    month_mins = None
    month_start = None
    if monthly and monthly["import"]:
        month_start = monthly["import"]
        end = monthly["export"] if monthly["export"] and monthly["export"] >= monthly["import"] else now
        month_mins = int((end - monthly["import"]).total_seconds() // 60)
    first = summ["first_run"]
    bk_set = BK.setting(conn)
    bk_ok = BK.last_success(conn)
    bk_last = BK.last_attempt(conn)
    eff = CARD.effective(conn, cid)
    return {
        "month": month, "data_to": pkg["months_to"] if pkg else None, "mode": mode, "has_package": any_pkg is not None,
        "package": pkg, "steps": st, "primary": {"label": label, "href": href, "icon": ic, "step": primary_no},
        "todo": todo_items(conn, cid, mode), "stale": stale, "blocked": blocked,
        "card": card, "card_status": card["status"] if card else None, "card_effective": eff,
        "card_banner": CARD.banner(card["status"]) if card else None,
        "snapshot": snap, "top5": top5, "top_meta": top_meta, "ranking_rows": len(rk["rows"]) if rk else 0,
        "timing": {"month_minutes": month_mins, "month_start": month_start, "target": runs.MONTHLY_TARGET_MIN,
                   "first": first, "first_target": runs.FIRST_RUN_TARGET_DAYS,
                   "exported": bool(monthly and monthly["export"])},
        "backup": {"setting": bk_set, "last_success": bk_ok, "last": bk_last},
        "config": cfg, "config_version": cfg_ver["version_no"], "contract_version": cv["version_no"] if cv else None,
        "reference": RK.reference_text(cfg), "job": job,
        "can_recompute": bool(stale) and job is None and not blocked,
    }


def footer(conn: Connection, cid: int, mode: str) -> str:
    pkg = PK.current_package(conn, cid, mode)
    cv = CT.current_version(conn, cid)
    cfg = CAT.current_version(conn, cid)
    card = CARD.current_card(conn, cid, mode)
    snap = RK.latest_snapshot(conn, cid, mode)
    parts = [f"数据包 {pkg['label']}" if pkg else "数据包 —", f"字段约定 v{cv['version_no']}" if cv else "字段约定 —",
             f"品类配置 v{cfg['version_no']}", f"判定卡 {card['label']}" if card else "判定卡 —"]
    if snap:
        parts.append(f"快照 {snap['month']} 第 {snap['seq']} 版")
    return " · ".join(parts)


def latest_export(conn: Connection, cid: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.export_record).where(D.export_record.c.category_id == cid)
                       .order_by(D.export_record.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None

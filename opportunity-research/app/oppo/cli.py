"""Command line `oppo` (API table in 技术方案 §4.3). Every command calls the same service functions as
the web pages (NFR-004)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from oppo import service as SV


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_import(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core.packages import ImportRejected

    try:
        r = SV.import_package(app, Path(a.path))
    except ImportRejected as exc:
        print(f"该数据包已导入：{exc.label}")
        return 3
    print(f"{r.label} · {'历史' if r.kind == 'history' else ('截面' if r.kind == 'cross' else '未知类型')} · "
          f"{ {'pass': '通过', 'warn': '有警告', 'block': '阻断'}[r.conclusion] }")
    return 2 if r.conclusion == "block" else 0


def cmd_report(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import packages as PK

    with app.engine.begin() as conn:
        pkg = PK.by_label(conn, a.version)
        if not pkg:
            print("数据包不存在")
            return 1
        for it in PK.validation(conn, pkg["id"]):
            if it["result"] in ("warn", "block"):
                print(f"[{it['result']}] {it['file_code'] or '-'} {it['field'] or ''} {it['check_name']}: "
                      f"{it['message'] or ''} 示例行号 {it['sample_rows'][:5]}")
        print(f"结论：{pkg['conclusion']}")
    return 0


def cmd_contract(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import contract as CT

    cid = app.category_id()
    if a.action == "show":
        with app.engine.begin() as conn:
            for it in CT.draft_items(conn, cid):
                print(f"{it['file_code']}\t{it['field']}\t{it['usage']}\t{it['status']}\t{it['source'] or ''}"
                      f"\t{it['change_kind'] or ''}")
        return 0
    keys = None
    if a.fields:
        keys = [tuple(f.split(":", 1)) for f in a.fields]  # type: ignore[misc]
    if a.exclude:
        with app.engine.begin() as conn:
            allk = [(i["file_code"], i["field"]) for i in CT.draft_items(conn, cid) if i["status"] != "confirmed"]
        ex = {tuple(f.split(":", 1)) for f in a.exclude}
        keys = [k for k in allk if k not in ex]
    res = SV.contract_confirm(app, keys, suggested_only=a.only_direct, save=not a.no_save)
    print(f"已确认 {res['confirmed']} 个字段" + (f"，保存为字段约定 v{res['version']}" if res["version"] else ""))
    return 0


def cmd_health(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import health as H
    from oppo.core import packages as PK

    cid = app.category_id()
    with app.engine.begin() as conn:
        pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
        if a.ack:
            H.acknowledge(conn, cid, pkg["id"], a.ack, a.note or "", app.operator)
            print(f"{a.ack} 已标为已知晓")
            return 0
        for r in H.results(conn, cid, pkg["id"]):
            print(f"{r['label']}: {r['value']} ({r['numerator']}/{r['denominator']}) 阈值 {r['threshold']} → {r['status']}")
    return 0


def cmd_merge(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import spu as SPU

    cid = app.category_id()
    if a.action == "list":
        with app.engine.begin() as conn:
            for s in SPU.suggestions(conn, cid):
                print(f"{s['code']}\t{s['status']}\t{s['basis']}\t{s['brand']}\t{','.join(s['parents'])}")
        return 0
    if a.action == "confirm":
        if a.basis:
            r = SV.merge_confirm_basis(app, a.basis)
        else:
            with app.engine.begin() as conn:
                ids = [s["id"] for s in SPU.suggestions(conn, cid) if s["code"] in (a.ids or [])]
            r = SV.merge_decide(app, ids, "confirm")
        print(f"确认 {r['done']} 条，跳过 {r['skipped']} 条")
        return 0
    if a.action == "reject":
        with app.engine.begin() as conn:
            ids = [s["id"] for s in SPU.suggestions(conn, cid) if s["code"] in (a.ids or [])]
        r = SV.merge_decide(app, ids, "reject")
        print(f"拒绝 {r['done']} 条")
        return 0
    if a.action == "revise":
        with app.engine.begin() as conn:
            new = SPU.revise(conn, cid, a.code, app.operator, a.keep or None, a.note or "")
        print(f"已{'修改为 ' + new if new else '拆分'}")
        return 0
    return 1


def cmd_compute(app: SV.App, a: argparse.Namespace) -> int:
    jid = SV.compute(app)
    print(f"计算完成（任务 {jid}）")
    return 0


def cmd_recompute(app: SV.App, a: argparse.Namespace) -> int:
    SV.recompute(app)
    print("全部重算完成")
    return 0


def cmd_backtest(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import backtest as BT

    SV.backtest(app, a.mode)
    with app.engine.begin() as conn:
        bt = BT.latest(conn, app.category_id(), a.mode)
    print(f"{bt['code']} · {bt['conclusion']}" + (f"（{bt['reason_class']}）" if bt["reason_class"] else ""))
    return 0


def cmd_ranking(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import ranking as RK

    with app.engine.begin() as conn:
        snaps = [s for s in RK.snapshot_rows(conn, app.category_id(), a.mode) if not a.month or s["month"] == a.month]
        if not snaps:
            print("还没有排序")
            return 1
        s = snaps[0]
        print(f"{s['label']} · 判定卡 {s['card_label']} {s['card_status']}")
        for r in s["content"]["rows"]:
            ci = r["ci"]
            print(f"{r['rank']:>3} {r['segment']:<28} 得分 {r['score'] if r['score'] is None else round(r['score'], 2)}"
                  f" 区间 {ci} n={r['sample']} 锦囊 {[t['action'] + ' ' + t['rule'] for t in r['tips']]}")
    return 0


def cmd_export(app: SV.App, a: argparse.Namespace) -> int:
    jid = SV.export(app, a.month, a.mode)
    res = SV.job_result(app, jid)["result"]
    _print(res)
    return 0


def cmd_decision(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import ledger as LG
    from oppo.core import ranking as RK

    cid = app.category_id()
    with app.engine.begin() as conn:
        if a.action == "add":
            snap = RK.latest_snapshot(conn, cid, "history")
            seg_name = a.segment.replace("|", " · ")
            code = LG.record_decision(conn, cid, app.operator, a.decision, a.segment, seg_name, a.reason or "",
                                      snap["id"] if snap else None, a.date, a.name)
        elif a.action == "backfill":
            code = LG.record_backfill(conn, cid, app.operator, a.name or "", a.date or "", a.segment,
                                      a.segment.replace("|", " · "), a.reason or "")
        else:
            code = LG.correct(conn, cid, app.operator, a.code, reason=a.reason or "", decision=a.decision)
    print(code)
    return 0


def cmd_backup_dir(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import backup as BK

    with app.engine.begin() as conn:
        ok, msg = BK.set_directory(conn, a.path, app.operator)
    print(msg)
    return 0 if ok else 1


def cmd_restore(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import backup as BK

    res = BK.restore(app, Path(a.backup), confirm=True)
    _print(res)
    return 0


def cmd_runs(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.core import runs

    with app.engine.begin() as conn:
        _print(runs.summary(conn, app.category_id()))
    return 0


def cmd_status(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.web import viewmodels as VM

    with app.engine.begin() as conn:
        _print(VM.workbench_summary(conn, app))
    return 0


def cmd_serve(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.web import server

    server.serve(app, port=a.port, open_browser=not a.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="oppo", description="品类机会判定台 · 命令行（与网页调用同一套服务函数）")
    p.add_argument("--data-dir", help="数据目录（默认取 OPPO_DATA_DIR 或安装目录下的 data）")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import", help="导入数据包（zip 或文件夹）并校验")
    s.add_argument("path")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("report", help="查看校验报告")
    s.add_argument("version")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("contract", help="字段约定：show / confirm")
    s.add_argument("action", choices=["show", "confirm"])
    s.add_argument("--suggested", action="store_true", help="按建议批量确认（默认全部待确认字段）")
    s.add_argument("--only-direct", action="store_true", help="只确认建议用法为“直接用”的字段")
    s.add_argument("--fields", nargs="*", help="只确认这些字段，格式 C1:字段名")
    s.add_argument("--exclude", nargs="*", help="除这些字段外全部确认，格式 C1:字段名")
    s.add_argument("--no-save", action="store_true", help="只改草稿，不保存新版本")
    s.set_defaults(fn=cmd_contract)
    s = sub.add_parser("health", help="体检结果；--ack 项 --note 说明 标为已知晓")
    s.add_argument("--ack")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_health)
    s = sub.add_parser("merge", help="SPU 合并建议：list / confirm / reject / revise")
    s.add_argument("action", choices=["list", "confirm", "reject", "revise"])
    s.add_argument("--basis")
    s.add_argument("--ids", nargs="*")
    s.add_argument("--code")
    s.add_argument("--keep", nargs="*")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_merge)
    s = sub.add_parser("compute", help="运行计算（成败判定 + 信号）")
    s.set_defaults(fn=cmd_compute)
    s = sub.add_parser("recompute", help="全部重算")
    s.set_defaults(fn=cmd_recompute)
    s = sub.add_parser("backtest", help="运行回测")
    s.add_argument("--mode", choices=["history", "cross"], default="history")
    s.set_defaults(fn=cmd_backtest)
    s = sub.add_parser("ranking", help="查看排序")
    s.add_argument("--month")
    s.add_argument("--mode", choices=["history", "cross"], default="history")
    s.set_defaults(fn=cmd_ranking)
    s = sub.add_parser("export", help="导出当月 Excel 与网页报告，随后自动备份")
    s.add_argument("--month")
    s.add_argument("--mode", choices=["history", "cross"], default="history")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("decision", help="立项记录：add / backfill / correct")
    s.add_argument("action", choices=["add", "backfill", "correct"])
    s.add_argument("--decision", choices=["立项", "不立项"])
    s.add_argument("--segment", default="")
    s.add_argument("--reason")
    s.add_argument("--date")
    s.add_argument("--name")
    s.add_argument("--code")
    s.set_defaults(fn=cmd_decision)
    s = sub.add_parser("backup-dir", help="设置备份目录")
    s.add_argument("path")
    s.set_defaults(fn=cmd_backup_dir)
    s = sub.add_parser("restore", help="从备份恢复")
    s.add_argument("backup")
    s.set_defaults(fn=cmd_restore)
    s = sub.add_parser("runs", help="运行记录与用时")
    s.set_defaults(fn=cmd_runs)
    s = sub.add_parser("status", help="工作台汇总")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("serve", help="启动本机网页服务（只监听 127.0.0.1）")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    import os

    if a.data_dir:
        os.environ["OPPO_DATA_DIR"] = a.data_dir
    app = SV.open_app()
    try:
        return int(a.fn(app, a) or 0)
    except Exception as exc:  # noqa: BLE001 - user-facing message, non-zero exit
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

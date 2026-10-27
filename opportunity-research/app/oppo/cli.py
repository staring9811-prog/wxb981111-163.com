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


def cmd_adjust(app: SV.App, a: argparse.Namespace) -> int:
    """数据审核：list / propose / confirm / reject / revoke。propose 读 JSON 文件（items 数组或 {source, items}）。"""
    from oppo.core import adjust as ADJ

    cid = app.category_id()
    if a.action == "list":
        pid = SV.resolve_package(app, a.package)["id"] if a.package else None
        with app.engine.begin() as conn:
            rows = ADJ.listing(conn, cid, package_id=pid, status=a.status or None, batch=a.batch or None)
        for r in rows:
            month = f"\t{r['month']}" if r["month"] else ""
            print(f"{r['code']}\t{r['status']}\t{r['file_code']}\t{r['child']}{month}\t{r['field']}\t"
                  f"{r['old_value'] if r['old_value'] is not None else '空'} → "
                  f"{r['final_value'] if r['status'] == ADJ.CONFIRMED else r['proposed_value']}\t{r['source']}")
        return 0
    if a.action == "propose":
        if not a.file:
            raise ADJ.AdjustError("请用 --file 指定 JSON 文件")
        body = json.loads(Path(a.file).read_text(encoding="utf-8"))
        items = body.get("items") if isinstance(body, dict) else body
        source = (body.get("source") if isinstance(body, dict) else None) or a.source or "手工"
        pkg = SV.resolve_package(app, a.package)
        _print(SV.adjust_propose(app, pkg["id"], items or [], source))
        return 0
    codes = list(a.codes or [])
    if a.action in ("confirm", "reject") and a.all_pending:
        pid = SV.resolve_package(app, a.package)["id"] if a.package else None
        with app.engine.begin() as conn:
            codes = [r["code"] for r in ADJ.listing(conn, cid, package_id=pid, status=ADJ.PENDING,
                                                     batch=a.batch or None)]
    if not codes:
        raise ADJ.AdjustError("请用 --codes 指定调整编号，或用 --all-pending")
    if a.action in ("confirm", "reject"):
        values = {codes[0]: a.value} if a.value is not None and len(codes) == 1 else None
        r = SV.adjust_decide(app, codes, a.action, values=values, note=a.note or "")
        print(f"{'确认' if a.action == 'confirm' else '驳回'} {len(r['done'])} 条，跳过 {len(r['skipped'])} 条")
        return 0
    if a.action == "revoke":
        r = SV.adjust_revoke(app, codes, note=a.note or "")
        print(f"撤销 {len(r['done'])} 条，跳过 {len(r['skipped'])} 条")
        return 0
    return 1


def cmd_api_token(app: SV.App, a: argparse.Namespace) -> int:
    print(app.settings.api_token())
    print(f"（保存在 {app.settings.api_token_path}；接口地址 http://127.0.0.1:{app.settings.port}/api/v1）",
          file=sys.stderr)
    return 0


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


def cmd_update(app: SV.App, a: argparse.Namespace) -> int:
    from oppo import update as UP

    res = UP.run(app.settings, url=a.url, zip_path=Path(a.zip) if a.zip else None, branch=a.branch or UP.BRANCH,
                 reinstall=True if a.reinstall else None)
    if res["changed"]:
        print(f"已更新 {len(res['changed'])} 个文件；旧文件备份在 {res['backup']}"
              + ("；依赖已重新安装" if res["reinstalled"] else ""))
        print("重新启动程序即可使用新版本（数据库会在启动时自动升级）。")
    return 0


def cmd_serve(app: SV.App, a: argparse.Namespace) -> int:
    from oppo.web import server

    return server.serve(app, port=a.port, open_browser=not a.no_browser)


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
    s = sub.add_parser("adjust", help="数据审核：list / propose / confirm / reject / revoke（数据包本身不变）")
    s.add_argument("action", choices=["list", "propose", "confirm", "reject", "revoke"])
    s.add_argument("--package", help="数据包编号，如 P-0001（默认当前数据包）")
    s.add_argument("--status", help="list 时按状态筛选：待审核 / 已确认 / 已驳回 / 已撤回 / 已撤销")
    s.add_argument("--batch", help="批次，如 B-0001")
    s.add_argument("--codes", nargs="*", help="调整编号，如 A-00001")
    s.add_argument("--all-pending", action="store_true", help="confirm / reject 全部待审核（可配合 --package、--batch）")
    s.add_argument("--value", help="confirm 单条时改成这个值再确认")
    s.add_argument("--file", help="propose 读取的 JSON 文件")
    s.add_argument("--source", help="propose 的来源名称（默认 手工）")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_adjust)
    s = sub.add_parser("api-token", help="显示本机接口（/api/v1）的令牌，给 Codex 等工具用")
    s.set_defaults(fn=cmd_api_token)
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
    s = sub.add_parser("update", help="从 GitHub 下载最新程序文件并替换（data 与 .venv 不动，旧文件先备份）")
    s.add_argument("--url", help="zip 下载地址（默认取仓库分支的 zip）")
    s.add_argument("--zip", help="已下载好的 zip 文件路径，不再联网下载")
    s.add_argument("--branch", help="分支名（默认交付分支）")
    s.add_argument("--reinstall", action="store_true", help="强制重新安装依赖")
    s.set_defaults(fn=cmd_update)
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

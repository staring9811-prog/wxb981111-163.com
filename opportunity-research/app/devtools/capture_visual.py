"""Capture the real running pages for the visual acceptance (DESIGN-01..26) into output/tests/visual/.

    python -m devtools.capture_visual <states_dir> [DESIGN-xx ...]

Every shot is a screenshot of the real app served on 127.0.0.1 from a copy of a prepared data state
(devtools/visual_states.py). A JSON manifest records, per shot, the URL, the state, the viewport, console errors and
whether the page scrolls horizontally.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn
from playwright.sync_api import Page, sync_playwright

from devtools.visual_states import FIX, clone, close, open_dir

APP = Path(__file__).resolve().parents[1]
OUT = APP.parent / "output" / "tests" / "visual"
TOKEN = "visual"


class Server:
    def __init__(self, data_dir: Path):
        from oppo.web.app import create_app

        self.app = open_dir(data_dir)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(create_app(self.app, token=TOKEN), host="127.0.0.1",
                                                    port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.05)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)
        close(self.app)


Action = Callable[[Page, Server], None]


def wait_idle(page: Page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def click(sel: str) -> Action:
    def act(p: Page, _s: Server) -> None:
        p.locator(sel).first.click()
        p.wait_for_timeout(450)
    return act


def press(key: str) -> Action:
    def act(p: Page, _s: Server) -> None:
        p.keyboard.press(key)
        p.wait_for_timeout(450)
    return act


def fill(sel: str, value: str) -> Action:
    def act(p: Page, _s: Server) -> None:
        p.locator(sel).first.fill(value)
        p.locator(sel).first.dispatch_event("input")
        p.locator(sel).first.dispatch_event("change")
        p.wait_for_timeout(600)
    return act


def go(path: str) -> Action:
    def act(p: Page, s: Server) -> None:
        p.goto(s.url(path))
        wait_idle(p)
    return act


def run_js(js: str) -> Action:
    def act(p: Page, _s: Server) -> None:
        p.evaluate(js)
        p.wait_for_timeout(400)
    return act


def stage_zip(zip_path: Path) -> Action:
    def act(p: Page, _s: Server) -> None:
        p.locator("input[data-stage-zip]").set_input_files(str(zip_path))
        p.wait_for_selector("#import-form", timeout=60_000)
        wait_idle(p)
    return act


class Shot:
    def __init__(self, design: str, name: str, state: str, path: str, actions: list[Action] | None = None,
                 width: int = 1440, height: int = 900, full: bool = True, mode: str | None = None):
        self.design, self.name, self.state, self.path = design, name, state, path
        self.actions = actions or []
        self.width, self.height, self.full, self.mode = width, height, full, mode

    @property
    def file(self) -> str:
        return f"{self.design}_{self.name}.png"


def zips(tmp: Path) -> dict[str, Path]:
    out = {}
    for name in ("H1-A", "H1-B"):
        z = tmp / f"{name}.zip"
        if not z.exists():
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted((FIX / name).iterdir()):
                    zf.write(f, f"{name}/{f.name}")
        out[name] = z
    return out


def shots(tmp: Path) -> list[Shot]:
    z = zips(tmp)
    X = "30–48″|落地式|$500–900"
    return [
        # PAGE-F03-01 本月工作台
        Shot("DESIGN-01", "1_workbench", "s1", "/"),
        Shot("DESIGN-01", "2_workbench_1366", "s1", "/", width=1366, height=768),
        Shot("DESIGN-01", "3_workbench_1920", "s1", "/", width=1920, height=1080),
        Shot("DESIGN-01", "4_workbench_unverified", "s_unverified", "/", full=False),
        # PAGE-F01-01 数据包
        Shot("DESIGN-02", "1_packages_zip_selected", "s1", "/packages", [stage_zip(z["H1-B"])]),
        Shot("DESIGN-02", "2_packages_duplicate", "s1", "/packages", [stage_zip(z["H1-A"])]),
        # PAGE-F01-02 校验报告
        Shot("DESIGN-03", "1_report_warn", "s1", "/packages/1/report"),
        Shot("DESIGN-03", "2_report_block", "s_block", "/packages/1/report"),
        # PAGE-F02-01 字段约定
        Shot("DESIGN-04", "1_fields", "s1", "/fields"),
        Shot("DESIGN-04", "2_batch_modal", "s1", "/fields",
             [click('[data-select-all="#field-table"]'), click('button[data-open="#batch-modal"]')], full=False),
        Shot("DESIGN-04", "3_save_modal", "s1", "/fields", [click('button[data-open="#save-modal"]')], full=False),
        Shot("DESIGN-04", "4_history_drawer", "s1", "/fields", [click('button[data-open="#history-drawer"]')],
             full=False),
        # PAGE-F03-02 数据体检
        Shot("DESIGN-05", "1_health_sample_open", "s1", "/health",
             [run_js("document.querySelectorAll('li[data-check=first_review_early] details').forEach(d => d.open = true)")]),
        Shot("DESIGN-05", "2_ack_modal", "s1", "/health", [click('button[data-open^="#ack-modal-"]')], full=False),
        # PAGE-F04-01 新品与 SPU
        Shot("DESIGN-06", "1_spu_history", "s1x", "/spu", mode="history"),
        Shot("DESIGN-06", "2_spu_cross", "s1x", "/spu", mode="cross"),
        # PAGE-F04-02 合并建议
        Shot("DESIGN-07", "1_merge_expanded", "s1", "/spu/merge",
             [run_js("document.querySelector('#pending-table details') && (document.querySelector('#pending-table details').open = true)")]),
        Shot("DESIGN-07", "2_batch_modal", "s1", "/spu/merge",
             [click('[data-select-all="#pending-table"]'), click('#panel-pending button[data-open="#batch-modal"]')],
             full=False),
        Shot("DESIGN-07", "3_edit_modal", "s1", "/spu/merge?tab=active", [click('button[data-open="#edit-modal"]')],
             full=False),
        Shot("DESIGN-07", "4_split_modal", "s1", "/spu/merge?tab=active", [click('button[data-open="#split-modal"]')],
             full=False),
        # PAGE-F05-01 SPU 成败明细
        Shot("DESIGN-08", "1_spu_hit", "s1", "/spu/B0C3HX7Y2L"),
        Shot("DESIGN-08", "2_spu_cross_miss", "s1x", "/spu/@Q", mode="cross"),
        # PAGE-F06-01 信号
        Shot("DESIGN-09", "1_signals_history", "s1x", "/signals?month=2026-03", mode="history"),
        Shot("DESIGN-09", "2_signals_cross", "s1x", "/signals", mode="cross"),
        Shot("DESIGN-09", "3_signals_history_all_columns", "s1x", "/signals?month=2026-03",
             [click('[data-cols-toggle="#sig-wrap"]')], mode="history"),
        Shot("DESIGN-09", "4_signals_cross_all_columns", "s1x", "/signals", [click('[data-cols-toggle="#sig-wrap"]')],
             mode="cross"),
        # PAGE-F06-02 细分详情抽屉
        Shot("DESIGN-10", "1_segment_drawer", "s1", "/signals?month=2026-03",
             [click(f'tr[data-segment="{X}"], tr:has-text("30–48″"):has-text("落地式"):has-text("$500–900")')], full=False),
        Shot("DESIGN-10", "3_drawer_middle", "s1", "/signals?month=2026-03",
             [click(f'tr[data-segment="{X}"]'),
              run_js("(b => b.scrollTop = b.scrollHeight / 3)(document.querySelector('.drawer.is-open .drawer__body'))")],
             full=False),
        Shot("DESIGN-10", "4_drawer_bottom", "s1", "/signals?month=2026-03",
             [click(f'tr[data-segment="{X}"]'),
              run_js("(b => b.scrollTop = b.scrollHeight)(document.querySelector('.drawer.is-open .drawer__body'))")],
             full=False),
        Shot("DESIGN-10", "2_after_esc", "s1", "/signals?month=2026-03",
             [click(f'tr[data-segment="{X}"], tr:has-text("30–48″"):has-text("落地式"):has-text("$500–900")'),
              press("Escape")], full=False),
        # PAGE-F07-01 回测
        Shot("DESIGN-11", "1_backtest_history", "s1x", "/backtest", mode="history"),
        Shot("DESIGN-11", "2_backtest_cross", "s1x", "/backtest", mode="cross"),
        # PAGE-F08-01 判定卡
        Shot("DESIGN-12", "1_card_pass", "s1", "/card"),
        Shot("DESIGN-12", "2_card_unverified", "s_unverified", "/card", full=False),
        Shot("DESIGN-12", "3_card_cross_only", "s_cross_only", "/card", full=False),
        # PAGE-F08-02 立项锦囊
        Shot("DESIGN-13", "1_kits_all", "s1", "/kits"),
        Shot("DESIGN-13", "2_kits_candidate", "s1", "/kits", [click('[role="tab"]:has-text("立项候选")')]),
        Shot("DESIGN-13", "3_kits_watch", "s1", "/kits", [click('[role="tab"]:has-text("观察")')]),
        Shot("DESIGN-13", "4_kits_drop", "s1", "/kits", [click('[role="tab"]:has-text("放弃")')]),
        # PAGE-F09-01 本月排序
        Shot("DESIGN-14", "1_ranking", "s1", "/ranking"),
        # PAGE-F10-01 台账 · 月度快照
        Shot("DESIGN-15", "1_snapshots", "s_ledger", "/ledger/snapshots"),
        Shot("DESIGN-15", "2_snapshot_drawer_reconciled", "s_ledger", "/ledger/snapshots?snap=2", full=False),
        # PAGE-F10-02 记录立项决定（弹窗）
        Shot("DESIGN-16", "1_decision_modal", "s1", "/ranking",
             [click('tbody tr:first-child button[data-open="#decision-modal"]')], full=False),
        Shot("DESIGN-16", "2_backfill_tab", "s1", "/ranking",
             [click('tbody tr:first-child button[data-open="#decision-modal"]'), click('#tab-backfill')], full=False),
        # PAGE-F10-03 备份与恢复
        Shot("DESIGN-17", "1_backup_page", "s_ledger", "/settings/backup"),
        Shot("DESIGN-17", "2_restore_confirm", "s_ledger", "/settings/backup",
             [click('tr[data-backup]:last-child button[data-open^="#restore-modal-"]')], full=False),
        Shot("DESIGN-17", "3_restored", "s_ledger", "/settings/backup",
             [click('tr[data-backup]:last-child button[data-open^="#restore-modal-"]'),
              click('.modal.is-open [data-restore-confirm]'),
              lambda p, s: p.wait_for_selector("#restore-done", timeout=120_000), lambda p, s: wait_idle(p)]),
        # PAGE-F10-04 台账 · 立项记录
        Shot("DESIGN-18", "1_decisions", "s_ledger", "/ledger/decisions"),
        # PAGE-F10-05 台账 · 到期对账
        Shot("DESIGN-19", "1_reconcile", "s_ledger", "/ledger/reconcile"),
        # PAGE-F10-06 录入自家上架数据（弹窗）
        Shot("DESIGN-20", "1_launch_modal_jia", "s_ledger", "/ledger/decisions?launch=D-0001", full=False),
        # PAGE-F11-01 策略库
        Shot("DESIGN-21", "0_rules", "s_ledger", "/rules"),
        Shot("DESIGN-21", "1_rules_basis_popover", "s_ledger", "/rules",
             [click('tr:has-text("已验证") button.etag')]),
        # PAGE-F11-02 规则编辑（抽屉）
        Shot("DESIGN-22", "1_rule_edit_threshold", "s_ledger", "/rules?rule=R-003",
             [fill('#rule-drawer input[name="cond_value"], .drawer.is-open input[name="cond_value"]', "-5%")], full=False),
        # PAGE-F12-01 导出报告弹窗
        Shot("DESIGN-23", "1_export_confirm", "s1", "/ranking?export=1", full=False),
        Shot("DESIGN-23", "2_export_running", "s1", "/ranking?export=1",
             [click("[data-export-start]")], full=False),
        Shot("DESIGN-23", "3_export_result", "s1", "/ranking?export=1",
             [click("[data-export-start]"), lambda p, s: p.wait_for_selector('[data-file="html"]', timeout=180_000),
              lambda p, s: p.wait_for_timeout(800)], full=False),
        Shot("DESIGN-23", "4_export_confirm_unverified", "s_unverified", "/ranking?export=1", full=False),
        # PAGE-F13-01 品类配置
        Shot("DESIGN-25", "0_config_edited_page", "s1", "/settings/category",
             [fill("input[name='bins.price']", "<$450 / $450–900 / ≥$900")]),
        Shot("DESIGN-25", "1_config_edited_save_modal", "s1", "/settings/category",
             [fill("input[name='bins.price']", "<$450 / $450–900 / ≥$900"), click("[data-cfg-review]")], full=False),
        Shot("DESIGN-25", "2_new_category_modal", "s1", "/settings/category",
             [click('button[data-open="#new-cat-modal"]')], full=False),
        # PAGE-F14-01 运行记录
        Shot("DESIGN-26", "1_runs", "s_timing", "/settings/runs"),
    ]


def resolve_path(path: str, srv: Server) -> str:
    """'/spu/@Q' → the cross SPU detail of the FLOW-06 sample Q (looked up from the fixture builder)."""
    if path == "/spu/@Q":
        from fixtures.build_samples import X1

        spec = X1()
        spec.assemble("X1")
        return "/spu/" + spec.special["Q"][0].asin
    return path


def capture(states: Path, only: list[str]) -> list[dict[str, Any]]:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = states.parent / "capture_tmp"
    tmp.mkdir(exist_ok=True)
    todo = [s for s in shots(tmp) if not only or s.design in only]
    results = []
    with sync_playwright() as pw:
        exe = Path("/opt/pw-browsers/chromium")
        browser = pw.chromium.launch(executable_path=str(exe) if exe.exists() else None)
        for i, sh in enumerate(todo):
            d = clone(states / sh.state, tmp / f"run_{i}")
            srv = Server(d)
            ctx = browser.new_context(viewport={"width": sh.width, "height": sh.height}, locale="zh-CN")
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            try:
                if sh.mode:
                    page.goto(srv.url(f"/mode/{sh.mode}?next=/"))
                page.goto(srv.url(resolve_path(sh.path, srv)))
                wait_idle(page)
                for act in sh.actions:
                    act(page, srv)
                hscroll = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                page.screenshot(path=str(OUT / sh.file), full_page=sh.full)
                results.append({"design": sh.design, "file": f"tests/visual/{sh.file}", "state": sh.state,
                                "url": page.url.replace(srv.url(""), ""), "viewport": [sh.width, sh.height],
                                "console_errors": errors, "horizontal_scroll": hscroll, "ok": True})
                print("ok  ", sh.file, flush=True)
            except Exception as exc:  # noqa: BLE001 - recorded; the shot is retried after a fix
                results.append({"design": sh.design, "file": sh.file, "state": sh.state, "ok": False,
                                "error": repr(exc)[:500]})
                print("FAIL", sh.file, repr(exc)[:300], flush=True)
            finally:
                ctx.close()
                srv.stop()
        browser.close()
    return results


def capture_reports(states: Path) -> list[dict[str, Any]]:
    """DESIGN-24: the exported single-file report, copied to another folder and opened with the network off."""
    import shutil
    import sqlite3

    tmp = states.parent / "capture_tmp" / "report_copy"
    tmp.mkdir(parents=True, exist_ok=True)
    out = []
    plan = [("s1", "1_report_all_sections_open", True), ("s1", "2_report_first_screen", False),
            ("s_unverified", "3_report_unverified_first_screen", False)]
    with sync_playwright() as pw:
        exe = Path("/opt/pw-browsers/chromium")
        browser = pw.chromium.launch(executable_path=str(exe) if exe.exists() else None)
        for state, name, expand in plan:
            db = sqlite3.connect(f"file:{states / state / 'oppo.sqlite3'}?mode=ro", uri=True)
            html = db.execute("SELECT html_path FROM export_record ORDER BY id DESC").fetchone()[0]
            db.close()
            copy = tmp / f"{state}_{Path(html).name}"
            shutil.copy2(html, copy)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN", offline=True)
            page = ctx.new_page()
            requests: list[str] = []
            errors: list[str] = []
            page.on("request", lambda r, requests=requests: requests.append(r.url))
            page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            page.goto(copy.as_uri())
            page.wait_for_timeout(600)
            if expand:
                page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                page.wait_for_timeout(300)
            file = f"DESIGN-24_{name}.png"
            page.screenshot(path=str(OUT / file), full_page=expand)
            out.append({"design": "DESIGN-24", "file": f"tests/visual/{file}", "state": state, "url": copy.name,
                        "offline": True, "requests": [u for u in requests if not u.startswith("file:")],
                        "console_errors": errors, "ok": True})
            print("ok  ", file, flush=True)
            ctx.close()
        browser.close()
    return out


def main() -> None:
    states = Path(sys.argv[1])
    only = sys.argv[2:]
    res = capture(states, [o for o in only if o != "DESIGN-24"]) if (not only or set(only) - {"DESIGN-24"}) else []
    if not only or "DESIGN-24" in only:
        res += capture_reports(states)
    man = OUT / "manifest.json"
    old = json.loads(man.read_text(encoding="utf-8")) if man.exists() else []
    keep = [r for r in old if r.get("design") not in {x["design"] for x in res}]
    man.write_text(json.dumps(keep + res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

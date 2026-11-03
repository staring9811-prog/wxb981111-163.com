"""评论月度 VP 追踪器 — local web app (Python standard library + openpyxl).

  python3 app.py                 # open http://localhost:8765 and work in the browser
  python3 app.py run <项目名> lists|estimate|collect|export|all     # command line

Projects: crawler/projects/<name>.json (no secrets). Data: crawler/data/projects/<name>/.
Keys: Network secrets (claude.ai cloud) or env BD_TOKEN / APIFY_TOKEN or crawler/.secrets.json (git-ignored).
"""
import glob, json, os, sys, threading, time, traceback, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from reviewkit import pipeline, estimate, export  # noqa: E402
from reviewkit.common import Ctx, load_json, save_json  # noqa: E402
from reviewkit.services import key  # noqa: E402

PROJ = os.path.join(HERE, "projects")
JOBS = {}


def load_cfg(name):
    return load_json(os.path.join(PROJ, f"{name}.json"))


def do_step(name, step):
    cfg = load_cfg(name)
    ctx = Ctx(cfg)
    steps = ["lists", "estimate", "collect", "export"] if step == "all" else [step]
    for s in steps:
        pipeline.status(ctx, step=s, running=True, error="")
        ctx.log(f"===== {s} 开始 =====")
        if s == "lists":
            pipeline.step_lists(ctx)
        elif s == "estimate":
            est = estimate.run(ctx)
            save_json(ctx.path("estimate.json"), est)
            ctx.log("评估：" + json.dumps(est["合计"], ensure_ascii=False))
        elif s == "collect":
            pipeline.step_collect(ctx)
        elif s == "export":
            os.makedirs(ctx.path("exports"), exist_ok=True)
            for plat in sorted({e["platform"] for e in pipeline.entries(ctx)}):
                fn = f"{plat}_{name}_{time.strftime('%Y%m%d')}.xlsx"
                n, m = export.export(ctx, plat, ctx.path("exports", fn))
                ctx.log(f"导出 {fn}：{n} 个商品，{m} 条评论")
            fn = f"汇总_{name}_{time.strftime('%Y%m%d')}.xlsx"
            n, m = export.export_combined(ctx, ctx.path("exports", fn))
            ctx.log(f"导出 {fn}（各渠道月度汇总总表）：{n} 个商品，{m} 条去重评论")
        ctx.log(f"===== {s} 完成 =====")
    pipeline.status(ctx, step=steps[-1], running=False)


def start_job(name, step):
    if JOBS.get(name) and JOBS[name].is_alive():
        return False

    def go():
        try:
            do_step(name, step)
        except Exception:
            ctx = Ctx(load_cfg(name))
            ctx.log("出错：\n" + traceback.format_exc()[-2000:])
            pipeline.status(ctx, running=False, error=traceback.format_exc()[-500:])
    JOBS[name] = threading.Thread(target=go, daemon=True)
    JOBS[name].start()
    return True


def project_state(name):
    ctx = Ctx(load_cfg(name))
    logf = ctx.path("run.log")
    log = open(logf, encoding="utf-8").read().splitlines()[-80:] if os.path.exists(logf) else []
    lists = {}
    for e in pipeline.entries(ctx):
        rows = (load_json(ctx.path("lists", f"{e['name']}.json")) or {}).get("rows", [])
        sel = [r for r in rows if r.get("排名")]
        done = sum(1 for r in sel if (load_json(ctx.path("products", r["平台"], f"{r['id']}.json")) or {}).get("状态"))
        lists[e["name"]] = {"看过": len(rows), "选中": len(sel), "目标": e.get("top_n"), "已采集": done}
    exports = sorted(os.listdir(ctx.path("exports"))) if os.path.isdir(ctx.path("exports")) else []
    return {"status": load_json(ctx.path("status.json"), {}), "log": log, "lists": lists,
            "estimate": load_json(ctx.path("estimate.json")), "exports": exports,
            "ledger": load_json(ctx.path("ledger.json"), {}),
            "running": bool(JOBS.get(name) and JOBS[name].is_alive()),
            "keys": {k: ("已配置" if key(k) != "dummy" else "未在本机配置（云端由 Network secrets 注入）") for k in ("BD_TOKEN", "APIFY_TOKEN")}}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/projects":
            return self._send(200, sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(PROJ, "*.json"))))
        if u.path == "/api/project":
            return self._send(200, load_cfg(q["name"]) or {})
        if u.path == "/api/state":
            return self._send(200, project_state(q["name"]))
        if u.path == "/download":
            ctx = Ctx(load_cfg(q["name"]))
            f = ctx.path("exports", os.path.basename(q["file"]))
            if os.path.exists(f):
                return self._send(200, open(f, "rb").read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote(os.path.basename(f))})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if u.path == "/api/project":
            cfg = json.loads(body)
            name = cfg.get("name", "").strip().replace("/", "_")
            if not name:
                return self._send(400, {"error": "项目名不能为空"})
            save_json(os.path.join(PROJ, f"{name}.json"), cfg)
            return self._send(200, {"ok": True, "name": name})
        if u.path == "/api/run":
            ok = start_job(q["name"], q["step"])
            return self._send(200 if ok else 409, {"ok": ok, "msg": "已开始" if ok else "该项目已有任务在运行"})
        return self._send(404, {"error": "not found"})


PAGE = open(os.path.join(HERE, "app_page.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "app_page.html")) else ""

def cli_new(argv):
    """One-line project creation for agents (Codex / Claude): build config → lists → estimate, then stop."""
    import argparse
    ap = argparse.ArgumentParser(prog="app.py new", description="新建项目并采集列表、给出时间费用评估（不采评论）")
    ap.add_argument("name")
    ap.add_argument("--category", default="")
    ap.add_argument("--start", default=f"{time.strftime('%Y')}-01-01", help="时间窗起始 YYYY-MM-DD")
    ap.add_argument("--full-end", default="", help="最后一个完整月月底 YYYY-MM-DD（默认上个月月底）")
    ap.add_argument("--top", type=int, default=100, help="每个入口取前 N")
    ap.add_argument("--keyword", help="三个平台都用这个关键词落地页")
    ap.add_argument("--lowes", help="Lowe's：网址（类目/BSR 榜单）或关键词")
    ap.add_argument("--hdp", help="Home Depot：网址或关键词")
    ap.add_argument("--wayfair", help="Wayfair：网址或关键词")
    ap.add_argument("--preset", default="", help="内置品类规则，如 bathroom_vanity")
    ap.add_argument("--include", default="", help="标题必含词，逗号分隔")
    ap.add_argument("--exclude", default="", help="标题排除词，逗号分隔")
    ap.add_argument("--keep", default="", help="含这些仍保留，逗号分隔")
    ap.add_argument("--dedupe-parent", action="store_true", help="父体去重")
    ap.add_argument("--dedupe-across", action="store_true", help="跨入口去重")
    ap.add_argument("--keep-sponsored", action="store_true", help="不排除广告位")
    ap.add_argument("--low-threshold", type=int, default=0, help="评论少于此数的商品…")
    ap.add_argument("--low-mode", default="split", choices=["split", "total_only", "skip"])
    ap.add_argument("--budget", type=float, default=10, help="每个平台每项服务的上限（美元）")
    ap.add_argument("--from", dest="base", help="以已有项目为模板复制")
    a = ap.parse_args(argv)
    if not a.full_end:
        import datetime
        a.full_end = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).isoformat()
    cfg = load_cfg(a.base) if a.base else {}
    cfg = dict(cfg, name=a.name, category=a.category or cfg.get("category", ""),
               window={"start": a.start, "full_end": a.full_end, "include_partial": True},
               dedupe_across_entries=a.dedupe_across, low_reviews={"threshold": a.low_threshold, "mode": a.low_mode},
               budget={k: a.budget for k in ("bd_lowes_usd", "bd_wayfair_usd", "apify_lowes_usd", "apify_wayfair_usd")},
               export=cfg.get("export", {"review_details": True}))
    if a.preset or a.include or a.exclude or a.keep or not a.base:
        cfg["filters"] = {"preset": a.preset, "include_keywords": [x.strip() for x in a.include.split(",") if x.strip()],
                          "exclude_keywords": [x.strip() for x in a.exclude.split(",") if x.strip()],
                          "keep_keywords": [x.strip() for x in a.keep.split(",") if x.strip()]}
    ents = []
    for plat, val, mode_url in (("Lowes", a.lowes, "bsr"), ("HomeDepot", a.hdp, "category"), ("Wayfair", a.wayfair, "category")):
        v = val or a.keyword
        if not v:
            continue
        e = {"enabled": True, "name": f"{plat}_{'关键词' if not v.startswith('http') else '类目'}", "platform": plat,
             "top_n": a.top, "exclude_sponsored": not a.keep_sponsored, "dedupe_parent": a.dedupe_parent}
        if v.startswith("http"):
            e.update(mode=mode_url, url=v)
        else:
            e.update(mode="keyword", keyword=v)
        ents.append(e)
    if ents:
        cfg["entries"] = ents
    if not cfg.get("entries"):
        sys.exit("至少给一个入口：--keyword 或 --lowes/--hdp/--wayfair")
    save_json(os.path.join(PROJ, f"{a.name}.json"), cfg)
    print(f"已保存 projects/{a.name}.json，开始采集列表并评估…")
    do_step(a.name, "lists")
    do_step(a.name, "estimate")
    est = load_json(Ctx(cfg).path("estimate.json"))
    print("\n===== 评估 =====")
    for p, v in est["平台"].items():
        print(f"{p}: {v['商品数']} 个商品，预计窗口内评论 {v['预计窗口内评论'][0]}–{v['预计窗口内评论'][1]} 条，"
              f"BD ${v['BD费用']}，Apify ${v['Apify费用']}，约 {v['预计耗时分钟']} 分钟")
    t = est["合计"]
    print(f"合计：约 ${t['总费用']}，约 {t['预计耗时分钟']} 分钟。{t['说明']}")
    print(f"\n确认后运行：python3 app.py run {a.name} collect && python3 app.py run {a.name} export")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "new":
        cli_new(sys.argv[2:])
    elif len(sys.argv) >= 4 and sys.argv[1] == "run":
        do_step(sys.argv[2], sys.argv[3])
    else:
        port = int(sys.argv[2]) if len(sys.argv) >= 3 and sys.argv[1] == "serve" else 8765
        print(f"打开浏览器访问 http://localhost:{port}")
        ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()

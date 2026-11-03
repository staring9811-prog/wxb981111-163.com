"""评论 VP 追踪（F23）：把原工具 reviewkit 并入系统（拷贝在 pdt/reviewkit，只改了密钥与记账，口径不变）。

- 项目设置存 data/vp/projects/<项目>.json，采集缓存与导出存 data/vp/data/<项目>/（与原工具同结构）；首次使用时
  把原工具 tools/评论月度VP追踪器/projects/ 下的项目设置复制过来（保留原工具全部项目设置）；
- 四步：① 采集列表（花钱：Lowe's / Wayfair 列表经 Bright Data，走费用闸门 vp_lists）→ ② 评估费用（不花钱）
  → ③ 采集评论（花钱，走费用闸门 vp_collect，可暂停，断点续跑不重复计费）→ ④ 导出 Excel；
- ③ 完成后把完整月份并入分析库：调用分析组 `core.channels.ingest_tracker_month(项目数据目录, months, collected_on)`，
  再调用 `core.ledger.reconcile_due()` 检查到期台账。
"""
import collections
import json
import math
import re
import shutil
import time
from datetime import date

from .. import costgate, services
from ..config import PROJECT_DIR, data_dir
from ..reviewkit import estimate as rk_estimate
from ..reviewkit import export as rk_export
from ..reviewkit import pipeline as rk_pipeline
from ..reviewkit.common import Ctx, load_json, save_json

ORIG_PROJECTS = PROJECT_DIR / "tools" / "评论月度VP追踪器" / "projects"
PLATS = {"HomeDepot": "Home Depot", "Lowes": "Lowe's", "Wayfair": "Wayfair"}
PAID = {"Lowes", "Wayfair"}  # 需要 Bright Data / Apify 的平台


class VpError(Exception):
    pass


def root():
    d = data_dir() / "vp"
    (d / "projects").mkdir(parents=True, exist_ok=True)
    (d / "data").mkdir(parents=True, exist_ok=True)
    return d


def projects() -> list:
    pdir = root() / "projects"
    if not any(pdir.glob("*.json")) and ORIG_PROJECTS.exists():
        for f in ORIG_PROJECTS.glob("*.json"):
            shutil.copy(f, pdir / f.name)
    return sorted(f.stem for f in pdir.glob("*.json"))


def load(name: str) -> dict:
    cfg = load_json(str(root() / "projects" / f"{name}.json"))
    if cfg is None:
        raise VpError("项目不存在")
    return cfg


def validate(cfg: dict):
    if not (cfg.get("name") or "").strip():
        raise VpError("请填写项目名")
    if not (cfg.get("category") or "").strip():
        raise VpError("请填写品类")
    w = cfg.get("window") or {}
    if not w.get("start") or not w.get("full_end"):
        raise VpError("请填写起始日期和最后一个完整月的月底")
    if w["start"] >= w["full_end"]:
        raise VpError("起始日期要早于最后一个完整月的月底")
    for i, e in enumerate(cfg.get("entries") or [], 1):
        if not e.get("enabled", True):
            continue
        if not (e.get("url") if e.get("mode") != "keyword" else e.get("keyword")):
            raise VpError(f"第 {i} 个入口缺少{'关键词' if e.get('mode') == 'keyword' else '网址'}")
        try:
            if int(e.get("top_n", 0)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise VpError("前 N 要填正整数") from None


def save(cfg: dict) -> str:
    validate(cfg)
    name = cfg["name"].strip().replace("/", "_")
    cfg["name"] = name
    save_json(str(root() / "projects" / f"{name}.json"), cfg)
    return name


def copy_as(src: str, new: str) -> str:
    new = (new or "").strip().replace("/", "_")
    if not new:
        raise VpError("请填写项目名")
    if new in projects():
        raise VpError("项目名不能和已有项目重复")
    cfg = load(src)
    cfg["name"] = new
    save_json(str(root() / "projects" / f"{new}.json"), cfg)
    return new


def rk_ctx(name: str, job=None, skip_paid=False) -> Ctx:
    cfg = load(name)
    if skip_paid:
        cfg = json.loads(json.dumps(cfg))
        for e in cfg.get("entries", []):
            if e.get("platform") in PAID:
                e["enabled"] = False
    ctx = Ctx(cfg, data_dir=str(root() / "data" / name))
    ctx.job = job
    return ctx


def paid_ready() -> bool:
    return services.connected("brightdata") and services.connected("apify")


def _target(name):
    return f"vp:{name}"


def _name(target: str) -> str:
    return target.split(":", 1)[1]


# ---------------------------------------------------------------- ① 采集列表（Lowe's / Wayfair 列表页经 Bright Data，计费）
def est_lists(p):
    ctx = rk_ctx(_name(p["target"]))
    lo = hi = 0
    for e in rk_pipeline.entries(ctx):
        if e["platform"] in PAID:
            top = int(e.get("top_n", 100))
            hi += max(5, math.ceil(top * 3 / 24) + 3) * (4 if e["platform"] == "Wayfair" else 3)
            lo += math.ceil(top / 24)
    ready = paid_ready()
    note = (f"Lowe's / Wayfair 列表页经 Bright Data，约 {lo}–{hi} 次请求（$1.5 / 千次）；Home Depot 直连免费；已采过的列表页不重复请求"
            if ready else "Bright Data / Apify 未连接：只采 Home Depot（免费），Lowe's / Wayfair 入口跳过")
    if not ready:
        lo = hi = 0
    return dict(service="brightdata", calls=hi, usd_lo=round(lo * 0.0015, 2), usd_hi=round(hi * 0.0015, 2),
                minutes=round(2 + hi * 0.5, 1), note=note)


def run_lists(ctx):
    name = _name(ctx.target)
    rc = rk_ctx(name, job=ctx, skip_paid=not paid_ready())
    if not paid_ready():
        rc.log("Bright Data / Apify 未连接：Lowe's / Wayfair 入口跳过，只采 Home Depot")
    rk_pipeline.status(rc, step="lists", running=True, error="")
    rc.log("===== lists 开始 =====")
    rk_pipeline.step_lists(rc)
    rc.log("===== lists 完成 =====")
    rk_pipeline.status(rc, step="lists", running=False)


# ---------------------------------------------------------------- ② 评估费用（不花钱）
def run_estimate(name: str) -> dict:
    rc = rk_ctx(name, skip_paid=not paid_ready())
    est = rk_estimate.run(rc)
    est["at"] = time.strftime("%m-%d %H:%M")
    save_json(rc.path("estimate.json"), est)
    rc.log("评估：" + json.dumps(est["合计"], ensure_ascii=False))
    return est


# ---------------------------------------------------------------- ③ 采集评论（计费，可暂停，续跑不重复计费）
def est_collect(p):
    name = _name(p["target"])
    est = run_estimate(name)
    pl, t = est["平台"], est["合计"]
    svcs = {"brightdata": dict(calls=sum(v.get("BD请求", 0) for v in pl.values()), usd_lo=t["BD费用"] * 0.5, usd_hi=t["BD费用"]),
            "apify": dict(calls=sum(1 for k in pl if k in PAID), usd_lo=round(t["Apify费用"] * 0.5, 2), usd_hi=t["Apify费用"])}
    note = "；".join(f"{PLATS[k]} {v['商品数']} 个商品，预计窗口内评论 {v['预计窗口内评论'][0]}–{v['预计窗口内评论'][1]} 条"
                    for k, v in pl.items()) + "。只计未完成部分；达到项目预算或月度上限即停，已采数据保留"
    return dict(service="apify", services=svcs, calls=sum(v["calls"] for v in svcs.values()),
                usd_lo=round(t["总费用"] * 0.5, 2), usd_hi=t["总费用"], minutes=t["预计耗时分钟"], note=note)


def run_collect(ctx):
    name = _name(ctx.target)
    rc = rk_ctx(name, job=ctx, skip_paid=not paid_ready())
    rk_pipeline.status(rc, step="collect", running=True, error="")
    rc.log("===== collect 开始 =====")
    try:
        rk_pipeline.step_collect(rc)
    finally:
        rk_pipeline.status(rc, step="collect", running=False)
    rc.log("===== collect 完成 =====")
    try:
        ingest(name)
    except Exception as e:  # 采集已完成并保存；并入失败要在日志和任务进度里看得到，可在“其他渠道数据”页重新上传导出
        import traceback
        rc.log("并入分析库失败：\n" + traceback.format_exc()[-1500:])
        ctx.progress(ingest_error=f"{type(e).__name__}: {e}")


def ingest(name: str) -> dict:
    """完整月份并入分析库（AC-F28-01）。分析组接口：core.channels.ingest_tracker_month。"""
    rc = rk_ctx(name)
    full = [m for m in rc.months if "未完整" not in m]
    try:
        from . import channels
    except ImportError:
        rc.log("分析库并入接口（core.channels.ingest_tracker_month）还未就绪，本次未并入")
        return {}
    stat = channels.ingest_tracker_month(rc.data, months=full, collected_on=date.today().isoformat())
    rc.log("并入分析库：" + json.dumps(stat, ensure_ascii=False, default=str)[:300])
    rk_pipeline.status(rc, ingested=time.strftime("%Y-%m-%d %H:%M"))
    from . import ledger
    ledger.reconcile_due()
    return stat


costgate.register("vp_lists", "评论 VP 追踪 · ① 采集列表", est_lists, run_lists)
costgate.register("vp_collect", "评论 VP 追踪 · ③ 采集评论", est_collect, run_collect)


# ---------------------------------------------------------------- ④ 导出 Excel（与原工具 app.py do_step('export') 相同）
def run_export(name: str) -> list:
    rc = rk_ctx(name)
    import os
    os.makedirs(rc.path("exports"), exist_ok=True)
    files = []
    for plat in sorted({e["platform"] for e in rk_pipeline.entries(rc)}):
        fn = f"{plat}_{name}_{time.strftime('%Y%m%d')}.xlsx"
        n, m = rk_export.export(rc, plat, rc.path("exports", fn))
        rc.log(f"导出 {fn}：{n} 个商品，{m} 条评论")
        files.append(fn)
    fn = f"汇总_{name}_{time.strftime('%Y%m%d')}.xlsx"
    n, m = rk_export.export_combined(rc, rc.path("exports", fn))
    rc.log(f"导出 {fn}（各渠道月度汇总总表）：{n} 个商品，{m} 条去重评论")
    files.append(fn)
    return files


# ---------------------------------------------------------------- 页面状态
def state(name: str) -> dict:
    rc = rk_ctx(name)
    import os
    logf = rc.path("run.log")
    log = open(logf, encoding="utf-8").read().splitlines()[-80:] if os.path.exists(logf) else []
    lists, prog = {}, {}
    for e in rk_pipeline.entries(rc):
        rows = (load_json(rc.path("lists", f"{e['name']}.json")) or {}).get("rows", [])
        sel = [r for r in rows if r.get("排名")]
        done = sum(1 for r in sel if (load_json(rc.path("products", r["平台"], f"{r['id']}.json")) or {}).get("状态"))
        lists[e["name"]] = {"看过": len(rows), "选中": len(sel), "目标": e.get("top_n"), "已采集": done, "done": bool(rows)}
        p = prog.setdefault(e["platform"], [0, 0])
        p[0] += done
        p[1] += len(sel)
    exports = sorted(os.listdir(rc.path("exports"))) if os.path.isdir(rc.path("exports")) else []
    return {"status": load_json(rc.path("status.json"), {}) or {}, "log": log, "lists": lists, "progress": prog,
            "estimate": load_json(rc.path("estimate.json")), "exports": exports, "ledger": load_json(rc.path("ledger.json"), {}) or {},
            "months": rc.months}


def monthly(name: str) -> list:
    """入口月度汇总（渠道 × 月，按评论 ID 去重；Wayfair 只有 Verified Purchase 计 VP，口径来自原工具 export）。"""
    rc = rk_ctx(name)
    out = []
    for plat in sorted({e["platform"] for e in rk_pipeline.entries(rc)}):
        _, revs = rk_export.gather(rc, plat)
        uniq = {x["评论ID"]: x for x in revs}.values()
        by = collections.Counter(x["月份"] for x in uniq)
        full = [x for x in uniq if "未完整" not in x["月份"]]
        vp = sum(1 for x in full if x["VP状态"] == "VP")
        out.append(dict(platform=plat, name=PLATS[plat], months={m: by.get(m, 0) for m in rc.months}, total=len(full), vp=vp,
                        nonvp=len(full) - vp, partial=sum(v for m, v in by.items() if "未完整" in m)))
    return out


def month_short(m: str) -> str:
    mm = re.match(r"(\d{4})-(\d{2})(.*)", m)
    return f"{int(mm.group(2))} 月{'（未完整）' if mm.group(3) else ''}" if mm else m

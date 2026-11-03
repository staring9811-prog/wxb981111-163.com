"""Pipeline steps: lists → estimate → collect → export. Each step is resumable (everything is cached on disk)."""
import os, math, time, traceback
from concurrent.futures import ThreadPoolExecutor
from . import hdp, lowes, wayfair
from .classify import include_reason
from .common import Ctx, save_json, load_json
from .services import BudgetExceeded
from ..costgate import CapReached, Paused

ADAPTERS = {"HomeDepot": hdp, "Lowes": lowes, "Wayfair": wayfair}
MODES = {"bsr": "BSR/热销榜", "category": "类目落地页", "keyword": "关键词落地页"}


def entries(ctx):
    return [e for e in ctx.cfg.get("entries", []) if e.get("enabled", True)]


def status(ctx, **kw):
    s = load_json(ctx.path("status.json"), {}) or {}
    s.update(kw, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
    save_json(ctx.path("status.json"), s)


# ------------------------------------------------------------------ step 1: lists + selection
def select_entry(ctx, entry, taken):
    """Walk the landing page in display order and pick the top N under the configured rules.
    taken: ids/parents already selected by earlier entries (for cross-entry dedupe)."""
    ad = ADAPTERS[entry["platform"]]
    f = ctx.path("lists", f"{entry['name']}.json")
    cached = load_json(f)
    key = [entry.get(k) for k in ("platform", "mode", "url", "keyword", "top_n", "sort", "exclude_sponsored", "dedupe_parent")]
    key += [ctx.cfg.get("filters"), ctx.cfg.get("dedupe_across_entries")]
    if cached and cached.get("key") == key and cached.get("done") and cached.get("taken_in") == sorted(taken):
        for r in cached["rows"]:
            if r.get("排名"):
                taken.update(r["_dedupe"])
        return cached["rows"]
    taken_in = sorted(taken)
    top = int(entry.get("top_n", 100))
    rows, seen_ids, seen_parent, rank, page, state = [], set(), set(), 0, 0, {}
    max_pages = max(5, math.ceil(top * 3 / 24) + 3)
    filters = ctx.cfg.get("filters", {})
    while rank < top and page < max_pages:
        items = ad.list_page(ctx, entry, page, state)
        if items is None:
            ctx.log(f"{entry['name']}: 第{page + 1}页取不到，排名停在 {rank}")
            break
        if not items:
            break
        for it in items:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            r = dict(it, 平台=ad.NAME, 入口=entry["name"], 落地页类型=MODES.get(entry.get("mode"), ""))
            if it["sponsored"] and entry.get("exclude_sponsored", True):
                r["纳入情况"] = "排除-广告"
            else:
                r["纳入情况"] = include_reason(it["title"], filters)
            if r["纳入情况"] == "纳入" and rank < top:
                parent = it.get("parent_id")
                if entry.get("dedupe_parent") and entry["platform"] == "HomeDepot":
                    parent = hdp.family_signature(ctx, r)
                r["_dedupe"] = [f"{ad.NAME}:id:{it['id']}"] + ([f"{ad.NAME}:p:{parent}"] if parent else [])
                if entry.get("dedupe_parent") and parent and parent in seen_parent:
                    r["纳入情况"] = "排除-同父体重复"
                elif ctx.cfg.get("dedupe_across_entries") and any(k in taken for k in r["_dedupe"]):
                    r["纳入情况"] = "排除-跨入口重复"
                else:
                    seen_parent.add(parent)
                    rank += 1
                    r["排名"] = rank
            elif r["纳入情况"] == "纳入":
                break
            rows.append(r)
        page += 1
        save_json(f, {"key": key, "done": False, "rows": rows})
    for r in rows:
        if r.get("排名"):
            taken.update(r["_dedupe"])
    save_json(f, {"key": key, "done": rank >= top or page >= max_pages, "rows": rows, "taken_in": taken_in})
    ctx.log(f"{entry['name']}: 选中 {rank}/{top}，共看 {len(rows)} 个（含排除）")
    return rows


def step_lists(ctx):
    taken, out = set(), {}
    for e in entries(ctx):
        status(ctx, step="列表", detail=e["name"])
        out[e["name"]] = select_entry(ctx, e, taken)
    return out


def selected(ctx):
    rows = []
    for e in entries(ctx):
        for r in (load_json(ctx.path("lists", f"{e['name']}.json")) or {}).get("rows", []):
            if r.get("排名"):
                rows.append(r)
    return rows


# ------------------------------------------------------------------ step 2: collect
def low_mode(ctx, r):
    th = int(ctx.cfg.get("low_reviews", {}).get("threshold", 0) or 0)
    if th and (r.get("review_count") or 0) < th:
        return ctx.cfg.get("low_reviews", {}).get("mode", "split")
    return "split"


def save_product(ctx, plat, pid, status_, note, det, revs):
    save_json(ctx.path("products", plat, f"{pid}.json"),
              {"状态": status_, "备注": note, "details": det or {}, "reviews": revs})


def step_collect(ctx):
    rows = selected(ctx)
    todo = {}
    for r in rows:
        f = ctx.path("products", r["平台"], f"{r['id']}.json")
        if (load_json(f) or {}).get("状态") in ("完整", "部分", "跳过-评论少"):
            continue
        if low_mode(ctx, r) == "skip":
            save_product(ctx, r["平台"], r["id"], "跳过-评论少", f"页面评论数 {r.get('review_count')} 低于阈值，未采集", {}, [])
            continue
        todo.setdefault(r["平台"], {})[r["id"]] = r     # same product in two entries → collect once
    ctx.log("待采集：" + ", ".join(f"{k} {len(v)}" for k, v in todo.items()) or "无")

    def do_hdp(rs):
        def one(r):
            o = hdp.collect(ctx, r)
            save_product(ctx, "HomeDepot", r["id"], o["状态"], o["备注"], o["details"], o["reviews"])
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(one, rs))

    def do_lowes(rs):
        res = lowes.reviews_batch(ctx, rs)
        with ThreadPoolExecutor(6) as ex:
            dets = dict(zip([r["id"] for r in rs], ex.map(lambda r: lowes.details(ctx, r), rs)))
        for r in rs:
            revs, st, note = res[r["id"]]
            if dets.get(r["id"]) is None:
                note = "；".join(x for x in (note, "详情页未取到") if x)
            save_product(ctx, "Lowes", r["id"], st, note, dets.get(r["id"]), revs)

    def do_wayfair(rs):
        res = wayfair.reviews_batch(ctx, rs)
        for r in rs:
            revs, st, note, det = res[r["id"]]
            save_product(ctx, "Wayfair", r["id"], st, note, det, revs)

    jobs = {"HomeDepot": do_hdp, "Lowes": do_lowes, "Wayfair": do_wayfair}
    stops = []  # 并入判定台后：设置页月度上限（CapReached）与暂停（Paused）要停下整个任务，交给费用闸门记状态

    def run(plat):
        try:
            status(ctx, step="采集", detail=plat)
            jobs[plat](list(todo[plat].values()))
            ctx.log(f"{plat} 采集完成")
        except BudgetExceeded as e:
            ctx.log(f"{plat} 达到预算上限，已停止：{e}")
        except (CapReached, Paused) as e:
            ctx.log(f"{plat} 已停止：{e or '已暂停，已完成部分保留'}")
            stops.append(e)
        except Exception:
            ctx.log(f"{plat} 出错：\n{traceback.format_exc()[-1500:]}")

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(run, list(todo)))
    if stops:
        raise stops[0]

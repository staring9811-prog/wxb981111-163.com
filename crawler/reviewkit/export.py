"""Excel per platform: 月度趋势 / 入口月度汇总 / 商品 / 评论明细(optional)."""
import collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from .common import load_json
from .pipeline import entries, low_mode

P_COLS = ["平台", "入口", "落地页类型", "排名", "平台徽章", "商品ID", "品牌", "标题", "型号/SKU", "选中颜色/尺寸", "卖点",
          "商品描述", "规格参数", "主图URL", "全部图片URL", "商品链接", "价格(USD)", "页面评分", "页面累计评论数",
          "纳入情况", "窗口内评论数", "VP", "non_VP", "其中转载", "VP区分", "采集状态", "备注"]
R_COLS = ["平台", "入口", "商品ID", "评论ID", "评论日期", "月份", "评分", "评论标题", "评论原文", "VP状态", "VP证据", "转载", "多商品共享"]
ROW_MAP = {"id": "商品ID", "title": "标题", "brand": "品牌", "model": "型号/SKU", "badges": "平台徽章", "url": "商品链接",
           "price": "价格(USD)", "rating": "页面评分", "review_count": "页面累计评论数"}


def gather(ctx, plat):
    prods, revs = [], []
    for e in entries(ctx):
        if e["platform"] != plat:
            continue
        for r in (load_json(ctx.path("lists", f"{e['name']}.json")) or {}).get("rows", []):
            row = {ROW_MAP.get(k, k): v for k, v in r.items() if not k.startswith("_")}
            if r.get("排名"):
                p = load_json(ctx.path("products", plat, f"{r['id']}.json"))
                split = low_mode(ctx, r) == "split"
                row["VP区分"] = "是" if split else "否（评论少，只计合计）"
                if p:
                    for k, v in (p.get("details") or {}).items():
                        if v and not row.get(k) or k in ("标题", "品牌") and v:
                            row[k] = v
                    rv = [dict(x, 平台=plat, 入口=e["name"], 商品ID=r["id"], 月份=ctx.month_label(x["评论日期"]),
                               _split=split) for x in p.get("reviews") or [] if ctx.in_window(x.get("评论日期"))]
                    c = collections.Counter(x["VP状态"] for x in rv)
                    row.update({"窗口内评论数": len(rv), "VP": c.get("VP", 0) if split else "",
                                "non_VP": c.get("non_VP", 0) if split else "", "其中转载": sum(x.get("转载") == "是" for x in rv),
                                "采集状态": p.get("状态", ""), "备注": p.get("备注", "")})
                    revs += rv
                else:
                    row["采集状态"] = "未采集"
            prods.append(row)
    owners = collections.defaultdict(set)
    for x in revs:
        owners[x["评论ID"]].add(x["商品ID"])
    for x in revs:
        x["多商品共享"] = "是" if len(owners[x["评论ID"]]) > 1 else "否"
    return prods, revs


def _months_cols(ctx, prefix):
    cols = list(prefix)
    for m in ctx.months:
        cols += [f"{m} VP", f"{m} 非VP", f"{m} 合计"]
    return cols + ["完整月 VP合计", "完整月 非VP合计", "完整月 合计", "完整月 VP占比"]


def _fill(ctx, row, rs, split=True):
    c = collections.Counter((x["月份"], x["VP状态"]) for x in rs)
    t = collections.Counter(x["月份"] for x in rs)
    for m in ctx.months:
        row[f"{m} VP"] = c.get((m, "VP"), 0) if split else ""
        row[f"{m} 非VP"] = c.get((m, "non_VP"), 0) + c.get((m, "unknown"), 0) if split else ""
        row[f"{m} 合计"] = t.get(m, 0)
    full = [x for x in rs if "未完整" not in x["月份"]]
    vp = sum(x["VP状态"] == "VP" for x in full)
    row.update({"完整月 VP合计": vp if split else "", "完整月 非VP合计": len(full) - vp if split else "",
                "完整月 合计": len(full), "完整月 VP占比": f"{vp / len(full):.1%}" if split and full else ""})
    return row


def _sheet(ws, cols, rows, lists=None):
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for r in rows:
        ws.append([r.get(c, "") if r.get(c) is not None else "" for c in cols])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(rows) + 1, 2)}"
    wide = {"标题": 50, "卖点": 50, "商品描述": 60, "规格参数": 50, "全部图片URL": 40, "评论原文": 80, "VP证据": 40, "备注": 40}
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = wide.get(c, 13)
    for col, opts in (lists or {}).items():
        if col in cols:
            dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
            L = get_column_letter(cols.index(col) + 1)
            dv.add(f"{L}2:{L}{max(len(rows) + 1, 2)}")
            ws.add_data_validation(dv)


def export(ctx, plat, path):
    prods, revs = gather(ctx, plat)
    by = collections.defaultdict(list)
    for x in revs:
        by[(x["入口"], x["商品ID"])].append(x)
    wb = Workbook()
    ws = wb.active
    ws.title = "月度趋势"
    trend = []
    for p in prods:
        if p.get("排名"):
            row = {k: p.get(k, "") for k in ("平台", "入口", "排名", "商品ID", "品牌", "标题", "页面累计评论数", "VP区分", "采集状态")}
            trend.append(_fill(ctx, row, by.get((p["入口"], p["商品ID"]), []), p.get("VP区分") == "是"))
    _sheet(ws, _months_cols(ctx, ("平台", "入口", "排名", "商品ID", "品牌", "标题", "页面累计评论数", "VP区分", "采集状态")), trend)
    ent = []
    for e in entries(ctx):
        if e["platform"] != plat:
            continue
        uniq = {}
        for x in revs:
            if x["入口"] == e["name"]:
                uniq[x["评论ID"]] = x
        ent.append(_fill(ctx, {"平台": plat, "入口": e["name"], "去重评论数": len(uniq)}, list(uniq.values())))
    _sheet(wb.create_sheet("入口月度汇总"), _months_cols(ctx, ("平台", "入口", "去重评论数")), ent)
    _sheet(wb.create_sheet("商品"), P_COLS, prods, {"采集状态": ["完整", "部分", "失败", "未采集", "跳过-评论少"]})
    if ctx.cfg.get("export", {}).get("review_details", True):
        revs.sort(key=lambda x: (x["入口"], str(x["商品ID"]), x.get("评论日期", "")))
        _sheet(wb.create_sheet("评论明细"), R_COLS, revs, {"VP状态": ["VP", "non_VP", "unknown"]})
    wb.save(path)
    return len([p for p in prods if p.get("排名")]), len(revs)

"""Build the 2-sheet Excel (SCHEMA.md v2) from collected JSON for one or more platforms."""
import os, glob, json, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from .common import DATA, load_json, month_of

P_COLS = ["平台", "入口", "排名", "平台徽章", "商品ID", "品牌", "标题", "型号/SKU", "选中颜色/尺寸", "卖点", "商品描述",
          "规格参数", "主图URL", "全部图片URL", "商品链接", "价格(USD)", "页面评分", "页面累计评论数", "纳入情况",
          "2026评论数", "VP", "non_VP", "unknown", "其中转载", "采集状态", "备注"]
R_COLS = ["平台", "入口", "商品ID", "评论ID", "评论日期", "月份", "评分", "评论标题", "评论原文", "VP状态", "VP证据",
          "转载", "多商品共享"]
DIRS = {"HomeDepot": "hdp", "Lowes": "lowes", "Wayfair": "wayfair"}


def _product_file(plat_dir, row):
    key = row.get("sku") or row["商品ID"]
    return os.path.join(DATA, plat_dir, "products", f"{key}.json")


def gather(platforms):
    prods, revs = [], []
    for plat in platforms:
        d = DIRS[plat]
        for lf in sorted(glob.glob(os.path.join(DATA, d, "list_*.json"))):
            for row in (load_json(lf) or {}).get("rows", []):
                row = dict(row)
                pd = load_json(_product_file(d, row)) if row.get("排名") else None
                if pd:
                    for k, v in (pd.get("details") or {}).items():
                        if v and not row.get(k):
                            row[k] = v
                    rv = pd.get("reviews") or []
                    c = collections.Counter(r["VP状态"] for r in rv)
                    row.update({"2026评论数": len(rv), "VP": c.get("VP", 0), "non_VP": c.get("non_VP", 0),
                                "unknown": c.get("unknown", 0), "其中转载": sum(r.get("转载") == "是" for r in rv),
                                "采集状态": pd.get("状态", ""), "备注": pd.get("备注", "")})
                    for r in rv:
                        r = dict(r, 入口=row["入口"], 商品ID=row["商品ID"], 月份=month_of(r.get("评论日期")))
                        revs.append(r)
                elif row.get("排名"):
                    row.update({"采集状态": "未采集"})
                prods.append(row)
    # same review attached to more than one product (variants / family) → flag
    owners = collections.defaultdict(set)
    for r in revs:
        owners[(r["平台"], r["评论ID"])].add(r["商品ID"])
    for r in revs:
        r["多商品共享"] = "是" if len(owners[(r["平台"], r["评论ID"])]) > 1 else "否"
    return prods, revs


def _sheet(ws, cols, rows, lists):
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
        ws.column_dimensions[get_column_letter(i)].width = wide.get(c, 14)
    n = max(len(rows) + 1, 2)
    for col, opts in lists.items():
        if col in cols:
            dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
            L = get_column_letter(cols.index(col) + 1)
            dv.add(f"{L}2:{L}{n}")
            ws.add_data_validation(dv)


MONTHS = [f"2026-{m:02d}" for m in range(1, 11)] + ["2026-11（未完整）"]


def _month_cols(prefix=(), unknown=False):
    cols = list(prefix)
    for m in MONTHS:
        cols += [f"{m} VP", f"{m} 非VP"] + ([f"{m} unknown"] if unknown else [])
    return cols + ["1-10月 VP合计", "1-10月 非VP合计", "1-10月 unknown合计", "1-10月 VP占比"]


def _fill_months(row, rs):
    c = collections.Counter((r["月份"], r["VP状态"]) for r in rs)
    for m in MONTHS:
        row[f"{m} VP"] = c.get((m, "VP"), 0)
        row[f"{m} 非VP"] = c.get((m, "non_VP"), 0)
        row[f"{m} unknown"] = c.get((m, "unknown"), 0)
    full = [r for r in rs if r["月份"] in MONTHS[:10]]
    vp = sum(r["VP状态"] == "VP" for r in full)
    nvp = sum(r["VP状态"] == "non_VP" for r in full)
    unk = sum(r["VP状态"] == "unknown" for r in full)
    row.update({"1-10月 VP合计": vp, "1-10月 非VP合计": nvp, "1-10月 unknown合计": unk,
                "1-10月 VP占比": f"{vp / (vp + nvp):.1%}" if vp + nvp else ""})
    return row


def trend_rows(prods, revs):
    by = collections.defaultdict(list)
    for r in revs:
        by[(r["平台"], r["入口"], r["商品ID"])].append(r)
    out = []
    for p in prods:
        if not p.get("排名"):
            continue
        row = {k: p.get(k, "") for k in ("平台", "入口", "排名", "商品ID", "品牌", "标题", "采集状态")}
        out.append(_fill_months(row, by.get((p["平台"], p["入口"], p["商品ID"]), [])))
    return out


def entry_rows(revs):
    by = collections.defaultdict(dict)
    for r in revs:
        by[(r["平台"], r["入口"])][r["评论ID"]] = r  # dedupe shared reviews within an entry
    out = []
    for (plat, entry), d in sorted(by.items()):
        out.append(_fill_months({"平台": plat, "入口": entry, "去重评论数": len(d)}, list(d.values())))
    return out


def export(platforms, path):
    prods, revs = gather(platforms)
    wb = Workbook()
    ws = wb.active
    ws.title = "月度趋势"
    unk = "Wayfair" in platforms
    tcols = _month_cols(("平台", "入口", "排名", "商品ID", "品牌", "标题", "采集状态"), unk)
    _sheet(ws, tcols, trend_rows(prods, revs), {})
    ws_e = wb.create_sheet("入口月度汇总")
    _sheet(ws_e, _month_cols(("平台", "入口", "去重评论数"), unk), entry_rows(revs), {})
    ws = wb.create_sheet("商品")
    _sheet(ws, P_COLS, prods, {"平台": ["Lowes", "HomeDepot", "Wayfair"], "采集状态": ["完整", "部分", "失败", "未采集"]})
    ws2 = wb.create_sheet("评论明细")
    revs.sort(key=lambda r: (r["平台"], r["入口"], str(r["商品ID"]), r.get("评论日期", "")), reverse=False)
    _sheet(ws2, R_COLS, revs, {"VP状态": ["VP", "non_VP", "unknown"], "转载": ["是", "否", "待核实"], "多商品共享": ["是", "否"]})
    wb.save(path)
    return len(prods), len(revs)

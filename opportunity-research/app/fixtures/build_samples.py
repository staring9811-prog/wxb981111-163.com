"""Build the hand-designed sample packages used by the acceptance tests (TDD 验收契约 §0.1).

Every expected value in the packages' 说明.md is a design input written down here (counts of hits,
keyword volumes, units …) and derived by hand from the confirmed rules; nothing is computed by the
oppo package. Values are deterministic per product-month, so H1-B is an exact extension of H1-A.

Usage: python fixtures/build_samples.py [--out DIR] [--with-scale]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ALNUM = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

C1_COLS = ["月份", "子ASIN", "当月父ASIN", "品牌", "卖家", "标题", "上架日期", "子体月销量", "子体月销售额", "父体月销量",
           "小类BSR", "类目节点", "配送方式", "变体数", "首次评分日期", "过去一个月购买", "当月价格", "当月评分", "五点描述",
           "优惠券"]
C2_COLS = ["子ASIN", "父ASIN", "品牌", "标题", "上架日期", "配送方式", "变体数", "首次评分日期", "五点描述"]
C3_COLS = ["月份", "子ASIN", "子体月销量", "子体月销售额", "小类BSR", "父体月销量"]
DIMS = ["尺寸", "颜色", "盆数", "形态", "安装方式", "元素", "台面形态", "柜体材质", "台面材质", "台盆材质"]
C4_COLS = ["子ASIN"] + [c for d in DIMS for c in (d, f"{d}证据状态")]
C5_COLS = ["关键词", "月份", "月搜索量", "关键词属性标签"]
C6_COLS = ["评论ID", "ASIN", "归属级别", "评论日期", "星级", "痛点事件代码", "是否结构类痛点", "标注版本"]
C7_COLS = ["立项名称", "立项日期", "关联细分或属性"]


def h(*parts: Any) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


_used_asins: set[str] = set()


def asin(*key: Any, prefix: str = "B0") -> str:
    n = h("asin", *key)
    while True:
        s = prefix
        x = n
        while len(s) < 10:
            s += ALNUM[x % len(ALNUM)]
            x //= len(ALNUM)
        if s not in _used_asins:
            _used_asins.add(s)
            return s
        n += 7919


def add_months(m: str, k: int) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    i = y * 12 + mo - 1 + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def mrange(a: str, b: str) -> list[str]:
    out = []
    while a <= b:
        out.append(a)
        a = add_months(a, 1)
    return out


def ym(m: str) -> str:
    return m.replace("-", "")


# ---- segments ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Seg:
    width: str
    form: str
    band: str

    @property
    def name(self) -> str:
        return f"{self.width} · {self.form} · {self.band}"


W_SMALL, W_MID, W_BIG = "≤30″", "30–48″", "≥48″"
FLOOR, FLOAT = "落地式", "悬浮式"
LOW, MIDP, HIGH = "<$500", "$500–900", "≥$900"
SIZES = {W_SMALL: (24, 30), W_MID: (36, 42), W_BIG: (48, 60)}
PRICE = {LOW: (300, 480), MIDP: (520, 880), HIGH: (950, 1450)}

SEGS = {
    "X": Seg(W_MID, FLOOR, MIDP), "Y": Seg(W_MID, FLOOR, LOW),
    "S5": Seg(W_SMALL, FLOOR, LOW), "Z19": Seg(W_SMALL, FLOOR, MIDP), "S9": Seg(W_SMALL, FLOOR, HIGH),
    "S6": Seg(W_MID, FLOAT, MIDP), "S10": Seg(W_MID, FLOAT, HIGH), "Q3": Seg(W_MID, FLOAT, LOW),
    "S7": Seg(W_BIG, FLOOR, MIDP), "P1a": Seg(W_BIG, FLOOR, LOW), "P1b": Seg(W_BIG, FLOOR, HIGH),
    "S8": Seg(W_SMALL, FLOAT, MIDP), "P2a": Seg(W_SMALL, FLOAT, LOW), "P2b": Seg(W_SMALL, FLOAT, HIGH),
    "M": Seg(W_BIG, FLOAT, MIDP),
}

FORM_WORD = {FLOOR: "Freestanding", FLOAT: "Floating"}
INSTALL = {FLOOR: "落地", FLOAT: "壁挂"}
COLORS = ["White", "Gray", "Navy Blue", "Espresso", "Natural Oak", "Black", "Sage Green", "Walnut"]
COLOR_CN = {"White": "白色", "Gray": "灰色", "Navy Blue": "海军蓝", "Espresso": "深咖", "Natural Oak": "原木色",
            "Black": "黑色", "Sage Green": "灰绿", "Walnut": "胡桃色"}
ELEMENTS = ["现代", "北欧", "美式", "中式", "工业风"]
TOPS = ["一体盆", "台上盆", "台下盆"]
BODY = ["实木", "MDF", "竹", "橡胶木"]
TOP_MAT = ["陶瓷", "石英", "岩板", "大理石"]
LINES = ["Harbor", "Lucca", "Aspen", "Bristol", "Calder", "Dalton", "Everett", "Fresno", "Galway", "Hudson", "Ithaca",
         "Juniper", "Kendall", "Laurel", "Monroe", "Newport", "Oakley", "Preston", "Quincy", "Rowan", "Sutton",
         "Thayer", "Upton", "Verona", "Weston", "Yardley", "Zurich", "Amherst", "Belmont", "Carlisle", "Denver",
         "Easton", "Fairview", "Glendale", "Hampton", "Irving", "Jasper", "Kingston", "Linden", "Madison", "Norwood",
         "Orchard", "Parker", "Raleigh", "Salem", "Trenton", "Vail", "Windsor", "Ashby", "Brook", "Cedar", "Delmar",
         "Elm", "Fulton", "Grove", "Haven", "Ivy", "Jordan", "Keene", "Lake", "Meadow", "Noble", "Olive", "Pine",
         "Ridge", "Stone", "Tulsa", "Union", "Vale", "Willow", "Alder", "Birch", "Cove", "Dune", "Ember", "Fern"]
TEMPLATES = [
    "{b} {s} Inch Bathroom Vanity with Sink, {line} {form} Shaker Cabinet with Soft Close Doors, {c}",
    "{b} {line} {s}\" {form} Vanity Set with Ceramic Vessel Basin and Open Shelf, {c}",
    "{b} {s} Inch {form} Bath Vanity Combo, {line} Collection with Quartz Countertop and Backsplash, {c}",
    "{b} {line} Modern {form} Bathroom Cabinet {s} in, Two Drawers and Integrated Resin Sink, {c}",
    "{b} {s}\" Farmhouse {form} Vanity with Marble Top, {line} Series Barn Door Storage, {c}",
    "{b} {line} {s} Inch {form} Single Vanity with Undermount Rectangular Basin and Brushed Hardware, {c}",
    "{b} Compact {s} Inch {form} Powder Room Vanity, {line} Edition Space Saving Cabinet, {c}",
    "{b} {line} Mid Century {s}\" {form} Vanity with Fluted Doors and Gold Handles, {c}",
    "{b} {s} Inch {form} Wood Vanity with Stone Top, {line} Handcrafted Rustic Finish, {c}",
    "{b} {line} {s} in. {form} Vanity Unit with LED Mirror Cabinet and Soft Close Hinges, {c}",
    "{b} {s} Inch {form} Coastal Vanity, {line} Louvered Doors with Adjustable Shelf, {c}",
    "{b} {line} Industrial {s}\" {form} Vanity with Metal Frame and Concrete Look Top, {c}",
]
NEW_BRANDS = ["Kiro", "Altair", "Merax", "Kleankin", "Tribesigns", "VANITYART", "HOMLUX", "Puluomis", "Eclife",
              "SOLIDEE", "Woodbridge", "LUCA Kitchen & Bath", "Nicbex", "Ronbow", "Belanger", "Hzuaneri", "Ktaxon",
              "Vinnova", "Elegant Decor", "James Martin", "Casainc", "Swiss Madison", "Stufurhome", "Ari Kitchen",
              "Native Trails", "Avanity", "Eviva", "Fine Fixtures", "Moreno Bath", "Legion Furniture", "Maykke",
              "Design Element", "Vanity Art Pro", "Lexora", "Water Creation", "Silkroad", "Sagehill", "Dreamline",
              "Haven Home", "Ove Decors", "Glacier Bay", "Allen Roth", "Crosswater", "Foremost", "Belvedere",
              "Kingsman", "Blossom", "Mirabelle", "Monterey", "Aquadom", "Brookline", "Cottonwood", "Duravit Style",
              "Elkay Home", "Fairmont Designs", "Gatco", "Hanover Bath", "Ivory Lane", "Jade Bath", "Kinsley",
              "Larchmont", "Montauk", "Nautica Home", "Oakridge Bath", "Palisade", "Quarry Lane", "Redwood Bath",
              "Seabrook", "Timberline", "Urbana", "Vesta Home", "Whitfield", "Yorktown", "Zenith Bath", "Arbor Lane"]
DESIGNED_BRANDS = {"SOLIDEE", "Eclife", "Woodbridge", "Puluomis", "HOMLUX", "Kingsman", "Belvedere",
                   "Mirabelle", "Monterey", "Aquadom", "Blossom"}
ROTATION = [b for b in NEW_BRANDS if b not in DESIGNED_BRANDS]
OLD_BRANDS = ["Wyndham Collection", "Virtu USA", "Fresca", "Spa Bathe", "Bellaterra", "Chans Furniture",
              "Ancerre Designs", "Home Decorators", "Scott Living", "Twin Star", "Kohler Style", "Pegasus",
              "Simpli Home", "Bathroom Plus", "Modern Sanitation", "Wellfor", "Gotalent", "Comfort Bath",
              "Vanity Republic", "Northlake"]


@dataclass
class Child:
    asin: str
    parent: str
    brand: str
    title: str
    seg: Seg
    size: int
    color: str
    price: int
    launch: str  # YYYY-MM-DD
    first_review: str | None
    fulfillment: str
    variants: int
    attrs: dict[str, tuple[str, str]] = field(default_factory=dict)
    bullets: str | None = None
    new: bool = False


@dataclass
class Plan:
    """A new SPU: outcome is 'bsr@a', 'gmv@a', 'miss', 'inc@a', 'watch', 'flat' (not rising)."""
    key: str
    segkey: str
    batch: str
    outcome: str
    children: list[Child] = field(default_factory=list)
    rise_age: int = 3


class Package:
    def __init__(self, name: str):
        self.name = name
        self.c1: list[dict[str, Any]] = []
        self.c2: list[dict[str, Any]] = []
        self.c3: list[dict[str, Any]] = []
        self.c4: list[dict[str, Any]] = []
        self.c5: list[dict[str, Any]] = []
        self.c6: list[dict[str, Any]] = []
        self.c7: list[dict[str, Any]] = []
        self.manifest: dict[str, Any] = {}
        self.doc = ""

    def write(self, root: Path, codes: dict[str, tuple[str, list[str], list[dict[str, Any]]]]) -> Path:
        d = root / self.name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        files = {}
        for code, (fname, cols, rows) in codes.items():
            with open(d / fname, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
            files[code] = fname
        if self.manifest is not None:
            m = dict(self.manifest)
            m["文件"] = files
            (d / "清单.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / f"{self.name}.说明.md").write_text(self.doc, encoding="utf-8")
        return d


def attrs_for(seg: Seg, size: int, color: str, key: Any) -> dict[str, tuple[str, str]]:
    k = h("attr", key)
    return {
        "尺寸": (str(size), "子体确认"), "颜色": (COLOR_CN[color], "子体确认"), "盆数": ("1", "子体确认"),
        "形态": (seg.form, "子体确认"), "安装方式": (INSTALL[seg.form], "子体确认"),
        "元素": (ELEMENTS[k % len(ELEMENTS)], "子体确认"), "台面形态": (TOPS[(k // 7) % 3], "子体确认"),
        "柜体材质": (BODY[(k // 11) % 4], "子体确认"), "台面材质": (TOP_MAT[(k // 13) % 4], "子体确认"),
        "台盆材质": ("陶瓷", "子体确认"),
    }


def pick_price(seg: Seg, key: Any) -> int:
    lo, hi = PRICE[seg.band]
    return lo + h("price", key) % (hi - lo)


# =====================================================================================
# H1: history package (约定 v1)
# =====================================================================================

H1_START, H1A_END, H1B_END = "2024-07", "2026-02", "2026-08"
KW_START = "2023-09"

# (segment, batch) -> (decided, hits, incomplete). Rule group 2025-01..06, test group 2025-07..09.
RULE = {
    "X": [(5, 5, 0), (5, 4, 0), (4, 1, 0), (4, 1, 0), (3, 1, 1), (3, 0, 1)],
    "Y": [(4, 3, 0), (4, 3, 0), (4, 2, 0), (4, 2, 0), (3, 1, 0), (3, 0, 0)],
    "S5": [(5, 0, 0), (4, 1, 0), (4, 0, 0), (4, 0, 0), (4, 1, 0), (4, 0, 0)],
    "S6": [(4, 0, 0), (4, 1, 0), (4, 0, 0), (4, 0, 0), (3, 1, 0), (3, 0, 0)],
    "S7": [(4, 1, 0), (4, 0, 0), (4, 0, 0), (3, 1, 0), (3, 0, 0), (3, 0, 0)],
    "S8": [(4, 0, 0), (4, 1, 0), (3, 0, 0), (3, 0, 0), (3, 1, 0), (3, 0, 0)],
    "P1a": [(2, 0, 0), (2, 1, 0), (2, 0, 0), (2, 0, 0), (1, 0, 0), (1, 0, 0)],
    "P1b": [(1, 0, 0), (1, 1, 0), (1, 0, 0), (1, 0, 0), (1, 0, 0), (0, 0, 0)],
    "P2a": [(1, 0, 0), (1, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)],
    "P2b": [(0, 0, 0), (1, 0, 0), (1, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)],
    "Z19": [(4, 1, 0), (3, 0, 0), (3, 0, 0), (3, 1, 0), (3, 0, 0), (3, 0, 0)],
}
TEST = {
    "X": [(5, 3, 0), (5, 3, 0), (10, 6, 0)],
    "Y": [(7, 4, 0), (7, 4, 0), (6, 4, 0)],
    "P1a": [(7, 2, 0), (7, 2, 0), (6, 1, 0)],
    "P1b": [(7, 2, 0), (7, 2, 0), (6, 1, 0)],
    "P2a": [(7, 1, 0), (7, 2, 0), (6, 1, 0)],
    "P2b": [(7, 2, 0), (7, 1, 0), (6, 1, 0)],
    "S5": [(15, 2, 0), (15, 2, 0), (15, 1, 0)],
    "S6": [(15, 2, 0), (15, 2, 0), (15, 1, 0)],
    "S7": [(15, 1, 0), (15, 2, 0), (15, 1, 0)],
    "S8": [(15, 2, 0), (15, 1, 0), (15, 1, 0)],
}
RULE_BATCHES = mrange("2025-01", "2025-06")
TEST_BATCHES = mrange("2025-07", "2025-09")
WATCH = {"2025-10": ["X", "Y", "S5"], "2025-11": ["X", "S6"], "2025-12": ["X", "S7"], "2026-01": ["X", "S8"],
         "2026-02": ["X", "Y"]}
# H1-B: the 2026-03 batch, 31 rising new SPUs (FLOW-14).
B2603 = {"X": (5, 2, 1), "Y": (4, 2, 0), "S5": (3, 1, 0), "S6": (3, 0, 0), "S7": (3, 1, 0), "S8": (3, 0, 0),
         "P1a": (2, 0, 0), "M": (5, 0, 2)}

DEMAND = {  # width×form -> keyword volumes per month in year0 (2023-09..2024-08), year1, year2 (2025-09..)
    (W_MID, FLOOR): [("36 inch bathroom vanity with sink", (83, 100, 120)),
                     ("36 inch freestanding vanity", (75, 90, 108)),
                     ("42 inch vanity cabinet", (50, 60, 72))],
    (W_SMALL, FLOOR): [("24 inch bathroom vanity", (100, 108, 117)), ("30 inch freestanding vanity", (50, 54, 58))],
    (W_MID, FLOAT): [("36 inch floating vanity", (100, 106, 112)), ("42 inch wall mounted vanity", (50, 53, 56))],
    (W_BIG, FLOOR): [("60 inch double vanity", (100, 94, 88)), ("48 inch freestanding vanity", (50, 47, 44))],
    (W_SMALL, FLOAT): [("24 inch floating vanity", (100, 92, 85)), ("30 inch wall mounted vanity", (50, 46, 42))],
    (W_BIG, FLOAT): [("60 inch floating double vanity", (100, 103, 106)), ("48 inch wall mounted vanity", (50, 52, 53))],
}
TAGS = {(W_MID, FLOOR): "尺寸=36;形态=freestanding", (W_SMALL, FLOOR): "尺寸=24;形态=freestanding",
        (W_MID, FLOAT): "尺寸=36;形态=floating", (W_BIG, FLOOR): "尺寸=60;形态=freestanding",
        (W_SMALL, FLOAT): "尺寸=24;形态=wall mounted", (W_BIG, FLOAT): "尺寸=60;形态=floating"}


def kw_year(m: str) -> int:
    if m <= "2024-08":
        return 0
    if m <= "2025-08":
        return 1
    return 2


class H1:
    """Builds H1-A (until 2026-02) or H1-B (until 2026-08) with optional variant tweaks."""

    def __init__(self, until: str, test: dict[str, list[tuple[int, int, int]]] | None = None,
                 rule: dict[str, list[tuple[int, int, int]]] | None = None, keep_batches: list[str] | None = None,
                 with_bullets: bool = True, with_spu_no: bool = False):
        self.until = until
        self.test = test if test is not None else TEST
        self.rule = rule if rule is not None else RULE
        self.keep_batches = keep_batches
        self.with_bullets = with_bullets
        self.with_spu_no = with_spu_no
        self.plans: list[Plan] = []
        self.old: list[Child] = []
        self.old_units: dict[tuple[str, str], int] = {}  # (asin, month) -> units
        self.old_sales: dict[tuple[str, str], int] = {}
        self.brand_i = 0
        self.special: dict[str, Any] = {}

    # ---- products ----------------------------------------------------------------------------
    def _new_child(self, segkey: str, key: str, launch: str, brand: str | None = None, title: str | None = None,
                   size: int | None = None, price: int | None = None, first_review: str | None = "auto",
                   parent: str | None = None, bullets: str | None = None, color: str | None = None,
                   asin_prefix: str = "B0", fixed_asin: str | None = None) -> Child:
        seg = SEGS[segkey]
        k = h("new", key)
        size = size or SIZES[seg.width][k % 2]
        color = color or COLORS[k % len(COLORS)]
        if brand is None:
            brand = ROTATION[self.brand_i % len(ROTATION)]
            rnd = self.brand_i // len(ROTATION)
            assert rnd < len(TEMPLATES), "more SPUs than brand × template combinations"
            self.brand_i += 1
        else:
            rnd = h("tpl", key)
        if title is None:
            tpl = TEMPLATES[rnd % len(TEMPLATES)]
            title = tpl.format(b=brand, s=size, line=LINES[h("line", key) % len(LINES)] + " " +
                               LINES[(h("line2", key) // 3) % len(LINES)], form=FORM_WORD[seg.form], c=color)
        a = fixed_asin or asin("child", key, prefix=asin_prefix)
        if first_review == "auto":
            d0 = date.fromisoformat(launch)
            first_review = (d0 + timedelta(days=12 + k % 40)).isoformat() if k % 5 else None
        c = Child(asin=a, parent=parent or asin("parent", key), brand=brand, title=title, seg=seg, size=size,
                  color=color, price=price or pick_price(seg, key), launch=launch, first_review=first_review,
                  fulfillment="FBA" if k % 4 else "FBM", variants=1 + k % 3,
                  attrs=attrs_for(seg, size, color, key), bullets=bullets, new=True)
        return c

    def build_plans(self) -> None:
        def add(segkey: str, batch: str, n: int, hits: int, inc: int, tag: str) -> None:
            for i in range(n + inc):
                key = f"{tag}-{segkey}-{batch}-{i}"
                day = 3 + h("day", key) % 24
                launch = f"{batch}-{day:02d}"
                if i < hits:
                    a = 1 + h("hitage", key) % 6
                    outcome = f"gmv@{a}" if (h("gmv", key) % 5 == 0 and SEGS[segkey].band != LOW) else f"bsr@{a}"
                elif i < n:
                    outcome = "miss"
                else:
                    outcome = f"inc@{(2, 4, 5)[h('incage', key) % 3]}"
                p = Plan(key, segkey, batch, outcome)
                p.children = [self._new_child(segkey, key, launch)]
                self.plans.append(p)

        for seg, rows in self.rule.items():
            for b, (n, hits, inc) in zip(RULE_BATCHES, rows, strict=False):
                add(seg, b, n, hits, inc, "R")
        for seg, rows in self.test.items():
            for b, (n, hits, inc) in zip(TEST_BATCHES, rows, strict=False):
                add(seg, b, n, hits, inc, "T")
        for b, segs in WATCH.items():
            for seg in segs:
                key = f"W-{seg}-{b}"
                p = Plan(key, seg, b, "watch")
                p.children = [self._new_child(seg, key, f"{b}-{5 + h('d', key) % 20:02d}")]
                self.plans.append(p)
        if self.until >= "2026-08":
            for seg, (n, hits, inc) in B2603.items():
                add(seg, "2026-03", n, hits, inc, "B")
        self._flow05()
        self._flow04()
        if self.keep_batches is not None:
            self.plans = [p for p in self.plans if p.batch in self.keep_batches]

    def _flow05(self) -> None:
        """FLOW-05: SPUs A–F in ≤30″ · 落地式 · ≥$900 (hand-written trajectories)."""
        sp = self.special
        A = Plan("A", "S9", "2025-03", "custom")
        A.children = [self._new_child("S9", "A", "2025-03-10", brand="Kingsman", price=1100,
                                      fixed_asin="B0C3HX7Y2L")]
        # ages 1..6 = 2025-03..08: BSR 120, 95, 80, 70, 60, 50 → first ≤ 50 at month 6 (2025-08)
        A.custom = {"bsr": [120, 95, 80, 70, 60, 50, 44, 47], "units": [62, 55, 50, 48, 45, 44, 40, 41]}
        B = Plan("B", "S9", "2025-02", "custom")
        B.children = [self._new_child("S9", "B", "2025-02-05", brand="Belvedere", price=1111)]
        # window 2025-02..07: best BSR 51, max sales $99,999 (90 units × $1,111.10 rounded); month 7 BSR 12
        B.custom = {"bsr": [140, 90, 51, 66, 72, 80, 12, 30], "units": [64, 70, 75, 60, 55, 50, 40, 38],
                    "sales_override": {2: 99999}}
        C = Plan("C", "S9", "2025-04", "custom")
        c1 = self._new_child("S9", "C1", "2025-04-12", brand="Mirabelle", price=1000)
        c2 = self._new_child("S9", "C2", "2025-04-12", brand="Mirabelle", price=1000, parent=c1.parent,
                             title=c1.title.replace(COLORS[h("new", "C1") % len(COLORS)], "Black"))
        C.children = [c1, c2]
        # month 2 (2025-05): $60,000 + $40,000 = $100,000
        C.custom = {"bsr": [110, 75, 90, 95, 100, 105, 110, 120], "units": [62, 60, 30, 28, 26, 25, 24, 22],
                    "units2": [20, 40, 15, 14, 13, 12, 12, 11]}
        D = Plan("D", "S9", "2025-10", "custom")
        D.children = [self._new_child("S9", "D", "2025-10-08", brand="Monterey", price=1050)]
        D.custom = {"bsr": [150, 130, 120, 110, 100, 95, 90, 88, 86, 85, 84],
                    "units": [61, 58, 50, 45, 42, 40, 38, 36, 35, 34, 33]}
        E = Plan("E", "S9", "2025-05", "custom")
        E.children = [self._new_child("S9", "E", "2025-05-15", brand="Aquadom", price=990)]
        # month 3 (2025-07) has no row in C1 or C3 → 数据不全
        E.custom = {"bsr": [130, 110, None, 100, 98, 97, 96, 95, 94, 93], "units": [63, 58, None, 45, 44, 43, 42, 41, 40, 39]}
        F = Plan("F", "S9", "2025-06", "custom")
        F.children = [self._new_child("S9", "F", "2025-06-01", brand="Blossom", price=980)]
        F.custom = {"bsr": [300, 280, 260, 250, 240, 230, 225, 220, 215], "units": [59, 50, 45, 40, 38, 36, 35, 34, 33],
                    "flat": True}
        for p in (A, B, C, D, E, F):
            self.plans.append(p)
        sp.update(A=A, B=B, C=C, D=D, E=E, F=F)

    def _flow04(self) -> None:
        """FLOW-04 / FLOW-03 boundary SPUs in 30–48″ · 悬浮式 · <$500, batch 2025-05 (all misses)."""
        mk = self._new_child
        sol_t = "SOLIDEE {s} Inch Floating Bathroom Vanity with Sink, Wall Mounted Cabinet with Soft Close Drawers, {c}"
        s1 = mk("Q3", "SOL1", "2025-05-06", brand="SOLIDEE", size=36, title=sol_t.format(s=36, c="White"),
                bullets="Solid wood frame; Soft close drawers; Ceramic basin included; Pre-drilled faucet hole",
                color="White")
        s2 = mk("Q3", "SOL2", "2025-05-09", brand="SOLIDEE", size=42, title=sol_t.format(s=42, c="Gray"),
                bullets="Wall mounted design; Quartz countertop; Two storage drawers; Easy assembly", color="Gray")
        bul = "• Waterproof MDF cabinet\n• Pre-installed soft-close hinges\n• Ceramic vessel sink with overflow"
        e1 = mk("Q3", "ECL1", "2025-05-08", brand="Eclife",
                title="Eclife 36\" Wall Mount Vanity Set, Vessel Sink and Chrome Faucet Combo, Matte White",
                size=36, bullets=bul)
        e2 = mk("Q3", "ECL2", "2025-05-18", brand="Eclife",
                title="Eclife Modern Floating Cabinet 42 in with Basin, Bathroom Storage Organizer, Light Oak",
                size=42, bullets="- Waterproof MDF cabinet - Pre-installed soft-close hinges - Ceramic vessel sink with overflow")
        wt = "Woodbridge {s} Inch Floating Vanity with Quartz Top and Integrated Sink, Fluted Front {p}, {c}"
        w1 = mk("Q3", "WB1", "2025-05-10", brand="Woodbridge", size=36, title=wt.format(s=36, p="Panel", c="White"))
        w2 = mk("Q3", "WB2", "2025-05-14", brand="Woodbridge", size=42, title=wt.format(s=42, p="Panels", c="Walnut"))
        same = {d: w1.attrs[d] for d in ("形态", "安装方式", "台面形态", "元素")}
        w2.attrs.update(same)
        pa = asin("parent", "PULUO")
        a1 = mk("Q3", "A1", "2025-05-03", brand="Puluomis", size=36, parent=pa, first_review="2025-04-25",
                fixed_asin="B0A1VNT3QZ",
                title="Puluomis 36 Inch Floating Bathroom Vanity with Resin Sink, Hidden Storage Cabinet, White")
        a2 = mk("Q3", "A2", "2025-05-20", brand="Puluomis", size=42, parent=pa, first_review="2025-05-28",
                fixed_asin="B0A2VNT3QZ", color="Gray",
                title="Puluomis 42 Inch Floating Bathroom Vanity with Resin Sink, Hidden Storage Cabinet, Gray")
        hx = mk("Q3", "HOM7", "2025-05-12", brand="HOMLUX", size=36, first_review="2025-05-05",
                title="HOMLUX 36 in Wall Mounted Vanity, Floating Bath Cabinet with Stone Resin Top, Glossy White")
        for key, kids in (("SOL1", [s1]), ("SOL2", [s2]), ("ECL1", [e1]), ("ECL2", [e2]), ("WB1", [w1]), ("WB2", [w2]),
                          ("PULUO", [a1, a2]), ("HOM7", [hx])):
            p = Plan(key, "Q3", "2025-05", "miss")
            p.children = kids
            self.plans.append(p)
        self.special.update(SOL=(s1, s2), ECL=(e1, e2), WB=(w1, w2), PULUO=(a1, a2), HOM7=hx)

    # ---- trajectories ---------------------------------------------------------------------
    def trajectory(self, p: Plan) -> list[dict[str, Any]]:
        """Monthly child rows (month, child, units, sales, bsr, parent_units) from launch to until."""
        rows = []
        launch_m = p.batch
        months = mrange(launch_m, self.until)
        if p.outcome == "custom":
            cu = p.custom
            for i, m in enumerate(months):
                bsr = cu["bsr"][i] if i < len(cu["bsr"]) else 80 + h("b", p.key, m) % 100
                units = cu["units"][i] if i < len(cu["units"]) else 30 + h("u", p.key, m) % 20
                if bsr is None:
                    continue
                kid = p.children[0]
                sales = units * kid.price
                if "sales_override" in cu and i in cu["sales_override"]:
                    sales = cu["sales_override"][i]
                pu = units
                if "units2" in cu:
                    u2 = cu["units2"][i] if i < len(cu["units2"]) else 10
                    k2 = p.children[1]
                    if i == 1:  # C: month 2 sales $60,000 + $40,000
                        sales, s2 = 60000, 40000
                    else:
                        s2 = u2 * k2.price
                    pu = units + u2
                    rows.append({"month": m, "child": k2, "units": u2, "sales": s2, "bsr": bsr + 15, "pu": pu})
                rows.append({"month": m, "child": kid, "units": units, "sales": sales, "bsr": bsr, "pu": pu})
            return rows
        hit_kind, hit_age = None, None
        if "@" in p.outcome:
            hit_kind, a = p.outcome.split("@")
            hit_age = int(a)
        for i, m in enumerate(months):
            age = i + 1
            if hit_kind == "inc" and age == hit_age:
                continue
            for kid in p.children:
                k = h("traj", kid.asin, m)
                cap = max(1, math.floor(94000 / kid.price))
                if age == p.rise_age:
                    units = min(60 + k % 6, cap)
                    units = max(units, 60)
                elif age < p.rise_age:
                    units = 30 + k % 25
                else:
                    units = 18 + k % 30
                bsr = 60 + k % 240
                sales = units * kid.price
                if hit_kind == "bsr" and age == hit_age:
                    bsr = 18 + k % 28
                if hit_kind == "gmv" and age == hit_age:
                    units = math.ceil(100000 / kid.price) + k % 5
                    sales = units * kid.price
                rows.append({"month": m, "child": kid, "units": units, "sales": min(sales, 94999) if not (
                    hit_kind == "gmv" and age == hit_age) else sales, "bsr": bsr, "pu": units})
        return rows

    # ---- old products -------------------------------------------------------------------------
    OLD_PLAN = {  # segkey -> (children, base units, price spec)
        "X": (99, 38), "Y": (80, 40), "S5": (60, 42), "S6": (50, 42), "S7": (50, 42), "S8": (50, 42),
        "P1a": (30, 95), "P1b": (20, 45), "P2a": (20, 90), "P2b": (30, 50), "Z19": (15, 40), "S9": (10, 40),
        "S10": (15, 40), "Q3": (10, 40), "M": (40, 250),
    }

    def build_old(self) -> None:
        bi = 0
        for segkey, (n, base) in self.OLD_PLAN.items():
            seg = SEGS[segkey]
            for i in range(n):
                key = f"OLD-{segkey}-{i}"
                k = h("old", key)
                brand = OLD_BRANDS[bi % len(OLD_BRANDS)]
                bi += 1
                size = SIZES[seg.width][k % 2]
                color = COLORS[k % len(COLORS)]
                y = 2019 + k % 5
                launch = f"{y}-{1 + k % 12:02d}-{1 + k % 27:02d}"
                tpl = TEMPLATES[k % len(TEMPLATES)]
                title = tpl.format(b=brand, s=size, line=f"Classic {LINES[k % len(LINES)]} {i}",
                                   form=FORM_WORD[seg.form], c=color)
                d0 = date.fromisoformat(launch)
                c = Child(asin=asin("oldchild", key), parent=asin("oldparent", key), brand=brand, title=title, seg=seg,
                          size=size, color=color, price=pick_price(seg, key), launch=launch,
                          first_review=(d0 + timedelta(days=15 + k % 50)).isoformat(),
                          fulfillment="FBA" if k % 3 else "FBM", variants=1 + k % 4,
                          attrs=attrs_for(seg, size, color, key))
                c.base = base  # type: ignore[attr-defined]
                c.key = key  # type: ignore[attr-defined]
                self.old.append(c)
        # unknown 形态 (FLOW-03: 5 children; one of them in 30–48″ · 未知 · $500–900)
        for i, (w, band) in enumerate([(W_MID, MIDP), (W_MID, LOW), (W_MID, MIDP), (W_SMALL, LOW), (W_SMALL, MIDP)]):
            key = f"OLD-UNK-{i}"
            seg = Seg(w, "未知", band)
            size = SIZES[w][i % 2]
            c = Child(asin=asin("oldchild", key), parent=asin("oldparent", key), brand="Northlake",
                      title=f"Northlake {size} Inch Bathroom Vanity Base Cabinet Model {LINES[i + 20]}, White",
                      seg=seg, size=size, color="White", price=PRICE[band][0] + 60, launch=f"2022-0{i + 1}-15",
                      first_review=f"2022-0{i + 1}-28", fulfillment="FBA", variants=1,
                      attrs=attrs_for(SEGS["X"], size, "White", key))
            c.attrs["形态"] = ("未知", "信息不足")
            c.base, c.key = 30, key  # type: ignore[attr-defined]
            self.old.append(c)
        X_old = [c for c in self.old if c.seg == SEGS["X"]]
        # FLOW-07: one X child with 柜体材质 only as parent candidate, one with colour missing
        X_old[5].attrs["柜体材质"] = ("实木", "父体候选")
        X_old[6].attrs["颜色"] = ("", "信息不足")
        # Parent-level review target: parent PX has an X child (best seller) and a Y child
        Y_old = [c for c in self.old if c.seg == SEGS["Y"]]
        Y_old[0].parent = X_old[2].parent
        Y_old[0].brand = X_old[2].brand
        Y_old[0].launch = (date.fromisoformat(X_old[2].launch) + timedelta(days=20)).isoformat()
        Y_old[0].first_review = (date.fromisoformat(Y_old[0].launch) + timedelta(days=15)).isoformat()
        self.special["PX"] = (X_old[2], Y_old[0])
        # FLOW-03: family spans 181 and 180 days (M segment), first review 8 days early ×2 (M), parent change ×1
        M_old = [c for c in self.old if c.seg == SEGS["M"]]
        M_old[0].launch, M_old[1].launch = "2022-03-01", "2022-08-29"  # 181 days
        M_old[1].parent, M_old[1].brand = M_old[0].parent, M_old[0].brand
        M_old[2].launch, M_old[3].launch = "2021-05-01", "2021-10-28"  # 180 days
        M_old[3].parent, M_old[3].brand = M_old[2].parent, M_old[2].brand
        for c in (M_old[0], M_old[1], M_old[2], M_old[3]):
            c.first_review = (date.fromisoformat(c.launch) + timedelta(days=20)).isoformat()
        M_old[4].first_review = (date.fromisoformat(M_old[4].launch) - timedelta(days=8)).isoformat()
        M_old[5].first_review = (date.fromisoformat(M_old[5].launch) - timedelta(days=8)).isoformat()
        S6_old = [c for c in self.old if c.seg == SEGS["S6"]]
        self.special["parent_change"] = (S6_old[3], asin("oldparent", "MOVED"))
        self.special["M_old"] = M_old

    def old_units_for(self, c: Child, m: str) -> int | None:
        """Base monthly units of an old child (None = not in C1 that month)."""
        key = c.key  # type: ignore[attr-defined]
        base = c.base  # type: ignore[attr-defined]
        segkey = next((k for k, s in SEGS.items() if s == c.seg), "UNK")
        idx = int(key.rsplit("-", 1)[1]) if key.rsplit("-", 1)[1].isdigit() else 0
        # trend design (FLOW-09): P1a and P2b add children between 2025-01 and 2025-08
        if segkey in ("P1a", "P2b"):
            n_total = self.OLD_PLAN[segkey][0]
            start = 15
            if m < "2025-01":
                active = start
            elif m <= "2025-08":
                active = start + round((n_total - start) * (mrange("2025-01", m).__len__()) / 8)
            else:
                active = n_total
            if idx >= active:
                return None
        units = base + (h("ou", key, m) % 5) - 2
        # low-score design: S7/S8 low-rated sellers are big before 2025-05, small afterwards
        if segkey in ("S7", "S8") and idx < 3:
            units = 160 if m < "2025-05" else 8
        if segkey in ("P2a", "P1b") and idx < 3:
            units = 160
        return max(units, 1)

    # ---- assemble -----------------------------------------------------------------------------
    def assemble(self, name: str) -> Package:
        self.build_plans()
        self.build_old()
        pkg = Package(name)
        months = mrange(H1_START, self.until)
        c1: dict[tuple[str, str], dict[str, Any]] = {}

        def c1row(c: Child, m: str, units: int, sales: int, pu: int, bsr: int, parent: str | None = None) -> None:
            c1[(c.asin, m)] = {
                "月份": ym(m), "子ASIN": c.asin, "当月父ASIN": parent or c.parent, "品牌": c.brand,
                "卖家": f"{c.brand} Store", "标题": c.title, "上架日期": c.launch, "子体月销量": units,
                "子体月销售额": sales, "父体月销量": pu, "小类BSR": bsr, "类目节点": "6810202011",
                "配送方式": c.fulfillment, "变体数": c.variants, "首次评分日期": c.first_review or "",
                "当月价格": round(sales / units) if units else "", "当月评分": "",
                "五点描述": c.bullets if self.with_bullets and c.bullets else "",
            }
        # new products: C2, C3, C1 in the rising month
        traj: dict[str, list[dict[str, Any]]] = {}
        for p in self.plans:
            rows = self.trajectory(p)
            traj[p.key] = rows
            for c in p.children:
                pkg.c2.append({"子ASIN": c.asin, "父ASIN": c.parent, "品牌": c.brand, "标题": c.title,
                               "上架日期": c.launch, "配送方式": c.fulfillment, "变体数": c.variants,
                               "首次评分日期": c.first_review or "",
                               "五点描述": c.bullets if self.with_bullets and c.bullets else ""})
            for r in rows:
                if r["month"] > self.until:
                    continue
                pkg.c3.append({"月份": ym(r["month"]), "子ASIN": r["child"].asin, "子体月销量": r["units"],
                               "子体月销售额": r["sales"], "小类BSR": r["bsr"], "父体月销量": r["pu"]})
                if r["pu"] >= 60:
                    c1row(r["child"], r["month"], r["units"], r["sales"], r["pu"], r["bsr"])
        # old products
        pc_child, pc_new_parent = self.special["parent_change"]
        for c in self.old:
            for m in months:
                u = self.old_units_for(c, m)
                if u is None:
                    continue
                self.old_units[(c.asin, m)] = u
                self.old_sales[(c.asin, m)] = u * c.price
        self._fit_targets(pkg, c1)
        for c in self.old:
            for m in months:
                if (c.asin, m) not in self.old_units:
                    continue
                u, s = self.old_units[(c.asin, m)], self.old_sales[(c.asin, m)]
                parent = pc_new_parent if (c is pc_child and m >= "2025-11") else None
                pu = u + (self.old_units.get((self.special["PX"][1].asin, m), 0) if c is self.special["PX"][0] else 0)
                if c is self.special["PX"][1]:
                    pu = u + self.old_units.get((self.special["PX"][0].asin, m), 0)
                c1row(c, m, u, s, pu, 300 + h("obsr", c.asin, m) % 2000, parent=parent)
        # snapshot-ish columns, coupons and "bought" labels on the latest month
        last = ym(self.until)
        olds_sorted = sorted(self.old, key=lambda c: c.asin)
        labelled = 0
        for c in olds_sorted:
            r = c1.get((c.asin, self.until))
            if r is None:
                continue
            r["当月评分"] = f"{3.9 + (h('rt', c.asin) % 11) / 10:.1f}"
            if h("cp", c.asin) % 4 == 0:
                r["优惠券"] = 10 + h("cp2", c.asin) % 4 * 10
            if labelled < 30 and r["子体月销量"] >= 50 and c.seg.form != "未知":
                r["过去一个月购买"] = "50+ bought in past month"
                labelled += 1
        below = [c for c in olds_sorted if c.seg == SEGS["S5"]][:2]
        for c in below:
            r = c1[(c.asin, self.until)]
            r["过去一个月购买"] = "100+ bought in past month"  # units are ~42 → below the label's lower bound
        rows = [c1[k] for k in sorted(c1, key=lambda k: (k[1], k[0]))]
        # FLOW-03: two duplicated primary keys
        rows.append(dict(rows[10]))
        rows.append(dict(rows[500]))
        pkg.c1 = rows
        self.special["dups"] = (rows[10]["子ASIN"], rows[500]["子ASIN"])
        self.special["last"] = last
        pkg.c4 = self._c4()
        pkg.c5 = self._c5()
        pkg.c6 = self._c6(c1)
        pkg.c7 = [{"立项名称": "36寸落地双门实木款", "立项日期": "2025-11-20", "关联细分或属性": "30–48″ · 落地式 · $500–900"},
                  {"立项名称": "24寸悬浮小户型款", "立项日期": "2025-12-15", "关联细分或属性": "≤30″ · 悬浮式 · <$500"}]
        pkg.manifest = {"类型": "历史", "约定版本": "v1", "品类": "浴室柜", "站点": "US", "类目节点": "6810202011",
                        "覆盖月份": {"起": H1_START, "止": self.until},
                        "新品上架窗口": {"起": "2025-01-01", "止": f"{self.until}-28"}}
        self.traj = traj
        self.c1map = c1
        return pkg

    def _fit_targets(self, pkg: Package, c1: dict[tuple[str, str], dict[str, Any]]) -> None:
        """Set old products' 2025-09..2026-02 figures so the FLOW-07 targets hold exactly."""
        if self.until < "2026-02":
            return
        Xseg, last = SEGS["X"], "2026-02"
        X_old = [c for c in self.old if c.seg == Xseg]
        new_x = [(k, r) for k, r in c1.items() if k[1] == last and r["子ASIN"] in self._new_asins_of("X")]
        nu = sum(r["子体月销量"] for _, r in new_x)
        ns = sum(r["子体月销售额"] for _, r in new_x)
        assert len(X_old) + len(new_x) == 100, (len(X_old), len(new_x))
        # units: two low-rated best sellers 170 + 150, 23 children at 60, the rest share what is left
        units = {X_old[0].asin: 170, X_old[1].asin: 150}
        for c in X_old[2:25]:
            units[c.asin] = 60
        rest = X_old[25:]
        remaining = 4000 - nu - 320 - 23 * 60
        q, r = divmod(remaining, len(rest))
        for i, c in enumerate(rest):
            units[c.asin] = q + (1 if i < r else 0)
        assert max(units[c.asin] for c in rest) < 60
        # sales: $660 average, exact total $2,640,000
        target = 2640000 - ns
        tot_u = sum(units.values())
        sales = {a: units[a] * 660 + ((h("xp", a) % 81) - 40) * units[a] for a in units}
        diff = target - sum(sales.values())
        for a in sorted(sales):
            share = diff * units[a] // tot_u
            sales[a] += share
        sales[X_old[30].asin] += target - sum(sales.values())
        for a in units:
            p = sales[a] / units[a]
            assert 500 <= p < 900, (a, p)
            self.old_units[(a, last)] = units[a]
            self.old_sales[(a, last)] = sales[a]
        # width 30–48″ price at 2026-02 = $600: adjust Y's old children (band <$500)
        mid = [c for c in self.old if c.seg.width == W_MID]
        y_old = [c for c in mid if c.seg == SEGS["Y"]]
        new_mid = [r for (a, m), r in c1.items() if m == last and self._width_of_new(a) == W_MID]
        mid_u = sum(self.old_units[(c.asin, last)] for c in mid if (c.asin, last) in self.old_units)
        mid_u += sum(r["子体月销量"] for r in new_mid)
        mid_s_wo_y = sum(self.old_sales[(c.asin, last)] for c in mid if c not in y_old and (c.asin, last) in self.old_units)
        mid_s_wo_y += sum(r["子体月销售额"] for r in new_mid)
        need_y = 600 * mid_u - mid_s_wo_y
        y_units = sum(self.old_units[(c.asin, last)] for c in y_old)
        assert 300 * y_units < need_y < 500 * y_units, need_y / y_units
        avg = need_y / y_units
        for c in y_old:
            self.old_sales[(c.asin, last)] = int(self.old_units[(c.asin, last)] * avg)
        y_old_sorted = sorted(y_old, key=lambda c: c.asin)
        self.old_sales[(y_old_sorted[0].asin, last)] += need_y - sum(self.old_sales[(c.asin, last)] for c in y_old)
        for c in y_old:
            p = self.old_sales[(c.asin, last)] / self.old_units[(c.asin, last)]
            assert 300 <= p < 500, p
        # X share: 2025-09..11 = 10.0 %, 2025-12..2026-02 = 12.0 % of all units (filler: M old children)
        def xunits(ms: list[str]) -> int:
            t = sum(self.old_units.get((c.asin, m), 0) for c in X_old for m in ms)
            t += sum(r["子体月销量"] for (a, m), r in c1.items() if m in ms and a in self._new_asins_of("X"))
            return t

        w1, w2 = mrange("2025-09", "2025-11"), mrange("2025-12", "2026-02")
        # make X(12..02) divisible by 3 (12 % share) by nudging one X child in 2025-12
        nudge = (-xunits(w2)) % 3
        self.old_units[(X_old[40].asin, "2025-12")] += nudge
        self.old_sales[(X_old[40].asin, "2025-12")] = self.old_units[(X_old[40].asin, "2025-12")] * X_old[40].price
        M_old = [c for c in self.old if c.seg == SEGS["M"]]
        for ms, share in ((w1, 10), (w2, 12)):
            total_target = xunits(ms) * 100 // share
            assert xunits(ms) * 100 % share == 0
            others = sum(u for (a, m), u in self.old_units.items() if m in ms and not any(a == c.asin for c in M_old))
            others += sum(r["子体月销量"] for (a, m), r in c1.items() if m in ms)
            m_total = total_target - others
            per = m_total // (len(ms) * len(M_old))
            assert per > 50, per
            left = m_total
            cells = [(c, m) for m in ms for c in M_old]
            for i, (c, m) in enumerate(cells):
                u = per if i < len(cells) - 1 else left
                left -= u
                self.old_units[(c.asin, m)] = u
                self.old_sales[(c.asin, m)] = u * c.price
        self.special["targets"] = {"x_units_w1": xunits(w1), "x_units_w2": xunits(w2)}

    def _new_asins_of(self, segkey: str) -> set[str]:
        return {c.asin for p in self.plans if p.segkey == segkey for c in p.children}

    def _width_of_new(self, a: str) -> str | None:
        for p in self.plans:
            for c in p.children:
                if c.asin == a:
                    return c.seg.width
        return None

    def _c4(self) -> list[dict[str, Any]]:
        out = []
        kids = [c for p in self.plans for c in p.children] + self.old
        for c in kids:
            row = {"子ASIN": c.asin}
            for d in DIMS:
                v, s = c.attrs.get(d, ("", "信息不足"))
                row[d], row[f"{d}证据状态"] = v, s
            out.append(row)
        return out

    def _c5(self) -> list[dict[str, Any]]:
        out = []
        for combo, kws in DEMAND.items():
            for kw, vols in kws:
                for m in mrange(KW_START, self.until):
                    if combo == (W_BIG, FLOAT) and m == "2024-12":
                        continue  # FLOW-07: this segment lacks 2024-12
                    out.append({"关键词": kw, "月份": ym(m), "月搜索量": vols[kw_year(m)], "关键词属性标签": TAGS[combo]})
        for m in mrange(KW_START, self.until):
            out.append({"关键词": "bathroom vanity", "月份": ym(m), "月搜索量": 5000 + h("g", m) % 400,
                        "关键词属性标签": "通用"})
        return out

    def _c6(self, c1: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
        """Reviews. X totals at T=2026-03: 200 reviews dated before 2026-03-01, 25 structural (one parent level)."""
        out: list[dict[str, Any]] = []
        n = [0]

        def rev(a: str, level: str, d: str, stars: int, structural: bool, code: str) -> None:
            n[0] += 1
            out.append({"评论ID": f"R{h('rid', a, n[0]) % 10**10:010d}", "ASIN": a, "归属级别": level, "评论日期": d,
                        "星级": stars, "痛点事件代码": code, "是否结构类痛点": "是" if structural else "否",
                        "标注版本": "v3"})

        X_old = [c for c in self.old if c.seg == SEGS["X"]]
        px_child, _py = self.special["PX"]
        # two low-rated best sellers (X_old[0], X_old[1]): 4 reviews each, avg 3.25, Oct 2025–Feb 2026
        for c in X_old[:2]:
            for j, (d, s) in enumerate([("2025-10-12", 3), ("2025-11-20", 3), ("2025-12-18", 4), ("2026-01-22", 3)]):
                rev(c.asin, "子体", d, s, j == 0, "S03" if j == 0 else "N12")
        # 191 more child-level X reviews + 1 parent-level review on PX = 200 (with the 8 above)
        others = X_old[2:]
        struct_left = 25 - 2
        made = 8
        i = 0
        while made < 199:
            c = others[i % len(others)]
            i += 1
            d = date(2024, 9, 1) + timedelta(days=(h("xd", c.asin, i) % 540))
            structural = struct_left > 0 and i % 8 == 0
            if structural:
                struct_left -= 1
            rev(c.asin, "子体", d.isoformat(), 4 + (h("xs", i) % 2), structural,
                "S01" if structural else "N03")
            made += 1
        while struct_left > 0:  # not reached with the numbers above; kept as a guard
            raise AssertionError("structural count")
        rev(px_child.parent, "父体", "2025-06-18", 5, False, "N01")
        rev(X_old[3].asin, "子体", "2026-03-01", 2, True, "S03")  # on T's first day: excluded at T = 2026-03
        # other segments: background reviews; S7/S8 low-rated best sellers (rule months, structural),
        # P2a/P1b low-rated best sellers (test months)
        for c in self.old:
            if c.seg == SEGS["X"]:
                continue
            segkey = next((k for k, s in SEGS.items() if s == c.seg), "UNK")
            idx = int(c.key.rsplit("-", 1)[1])  # type: ignore[attr-defined]
            if segkey in ("S7", "S8") and idx < 3:
                for j in range(4):
                    rev(c.asin, "子体", f"2024-{9 + j:02d}-1{j}", 2, True, "S02")
                continue
            if segkey in ("P2a", "P1b") and idx < 3:
                for j in range(4):
                    rev(c.asin, "子体", f"2025-0{3 + j}-1{j}", 2, False, "N07")
                continue
            for j in range(h("nr", c.asin) % 3 + 1):
                d = date(2024, 8, 1) + timedelta(days=h("od", c.asin, j) % 560)
                rev(c.asin, "子体", d.isoformat(), 4 + h("os", c.asin, j) % 2, h("ost", c.asin, j) % 9 == 0,
                    "S05" if h("ost", c.asin, j) % 9 == 0 else "N05")
        for p in self.plans:
            if p.segkey in ("X",):
                continue
            c = p.children[0]
            d = date.fromisoformat(c.launch) + timedelta(days=30)
            if d.isoformat()[:7] <= self.until:
                rev(c.asin, "子体", d.isoformat(), 4 + h("ns", c.asin) % 2, False, "N02")
        return out


def write_h1(pkg: Package, root: Path, drop_bullets: bool = False, spu_no: dict[str, str] | None = None,
             c1_rows: list[dict[str, Any]] | None = None, extra_cols: list[str] | None = None) -> Path:
    c1_cols = [c for c in C1_COLS if not (drop_bullets and c == "五点描述")] + (extra_cols or [])
    c2_cols = [c for c in C2_COLS if not (drop_bullets and c == "五点描述")]
    if spu_no is not None:
        c1_cols.append("SPU编号")
        c2_cols.append("SPU编号")
        for r in pkg.c1:
            r["SPU编号"] = spu_no.get(r["子ASIN"], "")
        for r in pkg.c2:
            r["SPU编号"] = spu_no.get(r["子ASIN"], "")
    files = {
        "C1": ("C1_月度类目商品.csv", c1_cols, c1_rows if c1_rows is not None else pkg.c1),
        "C2": ("C2_新品清单.csv", c2_cols, pkg.c2),
        "C3": ("C3_新品月度轨迹.csv", C3_COLS, pkg.c3),
        "C4": ("C4_属性标签.csv", C4_COLS, pkg.c4),
        "C5": ("C5_关键词月度.csv", C5_COLS, pkg.c5),
        "C6": ("C6_评论痛点.csv", C6_COLS, pkg.c6),
        "C7": ("C7_自家立项.csv", C7_COLS, pkg.c7),
    }
    return pkg.write(root, files)


# =====================================================================================
# X1: cross-section package (约定 v1.1)
# =====================================================================================

X_OBS = mrange("2026-06", "2026-09")
X_SEGS = {"XA": SEGS["X"], "XB": SEGS["Y"], "XC": SEGS["S5"], "XD": SEGS["S7"], "XE": SEGS["P2a"]}
# batch -> segment -> (n, hits) ; hits reach the success line in exactly one observed new-product month
X_BATCH = {
    "2026-01": {"XA": (4, 2), "XB": (4, 0), "XC": (4, 0), "XD": (4, 0), "XE": (4, 0)},
    "2026-02": {"XA": (4, 2), "XB": (4, 1), "XC": (4, 0), "XD": (4, 0), "XE": (4, 0)},
    "2026-03": {"XA": (5, 3), "XB": (4, 0), "XC": (4, 1), "XD": (4, 0), "XE": (4, 0)},
    "2026-04": {"XA": (5, 3), "XB": (5, 1), "XC": (5, 0), "XD": (5, 1), "XE": (5, 0), "XG": (2, 0)},
    "2026-05": {"XA": (5, 2), "XB": (5, 0), "XC": (5, 1), "XD": (5, 0), "XE": (5, 1)},
    "2026-06": {"XA": (5, 2), "XB": (5, 1), "XC": (5, 0), "XD": (5, 0), "XE": (5, 0)},
    "2026-07": {"XA": (8, 4), "XB": (7, 1), "XC": (7, 1), "XD": (7, 0), "XE": (7, 1)},
    "2026-08": {"XA": (7, 3), "XB": (7, 1), "XC": (7, 0), "XD": (7, 1), "XE": (7, 0)},
    "2026-09": {"XA": (7, 3), "XB": (7, 0), "XC": (7, 1), "XD": (7, 0), "XE": (7, 0)},
}
X_MAP = {"XA": "X", "XB": "Y", "XC": "S5", "XD": "S7", "XE": "P2a", "XF": "S10", "XG": "M"}
X_OLD = {"XA": 6, "XB": 6, "XC": 6, "XD": 6, "XE": 6, "XF": 10}  # 40 old products
X_OLD_UNITS = {"XA": 40, "XB": 45, "XC": 120, "XD": 50, "XE": 55, "XF": 50}  # XC top on 单位 ASIN 贡献
X_OLD_PRICE = {"XA": 640, "XB": 380, "XC": 330, "XD": 860, "XE": 420, "XF": 1200}  # XE top on 属性溢价


class X1:
    def __init__(self, with_old: bool = True):
        self.with_old = with_old
        self.special: dict[str, Any] = {}

    def assemble(self, name: str) -> Package:
        pkg = Package(name)
        s1: dict[tuple[str, str], dict[str, Any]] = {}
        h1 = H1("2026-09")  # reuse child factory
        new_children: list[tuple[Child, str, list[dict[str, Any]]]] = []

        def row1(c: Child, m: str, units: int, sales: int, bsr: int) -> None:
            s1[(c.asin, m)] = {"月份": ym(m), "子ASIN": c.asin, "当月父ASIN": c.parent, "品牌": c.brand,
                               "卖家": f"{c.brand} Store", "标题": c.title, "上架日期": c.launch, "子体月销量": units,
                               "子体月销售额": sales, "父体月销量": units, "小类BSR": bsr, "类目节点": "6810202011",
                               "配送方式": c.fulfillment, "变体数": c.variants, "首次评分日期": c.first_review or "",
                               "当月价格": round(sales / units) if units else ""}
        for b, segs in X_BATCH.items():
            for xs, (n, hits) in segs.items():
                segkey = X_MAP[xs]
                for i in range(n):
                    key = f"X1-{xs}-{b}-{i}"
                    special = None
                    if (b, xs, i) == ("2026-03", "XA", 0):
                        special = "P"
                    elif (b, xs, i) == ("2026-01", "XB", 3):
                        special = "Q"
                    elif (b, xs, i) == ("2026-08", "XD", 6):
                        special = "R"
                    launch = f"{b}-{4 + h('xd', key) % 20:02d}"
                    c = h1._new_child(segkey, key, launch, price=700 if special == "P" else None)
                    obs = [m for m in X_OBS if m >= b]
                    rows = []
                    hit_m = None
                    if i < hits and special != "Q" and special != "R":
                        cand = [m for m in obs if 1 <= len(mrange(b, m)) <= 6]
                        hit_m = cand[h("xh", key) % len(cand)]
                    if special == "P":
                        hit_m = "2026-07"
                    for m in obs:
                        age = len(mrange(b, m))
                        k = h("xt", key, m)
                        units = 60 + k % 20 if m == obs[0] else 25 + k % 30
                        bsr = 70 + k % 200
                        sales = min(units * c.price, 94000)
                        if hit_m == m:
                            if special == "P":
                                units, sales, bsr = 143, 100000, 75  # SPU sales exactly $100,000 at age 5
                            else:
                                bsr = 20 + k % 25
                        rows.append({"month": m, "units": units, "sales": sales, "bsr": bsr, "age": age})
                    new_children.append((c, b, rows))
                    if special:
                        self.special[special] = (c, b, hit_m)
        for c, _b, rows in new_children:
            pkg.c2.append({"子ASIN": c.asin, "父ASIN": c.parent, "品牌": c.brand, "标题": c.title, "上架日期": c.launch,
                           "配送方式": c.fulfillment, "变体数": c.variants, "首次评分日期": c.first_review or ""})
            for r in rows:
                pkg.c3.append({"月份": ym(r["month"]), "子ASIN": c.asin, "子体月销量": r["units"],
                               "子体月销售额": r["sales"], "小类BSR": r["bsr"], "父体月销量": r["units"]})
                if r["units"] >= 60:
                    row1(c, r["month"], r["units"], r["sales"], r["bsr"])
        olds: list[Child] = []
        if self.with_old:
            for xs, n in X_OLD.items():
                segkey = X_MAP[xs]
                for i in range(n):
                    key = f"X1-OLD-{xs}-{i}"
                    launch = "2025-11-14" if (xs, i) == ("XA", 0) else f"202{3 + i % 2}-0{1 + i % 8}-1{i % 9}"
                    c = h1._new_child(segkey, key, launch, price=X_OLD_PRICE[xs] + (i % 3) * 10,
                                      brand=OLD_BRANDS[i % len(OLD_BRANDS)])
                    olds.append(c)
                    if (xs, i) == ("XA", 0):
                        self.special["S"] = c
                    for m in X_OBS:
                        u = X_OLD_UNITS[xs] + h("xo", key, m) % 5
                        row1(c, m, u, u * c.price, 200 + h("xob", key, m) % 900)
        pkg.c1 = [s1[k] for k in sorted(s1, key=lambda k: (k[1], k[0]))]
        kids = [c for c, _b, _r in new_children] + olds
        pkg.c4 = []
        for c in kids:
            row = {"子ASIN": c.asin}
            for d in DIMS:
                v, s = c.attrs[d]
                row[d], row[f"{d}证据状态"] = v, s
            pkg.c4.append(row)
        # keywords: observation months plus 2025-06..09 for two width×form combos only (others lack the prior year)
        for combo in [(W_MID, FLOOR), (W_SMALL, FLOOR), (W_BIG, FLOOR), (W_SMALL, FLOAT)]:
            for kw, vols in DEMAND[combo]:
                months = list(X_OBS)
                if combo in [(W_MID, FLOOR), (W_SMALL, FLOOR)]:
                    months = mrange("2025-06", "2025-09") + months
                for m in months:
                    out = vols[1] if m < "2026-01" else vols[2]
                    pkg.c5.append({"关键词": kw, "月份": ym(m), "月搜索量": out, "关键词属性标签": TAGS[combo]})
        pkg.manifest = {"类型": "截面", "约定版本": "v1.1", "品类": "浴室柜", "站点": "US", "类目节点": "6810202011",
                        "观察月份": {"起": X_OBS[0], "止": X_OBS[-1]}}
        self.new_children = new_children
        self.olds = olds
        return pkg


def write_x1(pkg: Package, root: Path) -> Path:
    files = {
        "S1": ("S1_观察期月度类目商品.csv", [c for c in C1_COLS if c not in ("过去一个月购买", "当月评分", "五点描述", "优惠券")], pkg.c1),
        "S2": ("S2_新品期起量新品.csv", [c for c in C2_COLS if c != "五点描述"], pkg.c2),
        "S3": ("S3_新品观察期月度数据.csv", C3_COLS, pkg.c3),
        "C4": ("C4_属性标签.csv", C4_COLS, pkg.c4),
        "C5": ("C5_关键词月度.csv", C5_COLS, pkg.c5),
    }
    return pkg.write(root, files)


# =====================================================================================
# variants, explanation documents and entry point
# =====================================================================================

TEST_SPARSE = {  # 有效细分只有 4 个: X, Y, S7, S8 keep ≥ 20; others below 20 in the test group
    "X": TEST["X"], "Y": TEST["Y"], "S7": TEST["S7"], "S8": TEST["S8"],
    "P1a": [(2, 1, 0), (2, 0, 0), (2, 0, 0)], "P1b": [(2, 0, 0), (2, 1, 0), (2, 0, 0)],
    "P2a": [(2, 0, 0), (2, 0, 0), (2, 1, 0)], "P2b": [(2, 1, 0), (2, 0, 0), (2, 0, 0)],
    "S5": [(5, 1, 0), (5, 0, 0), (5, 0, 0)], "S6": [(5, 0, 0), (5, 1, 0), (5, 0, 0)],
}
TEST_FLAT = {**TEST, "X": [(5, 1, 0), (5, 0, 0), (10, 1, 0)], "Y": [(7, 1, 0), (7, 0, 0), (6, 1, 0)]}
TEST_19 = {**TEST, "P2b": [(7, 2, 0), (7, 1, 0), (5, 1, 0)]}


H1A_DOC = """# H1-A 样例包说明（历史数据包 · 约定 v1）

数据至 2026-02，本月排序月 T = 2026-03（DEC-005）。品类配置为浴室柜模板 v1：BSR ≤ 50、SPU 月销售额 ≥ $100,000、
判定窗口 6 个月、起量门槛父体月销 ≥ 60 件、回测前 2/3 定规则后 1/3 检验、细分 = 宽度档 × 形态 × 价格带。
以下期望值都是本样例的设计输入，按已确认规则手算得出，不来自被测程序。

## 文件
C1 2024-07 至 2026-02（老品每月一行；新品只在父体月销 ≥ 60 件的月份出现，另有 2 行完全重复的主键）；
C2 新品清单（上架 2025-01 起，另含一个未起量新品 F）；C3 新品月度轨迹（上架当月至 2026-02，E 缺 2025-07）；
C4 属性标签；C5 关键词 2023-09 至 2026-02（≥48″·悬浮式 两个词缺 2024-12）；C6 评论痛点；C7 两条自家立项。
C1 带约定外字段“优惠券”。

## 批次与成败（FLOW-05、FLOW-09）
已判定批次 = 窗口已结束的 2025-01 至 2025-09（9 个；2025-09 的第 6 个月是 2026-02）。前 2/3 定规则：
9 × 1/3 = 3 → 检验组 2025-07 至 2025-09，定规则组 2025-01 至 2025-06。

| 细分 | 定规则组 判定数（命中） | 检验组 判定数（命中） | 全部已判定 |
| :--- | :--- | :--- | :--- |
| X 30–48″ · 落地式 · $500–900 | 24（12），另 2 个数据不全 | 20（12） | 44 |
| Y 30–48″ · 落地式 · <$500 | 22（11） | 20（12） | 42 |
| ≤30″ · 落地式 · <$500 | 25（2） | 45（5） | 70 |
| 30–48″ · 悬浮式 · $500–900 | 22（2） | 45（5） | 67 |
| ≥48″ · 落地式 · $500–900 | 21（2） | 45（4） | 66 |
| ≤30″ · 悬浮式 · $500–900 | 20（2） | 45（4） | 65 |
| ≥48″ · 落地式 · <$500 | 10（1） | 20（5） | 30 |
| ≥48″ · 落地式 · ≥$900 | 5（1） | 20（5） | 25 |
| ≤30″ · 悬浮式 · <$500 | 2（0） | 20（4） | 22 |
| ≤30″ · 悬浮式 · ≥$900 | 2（0） | 20（4） | 22 |
| ≤30″ · 落地式 · $500–900 | 19（2） | 0 | 19（样本不足） |
| 30–48″ · 悬浮式 · <$500 | 8（0；只确认“标题主干相同”后 7，三条都确认后 5） | 0 | 7 |
| ≤30″ · 落地式 · ≥$900 | A 命中、B 未命中、C 命中（E 数据不全，F 未起量，D 观察中） | 0 | 3 |

检验组：有效细分（检验组新 SPU ≥ 20）10 个，全类目 60 / 300 = 20.0%；前 20% = ⌈10 × 0.2⌉ = 2 个细分。
需求在涨按宽度档 × 形态取值（关键词不映射价格带）：30–48″·落地式 +20%，≤30″·落地式 +8%，30–48″·悬浮式 +6%，
≥48″·落地式 −6%，≤30″·悬浮式 −8%。前 2 = X、Y：命中 12 + 12 = 24 / 40 = 60.0%，
Wilson 90% = 47.0%–71.7%，倍数 60.0% ÷ 20.0% = 3.00。
现用指标前 2（每个检验批次按 T = 批次月取值）：单位 ASIN 贡献 = ≥48″·落地式·<$500 与 ≤30″·悬浮式·<$500（5 + 4 = 9 / 40）；
属性溢价 = ≥48″·落地式·≥$900 与 ≤30″·悬浮式·≥$900（9 / 40）；属性趋势 = ≥48″·落地式·<$500 与 ≤30″·悬浮式·≥$900（9 / 40）；
低分高销 = ≤30″·悬浮式·<$500 与 ≥48″·落地式·≥$900（9 / 40）。都 ≤ 10 / 40，判定卡 60.0% 高于每一个 → 达标。
定规则组有效细分（≥ 20）为 X、Y 与四个 45 个检验 SPU 的细分，需求在涨均值 20、20、8、6、−6、−8（%）：
前 20% 边界取第 2、3 名的中点 (20 + 8) / 2 = 14% → 按 5 个百分点取整为 +15%；后 20% 边界 (6 + (−6)) / 2 = 0%。
因此锦囊：立项候选 需求在涨 ≥ +15%；观察 0% ≤ 需求在涨 < +15%；放弃 需求在涨 < 0%（均为“历史观察”）。

## FLOW-05 边界商品（≤30″ · 落地式 · ≥$900）
- A（2025-03，子 ASIN B0C3HX7Y2L）：小类 BSR 依次 120、95、80、70、60、50 → 第 6 个月 2025-08 首次 ≤ 50，命中，子 ASIN B0C3HX7Y2L。
- B（2025-02）：窗口 2025-02 至 07 最好 BSR 51、最高月销售额 $99,999；第 7 个月 2025-08 BSR 12 在窗口外 → 未命中。
- C（2025-04，两个子体同父体）：第 2 个月 2025-05 子体销售额 $60,000 + $40,000 = $100,000 → 命中，金额 $100,000。
- D（2025-10）：至 2026-02 共 5 个月未达标 → 观察中（还剩 1 个月）。
- E（2025-05）：第 3 个月 2025-07 在 C1、C3 都没有行，其余月份未达标 → 数据不全，缺失月份 2025-07。
- F（2025-06）：父体月销每月 ≤ 59 → 未起量，2025-06 批次显示“未起量（已排除）1”。

## FLOW-07 信号（T = 2026-03，只用 2026-03-01 之前的数据）
细分 X = 30–48″ · 落地式 · $500–900：
- 需求在涨：映射到 30–48″·落地式 的 3 个词 2025-11 至 2026-02 合计 (120 + 108 + 72) × 4 = 1,200，
  2024-11 至 2025-02 合计 (100 + 90 + 60) × 4 = 1,000 → +20.0%，参与关键词 3 个；泛词“bathroom vanity”标“通用”不计入。
  ≥48″·悬浮式 两个词缺 2024-12 → 该细分“无数据”。
- 新品进得去：上架 2025-03 至 2025-08（T−12 至 T−7）的 X 新 SPU：命中 1+1+1+0+3+3 = 9，未命中 15，数据不全 2 → 9 / 24 = 37.5%。
- 结构类痛点占比：X 子体评论日期早于 2026-03-01 的 199 条 + 父体级评论 1 条（该父体 2026-02 销量最大的子体在 X，另一子体在 Y）
  = 200 条，其中结构类 25 条 → 12.5%；X 另有一条 2026-03-01 的评论不计入。
- 2026-02（T−1）X 有销量的子 ASIN 100 个、销量 4,000 件、销售额 $2,640,000：
  单位 ASIN 贡献 4,000 ÷ 100 = 40.0；销量前 25%（25 个）中两个子体（170 件、150 件）评论均分 3.25 < 4.0 →
  高销低评 = 低分高销 = 320 ÷ 4,000 = 8.0%，涉及 2 个商品；
  属性溢价：X 均价 $2,640,000 ÷ 4,000 = $660，30–48″ 宽度档全部子体均价 $600 → +10.0%。
- 属性趋势：X 销量份额 2025-12 至 2026-02 为 12.0%，2025-09 至 2025-11 为 10.0% → +2.0 个百分点。
- 子体属性：一个 30–48″ 子体形态“未知”（信息不足）→ 归入“30–48″ · 未知 · $500–900”；一个 X 子体柜体材质只有父体候选值“实木”
  → 使用并标“父体回填”（X 回填占比 1 / 100 = 1.0%）；一个 X 子体颜色缺失 → 不回填，颜色为“未知”。

## FLOW-03 体检边界
首次评分早于上架 8 天的子体 3 个（B0A1VNT3QZ 与两个 ≥48″·悬浮式 老品），正好 7 天的 1 个（HOMLUX 子体，不计入）；
同父体上架跨度 181 天的家族 1 个（2022-03-01 / 2022-08-29），正好 180 天的 1 个（2021-05-01 / 2021-10-28，不计入）；
2026-02 有“过去一个月购买”标签的子体月份 32 个，其中 2 个子体月销量（≈42 件）低于“100+”的下界 100；
形态“未知”的子体 5 个；跨月换父 ASIN 的子体 1 个（2025-11 起换父体）；C1 主键重复 2 行（校验为警告并排除）。

## FLOW-04 SPU 归并与新品判定（30–48″ · 悬浮式 · <$500，2025-05 批次，全部未命中）
- 标题主干相同：SOLIDEE 两个父 ASIN（36″ White / 42″ Gray），去掉尺寸、颜色、数字后标题相同。
- 五点描述相同：Eclife 两个父 ASIN，五点描述去掉“•”“-”和换行后完全相同，标题不同。
- 标题主干高度相似且类型属性一致：Woodbridge 两个父 ASIN（Panel / Panels），形态、安装方式、台面形态、元素相同。
- Puluomis SPU：子体 B0A1VNT3QZ 上架 2025-05-03（首评 2025-04-25，早 8 天）、B0A2VNT3QZ 上架 2025-05-20 →
  SPU 上架日 2025-05-03，来自 B0A1VNT3QZ；B0A2VNT3QZ 为“新变体”；SPU 标“疑似重新上架”；归入 2025-05 批次。
- HOMLUX SPU：最早首评 2025-05-05，正好早于上架 2025-05-12 七天 → 不标疑似重新上架。

## FLOW-12 排序（T = 2026-03，判定卡 = 需求在涨，权重 1.00）
得分 = 需求在涨在参与排序细分中的百分位；同一宽度档 × 形态的细分得分相同。有效细分（样本量 ≥ 20）依次：
X（44）、Y（42）[同分，样本量大者在前]；≤30″·落地式·<$500（70）；30–48″·悬浮式·$500–900（67）；
≥48″·落地式·$500–900（66）、≥48″·落地式·<$500（30）、≥48″·落地式·≥$900（25）[同分，按样本量]；
≤30″·悬浮式·$500–900（65）、≤30″·悬浮式·<$500（22）、≤30″·悬浮式·≥$900（22）[后两者同分同样本量，按名称]。
样本不足在后：≤30″·落地式·$500–900（19）、≤30″·落地式·≥$900（3）、30–48″·悬浮式·<$500（7）。
前 20% = X 与 Y（立项候选 ≥ +15%）。
"""

H1B_DOC = """# H1-B 样例包说明（历史 · 约定 v1）

H1-A 的同一批商品延长到 2026-08（2026-02 及以前的每一行与 H1-A 完全相同），另加 2026-03 批次 31 个起量新 SPU：

| 细分（2026-03 快照中的锦囊） | 已判定 | 命中 | 数据不全 |
| :--- | :--- | :--- | :--- |
| X 30–48″·落地式·$500–900（立项候选 R-A） | 5 | 2 | 1 |
| Y 30–48″·落地式·<$500（立项候选 R-A） | 4 | 2 | 0 |
| ≤30″·落地式·<$500（观察 R-B） | 3 | 1 | 0 |
| 30–48″·悬浮式·$500–900（观察 R-B） | 3 | 0 | 0 |
| ≥48″·落地式·$500–900（放弃 R-C） | 3 | 1 | 0 |
| ≤30″·悬浮式·$500–900（放弃 R-C） | 3 | 0 | 0 |
| ≥48″·落地式·<$500（放弃 R-C） | 2 | 0 | 0 |
| ≥48″·悬浮式·$500–900（不在快照中） | 5 | 0 | 2 |

数据至 2026-08 → 2026-03 批次窗口 2026-03 至 2026-08 已结束，对账月份 = 2026-09。
全类目 6 / 28 = 21.4%（3 个数据不全不进分母）；前 20%（X、Y）4 / 9 = 44.4%，倍数 44.4 ÷ 21.4 = 2.07。
规则倍数：R-A 4 / 9 ÷ 6 / 28 = 2.07（≥ 2 → 升为已验证）；R-B 1 / 6 ÷ 6 / 28 = 0.78（观察，只记录）；
R-C 1 / 8 ÷ 6 / 28 = 0.58（未到 ≤ 0.5，状态不变）。
"""

X1_DOC = """# X1 样例包说明（截面数据包 · 约定 v1.1）

观察月 2026-06 至 2026-09（T = 2026-10）。S1 = 观察月起量商品月度数据（老品 40 个子体每月一行，新品在父体月销 ≥ 60 件的月份）；
S2 = 上架 2026-01 至 2026-09 的起量新品；S3 = 这些新品每个观察月一行；C4 属性；C5 关键词只有观察月，
另 30–48″·落地式 与 ≤30″·落地式 有 2025-06 至 2025-09；不含 C6。

## FLOW-06
- P（2026-03 上架，30–48″·落地式·$500–900）：2026-07 为第 5 个月，SPU 销售额 $100,000 → 截面命中，2026-07、月龄 5。
- Q（2026-01 上架，30–48″·落地式·<$500）：第 6 个月 2026-06 有数据未达到 → 截面未命中，未观察到的月龄 1–5。
- R（2026-08 上架，≥48″·落地式·$500–900）：未达到，新品期未结束 → 观察中，不进截面命中率分母。
- S（2025-11 上架老品）：观察月都在月龄 8 以后 → 老品，不做截面判定。

## FLOW-08（T = 2026-10）
新品进得去 → “截面模式不适用”；现用指标只用 40 个老品；属性趋势需 6 个月，观察期 4 个月 → 无数据；
不含 C6 → 结构类痛点、高销低评、低分高销 → 无数据；需求在涨：30–48″·落地式、≤30″·落地式 有上年同期 → 有值，其余细分 → 无数据。

## FLOW-11 截面回测
批次 2026-01 至 2026-09 共 9 个 → 建模组 2026-01 至 2026-06，检验组 2026-07 至 2026-09。
“新品-月”行（新品期内每个有数据的观察月一行）：
- 建模组：2026-01 批次 20 个 × 1 行 + 02 批次 20 × 2 + 03 批次 21 × 3 + 04 批次 27 × 4 + 05 批次 25 × 4 + 06 批次 25 × 4
  = 20 + 40 + 63 + 108 + 100 + 100 = 431 行。
- 检验组：07 批次 36 × 3 + 08 批次 35 × 2 + 09 批次 35 × 1 = 108 + 70 + 35 = 213 行。
检验组每个细分起量新 SPU：30–48″·落地式·$500–900 22（截面命中 10），30–48″·落地式·<$500 21（2），
≤30″·落地式·<$500 21（2），≥48″·落地式·$500–900 21（1），≤30″·悬浮式·<$500 21（1）→ 有效细分 5 个，前 20% = 1 个；
全类目 16 / 106 = 15.1%；建模组中 30–48″·落地式·$500–900 命中 14 / 28 最高 → 模型排第 1 → 10 / 22 = 45.5%，倍数 3.01。
老品现用指标：单位 ASIN 贡献最高 ≤30″·落地式·<$500（老品每月约 120 件）→ 检验组 2 / 21；
属性溢价最高 ≤30″·悬浮式·<$500（$420 对 ≤30″ 档约 $369，+16%）→ 1 / 21；两者都低于 45.5% → 达标（截面）。
≥48″·悬浮式·$500–900 只有 2026-04 批次 2 个新品 → 细分 × 月龄表中观察数 < 5 → 样本过少。
"""


def build_all(out: Path, with_scale: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    global _used_asins
    # H1-A
    _used_asins = set()
    a = H1(H1A_END)
    pa = a.assemble("H1-A")
    pa.doc = H1A_DOC
    write_h1(pa, out)
    # H1-B (same products, extended)
    _used_asins = set()
    b = H1(H1B_END)
    pb = b.assemble("H1-B")
    pb.doc = H1B_DOC
    pb.manifest["新品上架窗口"] = {"起": "2025-01-01", "止": "2026-08-31"}
    write_h1(pb, out)
    # bad-row variants: C1 = 1,000 unique rows of H1-A with n unparsable launch dates
    base_rows = [dict(r) for r in pa.c1[:-2]][:1000]
    for n in (8, 10, 11):
        rows = [dict(r) for r in base_rows]
        for i in range(n):
            rows[100 + i * 37]["上架日期"] = "2025/13/45"
        v = Package(f"H1-坏行{n}")
        v.c2, v.c3, v.c4, v.c5, v.c6, v.c7, v.manifest = pa.c2, pa.c3, pa.c4, pa.c5, pa.c6, pa.c7, pa.manifest
        v.c1 = rows
        v.doc = (f"# H1-坏行{n}\n\nH1-A 的 C1 只保留前 1,000 个不重复主键的行，其中 {n} 行“上架日期”写成 2025/13/45（无法解析）。\n"
                 f"{n} / 1,000 = {n / 10:.1f}% → {'≤ 1%，C1 记“警告”，排除这些行，计算只用其余 ' + str(1000 - n) + ' 行' if n <= 10 else '> 1%，C1 记“阻断”，不能计算'}。\n"
                 f"被排除的文件行号（表头为第 1 行）：{', '.join(str(102 + i * 37) for i in range(n))}。\n")
        write_h1(v, out)
    # no manifest
    v = Package("H1-无清单")
    v.c1, v.c2, v.c3, v.c4, v.c5, v.c6, v.c7 = pa.c1, pa.c2, pa.c3, pa.c4, pa.c5, pa.c6, pa.c7
    v.manifest = None  # type: ignore[assignment]
    v.doc = "# H1-无清单\n\nH1-A 去掉清单文件 清单.json → 清单缺失，记阻断，不保存只读副本。\n"
    write_h1(v, out)
    # field changes: two new fields and 优惠券 numeric → text
    v = Package("H1-字段变化")
    v.c2, v.c3, v.c4, v.c5, v.c6, v.c7, v.manifest = pa.c2, pa.c3, pa.c4, pa.c5, pa.c6, pa.c7, pa.manifest
    v.c1 = []
    for r in pa.c1:
        r2 = dict(r)
        r2["Prime价格"] = r2.get("当月价格") or ""
        r2["促销标记"] = "Deal" if h("deal", r2["子ASIN"], r2["月份"]) % 7 == 0 else ""
        if r2.get("优惠券"):
            r2["优惠券"] = f"满$300减{r2['优惠券']}"
        v.c1.append(r2)
    v.doc = ("# H1-字段变化\n\nH1-A 的 C1 新增字段“Prime价格”“促销标记”，并把“优惠券”从数值改为文本（如“满$300减20”）。\n"
             "其余字段与 H1-A 相同 → 只有这 3 个字段列为待确认，其余沿用当前字段约定。\n")
    write_h1(v, out, extra_cols=["Prime价格", "促销标记"])
    # SPU numbers / no bullets
    _used_asins = set()
    c = H1(H1A_END)
    pc = c.assemble("H1-SPU编号")
    numbers = {}
    for i, p in enumerate(sorted(c.plans, key=lambda p: p.key)):
        for kid in p.children:
            numbers[kid.asin] = f"SPU{1000 + i}"
    s = c.special
    for pair in ("SOL", "ECL", "WB"):
        x, y = s[pair]
        numbers[y.asin] = numbers[x.asin]
    for o in c.old:
        numbers.setdefault(o.asin, f"OLD{h('n', o.asin) % 100000:05d}")
    pc.doc = ("# H1-SPU编号\n\nH1-A 加上已确认的“SPU编号”字段（C1、C2）：每个新 SPU 一个编号，SOLIDEE、Eclife、Woodbridge 两个父体共用一个编号。\n"
              "字段约定确认 SPU编号 后，按编号归并，不生成合并建议。\n")
    write_h1(pc, out, spu_no=numbers)
    pd_ = Package("H1-无五点")
    pd_.c1, pd_.c2, pd_.c3, pd_.c4, pd_.c5, pd_.c6, pd_.c7, pd_.manifest = pa.c1, pa.c2, pa.c3, pa.c4, pa.c5, pa.c6, pa.c7, pa.manifest
    pd_.doc = "# H1-无五点\n\nH1-A 去掉 C1、C2 的可选字段“五点描述” → 不生成“五点描述相同”的建议，对照中五点摘要显示“无数据”。\n"
    write_h1(pd_, out, drop_bullets=True)
    # backtest variants (FLOW-10)
    for name, kwargs, doc in (
        ("H1-两批次", {"keep_batches": ["2025-08", "2025-09"] + list(WATCH)},
         "只保留 2025-08、2025-09 两个已判定批次（另有 2025-10 至 2026-02 观察中）→ 已判定批次 2 个 → 未达标：数据不足。"),
        ("H1-样本19", {"test": TEST_19},
         "检验组 ≤30″·悬浮式·≥$900 新 SPU 7 + 7 + 5 = 19 个 → 样本不足；≤30″·悬浮式·<$500 正好 20 个 → 照常参与。"),
        ("H1-有效4", {"test": TEST_SPARSE},
         "检验组只有 X、Y、≥48″·落地式·$500–900、≤30″·悬浮式·$500–900 四个细分新 SPU ≥ 20 → 有效细分 4 个（< 5）→ 未达标：细分样本不足。"),
        ("H1-无区分度", {"test": TEST_FLAT},
         "检验组 X 命中 2 / 20、Y 命中 2 / 20 → 需求在涨前 2 命中 4 / 40 = 10.0%，全类目 40 / 300 = 13.3%，倍数 0.75 → 未达标：信号无区分度。"),
    ):
        _used_asins = set()
        hb = H1(H1A_END, **kwargs)
        pv = hb.assemble(name)
        pv.doc = f"# {name}\n\n{doc}\n"
        write_h1(pv, out)
    # X1 and X1 without old products
    for name, with_old, doc in (("X1", True, X1_DOC),
                                ("X1-无老品", False, "# X1-无老品\n\nX1 去掉全部 40 个老品 → 四个现用指标都无法计算 → 未达标：数据不足。\n")):
        _used_asins = set()
        xb = X1(with_old=with_old)
        px = xb.assemble(name)
        px.doc = doc
        write_x1(px, out)
    if with_scale:
        from fixtures import build_scale

        build_scale.build(out / "S-规模")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "packages"))
    ap.add_argument("--with-scale", action="store_true")
    args = ap.parse_args()
    build_all(Path(args.out), args.with_scale)
    print("built", args.out)


if __name__ == "__main__":
    main()

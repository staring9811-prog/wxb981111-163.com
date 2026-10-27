"""S-规模 sample package (RULE-05 / NFR-005): the same order of magnitude as the prototype package P-0008 —
C1 ≈ 413k rows, C6 ≈ 183k reviews, ≈ 666k rows in all, 24 months, 12 new-product batches with trajectories.

The content is synthetic but follows the data contract (PRD §10.4) exactly, so import, compute and backtest run the
same code paths as on a real package. Generation is deterministic (fixed seed).

    python -m fixtures.build_scale [out_dir]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fixtures.build_samples import C1_COLS, C2_COLS, C3_COLS, C4_COLS, C5_COLS, C6_COLS, C7_COLS, DIMS, mrange, ym

SEED = 20261106
MONTHS = mrange("2024-03", "2026-02")  # 24 months of C1
BATCHES = mrange("2024-09", "2025-08")  # 12 batches whose 6-month windows end by 2026-02
N_OLD_PARENTS = 6_600
NEW_PER_BATCH = 260
N_REVIEWS = 183_000
ALNUM = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

WIDTHS = [("≤30″", (24, 30)), ("30–48″", (36, 42)), ("≥48″", (48, 60))]
FORMS = [("落地式", "freestanding", "落地"), ("悬浮式", "floating", "壁挂")]
BANDS = [(150, 499), (500, 899), (900, 1600)]
COLORS = [("White", "白色"), ("Gray", "灰色"), ("Black", "黑色"), ("Oak", "原木色"), ("Navy", "蓝色"), ("Green", "绿色")]
ELEMENTS = ["抽屉", "柜门", "开放层板", "镜柜", "LED 灯"]
TOPS = ["一体盆", "台上盆", "台下盆"]
BODY = ["实木", "MDF", "PVC", "颗粒板"]
TOP_MAT = ["石英石", "大理石", "陶瓷", "岩板"]


def code(i: int, prefix: str = "B0") -> str:
    s = []
    for _ in range(8):
        s.append(ALNUM[i % 34])
        i //= 34
    return prefix + "".join(s)


def brands(n: int, rng: np.random.Generator) -> list[str]:
    syl = ["Lu", "Ma", "Ver", "Sol", "Ka", "Ri", "Bel", "Do", "Fen", "Ta", "Mo", "Za", "Hel", "Ori", "Pa", "Que"]
    out: list[str] = []
    seen: set[str] = set()
    while len(out) < n:
        b = "".join(rng.choice(syl, size=int(rng.integers(2, 4)))) + rng.choice(["", "x", "on", "ia", "o"])
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def build(out: Path) -> dict[str, int]:
    rng = np.random.default_rng(SEED)
    brand_names = brands(600, rng)
    month_idx = {m: i for i, m in enumerate(MONTHS)}

    # ---- children: old parents (1–4 children) and new parents per batch (1–3 children)
    kids = []
    serial = 0

    def new_child(parent: str, brand: str, w: int, f: int, b: int, launch: str, is_new: bool) -> None:
        nonlocal serial
        serial += 1
        size = WIDTHS[w][1][int(rng.integers(0, 2))]
        color = COLORS[int(rng.integers(0, len(COLORS)))]
        price = int(rng.integers(BANDS[b][0], BANDS[b][1] + 1))
        kids.append({"child": code(serial * 7 + 3), "parent": parent, "brand": brand, "w": w, "f": f, "b": b,
                     "size": size, "color": color, "price": price, "launch": launch, "new": is_new})

    for p in range(N_OLD_PARENTS):
        parent = code(10_000_000 + p * 13, "B0")
        brand = brand_names[int(rng.integers(0, len(brand_names)))]
        w, f, b = int(rng.integers(0, 3)), int(rng.integers(0, 2)), int(rng.integers(0, 3))
        y = int(rng.integers(2019, 2024))
        launch = f"{y}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}"
        for _ in range(int(rng.integers(1, 5))):
            new_child(parent, brand, w, f, b, launch, False)
    n_old_kids = len(kids)
    for bi, batch in enumerate(BATCHES):
        made = 0
        while made < NEW_PER_BATCH:
            parent = code(20_000_000 + bi * 100_000 + made * 17, "B0")
            brand = brand_names[int(rng.integers(0, len(brand_names)))]
            w, f, b = int(rng.integers(0, 3)), int(rng.integers(0, 2)), int(rng.integers(0, 3))
            launch = f"{batch}-{int(rng.integers(1, 28)):02d}"
            n = int(rng.integers(1, 4))
            for _ in range(n):
                new_child(parent, brand, w, f, b, launch, True)
            made += n
    kd = pd.DataFrame(kids)
    form_word = {0: "Freestanding", 1: "Floating"}
    kd["title"] = [f"{r.brand} {r.size} Inch {form_word[r.f]} Bathroom Vanity with Sink, {r.color[0]}"
                   for r in kd.itertuples()]
    kd["fulfillment"] = np.where(rng.random(len(kd)) < 0.8, "FBA", "FBM")
    kd["variants"] = kd.groupby("parent")["child"].transform("count")
    kd["first_review"] = [(pd.Timestamp(lc) + pd.Timedelta(days=int(d))).strftime("%Y-%m-%d")
                          for lc, d in zip(kd["launch"], rng.integers(10, 60, len(kd)), strict=False)]

    # ---- monthly trajectories
    rows = []
    old = kd.iloc[:n_old_kids]
    base_units = rng.lognormal(2.9, 0.7, n_old_kids)
    for _mi, m in enumerate(MONTHS):
        keep = rng.random(n_old_kids) > 0.02
        units = np.maximum(1, (base_units * rng.uniform(0.8, 1.25, n_old_kids)).astype(int))
        rows.append(pd.DataFrame({"month": m, "child": old["child"].to_numpy()[keep], "units": units[keep]}))
    new = kd.iloc[n_old_kids:].reset_index(drop=True)
    traj = []
    rising = rng.random(len(new)) < 0.55
    hit = rng.random(len(new)) < 0.22
    for i, r in new.iterrows():
        start = month_idx.get(r["launch"][:7])
        for k, m in enumerate(MONTHS[start:]):
            u = int(rng.integers(8, 40)) + (int(rng.integers(30, 90)) if rising[i] and k in (1, 2, 3, 4) else 0)
            bsr = int(rng.integers(20, 50)) if hit[i] and k == 3 else int(rng.integers(60, 3000))
            traj.append((m, r["child"], u, bsr))
    tj = pd.DataFrame(traj, columns=["month", "child", "units", "bsr"])
    allm = pd.concat(rows + [tj[["month", "child", "units"]]], ignore_index=True)
    allm = allm.merge(kd[["child", "parent", "price"]], on="child")
    allm["sales"] = allm["units"] * allm["price"]
    allm["parent_units"] = allm.groupby(["month", "parent"])["units"].transform("sum")
    allm["bsr_rank"] = allm.groupby("month")["parent_units"].rank(ascending=False, method="min").astype(int)
    tj = tj.merge(allm[["month", "child", "parent_units", "price"]], on=["month", "child"])
    c1 = allm[(~allm["child"].isin(new["child"])) | (allm["parent_units"] >= 60)].merge(kd, on=["child", "parent", "price"])
    c1 = c1.sort_values(["month", "child"])
    c1_df = pd.DataFrame({
        "月份": c1["month"].map(ym), "子ASIN": c1["child"], "当月父ASIN": c1["parent"], "品牌": c1["brand"],
        "卖家": c1["brand"] + " Store", "标题": c1["title"], "上架日期": c1["launch"], "子体月销量": c1["units"],
        "子体月销售额": c1["sales"], "父体月销量": c1["parent_units"], "小类BSR": c1["bsr_rank"],
        "类目节点": "6810202011", "配送方式": c1["fulfillment"], "变体数": c1["variants"],
        "首次评分日期": c1["first_review"], "过去一个月购买": "", "当月价格": c1["price"], "当月评分": "",
        "五点描述": "", "优惠券": ""})
    c2_df = pd.DataFrame({"子ASIN": new["child"], "父ASIN": new["parent"], "品牌": new["brand"], "标题": new["title"],
                          "上架日期": new["launch"], "配送方式": new["fulfillment"], "变体数": new["variants"],
                          "首次评分日期": new["first_review"], "五点描述": ""})
    c3_df = pd.DataFrame({"月份": tj["month"].map(ym), "子ASIN": tj["child"], "子体月销量": tj["units"],
                          "子体月销售额": tj["units"] * tj["price"], "小类BSR": tj["bsr"],
                          "父体月销量": tj["parent_units"]})
    c4 = {"子ASIN": kd["child"]}
    vals = {
        "尺寸": kd["size"].astype(str), "颜色": kd["color"].map(lambda c: c[1]), "盆数": "1",
        "形态": kd["f"].map(lambda f: FORMS[f][0]), "安装方式": kd["f"].map(lambda f: FORMS[f][2]),
        "元素": [ELEMENTS[i] for i in rng.integers(0, len(ELEMENTS), len(kd))],
        "台面形态": [TOPS[i] for i in rng.integers(0, len(TOPS), len(kd))],
        "柜体材质": [BODY[i] for i in rng.integers(0, len(BODY), len(kd))],
        "台面材质": [TOP_MAT[i] for i in rng.integers(0, len(TOP_MAT), len(kd))], "台盆材质": "陶瓷",
    }
    for d in DIMS:
        c4[d] = vals[d]
        c4[f"{d}证据状态"] = "子体确认"
    c4_df = pd.DataFrame(c4)[C4_COLS]
    kw = []
    for _w, sizes in WIDTHS:
        for _f, en, _cn in FORMS:
            for k in range(50):
                size = sizes[k % 2]
                term = f"{size} inch {en} bathroom vanity {['', 'with sink', 'cabinet', 'set', 'modern'][k % 5]} {k}".strip()
                base = int(rng.integers(40, 400))
                trend = rng.uniform(-0.1, 0.25)
                for m in mrange("2023-09", "2026-02"):
                    yr = (int(m[:4]) - 2023) + (int(m[5:]) - 9) / 12
                    kw.append((term, ym(m), max(1, int(base * (1 + trend) ** yr)), f"尺寸={size};形态={en}"))
    c5_df = pd.DataFrame(kw, columns=C5_COLS)
    seen = allm.groupby("child")["month"].min()
    rv_child = rng.choice(seen.index.to_numpy(), N_REVIEWS)
    first = pd.to_datetime(seen.loc[rv_child].to_numpy() + "-01")
    span = (pd.Timestamp("2026-02-28") - first).days.to_numpy()
    rv_date = first + pd.to_timedelta((rng.random(N_REVIEWS) * np.maximum(span, 1)).astype(int), unit="D")
    structural = rng.random(N_REVIEWS) < 0.14
    c6_df = pd.DataFrame({"评论ID": [f"R{i:010d}" for i in range(N_REVIEWS)], "ASIN": rv_child,
                          "归属级别": np.where(rng.random(N_REVIEWS) < 0.03, "父体", "子体"),
                          "评论日期": rv_date.strftime("%Y-%m-%d"), "星级": rng.integers(1, 6, N_REVIEWS),
                          "痛点事件代码": np.where(structural, "S03", "N12"),
                          "是否结构类痛点": np.where(structural, "是", "否"), "标注版本": "v3"})
    par = c6_df["归属级别"] == "父体"
    c6_df.loc[par, "ASIN"] = c6_df.loc[par, "ASIN"].map(dict(zip(kd["child"], kd["parent"], strict=False)))
    c7_df = pd.DataFrame([{"立项名称": "规模测试立项", "立项日期": "2025-12-10", "关联细分或属性": "30–48″ · 落地式 · $500–900"}],
                         columns=C7_COLS)

    out.mkdir(parents=True, exist_ok=True)
    files = {"C1": ("C1_月度类目商品.csv", c1_df[C1_COLS]), "C2": ("C2_新品清单.csv", c2_df[C2_COLS]),
             "C3": ("C3_新品月度轨迹.csv", c3_df[C3_COLS]), "C4": ("C4_属性标签.csv", c4_df),
             "C5": ("C5_关键词月度.csv", c5_df), "C6": ("C6_评论痛点.csv", c6_df[C6_COLS]),
             "C7": ("C7_自家立项.csv", c7_df)}
    counts = {}
    for k, (name, df) in files.items():
        df.to_csv(out / name, index=False, encoding="utf-8")
        counts[k] = len(df)
    manifest = {"类型": "历史", "约定版本": "v1", "品类": "浴室柜", "站点": "US", "类目节点": "6810202011",
                "覆盖月份": {"起": MONTHS[0], "止": MONTHS[-1]},
                "新品上架窗口": {"起": f"{BATCHES[0]}-01", "止": "2026-02-28"},
                "文件": {k: v[0] for k, v in files.items()}}
    (out / "清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    counts["total"] = sum(counts.values())
    return counts


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "scale" / "S-规模"
    print(json.dumps(build(out), ensure_ascii=False))


if __name__ == "__main__":
    main()

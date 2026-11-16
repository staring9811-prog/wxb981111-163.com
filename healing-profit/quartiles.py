# -*- coding: utf-8 -*-
"""Sales-weighted price quartiles (P25 / P50 / P75) per product segment, Amazon SellerSprite 2026-10.
Each parent's monthly units are split evenly across its children (same rule as the matrices)."""
import json, matrix as M
def q(rs):
    tot = sum(r["u"] for r in rs); s = sorted(rs, key=lambda r: r["price"]); out = []
    for qq in (.25, .5, .75):
        c = 0
        for r in s:
            c += r["u"]
            if c >= qq * tot: out.append(r["price"]); break
    return {"units": round(tot), "n": len(rs), "p25": out[0], "p50": out[1], "p75": out[2]}
def rows(name, keep):
    rs = [r for r in M.load(f"mkt/{name}.csv") if keep(r) and r["price"]]
    M.split_parent_units(rs); return rs
sa = rows("sauna", lambda r: M.sauna_keep(r["t"]))
td = rows("tandem", lambda r: M.tandem_keep(r["t"]))
th = [r for r in rows("thermo", lambda r: M.thermo_keep(r["t"], r["price"])) if "thermostatic" in r["t"]]
Q = {
 "sauna_1": q([r for r in sa if M.sauna_cap(r["t"]) == "1 人"]),
 "sauna_12": q([r for r in sa if M.sauna_cap(r["t"]) == "1-2 人"]),
 "dual": q(td),
 "th_nojet": q([r for r in th if M.thermo_jets(r["t"]) == "无侧喷"]),
 "th_24": q([r for r in th if M.thermo_jets(r["t"]) == "2–4 个"]),
 "th_6": q([r for r in th if M.thermo_jets(r["t"]) == "6 个及以上"]),
}
json.dump(Q, open("quartiles.json", "w"), ensure_ascii=False, indent=1)
for k, v in Q.items(): print(k, v)

# -*- coding: utf-8 -*-
"""Break-even retail and max purchase cost (15% target) per SKU / tier / channel from calc_out.json."""
import json
d = json.load(open("calc_out.json")); P = d["params"]; rate, tax = P["rate"], P["tax"]
pct = (P["promo"] + P["fx"] + P["refund"] + P["comm"]) / 100
rows = []
for r in d["res"]:
    o = {"sku": r["sku"], "tier": r["tier"]}
    conv = (lambda usd: usd * rate) if r["sku"] == "DUAL" else (lambda usd: usd * rate * (1 + tax / 100))
    for ch, profit, ship in [("amzFBM", r["fbm"], r["fbmShip"]), ("amzFBA", r["fba"], r["fbaShip"])]:
        price = r["amzPrice"]; mx = r["cost"] + profit - 0.15 * price
        o[ch] = dict(price=price, profit=round(profit, 1), margin=round(profit / price, 3), maxCostUSD=round(mx, 1),
                     maxCostRMB=round(conv(mx)), breakeven=round((r["cost"] + r["sea"] + ship) / (1 - pct)))
    for k, v in r["plat"].items():
        if not v["priced"]: o[k] = None; continue
        mx = r["cost"] + v["profit"] - 0.15 * v["settle"]
        o[k] = dict(price=v["retail"], settle=round(v["settle"], 1), profit=round(v["profit"], 1), margin=round(v["margin"], 3),
                    maxCostUSD=round(mx, 1), maxCostRMB=round(conv(mx)), breakeven=round(v["breakeven"]))
    rows.append(o)
json.dump(rows, open("summary.json", "w"), indent=1, ensure_ascii=False)

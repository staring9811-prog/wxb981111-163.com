"""M1-真相: a history package with planted relationships, for checking that the 变量关系 models find them back.

It is H1-A's product world (same segments, batches, signals and old products) with four truths planted on the
judged new SPUs. The truths are written to 真相.json next to the package so tests and people can compare:

1. 细分 X（30–48″ · 落地式 · $500–900）命中率最高 — already true in H1-A's RULE/TEST tables.
2. 台面形态 = 一体盆 raises the hit odds inside every segment (direct effect): P(一体盆 | 命中) = 0.65, P(一体盆 | 未命中) = 0.25.
3. 柜体材质 = 实木 looks related to hitting only because both go with FBA: FBA is set to 85% for hits and 35% for
   misses, and 实木 is set to 70% for FBA SPUs and 20% for FBM SPUs, independent of the outcome given FBA.
4. 颜色 has nothing to do with the outcome (left as H1-A assigns it: deterministic hash, unrelated to outcome).

Simulated data verifies the method, never the business (solution-master, 案例-锦囊 §二 2).

Usage: python -m fixtures.build_mock_truth [--out DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fixtures import build_samples as B

NAME = "M1-真相"
P_TOP_HIT, P_TOP_MISS = 0.65, 0.25
P_FBA_HIT, P_FBA_MISS = 0.85, 0.35
P_WOOD_FBA, P_WOOD_FBM = 0.70, 0.20

TRUTH = {
    "说明": "模拟数据，只用来验证方法能否找回种入的关系，不代表业务效果。",
    "结果变量": "命中：上架 6 个月内小类 BSR ≤ 50 或月 GMV ≥ $100,000（与 H1-A 相同）",
    "真相": [
        {"编号": 1, "类型": "细分", "内容": "30–48″ · 落地式 · $500–900 的命中率最高（RULE/TEST 表设定，约 50–60%，全类目约 20%）",
         "期望": "模型 1 的重要性里 宽度档=30–48″、形态=落地式、价格带=$500–900 排前列；模型 3 找到包含这三个条件之一以上的高档规则"},
        {"编号": 2, "类型": "属性-直接效应", "内容": f"台面形态=一体盆：命中 SPU 中占 {P_TOP_HIT:.0%}，未命中中占 {P_TOP_MISS:.0%}",
         "期望": "控制细分与控制变量后优势比仍明显大于 1（约 5），验证组方向一致"},
        {"编号": 3, "类型": "属性-假关联", "内容": f"柜体材质=实木 只通过 FBA 与命中相关：FBA 在命中中 {P_FBA_HIT:.0%}、未命中中 {P_FBA_MISS:.0%}；"
                                          f"实木 在 FBA 中 {P_WOOD_FBA:.0%}、FBM 中 {P_WOOD_FBM:.0%}",
         "期望": "控制前优势比 > 1，控制配送方式后明显回落（接近 1）"},
        {"编号": 4, "类型": "属性-无关", "内容": "颜色 与结果无关", "期望": "每个颜色的优势比区间都包含 1；不出现只含颜色条件的高档规则"},
    ],
}


def _p(key: str, *parts: object) -> float:
    return (B.h("truth", key, *parts) % 10000) / 10000.0


class Mock(B.H1):
    def build_plans(self) -> None:
        super().build_plans()
        for p in self.plans:
            hit = "@" in p.outcome and not p.outcome.startswith("inc")
            miss = p.outcome == "miss"
            if not (hit or miss):
                continue  # watch / incomplete / custom SPUs are not judged, no truth planted
            for c in p.children:
                fba = _p("fba", c.asin) < (P_FBA_HIT if hit else P_FBA_MISS)
                c.fulfillment = "FBA" if fba else "FBM"
                top = _p("top", c.asin) < (P_TOP_HIT if hit else P_TOP_MISS)
                c.attrs["台面形态"] = ("一体盆" if top else ("台上盆" if _p("top2", c.asin) < 0.5 else "台下盆"), "子体确认")
                wood = _p("wood", c.asin) < (P_WOOD_FBA if fba else P_WOOD_FBM)
                c.attrs["柜体材质"] = ("实木" if wood else ("MDF" if _p("wood2", c.asin) < 0.5 else "橡胶木"), "子体确认")


def build(out: Path) -> Path:
    B._used_asins = set()
    m = Mock(B.H1A_END)
    pkg = m.assemble(NAME)
    pkg.doc = ("# M1-真相（模拟数据）\n\nH1-A 的产品世界，在已判定的新 SPU 上种入四条关系，用来验证“变量关系”模型能否找回它们；"
               "细节见同目录 `真相.json`。模拟数据只验证方法，不代表业务效果。\n")
    d = B.write_h1(pkg, out)
    judged = [p for p in m.plans if ("@" in p.outcome and not p.outcome.startswith("inc")) or p.outcome == "miss"]
    truth = dict(TRUTH)
    truth["样本"] = {"已判定新 SPU": len(judged), "命中": sum(1 for p in judged if "@" in p.outcome)}
    (d / "真相.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(B.HERE / "packages"))
    a = ap.parse_args()
    print("built", build(Path(a.out)))


if __name__ == "__main__":
    main()

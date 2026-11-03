"""品类配置（F27）：版本化保存，读取当前版本。默认值来自 PRD §3.3.12–3.3.14 与第二轮脚本 机会扫描.py。"""
import copy

from sqlalchemy import func, select

from .db import session
from .models import CategoryConfig

DEFAULT = {
    "category": "浴室柜",
    "frame_dims": [  # 分框维度（AC-F27-01 默认：尺寸段 × 拆装 × 形态）
        {"dim": "尺寸段", "tag": "尺寸段", "values": ["24″", "30″", "36″", "48″", "60″", "72″"]},
        {"dim": "拆装", "tag": "装", "values": ["拆装", "整装"]},
        {"dim": "形态", "tag": "形态", "values": ["落地式", "悬浮式"]},
    ],
    "scan_attrs": [  # 扫描属性（AC-F20-01）
        {"attr": "台面材质", "tag": "台面材质", "scan": True, "method": "规则 + 看图"},
        {"attr": "元素", "tag": "元素", "scan": True, "method": "看图（大模型）", "multi": True},
        {"attr": "主色", "tag": "主色", "scan": True, "method": "规则 + 看图"},
        {"attr": "柜体材质", "tag": "柜体材质", "scan": True, "method": "规则"},
    ],
    "low_conf_threshold": 0.75,  # 低于此置信度进入确认队列（RA-103）
    "tag_rules": {},  # 打标规则：由打标模块填充默认关键词规则
    "scan": {"min_frame_units": 200, "min_value_units": 10,
             "growth": {"dlog_share": 0.3, "min_units": 100, "newshare_gt_frame": True},
             "rating_gap": {"rating_diff": -0.15, "per_family_ratio": 1.0, "min_units": 50},
             "price_gap": {"premium": 1.3, "min_units": 20},
             "pit": {"dlog_share": -0.3, "min_units": 100}},
    "channels": {  # 其他渠道销量估算与成功线（AC-F27-03，PRD §3.3.12）
        "amazon": {"success": {"bsr_top": 50, "spu_revenue": 100000}},
        "homedepot": {"method": "review", "vp_coef": 50, "nonvp_coef": 20, "success": {"rank_top": 50, "units": 250}},
        "lowes": {"method": "review", "vp_coef": 50, "nonvp_coef": 20, "success": {"rank_top": 50, "units": 150}},
        "wayfair": {"method": "review", "vp_coef": 50, "nonvp_coef": 20, "success": {"rank_top": 50, "units": 120}},
    },
    "verify": {  # Amazon 核对阈值（DEC-102，wen 2026-11-03 确认；AC-F17-03 原文 10%）
        "total_change_pct": 30, "family_consistency_min": 90, "tag_coverage_min": 95, "rank_same_max_pct": 10},
    "budget_warn_pct": 80,  # DEC-104
}


def current() -> tuple[int, dict]:
    with session() as s:
        row = s.scalar(select(CategoryConfig).order_by(CategoryConfig.version.desc()).limit(1))
        if row is None:
            s.add(CategoryConfig(version=1, data=copy.deepcopy(DEFAULT), diff=[]))
            return 1, copy.deepcopy(DEFAULT)
        return row.version, copy.deepcopy(row.data)


def _diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else str(k))
    elif a != b:
        out.append({"path": path, "old": a, "new": b})
    return out


def preview(new: dict) -> list:
    _, cur = current()
    return _diff(cur, new)


def save(new: dict, user_id: int | None) -> int:
    v, cur = current()
    d = _diff(cur, new)
    if not d:
        return v
    with session() as s:
        nv = (s.scalar(select(func.max(CategoryConfig.version))) or 0) + 1
        s.add(CategoryConfig(version=nv, data=new, diff=d, created_by=user_id))
    return nv


def history():
    with session() as s:
        return [dict(version=r.version, diff=r.diff, at=r.created_at, by=r.created_by)
                for r in s.scalars(select(CategoryConfig).order_by(CategoryConfig.version.desc()))]

"""Bright Data / Apify 调用（并入品类机会判定台后的版本）。

与原工具 tools/评论月度VP追踪器/reviewkit/services.py 的差别只在"钱和密钥从哪来"（AC-F23-02）：
- 密钥：不再读环境变量或 .secrets.json，一律经 `pdt.services.client("brightdata" / "apify")` 取系统设置页保存的密钥；
- 记账：每笔调用前 `job.allow(...)` 检查设置页的月度上限，调用后 `job.charge(...)` 记入同一费用记录；
- 原工具的项目预算（budget.bd_<平台>_usd、apify_<平台>_usd，ledger.json）保留，与月度上限"任一先到即停"。
调用方式（异步 Web Unlocker、Actor 运行参数、计价）与原工具相同。
"""
import threading

from .common import load_json, save_json

_lock = threading.Lock()


class BudgetExceeded(Exception):
    pass


class Ledger:
    """项目自身的花费记录（原工具 ledger.json）：BD 按平台记请求数，Apify 按平台记美元。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.f = ctx.path("ledger.json")

    def get(self):
        return load_json(self.f, {}) or {}

    def add(self, k, n):
        with _lock:
            d = self.get()
            d[k] = round(d.get(k, 0) + n, 6)
            save_json(self.f, d)
            return d[k]


def _job(ctx):
    return getattr(ctx, "job", None)


# ---------------------------------------------------------------- Bright Data（Web Unlocker，异步）
BD_PRICE = 1.5 / 1000


class BD:
    def __init__(self, ctx):
        c = ctx.cfg.get("services", {}).get("brightdata", {})
        self.ctx, self.ledger = ctx, Ledger(ctx)
        self.customer = c.get("customer", "hl_87b86747")
        self.zone = c.get("zone", "mcp_unlocker")
        self.budget = ctx.cfg.get("budget", {})

    def _charge(self, platform):
        cap = float(self.budget.get(f"bd_{platform}_usd", 10))
        n = self.ledger.get().get(f"bd_{platform}_req", 0)
        if (n + 1) * BD_PRICE > cap:
            raise BudgetExceeded(f"BD {platform}: {n} requests, cap ${cap}")
        job = _job(self.ctx)
        if job is not None:
            job.allow("brightdata", amount=BD_PRICE, qty=1)  # 设置页月度上限，到上限抛 CapReached
        self.ledger.add(f"bd_{platform}_req", 1)
        if job is not None:
            job.charge("brightdata", qty=1, amount=BD_PRICE, task=f"评论 VP 追踪 · {platform} 页面", source=self.ctx.cfg.get("name", ""))

    def _client(self):
        from .. import services
        c = services.client("brightdata")
        if hasattr(c, "customer") and self.customer:
            c.customer = self.customer
        if hasattr(c, "zone") and self.zone:
            c.zone = self.zone
        return c

    def fetch(self, url, platform, poll=15, max_wait=1200):
        self._charge(platform)
        return self._client().fetch(url, poll=poll, max_wait=max_wait)


# ---------------------------------------------------------------- Apify
class Apify:
    def __init__(self, ctx):
        self.ctx, self.ledger = ctx, Ledger(ctx)
        self.budget = ctx.cfg.get("budget", {})

    def run(self, actor, run_input, platform, max_charge_usd=3, timeout_s=3600, poll=20):
        cap = float(self.budget.get(f"apify_{platform}_usd", 10))
        spent = self.ledger.get().get(f"apify_{platform}_usd", 0)
        if spent >= cap:
            raise BudgetExceeded(f"Apify {platform}: ${spent:.2f} spent, cap ${cap}")
        charge = min(max_charge_usd, cap - spent)
        job = _job(self.ctx)
        if job is not None:
            from .. import costgate
            job.allow("apify", amount=0.01)
            mcap, unit = costgate.budget("apify")
            if mcap is not None and unit == "usd":  # 单次运行的扣费上限也不超过本月剩余额度
                charge = max(0.01, min(charge, mcap - costgate.spent("apify")[0]))
        from .. import services
        items, usd = services.client("apify").run(actor, run_input, max_charge_usd=charge, timeout_s=timeout_s, poll=poll)
        self.ledger.add(f"apify_{platform}_usd", usd)
        if job is not None:
            job.charge("apify", qty=1, amount=usd, task=f"评论 VP 追踪 · {platform} 评论", source=self.ctx.cfg.get("name", ""))
        return items, usd

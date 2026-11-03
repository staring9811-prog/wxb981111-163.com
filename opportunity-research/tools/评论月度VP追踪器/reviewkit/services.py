"""Clients for external services (registry: services/README.md). No secrets in code.

Keys, in order: environment variable (BD_TOKEN / APIFY_TOKEN) → crawler/.secrets.json (git-ignored, for local
runs) → a dummy value, which works in the claude.ai cloud where Network secrets inject the real key.
"""
import json, os, time, threading, urllib.request, urllib.error, urllib.parse
from .common import ROOT, load_json, save_json

_lock = threading.Lock()


def key(name):
    v = os.environ.get(name)
    if v:
        return v
    sec = load_json(os.path.join(ROOT, ".secrets.json"), {}) or {}
    return sec.get(name) or "dummy"


def _http(url, data=None, headers=None, method=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


class BudgetExceeded(Exception):
    pass


class Ledger:
    """Per-project spend tracker: BD requests per platform, Apify USD per platform."""

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


# ---------------------------------------------------------------- Bright Data (Web Unlocker, async)
BD_API = "https://api.brightdata.com/unblocker"
BD_PRICE = 1.5 / 1000


class BD:
    def __init__(self, ctx):
        c = ctx.cfg.get("services", {}).get("brightdata", {})
        self.ctx, self.ledger = ctx, Ledger(ctx)
        self.customer = c.get("customer", "hl_87b86747")
        self.zone = c.get("zone", "mcp_unlocker")
        self.budget = ctx.cfg.get("budget", {})

    def _h(self):
        return {"Authorization": f"Bearer {key('BD_TOKEN')}", "Content-Type": "application/json"}

    def _charge(self, platform):
        cap = float(self.budget.get(f"bd_{platform}_usd", 10))
        n = self.ledger.get().get(f"bd_{platform}_req", 0)
        if (n + 1) * BD_PRICE > cap:
            raise BudgetExceeded(f"BD {platform}: {n} requests, cap ${cap}")
        self.ledger.add(f"bd_{platform}_req", 1)

    def fetch(self, url, platform, poll=15, max_wait=1200):
        self._charge(platform)
        q = urllib.parse.urlencode({"customer": self.customer, "zone": self.zone})
        st, h, b = _http(f"{BD_API}/req?{q}", json.dumps({"url": url, "country": "us"}).encode(), self._h())
        if st != 200:
            return st, b
        rid = json.loads(b)["response_id"]
        q = urllib.parse.urlencode({"customer": self.customer, "zone": self.zone, "response_id": rid})
        t0 = time.time()
        while time.time() - t0 < max_wait:
            st, h, b = _http(f"{BD_API}/get_result?{q}", headers=self._h())
            if st == 200:
                hl = {k.lower(): v for k, v in h.items()}
                return int(hl.get("x-brd-status-code", 200) or 200), b
            if st != 202:
                return st, b
            time.sleep(poll)
        return 504, b"timeout"


# ---------------------------------------------------------------- Apify
APIFY = "https://api.apify.com/v2"


class Apify:
    def __init__(self, ctx):
        self.ctx, self.ledger = ctx, Ledger(ctx)
        self.budget = ctx.cfg.get("budget", {})

    def _req(self, method, path, body=None, timeout=120):
        st, h, b = _http(f"{APIFY}{path}", json.dumps(body).encode() if body is not None else None,
                         {"Authorization": f"Bearer {key('APIFY_TOKEN')}", "Content-Type": "application/json"},
                         method, timeout)
        try:
            return st, json.loads(b or b"null")
        except Exception:
            return st, b[:300]

    def run(self, actor, run_input, platform, max_charge_usd=3, timeout_s=3600, poll=20):
        cap = float(self.budget.get(f"apify_{platform}_usd", 10))
        spent = self.ledger.get().get(f"apify_{platform}_usd", 0)
        if spent >= cap:
            raise BudgetExceeded(f"Apify {platform}: ${spent:.2f} spent, cap ${cap}")
        charge = min(max_charge_usd, cap - spent)
        act = actor.replace("/", "~")
        st, res = self._req("POST", f"/acts/{act}/runs?timeout={timeout_s}&maxTotalChargeUsd={charge:.2f}", run_input)
        if st not in (200, 201):
            raise RuntimeError(f"Apify start {actor}: HTTP {st} {res}"[:300])
        run = res["data"]
        while run.get("status") in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
            time.sleep(poll)
            st, res = self._req("GET", f"/actor-runs/{run['id']}")
            if st == 200:
                run = res["data"]
        items, off = [], 0
        while True:
            st, page = self._req("GET", f"/datasets/{run['defaultDatasetId']}/items?format=json&offset={off}&limit=1000")
            if st != 200 or not isinstance(page, list) or not page:
                break
            items += page
            off += len(page)
            if len(page) < 1000:
                break
        usd = run.get("usageTotalUsd") or 0
        self.ledger.add(f"apify_{platform}_usd", usd)
        if run.get("status") != "SUCCEEDED":
            self.ctx.log(f"  Apify run {run['id']} status {run.get('status')} (items kept: {len(items)})")
        return items, usd

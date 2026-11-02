"""Bright Data Web Unlocker async client.

Auth is injected by the cloud environment's proxy (Network secrets for
api.brightdata.com/unblocker/), so the Authorization header here is a dummy.
Each request is submitted, then polled until ready. A ledger counts requests
per platform so the per-platform budget can be enforced.
"""
import json, os, time, threading, urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor

API = "https://api.brightdata.com/unblocker"
CUSTOMER = os.environ.get("BD_CUSTOMER", "hl_87b86747")
ZONE = os.environ.get("BD_ZONE", "mcp_unlocker")
PRICE_PER_REQ = 1.5 / 1000
LEDGER = os.path.join(os.path.dirname(__file__), "..", "data", "bd_ledger.json")
_lock = threading.Lock()


class BudgetExceeded(Exception):
    pass


def _ledger():
    try:
        return json.load(open(LEDGER))
    except Exception:
        return {}


def _charge(platform, budget_usd):
    with _lock:
        led = _ledger()
        n = led.get(platform, 0)
        if (n + 1) * PRICE_PER_REQ > budget_usd:
            raise BudgetExceeded(f"{platform}: {n} requests used, budget {budget_usd}")
        led[platform] = n + 1
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        json.dump(led, open(LEDGER, "w"))


def _http(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer dummy", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def submit(url, platform, budget_usd=10.0, method=None, body=None, headers=None, country="us", extra=None):
    _charge(platform, budget_usd)
    payload = {"url": url, "country": country}
    if method:
        payload["method"] = method
    if body is not None:
        payload["body"] = body
    if headers:
        payload["headers"] = headers
    if extra:
        payload.update(extra)
    q = urllib.parse.urlencode({"customer": CUSTOMER, "zone": ZONE})
    st, h, b = _http(f"{API}/req?{q}", json.dumps(payload).encode())
    if st != 200:
        raise RuntimeError(f"submit {st}: {b[:200]!r}")
    return json.loads(b)["response_id"]


def result(rid, poll=15, max_wait=1200):
    q = urllib.parse.urlencode({"customer": CUSTOMER, "zone": ZONE, "response_id": rid})
    t0 = time.time()
    while time.time() - t0 < max_wait:
        st, h, b = _http(f"{API}/get_result?{q}")
        if st == 200:
            hl = {k.lower(): v for k, v in h.items()}
            return int(hl.get("x-brd-status-code", 200) or 200), b
        if st != 202:
            return st, b
        time.sleep(poll)
    return 504, b"timeout waiting for result"


def fetch(url, platform, retries=2, **kw):
    """Submit + wait. Returns (status, bytes)."""
    last = (0, b"")
    for _ in range(retries + 1):
        rid = submit(url, platform, **kw)
        last = result(rid)
        if last[0] == 200 and len(last[1]) > 500:
            return last
    return last


def fetch_many(urls, platform, workers=20, **kw):
    """Fetch many URLs concurrently. Returns {url: (status, bytes)}."""
    out = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {u: ex.submit(fetch, u, platform, **kw) for u in urls}
        for u, f in futs.items():
            try:
                out[u] = f.result()
            except Exception as e:  # budget or submit error
                out[u] = (0, str(e).encode())
    return out

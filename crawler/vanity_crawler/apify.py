"""Apify client. The token is injected by the cloud proxy (Network secrets for api.apify.com),
or read from the APIFY_TOKEN environment variable for the current session. Never commit a token."""
import json, os, urllib.request, urllib.error, urllib.parse

API = "https://api.apify.com/v2"


def _req(method, path, body=None, timeout=330):
    token = os.environ.get("APIFY_TOKEN", "dummy")
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500]


def run_actor(actor, run_input, timeout_s=300, max_charge_usd=None):
    """Run an actor synchronously; returns (items, run_info). max_charge_usd caps pay-per-event spend."""
    act = actor.replace("/", "~")
    q = f"timeout={timeout_s}" + (f"&maxTotalChargeUsd={max_charge_usd}" if max_charge_usd else "")
    st, res = _req("POST", f"/acts/{act}/run-sync-get-dataset-items?{q}", run_input, timeout=timeout_s + 30)
    if st not in (200, 201):
        raise RuntimeError(f"apify {actor} HTTP {st}: {res!r}"[:300])
    _, last = _req("GET", "/actor-runs?desc=1&limit=1")
    run = ((last or {}).get("data") or {}).get("items", [{}])[0] if isinstance(last, dict) else {}
    return res, {"id": run.get("id"), "usd": run.get("usageTotalUsd")}


def usage_this_month():
    st, res = _req("GET", "/users/me/usage/monthly")
    return res if st == 200 else None

import json, os, re, time, random, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
DATA = os.path.join(os.path.dirname(__file__), "..", "data")
YEAR_START, FULL_END = "2026-01-01", "2026-10-31"


def direct_get(url, retries=3, delay=(1.0, 2.5)):
    """Plain GET of a public page from the cloud (used for HDP only)."""
    last = (0, b"")
    for i in range(retries):
        time.sleep(random.uniform(*delay))
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.read())
            if e.code == 404:
                return last
        except Exception as e:  # network
            last = (0, str(e).encode())
        time.sleep(3 * (i + 1))
    return last


def decode_at(s, pos):
    """json-decode the value starting at s[pos]."""
    return json.JSONDecoder().raw_decode(s[pos:])[0]


def objects_by_key(s, key_regex):
    """Find every `"<key>":{...}` in a page and decode it. Returns {key: obj}."""
    out = {}
    for m in re.finditer(r'"(' + key_regex + r')":(?=[\{\[])', s):
        if m.group(1) in out:
            continue
        try:
            out[m.group(1)] = decode_at(s, m.end())
        except Exception:
            pass
    return out


def month_of(date):
    if not date:
        return ""
    m = date[:7]
    return m + "（未完整）" if m == "2026-11" else m


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, path)


def load_json(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default

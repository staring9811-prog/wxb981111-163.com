import json, os, re, time, random, threading, urllib.request, urllib.error, urllib.parse
from datetime import date

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # crawler/
_log_lock = threading.Lock()


class Ctx:
    """Everything a run needs: config, data dir, window, logger."""

    def __init__(self, cfg, data_dir=None, log=None):
        self.cfg = cfg
        self.data = data_dir or os.path.join(ROOT, "data", "projects", cfg["name"])
        w = cfg.get("window", {})
        self.start = w.get("start", f"{date.today().year}-01-01")
        self.full_end = w.get("full_end", "")          # last day of the last complete month
        self.include_partial = w.get("include_partial", True)
        self.months = month_list(self.start, self.full_end, self.include_partial)
        self._log = log
        os.makedirs(self.data, exist_ok=True)

    def path(self, *p):
        return os.path.join(self.data, *p)

    def log(self, *a):
        msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
        with _log_lock:
            print(msg, flush=True)
            with open(self.path("run.log"), "a", encoding="utf-8") as f:
                f.write(msg + "\n")
            if self._log:
                self._log(msg)

    def in_window(self, d):
        if not d or d < self.start:
            return False
        if self.include_partial or not self.full_end:
            return True
        return d <= self.full_end

    def month_label(self, d):
        m = (d or "")[:7]
        if self.full_end and d > self.full_end:
            return m + "（未完整）"
        return m


def month_list(start, full_end, include_partial):
    y, m = int(start[:4]), int(start[5:7])
    end = full_end or date.today().isoformat()
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if include_partial and full_end:
        t = date.today()
        y, m = (ey + 1, 1) if em == 12 else (ey, em + 1)
        while (y, m) <= (t.year, t.month):
            out.append(f"{y}-{m:02d}（未完整）")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def add_query(url, **params):
    parts = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    q = [(k, v) for k, v in q if k not in params] + [(k, str(v)) for k, v in params.items() if v is not None]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def direct_get(url, retries=3, delay=(1.0, 2.5)):
    """Plain GET of a public page (Home Depot)."""
    last = (0, b"")
    url = urllib.parse.quote(url, safe=":/?&=%#,+")
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
        except Exception as e:
            last = (0, str(e).encode())
        time.sleep(3 * (i + 1))
    return last


def decode_at(s, pos):
    return json.JSONDecoder().raw_decode(s[pos:])[0]


def objects_by_key(s, key_regex):
    out = {}
    for m in re.finditer(r'"(' + key_regex + r')":(?=[\{\[])', s):
        if m.group(1) in out:
            continue
        try:
            out[m.group(1)] = decode_at(s, m.end())
        except Exception:
            pass
    return out


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

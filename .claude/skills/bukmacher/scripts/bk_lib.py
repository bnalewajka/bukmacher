"""Shared helpers for the bukmacher skill scripts.

Pure standard library (urllib, json, datetime) so the scripts run anywhere
Python 3.9+ exists. Every network call goes through http_get_json(), which:
  * honours HTTPS_PROXY / SSL_CERT_FILE from the environment,
  * sends a browser-like User-Agent (Sofascore and ESPN reject bare clients),
  * retries transient failures,
  * caches responses on disk (default TTL 10 min) so re-runs do not burn
    API quota (The Odds API bills per request; api-sports has 100/day free).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
# Akamai-fronted hosts (ESPN) reject a browser UA sent with a non-browser TLS fingerprint
# but accept a plain client UA; http_get falls back to it once on 403.
PLAIN_UA = "curl/8.7.1"

CACHE_DIR = Path(os.environ.get("BUKMACHER_CACHE", Path.home() / ".cache" / "bukmacher"))
DEFAULT_TTL = int(os.environ.get("BUKMACHER_CACHE_TTL", "600"))
NO_CACHE = os.environ.get("BUKMACHER_NO_CACHE") == "1"

SPORTS = ["football", "basketball", "hockey", "tennis", "volleyball"]

# Canonical sport name -> per-source identifiers.
SPORT_MAP = {
    "football":   {"espn": "soccer",     "sofascore": "football",   "apisports": "football",   "oddsapi": "Soccer"},
    "basketball": {"espn": "basketball", "sofascore": "basketball", "apisports": "basketball", "oddsapi": "Basketball"},
    "hockey":     {"espn": "hockey",     "sofascore": "ice-hockey", "apisports": "hockey",     "oddsapi": "Ice Hockey"},
    "tennis":     {"espn": "tennis",     "sofascore": "tennis",     "apisports": None,         "oddsapi": "Tennis"},
    "volleyball": {"espn": None,         "sofascore": "volleyball", "apisports": "volleyball", "oddsapi": None},
}


# --------------------------------------------------------------------------- time
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_time(value: Any) -> Optional[datetime]:
    """Accept unix seconds, ISO 8601 (with Z or offset), or ESPN's '2024-01-01T19:00Z'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    s = str(value).strip()
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=timezone.utc)
    s = s.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


def in_window(start: Optional[datetime], t0: datetime, hours: float, grace_minutes: int = 0) -> bool:
    """Event counts if it starts between t0 - grace and t0 + hours."""
    if start is None:
        return False
    return (t0 - timedelta(minutes=grace_minutes)) <= start <= (t0 + timedelta(hours=hours))


def date_span(t0: datetime, hours: float) -> list[str]:
    """UTC calendar dates (YYYY-MM-DD) touched by the window, for per-day APIs."""
    days = set()
    cur = t0
    end = t0 + timedelta(hours=hours)
    while cur <= end:
        days.add(cur.strftime("%Y-%m-%d"))
        cur += timedelta(hours=12)
    days.add(end.strftime("%Y-%m-%d"))
    return sorted(days)


# --------------------------------------------------------------------------- http
SECRET_PARAMS = re.compile(r"((?:api_?key|apikey|token|key)=)[^&]+", re.I)


def redact(url: str) -> str:
    """Hide credentials passed as query parameters (The Odds API's apiKey) before a URL is
    printed, logged or written to the cache — CI logs of a public repo are public."""
    return SECRET_PARAMS.sub(r"\1***", url)


class HttpError(Exception):
    def __init__(self, url: str, status: Optional[int], detail: str):
        url = redact(url)
        super().__init__(f"{status} {url}: {detail}")
        self.url, self.status, self.detail = url, status, detail


def _cache_path(url: str, headers: dict) -> Path:
    key = hashlib.sha1((url + json.dumps(sorted(headers.items()))).encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def http_get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
             timeout: int = 25, retries: int = 2, ttl: int = DEFAULT_TTL) -> tuple[bytes, dict]:
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
    hdrs = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8"}
    if headers:
        hdrs.update(headers)
    safe_hdrs = {k: v for k, v in hdrs.items() if k.lower() not in ("x-apisports-key", "x-rapidapi-key", "authorization")}
    cpath = _cache_path(url, safe_hdrs)
    if not NO_CACHE and ttl > 0 and cpath.exists() and time.time() - cpath.stat().st_mtime < ttl:
        blob = json.loads(cpath.read_text())
        return blob["body"].encode("utf-8"), blob.get("headers", {})

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                if ttl > 0:
                    try:
                        CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        cpath.write_text(json.dumps({"url": redact(url), "headers": resp_headers,
                                                     "body": body.decode("utf-8", "replace")}))
                    except OSError:
                        pass
                return body, resp_headers
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            last_err = HttpError(url, e.code, detail)
            if e.code == 403 and hdrs.get("User-Agent") == UA:
                hdrs["User-Agent"] = PLAIN_UA
                continue
            if e.code in (400, 401, 403, 404, 422, 429):
                break  # not transient (429: do not hammer a rate-limited API)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_err = HttpError(url, None, str(e))
        time.sleep(1.5 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def http_get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, **kw) -> Any:
    body, _ = http_get(url, params=params, headers=headers, **kw)
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise HttpError(url, None, f"non-JSON response: {body[:120]!r}") from e


# --------------------------------------------------------------------------- odds math
def fractional_to_decimal(frac: Any) -> Optional[float]:
    """'1/5' -> 1.20 ; also accepts numbers already decimal."""
    if frac is None:
        return None
    if isinstance(frac, (int, float)):
        return float(frac)
    s = str(frac).strip()
    if "/" in s:
        try:
            a, b = s.split("/")
            return round(float(a) / float(b) + 1.0, 3)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def american_to_decimal(val: Any) -> Optional[float]:
    try:
        a = float(str(val).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (a / 100.0 if a > 0 else 100.0 / abs(a)), 3)


def implied(odds: float) -> float:
    return 1.0 / odds if odds and odds > 1 else 0.0


def devig(odds_list: Iterable[float]) -> list[float]:
    """Proportional (multiplicative) de-vig: normalise implied probabilities so they sum to 1.
    Good enough to compare selections; for short prices the power/Shin methods give slightly
    lower fair probabilities, which is why the skill treats de-vigged numbers as an upper bound."""
    probs = [implied(o) for o in odds_list]
    total = sum(probs)
    return [p / total for p in probs] if total > 0 else probs


def overround(odds_list: Iterable[float]) -> float:
    return sum(implied(o) for o in odds_list) - 1.0


# --------------------------------------------------------------------------- naming
def norm_name(name: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|sc|ac|bk|kk|hc|hk|ks|ss|ssc|afc|cd|club|women|w|u21|u19|u23)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def event_key(sport: str, home: str, away: str, start: Optional[datetime]) -> str:
    """Stable key to merge the same fixture across sources (15-minute time bucket)."""
    bucket = int(start.timestamp() // 900) if start else 0
    h, a = norm_name(home), norm_name(away)
    return f"{sport}|{h[:12]}|{a[:12]}|{bucket}"


# --------------------------------------------------------------------------- io
def eprint(*a, **k):
    print(*a, file=sys.stderr, **k)


def dump_json(obj: Any, path: Optional[str]):
    text = json.dumps(obj, ensure_ascii=False, indent=1, default=str)
    if path:
        Path(path).write_text(text, encoding="utf-8")
        eprint(f"[saved] {path}")
    else:
        print(text)


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table(rows: list[dict], cols: list[str], max_width: int = 34) -> str:
    if not rows:
        return "(no rows)"
    widths = {c: min(max_width, max(len(c), *(len(str(r.get(c, ""))) for r in rows))) for c in cols}
    def fmt(r):
        return " | ".join(str(r.get(c, ""))[:widths[c]].ljust(widths[c]) for c in cols)
    head = " | ".join(c.ljust(widths[c]) for c in cols)
    return "\n".join([head, "-" * len(head)] + [fmt(r) for r in rows])


# Gitignored KEY=value files checked after the real environment: the skill's own .env, then the cwd's.
DOTENV_PATHS = (Path(__file__).resolve().parent.parent / ".env", Path.cwd() / ".env")


def _dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in DOTENV_PATHS:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip("'\""))
    return out


def env_key(*names: str) -> Optional[str]:
    """First non-empty value among `names`, from the environment, else from a .env file."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    dotenv = _dotenv()
    for n in names:
        if dotenv.get(n):
            return dotenv[n]
    return None

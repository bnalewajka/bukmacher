#!/usr/bin/env python3
"""Verify the current UTC time before building a time window.

Why: the analysis window ("next 4 hours") is only meaningful if "now" is right.
Containers, VMs and sandboxes sometimes have a wrong clock, and the model itself
has no reliable sense of the date. We compare the system clock against the
`Date:` header returned by several independent HTTPS servers (an RFC 7231 header
every server sets from its own clock), and report the drift.

Usage:
  python3 clock.py            # human summary + JSON on stdout
  python3 clock.py --json     # JSON only
Exit code 2 when drift > --max-drift seconds or when no external source answered.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bk_lib import UA, iso, now_utc

HOSTS = [
    "https://api.github.com/",
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.google.com/generate_204",
    "https://www.wikipedia.org/",
    "https://api.sofascore.com/api/v1/sport/football/scheduled-events/2000-01-01",
    "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
]


def header_time(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = r.headers.get("Date")
    except urllib.error.HTTPError as e:  # 4xx still carries a Date header
        d = e.headers.get("Date") if e.headers else None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if not d:
        return None, "no Date header"
    try:
        return parsedate_to_datetime(d).astimezone(timezone.utc), None
    except Exception as e:  # noqa: BLE001
        return None, f"bad Date header {d!r}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-drift", type=int, default=120)
    args = ap.parse_args()

    system = now_utc()
    samples, errors = [], {}
    for url in HOSTS:
        dt, err = header_time(url)
        if dt:
            samples.append({"source": url, "utc": iso(dt), "drift_s": round((dt - system).total_seconds(), 1)})
        else:
            errors[url] = err

    result = {
        "system_utc": iso(system),
        "system_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "external": samples,
        "errors": errors,
    }
    if samples:
        drift = statistics.median(s["drift_s"] for s in samples)
        result["median_drift_s"] = drift
        result["verified_utc"] = iso(datetime.fromtimestamp(system.timestamp() + drift, tz=timezone.utc))
        result["verdict"] = "OK" if abs(drift) <= args.max_drift else "CLOCK DRIFT - use verified_utc, not the system clock"
    else:
        result["verified_utc"] = None
        result["verdict"] = ("NO EXTERNAL SOURCE REACHED - network blocked? Use `date -u` only as a hypothesis "
                             "and confirm the date against a fetched page (e.g. a live-score site) before trusting the window")

    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print(f"system   : {result['system_utc']}  (local {result['system_local']})")
        for s in samples:
            print(f"external : {s['utc']}  drift {s['drift_s']:+.1f}s  <- {s['source']}")
        for u, e in errors.items():
            print(f"failed   : {u} -> {e}")
        print(f"verified : {result['verified_utc']}")
        print(f"verdict  : {result['verdict']}")
    ok = bool(samples) and abs(result.get("median_drift_s", 0)) <= args.max_drift
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

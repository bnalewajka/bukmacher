#!/usr/bin/env python3
"""betexplorer.com: fixtures, bookmaker odds comparison (incl. Polish books) and results.

Keyless HTML/JSON scraping — the fallback when Sofascore is blocked, the source of Polish
prices (STS, eFortuna, Betclic.pl, Superbet.pl, LV BET…), and the settlement source for the
ledger (final score, partial scores, closing odds).

Page times are in the site's default zone (UTC+1 without a cookie); every function converts
to UTC using the page's own `data-dt-now` against the verified clock.

Usage:
  python3 betexplorer.py next --sport hockey --hours 4 [--now 2026-09-24T16:47:03Z] [--out f.json]
  python3 betexplorer.py odds <match_id> 1x2 dc ou ah bts dnb ha   # prints per line/column median, max, PL books
  python3 betexplorer.py result <match_url>

Sports: football, hockey, basketball, tennis, volleyball. Bet types: 1x2, dc, ou, ah, bts, dnb,
ha (home/away, no draw — basketball, tennis, volleyball).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bk_lib import HttpError, dump_json, eprint, http_get, iso, now_utc, parse_time, table

BASE = "https://www.betexplorer.com"
PL_BOOKS = ("STS", "Fortuna", "Betclic", "Superbet", "LV BET", "Fuksiarz", "BETFAN", "Betters", "ComeOn")
XHR = {"X-Requested-With": "XMLHttpRequest"}
LIST_PATH = {"football": "/football/", "hockey": "/hockey/next/", "basketball": "/basketball/next/",
             "tennis": "/tennis/next/", "volleyball": "/volleyball/next/"}


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _page(path: str, ttl: int = 600) -> str:
    body, _ = http_get(BASE + path, ttl=ttl)
    return body.decode("utf-8", "replace")


def _page_dt(dt: str) -> datetime:
    d, m, y, hh, mm = (int(x) for x in dt.split(","))
    return datetime(y, m, d, hh, mm)


def _page_offset(page: str) -> timedelta:
    """Site clock minus UTC, in whole hours: the page prints its own 'now' (data-dt-now), compared
    with the real clock — not the window start, which may be earlier. Whole hours absorb the
    few minutes a cached page can be old."""
    m = re.search(r'data-dt-now="([^"]+)"', page)
    if not m:
        return timedelta(hours=1)
    diff = _page_dt(m.group(1)) - now_utc().replace(tzinfo=None)
    return timedelta(hours=round(diff.total_seconds() / 3600))


# ----------------------------------------------------------------------------- fixtures
def _football_day(day: datetime) -> str:
    """Every football match of one (site-time) day. The /football/ page shows only a slice;
    the site lazy-loads the rest from homepage-data.php, and end=all returns all of it at once."""
    body, _ = http_get(f"{BASE}/gres/ajax/homepage-data.php", headers=XHR, params={
        "tab": "all", "year": day.year, "month": day.month, "day": day.day, "betType": "1x2",
        "start": 0, "end": "all"})
    return body.decode("utf-8", "replace")


def football_matches(now: datetime, hours: float) -> list[dict]:
    """All football fixtures in the window (≈100+ leagues a day instead of the ~10 on /football/)."""
    out, seen = [], set()
    end = now + timedelta(hours=hours)
    day = (now + timedelta(hours=1)).date()          # site days run on UTC+1; +1 h covers late-night UTC
    while datetime(day.year, day.month, day.day, tzinfo=timezone.utc) <= end + timedelta(hours=1):
        page = _football_day(datetime(day.year, day.month, day.day))
        offset = _page_offset(page)
        for block in page.split('<ul class="leagues-list')[1:]:
            name = re.search(r'data-league-name="([^"]*)"', block)
            country = re.search(r'data-country-name="([^"]*)"', block)
            league = ": ".join(html.unescape(x.group(1)) for x in (country, name) if x) or None
            for m in re.finditer(r'data-dt="([^"]+)"[^>]*?data-dt-now="[^"]+"(.*?)(?=data-dt="|\Z)', block, re.S):
                body = m.group(2)
                link = re.search(r'href="(/football/[^"]+/([A-Za-z0-9]{8})/)"', body)
                home = re.search(r'table-main__participantHome[^>]*>\s*<p[^>]*>([^<]*)</p>', body)
                away = re.search(r'table-main__participantAway[^>]*>.*?<p[^>]*>([^<]*)</p>', body, re.S)
                if not (link and home and away) or link.group(2) in seen:
                    continue
                start = (_page_dt(m.group(1)) - offset).replace(tzinfo=timezone.utc)
                if not (now <= start <= end):
                    continue
                seen.add(link.group(2))
                out.append({"sport": "football", "competition": league, "home": _text(home.group(1)),
                            "away": _text(away.group(1)), "start_utc": iso(start),
                            "odds": [float(x) for x in re.findall(r'data-odd="([\d.]+)"', body)[:3]],
                            "match_id": link.group(2), "url": BASE + link.group(1)})
        day += timedelta(days=1)
    return sorted(out, key=lambda r: r["start_utc"])


def next_matches(sport: str, now: Optional[datetime] = None, hours: float = 24) -> list[dict]:
    now = now or now_utc()
    if sport == "football":
        return football_matches(now, hours)
    page = _page(LIST_PATH[sport])
    offset = _page_offset(page)
    out, league = [], None
    row_re = (r'<tr class="js-tournament">.*?class="table-main__tournament[^"]*">(.*?)</a>'
              r'|<tr (?:data-fro="\d+" )?data-dt="([^"]+)"[^>]*>(.*?)</tr>')
    for m in re.finditer(row_re, page, re.S):
        if m.group(1) is not None:
            league = _text(m.group(1))
            continue
        body = m.group(3)
        if "time--fin" in body or "table-main__time--live" in body:
            continue
        teams = [_text(t) for t in re.findall(r'teamLine--(?:home|away)">(.*?)</span>', body)]
        link = re.search(rf'href="(/{sport}/[^"]+/([A-Za-z0-9]{{8}})/)"', body)
        if not link:
            continue
        if not teams:  # football list: "Home - Away" in one anchor
            a = re.search(rf'<a href="/{sport}/[^"]+/">(.*?)</a>', body, re.S)
            teams = [x.strip() for x in _text(a.group(1)).split(" - ", 1)] if a else []
        if len(teams) != 2:
            continue
        start = (_page_dt(m.group(2)) - offset).replace(tzinfo=timezone.utc)
        if not (now <= start <= now + timedelta(hours=hours)):
            continue
        out.append({"sport": sport, "competition": league, "home": teams[0], "away": teams[1],
                    "start_utc": iso(start), "odds": [float(x) for x in re.findall(r'data-odd="([\d.]+)"', body)],
                    "match_id": link.group(2), "url": BASE + link.group(1)})
    return out


# --------------------------------------------------------------------------------- odds
def odds(match_id: str, bettype: str, ttl: int = 300) -> dict:
    """{'columns': [...], 'rows': [{'bookmaker', 'line', 'odds': [...]}, ...]} for one bet type."""
    body, _ = http_get(f"{BASE}/match-odds-old/{match_id}/1/{bettype}/0/en/", headers=XHR, ttl=ttl)
    try:
        frag = json.loads(body)["odds"]
    except (ValueError, KeyError):
        return {"columns": [], "rows": []}
    cols = [_text(x) for x in re.findall(r'<th class="table-main__detail-odds"[^>]*>(.*?)</th>', frag)]
    rows = []
    for tr in re.findall(r'<tr data-bid="\d+"[^>]*>(.*?)</tr>', frag, re.S):
        bk = re.search(r'title="([^"]+)"', tr)
        line = re.search(r'table-main__doubleparameter">([^<]*)<', tr)
        prices = [float(x) for x in re.findall(r'data-odd="([\d.]+)"', tr)]
        if bk and prices:
            rows.append({"bookmaker": html.unescape(bk.group(1)), "line": line.group(1).strip() if line else "",
                         "odds": prices})
    return {"columns": cols, "rows": rows}


def price_summary(match_id: str, bettype: str, line: str = "", col: int = 0) -> Optional[dict]:
    """Median / max / per-Polish-book price of one selection (line as shown on the site, '' if none)."""
    rows = [r for r in odds(match_id, bettype)["rows"] if r["line"] == line and len(r["odds"]) > col]
    if not rows:
        return None
    vals = [r["odds"][col] for r in rows]
    best = max(rows, key=lambda r: r["odds"][col])
    return {"median": round(statistics.median(vals), 3), "max": best["odds"][col], "max_book": best["bookmaker"],
            "n_books": len(vals), "pl": {r["bookmaker"]: r["odds"][col] for r in rows
                                         if any(k.lower() in r["bookmaker"].lower() for k in PL_BOOKS)}}


# ------------------------------------------------------------------------------ results
def result(url: str, ttl: int = 300) -> dict:
    """Final state of a match page: finished flag, score, partial scores, stage (AET, After Penalties…)."""
    path = url.replace(BASE, "")
    page = _page(path, ttl=ttl)
    fin = re.search(r'value="(\d?)" id="isFinished"', page)
    live = re.search(r'value="(\d?)" id="isLive"', page)
    score = re.search(r'id="js-score">([^<]*)<', page)
    partial = re.search(r'js-partial">([^<]*)<', page)
    stage = re.search(r'id="js-eventstage"[^>]*>([^<]*)<', page)
    names = [_text(x) for x in re.findall(r'<h2 class="list-details__item__title">(.*?)</h2>', page, re.S)]

    def pair(txt: str) -> Optional[tuple[int, int]]:
        mm = re.match(r"\s*(\d+)\s*:\s*(\d+)", txt or "")
        return (int(mm.group(1)), int(mm.group(2))) if mm else None

    parts = [pair(p) for p in re.findall(r"\d+\s*:\s*\d+", partial.group(1))] if partial else []
    return {"url": url, "finished": bool(fin and fin.group(1) == "1"), "live": bool(live and live.group(1) == "1"),
            "home": names[0] if names else None, "away": names[1] if len(names) > 1 else None,
            "score": pair(score.group(1)) if score else None, "partials": [p for p in parts if p],
            "stage": _text(stage.group(1)) if stage else ""}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("next"); n.add_argument("--sport", required=True, choices=list(LIST_PATH))
    n.add_argument("--hours", type=float, default=4); n.add_argument("--now"); n.add_argument("--out")
    o = sub.add_parser("odds"); o.add_argument("match_id"); o.add_argument("bettypes", nargs="+")
    r = sub.add_parser("result"); r.add_argument("url")
    args = ap.parse_args()
    try:
        if args.cmd == "next":
            now = parse_time(args.now) if args.now else now_utc()
            rows = next_matches(args.sport, now, args.hours)
            print(table([{**x, "odds": " ".join(map(str, x["odds"]))} for x in rows],
                        ["start_utc", "competition", "home", "away", "odds", "match_id"], max_width=40))
            dump_json(rows, args.out) if args.out else None
        elif args.cmd == "odds":
            for bt in args.bettypes:
                data = odds(args.match_id, bt)
                print(f"== {bt}  columns={data['columns'][:4]}")
                for line in dict.fromkeys(r["line"] for r in data["rows"]):
                    for col in range(max(len(r["odds"]) for r in data["rows"] if r["line"] == line)):
                        s = price_summary(args.match_id, bt, line, col)
                        if s:
                            pl = ", ".join(f"{k}={v}" for k, v in s["pl"].items())
                            print(f"  line {line or '-':>6} col {col}: med {s['median']:.2f}  max {s['max']:.2f} "
                                  f"({s['max_book']})  n={s['n_books']}  [{pl}]")
        elif args.cmd == "result":
            print(json.dumps(result(args.url), ensure_ascii=False))
    except HttpError as e:
        eprint(f"[betexplorer] {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

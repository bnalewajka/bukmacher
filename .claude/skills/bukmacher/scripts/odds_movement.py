#!/usr/bin/env python3
"""How does a favourite's price movement (opening -> closing) relate to how often it wins?

Research tool behind the "follow the market?" question. For every favourite whose price falls in
a band (default 1.30-1.60) it buckets the opening->closing move and reports, per bucket:
the win rate, the probability implied by the opening and closing prices, and the return of
betting at the opening vs the closing price.

Football source: football-data.co.uk season files (opening B365/PS/Avg and closing B365C/PSC/AvgC
1X2 prices, full-time result) for the main European leagues, 2019/20 onwards (closing prices
exist from then). Prices used: market average (what a typical bookmaker pays, close to the Polish
books) for the move and the returns; Pinnacle reported alongside as the sharp reference.

  python3 odds_movement.py football [--from 1920] [--to 2526] [--band 1.30 1.60] [--by closing|opening]
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from bk_lib import HttpError, eprint, http_get

FD = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
LEAGUES = {  # division code -> name
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "SC0": "Scottish Premiership", "D1": "Bundesliga", "D2": "2. Bundesliga", "I1": "Serie A",
    "I2": "Serie B", "SP1": "La Liga", "SP2": "Segunda", "F1": "Ligue 1", "F2": "Ligue 2",
    "N1": "Eredivisie", "B1": "Jupiler League", "P1": "Primeira Liga", "T1": "Super Lig", "G1": "Super League GR",
}
BUCKETS = [(-1.0, -0.10, "spadek > 10%"), (-0.10, -0.05, "spadek 5–10%"), (-0.05, -0.02, "spadek 2–5%"),
           (-0.02, 0.02, "±2% (bez zmian)"), (0.02, 0.05, "wzrost 2–5%"), (0.05, 0.10, "wzrost 5–10%"),
           (0.10, 9.0, "wzrost > 10%")]


def seasons(a: int, b: int) -> list[str]:
    out, y = [], a // 100
    while y <= b // 100:
        out.append(f"{y:02d}{(y + 1) % 100:02d}")
        y += 1
    return out


def num(row: dict, *keys: str):
    for k in keys:
        try:
            v = float(row.get(k) or "")
            if v > 1:
                return v
        except ValueError:
            continue
    return None


def football_rows(first: int, last: int) -> list[dict]:
    rows = []
    for season in seasons(first, last):
        for div, name in LEAGUES.items():
            try:
                body, _ = http_get(FD.format(season=season, div=div), ttl=7 * 86400, timeout=60)
            except HttpError as e:
                eprint(f"[odds_movement] {season} {div}: {e.status}")
                continue
            text = body.decode("latin-1").lstrip("﻿")
            for r in csv.DictReader(io.StringIO(text)):
                if r.get("FTR") not in ("H", "D", "A"):
                    continue
                rec = {"season": season, "league": name, "ftr": r["FTR"]}
                for side, s in (("H", "home"), ("D", "draw"), ("A", "away")):
                    rec[f"avg_o_{s}"] = num(r, f"Avg{side}", f"BbAv{side}")
                    rec[f"avg_c_{s}"] = num(r, f"AvgC{side}")
                    rec[f"ps_o_{s}"] = num(r, f"PS{side}")
                    rec[f"ps_c_{s}"] = num(r, f"PSC{side}")
                if rec["avg_o_home"] and rec["avg_c_home"] and rec["avg_o_away"] and rec["avg_c_away"]:
                    rows.append(rec)
    return rows


def fair(row: dict, stage: str, side: str, book: str = "avg"):
    """De-vigged probability of `side` at `stage` ('o' opening / 'c' closing)."""
    prices = [row.get(f"{book}_{stage}_{s}") for s in ("home", "draw", "away")]
    if not all(prices):
        return None
    inv = [1 / p for p in prices]
    return inv[("home", "draw", "away").index(side)] / sum(inv)


def analyse(rows: list[dict], lo: float, hi: float, by: str) -> dict:
    groups = defaultdict(list)
    for r in rows:
        for side, code in (("home", "H"), ("away", "A")):
            o, c = r[f"avg_o_{side}"], r[f"avg_c_{side}"]
            ref = c if by == "closing" else o
            if not (lo <= ref <= hi):
                continue
            move = c / o - 1
            groups[bucket_of(move)].append({"won": r["ftr"] == code, "o": o, "c": c, "fair_o": fair(r, "o", side),
                                  "fair_c": fair(r, "c", side), "ps_c": r.get(f"ps_c_{side}"),
                                  "league": r["league"]})
    return bucket_stats(groups)


def bucket_of(move: float) -> str:
    return next(label for a, b, label in BUCKETS if a <= move < b)


def bucket_stats(groups: dict) -> dict:
    """Per movement bucket: n, win rate (95 % CI), mean fair prob at open/close, mean prices,
    return of a 1-unit bet at the opening and at the closing price."""
    out = {}
    for _, _, label in BUCKETS:
        g = groups.get(label, [])
        if not g:
            continue
        n = len(g)
        wins = sum(x["won"] for x in g)
        wr = wins / n
        se = math.sqrt(wr * (1 - wr) / n)
        roi_o = sum((x["o"] if x["won"] else 0) for x in g) / n - 1
        roi_c = sum((x["c"] if x["won"] else 0) for x in g) / n - 1
        ps = [x for x in g if x.get("ps_c")]
        roi_ps = (sum((x["ps_c"] if x["won"] else 0) for x in ps) / len(ps) - 1) if ps else None
        out[label] = {"n": n, "win_rate": wr, "ci95": (wr - 1.96 * se, wr + 1.96 * se),
                      "fair_open": sum(x["fair_o"] for x in g) / n, "fair_close": sum(x["fair_c"] for x in g) / n,
                      "avg_open": sum(x["o"] for x in g) / n, "avg_close": sum(x["c"] for x in g) / n,
                      "roi_open": roi_o, "roi_close": roi_c, "roi_pinnacle_close": roi_ps}
    return out


# ------------------------------------------------------------------------------ tennis
BE = "https://www.betexplorer.com"
TENNIS_BOOKS = ("STS.pl", "eFortuna.pl", "Betclic.pl", "Superbet.pl")
NOT_TOUR = re.compile(r"davis-cup|billie-jean|fed-cup|olympic|asian-games|atp-cup|united-cup|laver-cup|hopman|"
                      r"exhibition|six-kings|ultimate|world-tennis-league|mubadala|kooyong|hurlingham|next-gen")
XHR = {"X-Requested-With": "XMLHttpRequest"}
LONG = 180 * 86400  # finished matches never change: cache for months


def _be(path: str, xhr: bool = False, pause: float = 0.35) -> str:
    for attempt in range(4):
        try:
            body, _ = http_get(BE + path, headers=XHR if xhr else None, ttl=LONG)
            time.sleep(pause)
            return body.decode("utf-8", "replace")
        except HttpError as e:
            if e.status == 429:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise HttpError(BE + path, 429, "still rate-limited")


def tennis_matches(tour: str, seasons_: tuple[int, ...]) -> list[dict]:
    """Finished main-tour singles from betexplorer results pages: winner, date, list avg prices."""
    index = _be(f"/tennis/{tour}-singles/")
    slugs = sorted(set(re.findall(rf'href="/tennis/{tour}-singles/([a-z0-9-]+)/"', index)))
    slugs = [x for x in slugs if not NOT_TOUR.search(x) and not re.search(r"-\d{4}$", x)]
    out, seen = [], set()
    for slug in slugs:
        for suffix in ("",) + tuple(f"-{y}" for y in seasons_):
            try:
                page = _be(f"/tennis/{tour}-singles/{slug}{suffix}/results/")
            except HttpError:
                continue
            for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
                a = re.search(r'href="(/tennis/[^"]+/([A-Za-z0-9]{8})/)" class="in-match">(.*?)</a>', tr, re.S)
                # the current season prints dates without the year ("13.08.")
                d = re.search(r"(\d{2})\.(\d{2})\.(\d{4})?</td>", tr)
                if not a or not d or a.group(2) in seen:
                    continue
                year = int(d.group(3) or date.today().year)
                if year not in seasons_:
                    continue
                if re.search(r'title="(Retired|Walkover|Awarded|Cancelled)"|RET\.|w\.o\.', tr):
                    continue
                names = re.findall(r"<span>(?:<strong>)?(.*?)(?:</strong>)?</span>", a.group(3))
                won = [bool(re.search(rf"<strong>{re.escape(n)}</strong>", a.group(3))) for n in names]
                if len(names) != 2 or sum(won) != 1:
                    continue
                seen.add(a.group(2))
                out.append({"tour": tour, "id": a.group(2), "url": BE + a.group(1), "tournament": slug,
                            "date": f"{year}-{d.group(2)}-{d.group(1)}", "p1": names[0], "p2": names[1],
                            "winner": 0 if won[0] else 1,
                            "list_odds": [float(x) for x in re.findall(r'data-odd="([\d.]+)"', tr)[:2]]})
    return out


def tennis_prices(match_id: str) -> Optional[dict]:
    """Median opening and closing two-way prices across TENNIS_BOOKS (opening = first archived
    price; a cell without history never moved, so its opening equals its closing)."""
    frag = json.loads(_be(f"/match-odds-old/{match_id}/1/ha/0/en/", xhr=True) or "{}").get("odds", "")
    opens, closes = [[], []], [[], []]
    for tr in re.findall(r"<tr data-bid.*?</tr>", frag, re.S):
        bk = re.search(r'title="([^"]+)"', tr)
        if not bk or html.unescape(bk.group(1)) not in TENNIS_BOOKS:
            continue
        cells = re.findall(r"<td([^>]*data-odd=[^>]*)>", tr)[:2]
        if len(cells) != 2:
            continue
        for side, td in enumerate(cells):
            at = dict(re.findall(r'(data-[a-z-]+)="([^"]*)"', td))
            close = float(at["data-odd"])
            opening = close
            if at.get("data-oid"):
                hist = json.loads(_be(f"/archive-odds/{at['data-oid']}/{at['data-bid']}/{at['data-bt']}/"
                                      f"{at['data-sc']}/{at['data-hcp']}/", xhr=True) or "[]")
                if hist:
                    opening = float(hist[-1]["odd"])
            opens[side].append(opening)
            closes[side].append(close)
    if not closes[0] or not closes[1]:
        return None
    med = statistics.median
    return {"open": [med(opens[0]), med(opens[1])], "close": [med(closes[0]), med(closes[1])],
            "n_books": len(closes[0])}


def collect_tennis(out: Path, tours: tuple[str, ...], seasons_: tuple[int, ...], prefilter: tuple[float, float]) -> None:
    done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
    for tour in tours:
        matches = tennis_matches(tour, seasons_)
        todo = [m for m in matches if m["id"] not in done and m["list_odds"]
                and prefilter[0] <= min(m["list_odds"]) <= prefilter[1]]
        eprint(f"[tennis] {tour}: {len(matches)} finished matches, {len(todo)} to price")
        with out.open("a") as fh:
            for i, m in enumerate(todo, 1):
                try:
                    pr = tennis_prices(m["id"])
                except (HttpError, ValueError) as e:
                    eprint(f"[tennis] {m['id']}: {e}")
                    continue
                if pr:
                    fh.write(json.dumps({**m, **pr}) + "\n")
                    fh.flush()
                if i % 100 == 0:
                    eprint(f"[tennis] {tour}: {i}/{len(todo)}")


def fair2(a: float, b: float) -> float:
    """De-vigged probability of the first of two outcomes."""
    return (1 / a) / (1 / a + 1 / b)


def tennis_groups(rows: list[dict], lo: float, hi: float, by: str, tour: Optional[str] = None) -> dict:
    groups = defaultdict(list)
    for r in rows:
        if tour and r["tour"] != tour:
            continue
        o, c = r["open"], r["close"]
        ref = c if by == "closing" else o
        fav = 0 if ref[0] < ref[1] else 1
        if not (lo <= ref[fav] <= hi):
            continue
        groups[bucket_of(c[fav] / o[fav] - 1)].append({
            "won": r["winner"] == fav, "o": o[fav], "c": c[fav],
            "fair_o": fair2(o[fav], o[1 - fav]), "fair_c": fair2(c[fav], c[1 - fav])})
    return groups


def print_table(res: dict, title: str) -> None:
    print(f"\n## {title}")
    print(f"{'ruch kursu (otwarcie→zamknięcie)':34} {'n':>6} {'wygrane':>8} {'95% CI':>13} {'fair otw.':>9} "
          f"{'fair zamk.':>10} {'kurs otw.':>9} {'kurs zamk.':>10} {'ROI otw.':>9} {'ROI zamk.':>9} {'ROI PS zamk.':>12}")
    for label, s in res.items():
        ps = "" if s["roi_pinnacle_close"] is None else f"{s['roi_pinnacle_close']:+.1%}"
        print(f"{label:34} {s['n']:6d} {s['win_rate']:8.1%} {s['ci95'][0]:6.1%}–{s['ci95'][1]:5.1%} "
              f"{s['fair_open']:9.1%} {s['fair_close']:10.1%} {s['avg_open']:9.2f} {s['avg_close']:10.2f} "
              f"{s['roi_open']:+9.1%} {s['roi_close']:+9.1%} {ps:>12}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="sport", required=True)
    f = sub.add_parser("football")
    f.add_argument("--from", dest="first", type=int, default=1920)
    f.add_argument("--to", dest="last", type=int, default=2526)
    f.add_argument("--band", nargs=2, type=float, default=(1.30, 1.60))
    f.add_argument("--by", choices=("closing", "opening"), default="closing")
    t = sub.add_parser("tennis")
    t.add_argument("--collect", action="store_true", help="scrape betexplorer first (slow, resumable)")
    t.add_argument("--data", default=str(Path(__file__).resolve().parents[1] / "work" / "tennis_movement.jsonl"))
    t.add_argument("--seasons", default="2025,2026")
    t.add_argument("--tours", default="atp,wta")
    t.add_argument("--band", nargs=2, type=float, default=(1.30, 1.60))
    args = ap.parse_args()
    if args.sport == "tennis":
        data = Path(args.data)
        if args.collect:
            collect_tennis(data, tuple(args.tours.split(",")), tuple(int(y) for y in args.seasons.split(",")),
                           (1.15, 1.95))
        rows = [json.loads(l) for l in data.read_text().splitlines() if l.strip()]
        per_tour = ", ".join(f"{t}: {sum(r['tour'] == t for r in rows)}" for t in ("atp", "wta"))
        seasons_seen = sorted({r["date"][:4] for r in rows})
        print(f"# {len(rows)} priced matches ({per_tour}), seasons {', '.join(seasons_seen)}; "
              f"median of {', '.join(TENNIS_BOOKS)}")
        for by in ("opening", "closing"):
            print_table(bucket_stats(tennis_groups(rows, *args.band, by)), f"tenis — faworyt wg kursu {by} {args.band[0]:.2f}–{args.band[1]:.2f}")
        for tour in ("atp", "wta"):
            print_table(bucket_stats(tennis_groups(rows, *args.band, "opening", tour)), f"tenis {tour.upper()} — wg kursu otwarcia")
        return 0
    rows = football_rows(args.first, args.last)
    print(f"# {len(rows)} matches, {len({r['league'] for r in rows})} leagues, seasons {args.first}–{args.last}; "
          f"favourites with {args.by} average price {args.band[0]:.2f}–{args.band[1]:.2f}")
    print_table(analyse(rows, *args.band, by=args.by), f"piłka nożna — faworyt wg kursu {args.by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

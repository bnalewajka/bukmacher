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
import io
import math
import sys
from collections import defaultdict

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
            label = next(l for a, b, l in BUCKETS if a <= move < b)
            groups[label].append({"won": r["ftr"] == code, "o": o, "c": c, "fair_o": fair(r, "o", side),
                                  "fair_c": fair(r, "c", side), "ps_c": r.get(f"ps_c_{side}"),
                                  "league": r["league"]})
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
        ps = [x for x in g if x["ps_c"]]
        roi_ps = (sum((x["ps_c"] if x["won"] else 0) for x in ps) / len(ps) - 1) if ps else None
        out[label] = {"n": n, "win_rate": wr, "ci95": (wr - 1.96 * se, wr + 1.96 * se),
                      "fair_open": sum(x["fair_o"] for x in g) / n, "fair_close": sum(x["fair_c"] for x in g) / n,
                      "avg_open": sum(x["o"] for x in g) / n, "avg_close": sum(x["c"] for x in g) / n,
                      "roi_open": roi_o, "roi_close": roi_c, "roi_pinnacle_close": roi_ps}
    return out


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
    args = ap.parse_args()
    rows = football_rows(args.first, args.last)
    print(f"# {len(rows)} matches, {len({r['league'] for r in rows})} leagues, seasons {args.first}–{args.last}; "
          f"favourites with {args.by} average price {args.band[0]:.2f}–{args.band[1]:.2f}")
    print_table(analyse(rows, *args.band, by=args.by), f"piłka nożna — faworyt wg kursu {args.by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Turn odds.json into a ranked shortlist per odds range.

Ranges are fixed and contiguous, so every selection lands in exactly one of them (by its
median price across bookmakers): 1.10-1.19, 1.20-1.29, 1.30-1.44, 1.45-1.60. By default all
four are built in one run; --ranges picks some, --min/--max defines a custom one.

Ranking logic (why): the user wants the *most likely* outcome available inside the range,
not the highest price. So we rank by the best available de-vigged (fair)
probability, then by number of bookmakers agreeing, then by the best price. A bookmaker's
fair probability is an *upper bound* on truth for short prices (margin is loaded onto
favourites), so the final judgement must come from the analysis step, not this table.

Usage:
  python3 shortlist.py odds.json --out shortlist.json                  # all four ranges
  python3 shortlist.py odds.json --ranges 1.20-1.29,1.30-1.44 --out shortlist.json
  python3 shortlist.py odds.json --min 1.15 --max 1.25 --per-event 2 --top 40 --out shortlist.json
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict

from bk_lib import dump_json, load_json, table


AGG_FAMILIES = {"h2h", "double_chance", "dnb", "btts", "totals", "team_total", "handicap", "sets", "games"}

# (label, lower bound inclusive, upper bound exclusive) — contiguous, so no selection is counted twice.
RANGES = (("1.10-1.19", 1.10, 1.20), ("1.20-1.29", 1.20, 1.30), ("1.30-1.44", 1.30, 1.45),
          ("1.45-1.60", 1.45, 1.605))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("odds_json")
    ap.add_argument("--ranges", default="all",
                    help="'all' or comma-separated labels: " + ", ".join(r[0] for r in RANGES))
    ap.add_argument("--min", type=float, dest="lo", help="custom range, lower bound (with --max)")
    ap.add_argument("--max", type=float, dest="hi", help="custom range, upper bound inclusive")
    ap.add_argument("--per-event", type=int, default=3, help="max selections kept per event and range")
    ap.add_argument("--top", type=int, default=40, help="max selections kept per range")
    ap.add_argument("--sport")
    ap.add_argument("--exclude-markets", default="correct_score,htft,other",
                    help="market_norm categories to drop (exotic/low-liquidity)")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.lo or args.hi:
        if not (args.lo and args.hi and args.lo < args.hi):
            ap.error("--min and --max go together, with min < max")
        ranges = [(f"{args.lo:.2f}-{args.hi:.2f}", args.lo, args.hi + 0.005)]
    elif args.ranges == "all":
        ranges = list(RANGES)
    else:
        by_label = {r[0]: r for r in RANGES}
        unknown = [x for x in args.ranges.split(",") if x not in by_label]
        if unknown:
            ap.error(f"unknown range(s) {unknown}; choose from {list(by_label)}")
        ranges = [by_label[x] for x in args.ranges.split(",")]
    excl = set(args.exclude_markets.split(","))

    data = load_json(args.odds_json)
    rows = data["rows"] if isinstance(data, dict) else data
    if args.sport:
        rows = [r for r in rows if r["sport"] == args.sport]

    # aggregate the same selection across bookmakers/sources
    agg: dict[tuple, dict] = {}
    for r in rows:
        if r["market_norm"] in excl:
            continue
        # same bet across sources: canonical selection + line; keep market name only for exotic families
        fam = r["market_norm"] if r["market_norm"] in AGG_FAMILIES else r["market"].lower()
        k = (r["key"], fam, r.get("selection_norm") or str(r["selection"]).lower(), str(r.get("line")))
        a = agg.setdefault(k, {"key": r["key"], "sport": r["sport"], "competition": r.get("competition"),
                               "start_utc": r["start_utc"], "home": r["home"], "away": r["away"],
                               "market": r["market"], "market_norm": r["market_norm"], "selection": r["selection"],
                               "line": r.get("line"), "prices": [], "fair": [], "books": [], "drift": [],
                               "selection_norm": r.get("selection_norm")})
        a["prices"].append(r["odds"]); a["books"].append(f"{r['bookmaker']}@{r['odds']}")
        if r.get("fair_prob"):
            a["fair"].append(r["fair_prob"])
        if r.get("initial_odds"):
            a["drift"].append(round(r["odds"] - r["initial_odds"], 3))

    cands = []
    for a in agg.values():
        best, med = max(a["prices"]), statistics.median(a["prices"])
        fair = max(a["fair"]) if a["fair"] else None
        cands.append({
            **{k: a[k] for k in ("key", "sport", "competition", "start_utc", "home", "away", "market", "market_norm",
                                 "selection", "line")},
            "best_odds": best, "median_odds": round(med, 3), "n_books": len(a["prices"]),
            "implied_best": round(1 / best, 4), "fair_prob": round(fair, 4) if fair else None,
            "drift": round(statistics.mean(a["drift"]), 3) if a["drift"] else None,
            "books": a["books"][:8],
        })
    cands.sort(key=lambda c: (-(c["fair_prob"] or c["implied_best"]), -c["n_books"], -c["best_odds"]))

    print("# drift<0 = price shortened since opening (market backing it); fair_prob = de-vigged, upper bound")
    out = []
    for label, lo, hi in ranges:
        # the median decides the range; the best price is shown so a single generous book is visible
        in_range = [c for c in cands if lo <= c["median_odds"] < hi]
        kept, per = [], defaultdict(int)
        for c in in_range:
            if per[c["key"]] >= args.per_event:
                continue
            per[c["key"]] += 1
            kept.append(c)
            if len(kept) >= args.top:
                break
        print(f"\n# range {label}: {len(in_range)} matching selections, showing {len(kept)}")
        print(table(kept, ["start_utc", "sport", "home", "away", "market", "selection", "line", "median_odds",
                           "best_odds", "n_books", "fair_prob", "drift"], max_width=28))
        out.append({"label": label, "band": [lo, round(hi - 0.005, 2)], "candidates": kept})
    if args.out:
        dump_json({"ranges": out}, args.out)
    return 0 if any(r["candidates"] for r in out) else 2

if __name__ == "__main__":
    sys.exit(main())

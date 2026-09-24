#!/usr/bin/env python3
"""Collect bookmaker odds for the fixtures produced by fixtures.py and normalise them
into one flat list of selections (event, market, selection, line, odds, bookmaker, source).

Sources:
  espn       - odds already embedded in fixtures.json (ESPN BET moneyline/spread/total). Free.
  sofascore  - https://api.sofascore.com/api/v1/event/{id}/odds/1/all  (keyless; one partner
               bookmaker, typically bet365; ALL markets: 1X2, double chance, DNB, totals, AH,
               BTTS, sets, games, first half...). Also gives initial vs current price = drift.
  oddsapi    - The Odds API (ODDS_API_KEY). Featured markets h2h/spreads/totals from many EU
               bookmakers incl. Pinnacle (the sharp reference). Extra markets per event with
               --extra-markets (btts, draw_no_bet, alternate_spreads, alternate_totals,
               team_totals, h2h_h1, totals_h1, h2h_3_way). Costs credits: keep --max-keys low.
  apisports  - api-sports.io (APISPORTS_KEY): /odds?fixture= (football) or /odds?game= for
               basketball/hockey/volleyball; many bookmakers & markets. 1 request per event.

Usage:
  python3 odds.py --fixtures fixtures.json --out odds.json
  python3 odds.py --fixtures fixtures.json --only-keys "football|arsenal|..." --extra-markets --out odds_deep.json
Every row carries fair_prob = de-vigged probability computed inside its own market at its own
bookmaker (so it is comparable across selections), and implied_prob = 1/odds.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import timedelta
from typing import Any, Optional

from bk_lib import (HttpError, devig, dump_json, env_key, eprint, event_key, fractional_to_decimal, http_get,
                    http_get_json, implied, iso, load_json, norm_name, now_utc, parse_time, table)

# ------------------------------------------------------------------ market normalisation
MARKET_RULES = [
    (r"double chance", "double_chance"), (r"draw no bet|dnb", "dnb"), (r"both teams|btts", "btts"),
    (r"asian handicap|handicap|spread|point spread", "handicap"), (r"team total|home total|away total", "team_total"),
    (r"total sets|set handicap|sets", "sets"), (r"total games|games handicap|games", "games"),
    (r"correct score", "correct_score"), (r"half[- ]time/full[- ]time|ht/ft", "htft"),
    (r"1st half|first half|half[- ]time|h1|1st period|1st quarter|1st set", "period"),
    (r"over/under|total|goals", "totals"), (r"full time|match winner|winner|1x2|h2h|moneyline|match result|home/away", "h2h"),
]


def market_norm(name: str) -> str:
    n = (name or "").lower()
    for pat, cat in MARKET_RULES:
        if re.search(pat, n):
            return cat
    return "other"


def selection_norm(fx: dict, selection: str, line: Any) -> str:
    """Canonical selection so the same bet from different sources aggregates:
    'Chelsea' -> 'home', 'Over 1.5' -> 'over', 'X' -> 'draw', '1X' -> '1x', 'Home -1.5' -> 'home'."""
    s = str(selection or "").strip().lower()
    if line is not None:
        s = s.replace(str(line).lower(), "").strip()
    s = re.sub(r"[+-]?\d+(\.\d+)?$", "", s).strip(" :")
    hn, an = norm_name(fx.get("home", "")), norm_name(fx.get("away", ""))
    ns = norm_name(s)
    if s in ("x", "draw", "remis"):
        return "draw"
    if s in ("1", "home") or (ns and ns == hn):
        return "home"
    if s in ("2", "away") or (ns and ns == an):
        return "away"
    if s.startswith("over"):
        return "over"
    if s.startswith("under"):
        return "under"
    return s.replace(" ", "")


def row(fx: dict, market: str, selection: str, odds: Optional[float], bookmaker: str, source: str,
        line: Any = None, initial: Optional[float] = None, group: Optional[str] = None) -> Optional[dict]:
    try:
        odds = float(str(odds).replace(",", ".")) if odds is not None else None
    except ValueError:
        return None
    if not odds or odds <= 1.0:
        return None
    return {
        "key": fx["key"], "sport": fx["sport"], "competition": fx.get("competition"), "home": fx["home"],
        "away": fx["away"], "start_utc": fx["start_utc"], "market": market, "market_norm": market_norm(market),
        "selection": selection, "selection_norm": selection_norm(fx, selection, line), "line": line,
        "odds": round(float(odds), 3),
        "initial_odds": round(float(initial), 3) if initial else None,
        "implied_prob": round(implied(float(odds)), 4), "bookmaker": bookmaker, "source": source,
        "group": group or f"{source}|{bookmaker}|{fx['key']}|{market}|{line}",
        # event ids the ledger settles from (copy into a pick's `ref`)
        "refs": {k: v for k, v in (fx.get("sources") or {}).items() if k in ("espn", "oddsapi")},
    }


DC_MAP = {"1x": ("home", "draw"), "12": ("home", "away"), "x2": ("draw", "away"),
          "home/draw": ("home", "draw"), "home/away": ("home", "away"), "draw/away": ("draw", "away"),
          "home or draw": ("home", "draw"), "home or away": ("home", "away"), "draw or away": ("draw", "away")}


def add_fair_probs(rows: list[dict]) -> None:
    """De-vig inside each (source, bookmaker, event, market, line) group, but only when the
    group is a genuine set of mutually exclusive outcomes: 2 or 3 selections whose implied
    probabilities sum to a plausible book (1.00-1.30). Double chance, alternate lines listed
    together, or partial markets are NOT mutually exclusive, so a naive normalisation would be
    nonsense; double chance is derived from the same bookmaker's de-vigged 1X2 instead."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r.setdefault("fair_prob", None)
        groups[r["group"]].append(r)
    for g in groups.values():
        book = sum(implied(r["odds"]) for r in g)
        if len(g) in (2, 3) and 1.0 <= book <= 1.30:
            for r, p in zip(g, devig([r["odds"] for r in g])):
                r["fair_prob"] = round(p, 4)
                r["overround"] = round(book - 1, 4)
    # derive double chance from 1X2 of the same source+bookmaker+event
    h2h: dict[tuple, dict[str, float]] = {}
    for r in rows:
        if r["market_norm"] == "h2h" and r.get("fair_prob"):
            side = r.get("selection_norm") or "away"
            h2h.setdefault((r["source"], r["bookmaker"], r["key"]), {})[side] = r["fair_prob"]
    for r in rows:
        if r["market_norm"] == "double_chance" and not r.get("fair_prob"):
            sides = DC_MAP.get(r.get("selection_norm", "")) or DC_MAP.get(str(r["selection"]).lower())
            probs = h2h.get((r["source"], r["bookmaker"], r["key"]))
            if sides and probs and all(s in probs for s in sides):
                r["fair_prob"] = round(sum(probs[s] for s in sides), 4)
                r["fair_prob_note"] = "derived from 1X2"


# --------------------------------------------------------------------------- ESPN
def from_espn(fx: dict) -> list[dict]:
    out = []
    for o in fx.get("espn_odds") or []:
        bk = o.get("bookmaker") or "ESPN BET"
        trio = [(fx["home"], "home"), ("Draw", "draw"), (fx["away"], "away")]
        for s, side in trio:
            if o.get(f"{side}_win"):
                out.append(row(fx, "Match winner (ESPN)", s, o[f"{side}_win"], bk, "espn",
                               initial=o.get(f"{side}_win_open")))
        if o.get("total_over") and o.get("total_under"):
            line = o.get("total_over_line") or o.get("over_under")
            # the opening price only counts as drift when it was quoted on the same line
            for side, label in (("over", "Over"), ("under", "Under")):
                init = o.get(f"total_{side}_open") if o.get(f"total_{side}_open_line") == line else None
                out.append(row(fx, "Total", label, o[f"total_{side}"], bk, "espn", line=line, initial=init))
        if o.get("pointSpread_home") and o.get("pointSpread_away"):
            for side, name in (("home", fx["home"]), ("away", fx["away"])):
                line = o.get(f"pointSpread_{side}_line")
                if line is None and side == "home":
                    line = o.get("spread")
                init = (o.get(f"pointSpread_{side}_open")
                        if o.get(f"pointSpread_{side}_open_line") == line else None)
                out.append(row(fx, "Spread", name, o[f"pointSpread_{side}"], bk, "espn", line=line, initial=init))
    return [r for r in out if r]


# ------------------------------------------------------------------------ Sofascore
def from_sofascore(fx: dict, provider: int = 1) -> tuple[list[dict], Optional[str]]:
    sid = (fx.get("sources", {}).get("sofascore") or {}).get("id")
    if not sid:
        return [], None
    url = f"https://api.sofascore.com/api/v1/event/{sid}/odds/{provider}/all"
    try:
        data = http_get_json(url, headers={"Referer": "https://www.sofascore.com/"})
    except HttpError as e:
        return [], f"sofascore odds {sid}: {e}"
    out = []
    for m in data.get("markets") or []:
        if m.get("isLive") or m.get("suspended"):
            continue
        name = m.get("marketName") or "?"
        line = m.get("choiceGroup")
        grp = f"sofascore|p{provider}|{fx['key']}|{m.get('marketId')}|{line}"
        for c in m.get("choices") or []:
            sel = c.get("name") or "?"
            sel = {"1": fx["home"], "2": fx["away"], "X": "Draw"}.get(sel, sel) if market_norm(name) in ("h2h", "period") else sel
            out.append(row(fx, name, sel, fractional_to_decimal(c.get("fractionalValue")),
                           f"sofascore-provider{provider}", "sofascore", line=line,
                           initial=fractional_to_decimal(c.get("initialFractionalValue")), group=grp))
    return [r for r in out if r], None


# ---------------------------------------------------------------------- The Odds API
ODDS_API = "https://api.the-odds-api.com/v4"
GROUPS = {"football": "Soccer", "basketball": "Basketball", "hockey": "Ice Hockey", "tennis": "Tennis"}
EXTRA_MARKETS = {
    "football": "btts,draw_no_bet,alternate_spreads,alternate_totals,team_totals,h2h_h1,totals_h1,spreads_h1",
    "basketball": "alternate_spreads,alternate_totals,team_totals,h2h_h1,spreads_h1,totals_h1,h2h_q1",
    "hockey": "alternate_spreads,alternate_totals,team_totals,h2h_p1,totals_p1,h2h_3_way",
    "tennis": "alternate_spreads,alternate_totals",
}


def _sport_key_rank(sport: dict, competitions: set[str]) -> int:
    """0 = the key's title names a competition in fixtures.json, 1 = otherwise (credits go first
    to leagues we know are playing in the window)."""
    title = norm_name(sport.get("title") or "")
    return 0 if title and any(title in c or c in title for c in competitions) else 1


def _events_in_window(key: str, sport_key: str, span_from: str, span_to: str) -> int:
    """Number of events of a sport key starting in the window — /events costs no credits."""
    try:
        return len(http_get_json(f"{ODDS_API}/sports/{sport_key}/events", params={
            "apiKey": key, "dateFormat": "iso", "commenceTimeFrom": span_from, "commenceTimeTo": span_to}))
    except HttpError:
        return 0


def from_oddsapi(fixtures: list[dict], key: str, regions: str, t0, hours: float, max_keys: int,
                 extra: bool, only_keys: Optional[set[str]],
                 sport_keys: Optional[list[str]] = None, markets: str = "h2h,spreads,totals",
                 credit_budget: Optional[int] = None) -> tuple[list[dict], list[str]]:
    """Featured odds for the sport keys that actually have events in the window.

    Key discovery is free (/sports, /events); each /odds call costs len(markets) x len(regions)
    credits, so keys are ranked (competitions already in fixtures.json first, then by number of
    events in the window) and cut to --max-keys and --credit-budget."""
    errors: list[str] = []
    try:
        sports = http_get_json(f"{ODDS_API}/sports", params={"apiKey": key}, ttl=3600)
    except HttpError as e:
        return [], [f"oddsapi sports: {e}"]
    span_from, span_to = iso(t0 - timedelta(minutes=5)), iso(t0 + timedelta(hours=hours))
    if sport_keys:
        active = {s["key"] for s in sports if s.get("active")}
        errors += [f"oddsapi: sport key {k} not active" for k in sport_keys if k not in active]
        keys = [k for k in sport_keys if k in active]
    else:
        # all covered sports, not only those in fixtures.json: ESPN misses Euroleague, SHL, Liiga…
        wanted_groups = set(GROUPS.values())
        competitions = {norm_name(f.get("competition") or "") for f in fixtures} - {""}
        cands = [s for s in sports if s.get("active") and s.get("group") in wanted_groups and not s.get("has_outrights")]
        counted = [(s, _events_in_window(key, s["key"], span_from, span_to)) for s in cands]
        counted = [(s, n) for s, n in counted if n]
        counted.sort(key=lambda sn: (_sport_key_rank(sn[0], competitions), -sn[1]))
        keys = [s["key"] for s, _ in counted]
        eprint(f"[oddsapi] {len(keys)} sport keys with events in the window: "
               + ", ".join(f"{s['key']}({n})" for s, n in counted))
    cost = len(markets.split(",")) * len(regions.split(","))
    if credit_budget is not None:
        max_keys = min(max_keys, max(0, credit_budget // cost))
    if len(keys) > max_keys:
        eprint(f"[oddsapi] limiting to {max_keys} of {len(keys)} keys ({cost} credits each; --max-keys / --credit-budget)")
        keys = keys[:max_keys]
    by_key = {f["key"]: f for f in fixtures}
    out: list[dict] = []
    for sk in keys:
        sport = next((s for s, g in GROUPS.items() if g == next((x.get("group") for x in sports if x["key"] == sk), "")), "football")
        try:
            body, hdr = http_get(f"{ODDS_API}/sports/{sk}/odds", params={
                "apiKey": key, "regions": regions, "markets": markets, "oddsFormat": "decimal",
                "dateFormat": "iso", "commenceTimeFrom": span_from, "commenceTimeTo": span_to})
            import json as _j
            events = _j.loads(body)
            if hdr.get("x-requests-remaining"):
                eprint(f"[oddsapi] {sk}: {len(events)} events, credits remaining {hdr.get('x-requests-remaining')}")
        except HttpError as e:
            errors.append(f"oddsapi {sk}: {e}")
            continue
        for ev in events:
            start = parse_time(ev.get("commence_time"))
            k = event_key(sport, ev.get("home_team", ""), ev.get("away_team", ""), start)
            fx = by_key.get(k) or _fuzzy(by_key, sport, ev.get("home_team", ""), ev.get("away_team", ""), start)
            if not fx:
                fx = {"key": k, "sport": sport, "competition": ev.get("sport_title"), "home": ev.get("home_team"),
                      "away": ev.get("away_team"), "start_utc": iso(start), "sources": {}}
                by_key[k] = fx
                fixtures.append(fx)
            fx.setdefault("sources", {})["oddsapi"] = {"sport_key": sk, "event_id": ev.get("id")}
            if only_keys and fx["key"] not in only_keys:
                continue
            out += _oddsapi_rows(fx, ev)
            if extra and EXTRA_MARKETS.get(sport):
                try:
                    evd = http_get_json(f"{ODDS_API}/sports/{sk}/events/{ev['id']}/odds", params={
                        "apiKey": key, "regions": regions, "markets": EXTRA_MARKETS[sport], "oddsFormat": "decimal"})
                    out += _oddsapi_rows(fx, evd)
                except HttpError as e:
                    errors.append(f"oddsapi extra {ev.get('id')}: {e}")
    return out, errors


def _fuzzy(by_key: dict, sport: str, home: str, away: str, start) -> Optional[dict]:
    h, a = norm_name(home), norm_name(away)
    for fx in by_key.values():
        if fx["sport"] != sport:
            continue
        st = parse_time(fx["start_utc"])
        if not st or not start or abs((st - start).total_seconds()) > 1800:
            continue
        fh, fa = norm_name(fx["home"]), norm_name(fx["away"])
        if (h and (h in fh or fh in h)) and (a and (a in fa or fa in a)):
            return fx
    return None


def _oddsapi_rows(fx: dict, ev: dict) -> list[dict]:
    out = []
    for bk in ev.get("bookmakers") or []:
        for m in bk.get("markets") or []:
            mk = m.get("key", "?")
            for o in m.get("outcomes") or []:
                sel = o.get("name")
                line = o.get("point")
                desc = o.get("description")
                if desc:
                    sel = f"{desc}: {sel}"
                grp = f"oddsapi|{bk.get('key')}|{fx['key']}|{mk}|{line if mk not in ('h2h','h2h_3_way','btts','draw_no_bet','h2h_h1','h2h_p1','h2h_q1') else ''}"
                out.append(row(fx, mk, sel, o.get("price"), bk.get("key", "?"), "oddsapi", line=line, group=grp))
    return [r for r in out if r]


# ------------------------------------------------------------------------ api-sports
APISPORTS_BASE = {"football": "https://v3.football.api-sports.io", "basketball": "https://v1.basketball.api-sports.io",
                  "hockey": "https://v1.hockey.api-sports.io", "volleyball": "https://v1.volleyball.api-sports.io"}


def from_apisports(fx: dict, key: str) -> tuple[list[dict], Optional[str]]:
    aid = (fx.get("sources", {}).get("apisports") or {}).get("id")
    base = APISPORTS_BASE.get(fx["sport"])
    if not aid or not base:
        return [], None
    param = "fixture" if fx["sport"] == "football" else "game"
    try:
        data = http_get_json(f"{base}/odds", params={param: aid}, headers={"x-apisports-key": key})
    except HttpError as e:
        return [], f"apisports odds {aid}: {e}"
    if data.get("errors"):
        return [], f"apisports odds {aid}: {data['errors']}"
    out = []
    for resp in data.get("response") or []:
        for bk in resp.get("bookmakers") or []:
            for bet in bk.get("bets") or []:
                name = bet.get("name") or "?"
                for v in bet.get("values") or []:
                    val = str(v.get("value"))
                    line = None
                    mm = re.search(r"(Over|Under|Home|Away)\s*([+-]?\d+(?:\.\d+)?)", val)
                    if mm:
                        line = mm.group(2)
                    sel = {"Home": fx["home"], "Away": fx["away"]}.get(val, val)
                    grp = f"apisports|{bk.get('name')}|{fx['key']}|{bet.get('id')}|{line}"
                    out.append(row(fx, name, sel, v.get("odd"), bk.get("name", "?"), "apisports", line=line, group=grp))
    return [r for r in out if r], None


# ---------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--sources", default="espn,sofascore,oddsapi,apisports")
    ap.add_argument("--regions", default="eu", help="The Odds API regions: eu,uk,us,us2,au")
    ap.add_argument("--max-events", type=int, default=80, help="cap per-event calls (sofascore/apisports)")
    ap.add_argument("--max-keys", type=int, default=12, help="cap The Odds API sport keys per run (credits!)")
    ap.add_argument("--oddsapi-keys", help="comma separated The Odds API sport keys to query instead of "
                                           "auto-picking (e.g. soccer_uefa_nations_league,basketball_euroleague)")
    ap.add_argument("--oddsapi-markets", default="h2h,spreads,totals", help="featured markets (1 credit each per key)")
    ap.add_argument("--credit-budget", type=int, help="max The Odds API credits this run may spend on /odds")
    ap.add_argument("--extra-markets", action="store_true", help="The Odds API additional markets per event (costly)")
    ap.add_argument("--only-keys", help="comma separated fixture keys to restrict per-event calls to")
    ap.add_argument("--sport", help="restrict to one sport")
    ap.add_argument("--out")
    args = ap.parse_args()

    data = load_json(args.fixtures)
    fixtures = data["fixtures"] if isinstance(data, dict) else data
    t0 = parse_time(data.get("t0")) if isinstance(data, dict) and data.get("t0") else now_utc()
    hours = float(data.get("hours", 24)) if isinstance(data, dict) else 24
    if args.sport:
        fixtures = [f for f in fixtures if f["sport"] == args.sport]
    only = set(k.strip() for k in args.only_keys.split(",")) if args.only_keys else None
    sources = [s.strip() for s in args.sources.split(",")]
    rows: list[dict] = []
    errors: list[str] = []

    if "espn" in sources:
        for fx in fixtures:
            if only and fx["key"] not in only:
                continue
            rows += from_espn(fx)
    per_event = [f for f in fixtures if not only or f["key"] in only][: args.max_events]
    if "sofascore" in sources:
        n = 0
        for fx in per_event:
            r, e = from_sofascore(fx)
            rows += r; n += bool(r)
            if e:
                errors.append(e)
        eprint(f"[sofascore] odds for {n}/{len(per_event)} events")
    ak = env_key("APISPORTS_KEY", "API_SPORTS_KEY")
    if "apisports" in sources and ak:
        n = 0
        for fx in per_event:
            r, e = from_apisports(fx, ak)
            rows += r; n += bool(r)
            if e:
                errors.append(e)
        eprint(f"[apisports] odds for {n}/{len(per_event)} events")
    ok = env_key("ODDS_API_KEY", "THE_ODDS_API_KEY")
    if "oddsapi" in sources and ok:
        sport_keys = [k.strip() for k in args.oddsapi_keys.split(",") if k.strip()] if args.oddsapi_keys else None
        r, e = from_oddsapi(fixtures, ok, args.regions, t0, hours, args.max_keys, args.extra_markets, only,
                            sport_keys, args.oddsapi_markets, args.credit_budget)
        rows += r; errors += e
        eprint(f"[oddsapi] {len(r)} selections")
    elif "oddsapi" in sources:
        eprint("[oddsapi] skipped: ODDS_API_KEY not set")

    add_fair_probs(rows)
    for r in rows:
        r["fetched_at"] = iso(now_utc())
    for e in errors:
        eprint("[warn]", e)
    by_src = defaultdict(int)
    for r in rows:
        by_src[r["source"]] += 1
    print(f"# {len(rows)} selections from {dict(by_src)} across {len({r['key'] for r in rows})} events")
    if args.out:
        dump_json({"generated_at": iso(now_utc()), "t0": iso(t0), "errors": errors, "rows": rows}, args.out)
    else:
        print(table(rows[:60], ["start_utc", "home", "away", "market", "selection", "line", "odds", "bookmaker"]))
    return 0 if rows else 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Pull the pre-match context the analysis needs for ONE fixture: lineups and confirmed
status, missing players, recent form with scores, head-to-head, league table, the next
fixture of each side (rotation risk), venue/referee, and the ESPN summary if available.

Sources: Sofascore event endpoints (keyless) and ESPN summary (keyless). Everything
degrades gracefully: a missing endpoint prints a warning and the rest still comes out.

Usage:
  python3 context.py --fixtures fixtures.json --key "football|arsenal|chelsea|1234"
  python3 context.py --sofascore-id 12345678 [--espn soccer/eng.1/401234]
  python3 context.py ... --out context.json
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from bk_lib import HttpError, dump_json, eprint, http_get_json, iso, load_json, now_utc, parse_time

SOFA = "https://api.sofascore.com/api/v1"
HDR = {"Referer": "https://www.sofascore.com/"}


def get(url: str, warnings: list[str]) -> Optional[Any]:
    try:
        return http_get_json(url, headers=HDR)
    except HttpError as e:
        warnings.append(f"{url} -> {e.status or ''} {e.detail[:80]}")
        return None


def team_form(team_id: int, warnings: list[str], n: int = 6) -> list[dict]:
    data = get(f"{SOFA}/team/{team_id}/events/last/0", warnings)
    out = []
    for ev in (data or {}).get("events", [])[-n:]:
        hs, as_ = (ev.get("homeScore") or {}).get("current"), (ev.get("awayScore") or {}).get("current")
        out.append({"date": iso(parse_time(ev.get("startTimestamp"))), "tournament": (ev.get("tournament") or {}).get("name"),
                    "home": (ev.get("homeTeam") or {}).get("name"), "away": (ev.get("awayTeam") or {}).get("name"),
                    "score": f"{hs}-{as_}", "winner": ev.get("winnerCode")})
    return out


def team_next(team_id: int, warnings: list[str], n: int = 2) -> list[dict]:
    data = get(f"{SOFA}/team/{team_id}/events/next/0", warnings)
    out = []
    for ev in (data or {}).get("events", [])[:n]:
        out.append({"date": iso(parse_time(ev.get("startTimestamp"))), "tournament": (ev.get("tournament") or {}).get("name"),
                    "home": (ev.get("homeTeam") or {}).get("name"), "away": (ev.get("awayTeam") or {}).get("name")})
    return out


def sofascore_context(sid: int, warnings: list[str]) -> dict:
    ctx: dict[str, Any] = {"sofascore_id": sid}
    ev = (get(f"{SOFA}/event/{sid}", warnings) or {}).get("event") or {}
    home, away = ev.get("homeTeam") or {}, ev.get("awayTeam") or {}
    ctx["event"] = {
        "home": home.get("name"), "away": away.get("name"), "start_utc": iso(parse_time(ev.get("startTimestamp"))),
        "tournament": (ev.get("tournament") or {}).get("name"),
        "category": ((ev.get("tournament") or {}).get("category") or {}).get("name"),
        "round": (ev.get("roundInfo") or {}).get("name") or (ev.get("roundInfo") or {}).get("round"),
        "status": (ev.get("status") or {}).get("description"),
        "venue": ((ev.get("venue") or {}).get("stadium") or {}).get("name") or (ev.get("venue") or {}).get("name"),
        "city": ((ev.get("venue") or {}).get("city") or {}).get("name"),
        "referee": (ev.get("referee") or {}).get("name"),
        "home_manager": (ev.get("homeManager") or {}).get("name") if isinstance(ev.get("homeManager"), dict) else None,
        "away_manager": (ev.get("awayManager") or {}).get("name") if isinstance(ev.get("awayManager"), dict) else None,
        "best_of": ev.get("bestOf"), "ground_type": ev.get("groundType"),
    }
    # lineups + absences
    lu = get(f"{SOFA}/event/{sid}/lineups", warnings)
    if lu:
        ctx["lineups_confirmed"] = bool(lu.get("confirmed"))
        for side in ("home", "away"):
            s = lu.get(side) or {}
            starters = [f"{(p.get('player') or {}).get('name')} ({(p.get('player') or {}).get('position', '')})"
                        for p in s.get("players") or [] if not p.get("substitute")]
            missing = []
            for mp in s.get("missingPlayers") or []:
                p = mp.get("player") or {}
                missing.append({"name": p.get("name"), "position": p.get("position"),
                                "type": mp.get("type"), "reason": mp.get("reason")})
            ctx[f"{side}_formation"] = s.get("formation")
            ctx[f"{side}_starters"] = starters
            ctx[f"{side}_missing"] = missing
    # form / position / rating
    pf = get(f"{SOFA}/event/{sid}/pregame-form", warnings)
    if pf:
        ctx["pregame_form"] = {side: {"form": (pf.get(f"{side}Team") or {}).get("form"),
                                      "position": (pf.get(f"{side}Team") or {}).get("position"),
                                      "avg_rating": (pf.get(f"{side}Team") or {}).get("avgRating")} for side in ("home", "away")}
    h2h = get(f"{SOFA}/event/{sid}/h2h", warnings)
    if h2h:
        ctx["h2h"] = h2h.get("teamDuel") or h2h
    # recent results with scores and next fixtures (schedule congestion / rotation risk)
    if home.get("id"):
        ctx["home_last"] = team_form(home["id"], warnings)
        ctx["home_next"] = team_next(home["id"], warnings)
    if away.get("id"):
        ctx["away_last"] = team_form(away["id"], warnings)
        ctx["away_next"] = team_next(away["id"], warnings)
    # standings
    ut, season = (ev.get("tournament") or {}).get("uniqueTournament") or {}, ev.get("season") or {}
    if ut.get("id") and season.get("id"):
        st = get(f"{SOFA}/unique-tournament/{ut['id']}/season/{season['id']}/standings/total", warnings)
        rows = []
        for tbl in (st or {}).get("standings", []):
            for r in tbl.get("rows", []):
                rows.append({"pos": r.get("position"), "team": (r.get("team") or {}).get("name"), "P": r.get("matches"),
                             "W": r.get("wins"), "D": r.get("draws"), "L": r.get("losses"),
                             "GF": r.get("scoresFor"), "GA": r.get("scoresAgainst"), "pts": r.get("points")})
        if rows:
            ctx["standings"] = rows
    return ctx


def espn_context(espn: str, warnings: list[str]) -> dict:
    """espn = 'soccer/eng.1/401234567' (sport/league/event_id)."""
    try:
        sport, league, eid = espn.split("/")
    except ValueError:
        warnings.append(f"bad --espn value {espn!r}; expected sport/league/event_id")
        return {}
    data = get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={eid}", warnings) or {}
    out: dict[str, Any] = {}
    gi = data.get("gameInfo") or {}
    out["venue"] = (gi.get("venue") or {}).get("fullName")
    out["weather"] = gi.get("weather")
    out["officials"] = [o.get("displayName") for o in gi.get("officials") or []]
    out["attendance"] = gi.get("attendance")
    out["form"] = []
    for tf in data.get("form") or []:
        out["form"].append({"team": (tf.get("team") or {}).get("displayName"),
                            "last": [f"{e.get('gameResult')} {e.get('homeTeamScore')}-{e.get('awayTeamScore')} vs {(e.get('opponent') or {}).get('displayName')}"
                                     for e in tf.get("events") or []]})
    out["rosters"] = []
    for r in data.get("rosters") or []:
        starters = [(p.get("athlete") or {}).get("displayName") for p in r.get("roster") or [] if p.get("starter")]
        out["rosters"].append({"team": (r.get("team") or {}).get("displayName"), "formation": r.get("formation"),
                               "starters": starters, "has_lineup": bool(starters)})
    inj = data.get("injuries") or []
    out["injuries"] = [{"team": (i.get("team") or {}).get("displayName"),
                        "players": [f"{(p.get('athlete') or {}).get('displayName')} - {p.get('status')} {((p.get('details') or {}).get('type') or '')}"
                                    for p in i.get("injuries") or []]} for i in inj]
    out["predictor"] = data.get("predictor")
    out["odds"] = [{"provider": (o.get("provider") or {}).get("name"), "details": o.get("details"),
                    "overUnder": o.get("overUnder")} for o in (data.get("pickcenter") or data.get("odds") or [])]
    return out


def print_summary(ctx: dict) -> None:
    e = ctx.get("event") or {}
    print(f"== {e.get('home')} vs {e.get('away')} | {e.get('tournament')} ({e.get('category')}) {e.get('round') or ''}")
    print(f"   start {e.get('start_utc')} | venue {e.get('venue')} {e.get('city') or ''} | referee {e.get('referee')} | status {e.get('status')}")
    if "lineups_confirmed" in ctx:
        print(f"   lineups confirmed: {ctx['lineups_confirmed']} | formations {ctx.get('home_formation')} / {ctx.get('away_formation')}")
        for side in ("home", "away"):
            miss = ctx.get(f"{side}_missing") or []
            if miss:
                print(f"   {side} missing: " + "; ".join(f"{m['name']} ({m.get('reason')})" for m in miss))
            st = ctx.get(f"{side}_starters") or []
            if st:
                print(f"   {side} XI: " + ", ".join(st[:11]))
    pf = ctx.get("pregame_form")
    if pf:
        for side in ("home", "away"):
            print(f"   {side} form {pf[side].get('form')} pos {pf[side].get('position')} rating {pf[side].get('avg_rating')}")
    for side in ("home", "away"):
        for m in ctx.get(f"{side}_last") or []:
            print(f"   {side} last: {m['date'][:10]} {m['home']} {m['score']} {m['away']} [{m['tournament']}]")
        for m in ctx.get(f"{side}_next") or []:
            print(f"   {side} next: {m['date'][:16]} {m['home']} v {m['away']} [{m['tournament']}]")
    if ctx.get("h2h"):
        print(f"   h2h: {ctx['h2h']}")
    for r in (ctx.get("standings") or [])[:24]:
        print(f"   table {r['pos']:>2} {str(r['team'])[:24]:24} P{r['P']} W{r['W']} D{r['D']} L{r['L']} {r['GF']}:{r['GA']} pts {r['pts']}")
    es = ctx.get("espn") or {}
    if es:
        print(f"   espn: venue {es.get('venue')} weather {es.get('weather')} officials {es.get('officials')}")
        for f in es.get("form") or []:
            print(f"   espn form {f['team']}: {f['last']}")
        for r in es.get("rosters") or []:
            print(f"   espn roster {r['team']} lineup={r['has_lineup']} {r.get('formation') or ''}: {', '.join(x for x in r['starters'] if x)}")
        for i in es.get("injuries") or []:
            print(f"   espn injuries {i['team']}: {i['players']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures")
    ap.add_argument("--key", help="fixture key from fixtures.json")
    ap.add_argument("--sofascore-id", type=int)
    ap.add_argument("--espn", help="sport/league/event_id for the ESPN summary endpoint")
    ap.add_argument("--out")
    args = ap.parse_args()
    warnings: list[str] = []
    sid, espn = args.sofascore_id, args.espn
    if args.fixtures and args.key:
        data = load_json(args.fixtures)
        fx = next((f for f in data["fixtures"] if f["key"] == args.key), None)
        if not fx:
            eprint("key not found in fixtures"); return 1
        sid = sid or (fx["sources"].get("sofascore") or {}).get("id")
        es = fx["sources"].get("espn") or {}
        if not espn and es.get("event_id"):
            espn = f"{es['sport']}/{es['league']}/{es['event_id']}"
    if not sid and not espn:
        eprint("need --sofascore-id or --espn or --fixtures+--key"); return 1
    ctx: dict[str, Any] = {"fetched_at": iso(now_utc())}
    if sid:
        ctx.update(sofascore_context(sid, warnings))
    if espn:
        ctx["espn"] = espn_context(espn, warnings)
    ctx["warnings"] = warnings
    print_summary(ctx)
    for w in warnings:
        eprint("[warn]", w)
    if args.out:
        dump_json(ctx, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

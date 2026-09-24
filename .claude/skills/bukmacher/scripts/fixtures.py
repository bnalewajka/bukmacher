#!/usr/bin/env python3
"""List upcoming fixtures (football, basketball, hockey, tennis, volleyball) that
start inside the next N hours, merged from several sources.

Sources (each optional; a failing source is reported, not fatal):
  sofascore  - keyless, widest coverage (all five sports, clubs, national teams,
               cups, qualifiers, ATP/WTA/Challenger, volleyball leagues & FIVB).
               Unofficial JSON API; datacentre IPs sometimes get 403.
  espn       - keyless, official-ish JSON; soccer (curated league slugs), NBA/WNBA/
               college basketball, NHL, ATP/WTA. Also carries ESPN BET odds inline.
  apisports  - needs APISPORTS_KEY (api-sports.io, free 100 req/day per sport API);
               football/basketball/hockey/volleyball. Gives ids reused by odds.py.

Usage:
  python3 fixtures.py --hours 4 --now 2026-09-24T16:04:23Z --out fixtures.json
  python3 fixtures.py --hours 12 --sports football,tennis --sources sofascore,espn
Always pass --now with the clock.py verified time so the window is anchored correctly.
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from typing import Any, Optional

from bk_lib import (SPORTS, SPORT_MAP, HttpError, american_to_decimal, date_span, dump_json, env_key,
                    eprint, event_key, http_get_json, in_window, iso, now_utc, parse_time, table)

# ESPN league slugs. Unknown/inactive slugs just return 404/empty and are skipped.
ESPN_LEAGUES = {
    "football": [
        "uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.nations", "uefa.euro", "uefa.euroq",
        "fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.concacaf", "fifa.worldq.afc",
        "fifa.worldq.caf", "fifa.friendly", "conmebol.libertadores", "conmebol.sudamericana", "conmebol.america",
        "concacaf.nations.league", "concacaf.gold", "afc.asian.cup", "caf.nations", "uefa.wchampions",
        "eng.1", "eng.2", "eng.fa", "eng.league_cup", "esp.1", "esp.2", "esp.copa_del_rey", "ger.1", "ger.2",
        "ger.dfb_pokal", "ita.1", "ita.2", "ita.coppa_italia", "fra.1", "fra.2", "fra.coupe_de_france",
        "ned.1", "por.1", "bel.1", "tur.1", "sco.1", "pol.1", "aut.1", "sui.1", "den.1", "nor.1", "swe.1",
        "gre.1", "cze.1", "cro.1", "rus.1", "ukr.1", "usa.1", "mex.1", "bra.1", "arg.1", "col.1", "chi.1",
        "jpn.1", "aus.1", "ksa.1", "eng.w.1", "usa.nwsl",
    ],
    "basketball": ["nba", "wnba", "mens-college-basketball", "womens-college-basketball"],
    "hockey": ["nhl", "mens-college-hockey"],
    "tennis": ["atp", "wta"],
}

SOFA_STATUS_SKIP = {"finished", "canceled", "cancelled", "postponed", "interrupted", "suspended"}


# ----------------------------------------------------------------------------- ESPN
def _espn_competitions(ev: dict) -> list[dict]:
    comps = ev.get("competitions") or []
    if not comps:
        for g in ev.get("groupings", []) or []:
            comps.extend(g.get("competitions", []) or [])
    return comps


def _espn_competitor_name(c: dict) -> str:
    for path in (("team", "displayName"), ("team", "name"), ("athlete", "displayName"), ("athlete", "shortName"),
                 ("roster", "displayName")):
        cur: Any = c
        for p in path:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if cur:
            return str(cur)
    return c.get("displayName") or c.get("name") or "?"


def _espn_odds(comp: dict) -> list[dict]:
    out = []
    for o in comp.get("odds") or []:
        prov = (o.get("provider") or {}).get("name") or "ESPN"
        rec: dict[str, Any] = {"bookmaker": prov, "details": o.get("details"), "over_under": o.get("overUnder"),
                               "spread": o.get("spread")}
        for side in ("homeTeamOdds", "awayTeamOdds", "drawOdds"):
            s = o.get(side) or {}
            dec = None
            cur = s.get("current") or {}
            ml = cur.get("moneyLine") if isinstance(cur, dict) else None
            if isinstance(ml, dict):
                dec = ml.get("decimal")
            if dec is None and s.get("moneyLine") is not None:
                dec = american_to_decimal(s.get("moneyLine"))
            if dec is None and o.get("moneyline") and side != "drawOdds":
                pass
            rec[side.replace("TeamOdds", "").replace("Odds", "") + "_win"] = dec
        # ESPN also exposes "moneyline"/"pointSpread"/"total" objects in newer payloads
        for grp in ("moneyline", "pointSpread", "total"):
            g = o.get(grp)
            if isinstance(g, dict):
                for side in ("home", "away", "draw", "over", "under"):
                    v = g.get(side) or {}
                    close = (v.get("close") or v.get("current") or {}) if isinstance(v, dict) else {}
                    if isinstance(close, dict) and close.get("decimal"):
                        rec[f"{grp}_{side}"] = close.get("decimal")
                        if close.get("line"):
                            rec[f"{grp}_{side}_line"] = close.get("line")
        out.append(rec)
    return out


def fetch_espn(sport: str, t0, hours: float, leagues: Optional[list[str]] = None) -> tuple[list[dict], list[str]]:
    espn_sport = SPORT_MAP[sport]["espn"]
    if not espn_sport:
        return [], []
    days = date_span(t0, hours)
    dates = f"{days[0].replace('-', '')}-{days[-1].replace('-', '')}" if len(days) > 1 else days[0].replace("-", "")
    rows, errors = [], []
    for lg in leagues or ESPN_LEAGUES.get(sport, []):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{lg}/scoreboard"
        try:
            data = http_get_json(url, params={"dates": dates, "limit": 500})
        except HttpError as e:
            if e.status not in (400, 404):
                errors.append(f"espn {lg}: {e}")
            continue
        league_name = ((data.get("leagues") or [{}])[0]).get("name") or lg
        for ev in data.get("events") or []:
            for comp in _espn_competitions(ev):
                start = parse_time(comp.get("date") or ev.get("date"))
                state = (((comp.get("status") or ev.get("status") or {}).get("type") or {}).get("state")) or ""
                if state in ("post",) or not in_window(start, t0, hours):
                    continue
                comps = comp.get("competitors") or []
                home = next((c for c in comps if c.get("homeAway") == "home"), comps[0] if comps else {})
                away = next((c for c in comps if c.get("homeAway") == "away"), comps[1] if len(comps) > 1 else {})
                h, a = _espn_competitor_name(home), _espn_competitor_name(away)
                rows.append({
                    "sport": sport, "competition": league_name if sport != "tennis" else f"{league_name}: {ev.get('name', '')}",
                    "category": lg, "home": h, "away": a, "start_utc": iso(start), "status": state or "pre",
                    "neutral": bool(comp.get("neutralSite")),
                    "venue": ((comp.get("venue") or {}).get("fullName")),
                    "sources": {"espn": {"sport": espn_sport, "league": lg, "event_id": ev.get("id"),
                                         "competition_id": comp.get("id")}},
                    "espn_odds": _espn_odds(comp),
                })
    return rows, errors


# ------------------------------------------------------------------------ Sofascore
def fetch_sofascore(sport: str, t0, hours: float) -> tuple[list[dict], list[str]]:
    slug = SPORT_MAP[sport]["sofascore"]
    rows, errors, seen = [], [], set()
    for day in date_span(t0, hours):
        for suffix in ("", "/inverse"):
            url = f"https://api.sofascore.com/api/v1/sport/{slug}/scheduled-events/{day}{suffix}"
            try:
                data = http_get_json(url, headers={"Referer": "https://www.sofascore.com/"})
            except HttpError as e:
                errors.append(f"sofascore {slug} {day}{suffix}: {e}")
                continue
            for ev in data.get("events") or []:
                if ev.get("id") in seen:
                    continue
                start = parse_time(ev.get("startTimestamp"))
                stype = ((ev.get("status") or {}).get("type") or "").lower()
                if stype in SOFA_STATUS_SKIP or not in_window(start, t0, hours):
                    continue
                seen.add(ev.get("id"))
                t = ev.get("tournament") or {}
                cat = (t.get("category") or {}).get("name") or ""
                ut = t.get("uniqueTournament") or {}
                rows.append({
                    "sport": sport,
                    "competition": ut.get("name") or t.get("name") or "?",
                    "category": cat,
                    "round": (ev.get("roundInfo") or {}).get("name") or (ev.get("roundInfo") or {}).get("round"),
                    "home": (ev.get("homeTeam") or {}).get("name") or "?",
                    "away": (ev.get("awayTeam") or {}).get("name") or "?",
                    "start_utc": iso(start), "status": stype or "notstarted",
                    "sources": {"sofascore": {"id": ev.get("id"), "slug": ev.get("slug"), "customId": ev.get("customId"),
                                              "unique_tournament_id": ut.get("id"), "season_id": (ev.get("season") or {}).get("id"),
                                              "home_id": (ev.get("homeTeam") or {}).get("id"),
                                              "away_id": (ev.get("awayTeam") or {}).get("id")}},
                })
    return rows, errors


# ------------------------------------------------------------------------ api-sports
APISPORTS_BASE = {"football": "https://v3.football.api-sports.io", "basketball": "https://v1.basketball.api-sports.io",
                  "hockey": "https://v1.hockey.api-sports.io", "volleyball": "https://v1.volleyball.api-sports.io"}


def fetch_apisports(sport: str, t0, hours: float, key: str) -> tuple[list[dict], list[str]]:
    base = APISPORTS_BASE.get(sport)
    if not base:
        return [], []
    rows, errors = [], []
    for day in date_span(t0, hours):
        path = "/fixtures" if sport == "football" else "/games"
        try:
            data = http_get_json(base + path, params={"date": day, "timezone": "UTC"}, headers={"x-apisports-key": key})
        except HttpError as e:
            errors.append(f"apisports {sport} {day}: {e}")
            continue
        if data.get("errors"):
            errors.append(f"apisports {sport} {day}: {data['errors']}")
            continue
        for it in data.get("response") or []:
            if sport == "football":
                fx = it.get("fixture") or {}
                start, fid, status = parse_time(fx.get("date")), fx.get("id"), (fx.get("status") or {}).get("short")
                league, country = (it.get("league") or {}).get("name"), (it.get("league") or {}).get("country")
            else:
                start, fid, status = parse_time(it.get("date")), it.get("id"), (it.get("status") or {}).get("short")
                league, country = (it.get("league") or {}).get("name"), (it.get("country") or {}).get("name")
            if status not in (None, "NS", "TBD") or not in_window(start, t0, hours):
                continue
            teams = it.get("teams") or {}
            rows.append({
                "sport": sport, "competition": league or "?", "category": country or "",
                "home": (teams.get("home") or {}).get("name") or "?", "away": (teams.get("away") or {}).get("name") or "?",
                "start_utc": iso(start), "status": "NS",
                "sources": {"apisports": {"id": fid, "league_id": (it.get("league") or {}).get("id")}},
            })
    return rows, errors


# --------------------------------------------------------------------------- merge
def merge(rows: list[dict], t0) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in rows:
        k = event_key(r["sport"], r["home"], r["away"], parse_time(r["start_utc"]))
        if k in merged:
            m = merged[k]
            m["sources"].update(r.get("sources", {}))
            if r.get("espn_odds"):
                m.setdefault("espn_odds", []).extend(r["espn_odds"])
            if "sofascore" in r.get("sources", {}):  # prefer Sofascore's competition naming
                m["competition"], m["category"] = r["competition"], r.get("category", m.get("category"))
                m["round"] = r.get("round")
        else:
            merged[k] = dict(r, key=k)
    out = list(merged.values())
    for m in out:
        st = parse_time(m["start_utc"])
        m["minutes_to_start"] = int((st - t0).total_seconds() // 60) if st else None
    out.sort(key=lambda m: (m["start_utc"] or "", m["sport"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=4)
    ap.add_argument("--now", help="verified UTC time (ISO) from clock.py; default: system clock")
    ap.add_argument("--sports", default=",".join(SPORTS))
    ap.add_argument("--sources", default="sofascore,espn,apisports")
    ap.add_argument("--espn-leagues", help="override ESPN slugs for a single-sport run, comma separated")
    ap.add_argument("--grace", type=int, default=0, help="also include events that started up to N minutes ago")
    ap.add_argument("--out", help="write JSON here (default: print table only)")
    args = ap.parse_args()

    t0 = parse_time(args.now) if args.now else now_utc()
    if t0 is None:
        eprint("bad --now value"); return 1
    sports = [s.strip() for s in args.sports.split(",") if s.strip() in SPORTS]
    sources = [s.strip() for s in args.sources.split(",")]
    key = env_key("APISPORTS_KEY", "API_SPORTS_KEY")

    all_rows, all_errors = [], []
    for sport in sports:
        if "sofascore" in sources:
            r, e = fetch_sofascore(sport, t0, args.hours); all_rows += r; all_errors += e
            eprint(f"[sofascore] {sport}: {len(r)} events")
        if "espn" in sources:
            lg = args.espn_leagues.split(",") if args.espn_leagues and len(sports) == 1 else None
            r, e = fetch_espn(sport, t0, args.hours, lg); all_rows += r; all_errors += e
            eprint(f"[espn] {sport}: {len(r)} events")
        if "apisports" in sources and key:
            r, e = fetch_apisports(sport, t0, args.hours, key); all_rows += r; all_errors += e
            eprint(f"[apisports] {sport}: {len(r)} events")
        elif "apisports" in sources and sport == sports[0]:
            eprint("[apisports] skipped: APISPORTS_KEY not set")

    fixtures = merge(all_rows, t0)
    for err in all_errors:
        eprint("[warn]", err)

    print(f"# window: {iso(t0)} -> {iso(t0 + timedelta(hours=args.hours))}  ({len(fixtures)} fixtures)")
    print(table(fixtures, ["start_utc", "minutes_to_start", "sport", "competition", "home", "away"]))
    if args.out:
        dump_json({"generated_at": iso(now_utc()), "t0": iso(t0), "hours": args.hours, "errors": all_errors,
                   "fixtures": fixtures}, args.out)
    if not fixtures and all_errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

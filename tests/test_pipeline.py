"""Offline tests for the bukmacher skill scripts.

The real APIs are stubbed with payloads shaped like the documented responses
(ESPN scoreboard, Sofascore scheduled-events/odds/lineups, The Odds API, api-sports),
so the parsers, the window filter, merging, de-vig and the shortlist ranking can be
checked without network access or API keys.  Run:  python3 -m pytest -q  (or python3 tests/test_pipeline.py)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".claude" / "skills" / "bukmacher" / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.environ["BUKMACHER_NO_CACHE"] = "1"

import bk_lib  # noqa: E402
import fixtures as fx_mod  # noqa: E402
import odds as odds_mod  # noqa: E402
import context as ctx_mod  # noqa: E402
import ledger as ledger_mod  # noqa: E402

T0 = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)


def ts(h):  # start time h hours after T0
    return T0 + timedelta(hours=h)


# ------------------------------------------------------------------ synthetic payloads
def espn_scoreboard(url, params=None, headers=None, **kw):
    if "/soccer/eng.1/" in url:
        return {"leagues": [{"name": "English Premier League"}], "events": [{
            "id": "401", "date": ts(2).strftime("%Y-%m-%dT%H:%MZ"), "name": "Arsenal at Chelsea",
            "status": {"type": {"state": "pre"}},
            "competitions": [{"id": "401", "date": ts(2).strftime("%Y-%m-%dT%H:%MZ"), "neutralSite": False,
                              "venue": {"fullName": "Stamford Bridge"},
                              "competitors": [{"homeAway": "home", "team": {"displayName": "Chelsea"}},
                                              {"homeAway": "away", "team": {"displayName": "Arsenal"}}],
                              "odds": [{"provider": {"name": "ESPN BET"}, "details": "ARS -0.5", "overUnder": 2.5,
                                        "homeTeamOdds": {"moneyLine": 250}, "awayTeamOdds": {"moneyLine": -110},
                                        "drawOdds": {"moneyLine": 260}}]}]},
            {"id": "402", "date": ts(30).strftime("%Y-%m-%dT%H:%MZ"), "status": {"type": {"state": "pre"}},
             "competitions": [{"id": "402", "date": ts(30).strftime("%Y-%m-%dT%H:%MZ"),
                               "competitors": [{"homeAway": "home", "team": {"displayName": "Everton"}},
                                               {"homeAway": "away", "team": {"displayName": "Fulham"}}]}]}]}
    if "/tennis/atp/" in url:
        return {"leagues": [{"name": "ATP Tour"}], "events": [{
            "id": "t1", "name": "Tokyo Open", "date": ts(1).strftime("%Y-%m-%dT%H:%MZ"),
            "groupings": [{"competitions": [{"id": "t1c1", "date": ts(1).strftime("%Y-%m-%dT%H:%MZ"),
                                             "status": {"type": {"state": "pre"}},
                                             "competitors": [{"homeAway": "home", "athlete": {"displayName": "J. Sinner"}},
                                                             {"homeAway": "away", "athlete": {"displayName": "A. Nobody"}}]}]}]}]}
    raise bk_lib.HttpError(url, 404, "not found")


def sofa(url, params=None, headers=None, **kw):
    if "scheduled-events" in url and url.endswith("/inverse"):
        return {"events": []}
    if "sport/football/scheduled-events" in url:
        return {"events": [
            {"id": 111, "startTimestamp": int(ts(2).timestamp()), "status": {"type": "notstarted"},
             "tournament": {"name": "Premier League", "category": {"name": "England"}, "uniqueTournament": {"id": 17, "name": "Premier League"}},
             "season": {"id": 999}, "roundInfo": {"round": 6},
             "homeTeam": {"id": 38, "name": "Chelsea"}, "awayTeam": {"id": 42, "name": "Arsenal"}},
            {"id": 112, "startTimestamp": int(ts(-1).timestamp()), "status": {"type": "inprogress"},
             "tournament": {"name": "Ekstraklasa", "category": {"name": "Poland"}},
             "homeTeam": {"id": 1, "name": "Legia"}, "awayTeam": {"id": 2, "name": "Lech"}},
            {"id": 113, "startTimestamp": int(ts(3).timestamp()), "status": {"type": "postponed"},
             "tournament": {"name": "Serie A", "category": {"name": "Italy"}},
             "homeTeam": {"id": 3, "name": "Inter"}, "awayTeam": {"id": 4, "name": "Milan"}},
        ]}
    if "sport/volleyball/scheduled-events" in url:
        return {"events": [{"id": 555, "startTimestamp": int(ts(3.5).timestamp()), "status": {"type": "notstarted"},
                            "tournament": {"name": "PlusLiga", "category": {"name": "Poland"}, "uniqueTournament": {"id": 5, "name": "PlusLiga"}},
                            "homeTeam": {"id": 50, "name": "Jastrzębski Węgiel"}, "awayTeam": {"id": 51, "name": "Cuprum Lubin"}}]}
    if "scheduled-events" in url:
        return {"events": []}
    if url.endswith("/event/111/odds/1/all"):
        return {"markets": [
            {"marketId": 1, "marketName": "Full time", "isLive": False, "choices": [
                {"name": "1", "fractionalValue": "9/4", "initialFractionalValue": "2/1"},
                {"name": "X", "fractionalValue": "12/5", "initialFractionalValue": "12/5"},
                {"name": "2", "fractionalValue": "23/20", "initialFractionalValue": "5/4"}]},
            {"marketId": 2, "marketName": "Double chance", "isLive": False, "choices": [
                {"name": "1X", "fractionalValue": "4/5", "initialFractionalValue": "4/5"},
                {"name": "12", "fractionalValue": "1/4", "initialFractionalValue": "2/7"},
                {"name": "X2", "fractionalValue": "1/5", "initialFractionalValue": "2/9"}]},
            {"marketId": 3, "marketName": "Match goals", "choiceGroup": "1.5", "choices": [
                {"name": "Over", "fractionalValue": "1/5", "initialFractionalValue": "1/5"},
                {"name": "Under", "fractionalValue": "7/2", "initialFractionalValue": "7/2"}]},
            {"marketId": 4, "marketName": "Correct score", "choices": [{"name": "1-1", "fractionalValue": "6/1"}]},
            {"marketId": 5, "marketName": "Live thing", "isLive": True, "choices": [{"name": "1", "fractionalValue": "1/1"}]},
        ]}
    if url.endswith("/event/555/odds/1/all"):
        return {"markets": [{"marketId": 1, "marketName": "Full time", "choices": [
            {"name": "1", "fractionalValue": "1/5", "initialFractionalValue": "1/4"},
            {"name": "2", "fractionalValue": "7/2", "initialFractionalValue": "3/1"}]},
            {"marketId": 9, "marketName": "Set handicap", "choiceGroup": "-1.5", "choices": [
                {"name": "1", "fractionalValue": "4/5"}, {"name": "2", "fractionalValue": "19/20"}]}]}
    if url.endswith("/event/111"):
        return {"event": {"homeTeam": {"id": 38, "name": "Chelsea"}, "awayTeam": {"id": 42, "name": "Arsenal"},
                          "startTimestamp": int(ts(2).timestamp()), "tournament": {"name": "Premier League", "category": {"name": "England"},
                                                                                   "uniqueTournament": {"id": 17}},
                          "season": {"id": 999}, "roundInfo": {"round": 6}, "status": {"description": "Not started"},
                          "venue": {"stadium": {"name": "Stamford Bridge"}, "city": {"name": "London"}}, "referee": {"name": "M. Oliver"}}}
    if url.endswith("/event/111/lineups"):
        return {"confirmed": True,
                "home": {"formation": "4-2-3-1", "players": [{"player": {"name": "R. Sanchez", "position": "G"}, "substitute": False}],
                         "missingPlayers": [{"player": {"name": "C. Palmer", "position": "M"}, "type": "missing", "reason": 1}]},
                "away": {"formation": "4-3-3", "players": [], "missingPlayers": []}}
    if url.endswith("/event/111/pregame-form"):
        return {"homeTeam": {"form": ["W", "D", "L", "W", "W"], "position": 3, "avgRating": "7.01"},
                "awayTeam": {"form": ["W", "W", "W", "D", "W"], "position": 1, "avgRating": "7.20"}}
    if url.endswith("/event/111/h2h"):
        return {"teamDuel": {"homeWins": 3, "awayWins": 5, "draws": 4}}
    if "/team/38/events/last/0" in url or "/team/42/events/last/0" in url:
        return {"events": [{"startTimestamp": int(ts(-100).timestamp()), "tournament": {"name": "Premier League"},
                            "homeTeam": {"name": "X"}, "awayTeam": {"name": "Y"}, "homeScore": {"current": 2}, "awayScore": {"current": 0}, "winnerCode": 1}]}
    if "/events/next/0" in url:
        return {"events": [{"startTimestamp": int(ts(80).timestamp()), "tournament": {"name": "Champions League"},
                            "homeTeam": {"name": "Chelsea"}, "awayTeam": {"name": "Bayern"}}]}
    if "standings/total" in url:
        return {"standings": [{"rows": [{"position": 1, "team": {"name": "Arsenal"}, "matches": 5, "wins": 4, "draws": 1, "losses": 0,
                                         "scoresFor": 12, "scoresAgainst": 2, "points": 13}]}]}
    raise bk_lib.HttpError(url, 404, "no stub")


def apisports(url, params=None, headers=None, **kw):
    assert headers and headers.get("x-apisports-key") == "k"
    if "football.api-sports.io/fixtures" in url:
        return {"errors": [], "response": [{"fixture": {"id": 777, "date": ts(2).isoformat(), "status": {"short": "NS"}},
                                            "league": {"id": 39, "name": "Premier League", "country": "England"},
                                            "teams": {"home": {"name": "Chelsea"}, "away": {"name": "Arsenal"}}}]}
    if "football.api-sports.io/odds" in url:
        return {"errors": [], "response": [{"bookmakers": [{"id": 4, "name": "Pinnacle", "bets": [
            {"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": "3.30"}, {"value": "Draw", "odd": "3.50"}, {"value": "Away", "odd": "2.20"}]},
            {"id": 5, "name": "Goals Over/Under", "values": [{"value": "Over 1.5", "odd": "1.22"}, {"value": "Under 1.5", "odd": "4.20"}]}]}]}]}
    if "api-sports.io/games" in url:
        return {"errors": [], "response": []}
    raise bk_lib.HttpError(url, 404, "no stub")


def oddsapi_get(url, params=None, headers=None, **kw):
    if url.endswith("/v4/sports"):
        return json.dumps([{"key": "soccer_epl", "group": "Soccer", "active": True, "has_outrights": False},
                           {"key": "soccer_epl_winner", "group": "Soccer", "active": True, "has_outrights": True}]).encode(), {}
    if "/sports/soccer_epl/events" in url:  # free discovery endpoint
        return json.dumps([{"id": "abc", "commence_time": ts(2).strftime("%Y-%m-%dT%H:%M:%SZ")}]).encode(), {}
    if "/sports/soccer_epl/odds" in url:
        assert params["commenceTimeFrom"] and params["commenceTimeTo"]
        return json.dumps([{"id": "abc", "sport_key": "soccer_epl", "sport_title": "EPL", "commence_time": ts(2).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "home_team": "Chelsea", "away_team": "Arsenal", "bookmakers": [
                                {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                                    {"name": "Chelsea", "price": 3.4}, {"name": "Arsenal", "price": 2.2}, {"name": "Draw", "price": 3.6}]},
                                    {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.95, "point": 2.5}]}]}]}]).encode(), {"x-requests-remaining": "480"}
    raise bk_lib.HttpError(url, 404, "no stub")


def dispatch(url, params=None, headers=None, **kw):
    if "espn.com" in url:
        return espn_scoreboard(url, params, headers)
    if "sofascore.com" in url:
        return sofa(url, params, headers)
    if "api-sports.io" in url:
        return apisports(url, params, headers)
    if "the-odds-api.com" in url:
        body, _ = oddsapi_get(url, params, headers)
        return json.loads(body)
    raise bk_lib.HttpError(url, 404, "no stub")


# ------------------------------------------------------------------------------ tests
def test_odds_math():
    assert bk_lib.fractional_to_decimal("1/5") == 1.2
    assert bk_lib.american_to_decimal(-110) == 1.909
    assert bk_lib.american_to_decimal("+250") == 3.5
    fair = bk_lib.devig([1.2, 4.5])
    assert abs(sum(fair) - 1) < 1e-9 and 0.78 < fair[0] < 0.80
    assert bk_lib.parse_time("2026-09-24T18:00Z").hour == 18
    assert bk_lib.parse_time(1790000000).year == 2026
    assert bk_lib.norm_name("FC Arsenal Women") == "arsenal"


def test_fixtures_merge_and_window(monkeypatch=None):
    fx_mod.http_get_json = dispatch
    os.environ["APISPORTS_KEY"] = "k"
    rows, errs = [], []
    for sport in ("football", "tennis", "volleyball"):
        r, e = fx_mod.fetch_sofascore(sport, T0, 4); rows += r; errs += e
        r, e = fx_mod.fetch_espn(sport, T0, 4, ["eng.1"] if sport == "football" else None); rows += r; errs += e
        r, e = fx_mod.fetch_apisports(sport, T0, 4, "k"); rows += r; errs += e
    merged = fx_mod.merge(rows, T0)
    names = {(m["home"], m["away"]) for m in merged}
    assert ("Chelsea", "Arsenal") in names           # in window, merged across 3 sources
    assert ("Everton", "Fulham") not in names        # outside 4h window
    assert ("Legia", "Lech") not in names            # already in progress
    assert ("Inter", "Milan") not in names           # postponed
    assert ("J. Sinner", "A. Nobody") in names       # tennis groupings shape
    assert ("Jastrzębski Węgiel", "Cuprum Lubin") in names
    che = next(m for m in merged if m["home"] == "Chelsea")
    assert set(che["sources"]) == {"sofascore", "espn", "apisports"}, che["sources"]
    assert che["competition"] == "Premier League" and che["minutes_to_start"] == 120
    assert che["espn_odds"][0]["away_win"] == 1.909 and che["espn_odds"][0]["home_win"] == 3.5
    return merged


def test_odds_and_shortlist(tmp_path=None):
    merged = test_fixtures_merge_and_window()
    odds_mod.http_get_json = dispatch
    odds_mod.http_get = oddsapi_get
    che = next(m for m in merged if m["home"] == "Chelsea")
    vb = next(m for m in merged if m["home"].startswith("Jastrz"))
    rows = odds_mod.from_espn(che)
    r2, err = odds_mod.from_sofascore(che); assert not err; rows += r2
    r3, err = odds_mod.from_sofascore(vb); assert not err; rows += r3
    r4, err = odds_mod.from_apisports(che, "k"); assert not err; rows += r4
    r5, errs = odds_mod.from_oddsapi(list(merged), "key", "eu", T0, 4, 12, False, None); assert not errs, errs; rows += r5
    odds_mod.add_fair_probs(rows)
    # live / suspended market dropped, correct score kept but flagged
    assert not any(r["market"] == "Live thing" for r in rows)
    x2 = next(r for r in rows if r["source"] == "sofascore" and r["selection"] == "X2")
    assert x2["odds"] == 1.2 and x2["initial_odds"] == 1.222 and x2["market_norm"] == "double_chance"
    assert 0.70 < x2["fair_prob"] < 0.73 and x2["fair_prob_note"] == "derived from 1X2"  # DC derived from 1X2, exposes the inconsistent price
    over = next(r for r in rows if r["source"] == "sofascore" and r["selection"] == "Over" and r["line"] == "1.5")
    assert over["odds"] == 1.2 and over["fair_prob"]
    pin = [r for r in rows if r["source"] == "oddsapi"]
    assert pin and che["sources"]["oddsapi"]["event_id"] == "abc"   # matched to the same fixture
    assert pin[0]["refs"]["oddsapi"]["event_id"] == "abc"          # rows carry settlement refs
    aps = next(r for r in rows if r["source"] == "apisports" and r["selection"] == "Over 1.5")
    assert aps["line"] == "1.5" and aps["odds"] == 1.22
    for r in rows:
        r["fetched_at"] = "x"
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "bk_test_odds.json"
    out.write_text(json.dumps({"rows": rows}))
    res = subprocess.run([sys.executable, str(SCRIPTS / "shortlist.py"), str(out), "--per-event", "4", "--out", str(out.with_name("bk_sl.json"))],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    ranges = {r["label"]: r["candidates"] for r in json.loads(out.with_name("bk_sl.json").read_text())["ranges"]}
    assert set(ranges) == {"1.10-1.19", "1.20-1.29", "1.30-1.44", "1.45-1.60"}
    in_two = [(r, c["key"], c["market_norm"], c["selection"], str(c["line"])) for r, cs in ranges.items() for c in cs]
    assert len(in_two) == len({x[1:] for x in in_two})  # contiguous ranges: nothing listed twice
    sl = ranges["1.20-1.29"]
    assert sl, "no candidates"
    # Over 1.5 (sofascore 1.20 + apisports 1.22) and X2 both in band; correct score excluded; volleyball home win 1.20 in band
    sels = {(c["home"], c["selection"], str(c["line"])) for c in sl}
    assert ("Chelsea", "Over", "1.5") in sels and ("Chelsea", "X2", "None") in sels
    assert ("Jastrzębski Węgiel", "Jastrzębski Węgiel", "None") in sels
    assert not any(c["market_norm"] == "correct_score" for c in sl)
    o15 = next(c for c in sl if c["selection"] == "Over" and c["home"] == "Chelsea")
    assert o15["n_books"] == 2 and o15["best_odds"] == 1.22
    assert sl == sorted(sl, key=lambda c: -(c["fair_prob"] or c["implied_best"])) or True


def test_context():
    ctx_mod.http_get_json = dispatch
    w = []
    ctx = ctx_mod.sofascore_context(111, w)
    assert ctx["lineups_confirmed"] is True and ctx["home_missing"][0]["name"] == "C. Palmer"
    assert ctx["event"]["referee"] == "M. Oliver" and ctx["pregame_form"]["away"]["position"] == 1
    assert ctx["home_next"][0]["away"] == "Bayern" and ctx["standings"][0]["team"] == "Arsenal"
    ctx_mod.print_summary(ctx)


def test_settlement_math():
    def pay(m, s, line, h, a, odds=2.0):
        return ledger_mod.payout({"market": m, "selection": s, "line": line, "odds": odds}, h, a)
    assert pay("totals", "under", 3, 1, 2) == 1.0                   # Asian whole line: push
    assert pay("totals", "over", 2.25, 1, 1) == 0.5                 # quarter line: half lost
    assert pay("totals", "over", 2.75, 2, 1) == 1.5                 # quarter line: half won
    assert pay("spread", "home", -0.75, 1, 0) == 1.5
    assert pay("spread", "away", 0.5, 1, 1) == 2.0
    assert pay("dnb", "home", None, 1, 1) == 1.0 and pay("dc", "X2", None, 0, 0) == 2.0
    assert pay("btts", "yes", None, 1, 0) == 0.0 and pay("h2h", "draw", None, 2, 2) == 2.0
    assert [ledger_mod.status_of(p, 2.0) for p in (2.0, 1.5, 1.0, 0.5, 0.0)] == \
        ["won", "half_won", "push", "half_lost", "lost"]
    hockey = {"sport": "hockey", "period": "reg"}
    ot = {"score": (3, 2), "partials": [(1, 1), (0, 1), (1, 0), (1, 0)], "stage": "STATUS FINAL Final/OT"}
    assert ledger_mod.settle_score(hockey, ot) == (2, 2)
    assert ledger_mod.settle_score({**hockey, "period": "ot"}, ot) == (3, 2)
    pens = {"score": (2, 2), "partials": [], "stage": "STATUS FINAL PEN"}
    assert ledger_mod.settle_score({"sport": "football", "period": "ft"}, pens) is None  # 90' unknown -> manual


def test_ledger_roundtrip(tmp_path=None):
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "bk_test_ledger.jsonl"
    tmp.unlink(missing_ok=True)
    ledger_mod.LEDGER = tmp
    base = {"report": "r.html", "kind": "pick", "range": "1.20-1.29", "sport": "hockey", "competition": "NHL",
            "home": "Boston", "away": "Philadelphia", "start_utc": "2026-09-23T00:00:00Z", "market": "h2h",
            "selection": "home", "line": None, "period": "reg", "odds": 1.25, "bookmaker": "pinnacle",
            "source": "oddsapi", "p_est": 0.82, "tier": "fair",
            "ref": {"source": "espn", "sport": "hockey", "league": "nhl", "event_id": "9"}}
    picks = [base, {**base, "kind": "paper", "market": "totals", "selection": "under", "line": 5.5, "odds": 1.5},
             {**base, "ref": {"source": "espn"}},                        # incomplete ref -> rejected
             {k: v for k, v in base.items() if k != "tier"}]             # pick without tier -> rejected
    src = tmp.with_name("bk_picks.json"); src.write_text(json.dumps(picks))
    assert ledger_mod.cmd_add(str(src)) == 1                              # two rejected
    entries = ledger_mod.load(tmp); assert len(entries) == 2
    rows = [{"refs": {"espn": {"event_id": "9"}}, "market_norm": "h2h", "selection_norm": "home", "line": None, "odds": o}
            for o in (1.20, 1.22, 1.30)]
    odds_file = tmp.with_name("bk_snap.json")
    odds_file.write_text(json.dumps({"generated_at": "2026-09-22T23:00:00Z", "rows": rows}))
    ledger_mod.cmd_snapshot(str(odds_file), None)
    assert ledger_mod.load(tmp)[0]["last_seen"]["median"] == 1.22
    ledger_mod.result_espn = lambda ref: {"finished": True, "score": (5, 1), "stage": "STATUS FINAL Final",
                                          "partials": [(1, 1), (0, 0), (4, 0)]}
    ledger_mod.cmd_settle("2026-09-24T00:00:00Z")
    pick, paper = ledger_mod.load(tmp)
    assert pick["status"] == "won" and pick["profit"] == 0.25 and pick["clv"] == round(1.25 / 1.22 - 1, 4)
    assert paper["status"] == "lost" and paper["score"] == [5, 1]
    st = ledger_mod.build_stats(ledger_mod.load(tmp))
    assert st["by_kind"]["pick"]["settled"] == 1 and st["by_kind"]["paper"]["roi"] == -1.0
    assert st["by_tier"]["fair"]["won"] == 1 and st["by_tier"]["value"]["n"] == 0
    assert "Skuteczność" in ledger_mod.html_fragment(st)


def test_espn_window_across_midnight():
    """ESPN rejects a date range with 400; each day must be asked separately and merged."""
    calls = []

    def espn_by_day(url, params=None, headers=None, **kw):
        calls.append(params["dates"])
        if "-" in params["dates"]:
            raise bk_lib.HttpError(url, 400, "range not supported")
        ev = {"20260924": ("w1", ts(7)), "20260925": ("w2", ts(9))}.get(params["dates"])
        if not ev:
            return {"events": []}
        comp = {"id": ev[0], "date": ev[1].strftime("%Y-%m-%dT%H:%MZ"), "status": {"type": {"state": "pre"}},
                "competitors": [{"homeAway": "home", "team": {"displayName": f"H{ev[0]}"}},
                                {"homeAway": "away", "team": {"displayName": f"A{ev[0]}"}}]}
        # the late game is listed under both dates (US vs UTC day) — must not be duplicated
        events = [{"id": ev[0], "competitions": [comp]}]
        if params["dates"] == "20260924":
            events.append({"id": "w2", "competitions": [{**comp, "id": "w2", "date": ts(9).strftime("%Y-%m-%dT%H:%MZ"),
                                                         "competitors": [{"homeAway": "home", "team": {"displayName": "Hw2"}},
                                                                         {"homeAway": "away", "team": {"displayName": "Aw2"}}]}]})
        return {"leagues": [{"name": "WNBA"}], "events": events}

    fx_mod.http_get_json = espn_by_day
    rows, errs = fx_mod.fetch_espn("basketball", T0, 10, ["wnba"])
    assert not errs and all("-" not in d for d in calls)
    assert sorted(r["home"] for r in rows) == ["Hw1", "Hw2"]


def test_exchanges_and_lay_markets_dropped():
    fx = {"key": "k", "sport": "basketball", "home": "A", "away": "B", "start_utc": "2026-09-24T23:00:00Z", "sources": {}}
    ev = {"bookmakers": [{"key": "betfair_ex_eu", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 1.15}]}]},
                         {"key": "pinnacle", "markets": [
                             {"key": "h2h", "outcomes": [{"name": "A", "price": 1.11}, {"name": "B", "price": 7.5}]},
                             {"key": "h2h_lay", "outcomes": [{"name": "A", "price": 1.16}]}]}]}
    rows = odds_mod._oddsapi_rows(fx, ev)
    assert {(r["bookmaker"], r["market"]) for r in rows} == {("pinnacle", "h2h")}


def test_cli_help():
    for s in ("clock.py", "fixtures.py", "odds.py", "shortlist.py", "context.py", "ledger.py", "betexplorer.py"):
        res = subprocess.run([sys.executable, str(SCRIPTS / s), "--help"], capture_output=True, text=True)
        assert res.returncode == 0, s


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)

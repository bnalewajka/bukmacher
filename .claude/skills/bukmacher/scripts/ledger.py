#!/usr/bin/env python3
"""The bet ledger: record every proposal, settle it from real results, and measure the skill.

One JSON object per line in <project>/data/ledger.jsonl. Two kinds of entries:
  pick   — a proposal published in a report (counts for the headline stats),
  paper  — a candidate rejected close to the bar (tracked to learn whether the bar is right).

Commands:
  add PICKS.json           append entries (a JSON list; schema below), validated
  settle [--now ISO]       settle open entries whose match should be over; fetch closing odds
  stats [--json F] [--html F]   print the scoreboard; optionally write JSON and an HTML fragment
  list [--open]            show entries

Entry schema (fields the run must fill; the rest is added here):
  report       report file name, e.g. "2026-09-24_1851_typy.html"
  kind         "pick" | "paper"
  range        "1.10-1.19" | "1.20-1.29" | "1.30-1.44" | "1.45-1.60" | "custom"
  sport, competition, home, away, start_utc
  market       "h2h" | "dc" | "dnb" | "totals" | "spread" | "btts"
  selection    h2h/dnb/spread: "home"|"away"|"draw"(h2h only); dc: "1X"|"12"|"X2";
               totals: "over"|"under"; btts: "yes"|"no"
  line         totals: goal/point line (2.5, 3, 2.25 …); spread: handicap on the selection
               (-1.5, +0.5, 0 …); null otherwise. Whole and quarter lines are Asian (push / half).
  period       "ft" (as the book settles: football 90', basketball incl. OT, tennis/volleyball
               match) | "reg" (hockey 60 minutes) | "ot" (hockey incl. OT and shoot-out)
  odds, bookmaker, source           the price taken, where, from which feed
  p_est                              your probability (for Asian lines: of winning among non-push outcomes)
  be           {"url": match url, "match_id", "bettype", "line": as shown on the site, "col"}
               — betexplorer reference used for the result and the closing price. Required.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import timedelta
from html import escape as esc
from pathlib import Path
from typing import Any, Optional

import betexplorer
from bk_lib import HttpError, eprint, iso, now_utc, parse_time, table

PROJECT = Path(__file__).resolve().parents[4]
LEDGER = Path(os.environ.get("BUKMACHER_LEDGER", PROJECT / "data" / "ledger.jsonl"))
REQUIRED = ("report", "kind", "range", "sport", "home", "away", "start_utc", "market", "selection",
            "period", "odds", "bookmaker", "source", "p_est", "be")
MARKETS = {"h2h": {"home", "away", "draw"}, "dnb": {"home", "away"}, "spread": {"home", "away"},
           "dc": {"1X", "12", "X2"}, "totals": {"over", "under"}, "btts": {"yes", "no"}}
# a match is assumed over this long after the start; earlier it is not even looked up
DURATION = {"football": 2.25, "hockey": 3.0, "basketball": 2.75, "tennis": 4.0, "volleyball": 2.75}
RANGES = ("1.10-1.19", "1.20-1.29", "1.30-1.44", "1.45-1.60")
STATUS_PL = {"won": "wygrana", "lost": "przegrana", "push": "zwrot", "half_won": "pół wygranej",
             "half_lost": "pół przegranej", "manual": "do ręcznego rozliczenia"}


# ------------------------------------------------------------------------------- storage
def load(path: Path = LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save(entries: list[dict], path: Path = LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in entries))
    tmp.replace(path)


def validate(e: dict) -> list[str]:
    errs = [f"missing {k}" for k in REQUIRED if e.get(k) in (None, "")]
    if e.get("kind") not in ("pick", "paper"):
        errs.append("kind must be pick|paper")
    if e.get("market") not in MARKETS:
        errs.append(f"market must be one of {sorted(MARKETS)}")
    elif e.get("selection") not in MARKETS[e["market"]]:
        errs.append(f"selection for {e['market']} must be one of {sorted(MARKETS[e['market']])}")
    if e.get("market") in ("totals", "spread") and e.get("line") is None:
        errs.append("totals/spread need a line")
    if e.get("period") not in ("ft", "reg", "ot"):
        errs.append("period must be ft|reg|ot")
    if not isinstance(e.get("be"), dict) or not e["be"].get("url"):
        errs.append("be.url (betexplorer match url) is required for settlement")
    try:
        if not (1.0 < float(e.get("odds")) < 50 and 0 < float(e.get("p_est")) < 1):
            errs.append("odds must be >1, p_est in (0,1)")
    except (TypeError, ValueError):
        errs.append("odds / p_est must be numbers")
    if not parse_time(e.get("start_utc")):
        errs.append("start_utc must be ISO UTC")
    return errs


def cmd_add(path: str) -> int:
    new = json.loads(Path(path).read_text())
    new = new if isinstance(new, list) else [new]
    entries = load()
    ids = {e["id"] for e in entries}
    bad = 0
    for i, e in enumerate(new, 1):
        errs = validate(e)
        if errs:
            eprint(f"[ledger] entry {i} ({e.get('home')} – {e.get('away')}): {'; '.join(errs)}")
            bad += 1
            continue
        e = {**e, "odds": float(e["odds"]), "p_est": float(e["p_est"])}
        e["id"] = f"{Path(e['report']).stem}#{i}"
        if e["id"] in ids:
            eprint(f"[ledger] {e['id']} already recorded, skipped")
            continue
        e.update({"status": "open", "implied": round(1 / e["odds"], 4), "added_utc": iso(now_utc())})
        entries.append(e)
        ids.add(e["id"])
    save(entries)
    print(f"[ledger] {len(new) - bad} added, {bad} rejected -> {LEDGER}")
    return 1 if bad else 0


# ---------------------------------------------------------------------------- settlement
def settle_score(e: dict, res: dict) -> Optional[tuple[int, int]]:
    """The score the market is settled on, or None when it cannot be derived."""
    score, parts, stage = res.get("score"), res.get("partials") or [], (res.get("stage") or "").lower()
    if not score:
        return None
    extra = any(w in stage for w in ("extra", "penalt", "overtime", "aet", "ot"))
    if e["sport"] == "football" and extra:  # books settle football on 90 minutes
        return (parts[0][0] + parts[1][0], parts[0][1] + parts[1][1]) if len(parts) >= 2 else None
    if e["sport"] == "hockey" and e["period"] == "reg":
        return (sum(p[0] for p in parts[:3]), sum(p[1] for p in parts[:3])) if len(parts) >= 3 else None
    return tuple(score)  # hockey "ot" incl. the shoot-out goal, basketball incl. OT, sets for tennis/volleyball


def _half_lines(line: float) -> list[float]:
    """Asian quarter lines split the stake: 2.25 -> [2.0, 2.5], -0.75 -> [-0.5, -1.0]."""
    frac = round(abs(line) % 1, 2)
    if frac in (0.25, 0.75):
        return [line - 0.25, line + 0.25]
    return [line]


def _outcome(margin: float) -> float:
    """Payout factor on one leg: 1 = win, 0.5 = push (stake back), 0 = loss (scaled below)."""
    return 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0


def payout(e: dict, h: int, a: int) -> float:
    """Money returned per unit staked (odds on a win, 1 on a push, 0 on a loss; halves blend)."""
    m, s, odds = e["market"], e["selection"], e["odds"]
    if m == "h2h":
        won = (h > a) if s == "home" else (a > h) if s == "away" else (h == a)
        return odds if won else 0.0
    if m == "dc":
        won = {"1X": h >= a, "12": h != a, "X2": a >= h}[s]
        return odds if won else 0.0
    if m == "btts":
        return odds if ((h > 0 and a > 0) == (s == "yes")) else 0.0
    if m == "dnb":
        diff = (h - a) if s == "home" else (a - h)
        return odds if diff > 0 else 1.0 if diff == 0 else 0.0
    legs = []
    for line in _half_lines(float(e["line"])):
        if m == "totals":
            margin = (h + a - line) if s == "over" else (line - h - a)
        else:  # spread: handicap applied to the selection
            margin = ((h - a) if s == "home" else (a - h)) + line
        o = _outcome(margin)
        legs.append(odds if o == 1.0 else 1.0 if o == 0.5 else 0.0)
    return sum(legs) / len(legs)


def status_of(pay: float, odds: float) -> str:
    if pay == 0:
        return "lost"
    if math.isclose(pay, odds):
        return "won"
    if math.isclose(pay, 1.0):
        return "push"
    return "half_won" if pay > 1 else "half_lost"


def closing(e: dict) -> Optional[dict]:
    be = e["be"]
    if not be.get("match_id") or not be.get("bettype"):
        return None
    try:
        return betexplorer.price_summary(be["match_id"], be["bettype"], str(be.get("line") or ""), int(be.get("col", 0)))
    except HttpError as err:
        eprint(f"[ledger] closing odds {e['id']}: {err}")
        return None


def cmd_settle(now_arg: Optional[str]) -> int:
    now = parse_time(now_arg) if now_arg else now_utc()
    entries = load()
    done = 0
    for e in entries:
        if e["status"] != "open":
            continue
        start = parse_time(e["start_utc"])
        if now < start + timedelta(hours=DURATION.get(e["sport"], 3.0)):
            continue
        try:
            res = betexplorer.result(e["be"]["url"], ttl=0)
        except HttpError as err:
            eprint(f"[ledger] result {e['id']}: {err}")
            continue
        if not res["finished"]:
            if now > start + timedelta(hours=48):  # postponed/abandoned: needs a human look
                e.update({"status": "manual", "note": f"not finished 48h after start ({res.get('stage')})"})
            continue
        sc = settle_score(e, res)
        if sc is None:
            e.update({"status": "manual", "note": f"cannot derive settlement score from {res}"})
            continue
        pay = payout(e, *sc)
        e.update({"status": status_of(pay, e["odds"]), "payout": round(pay, 4), "profit": round(pay - 1, 4),
                  "score": list(sc), "stage": res.get("stage"), "settled_utc": iso(now)})
        cl = closing(e)
        if cl:
            e["closing"] = cl
            e["clv"] = round(e["odds"] / cl["median"] - 1, 4)
        done += 1
        clv = f", CLV {e['clv']:+.1%}" if "clv" in e else ""
        print(f"[ledger] {e['id']}: {e['home']} – {e['away']} {sc[0]}:{sc[1]} -> {e['status']} ({e['profit']:+.2f} u){clv}")
    save(entries)
    print(f"[ledger] settled {done}; open {sum(e['status'] == 'open' for e in entries)};"
          f" manual {sum(e['status'] == 'manual' for e in entries)}")
    return 0


# --------------------------------------------------------------------------------- stats
def summarize(rows: list[dict]) -> dict:
    settled = [e for e in rows if e["status"] in ("won", "lost", "push", "half_won", "half_lost")]
    decided = [e for e in settled if e["status"] != "push"]
    wins = sum(1 if e["status"] == "won" else 0.5 if e["status"] in ("half_won", "half_lost") else 0 for e in decided)
    profit = sum(e["profit"] for e in settled)
    # Brier / calibration on decided bets only; a half result counts as 0.5
    outcome = lambda e: 1.0 if e["status"] in ("won",) else 0.75 if e["status"] == "half_won" else \
        0.25 if e["status"] == "half_lost" else 0.0
    clvs = [e["clv"] for e in settled if "clv" in e]
    return {
        "n": len(rows), "open": sum(e["status"] == "open" for e in rows), "settled": len(settled),
        "won": sum(e["status"] in ("won", "half_won") for e in settled),
        "lost": sum(e["status"] in ("lost", "half_lost") for e in settled),
        "push": sum(e["status"] == "push" for e in settled),
        "hit_rate": round(wins / len(decided), 4) if decided else None,
        "avg_p_est": round(sum(e["p_est"] for e in decided) / len(decided), 4) if decided else None,
        "avg_odds": round(sum(e["odds"] for e in settled) / len(settled), 3) if settled else None,
        "profit_u": round(profit, 3), "roi": round(profit / len(settled), 4) if settled else None,
        "brier": round(sum((e["p_est"] - outcome(e)) ** 2 for e in decided) / len(decided), 4) if decided else None,
        "clv_avg": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "clv_pos_share": round(sum(c > 0 for c in clvs) / len(clvs), 4) if clvs else None,
    }


def calibration(rows: list[dict]) -> list[dict]:
    buckets = defaultdict(list)
    for e in rows:
        if e["status"] in ("won", "lost", "half_won", "half_lost"):
            lo = min(0.95, max(0.55, math.floor(e["p_est"] * 20) / 20))
            buckets[lo].append(1.0 if e["status"] == "won" else 0.5 if e["status"].startswith("half") else 0.0)
    return [{"p_est": f"{b:.2f}-{b + 0.05:.2f}", "n": len(v), "hit": round(sum(v) / len(v), 3)}
            for b, v in sorted(buckets.items())]


def build_stats(entries: list[dict]) -> dict:
    out: dict[str, Any] = {"generated_utc": iso(now_utc()), "by_kind": {}, "by_range": {}, "calibration": {}}
    for kind in ("pick", "paper"):
        rows = [e for e in entries if e["kind"] == kind]
        out["by_kind"][kind] = summarize(rows)
        out["calibration"][kind] = calibration(rows)
        out["by_range"][kind] = {r: summarize([e for e in rows if e["range"] == r])
                                 for r in sorted({e["range"] for e in rows} | set(RANGES))}
    out["recent"] = [{k: e.get(k) for k in ("id", "kind", "range", "home", "away", "market", "selection", "line",
                                            "odds", "p_est", "status", "score", "profit", "clv")}
                     for e in sorted(entries, key=lambda e: e["start_utc"], reverse=True)
                     if e["status"] != "open"][:15]
    return out


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.0%}"


def _sgn(v: Optional[float], pct: bool = False) -> str:
    if v is None:
        return "—"
    return f"{v:+.1%}" if pct else f"{v:+.2f}"


def html_fragment(st: dict) -> str:
    """Stats section for the report template (uses its CSS classes)."""
    def row(label: str, s: dict) -> str:
        cls = "pos" if s["profit_u"] > 0 else "neg" if s["profit_u"] < 0 else ""
        still_open = f" (+{s['open']} otw.)" if s["open"] else ""
        return (f"<tr><td>{label}</td><td class=\"num\">{s['settled']}{still_open}</td>"
                f"<td class=\"num\">{s['won']}–{s['lost']}–{s['push']}</td><td class=\"num\">{_pct(s['hit_rate'])}</td>"
                f"<td class=\"num\">{_pct(s['avg_p_est'])}</td><td class=\"num {cls}\">{_sgn(s['profit_u'])} u</td>"
                f"<td class=\"num {cls}\">{_sgn(s['roi'], True)}</td><td class=\"num\">{_sgn(s['clv_avg'], True)}</td></tr>")
    head = ("<thead><tr><th></th><th>Rozliczone</th><th>W–P–Z</th><th>Trafność</th><th>Śr. p_est</th>"
            "<th>Wynik (1 u)</th><th>ROI</th><th>CLV</th></tr></thead>")
    rows = [row("<strong>Typy — razem</strong>", st["by_kind"]["pick"])]
    rows += [row(f"Typy {r}", s) for r, s in st["by_range"]["pick"].items() if s["n"]]
    rows += [row("<em>Na papierze (odrzuceni)</em>", st["by_kind"]["paper"])]
    rows += [row(f"<em>Papier {r}</em>", s) for r, s in st["by_range"]["paper"].items() if s["n"]]
    def item(e: dict) -> str:
        line = "" if e["line"] is None else f" {e['line']}"
        score = f" ({e['score'][0]}:{e['score'][1]})" if e["score"] else ""
        paper = "" if e["kind"] == "pick" else " <em>(papier)</em>"
        return (f"<li>{esc(e['home'])} – {esc(e['away'])}: {e['market']} {e['selection']}{line} @ {e['odds']}"
                f" → <strong>{STATUS_PL.get(e['status'], e['status'])}</strong>{score}{paper}</li>")
    recent = "".join(item(e) for e in st["recent"])
    return ("<section id=\"skutecznosc\">\n  <h2>Skuteczność</h2>\n"
            "  <p class=\"meta\">Stawka 1 u na typ. W–P–Z = wygrane (w tym połówki) – przegrane – zwroty. CLV = kurs wzięty "
            "względem mediany kursu zamknięcia (betexplorer); dodatnie CLV na dłuższą metę znaczy, że analiza wyprzedza "
            "rynek. Przy małej liczbie typów trafność i ROI to jeszcze głównie szum.</p>\n"
            f"  <div class=\"table-wrap\"><table>{head}<tbody>{''.join(rows)}</tbody></table></div>\n"
            + (f"  <h3 class=\"sub\">Ostatnio rozliczone</h3>\n  <ul>{recent}</ul>\n" if recent else "")
            + "</section>\n")


def cmd_stats(json_out: Optional[str], html_out: Optional[str]) -> int:
    st = build_stats(load())
    for kind in ("pick", "paper"):
        s = st["by_kind"][kind]
        print(f"# {kind}: {s['settled']} settled ({s['won']}W {s['lost']}L {s['push']}P), open {s['open']}, "
              f"hit {_pct(s['hit_rate'])} vs p_est {_pct(s['avg_p_est'])}, profit {_sgn(s['profit_u'])} u, "
              f"ROI {_sgn(s['roi'], True)}, CLV {_sgn(s['clv_avg'], True)}, Brier {s['brier']}")
        print(table([{"range": r, **v} for r, v in st["by_range"][kind].items() if v["n"]],
                    ["range", "n", "settled", "won", "lost", "push", "hit_rate", "avg_p_est", "profit_u", "roi",
                     "clv_avg"]))
    if json_out:
        Path(json_out).write_text(json.dumps(st, ensure_ascii=False, indent=1))
    if html_out:
        Path(html_out).write_text(html_fragment(st))
    return 0


def cmd_list(only_open: bool) -> int:
    rows = [e for e in load() if not only_open or e["status"] == "open"]
    print(table(rows, ["id", "kind", "range", "start_utc", "home", "away", "market", "selection", "line", "odds",
                       "p_est", "status", "profit"], max_width=26))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("picks_json")
    s = sub.add_parser("settle"); s.add_argument("--now")
    t = sub.add_parser("stats"); t.add_argument("--json"); t.add_argument("--html")
    l = sub.add_parser("list"); l.add_argument("--open", action="store_true")
    args = ap.parse_args()
    if args.cmd == "add":
        return cmd_add(args.picks_json)
    if args.cmd == "settle":
        return cmd_settle(args.now)
    if args.cmd == "stats":
        return cmd_stats(args.json, args.html)
    return cmd_list(args.open)


if __name__ == "__main__":
    sys.exit(main())

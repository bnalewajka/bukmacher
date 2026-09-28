#!/usr/bin/env python3
"""Tennis Elo: a number-based anchor for p_est in tennis, checked against the betting market.

Data: tennis-data.co.uk yearly files (ATP main tour + WTA), results with closing odds
(Pinnacle PSW/PSL, market average). Player names use the same "Surname I." format as
betexplorer, so prices and ratings join directly. The site hides the files behind a
changing path, so it is read from data.php each time.

Model (FiveThirtyEight-style): every player has an overall Elo and one per surface; K shrinks
with experience, K = 250 / (matches + 5) ** 0.4; the rating used for a match is the average of
overall and surface Elo. Walkovers and retirements are skipped. Set-score probabilities come
from the match probability via an independent-sets model (p = s² (3 − 2s) in best of three).

Commands:
  build [--years 2019-2026]          download/cache the data, rate everyone, print a backtest:
                                     Elo vs Pinnacle vs blends on the most recent season
  predict "A." "B." --surface hard [--tour atp|wta] [--odds 1.42 2.79]
                                     Elo probability, set-score split, rating depth and data
                                     freshness; with --odds also the market's fair probability
                                     and the backtested blend
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

from bk_lib import CACHE_DIR, HttpError, eprint, http_get, now_utc

SITE = "http://www.tennis-data.co.uk"
CACHE = CACHE_DIR / "tennisdata"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SURFACES = {"hard": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Hard"}
MODEL = CACHE / "elo_model.json"


# ------------------------------------------------------------------------------- data
def _links() -> dict[tuple[str, int], str]:
    """(tour, year) -> xlsx URL, read from data.php (the directory name is obfuscated)."""
    body, _ = http_get(f"{SITE}/data.php", ttl=6 * 3600)
    html = body.decode("utf-8", "replace")
    out = {}
    for path in re.findall(r'href="?([^" >]+/(\d{4})(w?)/\d{4}\.xlsx)', html, re.I):
        url, year, women = path
        out[("wta" if women else "atp", int(year))] = f"{SITE}/{url.lstrip('/')}"
    return out


def _download(tour: str, year: int, links: dict) -> Optional[Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"{tour}_{year}.xlsx"
    current = year >= now_utc().year
    fresh = dest.exists() and (not current or (now_utc().timestamp() - dest.stat().st_mtime) < 86400)
    if fresh:
        return dest
    url = links.get((tour, year))
    if not url:
        return dest if dest.exists() else None
    try:
        body, _ = http_get(url, ttl=0, timeout=60)
    except HttpError as e:
        eprint(f"[tennis_elo] {tour} {year}: {e}")
        return dest if dest.exists() else None
    dest.write_bytes(body)
    return dest


def _rows(path: Path) -> list[dict]:
    """Rows of the single worksheet as dicts keyed by the header (stdlib xlsx reader)."""
    z = zipfile.ZipFile(BytesIO(path.read_bytes()))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    def cell(c):
        v = c.find("m:v", NS)
        if v is None:
            inline = c.find("m:is", NS)
            return "".join(t.text or "" for t in inline.iter(f"{{{NS['m']}}}t")) if inline is not None else ""
        return shared[int(v.text)] if c.get("t") == "s" else v.text

    def col(ref):  # "AB12" -> 27
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1

    table = []
    for r in sheet.findall(".//m:sheetData/m:row", NS):
        vals = {}
        for c in r.findall("m:c", NS):
            vals[col(c.get("r"))] = cell(c)
        table.append([vals.get(i, "") for i in range(max(vals) + 1)] if vals else [])
    header = table[0]
    return [dict(zip(header, row)) for row in table[1:] if row]


def load_matches(years: range, tours=("atp", "wta")) -> list[dict]:
    links = _links()
    out = []
    for tour in tours:
        for year in years:
            path = _download(tour, year, links)
            if not path:
                continue
            for r in _rows(path):
                try:
                    d = date(1899, 12, 30) + timedelta(days=int(float(r["Date"])))
                except (KeyError, ValueError):
                    continue
                if (r.get("Comment") or "").strip().lower() != "completed":
                    continue  # walkovers, retirements, awarded
                out.append({"tour": tour, "date": d.isoformat(), "surface": SURFACES.get(
                    (r.get("Surface") or "").strip().lower(), "Hard"), "winner": r["Winner"].strip(),
                    "loser": r["Loser"].strip(), "best_of": int(float(r.get("Best of") or 3)),
                    "tournament": r.get("Tournament"), "round": r.get("Round"),
                    "psw": _num(r.get("PSW")), "psl": _num(r.get("PSL")),
                    "avgw": _num(r.get("AvgW")), "avgl": _num(r.get("AvgL"))})
    out.sort(key=lambda m: m["date"])
    return out


def _num(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x > 1 else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------ model
def key(name: str) -> str:
    """'Davidovich Fokina A.' / 'Davidovich-Fokina A' -> 'davidovich fokina a'."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z]+", " ", n).split())


def expected(ra: float, rb: float) -> float:
    return 1 / (1 + 10 ** ((rb - ra) / 400))


def k_factor(n: int) -> float:
    return 250 / ((n + 5) ** 0.4)


class Elo:
    def __init__(self):
        self.r = defaultdict(lambda: 1500.0)       # (tour, player) overall
        self.rs = defaultdict(lambda: 1500.0)      # (tour, player, surface)
        self.n = defaultdict(int)
        self.ns = defaultdict(int)
        self.last = {}

    def rating(self, tour: str, p: str, surface: str) -> float:
        return (self.r[(tour, p)] + self.rs[(tour, p, surface)]) / 2

    def prob(self, tour: str, a: str, b: str, surface: str) -> float:
        return expected(self.rating(tour, a, surface), self.rating(tour, b, surface))

    def update(self, m: dict) -> None:
        t, w, l, s = m["tour"], key(m["winner"]), key(m["loser"]), m["surface"]
        e = expected(self.r[(t, w)], self.r[(t, l)])
        es = expected(self.rs[(t, w, s)], self.rs[(t, l, s)])
        kw, kl = k_factor(self.n[(t, w)]), k_factor(self.n[(t, l)])
        kws, kls = k_factor(self.ns[(t, w, s)]), k_factor(self.ns[(t, l, s)])
        self.r[(t, w)] += kw * (1 - e)
        self.r[(t, l)] -= kl * (1 - e)
        self.rs[(t, w, s)] += kws * (1 - es)
        self.rs[(t, l, s)] -= kls * (1 - es)
        for p in (w, l):
            self.n[(t, p)] += 1
            self.ns[(t, p, s)] += 1
            self.last[(t, p)] = m["date"]


def set_prob(p: float, best_of: int = 3) -> float:
    """Per-set win probability s that reproduces match probability p (independent sets)."""
    def match(s):
        if best_of == 5:
            return s ** 3 * (1 + 3 * (1 - s) + 6 * (1 - s) ** 2)
        return s * s * (3 - 2 * s)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if match(mid) < p else (lo, mid)
    return (lo + hi) / 2


def set_scores(p: float) -> dict[str, float]:
    s = set_prob(p)
    return {"2:0": s * s, "2:1": 2 * s * s * (1 - s), "1:2": 2 * s * (1 - s) ** 2, "0:2": (1 - s) ** 2}


def market_fair(o_a: float, o_b: float) -> float:
    ia, ib = 1 / o_a, 1 / o_b
    return ia / (ia + ib)


def blend(p_market: float, p_elo: float, w: float) -> float:
    """Blend in log-odds space; w = weight of the market."""
    lg = lambda p: math.log(p / (1 - p))
    x = w * lg(min(max(p_market, 1e-4), 1 - 1e-4)) + (1 - w) * lg(min(max(p_elo, 1e-4), 1 - 1e-4))
    return 1 / (1 + math.exp(-x))


# ---------------------------------------------------------------------------- backtest
def build(years: range) -> dict:
    matches = load_matches(years)
    if not matches:
        raise SystemExit("no tennis data downloaded")
    # the last two seasons are the test set; earlier years only warm the ratings up
    test_from = f"{max(years) - 1}-01-01"
    elo = Elo()
    samples = []  # (p_elo, p_market, outcome=1 for the winner-side row)
    for m in matches:
        t, w, l, s = m["tour"], key(m["winner"]), key(m["loser"]), m["surface"]
        # market reference: Pinnacle closing odds when present, else the market average (de-vigged)
        ow, ol = (m["psw"], m["psl"]) if m["psw"] and m["psl"] else (m["avgw"], m["avgl"])
        if m["date"] >= test_from and elo.n[(t, w)] >= 10 and elo.n[(t, l)] >= 10 and ow and ol:
            pe = elo.prob(t, w, l, s)
            if m["best_of"] == 5:  # convert a bo3-calibrated probability to bo5
                sp = set_prob(pe, 3)
                pe = sp ** 3 * (1 + 3 * (1 - sp) + 6 * (1 - sp) ** 2)
            samples.append((pe, market_fair(ow, ol)))
        elo.update(m)

    def score(ps):
        # each sample is scored from the winner's side (outcome 1) — Brier and log loss are symmetric
        brier = sum((1 - p) ** 2 for p in ps) / len(ps)
        ll = -sum(math.log(max(p, 1e-9)) for p in ps) / len(ps)
        return round(brier, 4), round(ll, 4)

    report = {"test_from": test_from, "n_test": len(samples), "matches": len(matches),
              "data_until": matches[-1]["date"], "elo": score([s[0] for s in samples]),
              "market": score([s[1] for s in samples]), "blends": {}}
    for w in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        report["blends"][w] = score([blend(pm, pe, w) for pe, pm in samples])
    best_w = min(report["blends"], key=lambda w: report["blends"][w][1])
    report["best_weight_market"] = best_w if report["blends"][best_w][1] < report["market"][1] else 1.0
    # buckets: does Elo add information where it disagrees with the market?
    dis = [(pe, pm) for pe, pm in samples if abs(pe - pm) >= 0.10]
    report["disagree_10pts"] = {"n": len(dis), "elo": score([d[0] for d in dis]) if dis else None,
                                "market": score([d[1] for d in dis]) if dis else None}
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    MODEL.write_text(json.dumps({
        "report": report, "built": now_utc().isoformat(),
        "r": {f"{t}|{p}": v for (t, p), v in elo.r.items()},
        "rs": {f"{t}|{p}|{s}": v for (t, p, s), v in elo.rs.items()},
        "n": {f"{t}|{p}": v for (t, p), v in elo.n.items()},
        "ns": {f"{t}|{p}|{s}": v for (t, p, s), v in elo.ns.items()},
        "last": {f"{t}|{p}": v for (t, p), v in elo.last.items()}}))
    return report


def load_model() -> tuple[Elo, dict]:
    if not MODEL.exists():
        raise SystemExit("no model yet — run: tennis_elo.py build")
    d = json.loads(MODEL.read_text())
    elo = Elo()
    for k, v in d["r"].items():
        t, p = k.split("|"); elo.r[(t, p)] = v
    for k, v in d["rs"].items():
        t, p, s = k.split("|"); elo.rs[(t, p, s)] = v
    for k, v in d["n"].items():
        t, p = k.split("|"); elo.n[(t, p)] = v
    for k, v in d["ns"].items():
        t, p, s = k.split("|"); elo.ns[(t, p, s)] = v
    for k, v in d["last"].items():
        t, p = k.split("|"); elo.last[(t, p)] = v
    return elo, d["report"]


def find(elo: Elo, tour: str, name: str) -> Optional[str]:
    k = key(name)
    if elo.n.get((tour, k)):
        return k
    # fall back to surname match (initials sometimes differ: "Bautista Agut R." vs "Bautista R.")
    sur = k.rsplit(" ", 1)[0]
    cands = [p for (t, p) in elo.n if t == tour and p.rsplit(" ", 1)[0] == sur]
    return max(cands, key=lambda p: elo.n[(tour, p)]) if cands else None


def cmd_predict(a: str, b: str, surface: str, tour: str, odds: Optional[list[float]]) -> int:
    elo, report = load_model()
    s = SURFACES.get(surface.lower(), "Hard")
    ka, kb = find(elo, tour, a), find(elo, tour, b)
    for name, k in ((a, ka), (b, kb)):
        if not k:
            print(f"[tennis_elo] no rating for {name!r} ({tour}) — Challenger/ITF players are not in the data")
            return 2
    p = elo.prob(tour, ka, kb, s)
    print(f"# data until {report['data_until']} (matches after that are not rated)")
    for name, k in ((a, ka), (b, kb)):
        print(f"  {name:24} Elo {elo.rating(tour, k, s):7.1f} (overall {elo.r[(tour, k)]:.0f}, {s} "
              f"{elo.rs[(tour, k, s)]:.0f}; {elo.n[(tour, k)]} matches, {s} {elo.ns[(tour, k, s)]}, "
              f"last {elo.last.get((tour, k), '?')})")
    print(f"  Elo: P({a} wins) = {p:.3f}")
    print("  sets (bo3, Elo): " + ", ".join(f"{a} {sc} {v:.3f}" for sc, v in set_scores(p).items()))
    if odds:
        pm = market_fair(*odds)
        w = report.get("best_weight_market", 0.8)
        pb = blend(pm, p, w)
        print(f"  market fair: {pm:.3f}   blend (market weight {w}): {pb:.3f}   Elo − market: {p - pm:+.3f}")
        print("  sets (bo3, blend): " + ", ".join(f"{a} {sc} {v:.3f}" for sc, v in set_scores(pb).items()))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--years", default=f"2019-{now_utc().year}")
    p = sub.add_parser("predict"); p.add_argument("a"); p.add_argument("b")
    p.add_argument("--surface", default="hard"); p.add_argument("--tour", default="atp", choices=("atp", "wta"))
    p.add_argument("--odds", nargs=2, type=float)
    args = ap.parse_args()
    if args.cmd == "build":
        y0, y1 = (int(x) for x in args.years.split("-"))
        print(json.dumps(build(range(y0, y1 + 1)), indent=1))
        return 0
    return cmd_predict(args.a, args.b, args.surface, args.tour, args.odds)


if __name__ == "__main__":
    sys.exit(main())

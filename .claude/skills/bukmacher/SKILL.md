---
name: bukmacher
description: >-
  Find the most probable sports-betting selection at a target price (default 1.20) among real
  matches starting in the next 4/8/12/24 hours, using live fixture feeds, real bookmaker odds and a
  deep, self-made pre-match analysis (motivation, form, absences, lineups, schedule, market signals)
  across football, volleyball, basketball, hockey and tennis, and deliver a Polish report with
  several proposals, the reasoning, pluses and risks. Use this skill whenever the user asks for
  betting tips, "typy", "pewniaki", "co obstawić", "kurs 1.20", the safest bet today/tonight, a
  betting analysis of upcoming games, a bet scan for the next hours, or anything about bukmacher /
  zakłady / sports odds — even if they do not say "skill" or name a sport.
---

# Bukmacher — najbardziej prawdopodobny typ o zadanym kursie

The job: among **every** real fixture starting inside the chosen time window, across the five
sports, find the handful of bookmaker selections priced around the target odds whose *true*
probability you believe is highest, and explain why — with confirmed events, confirmed prices,
and an honest list of risks. You are the analyst; tipster sites are not.

Scripts live in `scripts/` (Python 3.9+, stdlib only). Run them with the skill's base directory
as the working directory (it is printed when the skill loads) and keep intermediate files in a
`work/` folder there (`fixtures.json`, `odds.json`, …); only the final report goes to `reports/`. Reference files explain sources, markets, the analysis checklist and the
report template — read them at the step that needs them, not all up front.

## Step 0 — Parameters (ask, don't assume)

Two things are the user's call and change the whole run, so ask for them with one
`AskUserQuestion` call unless the user already stated them in the prompt:

1. **Horizon**: 4 h (Recommended, default), 8 h, 12 h, 24 h.
2. **Target odds**: 1.20 (Recommended, default), 1.15, 1.30, 1.50 — "Other" lets them type any
   number or a range. Treat the answer as the centre of a band (default −0.08 / +0.10; the
   shortlist script uses that band).

Optional third question only if the prompt hints at it: restrict sports, or a bookmaker
region for The Odds API (`eu` default; Polish bookmakers are not in the API — say so).
Where no interactive tool exists (headless run), use the defaults and state that at the top of
the report.

## Step 1 — Verify the clock

The window is meaningless if "now" is wrong, and you have no innate sense of the date.

```bash
mkdir -p work && python3 scripts/clock.py
```

Use `verified_utc` from its output as T0 for every later step (`--now`). If no external source
was reachable, `date -u` is only a hypothesis: confirm the date from a fetched live-score page
(the fixtures list itself shows "today's" dates) before trusting the window, and say in the
report which clock you trusted. Convert to the user's local time (Poland: CET/CEST) in the report.

## Step 2 — Collect every fixture in the window

```bash
python3 scripts/fixtures.py --hours 4 --now <verified_utc> --out work/fixtures.json
```

Sofascore (keyless) gives the widest coverage — club leagues, cups, national teams,
qualifiers, ATP/WTA/Challenger, volleyball leagues and FIVB; ESPN adds its own list plus
ESPN BET odds; api-sports joins if `APISPORTS_KEY` is set. Events already in progress,
postponed or cancelled are dropped. Read `references/sources.md` when a source fails (403 from
Sofascore on datacentre IPs is common) — it lists the WebFetch/WebSearch fallbacks per sport.

Sanity-check the list: does it contain the big games you would expect tonight? An empty
sport with no error usually means the source has no coverage (ESPN has no volleyball), not that
nothing is played. If the window is quiet (few events), say so rather than stretching it.

## Step 3 — Real odds and a shortlist

```bash
python3 scripts/odds.py --fixtures work/fixtures.json --out work/odds.json
python3 scripts/shortlist.py work/odds.json --target 1.20 --out work/shortlist.json
```

`odds.py` pulls every market the sources expose (1X2, double chance, draw-no-bet, totals,
Asian handicaps, BTTS, set/game handicaps, first-half…) and computes `fair_prob` — the
bookmaker's own de-vigged probability, valid only inside mutually exclusive markets
(double chance is derived from 1X2). `shortlist.py` keeps selections priced inside the band,
merges the same bet across bookmakers, and ranks by fair probability. Set `ODDS_API_KEY`
(The Odds API) for Pinnacle and a dozen EU books; run with `--extra-markets --only-keys …`
on the finalists only, because it costs credits.

Treat the shortlist as candidates, not answers: bookmaker margin is loaded onto favourites,
so the de-vigged number is an upper bound on the truth. Read `references/markets.md` for the
markets worth considering per sport, and their traps (hockey 60-minute vs incl. OT, tennis
retirement rules, volleyball set handicaps, Asian handicap refunds).

Keep 8–15 candidates spanning sports and market types; do not let one sport or one league
dominate just because it has more fixtures. Prefer a market that makes losing require two
independent things to go wrong over a plain win at the same price.

## Step 4 — Deep analysis (this is where the value is)

For every finalist run the context script and then research what it cannot see:

```bash
python3 scripts/context.py --fixtures work/fixtures.json --key "<fixture key>" --out work/ctx_<n>.json
```

It prints lineups (confirmed or not), missing players, form with scores, the next fixture of
each side (rotation risk), head-to-head, the table, venue and referee. Then work through
`references/analysis.md`: motivation and stakes, real form (opponent-adjusted, xG where
available), absences and *who* replaces them, predicted/confirmed lineups and when they are
published, schedule and travel, venue and conditions, style match-ups, market signals (drift,
sharp vs soft books), sport-specific killers (starting goalie, tennis fitness/withdrawal,
volleyball rotation, NBA rest days), and data quality (youth, women's, reserve, lower-tier or
exhibition games = thin data, thin markets, no bet).

Use WebSearch/WebFetch for news, injury reports, press conferences and official sources
(club sites, NBA injury report, DailyFaceoff, ATP/WTA, PlusLiga, FIVB). Ignore prediction
sites and tipster "pewniaki": they are not evidence. Form your own probability estimate
(`p_est`) for each finalist and write one line on *what has to happen for this bet to lose*.
Drop any finalist whose `p_est` is not clearly above the implied probability of the price.

Never analyse a game that has already started (T0 vs start time) or a price you did not fetch.

## Step 5 — Rank and report

Rank by `p_est`, tie-break by edge (`p_est × odds − 1`) and by liquidity (number of books
agreeing). Present 3–5 proposals plus the notable rejected candidates and why. Write the report
in the user's language (Polish by default) using `references/report-template.md`, save it to
`reports/<YYYY-MM-DD_HHMM>_typy.md` in the project and print it in the reply. Every proposal
must carry: event, competition, start time (UTC and local), market and selection, the odds
with bookmaker + source + fetch time, `p_est` vs implied, the reasoning, pluses, risks, and
the "how it loses" line. State plainly that odds move and must be re-checked at the bookmaker
before placing anything; single bets, not accumulators, unless asked.

## Hard rules

- Confirmed facts only: a fixture without a source id and a price without a source line do not
  go into the report. If a source failed, say which and what you used instead.
- The user's constraints (window, odds) beat convenience: no "1.45 but it's a great bet"
  unless flagged as outside the band.
- Small samples and exotic markets (correct score, HT/FT, player props in thin leagues) are
  out unless the user asks.
- Betting is risky by nature; one short sentence of responsible-gambling caution in the report
  is enough, no lecture.

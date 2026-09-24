---
name: bukmacher
description: >-
  Find the most probable sports-betting selections in each odds range (1.10-1.19, 1.20-1.29,
  1.30-1.44, 1.45-1.60; all four by default) among real matches starting in the next 4/8/12/24 hours, using live fixture feeds, real bookmaker odds and a
  deep, self-made pre-match analysis (motivation, form, absences, lineups, schedule, market signals)
  across football, volleyball, basketball, hockey and tennis, and deliver a Polish HTML report with
  several proposals per range, the reasoning, pluses and risks. Use this skill whenever the user asks for
  betting tips, "typy", "pewniaki", "co obstawić", "kurs 1.20", the safest bet today/tonight, a
  betting analysis of upcoming games, a bet scan for the next hours, or anything about bukmacher /
  zakłady / sports odds — even if they do not say "skill" or name a sport.
---

# Bukmacher — najbardziej prawdopodobne typy w zakresach kursów

The job: among **every** real fixture starting inside the chosen time window, across the five
sports, find — separately for each chosen odds range — the handful of bookmaker selections
whose *true* probability you believe is highest, and explain why — with confirmed events, confirmed prices,
and an honest list of risks. You are the analyst; tipster sites are not.

Scripts live in `scripts/` (Python 3.9+, stdlib only). Run them with the skill's base directory
as the working directory (it is printed when the skill loads) and keep intermediate files in a
`work/` folder there (`fixtures.json`, `odds.json`, …); only the final report goes to `reports/`. Reference files explain sources, markets, the analysis checklist and the
HTML report template — read them at the step that needs them, not all up front.

API keys (`ODDS_API_KEY`, `APISPORTS_KEY`) are read from the environment or, failing that, from
a gitignored `.env` file in the skill directory (`KEY=value` per line). Never print a key or
write it anywhere else.

## Step 0 — Parameters (ask, don't assume)

Two things are the user's call and change the whole run, so ask for them with one
`AskUserQuestion` call unless the user already stated them in the prompt:

1. **Horizon**: 4 h (Recommended, default), 8 h, 12 h, 24 h.
2. **Odds ranges** (`multiSelect: true`): `1.10–1.19`, `1.20–1.29`, `1.30–1.44`, `1.45–1.60`.
   Say in the question that the default is all four — and if the user selects nothing, or
   answers "all"/"domyślnie", run all four. The ranges are contiguous and fixed in
   `scripts/shortlist.py` (`RANGES`); a selection belongs to the range of its *median* price.
   "Other" lets them type a custom range (e.g. `1.25–1.35`) → `--min/--max`. A single price in
   the prompt ("kurs około 1.20") means the range that contains it — don't ask again.

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

## Step 1b — Settle the ledger (before looking at tonight)

Every proposal and every near-miss is recorded in `<project>/data/ledger.jsonl`. Before the
new analysis, settle what has finished and look at the scoreboard:

```bash
python3 scripts/ledger.py settle            # final scores + closing odds from betexplorer
python3 scripts/ledger.py stats --html work/stats.html --json work/stats.json
python3 scripts/ledger.py list --open       # anything stuck as "manual" needs a look
```

Read the result before choosing anything: for every settled *pick* that lost, and every
"paper" candidate that won, ask whether it was foreseeable (a missed absence, a wrong market,
a bar set too high) and write one line on it into the report's "Wnioski" (lessons). Watch
**CLV** (price taken vs the closing median) more than the win rate: over a few dozen bets a
positive average CLV is the best evidence the analysis beats the market; the win rate needs
hundreds. Entries marked `manual` (postponed, abandoned, unparsable) are settled by hand in the
ledger file.

## Step 2 — Collect every fixture in the window

```bash
python3 scripts/fixtures.py --hours 4 --now <verified_utc> --out work/fixtures.json
```

Sofascore (keyless) gives the widest coverage — club leagues, cups, national teams,
qualifiers, ATP/WTA/Challenger, volleyball leagues and FIVB; ESPN adds its own list plus
ESPN BET odds; api-sports joins if `APISPORTS_KEY` is set. Events already in progress,
postponed or cancelled are dropped. Read `references/sources.md` when a source fails (403 from
Sofascore on datacentre IPs is common) — it lists the WebFetch/WebSearch fallbacks per sport.

`scripts/betexplorer.py` is the keyless fallback that has worked when Sofascore did not: fixture
lists with average odds for hockey, basketball, tennis, volleyball and football, times already
converted to UTC:

```bash
python3 scripts/betexplorer.py next --sport hockey --hours 4 --out work/be_hockey.json
```

Sanity-check the list: does it contain the big games you would expect tonight? An empty
sport with no error usually means the source has no coverage (ESPN has no volleyball), not that
nothing is played. If the window is quiet (few events), say so rather than stretching it.

## Step 3 — Real odds and a shortlist

```bash
python3 scripts/odds.py --fixtures work/fixtures.json --out work/odds.json
python3 scripts/shortlist.py work/odds.json --out work/shortlist.json   # all four ranges
# only some: --ranges 1.20-1.29,1.30-1.44   ·   custom: --min 1.25 --max 1.35
```

`odds.py` pulls every market the sources expose (1X2, double chance, draw-no-bet, totals,
Asian handicaps, BTTS, set/game handicaps, first-half…) and computes `fair_prob` — the
bookmaker's own de-vigged probability, valid only inside mutually exclusive markets
(double chance is derived from 1X2). `shortlist.py` merges the same bet across bookmakers,
puts it in the range of its median price and ranks each range by fair probability. With `ODDS_API_KEY`
(The Odds API, in `.env`) it adds Pinnacle and a dozen EU books; the free plan has 500
credits a month: name the leagues actually playing with `--oddsapi-keys` (e.g.
`soccer_uefa_nations_league,basketball_euroleague`), run `--extra-markets --only-keys …` on
the finalists only, and report the remaining credits the script prints.

Polish bookmakers' prices (and every market line, Asian totals and handicaps included) come
from betexplorer for any match id from its lists or match URLs:

```bash
python3 scripts/betexplorer.py odds <match_id> 1x2 dc ou ah bts   # ha instead of 1x2 for no-draw sports
```

Treat the shortlist as candidates, not answers: bookmaker margin is loaded onto favourites,
so the de-vigged number is an upper bound on the truth. Read `references/markets.md` for the
markets worth considering per sport, and their traps (hockey 60-minute vs incl. OT, tennis
retirement rules, volleyball set handicaps, Asian handicap refunds).

Keep 5–10 candidates **per range** spanning sports and market types; do not let one sport or
one league dominate just because it has more fixtures. The same fixture may appear in several
ranges through different markets (e.g. a 1.15 win and a 1.40 handicap) — analyse the match
once and reuse it. Prefer a market that makes losing require two
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
Drop any finalist whose `p_est` is not clearly above the implied probability of the price
(per-range bars in `references/analysis.md` §12).

Never analyse a game that has already started (T0 vs start time) or a price you did not fetch.

## Step 5 — Rank and report

Within each range rank by `p_est`, tie-break by edge (`p_est × odds − 1`) and by liquidity
(number of books agreeing). Present up to 3 proposals per range plus the notable rejected
candidates and why; a range with nothing worth betting says so instead of padding. The report
is **one HTML file with a section per range**: copy `references/report-template.html`
(self-contained, inline CSS, light/dark, phone-friendly), fill it in the user's language
(Polish by default) and save it to `reports/<YYYY-MM-DD_HHMM>_typy.html` in the project. In
the reply give a ranking table per range and the one-line "how it loses" per proposal in
Markdown — not the whole HTML — and **always end
the reply with the report's `file://` link** on its own line, ready to paste into a browser.
Build it from the saved file, never by hand, so spaces and Polish characters are encoded:

```bash
python3 -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().as_uri())" <project>/reports/<file>.html
```

Every proposal
must carry: event, competition, start time (UTC and local), market and selection, the odds
with bookmaker + source + fetch time, `p_est` vs implied, the reasoning, pluses, risks, and
the "how it loses" line. State plainly that odds move and must be re-checked at the bookmaker
before placing anything; single bets, not accumulators, unless asked.

The report also carries the scoreboard: paste `work/stats.html` (from Step 1b) into the
template's "Skuteczność" section, and fill "Wnioski" with the lessons from the settled bets —
or say that nothing settled yet.

**Record the run in the ledger** — every proposal as `kind: "pick"` and every rejected
candidate within ~0.03 of the bar as `kind: "paper"` (the paper bets are how we learn whether
the bar is too strict). Write them as a JSON list (schema in `scripts/ledger.py`'s docstring;
`be` must point at the betexplorer match and the exact bet type / line / column so the closing
price can be read later) and add them:

```bash
python3 scripts/ledger.py add work/picks.json
```

A proposal without a betexplorer reference cannot be settled — find the match there before
publishing it, or leave it out.

## Hard rules

- Confirmed facts only: a fixture without a source id and a price without a source line do not
  go into the report. If a source failed, say which and what you used instead.
- The user's constraints (window, ranges) beat convenience: a selection sits only in the range
  of its median price; a bet only one bookmaker prices into a range is flagged as such, and
  ranges the user did not choose are not reported.
- Small samples and exotic markets (correct score, HT/FT, player props in thin leagues) are
  out unless the user asks.
- Betting is risky by nature; one short sentence of responsible-gambling caution in the report
  is enough, no lecture.

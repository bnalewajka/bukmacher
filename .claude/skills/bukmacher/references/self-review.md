# Weekly self-review — how the skill improves itself

Run by `.github/workflows/review.yml` (Sundays, Opus) or by hand. The owner has authorised
the review to change the skill on its own judgement; the guard-rails below are what keeps
that from turning noise into rules.

## 1. Gather the evidence

```bash
cd .claude/skills/bukmacher
python3 scripts/ledger.py settle          # anything still open that has finished
python3 scripts/ledger.py stats --json work/stats.json
python3 scripts/ledger.py list
```

Read: `work/stats.json` (by kind, by range, calibration), `data/ledger.jsonl` (every settled
entry with score, CLV, p_est), `data/lessons.md` (the per-report lessons), `data/changelog.md`
(what earlier reviews changed and why — do not undo a change without new evidence), and the
reports of the last 7 days in `reports/`.

## 2. Diagnose — questions to answer in writing

- **Calibration.** Per p_est bucket, is the hit rate close to p_est? Consistently lower means
  p_est is optimistic → the analysis over-adjusts from the market; consistently higher means the
  bar is too strict.
- **CLV.** Average and share of positive CLV for picks. Negative average CLV over 20+ picks is
  the clearest sign the analysis does not beat the market (whatever the win rate says).
- **Tiers.** Do "value" picks (p_est ≥ implied + 0.03) beat "fair" picks on hit rate vs p_est
  and on CLV? If not, p_est does not separate them and the tier label is noise. Do "paper"
  bets (dropped just below implied) win as often as fair picks? Then p_est is too pessimistic.
- **Research depth.** Do picks whose `sources` include more pages read in full do better
  (hit rate vs p_est, CLV) than thinly researched ones? Were any lost picks built on a fact
  that turned out wrong or outdated — which source was it?
- **Ranges, sports, markets.** Where do losses and negative CLV concentrate? (e.g. basketball
  moneylines at 1.20–1.29, football unders, Euroleague openers.)
- **Process.** From `lessons.md`: recurring causes — a missed absence, stale price, wrong
  settlement assumption, a source failing, too few candidates, time wasted.
- **Operations.** Runs that failed or produced no report (workflow history if available),
  credits burnt per run, sources that errored.

## 3. Decide what to change — guard-rails

- **Sample sizes.** Numbers are not evidence below: 30 settled picks for anything about
  calibration or thresholds overall; 20 within a range/sport/market before changing rules for
  that slice. Below that, you may only change *process* (checklists, sources, instructions
  that prevent a concrete, documented mistake) — not thresholds or market preferences.
- **One hypothesis per change**, stated with the evidence (numbers + entry ids) and what
  result next week would show it was wrong.
- **Small steps.** Bars move by at most 0.01 per review; never loosen and tighten the same
  thing in consecutive weeks without new evidence.
- **Keep the invariants.** Confirmed facts only; no prices that were not fetched; single bets;
  responsible-gambling line; the report/ledger formats (the site and the settlement depend
  on them); the free-plan credit budget unless the owner upgraded.
- Code changes are allowed (scripts, tests, templates). Every code change needs a test or an
  updated test, and `python3 -m pytest -q tests` must pass before you finish. If it does not,
  revert your code change and write down why in the changelog.

## 4. Record

Append to `data/changelog.md`:

```markdown
## <date> — weekly review
Sample: <n picks settled (W–L–P)>, <n paper>, CLV avg <x>, hit <y> vs p_est <z>.
Findings: <3–6 bullets with numbers and entry ids>.
Changes: <file — what — why — how we will know it worked>  (or "none — sample too small")
Next review: <what to look at first>.
```

Keep `data/lessons.md` as is (it is the raw log). End with a short plain-text summary of the
findings and the changes.

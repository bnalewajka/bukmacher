# Analysis checklist — what decides whether a 1.20 favourite actually delivers

Go through every heading for every finalist. Write down what you found, not just the
heading; "checked, nothing" is a valid finding. The purpose is to estimate `p_est`
independently from the price and to name the failure mode of the bet.

## 1. Stakes and motivation
- Table position and what is still at stake (title race, European places, relegation, play-off
  seeding, promotion). A mid-table team in May, a group already decided, a Nations League
  dead rubber, a pre-season friendly = low motivation, high rotation.
- Competition priority: a domestic cup between two European games, a league game three days
  before a Champions League decider, a tennis 250 event the week before a Slam, a volleyball
  league match before a CEV final.
- Derby / rivalry / revenge / manager under pressure / new manager bounce / farewell game.
- International windows: national-team call-ups leave clubs short; national teams themselves
  may field B-squads (volleyball and basketball qualifiers especially).

## 2. Form, properly
- Last 5–10 results *and* who they were against; a win streak against bottom teams is not
  form. Use the table + form from `context.py`; look at goal difference, xG (football) where
  you can find it, point differential (basketball), shot share/PDO (hockey), set ratios
  (volleyball), recent match durations and retirements (tennis).
- Home/away split of both sides. Away favourites are overrated by the public.
- Regression: a team winning every game 1-0 with low xG is due a draw.

## 3. Absences and their replacements
- Injuries, suspensions (card accumulation!), illness, international duty, personal leave,
  transfer-listed players frozen out. Not just "is the star out" but who plays instead and
  how the team performed without them this season.
- Goalkeeper / starting goalie / setter / point guard — the single position that changes the
  probability the most in each sport. In hockey, confirm the starting goalie or discount the bet.
- Tennis: injuries carried from the last tournament, medical time-outs, walkovers this month,
  a player who has retired mid-match more than once this season.

## 4. Lineups
- Confirmed lineup available? (`lineups_confirmed`). If not, when will it be, and is the
  window long enough to wait for it? For games starting within ~75 minutes, the confirmed
  football XI exists — fetch it. NBA: final injury report ~30 min before. NHL: goalie
  confirmations after morning skate.
- Rotation signals: next fixture within 3 days (`home_next` / `away_next`), a manager who
  historically rotates, five subs used aggressively, an academy-heavy cup XI.
- Formation/style change after a new manager.

## 5. Schedule, travel, physical state
- Days since last match; extra time in the last match; back-to-backs (NBA/NHL); long-haul
  travel and time zones (CONMEBOL/AFC qualifiers, US teams in Europe); altitude (La Paz,
  Quito, Bogotá, Denver); midweek European game returning late.
- Tennis: matches played this week (singles + doubles), night finishes, rain-delay backlogs.

## 6. Venue and conditions
- Real home advantage (some "home" games are neutral or behind closed doors or in a
  temporary stadium); artificial turf; pitch quality; weather (heavy rain/wind kills goals;
  extreme heat slows games; snow in hockey does not matter but a flooded football pitch does).
- Tennis surface fit (clay specialist on grass), indoor vs outdoor, altitude balls.
- Volleyball/basketball arenas: nothing physical, but travel (Russian/Kazakh away trips).

## 7. Style match-up and tactical fit
- Does the favourite create a lot but finish poorly (over 1.5 goals risk)? Does the underdog
  park the bus (DC safer than win)? Counter-attacking dogs vs high line favourites.
- Hockey: goalie quality vs shot volume; power-play vs penalty-kill.
- Basketball: pace, 3-point variance, zone defence vs poor shooting.
- Tennis: serve-dominant player on fast court (tie-breaks = variance), returner on clay.
- Volleyball: block/serve strength vs reception; a strong serving team beats a weak reception team 3-0.

## 8. Head-to-head, but with care
- H2H matters when the same coaches and cores meet repeatedly (tennis H2H, derby psychology,
  a team that never wins at a specific venue). Otherwise it is noise; do not lean on it.

## 9. Market signals
- Drift since opening: lengthening favourite = information you lack. Sharp (Pinnacle,
  Betfair exchange) vs soft (bet365, Unibet, STS) difference. Number of books agreeing.
- Money on the total often tells you about lineups before the news does.
- Suspended or missing markets at the source can mean a doubt about the event (weather,
  postponement, a retirement rumour).

## 10. Data quality and event integrity
- Youth (U19/U21), women's leagues below top level, reserve teams, friendlies, lower tiers,
  exhibition and "esports-like" streams (Ukrainian 3rd league, Simulated Reality) — thin data,
  thin markets, occasional integrity problems. Exclude unless the user insists.
- Confirm the event exists at two sources, the start time matches, and the market is
  pre-match (not live).

## 11. Sport-specific killers (say which applies)
- Football: late red cards, penalties, VAR, set-piece weakness, keeper errors, a 90+ minute
  equaliser in a game the favourite has stopped pressing.
- Basketball: star rested at the last minute, foul trouble, three-point luck, tanking teams
  suddenly trying.
- Hockey: backup goalie, empty-net goals, OT/shootout coin flips, three-way vs two-way market.
- Tennis: injury, retirement, fatigue, first-round rust, motivation at small events, weather
  interruptions, lucky loser fresh from a win.
- Volleyball: rotation in group stages, a libero/setter absence, a hot server on the other side,
  a home crowd for the underdog in the 5th set.

## 12. Put a number on it
- Start from the de-vigged market probability (`fair_prob`), then adjust with what you found
  above. Say why you moved it and by how much. Be honest: most 1.20 favourites are fairly
  priced; the point is to find the *few* where the evidence stacks up on the same side.
- Write the "how this loses" line. If you cannot describe a realistic losing scenario, you
  have not analysed it enough; if the losing scenario is easy to imagine and likely, drop it.
- Calibration anchors: 1.20 → break-even 83 %. A proposal needs `p_est ≥ 0.86` to be worth
  listing at 1.20; at 1.30, ≥ 0.80; at 1.15, ≥ 0.89.

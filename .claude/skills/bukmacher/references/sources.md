# Data sources

Everything below is used by `scripts/`; the fallback column is what to do by hand (WebFetch /
WebSearch) when a script's source fails or the network policy blocks the host. In a Claude Code
cloud environment the hosts listed in the "Host" column must be allowed in the environment's
network settings; locally nothing is needed except optional API keys.

## Time
| Purpose | How | Notes |
|---|---|---|
| Verified UTC | `scripts/clock.py` — median of HTTP `Date:` headers from several hosts vs system clock | Exit code 2 = drift or nothing reachable. Fallback: fetch any live-score page and read "today". |

## Fixtures (who plays in the window)
| Source | Host | Key | Covers | Quirks |
|---|---|---|---|---|
| Sofascore | `api.sofascore.com/api/v1/sport/{football,basketball,ice-hockey,tennis,volleyball}/scheduled-events/{YYYY-MM-DD}` (+`/inverse`) | none | all five sports; clubs, national teams, cups, qualifiers, friendlies, ATP/WTA/Challenger/ITF, volleyball leagues/FIVB | unofficial JSON; browser User-Agent required (lib does it); datacentre IPs get 403 sometimes; `status.type` = notstarted / inprogress / finished / postponed |
| ESPN | `site.api.espn.com/apis/site/v2/sports/{soccer,basketball,hockey,tennis}/{league}/scoreboard?dates=YYYYMMDD-YYYYMMDD` | none | soccer by league slug (eng.1, esp.1, ger.1, ita.1, fra.1, pol.1, uefa.champions…), nba/wnba/college, nhl, atp/wta | no volleyball; tennis scoreboard nests matches in `groupings[].competitions[]`; carries `competitions[].odds[]` (ESPN BET) |
| api-sports | `v3.football.api-sports.io/fixtures?date=`, `v1.{basketball,hockey,volleyball}.api-sports.io/games?date=` | `APISPORTS_KEY` (header `x-apisports-key`) | football, basketball, hockey, volleyball | free plan ≈100 req/day per sport API; ids reused by odds/injuries/lineups/predictions endpoints |

Fallback by hand: `https://www.flashscore.pl/` / `livesport.com` (per sport pages), `https://www.sofascore.com/{sport}/{date}`, `https://www.espn.com/soccer/scoreboard`, league sites (`plusliga.pl`, `nhl.com/schedule`, `nba.com/schedule`, `atptour.com/en/scores/current`, `wtatennis.com/scores`, `volleyballworld.com`).

## Odds
| Source | Host | Key | Markets | Quirks |
|---|---|---|---|---|
| Sofascore odds | `api.sofascore.com/api/v1/event/{id}/odds/1/all` | none | everything the partner book offers: 1X2, double chance, DNB, totals by line, Asian handicap, BTTS, HT markets, sets/games, team totals | provider `1` = one bookmaker (bet365 in most of Europe); fractional strings (`"1/5"` = 1.20), `initialFractionalValue` gives opening price → drift; `isLive` markets skipped |
| The Odds API | `api.the-odds-api.com/v4/sports/{key}/odds?regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal&commenceTimeFrom=&commenceTimeTo=`; extra markets per event: `/v4/sports/{key}/events/{id}/odds?markets=btts,draw_no_bet,alternate_spreads,alternate_totals,team_totals,h2h_h1,totals_h1,…` | `ODDS_API_KEY` (free 500 credits/month; 1 credit per region × market group per call) | h2h, spreads, totals from Pinnacle, Betfair, Unibet, Betsson, William Hill, 1xBet, Marathon, Betclic… | sport keys are per league/tournament (`soccer_epl`, `soccer_poland_ekstraklasa`, `basketball_euroleague`, `icehockey_nhl`, `tennis_atp_*`); no volleyball; Polish books absent; `x-requests-remaining` header printed by the script |
| api-sports odds | `/odds?fixture={id}` (football) / `/odds?game={id}` (others) | `APISPORTS_KEY` | dozens of markets × many bookmakers (Bet365, Pinnacle, 1xBet, Unibet, Betsson…) | one request per event — feed it the shortlist, not the whole day |
| ESPN BET | inside the ESPN scoreboard | none | moneyline, spread, total | US-centric; American odds converted by the script |

Fallback by hand: `https://www.oddsportal.com/` (match page → compare bookmakers), `https://www.betexplorer.com/`, the Sofascore match page "Odds" tab, `https://www.flashscore.pl/mecz/{id}/#/zestawienie-kursow`. Polish prices: `sts.pl`, `fortuna.pl`, `superbet.pl`, `betclic.pl` (WebFetch of their sites often fails; quote what you can and say it is unverified if you cannot).

Sharp reference: Pinnacle (via The Odds API or oddsportal). If Pinnacle is meaningfully shorter than the soft book, the soft price is value; if Pinnacle is longer, be suspicious.

## Context (lineups, absences, form, schedule, news)
| Need | Source |
|---|---|
| Lineups, missing players, form, h2h, next fixture, table | `scripts/context.py` (Sofascore event/lineups, pregame-form, h2h, team events last/next, standings; ESPN summary rosters/injuries/officials/weather) |
| Football injuries & suspensions | Transfermarkt ("Injuries & suspensions" per club), club official sites, pre-match press conferences (WebSearch `"<club>" press conference <date>`), `whoscored.com` preview / `sofascore` "missing players" |
| Football predicted XI | club press, `whoscored.com/Matches/{id}/Preview`, `sportsmole`, beat reporters; confirmed XI ~60–75 min before kick-off |
| NBA | official injury report (`official.nba.com/nba-injury-report-*`, published ~5:30 pm ET and updated; final ~30 min pre-tip), `rotowire.com/basketball/nba-lineups.php`, back-to-back schedule |
| NHL | starting goalies + line combos: `dailyfaceoff.com/starting-goalies`, `nhl.com` injuries, morning-skate reports; goalie is the single biggest variable |
| Euroleague / national basketball | club sites, `euroleaguebasketball.net` game centre, Eurohoops injury notes |
| Tennis | `atptour.com` / `wtatennis.com` (draws, withdrawals, order of play), `tennisexplorer.com` (results, retirements, surface records), player fitness news; check "walkover"/"retired" history of both players |
| Volleyball | `plusliga.pl`, `volleyballworld.com`, `cev.eu`, `volleybox.net` (rosters, injuries), club social media |
| Hockey Europe (SHL, Liiga, Extraliga, KHL, PHL) | league sites, `eliteprospects.com` rosters/injuries |
| Weather (outdoor football/tennis) | `open-meteo.com` API (keyless), or WebSearch "<city> weather <date>" |
| Referee tendencies | `whoscored` referee stats, `transfermarkt` referee page, `football-referee.com` |

Search operator patterns that work: `"<team>" injury news`, `"<team>" "predicted lineup"`, `"<player>" doubtful OR ruled out`, `<team> rotation Champions League`, `"<player>" withdraws OR retires tournament`, `starting goalie <team> tonight`.

## Predictions to ignore
Tipster sites, "sure bets", "pewniaki dnia", AI prediction aggregators, forum consensus. They
have no accountability and often copy each other. Use the *market* (prices, drift, sharp vs
soft) as the only external opinion, and your own analysis for the rest.

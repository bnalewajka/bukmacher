# Dziennik zmian skilla

Każda zmiana wprowadzona przez cotygodniowy przegląd (albo ręcznie) z uzasadnieniem.

## 2026-09-24 — start
Sample: 0 rozliczonych (4 typy, 10 na papierze otwartych).
Changes: zakresy kursów 1.10–1.19 / 1.20–1.29 / 1.30–1.44 / 1.45–1.60 z progiem p_est ≥ implikowane + 0.03; raport HTML; dziennik typów z rozliczaniem (ESPN, The Odds API, betexplorer) i CLV z ostatniej ceny przed startem; tryb automatyczny w GitHub Actions (3 raporty dziennie, Sonnet 5; przegląd tygodniowy, Opus).
Next review: czy rozliczenia działają bez ręcznych poprawek; ile kredytów The Odds API schodzi na raport.

## 2026-09-24 — poprawki po pierwszym raporcie z chmury (z „Wniosków” raportu 20:31)
Findings: (1) `fixtures.py` pytał ESPN o zakres dat, ESPN odpowiadał 400 dla okien przez północ UTC, a błąd był cicho połykany — wieczorny raport (okno 8 h) tracił WNBA; (2) The Odds API zwraca giełdy (Betfair Exchange, Matchbook…) i rynki `h2h_lay` — ceny przed prowizją / zakłady „przeciw”, które wypływały jako „najlepszy kurs” (Mystics 1.15 na Betfair przy medianie 1.12).
Changes: `fixtures.py` — ESPN odpytywany dzień po dniu, deduplikacja po id; `odds.py` — pomijane giełdy i rynki `*_lay`; testy na oba przypadki. Jak poznamy, że działa: wieczorne raporty widzą mecze po północy UTC; `best_odds` pochodzi od bukmacherów, nie z giełd.

## 2026-09-24 — decyzja właściciela: typy w każdym zakresie
Findings: raport 20:31 dał 0 typów w 4 zakresach — próg „p_est ≥ implikowane + 0.03” na płynnych rynkach (Pinnacle + kilkanaście książek zgodnych) przepuszcza bardzo rzadko cokolwiek, a właściciel chce najbardziej prawdopodobnych zakładów w każdym przedziale kursów przy każdym raporcie.
Changes: SKILL.md / analysis.md / szablon / ledger — do 3 typów na zakres z dwóch klas: „z przewagą” (≥ implikowane + 0.03) i „uczciwa cena” (implikowane ≤ p_est < +0.03); poniżej implikowanego nadal nie publikujemy (papier). Statystyki osobno dla klas. 4 wcześniejsze typy dostały klasę z własnych liczb (3× fair, Serbia–Grecja value). Wpisy „papier” z raportu 20:31 zostają papierem (nie były opublikowane jako typy).
How we will know: po ~30 rozliczonych typach na klasę — czy „z przewagą” ma lepsze CLV i trafność względem p_est niż „uczciwa cena”; jeśli nie, etykieta jest szumem.

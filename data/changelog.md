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

## 2026-09-25 — minimum researchu dla typów (decyzja właściciela)
Findings: lokalny przebieg 12:56 opublikował 3 typy po 4 wyszukiwaniach łącznie (1 na finalistę) i bez żadnego przeczytanego źródła — tylko streszczenia wyszukiwarki, które wcześniej zmyślały wyniki niezagranych meczów.
Changes: SKILL.md — typ wymaga ≥ 2 niezależnych źródeł (różne serwisy) i ≥ 1 przeczytanego w całości (WebFetch / strona oficjalna); fakty zmieniające p_est tylko z przeczytanych stron. `ledger.py add` odrzuca typ bez tego (`sources: [{url, what, read}]`); słabiej zbadany kandydat → papier. Szablon: przy typie liczba źródeł i przeczytanych. Self-review: porównuje wyniki typów wg głębokości researchu.
How we will know: brak typów opartych na zmyślonych faktach w „Wnioskach”; po ~30 typach — czy głębiej zbadane mają lepsze CLV / trafność względem p_est.

## 2026-09-27 — weekly review
Sample: 30 typów rozliczonych (23–6–1), 42 papier (30–12; po usunięciu duplikatów 29 wpisów, 20–9), CLV śr. +1.3% (73% dodatnich, n=22), trafność 79.3% vs p_est 79.0% (implikowane 76.3%), zysk +0.98 u (ROI +3.3%), Brier 0.152.
Findings:
- Kalibracja typów trafiona (79.3% vs 79.0%, dokładnie próg n=30) i CLV dodatnie → brak podstaw do ruszania progów. Papier (bez duplikatów) 69% vs p_est 73.7% i implikowane 76.1%, ROI −10% — odrzucenia były słuszne, p_est nie jest zbyt pesymistyczne.
- Klasy „z przewagą” vs „uczciwa cena” nie różnią się: 7–2–1 vs 16–4, trafność 0.78 vs 0.80, CLV +1.36% vs +1.24% (n=10 vs 20). Etykieta na razie wygląda na szum, ale „value” poniżej 20 — bez zmian.
- Głębokość researchu: typy z ≥ 2 przeczytanymi źródłami 7–3 (CLV +1.1%, n=9) vs 1 przeczytane 8–1 (CLV +1.5%, n=8) — brak przewagi głębszego researchu na tej próbie; typy sprzed reguły źródeł 8–2–1. Za mało, by wnioskować.
- Jedyna porażka zbudowana na błędnym fakcie: 2026-09-25_2052_typy#1 (Novorizontino, Série B, 0:0) — gazetaesportiva.com wystawił w przewidywanym składzie dwóch zawieszonych za kartki (Patrick, Matheus Bianqui), wykrył to dopiero raport 23:56 (Terra). Pozostałe porażki: Lynx (miękka narracja motywacyjna, 2059#3), Sakkari (bez źródeł, 1256#3), Gruzja 1X (1310#3), Salzburg (1328#3), Wydad U3.5 (1422#5) — bez wspólnego wzorca.
- Wycinki: 1.45–1.60 typy 3–2 przy p_est 0.68 (n=5), tenis 2–1 (−0.72 u), h2h 14–4 (−0.52 u) vs unders 8–1 (+1.97 u) — wszystkie poniżej 20, bez zmian reguł.
- Rejestr liczy te same zakłady wielokrotnie: 12 grup powtórzeń (np. Houston–SKC papier 2026-09-26_2011_typy#5 i 2026-09-26_2342_typy#2; Portugalia typ 1835#2 + papier 1851#3 i 2031#1). 13 z 42 wpisów papieru to powtórzenia; w 1.45–1.60 dwie z pięciu porażek papieru to duplikaty — statystyki papieru, na których opiera się pytanie „czy p_est jest zbyt pesymistyczne”, są zniekształcone.
Changes:
- `scripts/ledger.py` (`add`) — nie dopisuje ponownie tego samego zakładu (drużyny, dzień, rynek, selekcja, linia): papier pomijany, jeśli selekcja już jest w rejestrze; typ pomijany, jeśli już jest jako typ; papier → typ nadal dopisywany. Test `test_ledger_skips_repeated_selection`. Dlaczego: jeden wynik liczony 2–3 razy. Jak poznamy, że działa: w kolejnym tygodniu 0 nowych grup powtórzeń w `ledger.py list`; źle, jeśli pojawią się mimo to (np. inna pisownia nazw — wtedy klucz po `ref.event_id`). Historycznych duplikatów nie usuwano (surowy log); liczby „bez duplikatów” powyżej policzone ręcznie.
- `references/analysis.md` §3 — w piłce osobne sprawdzenie zawieszeń (kartki) w źródle, które je wymienia; przewidywany skład to nie to samo; bez takiego sprawdzenia kandydat zostaje papierem. Dlaczego: 2026-09-25_2052_typy#1. Jak poznamy: brak porażek typów, w których „Wnioski” wskazują pominięte zawieszenie.
Next review: kalibracja przy n≈60; value vs fair (czy „value” dojdzie do 20 i nadal nie odstaje — wtedy rozważyć uproszczenie etykiety); 1.45–1.60 i h2h vs totals under, gdy dojdą do 20; czy duplikaty zniknęły.

## 2026-09-27 — bez kursów poniżej 1.20, wynik po podatku (decyzja właściciela)
Findings: dotychczasowe „przewagi” i zysk liczone od kursu brutto. Po 12 % podatku od stawki (wygrana = 0.88 × kurs) 30 rozliczonych typów: brutto +0.98 u (ROI +3.3 %), **netto −2.74 u (ROI −9.1 %)**; value −0.71 u, fair −2.03 u netto. Próg rentowności po podatku = 1 / (0.88 × kurs): 1.20 → 94.7 %, 1.45 → 78.4 %.
Changes: zakres 1.10–1.19 usunięty (shortlist/ledger/SKILL/szablon/workflow); przy każdym typie „EV po podatku = p_est × kurs × 0.88 − 1”, raport mówi wprost, gdy jest ujemne; statystyki i strona pokazują zysk po podatku (push liczony konserwatywnie z utratą podatku). Klasy value/fair bez zmian (porównanie z rynkiem).
How we will know: kolumna „Po podatku” w statystykach; następny przegląd powinien ocenić, czy przy kursach ≤ 1.60 w ogóle da się wyjść na plus po podatku — jeśli nie, rozważyć wyższe zakresy kursów.

## 2026-09-27 — zakresy „okazji” 1.61–2.00 i 2.01–3.00 (decyzja właściciela)
Findings: po podatku 12 % krótkie kursy (≤ 1.60) wymagają przewagi 10–15 pkt nad rynkiem — nieosiągalnej przy naszym CLV ~1–2 %; przy wyższych kursach wymagana przewaga w pkt jest mniejsza (2.00 → +6.8 pkt).
Changes: dwa nowe zakresy „okazje”; shortlist szereguje je wg `edge_market` (najlepsza cena vs mediana uczciwej ceny z książek), nie wg prawdopodobieństwa; typ tylko gdy EV po podatku ≥ 0 (ledger to egzekwuje), inaczej papier; SKILL.md opisuje źródła prawdziwej przewagi (newsy niewycenione, spóźniona książka, DNB/+AH/under). Test na ranking i walidację.
How we will know: po ~20 typach „okazji” — wynik po podatku i CLV; jeśli ujemne, okazje to szum.

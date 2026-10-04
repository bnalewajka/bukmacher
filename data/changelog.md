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

## 2026-09-28 — warunek podatku usunięty (decyzja właściciela)
Changes: typy nie są już oceniane ani blokowane wg EV po podatku; w zakresach okazji 1.61–3.00 warunkiem jest klasa „z przewagą” (p_est ≥ implikowane + 0.03). Kolumna „po podatku” zostaje tylko w statystykach strony, informacyjnie.

## 2026-09-28 — model Elo dla tenisa (prośba właściciela)
Findings: `tennis_elo.py` (tennis-data.co.uk, 2019–2026, 35 847 meczów, Elo ogólne + nawierzchnia, K = 250/(n+5)^0.4). Test out-of-sample 2025–26, 7 890 meczów: rynek (zamknięcie; Pinnacle albo średnia) Brier 0.2036 / log-loss 0.5918, Elo 0.2175 / 0.6241; każda mieszanka gorsza od samego rynku (najlepsza 95/5 = 0.5921); przy rozbieżności ≥ 10 pkt (2 354 mecze) rynek 0.2235 vs Elo 0.263 Brier. Dane opóźnione 2–3 tygodnie (brak bieżącego tygodnia).
Changes: SKILL.md — Elo jako kontrola, nie źródło p_est; duża rozbieżność = szukać faktu (forma z bieżącego tygodnia, kwalifikacje, kontuzja). Test matematyki modelu.
How we will know: przegląd tygodniowy może przebudować model (`build`) i sprawdzić, czy dodanie formy z bieżącego tygodnia zmniejsza przewagę rynku; dopóki blend nie bije rynku w teście — Elo nie wpływa na p_est.

## 2026-09-28 — powrót do celu: „typ dnia” 1.20–1.30 (decyzja właściciela)
Findings: skill rozrósł się do 5 zakresów, okazji, klas i długich raportów, a właściciel od początku chciał 1–2 najbardziej prawdopodobnych zakładów dziennie po 1.20–1.30. Badanie ruchu kursów (`odds_movement.py`): przy kursie 1.20–1.30 faworyt wygrywa ~77–80 % niezależnie od wcześniejszego ruchu (piłka 46 k, tenis ATP 2 k meczów) — spadek kursu nie podnosi szansy; faworyt, którego kurs wzrósł > 10 %, wypada wyraźnie gorzej od swojego kursu.
Changes: domyślnie 1.20–1.30, horyzont do końca dnia, 1–2 typy wg p_est (≥ implikowane, minimum researchu); czerwona flaga: kurs faworyta +10 % od otwarcia → odpada (`betexplorer.py move`); inne zakresy i okazje tylko na prośbę; `shortlist.py --ranges daily` domyślnie; krótki raport (szablon); workflow prosi o typ dnia.
How we will know: trafność typów dnia vs p_est w kolejnym przeglądzie; reguła +10 % — czy odrzucone „czerwone flagi” (papier) przegrywają częściej.

## 2026-10-04 — weekly review
Sample: 57 typów (55 rozliczonych: 45–10, 2 zwroty), 84 papier (83 rozliczone: 63–20, 1 zwrot; bez powtórzeń 73: 55–18), CLV typów śr. +2.0% (84% dodatnich, n=38), trafność 81.8% vs p_est 78.2% (implikowane 76.0%), zysk +4.23 u (ROI +7.4%; po podatku −3.12 u), Brier 0.145. Od zmiany na „typ dnia” (od 2026-09-28_1616): 14 typów 12–2, p_est 0.80, implikowane 0.79, CLV +2.9% (n=8).
Findings:
- Kalibracja typów w normie: +3.6 pkt nad p_est przy n=55 to ~0.6 błędu standardowego; kubełki 0.75–0.80 (76.9%, n=13) i 0.80–0.85 (85.7%, n=21) zgodne. Papier 75.9% vs p_est 71.9% i implikowane 74.3% (bez powtórzeń 75.3% vs 73.6%) — odrzucone zakłady wygrywają mniej więcej po cenie rynku, czyli p_est na papierze jest lekko pesymistyczne, ale ~0.4 SE — progi bez zmian.
- Klasy: „z przewagą” 11–2 (trafność 0.85 vs p_est 0.78, CLV +2.4%, n=13 rozliczonych) vs „uczciwa cena” 34–8 (0.81 vs 0.78, CLV +1.8%, n=42). Kierunek jak trzeba, ale „value” nadal < 20 i od 2026-09-28 przybywa ich bardzo mało (typ dnia to prawie zawsze „fair”).
- Głębokość researchu: 1 przeczytane źródło 20–3 (CLV +2.7%, n=23), ≥ 2 przeczytane 17–5 (77% vs p_est 78%, CLV +1.3%, n=22), 0 przeczytanych 8–2. Głębszy research nie daje lepszych wyników — raczej świadczy o trudniejszych meczach. Porażki tygodnia: 2026-10-01_1744_typy#1 (Malta–Gibraltar 1:1, h2h; mecz bez stawki, głęboki blok rywala), 2026-10-03_0033_typy#1 (Rakhimova–Fernandez 2:1, trzy sety, bez sygnału), 2026-09-28_0835_typy#1 (Turcja–Włochy U3.5 1:4, kurs rósł od otwarcia). Żadna nie stała na błędnym fakcie; wymyślone przez wyszukiwarkę wyniki nierozegranych meczów (≥ 6 razy w lessons) zostały złapane przez pełne odczyty.
- Wycinki: piłka h2h 6–2 (n=8), piłka under 11–3 (n=14), tenis h2h 9–2 (n=11), koszykówka 7–1, hokej 6–1 — wszystkie < 20, bez zmian reguł rynkowych (np. „1X zamiast h2h dla małych reprezentacji” z lessons 2026-10-02_0054 — dopiero przy 20 typach piłki h2h).
- Kredyty The Odds API: przegląd 2026-09-24 ustalił budżet 4 na bieg, ale od 2026-09-29_2143 biegi rutynowo podnosiły go do 8–16 i dociągały klucze ręcznie (2026-10-01_2153, 10-02_0054, 10-02_1705, 10-02_2135, 10-03_1556, 10-03_2348). W październiku 500 → 335 w 3 dni (~55/dzień) — plan skończyłby się ok. 10 października i wszystkie biegi zostałyby bez cen. Przyczyną dociągania był też ranking kluczy (tenis ucinany przy budżecie 4).
- Błąd w `odds.py` (lessons 2026-10-03_1556): `market_norm` nie rozpoznawał kluczy The Odds API z podkreśleniem — `draw_no_bet` i `double_chance` lądowały w „other” (shortlist je odrzuca), a `team_totals` liczono jako sumę meczu (`totals`).
- CLV ma tylko 8 z 14 typów dnia (papier 3 z 16): typ dnia często startuje przed kolejnym biegiem, więc nikt nie zapisuje ceny zamknięcia (`last_seen`). Bez zmian (dodatkowe snapshoty kosztują kredyty), ale CLV w typie dnia jest na razie słabą miarą.
Changes:
- `scripts/odds.py` — `market_norm` zamienia „_” na spację przed dopasowaniem; test `test_oddsapi_underscore_market_keys`. Dlaczego: lessons 2026-10-03_1556 (DNB Chorwacja–Anglia znalezione tylko ręcznym obejściem). Jak poznamy: DNB/DC z The Odds API pojawiają się w shortliście bez obejść; źle, jeśli w lessons wróci „rynek w other”.
- `scripts/odds.py` + `SKILL.md` — `--credit-budget auto`: (kredyty pozostałe − 60 rezerwy) / (3.5 biegu × dni do końca miesiąca), max 16; odczyt z darmowego `/sports`. Na start miesiąca daje 4 (jak dotąd), przy nadwyżce pod koniec miesiąca więcej, przy przepaleniu mniej (dziś 2). SKILL.md zakazuje ręcznego dociągania kluczy ponad ten budżet. Test `test_credit_budget_auto`. Dlaczego: niezmiennik planu darmowego (self-review §3) łamany od 6 dni. Jak poznamy: w raportach do kolejnego przeglądu zużycie ≤ ~5 kredytów/bieg i pozostałe kredyty 1 listopada > 0; źle, jeśli raporty nadal piszą o ręcznym rozszerzeniu albo typy dnia znikają przez brak kluczy (wtedy zmienić ranking kluczy, nie budżet).
- Progi, zakres 1.20–1.30, klasy — bez zmian (brak sygnału ponad szum).
Next review: zużycie kredytów i ile biegów miało budżet < 4 (czy auto nie zagłodziło tenisa — wtedy ranking kluczy w `from_oddsapi`); kalibracja typów dnia przy n≈30 w nowym trybie; piłka h2h (małe reprezentacje, mecze bez stawki), gdy dojdzie do 20; pokrycie CLV.

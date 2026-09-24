# bukmacher

Skill dla Claude Code: **najbardziej prawdopodobny typ bukmacherski o zadanym kursie**
(domyślnie 1.20) wśród prawdziwych spotkań z najbliższych 4/8/12/24 godzin — piłka nożna,
siatkówka, koszykówka, hokej, tenis. Skill sam pyta o horyzont i kurs, weryfikuje zegar,
pobiera wydarzenia i kursy z prawdziwych źródeł, analizuje kandydatów (motywacja, forma,
absencje, składy, terminarz, sygnały rynkowe i inne) i oddaje raport z kilkoma propozycjami,
uzasadnieniem, plusami i ryzykami.

Skill leży w `.claude/skills/bukmacher/` i uruchamia się automatycznie, gdy poprosisz Claude
Code o typy / analizę bukmacherską, albo ręcznie: `/bukmacher`.

## Uruchomienie

```
claude
> Znajdź najpewniejszy typ na dziś, kurs ~1.20
```

Claude zapyta o okno czasowe (4/8/12/24 h) i kurs, potem wykona kroki z `SKILL.md`.
Raport trafia do `reports/<data>_typy.md` i do odpowiedzi.

## Źródła danych (co działa bez kluczy, co wymaga klucza)

| Dane | Bez klucza | Z kluczem (opcjonalnie) |
|---|---|---|
| Czas | nagłówki `Date:` kilku serwerów HTTPS (`scripts/clock.py`) | — |
| Wydarzenia | Sofascore API (wszystkie 5 sportów), ESPN API | api-sports.io (`APISPORTS_KEY`) |
| Kursy | Sofascore (partner-bukmacher, wszystkie rynki, kurs otwarcia → drift), ESPN BET | The Odds API (`ODDS_API_KEY`, Pinnacle + kilkanaście książek EU), api-sports (`APISPORTS_KEY`) |
| Kontekst | Sofascore (składy, absencje, forma, H2H, tabela, następny mecz), ESPN summary | — |
| Newsy | WebSearch / WebFetch (oficjalne źródła: kluby, NBA injury report, DailyFaceoff, ATP/WTA, PlusLiga…) | — |

Klucze (darmowe plany wystarczają):

```bash
export ODDS_API_KEY=...        # https://the-odds-api.com  (500 kredytów/mies.)
export APISPORTS_KEY=...       # https://api-sports.io     (100 zapytań/dzień na sport)
```

Szczegóły endpointów, limitów i fallbacków: `.claude/skills/bukmacher/references/sources.md`.

## Claude Code w chmurze (claude.ai/code)

Środowisko chmurowe ma politykę sieci; skrypty potrzebują dostępu do hostów:
`api.sofascore.com`, `site.api.espn.com`, `api.the-odds-api.com`, `*.api-sports.io`
oraz do stron z newsami (lub pełnego dostępu do sieci). Bez tego skill przechodzi na
fallbacki opisane w `references/sources.md` (WebFetch/WebSearch) i mówi o tym w raporcie.
Lokalnie nic nie trzeba konfigurować.

## Skrypty (Python 3.9+, tylko biblioteka standardowa)

```bash
cd .claude/skills/bukmacher
python3 scripts/clock.py                                        # zweryfikowany czas UTC
python3 scripts/fixtures.py --hours 4 --now <UTC> --out fixtures.json
python3 scripts/odds.py --fixtures fixtures.json --out odds.json
python3 scripts/shortlist.py odds.json --target 1.20 --out shortlist.json
python3 scripts/context.py --fixtures fixtures.json --key "<klucz z fixtures.json>"
```

Odpowiedzi są cache'owane 10 min w `~/.cache/bukmacher` (oszczędza limity API);
`BUKMACHER_NO_CACHE=1` wyłącza cache.

## Testy

```bash
python3 -m pytest -q tests      # albo: python3 tests/test_pipeline.py
```

Testy działają offline na syntetycznych odpowiedziach o kształcie prawdziwych API
(ESPN, Sofascore, The Odds API, api-sports) i sprawdzają okno czasowe, scalanie źródeł,
de-vig, wyprowadzanie podwójnej szansy z 1X2 i ranking shortlisty.

## Zastrzeżenie

Kurs 1.20 to ~83 % implikowanego prawdopodobieństwa — nawet najlepiej wybrany typ przegrywa
średnio raz na 6–7 razy. To narzędzie analityczne, nie gwarancja. Obstawiaj wyłącznie środki,
których utratę akceptujesz.

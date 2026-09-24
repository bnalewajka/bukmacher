# Report template (Polish, default). Keep the structure; fill every field.

```markdown
# Typy bukmacherskie — okno {okno} h, kurs docelowy {kurs} ({pasmo})

Wygenerowano: {data i godzina UTC} / {czas lokalny PL}. Zegar zweryfikowany: {tak/nie + źródło}.
Przeanalizowano: {N} spotkań ({piłka nożna X, siatkówka Y, koszykówka Z, hokej W, tenis V}),
{M} selekcji w paśmie kursów z {lista źródeł kursów}. Kursy pobrane o {godzina}; przed
postawieniem sprawdź je u bukmachera — mogą się zmienić.

## Ranking propozycji

| # | Godz. (PL) | Wydarzenie | Rozgrywki | Zakład | Kurs (bukmacher, źródło) | p_est | implikowane |
|---|---|---|---|---|---|---|---|
| 1 | 20:45 | Gospodarz – Gość | Liga | np. Podwójna szansa X2 | 1.20 (bet365 via Sofascore, 17:32 UTC) | 0.88 | 0.83 |

## 1. {Wydarzenie} — {Zakład} @ {kurs}

**Dlaczego ten typ, a nie inne:** {2–4 zdania: co przesądza; co odróżnia od innych kandydatów
w paśmie; dlaczego ten rynek, a nie zwykła wygrana}
**Analiza:**
- Motywacja i stawka: …
- Forma (z uwzględnieniem rywali): …
- Absencje i zastępstwa: …
- Składy (potwierdzone / przewidywane, godzina publikacji): …
- Terminarz, podróż, zmęczenie: …
- Miejsce, warunki, sędzia: …
- Styl gry / dopasowanie: …
- Sygnały rynkowe (drift, Pinnacle vs soft, liczba bukmacherów): …
- Inne istotne: …
**Plusy:** {lista}
**Ryzyka:** {lista, w tym reguły rozliczenia zakładu u bukmachera}
**Jak ten zakład przegrywa:** {jedno zdanie, realistyczny scenariusz}
**Źródła:** {linki / endpointy, godzina pobrania}

## 2. …

## Odrzuceni kandydaci (dlaczego nie)
- {Wydarzenie, rynek, kurs} — {powód: rotacja, kontuzja, brak potwierdzonego bramkarza, drift w górę, cienki rynek…}

## Uwagi
- Zakłady pojedyncze; nie łączyć w AKO bez wyraźnej prośby.
- Kursy 1.20 oznaczają ~83 % implikowanego prawdopodobieństwa — nawet dobrze wybrany typ
  przegrywa mniej więcej raz na sześć–siedem razy. Obstawiaj tylko środki, których utratę akceptujesz.
- Źródła, które zawiodły w tym uruchomieniu: {lista lub „brak”}.
```

Rules for filling it:
- Times in Polish local time with the UTC in brackets when it avoids ambiguity.
- `p_est` is your estimate after analysis; `implikowane` = 1/kurs. If `p_est` is below
  implied, the selection does not belong in the ranking.
- Do not pad: three strong proposals beat five weak ones. If nothing qualifies, say so and
  show the best rejected candidates with what would change your mind (e.g. confirmed goalie).
- English-language user → same structure in English.

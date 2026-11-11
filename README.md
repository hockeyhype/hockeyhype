# Hockeyhype

Tabeller, resultat och spelarstatistik för ungdomshockey i Stockholm, Uppland och Södermanland (U14–U18, pojkar och flickor), hämtat från [stats.swehockey.se](https://stats.swehockey.se).

Sidan är `index.html`. Datan ligger i `data/` och laddas av sidan när den öppnas:

- `data/index.json`: vilka säsonger och distrikt som finns, och när de uppdaterades
- `data/<säsong>/<distrikt>.json`: alla grupper (serier) i ett distrikt, t.ex. `data/2026-27/stockholm.json`

Distrikten i säsong 2026-27 är Stockholm, Uppland, Södermanland och Region Öst (U18-serierna, som spelas på regionnivå). Säsong 2025-26 innehåller bara Stockholm och uppdateras inte längre.

## Daglig uppdatering

GitHub Actions (`.github/workflows/daglig-uppdatering.yml`) kör två gånger om dagen:

- **Morgon:** 05:00 UTC, det vill säga 06:00 vintertid och 07:00 sommartid.
- **Kväll:** 22:00 svensk tid på vardagar och 20:00 på helger, året runt. Båda UTC-timmarna schemaläggs, och steget "Kontrollera tiden" släpper bara igenom den som motsvarar rätt svensk tid.

Varje körning:

1. `dagligen.py` hämtar alla serier i `serier.json` från swehockey. U14-serierna hämtar bara tabellen.
2. Varje serie kontrolleras mot förra körningen. Ser en serie trasig ut (kraschar, tom tabell, färre spelade matcher eller lag, färre än 80 % av spelarna) behålls förra körningens data för just den serien, och det skrivs en varning i loggen. Resten uppdateras som vanligt.
3. Datan sparas i `data/` och sidan publiceras på GitHub Pages.
4. Går mer än en fjärdedel av serierna inte att uppdatera avbryts körningen utan att något sparas. Den gamla sidan ligger kvar och GitHub skickar ett mejl om att körningen misslyckades.

Du kan också starta en körning för hand under **Actions → Daglig uppdatering → Run workflow**.

De statiska serie- och lagsidorna finns för sökmotorer. De visar bara tabeller och matcher, inga spelarnamn.

Sidan speglar swehockey. Spelare eller uppgifter som tas bort där försvinner också här vid nästa körning.

## Filer

| Fil | Innehåll |
|---|---|
| `index.html` | Sidan |
| `data/` | Datan per säsong och distrikt (skrivs av `dagligen.py`) |
| `serier.json` | Vilka serier som hämtas, per distrikt (skapas av `hitta_serier.py`) |
| `hitta_serier.py` | Letar upp alla ungdomsserier (U14–U16 pojkar och flickor) i distriktens menyer på swehockey |
| `swehockey.py` | Hämtar och tolkar sidor från stats.swehockey.se |
| `hockeydata.py` | Läser och skriver filerna i `data/` |
| `dagligen.py` | Kör hela uppdateringen med kontroller och sammanfattning |
| `favicon.svg` | Ikonen i webbläsarfliken |
| `bygg_sidor.py` | Bygger statiska sidor per serie (`/serie/<id>/`) och lag (`/lag/<namn>/`), översikten `/serier/`, `sitemap.xml` och `robots.txt` vid varje publicering |
| `om.html` | Om sidan och integritet |
| `og.png` | Bilden som visas när en länk delas, ritad från `verktyg/delningsbild.html` |
| `fonts/` | Oswald och Karla (SIL Open Font License), lokala kopior så att inget hämtas från Google |

Inga extra Python-bibliotek behövs.

## Källsidor per serie

| Data | Sida |
|---|---|
| Tabell | `/ScheduleAndResults/Standings/{id}` (bara totaltabellen) |
| Matcher | `/ScheduleAndResults/Schedule/{id}` |
| Spelare och målvakter | `/Teams/Info/PlayersByTeam/{id}` |
| Födelseår | `/Teams/Info/TeamRoster/{id}` |

## Lägga till serier, distrikt eller en ny säsong

Vilka serier som hämtas styrs av `serier.json`. Den skapas av:

```
python hitta_serier.py
```

Skriptet går igenom distriktens menyer på swehockey, plockar ut ungdomsligorna (cuper, träningsmatcher och yngre åldrar hoppas över) och listar säsongens alla grupper, inklusive DM- och kvalgrupper. Distrikten och U18-serierna på regionnivå står i början av `hitta_serier.py` (`DISTRIKT`, `REGIONSERIER`), liksom säsongen (`SASONG`).

Kör skriptet igen när nya grupper tillkommer under säsongen (t.ex. DM eller slutspel) och inför en ny säsong. En enskild serie kan också läggas till för hand i `serier.json`. Nästa körning av `dagligen.py` hämtar sedan datan.

`endast_tabell: true` (U14) betyder att bara tabellen hämtas.

## Dataformat

- `spelare`: `[namn, lag, pos, födelseår, GP, G, A, TP, PIM]`
- `malvakter`: `[namn, lag, födelseår, GPT, GKD, GPI, MIP, GA, SVS, SOG, SVS%, GAA, SO, W, L]`
- `tabell`: `[placering, lag, GP, W, T, L, målskillnad, poäng]`
- `matcher.spelade`: `[datum, hemma, borta, hemmamål, bortamål, arena]`, med den senaste först
- `matcher.kommande`: `["datum tid", hemma, borta, arena]`, med den närmaste först

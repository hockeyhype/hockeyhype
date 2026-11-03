# Hockeyhype

Tabeller, resultat och spelarstatistik för Stockholms ungdomshockey (U15, U16 och U18), hämtat från [stats.swehockey.se](https://stats.swehockey.se).

Hela sidan är en enda fil, `index.html`. Datan ligger inbäddad i den (`const RAW = {...}`).

## Daglig uppdatering

GitHub Actions (`.github/workflows/daglig-uppdatering.yml`) kör varje morgon klockan 05:00 UTC, det vill säga 06:00 vintertid och 07:00 sommartid:

1. `dagligen.py --sida index.html` hämtar alla serier under säsong 2026-27 och kontrollerar att inget ser trasigt ut. Följande stoppar körningen: färre spelade matcher än förut, färre än 80 % av spelarna eller färre lag i tabellen.
2. Om datan ser rimlig ut sparas `index.html` och sidan publiceras på GitHub Pages.
3. Om något ser fel ut avbryts körningen. Den gamla sidan ligger kvar och GitHub skickar ett mejl om att körningen misslyckades.

Du kan också starta en körning för hand under **Actions → Daglig uppdatering → Run workflow**.

Sidan speglar swehockey. Spelare eller uppgifter som tas bort där försvinner också här vid nästa körning.

## Filer

| Fil | Innehåll |
|---|---|
| `index.html` | Sidan, med datan inbäddad |
| `swehockey.py` | Hämtar och tolkar sidor från stats.swehockey.se |
| `uppdatera.py` | Byter ut en säsongs serier i sidan mot färsk data |
| `dagligen.py` | Kör hela uppdateringen med kontroller och sammanfattning |
| `favicon.svg` | Ikonen i webbläsarfliken |

Inga extra Python-bibliotek behövs.

## Källsidor per serie

| Data | Sida |
|---|---|
| Tabell | `/ScheduleAndResults/Standings/{id}` (bara totaltabellen) |
| Matcher | `/ScheduleAndResults/Schedule/{id}` |
| Spelare och målvakter | `/Teams/Info/PlayersByTeam/{id}` |
| Födelseår | `/Teams/Info/TeamRoster/{id}` |

## Lägga till en serie eller en ny säsong

Skriptet uppdaterar bara de serier som redan finns under säsongen i `index.html`. En ny serie läggs in som en ny rad i säsongens `grupper`, med id (numret i swehockey-adressen), namn och kategori. Därefter fyller nästa körning i resten.

## Dataformat

- `spelare`: `[namn, lag, pos, födelseår, GP, G, A, TP, PIM]`
- `malvakter`: `[namn, lag, födelseår, GPT, GKD, GPI, MIP, GA, SVS, SOG, SVS%, GAA, SO, W, L]`
- `tabell`: `[placering, lag, GP, W, T, L, målskillnad, poäng]`
- `matcher.spelade`: `[datum, hemma, borta, hemmamål, bortamål, arena]`, med den senaste först
- `matcher.kommande`: `["datum tid", hemma, borta, arena]`, med den närmaste först

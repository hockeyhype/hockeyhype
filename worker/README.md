# hockeyhype-live (Cloudflare Worker)

Visar ställningen i pågående matcher på hockeyhype.se, 1–3 minuter efter swehockey.

## Så fungerar det

1. `dagligen.py` skriver `data/live-kandidater.json`: dagens och de två närmaste dagarnas matcher.
2. Workern körs varannan minut (cron). Den väljer matcher från 90 minuter före nedsläpp till
   4 timmar efter. Matcher utan satt tid (00:00) bevakas hela dagen från kl 08.
3. Saknas swehockeys match-id läses seriens liveöversikt (`/StatPage/Live/<serie>/`, några kB). Den
   listar dagens matcher med id redan före nedsläpp (sett 45 minuter före). Står matchen inte där
   läses spelschemat i stället, var tionde minut, för matcher som borde ha börjat.
4. Matchsidan (`stats.swehockey.se/Game/Events/<id>`) ger ställning, perioder och status. Den läses
   från 5 minuter före nedsläpp.
5. Läget sparas i KV-nyckeln `live`, men bara när något ändrats (gratisplanen tillåter 1 000
   skrivningar per dygn).
6. När en match blir klar väcks GitHub-flödet (`repository_dispatch`, typ `matchklar`). Det läser om
   serien, så att resultat, tabell och poängliga uppdateras på vanligt sätt.
7. `GET hockeyhype.se/api/match/<id>` svarar med hela matchen: händelser, statistik och
   laguppställning, i samma format som `data/<säsong>/matcher/<id>.json`. Tolkningen i
   `src/matchdata.js` är en kopia av `matchdata.py` - ändra båda. Bara matcher i läget, cachat
   60 sekunder. Sidan använder den för matcher som inte är spelade än: laguppställningen före match
   och händelserna under match.
8. `GET hockeyhype.se/api/live` svarar med läget. Matcher med id men utan ställning är med, så att
   sidan vet vilket id den ska fråga efter. Sidan frågar varje minut, men bara när en match
   pågår och fliken syns.

Faller workern bort fungerar allt som förut: GitHub-flödets matchbevakning var 10:e minut ligger kvar.

## Installation (en gång)

```bash
cd worker
npx wrangler login                          # loggar in i Cloudflare via webbläsaren
npx wrangler kv namespace create LIVE       # skriv in id:t i wrangler.toml
npx wrangler secret put GITHUB_TOKEN        # GitHub-nyckel, se nedan
npx wrangler deploy
```

GitHub-nyckeln är en fine-grained personal access token. Den ska bara gälla repot
hockeyhype/hockeyhype och behöver bara behörigheten **Contents: Read and write**, som krävs för
`repository_dispatch`.

## Test och felsökning

```bash
node worker/test/test.mjs          # tolkningen av swehockeys sidor och en hel bevakningsrunda
npx wrangler tail                  # se workerns logg live (en rad per runda)
curl https://hockeyhype.se/api/live
```

Testfilerna i `test/fixtures/` är swehockey-sidor där spelarnamnen tagits bort.

## Gränser (Cloudflare gratisplan)

| | Gräns | Användning |
|---|---|---|
| Anrop till workern | 100 000/dygn | /api/live från besökare under pågående matcher |
| Cron | 5 per konto | 1 |
| Anrop till andra sajter per körning | 50 | Högst 40 (MAX_ANROP) |
| KV-skrivningar | 1 000/dygn | Högst 720 (en per runda, bara vid ändring) |
| Processortid | 10 ms per körning | Tolkningen av en sida tar några ms |

# Første defensive oddsvariant

`component_baseline_v1` forbliver standard. `component_defensive_odds_v1` bruger frekvensprior 1,0 og betinget minutprior 1,0. Kun holdets målproces for **clean sheets og fradrag for indkasserede mål** erstattes, når et komplet, tidsmæssigt gyldigt marked kan matches. Spilletid, egne mål/assists, den eksisterende offensive kampfaktor, bonus, redninger, defensive bidrag og øvrige hændelser bevares. Dette er ikke en fuldt oddsbaseret model.

## Kilde og rådata

Én ny kørsel blev hentet gennem de eksisterende adapters:

- Snapshot: `2026-09-27_104712135033Z_f5ca590694aa4e57ae515ce1a16362fa`.
- Odds: `raw/football_data_uk/attempt_02/fixtures.csv`, HTTP 200 / `text/csv`, 12.343 bytes. Første svar er den bevarede canonical-host-redirect.
- Hentet / available_at: `2026-09-27T10:47:12.662394+00:00`.
- SHA-256: `ead342693c9e68fb987d59db7478d871043317de79322bde81dc58e893324c8c`.
- Feed: `https://www.football-data.co.uk/fixtures.csv`, canonical redirect til host uden `www`.
- 41 CSV-rækker, **0 `E0`-rækker**. Ingen priser bruges fra andre ligaer.
- Kildens pris-publiceringstid er ukendt. Hentetid er hverken kickoff eller dokumentation for prisens alder.

Samme run opdaterede kun officiel bootstrap/fixtures-kontekst. Spillerhistorik, priser og statusfelter genbruges fra `2026-09-24_164002695814Z_4fee7b0047014ffba28b416e9b9928ce`; deres oprindelige tidspunkt fremgår i `input_sources.history`. Nye spillerhistorikker er ikke hentet. Team-ID/navne og spillerklub kontrolleres mod frisk bootstrap; ændret identitet/klub blokerer genbrug frem for at gætte en mapping. Pris/skadestatus kan stadig være forældet. Officielle deadlineændringer registreres som gamle/nye observationer.

## Kampmatching og tidszone

Kun eksakte officielle navne eller disse eksplicitte aliaser accepteres:

| Football-Data.co.uk | Officiel FPL | Evidens: FPL-kamp-ID |
|---|---|---:|
| Hull | Hull City | 33, Chelsea–Hull |
| Ipswich | Ipswich Town | 34, Crystal Palace–Ipswich |
| Tottenham | Spurs | 37, Tottenham–Everton |
| Coventry | Coventry City | 38, Coventry–Brighton |
| Man United | Man Utd | 39, Man United–Man City |

Alias og tid blev kontrolleret mod de to rå filer i det allerede godkendte Step 2A-snapshot `2026-09-13_154638516264Z_fe2dc3c782d146b2b6a22bdaafb905c5`. Alle **10/10** PL-rækker gav ét eksakt match, inklusive fem alias-kampe mod hold med identiske navne. Dette er særskilt kontrolleret identitetsevidens; de gamle priser bruges ikke som forecasts.

CSV-dato/tid fortolkes efter den dokumenterede operationelle politik `Europe/London` med DST. September-kontrollen gav de officielle UTC-tider præcist (fx 17:30 lokal = 16:30 UTC). Providerens [feltbeskrivelse](https://football-data.co.uk/notes.txt) specificerer ikke en tidszone: politikken er empirisk kontrolleret, ikke en garanti fra udbyderen. Hver ny række skal stadig matche eksakt på verificeret hjemme-/ude-ID og UTC-kickoff. Intet tolerancevindue, dagsmatch, nærmeste kamp eller fuzzy match. Ukendt navn, tom tid, DST-tvetydighed/ikke-eksisterende lokal tid, flere kandidater eller dublerede markedsrækker giver manglende dækning. Flyttet kickoff efter forberedelsen afvises også ved simulation.

## Fast markedspolitik og tilpasning

Kun **Bet365**: `B365H`, `B365D`, `B365A`, `B365>2.5`, `B365<2.5`. Det er samme bookmaker for begge komplette markeder; ingen `Max`, `Avg`, closing-fallback, asian handicap eller spillerodds. [Udbyderens kolonnenøgle](https://football-data.co.uk/notes.txt) beskriver disse felter som henholdsvis 1X2 og over/under 2,5. Manglende/ikke-endelige værdier eller decimalodds ≤1 afvises. Ukendte øvrige kolonner påvirker ikke dette valg.

For hvert marked separat: `q_i = (1 / odds_i) / sum_j(1 / odds_j)`. Den oprindelige sum minus én gemmes som margin. Det er proportional marginfjernelse, ikke evidens for sande sandsynligheder.

Tilpas `lambda_home, lambda_away > 0` med uafhængige Poisson-mål. 1X2 beregnes med Skellam-fordelingen for målforskellen, O/U med Poisson for summen. Solver: least squares med samme vægt for fem udfaldssandsynligheder, log-parametre, fast start 1,5/1,2, grænser 0,05–6,0 og maks. 200 funktionsevalueringer. De fem residualer er redundante inden for markederne; dette er den bevidste, faste vægtning. Alle fem markeds-/model-sandsynligheder, residualer, maksimal absolut afvigelse og priser gemmes.

Manglende konvergens, grænseløsning eller maksimal absolut afvigelse over **0,06** afvises. Grænsen er en operationel kontrakt, ikke en tunet eller statistisk kalibreret tærskel. Fallback er eksplicit pr. kamp. Ingen parameterjagt.

Clean-sheet-sandsynlighed for hjemmeholdet er `exp(-lambda_away)` og omvendt. Det gælder hele holdkampen; FPL-spillerpoint afhænger fortsat af minutter og mål i spillerens interval, inklusive eksisterende rødt-kort-regel.

## Tid og simulationsafgrænsning

Odds kræver `retrieved_at <= available_at <= forecast_origin_at` og **`available_at < officiel deadline`**. Publikationstid er `null`. Fremtidig officiel kontekst/historik afvises. `as_of_at` i den sammensatte prognose betyder informations-cutoff, mens originale retrieval-tider bevares separat; de tilbagedateres aldrig. Historisk simulation med odds-overlay er eksplicit forbudt. Sammenligningen kører ingen GW3–5-evaluering.

Baseline-RNG forbruges som før i begge varianter. Kun alternative indkasserede mål trækkes fra en separat stream, afledt af `[seed, fixture_id, 271828]`. Det bevarer spilletid og alle ikke-påvirkede pointkomponenter bit-identisk ved samme seed. Teammates deler fortsat modstanderens måltider. Defensive forskelle indeholder Monte Carlo-støj; denne første variant er ikke dokumenteret kalibreret. Uden brugbare odds bliver også pointscenarierne bit-identiske med baseline.

## Faktisk kørsel og tydeligt separat eksempel

Forecast-origin: `2026-09-27T10:55:00Z`, GW6-deadline: `2026-10-10T10:00:00Z`, 3.000 scenarier, seed 42, budget £100m. Samme spillerdata og konfiguration for begge modeller.

**Faktisk odds-dækning: 0/10 kampe**, alle med årsagen `no_premier_league_rows`. Alle spillerprognoser og holdvalg er uændrede. Intet resultat fortæller, om oddsvarianten er bedre.

Det separate `synthetic_offline_example_NOT_CURRENT_FORECAST` opstiller ét opdigtet Bet365-formateret marked på Arsenal–Leeds ud fra målrate 1,8/0,7 og 4 % margin. Fittet genfinder disse tal; maksimal sandsynlighedsafvigelse er under 1e-12. Baselinens holdmål var 1,1862/0,9821. Arsenal clean sheet: 37,45 % → 49,66 %; Leeds: 30,54 % → 16,53 %.

**Kun som syntetisk eksempel:** Traffords xP går fra 4,111 til 3,276, defensive point fra 1,672 til 0,837; minutter og offensive bidrag er uændrede. Dette er ikke aktuelle odds eller en aktuel ændret spillerprognose. Det syntetiske holdforslag ændres også; det vises separat i appen.

Rapporter gemmes eksklusivt under `artifacts/defensive_odds/` med begge modelversioner, konfiguration, seeds, raw checksums/kildestier, forecast/deadline, fit, spillerprognoser og hold. Filerne er gitignored; de er til senere udfaldsevaluering, som ikke implementeres her. Syntetiske rapporter må ikke indgå i en rigtig evaluering.

## The Odds API / William Hill (1. oktober 2026)

Denne kilde er nu et **separat kildevalg til samme** `component_defensive_odds_v1`.
Football-Data.co.uk/Bet365 er fortsat tilgængelig via `--odds-source football_data_uk`
(den eksisterende standard for sammenligningskommandoen). Den almindelige appmodel
forbliver `component_baseline_v1`; valg af en gemt oddsrapport ændrer ikke modellen.

API-politikken er fast `williamhill`: ét komplet `h2h`-marked med hjemme/uafgjort/ude
og ét `totals`-marked med både Over og Under på **præcis 2,5**, fra samme bookmaker.
Gyldige priser er endelige numeriske decimalodds >1. Ingen anden bookmaker, lay-pris
eller 3,5-linje erstatter et manglende marked. Dubletter, ugyldige priser, manglende
opdateringstidspunkter, fremtidige opdateringer, uafklaret matching og mislykket fit
registreres som eksplicit baseline-fallback pr. kamp.

API-navnealiaser: Leeds United→Leeds, Brighton and Hove Albion→Brighton,
Manchester United→Man Utd, Tottenham Hotspur→Spurs, Nottingham Forest→Nott'm Forest,
Manchester City→Man City, Newcastle United→Newcastle. Disse er angivet eksplicit i
`odds_api_markets.py` og blev kontrolleret i adgangsauditten mod 20 unikke officielle
kampe. API'ets timezone-aware `commence_time` skal matche det officielle UTC-kickoff
præcist sammen med hjemme-/udeidentitet. CSV-kildens London-tidspolitik bruges ikke
på API-tider.

De fem priser oversættes til hjemme/uafgjort/ude/over25/under25 og sendes til den
**eksisterende** marginfjernelse og Poisson-tilpasning uden ændrede grænser, vægte
eller startværdier. Rapporten gemmer priser, markeder, bookmaker, API-event-ID,
normaliserede sandsynligheder, målrater, residualer og kilde-/snapshotchecksums.

`bookmaker_last_update` og `market_last_updates` beholdes separat fra lokal
`retrieved_at`/`available_at`. Opdateringstid er ikke dokumenteret præcis prispublicering
og giver ikke bagudrettet lokal tilgængelighed. Lokal availability skal være senest
forecast-origin og strengt før deadline. Spillerhistorikkens/metadataenes og den
officielle kampkonteksts alder ved forecast gemmes separat under `input_sources`.

### Gennemført reel GW6-sammenligning

Ingen nye netværkskald. Genbrugte API-snapshot
`2026-10-01_135741394331Z_fc98daee5363459eb0d009bf198eb4be`, råfil
`raw/the_odds_api/soccer_epl/odds.json`, SHA-256
`4eb30850af3631fc22b47ee28e9bbfa91ec36014beacbfcb095276e3177d9e28`.
Hentet 1. oktober kl. 13:57:41 UTC. De oprindelige quotaheaders fra adgangstjekket
var 2 credits for kaldet / 498 tilbage; denne offline sammenligning bruger ingen credits.

Forecast-origin `2026-10-01T14:16:17.998435+00:00`, GW6, deadline 10. oktober kl.
10:00 UTC, 3.000 scenarier, seed 42, budget £100m, frekvens-/minutprior 1,0/1,0.
Historik/metadata fra 24. september: 165,5 timer gammel; officiel kamp-/deadlinekontekst
fra 27. september: 99,5 timer gammel. De genbrugte priser og skadesstatus kan være
forældede; ingen nye historikker eller officiel kontekst er hentet i denne opgave.

**10/10 anvendte kampe efter matching, tidskontrol og fit**, ingen fallback. Maksimal
absolut sandsynlighedsresidual pr. kamp: 0,0066–0,0279 (grænse 0,06).
Rapport: `artifacts/defensive_odds/20261001T141622183554Z_2dc7edff/comparison.json`.
Spilletid, ikke-defensive pointkomponenter og offensive kampantagelser verificeres
ved hver sammenligning; regressionstests kontrollerer også de ikke-defensive
pointarrays scenarie for scenarie. Den separate defensive RNG er uændret.

| Spiller | Baseline xP | William Hill xP | Forskel |
|---|---:|---:|---:|
| Trafford | 4,111 | 3,002 | −1,109 |
| Muharemović | 4,113 | 3,008 | −1,106 |
| Justin | 4,043 | 2,945 | −1,098 |
| Bogle | 4,256 | 3,199 | −1,057 |
| Meunier | 2,146 | 3,167 | +1,021 |

Alle forskelle kommer fra clean sheets/fradrag for indkasserede mål. Trup ind:
Raya, Calafiori, Saka, Isak; trup ud: Schade, Thomas, Haaland, Lammens.
XI ind: Raya, Calafiori, Saka, Isak; XI ud: Schade, Davis, Haaland, Tzolakis.
Anfører er fortsat Groß. Det er ændrede prognoser/optimeringsvalg og ikke dokumentation
for bedre præcision. Holdfordelingerne i rapporten evaluerer hver variant i dens egen
model; de er ikke en performance-rangering på observerede resultater.

### Fremtidig eksplicit hentning

`python scripts/fetch_odds_api.py` læser kun `ODDS_API_KEY` fra lokal `.env` (uden
shell-eksekvering/interpolation), og ændrer ikke filen. Ét EPL-kald med `h2h,totals`,
`uk`, decimal/ISO, connect/read-timeout 10/40 sekunder. Ingen automatiske retries
eller redirects; fejl bevares i snapshotkontrakten, og CLI returnerer nonzero.
Svarbytes skrives før validering. Hvis en fejlrespons mod forventning ekkoer nøglen,
redigeres netop hemmeligheden ud, svaret mærkes afvist, og redigeringen registreres.
Request-URL uden query og kun allowlistede offentlige parametre/kvoteheaders gemmes.
Transportlogging er slået fra under requesten; ingen exceptions med nøgle-URL udskrives.
CLI viser `last`, `used`, `remaining` fra headers; manglende headers bliver ikke nul.

Kommandoen er kun testet offline med mock-svar i denne integration. Appen og
sammenligningskommandoen kalder den aldrig automatisk. Ingen nye API-credits brugt.

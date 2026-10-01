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

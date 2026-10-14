# Dødboldsroller: afgrænset følsomhedsvariant

`component_set_piece_sensitivity_v1` er valgfri. Baseline, angrebsoddsmodellen og begge tidligere minutmodeller er bevaret. Denne variant ændrer kun mål-/assistfordelingen i den eksisterende angrebsoddsmodel. Den kombineres ikke automatisk med en ny minutmodel eller fælles målsimulation.

## Hvad vi faktisk har

Det officielle bootstrap fra 12. oktober kl. 05:15:41 UTC indeholder 61 spillere med `penalties_order`, 62 med `direct_freekicks_order` og 88 med `corners_and_indirect_freekicks_order`. Alle 20 hold har en entydig førsteprioritet i hver kategori. [FPL beskriver listerne som en orden for dødboldstagere](https://www.premierleague.com/en/news/973755); orden er ikke en kalibreret sandsynlighed. Ukendt/null betyder ikke nul chance eller bekræftet fravær af en rolle.

De indlæste officielle spillerhistorikker giver samlet xG/xA, men ikke non-penalty xG eller særskilt dødbolds-xA. Vi kan derfor **ikke dokumenteret fjerne det historiske straffesparksbidrag og erstatte det med et nyt**. Implementeringen er en eksplicit følsomhedsomfordeling inden for uændrede holdbudgetter, ikke en identificeret model for straffespark, frisparksmål eller hjørneassists. Det mekaniske tillæg af ekstra straffesparksmål undgås; ukendt historisk overlap er fortsat en modelbegrænsning.

## Beregning

Den eksisterende angrebsoddsmodel giver hvert hold et målbudget og et assistbudget. Begge bevares. Lad `b_i` være spillerens eksisterende andel og `e_i` dens forventede minutter / 90. For en dokumenteret rolleorden er den antagne rollevægt:

```
r_i = e_i * produkt(1 - e_j for højere prioriterede spillere j)
c = sum(r_i)
ny andel_i = (1 - w*c) * b_i + w*r_i
```

Dette er en tilnærmelse til, hvem der er på banen på et tilfældigt tidspunkt. Den antager uafhængig spilletid og prioritetsrækkefølge. Den modellerer ikke en fælles virkelig startellever, spillernes samtidige ind-/udskiftninger eller delte højre/venstre hjørner. Resten `1-c`, hvor ingen dokumenteret tager forventes til stede, beholder den hidtidige fordeling. Skadesfaktor indgår allerede i eksponeringen og ganges ikke på igen.

Mål kan omfordeles gennem straffesparks- og direkte frisparksrollen; assists gennem hjørne-/indirekte frisparksrollen. Standardscenariet bruger budgetandele 10%, 2%, 15%, alle dæmpet med rollevægt 50%: effektive vægte 5%, 1%, 7,5% før eksponering. **Alle fire tal er konfigurerbare antagelser, ikke estimerede ligafrekvenser eller statistisk sikkerhed.** Ingen parameterjagt er foretaget. Vægt 0 giver den eksisterende angrebsoddsmodel præcist.

Den resterende historiske andel må ikke kaldes non-penalty/open-play xG. Straffesparksmisbrug, målmandsredninger af straffespark, bonus og øvrige pointkomponenter er uændrede og modelleres ikke som sammenhængende straffesparkshændelser. Dødboldstagere får ikke garanteret spilletid. Modellen afleder heller ikke sandsynligheder fra nyhedstekst.

## Fallback og tid

- Manglende, ugyldig, dubleret eller ufuldstændig rolleorden → eksplicit `unknown`/`conflicted`; den pågældende kategori bevarer den eksisterende fordeling.
- Spillere, som ikke forventes at spille, får ingen rolleallokering. En sekundær tager kan få andel, når førstevalg ikke forventes på banen.
- Manglende/afviste odds → eksisterende baseline-fallback. Rolledata skaber ikke fiktive markedsmål.
- Rolledata indlæses fra checksum-verificeret bootstrap. Snapshot-ID, råsti, SHA-256, retrieved_at og available_at bevares. Publikationstiden står ukendt.
- Spiller-/hold-ID'er skal stemme nøjagtigt. Dubletter eller ændret klub afvises; ingen navnegæt.
- Både rolleobservation og odds skal ligge senest ved forecast og før deadline. Dødboldsvarianten er forbudt i retrospektiv evaluering. Nutidige rolleordener bruges ikke på GW3–5.
- Roller videreføres som scenarie gennem en valgt horisont; fremtidige rolleændringer er ukendte. Spillerhistorik/priser og nyere rollekontekst har separate tidspunkter.

## Brug

App: **Mit hold → Prognosemodel → Eksperiment · dødboldsroller og odds**. Vælg et gemt officielt snapshot til roller samt et gemt William Hill-odds-snapshot. Antagelserne kan ændres og gemmes i forecastcachen/transferforslaget. Nye beregninger sker kun ved eksplicit klik. Ingen downloads ved appstart.

**Analyse og eksperimenter → Dødboldsroller · gemt følsomhedssammenligning** viser oprindelige tidspunkter, dækning, spillerændringer, holdbudgetter og individuelle allokeringer.

Offline-kommando:

```bash
.venv/bin/python scripts/compare_set_pieces.py \
  --snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --context-snapshot data/raw/2026-10-12_051541027780Z_e7171f9555904b94908001be74937c16 \
  --odds-snapshot data/raw/2026-10-09_044610511257Z_bb08becd841f43c0ab0aa492560237b9 \
  --draws 3000 --seed 42
```

Kommandoen vælger næste fremtidige officielle deadline. Kørslens baseline, angrebsoddsreference og dødboldsscenarie bruger identiske spillerdata, minutter, seed og antal scenarier. Forecasts, scenario-arrays, konfiguration, kildehash og forklaringer gemmes i en ny mappe under `artifacts/set_piece_forecasts/`. Den eksisterende `scripts/evaluate_saved_forecast.py` kan senere evaluere de gemte arrays mod endelige udfald. Konkludér ikke forbedret præcision ud fra xP-forskelle.

## Gennemført kørsel

13. oktober 2026 kl. 05:12 UTC: GW7, deadline 17. oktober kl. 10:00 UTC, 3.000 scenarier, seed 42. Spillere/priser/historik er fra 9. oktober kl. 04:51 UTC; odds fra 9. oktober kl. 04:46 UTC; officiel kampkontekst og roller fra 12. oktober kl. 05:15 UTC. **Dette er genbrugte data, ikke friske odds eller opdaterede priser.** Ingen downloads blev foretaget.

10/10 kampe med anvendelige odds. 20/20 hold med brugbare ordener i alle tre kategorier. Kørslens budget- og komponentkontroller bestod. De største ændringer mod angrebsoddsreferencen:

| Spiller | Uden rolleomfordeling | Med scenarie | Forskel |
|---|---:|---:|---:|
| Groß | 5,03 | 5,66 | +0,63 |
| Tavernier | 5,44 | 6,00 | +0,56 |
| Szoboszlai | 3,86 | 4,40 | +0,54 |
| B. Fernandes | 4,39 | 4,85 | +0,46 |
| Saka | 5,74 | 6,09 | +0,35 |

Andre spillere afgiver andel, fx King −0,12, Rayan −0,11 og Anthony −0,10 xP. Ændringerne indeholder også simulationsstøj. Rolleantagelsen er ikke en ny observation af spillernes styrke.

Rapport: `artifacts/set_piece_forecasts/20261013T051258398037Z_a71d2f55/`. Baseline forbliver standard. For en egentlig straffesparks-/dødboldsmodel mangler verificerede historiske hændelsestyper og npxG/xA-opdeling; dette trin udfylder ikke de manglende data med gæt.

# Implementeringsplan: probabilistisk FPL-model på gratis data

Dato: 2026-09-13. Status: repositorygennemgang og plan; ingen modelkode ændret.

## 1. Mål og afgrænsning

Det primære produkt er `P(FPL-point = k)` for hver FPL-spiller i hver kommende Gameweek, betinget på information tilgængelig ved forecastets cutoff. Expected points, varians, kvantiler og sandsynligheder for bestemte udfald afledes af denne fordeling. En sum af forventede pointkomponenter er ikke tilstrækkelig.

Arbejdsgangen skal være:

```text
Gratis kilder -> immutable rå snapshots -> normaliserede observationer
             -> canonical player-match data -> features ved cutoff
             -> probabilistiske forecasts -> forecast-evaluering
                                         -> senere, separat FPL-optimering
```

Start med lokale JSON/CSV-filer, Parquet, pandas, små funktioner og pytest. Ingen database, feature store eller generel workflowplatform er nødvendig. Udvid først modellen, når datagrundlag og tidsregler er testet. Optimering må kun læse publicerede forecastartefakter; den må ikke indgå i træning eller definition af forecastkvalitet.

## 2. Gennemgang af det eksisterende repository

Alle 31 eksisterende filer er gennemgået, herunder 24 Python-filer, dokumentation, konfiguration og tomme `.gitkeep`-filer. Mappen har ingen `.git`, ingen `AGENTS.md`, ingen tests og ingen indsamlede data eller trænede modeller. Versionshistorik og faktisk kildedækning kan derfor ikke vurderes lokalt. Fetch-scriptet er ikke kørt som del af gennemgangen.

### Datakilder, der allerede har adapterkode

| Kilde / fil under `src/fpl_model/data_sources/` | Implementeret adfærd | Mangler eller begrænsninger |
| --- | --- | --- |
| Officiel FPL API — `fpl_api.py` | Henter `bootstrap-static/` og `fixtures/` med timeout og HTTP-statuskontrol. Gemmer genserialiseret JSON. | Ingen spillerhistorik pr. fixture, ingen event/live-adapter, ingen schema- eller dækningskontrol. Originale response-bytes og metadata bevares ikke. |
| FPL Core Insights — `fpl_core.py` | Læser `players.csv`, `teams.csv`, `playerstats.csv`, `gameweek_summaries.csv` fra `main/data/2026-2027`; skriver Parquet. | Ingen `matches`/`playermatchstats`/turneringsmapper. Flydende `main`, hardkodet sæson, ingen commitreference. Alle læsefejl bliver til print og fortsættelse. |
| Football-Data.co.uk — `football_data_uk.py` | Læser upcoming `fixtures.csv` direkte med pandas og skriver Parquet. | Ingen original CSV, requestmetadata, eksplicit HTTP-timeout/retry, PL-filter, fixturemapping eller observationstid for odds. Ingen historisk adapter. |
| football-data.org — `football_data_org.py` | Henter v4 competition matches som JSON. Scriptet anmoder om `PL` og `CL`. Token læses fra miljø/`.env`; manglende token giver skip. | Ingen eksplicit sæson/datoafgrænsning, dækningskontrol eller player-minutes-parser. HTTP-fejl med et konfigureret token stopper hele scriptet, selv om kilden beskrives som optional. Gratis adgang til nødvendige felter skal verificeres. |
| ClubElo — `clubelo.py` | Henter dagsrating og rating præcis 21 dage tidligere. Tilføjer klubber, som mangler i dagens svar; skriver samlet Parquet. | Bruger maskinens lokale `date.today()`. Ingen eksplicit historisk as-of-dato, original CSV eller provenance for hver fallback-række. Det er to opslag, ikke en søgning gennem 21 dage. |

Adapterkode er ikke det samme som verificeret drift: der findes ingen lokale payloads, som dokumenterer, at alle endpoints og felter fungerer med den aktuelle kode.

FPL Cores dokumentation beskriver `playerstats.csv` som sæsonaggregater og `By Gameweek` som snapshots ved afslutningen af en Gameweek. Den beskriver også `matches` og `playermatchstats`, som vores adapter endnu ikke henter. Dokumentationens omtale af enkelte deadlinefelter er ikke dokumentation for hele filens tilgængelighed før deadline. Disse tidsforskelle skal afklares med konkrete payloads og versionshistorik. Kilde: [FPL Core Insights README](https://github.com/olbauday/FPL-Core-Insights), læst 2026-09-13.

### Øvrig kode og dokumentation

| Filer | Vurdering |
| --- | --- |
| `io.py` | `snapshot_dir()` opretter en UTC-mappe med sekundopløsning og `exist_ok=False`. God begyndelse; samme sekund giver kollision. Underliggende writers kan overskrive filer i en eksisterende undermappe. Intet manifest, checksum eller færdigmarkering. |
| `config.py` | Stier peger korrekt på projektroden i det aktuelle checkout. Kildesæson er hardkodet; datarod og kørselsdato kan ikke konfigureres. Installation uden for checkout bør senere testes. |
| `scripts/fetch_snapshot.py` | Sekventiel orchestration med forskellige fejlpolitikker. Ingen samlet status for complete/partial/failed, ingen inputparametre og ingen coverage-rapport. En succesbesked kan dække over manglende Core-filer. |
| `features/build.py` | Implementerer spillergrupperede, forskudte rolling means over 3/5/10 rækker. Manglende kolonner ignoreres. Ingen sæsonnøgle, schema, kildeversion eller deadlinefilter. |
| `features/workload.py`, `features/role.py` | Returnerer input uændret; kommentarer beskriver forslag. |
| `models/expected_points.py` | `XPComponents` summerer floats. Ingen fordelinger, scoringmotor eller modellering af afhængighed. Egenmål og straffesparksevents har ikke særskilte komponenter. |
| `models/minutes.py`, `attack.py`, `team_goals.py`, `defcon.py` | Kun kommentarer og modelidéer; ingen fit/predict/simulation. DefCon-regler i kommentarer er ikke validerede sæsonregler. |
| `backtest/walk_forward.py`, `optimizer/squad.py` | Kun skitser. Backtestskitsen blander forecast- og beslutningsmålinger; de bør få separate evalueringer. |
| `README.md`, `notes/edge_candidates.md` | Nyttig retning og hypoteser. Workload, rolle, vejr, dommere, prisdynamik og lignende er ikke implementerede datakilder/features. README-lagdelingen skal præciseres omkring forecastfordelinger. |
| `pyproject.toml` | Python >=3.11 og dependencies med nedre versionsgrænser. pytest/ruff er deklareret, men ingen tests, lockfil, eksplicit build-system eller CI-konfiguration. Flere tunge model-/solverdependencies er endnu ubrugte. |
| `.env.example`, `__init__.py`, `.gitkeep` | Tokeneksempel, versionsstreng, tomme pakkemarkører og tomme data-/modelmapper. Ingen `.gitignore` til fremtidig versionsstyring. |

### Højeste prioriteter fra reviewet

1. **Manglende tidsprovenance:** mappens oprettelsestid beviser ikke, at sidste API-svar var modtaget før deadline. En fetch kan krydse deadline.
2. **Utilstrækkeligt rålag:** flere adaptere parser/transformerer før lagring; rå CSV'er og ClubElo-fallbackens separate svar går tabt.
3. **Forkert mulig datagranularitet:** sæson-/GW-aggregater kan ikke bruges som player-match-observationer eller fordeles på to kampe uden yderligere dokumentation.
4. **`shift(1)` er utilstrækkelig:** en spillers første kamp i en Double Gameweek kan lække ind i forecastet for den anden, selv om begge forecasts skal fryses ved samme deadline. Senere rettelser af ældre kampe er et andet hul.
5. **Ingen canonical identiteter, labels eller tests:** nye modeller nu ville bygge på uafklarede joins og tidsantagelser.

## 3. Tidskontrakt og immutable snapshots

### Én eksplicit tidsregel

Alle timestamps er timezone-aware UTC. Hver forecastkørsel har `forecast_origin_at` (informationscutoff), `created_at` (faktisk beregningstid), mål-GW og den kendte deadlineversion. For nærmeste GW gælder `forecast_origin_at <= deadline_at`; alle input skal have `available_at < forecast_origin_at`. Et svar modtaget præcis ved cutoff er udelukket.

Ved forecasts flere GWs frem gælder den oprindelige kørsels cutoff for alle horisonter. Man må ikke bruge den fremtidige mål-GW's senere deadline som inputfilter.

Skeln mellem:

| Felt | Betydning |
| --- | --- |
| `event_time` / `kickoff_at` | Hvornår kampen/handlingen fandt sted eller er planlagt. Beviser ikke tilgængelighed. |
| `source_published_at` | Kildens dokumenterede publiceringstid, nullable; må ikke udledes alene af kampdato eller filnavn. |
| `request_started_at`, `retrieved_at` | Lokal start og tidspunktet, hvor hele svaret er modtaget. |
| `available_at` | Tidligste dokumenterede tidspunkt, hvor netop denne dataversion kan anvendes. Standard: `retrieved_at`. |
| `availability_basis`, `evidence_ref` | Lokal observation eller særskilt auditeret historisk publiceringsbevis. |
| `valid_from`, `valid_to` | Eventuel gyldighedsperiode for fx klubtilhørsforhold; adskilt fra observationstid. |

For gennemførte kampstats kræves både, at kampen er afsluttet, og at den anvendte statistikversion var tilgængelig før cutoff. Fremtidige, kendte fixtures må gerne bruges som kalenderfeatures. Afledte felter arver seneste tilgængelighedstid fra alle input, også mappings.

### Lagring

Foreslået struktur, indført gradvist:

```text
data/raw/<utc_timestamp_with_microseconds>_<run_id>/
    manifest.json
    fpl_api/bootstrap_static.json
    fpl_api/fixtures.json
    fpl_api/element_summary/<player_id>.json   # senere udvidelse
    fpl_core/<commit_sha>/<original_file>.csv
    football_data_uk/fixtures.csv
    football_data_org/PL_matches.json
    clubelo/<rating_date>.csv
data/processed/<dataset_id>/...
artifacts/forecasts/<run_id>/...
artifacts/backtests/<backtest_id>/...
```

- Gem uændrede response-body-bytes før parsing. Normalisering og sammenlægning foregår i processed-laget.
- Manifestet registrerer hvert request/fils URL og parametre uden secrets, HTTP-status, tidsfelter, content type, SHA-256, størrelse, kildeversion/commit, parserversion og fejl-/skipstatus. API-tokens og authheaders logges aldrig.
- Hent alle Core-filer fra samme eksplicitte commit; registrér stadig den faktiske lokale hentetid. En commitdato alene er ikke sikkert bevis på offentlig tilgængelighed dengang.
- Skriv til staging og publicér en færdig snapshotmappe uden overskrivning. Afbrudte kørsler kan diagnosticeres, men må ikke vælges som komplette datasæt. Finaliserede råfiler og manifest ændres aldrig; retry/rettelse giver et nyt run.
- Gør nødvendige og valgfrie kilder eksplicitte. Første baseline skal kunne fungere med FPL alene. Manglende optional data får status og dokumenteret fallback; manglende required data gør kørslen ugyldig.
- Ét samlet run-timestamp erstatter ikke tidskontrol pr. fil. En historisk as-of-selector vælger kompatible, validerede observationer og kontrollerer alle afhængigheder mod cutoff.
- Gem ClubElo-datoer separat; eventuel fallback får `rating_date`, alder, fallbackflag og reference til det konkrete svar. Ingen fallback fra en senere dato. Ingen skjult backfill i rålaget.
- Indsaml ved et konfigureret tidspunkt med margin før den officielle deadline og efter kampe til labels. Daglige snapshots kan supplere. Planen opretter ingen scheduler nu.

### Historiske data: hvad kan vi faktisk backteste?

Et historisk datasæt hentet i dag bliver ikke automatisk til et historisk pre-deadline-snapshot. Vi starter en coverage-tabel pr. sæson/GW med deadlines, spillerunivers, fixtures, labels og tilgængelighedsbevis for hver nødvendig kilde.

Godkendte backtestinput er enten egne snapshots modtaget før cutoff eller historiske versioner med auditerbart bevis for publicering før cutoff. Ved historisk import bevares dagens `retrieved_at`; et tidligere `available_at` kræver særskilt bevis og eksplicit godkendt importpolitik. Usikre/reviderede historiske data kan bruges til udforskning, men holdes ude af den leakage-sikre hovedrapport.

Hvis dækningen ikke rækker, rapporteres backtesten som ikke mulig for de pågældende GWs. Start fremadrettet arkivering og saml nok observationer; opfind ikke historiske odds, skadestatusser eller deadlines. En planlagt publiceringstid eller mappenavnet `GWx` er utilstrækkeligt bevis.

## 4. Schemas vi skal indføre

Brug versionerede kontrakter med eksplicitte kolonnenavne, pandas/Arrow-typer, nøgler, nullability og enheder. Første implementation kan være små valideringsfunktioner og dataclasses; intet nyt valideringsframework kræves.

Fælles: `season` er fx `2026-2027`; kilde-ID'er opbevares uden tab som strings; point/counts er integers; `price_tenths` er integer; xG/xA er floats; ukendt er null, aldrig implicit 0. Normaliserede observationer har `schema_version`, `snapshot_id`, `source`, `source_record_id`, `available_at` og provenance til råfilen. Forskellige feltkilder i samme række skal kunne spores separat.

| Tabel / artefakt | Rækkeniveau og nøgle | Minimumsindhold |
| --- | --- | --- |
| `snapshot_manifest` | Ét run samt én entry pr. request/fil | Tider, hash, path, kildeversion, status, required/optional og availability-bevis som beskrevet ovenfor. |
| `gameweek_observations` | `(season, gw_id, snapshot_id)` | `deadline_at`, eventstatus. Bevar deadlineversioner. |
| `player_observations` | `(season, fpl_player_id, snapshot_id)` | Navn, nullable `player_code`, `team_id`, FPL-position, status/news, chancer for spil, `price_tenths`, registreringsstatus. Historisk klub/position hentes as-of. |
| `team_observations` | `(season, fpl_team_id, snapshot_id)` | Navn, kortnavn, nullable team code. Separate canonical team-ID'er gør ikke-PL-hold mulige. |
| `entity_map` | `(source, entity_type, season, source_id, mapping_version)` | Canonical player/team/match-ID, validity, availability, mappingmetode, dokumentation og reviewstatus. FPL-ID'er antages ikke stabile mellem sæsoner. |
| `fixture_observations` | `(season, canonical_match_id, snapshot_id)` | Source fixture-ID, nullable FPL fixture-ID/GW, competition, hjemme-/udehold, kickoff, status. Resultater må være nullable; senere GW-/kickoffrettelser bliver nye observationer. |
| `player_match_observations` | `(season, canonical_player_id, canonical_match_id, source, snapshot_id)` | Klub/opponent, minutter, nullable startflag, mål, assists, xG/xA, relevante defensive counts, saves, cards, straffespark, egenmål, BPS/bonus og officielle point, når tilgængelige. Dæknings- og finalitetsflag. |
| `canonical_player_match` | I et valgt dataset: `(season, canonical_player_id, canonical_match_id)` | Deterministisk sammenflettede observationer, historisk klub/position, competition/FPL fixture-ID, målt kampstatus, feltprovenance, `observation_status` og dataset-cutoff. Versioneringen ligger i inputobservationer og `dataset_id`. |
| `player_gw_outcomes` | `(season, fpl_player_id, gw_id, label_version)` | Officielle realiserede point/minutter, faktisk scorende fixtureliste, finalitetsstatus, `available_at` og label-snapshot. Holdes adskilt fra forecastinput. |
| `odds_observations` (senere) | `(source, match_id, market, selection, bookmaker, snapshot_id)` | Decimalodds, observationstid, nullable kildetid og overround/marginmetode i afledt lag. |
| `team_rating_observations` (senere) | `(source, team_id, rating_date, snapshot_id)` | Elo, availability og fallbackalder. |
| `player_fixture_features` | `(feature_run_id, season, player_id, match_id)` | Origin/cutoff, mål-GW, snapshot-/mappingreferencer, features, missingness og historikstørrelse. Ingen targetkolonner. |
| `forecast_run` + `player_gw_pmf` | Runmetadata; PMF-række `(run_id, season, player_id, target_gw, points)` | Sandsynlighed, origin, kendt fixtureliste, model-/regelversion, input-/træningsreferencer, seed og horisont. Separat summary med mean/varians/kvantiler og P(0 minutter). |
| `scenario_points` (senere) | `(run_id, scenario_id, player_id, target_gw)` | FPL-point og minutter i fælles scenarier. Samme scenario-ID bevarer afhængighed mellem spillere og kampe. |
| `dataset_manifest` / `backtest_run` | Ét dataset/evalueringsrun | Inputhashes, schema-/feature-/regelversion, kodehash eller Git-SHA, dependency-lock, konfiguration, cutoffs/folds, labelpolitik, metrics og eksklusionsårsager. |

Ingen universel `latest`-join. Normalisering bevarer alle versioner; `build_as_of(cutoff, snapshot_selection)` vælger deterministisk én tilladt version pr. observation. Flere observationer af den samme kamp må ikke tælles som flere kampe.

## 5. Opbygning af canonical player-match-datasættet

1. **Fastlæg source contracts på små rigtige snapshots.** Kortlæg faktiske navne, ID-relationer, granularitet, enheder og nullværdier. Bevar små offline testpayloads. Fremtidige adaptere til FPL `element-summary/{id}/` og event/live skal verificeres for fixturebaserede labels; start med den enkleste verificerede vej, og tilføj kun den anden ved et dokumenteret hul.
2. **Udvid Core-ingestion målrettet.** Hent fixtures/matches og playermatchstats fra de relevante mapper på en fast commit. Registrér overlap mellem GW- og turneringsmapper; dedupliker på kilde-ID'er. Sæson- og GW-aggregater bruges til reconciliation, ikke som opfundne kampobservationer.
3. **Normaliser entiteter og mappings.** Brug `(season, fpl_player_id)` som FPL-anker. Kontrollér Core-ID'ers betydning mod faktiske data. Eksterne holdnavne matches via en lille eksplicit mappingtabel. Fuzzy navnematch må foreslå kandidater, men ikke automatisk godkende joins. Uafklarede joins kommer i en rapport.
4. **Byg fixture-rygraden.** Officiel FPL fixture-ID er ankeret for PL/FPL; andre turneringer får egne canonical match-ID'er og nullable FPL-GW. Koble kilder via verificerede ID'er eller entydige hold/competition/tid-match med rapportering af tvetydighed. En kickoffændring må ikke skabe en ny canonical kamp.
5. **Bevar historisk spillerunivers.** Match spilleren med det hold og den registrering, som var kendt på tidspunktet. Medtag spillere, der senere er solgt/fjernet, og håndtér oprykning, nye spillere og sæsonskift uden ID-kollision. Undgå survivorship bias fra dagens spillerliste.
6. **Bevar ikke-spil og manglende data som forskellige tilstande.** Udvid PL-rækker med det relevante registrerede spillerunivers, når kildedækning dokumenterer det. En manglende playerstats-række er ikke bevis på 0 minutter. Brug fx `observed`, `confirmed_dnp`, `unknown`; ukendte labels udelukkes med rapportering. Startstatus må ikke udledes alene af `start_min == 0`. En spiller med 0 minutter får ikke automatisk alle scoringfelter sat til 0.
7. **Sammenflet med feltvis prioritet.** Officielle FPL-point, FPL-assists og FPL-scoringkomponenter er labelgrundlag. Core bruges til verificerede ekstra kampstats og eventuelt andre turneringers minutter. Forskellige xG-leverandører holdes adskilt, indtil en ensartet featuredefinition vælges. Konflikter og kildeskift logges; ingen vilkårlig overskrivning.
8. **Adskil workloads fra FPL-labels.** Europa/pokaler kan bidrage til minutter og hvile, men aldrig til FPL-point. En holdkalender fra football-data.org beviser ikke spillerens minutter. Ekstra spilletid, ukendt lineup og ufuldstændig dækning skal fremgå.
9. **Lav et reproducerbart as-of-build.** Rålag + mappingversion + cutoff + schema-/kodeversion giver et dataset med kvalitetsrapport. Historiske kampresultater findes i observationslaget; featurebyggeren ser kun tilladte rækker/felter. Targetjoin udføres separat.
10. **Byg GW-lag ovenpå kamplaget.** Bevar hver kamp i en Double Gameweek. Blank Gameweeks får en GW-række med tom kendt fixtureliste; der oprettes ingen kunstig kamp. Gem både fixturelisten kendt ved forecast og den realiserede FPL-GW-tildeling til evaluering. Efterfølgende udsættelser/omplaceringer må ikke omskrive det gamle forecast.

Første canonical leverance begrænses til PL, officielle labels og et lille antal verificerede felter. Ekstra turneringer og optional kontekst tilføjes efter samme kontrakt, når basen består testene.

## 6. Valideringer og tests, der mangler

Alle nedenstående tests mangler i dag. Brug små, syntetiske edge cases samt anonymiseringsfri offentlige kildeeksempler. Normale tests kører uden netværk; live contract-smoketests er særskilte og valgfrie.

| Område / foreslået testfil | Konkrete kontroller |
| --- | --- |
| `test_snapshot_io.py` | Unikke run-ID'er ved samme klokkeslæt; ingen overskrivning; uændrede råbytes; checksumkontrol; atomisk færdigmarkering; afbrudt write; finaliseret manifest ændres ikke. |
| `test_source_contracts.py` | Timeout, HTTP 429/5xx og begrænset retry/backoff; tomt svar; HTML i stedet for CSV/JSON; manglende required felter; ekstra felter bevares/tolereres; tokenfravær; optional versus required fejl. |
| `test_schemas.py` | Typer, nullability, nøgler og foreign keys; gyldig position; home != away; counts ikke negative; odds >1; sandsynligheder i [0,1]; ingen uendelige floats. Negative FPL-point er tilladt. Minutgrænser følger kildedefinition/competition, ikke en universel 90-minutters cap. |
| `test_identity_mapping.py` | Homonymer, holdaliaser, transfers, sæson-ID-kollision, ukendt ID, dubletmapping og many-to-many-join afvises. Joins må ikke uventet øge antal rækker. |
| `test_canonical.py` | Deduplikering mellem mapper/snapshots, feltprioritet, konfliktflag, DNP versus manglende dækning, fjernede spillere, cup/PL-adskillelse og officielle pointsummer pr. GW. |
| `test_asof.py` | Fetch starter før og slutter efter deadline; svar præcis ved cutoff; UTC/tidszoneskift; ændret deadline/fixture/klub; forsinket statistik; revision af gammel kamp. Alle vælges efter tilgængelighed, ikke blot kampdato. |
| `test_features.py` | Ingen aktuel targetrække i rolling features; deterministisk sortering og tie-regel; forskel på sidste N kampe og 7/14 kalenderdage; cold-start fallback; ingen skjult udfyldning med fremtidige værdier. |
| `test_walk_forward.py` | To kampe i samme GW bruger samme origin; forsinkede træningslabels udelukkes; preprocessing/tuning kun på tidligere data; samme spillerunivers på tværs af sammenlignede modeller. |
| `test_scoring.py` (senere) | Sæsonregler og tærskelgrænser; minutter/start/sub, mål efter position, clean sheets ved relevante minut-/eventgrænser, saves, cards, bonus/ties, egenmål og straffespark. Sammenhold med verificerede officielle kamp-point. |
| `test_distributions.py` (senere) | PMF >=0 og sum 1; tilladt negativ support; mean/varians matcher PMF; kvantiler monotone; blank GW-masse ved 0; fast seed; korrekt DGW-summering og bevaret scenarieafhængighed. |
| `test_offline_pipeline.py` | To syntetiske GWs kan genbygges og evalueres helt offline fra immutable snapshots med identiske sorteret-datahashes og forecasts for samme miljø/seed. |

**Vigtig leakage-regressionstest:** Byg features og forecast for cutoff D. Tilføj/flyt derefter alle observationer med `available_at >= D`, herunder første kamp i en DGW og en senere rettelse af en gammel kamp. Det gamle feature-/forecastresultat skal være uændret. Test også at samme snapshot ikke kan overskrives for at ændre historikken.

Kvalitetsrapporten skal vise antal rækker, dubletter, uløste mappings, missingness pr. felt/kilde/GW, datastaleness, labeldækning og eksklusionsårsager. Identitetsfejl, brudte nøgler og tidsbrud stopper build. Manglende optional felter giver synlig, versioneret fallback. Dækningstærskler fastsættes på faktiske prøver og fryses inden modelevaluering.

## 7. Efterfølgende probabilistisk forecasting

Denne del implementeres først efter datagrundlaget. Hold outputkontrakten stabil, så en simpel baseline kan erstattes uden at ændre backtest eller optimizer.

1. **Fordelingsbaseline til at teste systemet:** en glattet empirisk pointfordeling fra tidligere, tilladte observationer med pooling efter position og dokumenteret cold-start fallback. Den er en reference, ikke den endelige komponentmodel. Start desuden med en enkel baseline for P(spilletid) og minutter.
2. **Minutfordeling:** masse ved 0, start/sub-sandsynligheder og betingede minutfordelinger. Bevar usikkerhed omkring scoringtærskler; forventede minutter alene er utilstrækkelige.
3. **Hold og angreb:** simpel regulariseret Poissonmodel for holdmål og spillerandele betinget på minutter. Start med få features. Simulér fælles kampmål og fordel dem til spillere, så angreb/clean sheets og spillerudfald er konsistente. Dokumentér forenklinger og håndtér egenmål separat.
4. **Øvrig scoring:** DefCon-counts, saves, cards og bonus samt sjældne straffesparks-/egenmålsevents. Tilføj komponenter trinvist, men kald ikke en ufuldstændig komponentfordeling for fulde FPL-point. Brug kun en eksplicit, valideret fallback baseret på tidligere data, hvis en komponent endnu ikke kan modelleres særskilt.
5. **Ren, sæsonversioneret scoringmotor:** omsæt simulerede events og minutter til heltalspoint. Arkivér den relevante officielle regelversion. Kommentarerne i repositoryet er hypoteser; numeriske regler må ikke kopieres ukritisk. Den officielle regelside kunne ikke tekstlæses i denne gennemgang, så reglerne er ikke verificeret her: [officielle FPL-regler](https://fantasy.premierleague.com/help/rules).
6. **GW-fordeling:** aggregér kampe inden for hvert scenarie. En convolution kan bruges til en eksplicit uafhængighedsbaseline; senere modeller bør håndtere fælles skade-/rotationsusikkerhed mellem DGW-kampe. Et kendt blankt kampprogram giver initialt pointmasse ved 0; fremtidige programændringer er en dokumenteret modelbegrænsning.

Clean sheets afhænger af spillerens relevante spilleinterval og regler, ikke alene af holdets slutresultat. Assists og defensive counts skal have FPL-kompatible definitioner. DefCon-tærskler anvendes på de simulerede counts, ikke på countets middelværdi. P(0 FPL-point) og P(0 minutter) er forskellige størrelser og gemmes separat.

Gem fuld PMF eller scenarier samt afledt xP, standardafvigelse, kvantiler og tærskelsandsynligheder. Ved finite PMF-/Monte Carlo-approksimationer dokumenteres tail- og smoothingpolitik, så et sjældent udfald ikke får vilkårlig nul-sandsynlighed. Regler fastlægges uden at se testlabels.

Udskyd XGBoost, Dixon-Coles-udvidelser, taktiske regimeskift, vejr, dommere, prisdynamik og alle solverfeatures, indtil de enkle modeller har en troværdig walk-forward-reference. Hver ekstra datakilde skal kunne fjernes i en sammenligning og have gratis, reproducerbar adgang.

## 8. Walk-forward backtesting

### Protokol

1. Fastlæg sæsoner, evaluerings-GWs, lead time, træningsvindue, minimumshistorik, tilladte kilder, labelpolitik og modelkonfiguration inden testperioden. Coverage-audit afgør, hvilke folds der er gyldige.
2. For hvert origin D: indlæs den arkiverede, da kendte deadline, spillerliste og fixtureplan. Vælg kun inputversioner med `available_at < D`. Rapportér manglende data; hent ikke dagens API som erstatning for et gammelt snapshot.
3. Træningslabels skal være observeret og anvendelige før D. Ved supervised træning skal hver historisk træningsrækkes features bygges ved dens eget forecast-origin, ikke rekonstrueres med information, der først kom inden D. Også skadestatus, position og mappings følger den regel.
4. Fit imputation, skalering, priors, featurevalg og model på træningsdata alene. Start med faste hyperparametre; senere tuning/kalibrering bruger indre kronologiske folds. Ingen random train/test split.
5. Forecast alle spillere i det daværende FPL-univers. Gem PMF/scenarier, features, origin, fixtureliste og runmanifest før evalueringslabels tilkobles. Ved DGW forbliver begge kampe betinget på samme oprindelige information; hverken realiseret kamp 1 eller dens lineup må indgå som kendt input til kamp 2.
6. Evaluer efter GW'en mod officielle outcomes fra en fast, dokumenteret labelversion. Hold foreløbige resultater adskilt fra færdige. Senere labelrettelser giver en ny evaluering; gamle forecasts og rapporter omskrives ikke.
7. Flyt origin frem og gentag. Multi-GW-forecasts evalueres særskilt pr. horisont med oprindeligt cutoff bevaret.

Programændringer efter origin håndteres som realiseret forecastusikkerhed: evaluer imod de faktiske officielle GW-point, men vis særskilt, hvilke folds der blev ramt af omplaceringer. Opdater ikke bagudrettet den fixtureplan, forecastet så.

### Målinger

- Primært: diskret CRPS/ranked probability score på heltalspointfordelingen; supplér med log score, når PMF-support/tailpolitik er veldefineret. For en ren empirisk scenariefordeling er CRPS det naturlige første mål.
- Kalibrering: dækningsgrad og bredde for fx 50/80/95 %-intervaller, diskret/randomiseret PIT og reliability for P(spil), P(60+ minutter) og pointtærskler. Brug faste seeds, hvor diagnostikken randomiseres.
- Sekundært: MAE/RMSE for xP, minutfejl og komponentdiagnostik. God middelværdi alene er ikke succeskriteriet.
- Vis resultater pr. GW, position, minutgruppe, cold start, blank/double GW og forecast-horisont. Rapportér både hele det kendte spillerunivers og en på forhånd defineret relevant spillergruppe; mange ikke-spillende spillere må ikke skjule dårlig kvalitet blandt aktive spillere.
- Sammenlign modeller på identiske folds/spillere og vis ændringen pr. GW. Usikkerhedsintervaller skal respektere fælles kamp-/GW-udfald, fx med blokvis resampling; undgå at behandle alle spiller-rækker som uafhængige.

Hver rapport indeholder antal forecasts, labeldækning, udeladte folds og årsager, kilde-/kodeversion, konfiguration, seeds og links til lokale input-/outputartefakter. Replay skal kunne køre uden netværk.

Optimeringsbacktests er et senere, separat projekttrin med budget, historiske priser, holdstatus, transfers, captain og chips. De læser fastfrosne forecastartefakter. Beslutningspoint og forecast-metrics blandes ikke i modelrapporten.

## 9. Konkret, inkrementel leverancerækkefølge

Hver leverance skal kunne reviewes og verificeres selvstændigt. Nye moduler oprettes først, når trinnet kræver dem; nedenstående navne er foreslåede placeringer.

| Trin | Arbejde og filer | Acceptkriterium |
| --- | --- | --- |
| **1. Reproducerbart rålag** | Udvid `io.py`, `config.py`, kildeadapterne og `scripts/fetch_snapshot.py`. Tilføj `schemas.py`, tests for snapshot/source contracts, eksplicit packaging/testkommando, dependency-lock og `.gitignore`. Parametriser sæson/datarod; bevar modelkode. | En offline mock-kørsel gemmer originale bytes og validerbart manifest. Samme tidspunkt, afbrudt write, required fejl og optional skip er testet. Ingen overskrivning. Reproducerbar installation/import virker. |
| **2. Datakontrakter og coverage-audit** | Indsaml små faktiske prøver via det nye rålag. Dokumentér source fields, gratis adgang, ID'er, publicering og dækning i `notes/data_contracts.md`. Udvid FPL-matchlabels og målrettet Core-ingestion. Implementér schema-/as-of-validering. | Rapport pr. kilde/GW siger præcist, hvilke features/labels der kan bruges og hvorfor. Usikker availability afvises. Ingen løfter om historisk backtest uden bevis. |
| **3. Canonical PL-datasæt** | Tilføj fx `datasets/normalize.py`, `datasets/canonical.py`, `datasets/asof.py`, `scripts/build_dataset.py` og mappingdata. Implementér punkterne i afsnit 5 med få kernefelter. | Offline testdata dækker transfer, DNP/unknown, DGW, blank GW, flyttet fixture og revision. Unikke nøgler, feltprovenance og reconciliation til officielle labels. Samme input giver samme logiske dataset/hash. |
| **4. Deadline-features og backtestskelet** | Refaktorér `features/build.py` omkring eksplicit cutoff; implementér `backtest/walk_forward.py`, runmanifester og en minimal empirisk fordelingsbaseline. Tilføj offline integrationstest. | To syntetiske GWs kan replayes; fremtidige ændringer påvirker ikke tidligere forecasts. Træningsfeatures og labels følger deres respektive tidsregler. Ingen optimizerafhængighed. |
| **5. Enkel komponentmodel og scoring** | Implementér små modeller i de eksisterende `models/`-moduler, plus fx `scoring.py` og `simulation.py`. Begynd med minutter og holdmål; tilføj fuld scoring via verificerede komponenter/fallbacks. | Normaliserede fordelinger, scoringtests, reproducerbare seeds og forecastkontrakt. Sammenligning mod baseline på første gyldige walk-forward-folds med CRPS og kalibrering. |
| **6. Målrettede forbedringer** | Tilføj verificeret all-competition workload, odds/Elo og øvrige komponentforbedringer én ad gangen. Senere separat optimering i `optimizer/`. | Hvert tiltag har dokumenteret tidsdækning og effekt på samme evalueringsgrundlag. Øget kompleksitet beholdes kun ved begrundet forbedring. |

**Første næste kodeændring:** trin 1, begyndende med snapshotkontrakten og dens offline tests; derefter tilpasning af de eksisterende adapters. Der skal ikke trænes en model i dette trin.

## 10. Afklaringer, der skal løses med data i trin 2

- Hvilke historiske sæsoner/GWs har faktisk pre-deadline-provenance, også for spillerunivers og kampflytninger?
- Hvilken verificeret gratis FPL-vej giver komplette per-fixture-labels, inklusive ikke-spillende spillere og efterfølgende korrektioner?
- Hvilke Core-felter har konsistente definitioner og dokumenteret dækning for starterstatus, xG/xA, defensive counts og cup-minutter?
- Hvilke football-data.org-resourcer/felter er tilgængelige med den gratis konto? Matchressourcer alene er ikke dokumentation for player-minutes-dækning. Se [udbyderens v4-dokumentation](https://docs.football-data.org/general/v4/index.html).
- Kan Football-Data.co.uk-odds knyttes entydigt til fixtures og en observation før origin? Historiske closing odds er ikke automatisk kendt ved FPL-deadline. Den aktuelle adapter henter kun upcoming-filen; dokumentationsopslag gav delvist HTTP 429 i reviewet. Se [udbyderens databeskrivelse](https://football-data.co.uk/data.php).
- Kan ClubElo-observationer bruges med tilstrækkelig tidsprovenance og entydig klubmapping? Ellers udelades de fra første baseline.
- Hvilke officielle scoringsregler og tilgængelige scoringfelter gælder i hver evalueret sæson? Gem regelversionen sammen med data og model.

Disse afklaringer spærrer ikke for at implementere rålag, schemas og syntetiske tests. De afgør, hvilke virkelige data og modelkomponenter der senere kan godkendes.

# FPL Lab

Kørbar lokal prototype: officielle snapshotdata → komponentbaseline → pointfordelinger → lovlig trup/XI/anfører → simulation af holdet og kronologisk retrospektiv evaluering.

## Start

Fra repositoryets rod, med den eksisterende virtuelle Python-installation:

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Åbn http://127.0.0.1:8501. **Mit hold** er hovedindgangen: indtast 15 spillere, deres faktiske salgsværdier, bank og resterende gratis transfers. Gem lokalt, vælg 1–4 GWs og tryk **Sammenlign transferforslag**. Det uændrede hold sammenlignes med transferstrategier uge for uge; alle transfers nu kan også vælges. XI, bænk og anfører/vice vælges med autosubs på planlægningsscenarier og evalueres separat. Hits er slået fra som standard. Eksempelholdet fra skærmbilledet indeholder kun verificerede spiller-ID’er; bank og salgsværdier skal udfyldes.

**Import via hold-ID/link:** Skriv fx `3533723` eller det officielle link fra FPL’s pointside øverst i **Mit hold**. Tryk **Hent hold fra FPL**, kontrollér GW og spillerne, og tryk **Brug dette hold**. Importen udfylder de 15 spillere; dit gemte hold ændres først ved **Gem hold**. Bank fra den offentlige deadline vises, men skal kontrolleres. Salgsværdier, resterende gratis transfers og transfers siden deadline udfyldes manuelt; de er ikke tilgængelige i de offentlige picks. Ved samme gemte trup kan du eksplicit genbruge din lokale økonomi.

Ligesom [FPL Reviews normale ID-import](https://docs.fplreview.com/the-model/planner-interface/sync_team/) er dette den seneste **offentlige deadlineopstilling**, ikke private transfers lavet bagefter. Et Free Hit-hold afvises som midlertidigt; brug manuel indtastning af den faste trup. Importen bruger kun officielle offentlige endpoints (bootstrap, entry, event picks), kræver ikke login og gemmer rå svar som lokale immutable snapshots. Ingen requests ved appstart/genkørsel, ingen automatiske retries; HTTP-fejl ændrer ikke dit gemte hold. Prognoser bruger fortsat det valgte officielle datagrundlag; ny holdimport er ikke en opdatering af alle spillerhistorikker/priser.

**Holdoverblik:** Startsiden viser bank, gratis transfers og truppen på en bane efter position (ikke en anbefalet XI). Import og økonomi ligger under **Redigér hold**, og indstillinger under **Planlæg transfers**. Gemte/beregnede forslag viser ud/ind-kort og GW-faner med den faktiske anbefalede XI, prioriteret bænk, anfører, xP og minutter. Spiller-xP er før anførerfordobling; gamle rapporter beholder deres oprindelige datatidspunkt. Layoutet tilpasser sig smalle skærme.

På **Analyse og eksperimenter** ligger den hidtidige enkelt-GW-prototype, spillerforklaringer, retrospektiv evaluering og gemte prior-/oddsforsøg. Den gamle optimering er fortsat til en ny trup til købspriser. Se [transferforløb og antagelser](notes/my_team_transfers.md).

Kun hvis pakkerne mangler: `.venv/bin/python -m pip install -r requirements-prototype.txt`. Versionslisten er afprøvet med projektets Python 3.14.

Samme kæde uden brugerflade:

```bash
.venv/bin/python scripts/run_prototype.py --event 6 --draws 3000 --seed 42 --budget 100
```

CLI vælger det nyeste verificerede officielle snapshot; brug `--snapshot PATH` for et bestemt input. Udelad `--event` for den første GW efter snapshotets observationstid. `--locked 1 439` og `--excluded 26` bruger officielle spiller-ID'er. Hver kørsel opretter en ny mappe under `artifacts/prototype/` med `report.json` og `players.csv`. Eksisterende output overskrives ikke. Ingen downloads sker ved modelkørsel eller appstart.

## Frisk kampvis historik for hele spillerpuljen

Dataindsamling er en eksplicit CLI-handling, adskilt fra Streamlit-genkørsler:

```bash
.venv/bin/python scripts/capture_all_players.py --season 2026-2027 --request-interval 0.5
```

Kommandoen henter frisk officiel bootstrap/fixtures og derefter alle spiller-ID'er fra netop dette bootstrap. Ingen hardcodet puljestørrelse. Én session, sekventielle requests, 0,5 sekunders pause (minimum 0,25), connect/read-timeout 10/30 sekunder, højst tre spillerforsøg ved 429/5xx/timeout/forbindelsesfejl og 1/2 sekunders backoff. `Retry-After` respekteres også mellem spillere; ved ventetid over 30 sekunder eller udtømte 429-forsøg udskydes resten eksplicit. Bootstrap/fixtures anvender fortsat den eksisterende adapters fail-fast-politik.

Hver rå body og hvert forsøg gemmes uændret i et nyt snapshot. Context er påkrævet; individuelle spillerfejl tillades med `overall=partial`, fejlede/udskudte ID'er og tidsprovenance. Ingen fallback til tidligere captures. Afbrydelse bevarer staging-data og publicerer ikke et komplet snapshot. Der er endnu ingen resumefunktion for afbrudte runs. Normalisering genbruger labelkontrakterne; dens rapport ligger under `artifacts/player_history/`. CLI-exit: 0 komplet uden karantæne, 2 delvis dækning/karantæne, 1 workflowfejl.

Genindlæs appen og vælg det nye snapshot. Den viser forsøg, gyldige svar, tomme historikker, fejl/manglende svar, brugbare rækker, eksplicitte nulminutter og karantæne samt status pr. spiller.

### Opdatér data i appen

Øverst på **Mit hold** henter **Hent seneste data** kun officiel bootstrap og kampplan (to HTTP-kald) og gemmer et nyt immutable snapshot. Priser, skadesstatus, nyheder og deadlines kommer fra dette snapshot; kampvis historik læses fra den seneste komplette fuldpuljeindsamling, som fandtes på det tidspunkt, og beholder sit eget snapshot-ID og hentetidspunkt. Begge tider vises særskilt. Appen henter aldrig data ved start eller almindelig genkørsel.

Hvis en kamp er begyndt/afsluttet siden historikken, et resultat er revideret, eller en ny spiller mangler historik, blokeres nye transferforslag. Brug da **Hent fuld spillerhistorik** på samme side (eller CLI-kommandoen ovenfor); det tager flere minutter og gemmer også et nyt snapshot. Et delvist/fejlet svar bliver ved med at være synligt som delvis dækning, aldrig som en nulminutterskamp. Den nuværende element-summary-kilde sender hele spillerhistorikken pr. forespørgsel, så en fuld opdatering efter en spillet GW bruger stadig ét kald pr. spiller. En egentlig GW-delta-kilde kræver særskilt felt- og proveniensvalidering.

## Data og antagelser

Den første fulde indsamling, 24. september 2026, hentede 667/667 spillere: 3.216 finale spiller-kampe, 1.678 eksplicitte nulminuttersrækker, ingen tomme historikker, fejl eller karantæne. Snapshot: `2026-09-24_164002695814Z_4fee7b0047014ffba28b416e9b9928ce`. De tidligere samples er bevaret. Appen viser datatidspunkt og alder. GW-valget er relativt til snapshotet; et gammelt snapshot er ikke en live-skadesopdatering. Sæsonen er foreløbig 2026/27.

- **Spilletid:** start/indskiftning/DNP med udglattede frekvenser. Med kampdata bruges observerede starter og minutter; ellers aktuelle sæsonminutter/starter og en markeret tilnærmelse for indskiftninger. Kampantal for nuværende klub er en tilnærmelse for tilflyttere og sent tilføjede spillere.
- **Kort/manglende historik:** eksplicitte priors og en `fallbacks`-kolonne. Standard er én prior-kamp med startchance 0,45, indskiftningschance 0,10 og 82/22 minutter. Ukendt er ikke nul. Manglende historikrækker bruges ikke som DNP.
- **Hændelser:** xG/xA pr. 90 minutter udglattes med tre prior-kampe. Mål-priors for GK/DEF/MID/FWD er 0,002/0,06/0,20/0,38; assist-priors 0,005/0,09/0,16/0,12. Øvrige standarder fremgår af `models/baseline.py`. Holdets målrate bruger tidligere resultater og fem prior-kampe. Priors er antagelser, ikke estimeret kalibrering.
- **Skader:** officiel chance for næste runde skalerer deltagelsen. Ved skadesstatus uden chance bruges konfigurerbar faktor 0,25. Længere fremme valgte GWs er scenarier uden prognose for skadesheling.
- **Simulation:** kategorisk deltagelse, afkortede normalfordelte minutter, Poisson-hændelser og binomial tilnærmelse for 0–3 bonuspoint. Seed er valgfrit i Python-API'et; CLI/UI registrerer seed (standard 42). Samme snapshot, konfiguration, seed og pakkeversioner giver samme simulation.

Fælles modstandermål og måltidspunkter giver afhængighed mellem holdkammeraters clean sheets/indkasserede mål. Spilleres mål/assists simuleres uafhængigt og behøver ikke summere til holdets mål. Spilletid er uafhængig: ingen sammenhængende virkelig startellever, gensidig udelukkelse af keepere eller fælles rotationschok. Bonus bruger ikke fuld BPS-rangering. Kort uden spilleminutter og en fuld sekventiel hændelsesmodel simuleres ikke. Fordelingerne er **foreløbige og ikke dokumenteret kalibrerede**.

## Point og holdvalg

Pointkomponenten følger de [officielle 2026/27-pointregler](https://www.premierleague.com/en/news/2174909), inklusive forsvarsbidrag, keepermål, negative point og 60-minuttersgrænsen. Koncessioner tælles i spillerens simulerede interval; efter udvisning frem til kampens slutning.

Optimizeren vælger 15 spillere (2 GK/5 DEF/5 MID/3 FWD), højst tre fra samme klub, inden for budgettet, samt lovlig XI og anfører. Den kontrollerer lås/udeluk og officiel valgbarhed. Se [officielle trupregler](https://www.premierleague.com/en/news/2174419).

I den ældre enkelt-GW-analyse er målet XI-xP + anfører-xP + konfigurerbar vægt af bænk-xP (standard 0,10). Dette er en tilnærmelse i optimeringen; viceanfører og bænkrækkefølge vælges efter xP. Et tidsbegrænset solverresultat vises som ikke bevist optimalt. Det faste hold evalueres bagefter på **nye scenarier med seed + 1**, med autosubs, formationskrav, reservemålmand og viceanfører pr. scenarie. Nul point tæller ikke som DNP. Det viste bænkbidrag beregnes i scenarierne.

## Evaluering og tid

Liveprognosen bruger det valgte snapshot og kampobservationer tilgængelige senest på dets observationstid. Et snapshot efter GW-deadline kan ikke bruges som prædeadlineprognose.

Evalueringen kræver mindst to tidligere kampobservationer og komplette, finale mål-GW-rækker. Begge metoder evalueres på præcis samme rækker. Referencen er gennemsnit af tidligere kamp-point ganget med mål-GW'ens kampantal. Begge bruger alene tidligere GWs med kickoff før deadline. Aktuelle sæsonaggregater, skadesstatus og odds bruges ikke til historiske prognoser. Baseline rapporterer MAE/RMSE/empirisk CRPS; punktreferencen MAE/RMSE. Appen viser samlet, pr. position og pr. GW, samt minut-MAE/RMSE og DNP-Brier med sandsynlighedsintervaller. Minutreferencen er tidligere kampminutters gennemsnit; DNP-referencen er tidligere nulminuttersfrekvens (opløftet i kampantal ved DGW, en uafhængighedsantagelse).

Baselineformler og standardparametre er uændrede (`component_baseline_v1`). Et nyt konservativt dækningskrav beskytter nævneren: alle tidligere afsluttede kampe for én konsistent observeret klub skal have rækker. Huller, transfers og uklar registreringsstart giver markeret aggregate/prior-fallback i liveprognosen og udeladelse fra evalueringen. Manglende rækker bliver aldrig nulminutter. Denne politik kan udelade reelt komplette historikker for nye spillere; vi opfinder ikke registreringsdatoer.

Den første brede kørsel (seed 42, 3.000 prognosescenarier og 2.000 evalueringsscenarier pr. GW) dækker 593 spillere / 1.779 spiller-GWs, GW3–5. Point-MAE/RMSE: baseline 1,376/2,191, reference 1,298/2,421; baseline-CRPS 0,810. Minut-MAE: 18,22 mod 11,47. DNP-Brier: 0,11097 mod 0,11201. Baseline er altså ikke bedre på alle mål; minutmodellen og overestimeret deltagelse er synlige svagheder, ikke rettet ved efterfølgende tuning i denne milepæl.

Både appens kørselsknap og CLI gemmer `report.json`, `players.csv` og `evaluation_rows.csv` i en ny mappe. Rapporten indeholder konfiguration, seed, model-/evalueringsversion, kodechecksums, pakkeversioner, snapshot-ID/manifestchecksum, dækning, grupperede resultater og udeladte ID'er/årsager. Det er lagring af en enkelt kørsel, ikke en konfigurations-/forsøgsrunner.

Dette er **retrospektivt, ikke strikt prospektivt**: historiske labels er hentet senere og kan være revideret; positioner og kampplan er fra aktuelle versioner. Holdtilknytning udledes af tidligere observerede kampe; flyttede/ufuldstændige kampmængder udelades. Den aktuelle spillerpulje og det konservative dækningskrav giver udvælgelsesbias; kun tre test-GWs giver stadig et kort grundlag. Historiske snapshots og en længere urørt testperiode mangler for stærkere konklusioner.

Freeze/readiness bevares som separat kvalitetsspor og blokerer ikke prototypen. Se `notes/prospective_freeze.md` og `notes/label_contracts.md`.

## Implementeret og senere arbejde

Implementeret: immutable adapters/snapshots, versionerede labels, as-of/outcome-selektion, readiness/freeze samt ovenstående baseline, simulation, optimizer, CLI, Streamlit og mini-evaluering. Modelkode ligger i `src/fpl_model/`, adskilt fra UI.

De ældre `models/minutes.py`, `attack.py`, `defcon.py` og `team_goals.py` er stadig scaffold; prototypens komponentlogik ligger i `models/baseline.py` og `simulation.py`. Der er ingen trænet ML-model. Transfers nu med fastholdt trup over 1–4 GWs og valgfri defensiv oddsvariant er implementeret. Uge-for-uge-transfersekvenser og autosub-aware opstillinger for fundne kandidattrupper er implementeret. Chips, Core/Elo i prognoser og dokumenteret kalibrering er senere arbejde.

```bash
.venv/bin/python -m pytest -q
```

Default-tests er offline og omfatter scoring, lovlighed, autosubs, lækage, reproducerbarhed og appens fulde kæde. Rå snapshots og genererede resultater forbliver gitignored.

### Spillerforklaringer og minutdiagnostik

Kør prototypen på det eksisterende snapshot og vælg en spiller under **Spillere og fordelinger**. Forklaringen viser historik, start/indhop/DNP, xG/xA-priorer og udglatning, skades-/kampjustering samt pointkomponenter fra præcis samme simulation. Under **Evaluering** vises minut-bias/MAE/RMSE mod reference efter position og historik før forecast, både hele evalueringspuljen og en eksplicit regelmæssig gruppe. Alt gemmes i den nye kørselsrapport; tidligere resultater overskrives ikke. Modellen er fortsat `component_baseline_v1`.

Definitioner, fund og én anbefalet efterfølgende ændring: [notes/minutes_diagnostics.md](notes/minutes_diagnostics.md).

### Afgrænset eksperiment: tre frekvenspriorer

Kør offline mod den eksisterende baseline-rapport (ingen AI-kald eller downloads):

```bash
.venv/bin/python scripts/compare_minutes_priors.py --reference-run artifacts/prototype/20260924T164629668707Z_0c22d357/report.json
```

Dette sammenligner **1,0 / 0,25 / 0,10** i `frequency_prior_games`, med `minutes_prior_games=1,0` og alle øvrige antagelser fra rapporten uændret. Standarden er stadig 1,0/1,0. Den tidligere fælles sidebar-kontrol styrer nu kun betingede minutter; frekvensprioren i den almindelige app-prognose forbliver 1,0. Nye kandidatversioner betegnes `component_frequency_025_v1` og `component_frequency_010_v1`.

Kommandoen validerer snapshot/manifest og præcis samme mål-/reference-rækker samt identisk baseline-reproduktion. Den bruger rapportens simulationsantal og primære seed plus to ekstra seeds; hvert GW bruger `seed + GW`. Gemte JSON/CSV-filer under `artifacts/minutes_experiments/` indeholder fulde rækker, konfiguration, model-/kodeversioner, alle gruppemål og parvise seed-forskelle. Eksisterende filer overskrives ikke. Genindlæs appen: **Tre frekvenspriorer · gemt udviklingseksperiment** kan ses uden at køre den almindelige prognose. Sidebarens antagelser ændrer ikke en gemt sammenligning.

GW3–5 er **udviklingsdata**, allerede brugt til diagnostik. Seeds viser kun Monte Carlo-støj, ikke statistisk sikkerhed. Standarden ændres ikke automatisk. Se [resultater og afvejninger](notes/frequency_prior_experiment.md).

Næste større modeludvidelse er **odds-integration**, ikke implementeret her: som alternativ/supplement til holdets målmodel, fjern bookmaker-margin, håndtér manglende markeder og observationstidspunkter eksplicit, og sammenlign med/uden odds. Aktuelle odds må aldrig indsættes i historiske forecasts.

Allerede gemte seeds kan sammenfattes **uden nye simulationer eller snapshotlæsning**:

```bash
.venv/bin/python scripts/compare_minutes_priors.py --saved-comparison artifacts/minutes_experiments/20260924T172721154282Z_40fcacf6/comparison.json
```

Det opretter en ny rapport med kildefilens checksum, uændrede kørsler og `seed_summary.csv`. Appen viser gennemsnit [min–maks] over seeds, både samlet og for regelmæssige spillere, og fremhæver forværrede gruppemål. Antal observationer ganges ikke med antal seeds. Spændet viser simulationsvariation, ikke statistisk usikkerhed på tværs af kampe.

### Valgfri defensiv oddsvariant

`component_defensive_odds_v1` bruger gyldige 1X2/O-U 2,5-markeder til clean sheets og indkasserede mål: enten Football-Data.co.uk/Bet365 eller The Odds API/William Hill, som separate kildevalg. Egne mål/assists, minutter og øvrige hændelser bevares. Baseline er standard. Manglende/uklare markeder, identiteter, kickoff eller tidsprovenance giver synlig fallback.

Kør sammenligningen offline på de allerede hentede snapshots:

```bash
.venv/bin/python scripts/compare_defensive_odds.py \
  --history-snapshot data/raw/2026-09-24_164002695814Z_4fee7b0047014ffba28b416e9b9928ce \
  --context-snapshot data/raw/2026-09-27_104712135033Z_f5ca590694aa4e57ae515ce1a16362fa \
  --odds-snapshot data/raw/2026-09-27_104712135033Z_f5ca590694aa4e57ae515ce1a16362fa \
  --forecast-origin-at 2026-09-27T10:55:00Z --event 6 --draws 3000 --seed 42 \
  --include-offline-example
```

Udelad `--forecast-origin-at` for en ny, eksplicit registreret kørselstid; brug passende eksisterende captures. Kommandoen henter ingen data. Det konkrete nye feed indeholder 0 PL-rækker, så 0/10 GW6-kampe får odds; det opdigtede eksempel markeres særskilt og er ikke en aktuel oddsprognose. Appsektionen **Odds til clean sheets og indkasserede mål** viser de gemte sammenligninger uafhængigt af sidebarens almindelige prognosevalg. Kun egentlige captures er kilde til en rigtig prognose; syntetiske eksempler er udelukket som dokumentation for performance.

[Markedspolitik, verificerede aliaser, tidszoneevidens, fit og begrænsninger](notes/defensive_odds.md).

**Reel William Hill-sammenligning**, offline på API-svaret fra adgangstjekket (ingen nye kald):

```bash
.venv/bin/python scripts/compare_defensive_odds.py \
  --history-snapshot data/raw/2026-09-24_164002695814Z_4fee7b0047014ffba28b416e9b9928ce \
  --context-snapshot data/raw/2026-09-27_104712135033Z_f5ca590694aa4e57ae515ce1a16362fa \
  --odds-snapshot data/raw/2026-10-01_135741394331Z_fc98daee5363459eb0d009bf198eb4be \
  --odds-source the_odds_api --event 6 --draws 3000 --seed 42
```

Den gennemførte GW6-kørsel har **10/10 godkendte kampe efter matching, tidskontrol og fit**. Vælg `the_odds_api`-rapporten under **Odds-sammenligning** i appen. Football-Data-rapporten med 0/10 og det syntetiske eksempel forbliver særskilte valg. Rapporterne viser kilde/bookmaker, lokal tilgængelighed, provider-opdateringstider, historik-/kontekstalder og ændringer i point, trup, XI og anfører. Modelversion og standardmodel er uændrede.

**Kun ved en ønsket fremtidig opdatering** (forbruger API-credits):

```bash
.venv/bin/python scripts/fetch_odds_api.py
```

Dette læser `ODDS_API_KEY` fra lokal `.env`, laver ét kald og skriver et nyt immutable snapshot samt kvotestatus til terminalen. Ingen automatiske gentagelser. Brug det udskrevne snapshot som `--odds-snapshot` i den offline sammenligning. Appstart og genkørsler henter aldrig odds. Hentekommandoen er kun mock-testet i denne integration; det gemte adgangstjek er genbrugt.

Uge-for-uge-transferstrategier, FPL-nyheder og eksplicitte skadesscenarier: se [notes/transfer_sequences.md](notes/transfer_sequences.md). Ingen automatisk nyhedsindsamling eller chips.

### Odds til angreb og forsvar

I **Mit hold → Planlæg transfers → Prognosemodel** kan du vælge **Odds til angreb og forsvar · William Hill**. Den gamle defensive variant ændrer fortsat kun clean sheets/indkasserede mål. Den nye `component_attacking_odds_v1` fordeler også holdets odds-målbudget efter udglattet spiller-xG/xA og forventede minutter, uden ekstra egen-holdstyrkemultiplikator. Baseline er stadig standard. Se [metode, fallback og begrænsninger](notes/attacking_odds.md). Gemte trevejssammenligninger ligger under **Analyse og eksperimenter → Oddsmodeller**; kør den eksisterende sammenlignings-CLI med `--odds-scope attack_and_defence`. Ingen implicit datahentning.

Opt-in **Eksperiment · rolle, returminutter og fælles mål** tilføjer nyere rollehistorik, separate returbegrænsninger og fælles scorer/assist-mål. Baseline er fortsat standard; den første rolle-evaluering forværrer regelmæssige spilleres minutfejl. Gemte før-deadline-scenarier kan efterkontrolleres mod endelige officielle labels fra appen eller CLI. Se [metode, begrænsninger og kommandoer](notes/model_evolution.md).

**Efter runden:** Under **Analyse og eksperimenter → Efter runden** kan både tidligere reelle GW6-oddsrapporter og nyere gemte simulationer efterkontrolleres på samme endelige spillerudfald. Rundestatus, afventende labels og fejl for regelmæssige spillere vises eksplicit. Ældre rapporter uden scenarier får ingen CRPS. [Arbejdsgang og konkret GW6-kommando](notes/model_evolution.md#praktisk-efterkontrol-af-gw6-og-senere-runder). Ingen automatisk datahentning, genberegning eller ændring af standardmodellen.

### Rollespecifik spilletid (valgfrit eksperiment)

Vælg **Mit hold → Prognosemodel → Eksperiment · rollespecifik spilletid**. Baseline er fortsat standard. Gemte sammenligninger findes under **Analyse og eksperimenter → Rollespecifik spilletid · udviklingssammenligning**. Se [kontrakt, offline-kommando og resultater](notes/role_minutes.md). Ingen nye downloads kræves.

### Dødboldsroller (valgfrit følsomhedsscenarie)

**Mit hold → Prognosemodel → Eksperiment · dødboldsroller og odds** bruger gemte officielle rolleordener til at omfordele en antaget del af eksisterende mål-/assistbudgetter. Baseline er uændret; dette er ikke en kalibreret non-penalty xG-model. Konfiguration og kildetidspunkter er synlige. Gemte sammenligninger findes under **Analyse og eksperimenter → Dødboldsroller**. Se [metode, begrænsninger og offline-kommando](notes/set_piece_roles.md).

### Præstationsafhængig bonus (valgfrit eksperiment)

Under **Mit hold → Prognosemodel** kan baseline eller angrebsodds få tilvalget **Eksperiment: præstationsafhængig bonus**. Kun bonus ændres; modellen trænes på tidligere endelige kampe og anvendes på simulerede præstationer. Standardmodellen er uændret. **Analyse og eksperimenter → Bonus** viser gemt evaluering og GW7-prognose. Resultaterne er blandede og begrunder ikke et standardskifte. Se [metode, begrænsninger og reproducerbar kommando](notes/conditional_bonus.md).

### Spillerprior fra sidste sæson (eksperiment)

Under **Mit hold → Prognosemodel** kan Baseline eller angrebsoddsmodellen bruge seneste afsluttede sæsons officielle xG/xA som svagt spillerprior. Tilvalget er fravalgt som standard og bevarer spilletid, bonus og forsvar. Eksisterende `history_past` genbruges uden downloads; manglende/ugyldig historik giver markeret positions-fallback. Gemte sammenligninger vises under **Analyse og eksperimenter → Spillerprior fra sidste sæson · xG/xA**. Se [metode, begrænsninger og kørekommando](notes/previous_season_priors.md).

### FPL-assistkorrektion (eksperiment)

Under **Mit hold → Prognosemodel** findes det fravalgte tilvalg **Eksperiment: FPL-assistkorrektion**. En fælles faktor fra tidligere færdige FPL-assists/xA ændrer kun assistdelen. Den kombineres ikke med de andre eksperimenter. Gemte resultater findes under **Analyse og eksperimenter → FPL-assists · xA-korrektion**. Den første udviklingsevaluering forbedrer ikke baseline; behold standardmodellen. Se [metode, resultater og kørekommando](notes/fpl_assist_correction.md).

### Standardprognose og manuelle chips

**Mit hold** bruger nu én standardprognose. Bekræft dine chips under **Redigér hold →
Mine chips**, vælg derefter chipuge under **Planlæg transfers → Chips i denne plan**.
Wildcard, Free Hit, Triple Captain og Bench Boost understøttes med manuelt valgte uger
inden for 1–4 GWs. Automatisk chipstrategi frem til GW19 kommer senere.
Modelvalg og forsøg ligger under **Analyse og eksperimenter → Transferlaboratorium**.
Se [regler, brug og begrænsninger](notes/chips.md).

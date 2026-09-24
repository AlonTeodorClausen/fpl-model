# FPL Lab

Kørbar lokal prototype: officielle snapshotdata → komponentbaseline → pointfordelinger → lovlig trup/XI/anfører → simulation af holdet og en lille retrospektiv evaluering.

## Start

Fra repositoryets rod, med den eksisterende virtuelle Python-installation:

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Åbn http://127.0.0.1:8501. Vælg snapshot, én GW, budget, antagelser og eventuelt låste/udelukkede spillere. Tryk **Kør prognose, simulation og optimering**. Download tabeller og kørselsrapport som CSV/JSON. Budgettet er til en ny trup; salgsværdier indgår ikke.

Kun hvis pakkerne mangler: `.venv/bin/python -m pip install -r requirements-prototype.txt`. Versionslisten er afprøvet med projektets Python 3.14.

Samme kæde uden brugerflade:

```bash
.venv/bin/python scripts/run_prototype.py --event 6 --draws 3000 --seed 42 --budget 100
```

CLI vælger det nyeste verificerede officielle snapshot; brug `--snapshot PATH` for et bestemt input. Udelad `--event` for den første GW efter snapshotets observationstid. `--locked 1 439` og `--excluded 26` bruger officielle spiller-ID'er. Hver kørsel opretter en ny mappe under `artifacts/prototype/` med `report.json` og `players.csv`. Eksisterende output overskrives ikke. Ingen downloads sker ved modelkørsel eller appstart.

## Data og antagelser

Det seneste eksisterende snapshot, 21. september 2026, indeholder 667 spillere og seks spilleres kampvise historik. Appen viser datatidspunkt og alder. GW-valget er relativt til snapshotet; et gammelt snapshot er ikke en live-skadesopdatering. Sæsonen er foreløbig 2026/27.

- **Spilletid:** start/indskiftning/DNP med udglattede frekvenser. Med kampdata bruges observerede starter og minutter; ellers aktuelle sæsonminutter/starter og en markeret tilnærmelse for indskiftninger. Kampantal for nuværende klub er en tilnærmelse for tilflyttere og sent tilføjede spillere.
- **Kort/manglende historik:** eksplicitte priors og en `fallbacks`-kolonne. Standard er én prior-kamp med startchance 0,45, indskiftningschance 0,10 og 82/22 minutter. Ukendt er ikke nul. Manglende historikrækker bruges ikke som DNP.
- **Hændelser:** xG/xA pr. 90 minutter udglattes med tre prior-kampe. Mål-priors for GK/DEF/MID/FWD er 0,002/0,06/0,20/0,38; assist-priors 0,005/0,09/0,16/0,12. Øvrige standarder fremgår af `models/baseline.py`. Holdets målrate bruger tidligere resultater og fem prior-kampe. Priors er antagelser, ikke estimeret kalibrering.
- **Skader:** officiel chance for næste runde skalerer deltagelsen. Ved skadesstatus uden chance bruges konfigurerbar faktor 0,25. Længere fremme valgte GWs er scenarier uden prognose for skadesheling.
- **Simulation:** kategorisk deltagelse, afkortede normalfordelte minutter, Poisson-hændelser og binomial tilnærmelse for 0–3 bonuspoint. Seed er valgfrit i Python-API'et; CLI/UI registrerer seed (standard 42). Samme snapshot, konfiguration, seed og pakkeversioner giver samme simulation.

Fælles modstandermål og måltidspunkter giver afhængighed mellem holdkammeraters clean sheets/indkasserede mål. Spilleres mål/assists simuleres uafhængigt og behøver ikke summere til holdets mål. Spilletid er uafhængig: ingen sammenhængende virkelig startellever, gensidig udelukkelse af keepere eller fælles rotationschok. Bonus bruger ikke fuld BPS-rangering. Kort uden spilleminutter og en fuld sekventiel hændelsesmodel simuleres ikke. Fordelingerne er **foreløbige og ikke dokumenteret kalibrerede**.

## Point og holdvalg

Pointkomponenten følger de [officielle 2026/27-pointregler](https://www.premierleague.com/en/news/2174909), inklusive forsvarsbidrag, keepermål, negative point og 60-minuttersgrænsen. Koncessioner tælles i spillerens simulerede interval; efter udvisning frem til kampens slutning.

Optimizeren vælger 15 spillere (2 GK/5 DEF/5 MID/3 FWD), højst tre fra samme klub, inden for budgettet, samt lovlig XI og anfører. Den kontrollerer lås/udeluk og officiel valgbarhed. Se [officielle trupregler](https://www.premierleague.com/en/news/2174419).

Målet er XI-xP + anfører-xP + konfigurerbar vægt af bænk-xP (standard 0,10). Dette er en tilnærmelse i optimeringen; viceanfører og bænkrækkefølge vælges efter xP. Et tidsbegrænset solverresultat vises som ikke bevist optimalt. Det faste hold evalueres bagefter på **nye scenarier med seed + 1**, med autosubs, formationskrav, reservemålmand og viceanfører pr. scenarie. Nul point tæller ikke som DNP. Det viste bænkbidrag beregnes i scenarierne.

## Evaluering og tid

Liveprognosen bruger det valgte snapshot og kampobservationer tilgængelige senest på dets observationstid. Et snapshot efter GW-deadline kan ikke bruges som prædeadlineprognose.

Mini-evalueringen kræver mindst to tidligere kampobservationer og komplette, finale mål-GW-rækker. Begge metoder evalueres på præcis samme rækker. Referencen er gennemsnit af tidligere kamp-point ganget med mål-GW'ens kampantal. Begge bruger alene tidligere GWs med kickoff før deadline. Aktuelle sæsonaggregater, skadesstatus og odds bruges ikke til historiske prognoser. Baseline rapporterer MAE/RMSE/empirisk CRPS; punktreferencen MAE/RMSE.

Dette er **retrospektivt, ikke strikt prospektivt**: historiske labels er hentet senere og kan være revideret; positioner og kampplan er fra aktuelle versioner. Holdtilknytning udledes af tidligere observerede kampe; flyttede/ufuldstændige kampmængder udelades. Det lille udvalg er ikke repræsentativt. Historiske snapshots, bredere kampvis historik og en urørt testperiode mangler for stærkere konklusioner.

Freeze/readiness bevares som separat kvalitetsspor og blokerer ikke prototypen. Se `notes/prospective_freeze.md` og `notes/label_contracts.md`.

## Implementeret og senere arbejde

Implementeret: immutable adapters/snapshots, versionerede labels, as-of/outcome-selektion, readiness/freeze samt ovenstående baseline, simulation, optimizer, CLI, Streamlit og mini-evaluering. Modelkode ligger i `src/fpl_model/`, adskilt fra UI.

De ældre `models/minutes.py`, `attack.py`, `defcon.py` og `team_goals.py` er stadig scaffold; prototypens komponentlogik ligger i `models/baseline.py` og `simulation.py`. Der er ingen trænet ML-model. Transfers, chips, fler-GW-planlægning, Core/odds/Elo i prognoser, fuld spillerhistorik og dokumenteret kalibrering er senere arbejde.

```bash
.venv/bin/python -m pytest -q
```

Default-tests er offline og omfatter scoring, lovlighed, autosubs, lækage, reproducerbarhed og appens fulde kæde. Rå snapshots og genererede resultater forbliver gitignored.

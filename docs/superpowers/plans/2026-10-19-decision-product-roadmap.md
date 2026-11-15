# Fra modelværksted til forståelig FPL-beslutningshjælp

> **For agentic workers:** Brug `superpowers:executing-plans` ved implementering af den enkelte godkendte leverance. Afkrydsningsfelter er arbejde, der endnu ikke er udført. Dette er en prioriteret produktplan; senere model- og driftsleverancer afgrænses særskilt før implementering.

**Goal:** Hjælpe brugeren med at vælge hold, transfers og chips bedre end ved blot at læse FPL-statistik — med konkrete begrundelser og efterfølgende kontrol af anbefalingerne.

**Architecture:** Bevar Streamlit, de eksisterende snapshots, prognoser, scenarier og optimering. Bind den daglige anbefaling sammen med spillerforklaringen og evalueringen gennem de samme versionsbestemte input og rapporter. Adskil produktforbedringer fra ændringer i prognosemodellen.

**Tech Stack:** Eksisterende Python, NumPy, SciPy, Streamlit og pytest. Ingen ny platform eller database er en forudsætning for de første leverancer.

**Spec:** Brugerens ønske 19. oktober 2026 om en konkret, trinvis plan med fokus på edge, brugervenlighed og forståelig dokumentation. Første leverance implementeres særskilt; senere leverancer er fortsat forslag.

## Global Constraints

- Bevar eksisterende kodeændringer, holdprofiler, rådata og rapporter. Ingen generel omskrivning.
- `component_baseline_v1` forbliver standard, indtil en konkret modelændring er vurderet og godkendt.
- Ingen nutidige odds, skadesoplysninger eller sæsonaggregater i historiske input, hvor de ikke var tilgængelige.
- Hold retrospektive udviklingsresultater, dokumenterede før-deadline-prognoser og syntetiske eksempler adskilt.
- Manglende historik er ikke DNP. Ukendt skadesprognose er ikke en estimeret medicinsk sandsynlighed.
- Prognoser beregnes én gang pr. dataversion/model/horisont og genbruges på tværs af spiller- og holdvisninger.
- Rådata, credentials og genererede rapporter følger eksisterende ignore-regler. Ingen automatisk publicering eller kontohandling på FPL.

## Review Focus

1. En igangværende kamp eller én karantænerække må ikke skjule en allerede gemt prognose; kritiske fejl må stadig blokere nye ugyldige beregninger. Test i leverance 1.
2. Spillerkort og transferforslag skal bruge samme model, dataversion og GW — også efter ændring af indstillinger. Test i leverance 2.
3. Efterfølgende data må ikke ændre prognosen, som evalueringen hævder blev lavet før deadline. Test i leverance 3.
4. En gevinst blandt reserver må ikke skjule en forværring blandt faste startere eller relevante transferkandidater. Test og resultatkrav i leverance 4.
5. Chip/FT-gevinster ved horisontens slutning og private hold på en fælles server må ikke fremstilles som henholdsvis globalt optimale og fælles brugerdata. Test i leverance 5 og 6.

## Faktisk status ved gennemgangen

| Område | Implementeret | Vigtig grænse |
|---|---|---|
| Data | Immutable snapshots, historik, identiteter, tidskontrakter og selektiv genhentning | API-historik hentes som hele svar; ikke en ægte delta-API |
| Daglig app | Holdimport, lokal profil, billeder, spillerprojektioner og sammenligning | Meget funktionalitet, men datastatus og forskellige rapportforløb er ikke samlet |
| Standard | Komponentbaseret Monte Carlo med minutter, point og fallback | `standard_forecast_settings()` vælger baseline **uden odds** |
| Forsøg | Defensive/offensive odds, rolleminutter, bonus, tidligere sæsonprior og assistkorrektion | Separate forsøg; ingen samlet dokumentation for, at alle forbedrer standarden |
| Optimering | Transfersekvenser over 1–4 GWs, budget/FT, manuelle chips og autosubs | Kandidattrupper søges med en tilnærmet målfunktion; ingen garanti for global autosub-optimal transferplan |
| Opstilling | Eksakt søgning over lovlige opstillinger for en fast kandidattrup med de gemte scenarier | Anbefaling rangeres efter raffineret planlægningsværdi; uafhængige evalueringsscenarier bruges til rapportering |
| Evaluering | Kronologisk retrospektiv evaluering og evaluering af visse gemte prognoser | Daglige `transfer_forecasts` indgår ikke i det nuværende “Efter runden”-katalog |
| Offentlig drift | Gæstesessioner, begrænsninger og publicering af verificeret fælles data | Færdig drift, holdbar profilopbevaring og lancering er ikke leveret |

Den faktiske baseline findes i `models/baseline.py` og `simulation.py`. Filer som `models/minutes.py`, `attack.py`, `defcon.py` og `team_goals.py` er fortsat scaffold og bør ikke beskrives som færdige separate modeller.

### Hvad de gemte evalueringer siger

`artifacts/prototype/20261015T101157426725Z_be9810be/report.json`: 2.372 observationer, 593 spillere, GW3–6. Retrospektive resultater med begrænset dokumentation for historisk datatilgængelighed:

| Mål | Baseline | Simpel reference |
|---|---:|---:|
| Point-MAE | 1,361 | 1,291 |
| Point-RMSE | 2,187 | 2,391 |
| Minut-MAE | 18,14 | 12,17 |
| Minut-RMSE | 23,87 | 23,38 |

Baseline vinder altså ikke på alle mål. Minutter er et konkret forbedringsområde. Rollemodellen har tidligere forbedret minutfejl samlet, men haft problemer i enkelte grupper; en universel svækkelse af frekvensprioren havde også negative effekter blandt regelmæssige spillere. Se `notes/role_minutes.md` og `notes/frequency_prior_experiment.md`.

`artifacts/forecast_reviews/20261015T075110326994Z_5b503544/report.json`: den gemte GW6-sammenligning viser point-MAE 1,132 → 1,123 og RMSE 2,090 → 2,083 med **defensive** odds. Det er én runde og en legacy-rapport med deklareret før-deadline-provenance; scenarier mangler, så CRPS kan ikke beregnes. Det dokumenterer hverken sikker forbedring eller effekten af offensive odds.

Alle allerede undersøgte runder er udviklings-/diagnostikdata. Flere seeds måler simulationsvariation, ikke uafhængig evidens på tværs af kampe.

## Hvor kan produktet give edge?

FPL tilbyder allerede form, kommende modstandere/FDR, ejerskab og prisinformation; endnu en statistikside er ikke i sig selv en fordel. Kilde: [FPLs beskrivelse af holdvisninger](https://www.premierleague.com/en/news/4680259/whats-new-in-202627-fantasy-more-ways-to-view-your-squad).

Vores mulige bidrag er at omsætte oplysningerne til en beslutning for **netop brugerens trup**:

- Forventet spilletid og kampspecifikke målforventninger frem for seneste pointsum alene.
- Marginal gevinst ved en transferpakke relativt til at beholde holdet, inklusive anfører, bænk, pris og pointfradrag.
- Værdien af autosubs ved risiko for DNP, sammenholdt med risikoen for et kort indhop.
- Hvor følsom anbefalingen er over for startchance, tilbagevenden og odds-fallback.
- Efterkontrol af, om antagelserne og beslutningsreglen virker over flere runder.

Lavt ejerskab giver ikke i sig selv højere forventede point. En senere miniligastrategi kan ændre risikomålet, men standardmålet bør fortsat være forventede nettopoint. Odds er et informationsinput, ikke bevis for, at vi slår markedet eller andre managers.

## Leverance 1 — Én pålidelig ugentlig arbejdsgang

**Brugerresultat:** Åbn hold → se datastatus → opdatér efter behov → vælg horisont/rammer → få forslag. Tidligere resultater er stadig læsbare.

**Filer:** `src/fpl_model/readiness.py`, `ui/my_team.py`, `ui/decision_summary.py`, `ui/player_detail.py`; tests i `tests/test_operational_readiness.py`, `test_guided_team_flow.py`, `test_player_detail.py`.

- [x] Tilføj regressioner for læsning af gemt prognose uden kommende deadline, manglende spillerhistorik og karantænerækker. Kritiske fejl som fremtidig kilde, ukendt deadline og brudt identitet forhindrer fortsat en ugyldig ny prognose.
- [x] Skeln mellem adgang til en gemt rapport og mulighed for ny beregning. Endelig udfaldsevaluering er et særskilt forløb; de daglige transfer-rapporter kobles på i leverance 3.
- [x] Tillad kun nye delvist dækkede beregninger efter udtrykkeligt tilvalg med markeret fallback og gemte begrænsninger. Genbrug ikke ældre input i smug.
- [x] Vis hentetid for priser/status og historik, deadline, rapportens beregningstid og om odds er valgt. Tekniske ID'er ligger i detaljer; baseline er standard.
- [x] Kør de relevante tests og kontrollér forløbet i browseren med eksisterende lokale data.

**Færdig når:** En ny bruger kan finde sit hold, se om resultatet er aktuelt, beregne eller forstå præcis hvorfor ikke — uden at kende snapshot-kontrakten. Gemte resultater vises med deres oprindelige tidspunkter.

## Leverance 2 — Forklar beslutningen, ikke kun spillerens xP

**Brugerresultat:** Hvert forslag besvarer “Hvorfor denne pakke?”, “Hvorfor denne XI?” og “Hvad kan ændre valget?”.

**Filer:** `ui/player_detail.py`, `ui/decision_summary.py`, `ui/strategy.py`, `sequence_planner.py`; genbrug `optimizer/lineup.py`. Tests i `test_player_detail.py`, `test_sequence_planner.py`, `test_lineup_optimization.py`.

- [x] Bind spillerkortet til samme gemte prognosecache som forslaget. Ved manglende cache bruges kun rapportens gemte spilleroversigt. App-regressioner dækker skift af horisont, en indkøbt spiller og uændret gemt hold uden ny simulation.
- [x] Vis transferpakke versus behold: nettopoint pr. GW/horisont, bank, hits, FT efter planen og afvejningen mellem spillerne. Vis planlægningsmålværdi og simuleret holdresultat som forskellige størrelser.
- [x] Genbrug komponenter, minutter, start-/indhop-/DNP-sandsynligheder og historik fra spillerforklaringen. Afstem holdpoint til XI, bænk/Bench Boost, anfører/vice og hits under den faste plan. Spillerbidrag er forskellen mellem hele planer, ikke isolerede kausale transfereffekter.
- [x] Genbrug parrede scenarier til spredning i gevinst og andel scenarier, hvor forslaget slår behold. Mærk dette som betinget af modellen. De eksisterende gemte returscenarier vises særskilt som følsomhed, ikke ny information.
- [x] Kør lineup-, transfer-, sekvens- og Streamlit AppTest-regressioner, inklusive usikker angriber versus sikker forsvarer og budgetbundne transferpakker.

**Færdig når:** Brugeren kan forklare anbefalingens to vigtigste drivere og dens vigtigste forbehold. Appen kalder ikke en lille beregnet gevinst “sikker”, og solver-gap beskrives kun for det problem, solver faktisk løser.

## Leverance 3 — Knyt daglig brug til “Efter runden”

**Brugerresultat:** De prognoser og forslag, man faktisk brugte, dukker automatisk op til efterkontrol, når endelige labels findes.

**Filer:** `transfer_planner.py`, `forecast_review.py`, `ui/forecast_review.py`, `prediction_evaluation.py`; tests i `test_forecast_review.py`, `test_transfer_planner.py`. Udvid eksisterende rapportkontrakt frem for et nyt audit-system.

- [x] Tilføj en læser til de daglige `transfer_forecasts` og en fælles katalogfunktion, så UI og evaluator finder samme rapporter. Medtag senere øvrige eksisterende prognoseformater gennem samme interface.
- [x] Gem/henvis til dataversion, model/config, forecast-tid, seed, scenarier og den sammenlignede behold-plan. Test at senere snapshots ikke ændrer input, og at manglende legacy-scenarier giver “CRPS ikke tilgængelig”, ikke et rekonstrueret tal.
- [x] Vis point-MAE/RMSE/CRPS, minut-bias/MAE, DNP-Brier og relevante gruppeopdelinger mod den simple reference på samme rækker. Hold aktive/ufærdige kampe adskilt fra endelige udfald.
- [x] Evaluér gemt forslag mod gemt behold-plan på realiserede udfald, når hele sammenligningen kan scores. Brug en på forhånd fastlagt regel for referenceprognosen pr. GW, eksempelvis sidste vellykkede kørsel før det valgte operationelle cutoff. Ingen efterfølgende udvælgelse af den bedste kørsel.
- [x] Kør de nævnte tests og åbn en eksisterende daglig prognose i “Efter runden”. Ingen ny simulation for at genskabe en angivelig gammel prognose.

**Færdig når:** Et forslag kan følges fra input til prognose til udfald. Ingen automatisk tuning; rapporten skal gøre en vurdering mulig. Start fremtidig dokumenteret evaluering nu, uden at gøre den til en blokering for øvrig udvikling.

**Verificeret 7. november 2026:** 923 offline-tests bestået, 5 live-tests fravalgt. Den oprindelige GW8–11-rapport er efterkontrolleret uden nye simulationer/downloads og vist gennem Streamlit AppTest. GW8: forslag 35 / behold 34; GW9: 40 / 39; GW10–11 afventer i udfaldssnapshottet fra 6. november. 593 fælles evalueringsrækker pr. afsluttet GW. Uafhængigt review gav tre konkrete rettelser med regressionstests: DGW-reference, kort uden minutter og ændret fixture-univers. Se `notes/daily_forecast_review.md`.

## Leverance 4 — Forbedr prognosen med én ændring ad gangen

**Brugerresultat:** Standardmodellen ændres kun med en forståelig begrundelse. Brugeren behøver ikke vælge mellem en voksende liste af forsøg.

**4A: Udnyt det allerede implementerede oddsarbejde.** Lad eksisterende angreb+forsvar-odds være én navngiven udfordrer i fremtidige gemte sammenligninger mod baseline. Samme data, seedstrategi og evalueringsrækker; ingen ny oddsmodel. Rapportér både dækkede kampe og fallback, og kontrollér, at eget hold ikke får styrkejustering to gange. Ingen automatisk aktivering i “Mit hold”.

**4B: Prioritér derefter spilletid som isoleret modelændring.** Genbrug erfaringerne fra rollemodellen. Adskil tilgængelighed, start givet tilgængelighed og minutter givet start/indhop. Afklar risikoen for at både historiske fravær og dagens skadesfaktor sænker samme spiller. Hold ukendte årsager ukendte; en kamp i Europa dokumenterer ikke spillerens deltagelse.

**Filer:** `ui/forecast_controls.py`, `attacking_odds.py`, `models/baseline.py`, `role_minutes.py`, `availability.py` og eksisterende sammenligningsmoduler. Relevante eksisterende tests samt målrettede nye regressioner for den valgte ændring.

- [ ] Fastlæg før hvert forsøg: én hypotese, uændrede komponenter, udviklingsrunder, fremtidige vurderingsrunder, primært mål og kriterier for acceptabel forværring i undergrupper. Genbrug evalueringsforløbet fra leverance 3.
- [ ] Mål hele puljen, faste startere, rotation og reserver samt brugerens ejede/kandidatspillere defineret **før** udfald. En bedre samlet minut-MAE er utilstrækkelig, hvis pointfordelingen bliver dårligere for relevante beslutninger.
- [ ] Bevar kort historik/fallback og tidskontrakter. Nyheder bliver i første omgang dateret evidens med kilde og manuelle scenarier; ingen udokumenteret omregning af fritekst til præcise skadesprocenter.
- [ ] Udfør én afgrænset sammenligning ad gangen, med tests for uændrede øvrige komponenter og fremtidslækage. Beslut behold/forkast/fortsæt som forsøg. Kombinér først forbedringer, når deres samspil kan vurderes.

**Færdig når:** Vi kan sige præcis, hvad en kandidat forbedrer, hvem den skader, og hvor meget evidens der er. Ny standard kræver eksplicit beslutning, ikke bare laveste fejl blandt mange gennemprøvede varianter.

## Leverance 5 — Strategi med en realistisk lang horisont

**Brugerresultat:** En konkret plan for de nærmeste 1–4 GWs plus et strategisk overblik til GW19. Den fjerne del fremstår som usikker og genberegnes løbende.

**Filer:** `sequence_planner.py`, `optimizer/transfer_sequences.py`, `chips.py`, `ui/strategy.py`; tests i `test_sequence_planner.py`, `test_transfer_sequences.py`, `test_chip_sequences.py`.

- [ ] Bevar den eksisterende korte transferoptimering. Vis kampprogram, blanke/dobbelte runder og chipfrister længere frem, inklusive usikkerheder i planlagt kampplacering. Kontrollér reglerne for den aktuelle sæson ved implementering.
- [ ] Sammenlign chip nu med udvalgte senere muligheder. Gør det tydeligt, når en kort horisont udelader mulige fremtidige chipgevinster.
- [ ] Synliggør resterende FT og horisontens slutbias. Afprøv en eksplicit følsomhed for værdien af en opsparet transfer før en mere kompleks stokastisk strategi; denne værdi må ikke præsenteres som observeret sandhed.
- [ ] Test budget, FT, lovlighed og chiprestaurering på tværs af horisonter. Fremtidige priser og tilgængelighed forbliver tydelige antagelser.

**Færdig når:** Brugeren kan vælge mellem handle/vente/chip med synlige afvejninger. Appen påstår ikke at kende fremtidige skader eller fuldt optimere værdien af ny information.

## Leverance 6 — Lille offentlig beta

**Brugerresultat:** En ny bruger kan importere sit hold, få et forslag og vende tilbage uden lokal opsætning eller adgang til andres data.

**Filer:** Genbrug `public_data.py`, `ui/guest_state.py`, `ui/guest_limits.py`, `ui/team_import.py` og de eksisterende jobforløb. Separat, kort driftsplan før valg af hosting og profilopbevaring.

- [ ] Lad nogle få nye brugere gennemføre import → bank/FT/chips → forslag → spillerforklaring → genåbn hold. Registrér konkrete misforståelser, stopsteder og ventetid; ret dem før nye funktioner.
- [ ] Planlæg fælles serveropdatering og genbrug af prognoser, begræns beregningsjob, og vis kø/fremdrift. Hold API-nøgler på serveren. Genbrug eksisterende publicering af verificerede data.
- [ ] Vælg persistent profilopbevaring og brugeridentitet efter betabehov. Test to brugere samtidigt, genstart, slettet profil og fejlet opdatering uden krydsning af private data.
- [ ] Kontrollér brugsvilkår for data og billedaktiver før offentlig distribution. Dokumentér driftsansvar, dataalder og håndtering af afbrudte jobs.

**Færdig når:** Forløbet virker uden udviklerhjælp, gemte hold overlever den valgte drift, og fælles beregninger ikke lækker private hold. Vercel/Supabase eller en ny frontend vælges kun, hvis et konkret behov kræver det.

## Dokumentation indbygget i alle leverancer

1. **På beslutningen:** gevinst, datatidspunkt, to vigtigste grunde og ét væsentligt forbehold.
2. **På spilleren:** faktisk historik, start/indhop/DNP, betingede minutter, xG/xA-rate, justeringer, komponentpoint og fallback — med tal fra den viste kørsel.
3. **Under “Modellen”:** estimand, fordelinger, priors, afhængigheder, odds-tilpasning, optimeringsmål, tidskontrakter og aktuelle evalueringsresultater. Eksempelvis `E[min] = P(start)·E[min|start] + P(indhop)·E[min|indhop]`; usikkerhed om modellen holdes adskilt fra variation i simulerede kampudfald.

Opdatér den aktuelle vejledning i `README.md` og `ui/model_guide.py` sammen med den relevante leverance. Bevar daterede forsøgsnoter som historik. Nye modelkomponenter skal have én kort modelbeskrivelse med antagelser, fallback og dokumentation for resultater; ikke et nyt stort dokumentationssystem.

## Anbefalet første afgrænsning og fravalg

Start med **leverance 1 og 2**, uden modelændringer eller downloads som standard. Dernæst leverance 3, så de daglige anbefalinger kan vurderes. Leverance 4 skal bygge på dette; offentliggørelse kommer efter et forståeligt og stabilt lokalt forløb.

Udskyd nye store datakilder, automatisk nyhedsscraping, bred ML-/parametersøgning, fuld BPS-rekonstruktion, dommer/vejr-modeller og miniligaspecifik risikooptimering. De har ingen dokumenteret højere prioritet end de identificerede problemer.

Planen blev oprettet uden modelændringer. Leverance 1 har efterfølgende ændret status- og appforløbet, mens standardmodel, rådata og genererede resultater er bevaret. Senere leverancer kræver særskilt verifikation.

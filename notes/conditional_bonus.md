# Præstationsafhængig bonus – ét afgrænset eksperiment

Baseline og den eksisterende angrebsoddsmodel er uændrede. Under **Mit hold → Prognosemodel** kan baseline eller **Odds til angreb og forsvar · William Hill** få fluebenet **Eksperiment: præstationsafhængig bonus**. Det er fravalgt som standard og kombineres ikke med rolle-/dødboldseksperimenterne. Modelversionen får `__conditional_bonus_v1`.

Kun bonus ændres. Træning, optimering og UI er adskilt; appen henter ikke data. Prognosecachen inkluderer konfiguration, input og kodehash, og bonusmodellen gemmes med koefficienter og træningsreferencer. Separate planlægnings-/evalueringsscenarier og de eksisterende transferregler genbruges.

## Model

En binomial GLM estimerer forventet bonus blandt spillere med minutter > 0:

`E[bonus | præstation, spillet] = 3 × logistic(Xβ)`

X indeholder intercept, minutter/90, mål og assists (afklippet til 3 hver), clean sheet for GK/DEF med mindst 60 minutter, opnået defensivt bidrag samt position. Mål-/assistpoint konverteres til antal hændelser med de eksisterende positionsregler. Modellen trænes på **faktiske hændelser i tidligere kampe** og anvendes på **simulerede hændelser i forecast-kampen**. Forecast-kampens faktiske mål, bonus, BPS og totalpoint kan ikke komme ind som input.

Bonus trækkes som Binomial(3, E[bonus]/3), altså 0–3 heltal. DNP giver præcis nul. Indhoppere er med i træningen og er ikke kunstigt låst til nul bonus. Måltid/clean-sheet-regler kommer fra den eksisterende simulation. En separat RNG `SeedSequence([seed, fixture_id, player_id, 57721])` bevarer minutter og alle ikke-bonuskomponenter. Ingen ny målrateskalering, assistdefinition eller skadesfaktor.

Ridge-styrke 1, mindst 100 gyldige spillede rækker og fem rækker med bonus er faste, ikke optimerede valg. Intercept straffes ikke. Effekterne af minutter, mål, assists, clean sheet og defensive bidrag begrænses til at være ikke-negative, alt andet lige. Utilstrækkelig træning eller manglende numerisk konvergens giver eksplicit, uændret baseline-bonus. Ukendte/manglende felter bliver aldrig nul; afvisningsantal gemmes. Dublerede eligible spiller/kamp-rækker afvises i stedet for at blive vægtet dobbelt.

Dette er **ikke** en BPS-simulator. Bonuskonkurrencen mellem holdkammerater/modstandere og det samlede bonusbudget pr. kamp håndhæves ikke. Binomialfordelingen er en ukalibreret marginal tilnærmelse. Sparsom historik, keeperredninger, kort, afleveringer og individuelle BPS-egenskaber er fortsatte begrænsninger; modellen bruger ingen individuelle spillerintercepts. En lavere prognose er ikke bevis for, at den gamle var forkert.

## Tid og evaluering

Live: kun endelige officielle rækker fra tidligere events, med kickoff før origin og `available_at <= origin`. Ingen tidligere sæsoner hentes eller tilføjes. Træningsgrundlag gemmes inklusive player/fixture/observation/snapshot-ID, værdier, observationstid og hash.

Retrospektiv diagnostik: genestimering før hver GW på tidligere GWs/kickoffs; senere hentede labels tillades eksplicit og kaldes derfor ikke prospektiv validering. Ingen aktuelle odds eller slutaggregater bruges historisk. Træningspuljen bestemmes før filtrering på tilgængelige targets. Positioner og spillerpulje er dog fra det aktuelle snapshot, med den samme dokumenterede dæknings-/survivorshipbegrænsning som eksisterende evaluering.

Samme evalueringsrækker, seed + GW og simulationsantal for baseline og kandidat. Simpelt tidligere point-/bonusgennemsnit bevares som reference. Bonusbias/MAE/RMSE og point-MAE/RMSE/CRPS vises samlet, pr. position, GW og for regelmæssig tidligere spilletid (den eksisterende præ-forecast-definition). Ingen parametersøgning eller automatisk udskiftning af standardmodellen.

## Reproducerbar kørsel, uden downloads

```bash
.venv/bin/python scripts/compare_bonus.py \
  --snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --context-snapshot data/raw/2026-10-12_051541027780Z_e7171f9555904b94908001be74937c16 \
  --odds-snapshot data/raw/2026-10-09_044610511257Z_bb08becd841f43c0ab0aa492560237b9 \
  --draws 3000 --seed 42
```

Udelad de to sidste snapshotargumenter for kun retrospektiv diagnostik. Med dem gemmes også næste fremtidige officielle GW: eksisterende angrebsoddsvariant og den samme variant med ny bonus. Begge gemmes med arrays til senere efterkontrol. Hver kørsel skriver nye mapper under `artifacts/conditional_bonus/`. Gamle snapshots/prognoser ændres ikke.

I **Analyse og eksperimenter → Bonus · præstationsafhængigt eksperiment** genindlæses rapporter, datatidspunkter, koefficienter, pointkomponenter og ændrede prognoser uden ny træning/simulation.

## Faktisk kørsel 13. oktober 2026

GW3–5 er allerede anvendte **udviklingsdata**: 1.779 observationer / 593 spillere, 3.000 scenarier, seed 42 + GW. Træning før GW3/4/5: 622/929/1.236 spillede kamprækker, heraf 203/298/408 under 60 minutter.

| Model | Bonus-MAE | Bonus-RMSE | Point-MAE | Point-RMSE | CRPS |
|---|---:|---:|---:|---:|---:|
| Baseline | 0,1996 | 0,4691 | 1,3734 | 2,1895 | 0,8099 |
| Ny bonus | 0,1914 | 0,4679 | 1,3716 | 2,1948 | 0,8062 |
| Tidligere gennemsnit | 0,1714 | 0,5251 | 1,2980 | 2,4206 | — |

Regelmæssige spillere (536 rækker): bonus-MAE 0,4606 → 0,4490, men point-MAE 2,5442 → 2,5463 og RMSE 3,3804 → 3,3901. Angribere får dårligere bonus-MAE (0,2347 → 0,2775); keepere og forsvarere får lavere bonus-MAE. Små, blandede forskelle; ingen påstand om statistisk sikker forbedring og ingen yderligere tuning/seeds. **Behold baseline som standard.**

GW7-prognosen bruger 10/10 allerede dækkede William Hill-kampe, samme 3.000 scenarier/seed 42, og trænes på 1.538 spillede rækker fra GW1–5 (499 under 60 minutter). Odds/spillerhistorik er stadig fra 9. oktober, kampkontekst fra 12. oktober. Reference-oddsprognosens point- og minutarrays er bit-identiske med den tidligere gemte kørsel. Haaland 7,663 → 7,951 xP; Saka 5,738 → 5,859; Groß 5,031 → 4,452. Alt skyldes bonus. Ingen faktisk accuracy-evaluering af GW7 endnu.

Lokale resultater:

- `artifacts/conditional_bonus/development/20261013T134259095079Z_ef127758/report.json`
- `artifacts/conditional_bonus/forecasts/20261013T134301362754Z_e59d6f1d/`

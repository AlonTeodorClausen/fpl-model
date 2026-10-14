# FPL-assistkorrektion — separat, fravalgt eksperiment

Tilvalget **Eksperiment: FPL-assistkorrektion** findes under **Mit hold → Planlæg transfers → Prognosemodel** for Baseline og Odds til angreb og forsvar. Det kan ikke kombineres med sæsonprior, præstationsbonus, dødbolde eller rollemodeller. `component_baseline_v1` og alle standardparametre er uændrede. Resultater findes under **Analyse og eksperimenter → FPL-assists · xA-korrektion**.

## Hvorfor undersøge det?

FPL-assists kan tildeles for returer, fremtvungne selvmål og vundne straffespark/direkte frispark, ud over almindelige målgivende afleveringer. Se [Premier Leagues officielle forklaring](https://www.premierleague.com/en/news/2174909), kontrolleret 13. oktober 2026. xA er derfor ikke i sig selv forventede FPL-assists.

Vores gemte aktuelle spillerpulje har i færdige GW1–5-rækker med positive minutter **130 FPL-assists og 92,27 xA**. Forskellen kan ikke opdeles i definitionsforskel, afslutningsheld og stikprøvestøj med disse data. Vi har ikke hændelseslabels for returer, vundne straffespark eller traditionelle assists. Eksperimentet er derfor **en empirisk ratekorrektion**, ikke en implementering af reglerne på konkrete kampbegivenheder. Det beviser heller ikke, at grundmodellen undervurderer assists: den har allerede priors, spilletid og kampjusteringer.

## Fast model, ingen tuning

En fælles faktor beregnes fra matchede spiller-kamp-rækker:

```
faktor = (sum tidligere FPL-assists + 20) / (sum tidligere xA + 20)
korrigeret assist-rate = eksisterende udglattet xA-rate × faktor
```

`AssistConfig(prior_xa=20, min_rows=100, min_xa=5)` er et fast udgangspunkt. De 20 xA-enheder svarer til udglatning mod faktor 1; det er ikke 20 kampe. Der kræves mindst 100 gyldige spillede rækker og 5 xA i summen. Ellers bruges præcis uændret baseline med eksplicit fallback. Faktoren kan ligge under 1; vi antager ikke automatisk en positiv korrektion. Manglende/ugyldig xA betyder, at både xA og assists fra rækken udelades. Et observeret nul beholdes. DNP-rækker estimerer ikke spillede rater.

Kun tidligere **final**, officielle FPL-rækker fra tidligere GWs og kickoff før forecast må indgå. Live kræves også `available_at <= forecast_origin_at`; senere snapshots må ikke påvirke faktoren. Dublerede spiller-fixture-observationer afvises. Normaliserede player IDs er kanoniske, og ingen navnematching foretages. Faktorens træningspulje bestemmes før udvælgelse af evaluerbare targets, så en manglende target ikke ændrer træningen.

Faktor, konfiguration, rå summer, GW-dækning, afviste rækker, observation-/snapshot-ID, tider og hash gemmes. Rå kildereferencer følger den eksisterende forecastkontrakt. Retrospektiv evaluering tillader senere hentede tidligere labels eksplicit; tilgængeligheden ved gamle deadlines er ikke bevist. Der anvendes ikke nye odds i historiske forecasts, og alle øvrige evalueringsrækker/seedvalg er identiske med baseline.

## Effekt i simulationen

Uden odds erstattes kun assist-Poisson-raten. Baseline-RNG forbruges uændret, og assistkorrektionen får en separat strøm med `[seed, fixture_id, player_id, 73519]`. Med angrebsodds genbruges den eksisterende angrebsstrøm og normalisering. Alle assistvægte ganges med samme faktor: relative assistandele ændres ikke, men holdets forventede assistandel kan stige. Den eksisterende grænse `min(1, total_xA / total_xG)` bevares, så **forventede** holdassists ikke overstiger holdets målmiddel. Det er ikke en fælles hændelsessimulation; enkelte scenarier kan stadig have flere assists end mål.

Faktoren anvendes én gang, før oddsnormaliseringen. Holdets målbudget, målfordeling, minutter, skader, bonus, defensive og øvrige point er identiske ved samme seed. Testene og den faktiske sammenligning afstemmer total xP-forskel til assistpoint alene. Ingen ekstra målrateskalering eller kombination med andre eksperimenter.

Spillere uden individuel xA-historik får fortsat det markerede positionsprior; den fælles faktor påvirker også dette proxy. Modellen ved ikke, hvilke spillere der typisk vinder straffespark eller skaber returer. Træningspuljen er nuværende FPL-spillere; manglende/tidligere udgåede spillere og få GWs giver fortsat dækningsbegrænsning.

## Reproducerbar kørsel uden downloads

```bash
.venv/bin/python scripts/compare_assists.py \
  --snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --context-snapshot data/raw/2026-10-12_051541027780Z_e7171f9555904b94908001be74937c16 \
  --odds-snapshot data/raw/2026-10-09_044610511257Z_bb08becd841f43c0ab0aa492560237b9 \
  --draws 3000 --seed 42
```

Udelad context/odds-argumenterne for kun retrospektiv diagnostik. Nye rapportmapper oprettes; rådata og tidligere resultater ændres ikke. Ingen AI-kald eller app-udløste downloads.

## Faktiske resultater, 13. oktober 2026

1.779 observationer, 593 spillere, GW3–5, 3.000 scenarier, seed 42 + GW. Disse runder er allerede brugte **udviklingsdata**, ikke uafhængig validering. Før GW3/4/5 er faktorerne 1,3462 / 1,3072 / 1,3397, trænet på 622 / 929 / 1.236 spillede rækker.

| Model | Assist-bias | Assist-MAE | Assist-RMSE | Point-MAE | Point-RMSE | CRPS |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 0,0010 | 0,0737 | 0,2095 | 1,3734 | 2,1895 | 0,8099 |
| Assistkorrektion | 0,0145 | 0,0852 | 0,2107 | 1,3904 | 2,1923 | 0,8116 |
| Tidligere gennemsnit | 0,0054 | 0,0709 | 0,2382 | 1,2980 | 2,4206 | — |

Assistfejl er antal assists, pointfejl er FPL-point. Positiv bias er overvurdering. Blandt regelmæssige spillere (536 rækker) forbedres assist-bias fra −0,0252 til +0,0007, men assist-MAE stiger 0,1663 → 0,1864, og point-MAE stiger 2,5442 → 2,5665. Andre spillere får større assist-overvurdering (0,0123 → 0,0204). Mindre bias er altså ikke automatisk mindre individuel fejl.

**Anbefaling: behold baseline og lad korrektionen være fravalgt.** Denne fælles multiplikator forbedrer ikke den nuværende baseline på de målte udviklingsrækker. Der er ikke udført parametersøgning eller ekstra seeds. Resultatet afgør ikke, om en fremtidig model med konkrete hændelses-/rolledata kunne hjælpe.

GW7: faktor 1,3361 fra 1.538 tidligere spillede rækker, samme 3.000 scenarier/seed 42 og 10/10 allerede dækkede William Hill-kampe. Eksempler, angrebsoddsreference → assistvariant:

- Ødegaard: 4,684 → 4,920 xP (+0,236).
- Tavernier: 5,441 → 5,677 (+0,236).
- Rogers: 4,399 → 4,609 (+0,210).

Dette er **prognoseforskelle**, ikke bedre dokumenteret præcision. Spillerdata og odds er fra 9. oktober, kampkontekst fra 12. oktober; prognosen er gemt 13. oktober. Referenceprognosens point-/minutarrays er bit-identiske med den tidligere gemte angrebsoddsreference fra sæsonprior-forsøget.

Lokale resultater:

- `artifacts/assist_correction/development/20261013T183320485714Z_9f85abfe/report.json`
- `artifacts/assist_correction/forecasts/20261013T183322842486Z_b8bcbd21/`

Alle resultater og rå captures forbliver gitignored. Default-test: 775 bestået, 5 live-tests fravalgt.

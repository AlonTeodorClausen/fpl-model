# Tre frekvenspriorer — afgrænset udviklingseksperiment

Samme immutable snapshot `4fee7b0047014ffba28b416e9b9928ce`, samme 1.779 spiller-GW-rækker / 593 spillere i GW3–5 som den eksisterende kørsel `20260924T164629668707Z_0c22d357`. To tusind scenarier pr. GW; seeds 42, 43, 44 med den eksisterende `seed + GW`-strategi. **GW3–5 er udviklingsdata, ikke en uafhængig test.** Alle andre antagelser, inklusive frekvenspriorernes gennemsnit 45 % start / 10 % indhop / 45 % DNP, fastholdes.

`frequency_prior_games` styrer kun udglatningen af start/indhop/DNP. `minutes_prior_games` styrer kun minutter betinget på start/indhop og fastholdes på 1,0. `component_baseline_v1` med standardkonfigurationen reproducerer eksisterende evalueringsrækker præcist. Fallback og manglende-data-regler er bevaret. Kandidaterne anvendes kun i det eksplicitte eksperiment; ingen automatisk modeludskiftning.

## Samlet, primært seed 42

| Variant | Minut-bias | Minut-MAE | Minut-RMSE | DNP-Brier | DNP forudsagt / observeret | Point-MAE | Point-RMSE | CRPS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1: 1,0 | +3,310 | 18,222 | 23,395 | 0,11097 | 49,03 % / 53,96 % | 1,376 | 2,191 | 0,81040 |
| 0,25 | +2,123 | 13,986 | 22,446 | 0,10870 | 49,93 % / 53,96 % | 1,269 | 2,172 | 0,80655 |
| 0,10 | +1,800 | 12,916 | 22,487 | 0,11021 | 50,19 % / 53,96 % | 1,242 | 2,174 | 0,81072 |
| Historisk gennemsnit | +1,786 | 11,471 | 22,511 | 0,11201 | 50,37 % / 53,96 % | 1,298 | 2,421 | 1,29801* |

\* Referencens punktforecast behandles som en degenereret fordeling; CRPS er da MAE. Det er ikke en kalibreret probabilistisk reference. Reference-DNP kommer som hidtil fra tidligere observeret DNP-frekvens.

## Regelmæssige spillere: samlet gevinst har en bagside

Den tidligere definition fastholdes: mindst to tidligere kampe, gennemsnit ≥60 minutter og deltagelse i ≥75 % af tidligere kampe. 536 observationer / 203 unikke spillere. Alle grupper bestemmes før den pågældende forecast ud fra tidligere rækker; senere hentede revisioner er stadig en retrospektiv provenancebegrænsning.

| Variant | Minut-bias | Minut-MAE | Minut-RMSE | DNP-Brier | Point-MAE | Point-RMSE | CRPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | −4,421 | 21,464 | 27,222 | 0,0809 | 2,551 | 3,386 | 1,744 |
| 0,25 | +2,986 | 17,539 | 26,758 | 0,0799 | 2,639 | 3,383 | 1,763 |
| 0,10 | +4,983 | 16,713 | 27,021 | 0,0818 | 2,666 | 3,392 | 1,777 |
| Reference | +8,608 | 14,528 | 27,453 | 0,0840 | 2,897 | 3,807 | 2,897* |

0,25 reducerer minutfejl, men øger point-MAE med ca. 3,4 % og CRPS med ca. 1,1 % i den regelmæssige gruppe. 0,10 giver større forværring og vender minut-bias til en større overvurdering end v1's undervurdering. Det er relevant for holdvalg og må ikke skjules af resultaterne for hele puljen.

Ingen tidligere starter: 994 observationer. Minut-bias går fra +7,67 til +1,32 (0,25) og −0,40 (0,10); MAE fra 12,85 til 7,46 og 6,04. Samlede gevinster kommer især herfra. Reference-MAE er stadig 4,84.

Alle mål, antal og reference er gemt pr. position, GW, tidligere startfrekvens/minutgruppe, regelmæssige pr. position og position × startergruppe. På GW5 forværrer begge kandidater DNP-Brier og CRPS ved seed 42. For forsvarere forværrer begge CRPS. Dette er ikke en ensartet forbedring på tværs af segmenter.

## Simulationsstøj og anbefaling

Over tre seeds er 0,10 minus 0,25 i samlet CRPS **+0,00404 til +0,00417**, DNP-Brier **+0,00151 til +0,00177** og minut-RMSE **+0,04062 til +0,06437**. 0,25's fordel på disse mål skifter ikke fortegn over de få seeds, mens 0,10 har lavere MAE. Forskellene er små; seeds siger intet om usikkerheden ved kun tre GWs.

For regelmæssige spillere bliver 0,25's CRPS **0,01877–0,02700 dårligere** end v1 over seeds; minut-RMSE bliver **0,38081–0,46339 bedre**. Point-RMSE-differencen skifter fortegn (−0,00327 til +0,00849), så den kan ikke beskrives som en stabil gevinst her. 0,10's CRPS-forværring er større: +0,03275–0,03712.

**Anbefaling:** 0,25 er den mest lovende kandidat til videre afprøvning på senere, hidtil ubrugte GWs. Behold v1 som standard nu. Følg især regelmæssige spilleres pointfordelinger; bedre minutter alene beviser ikke bedre prognoser. Ingen bred tuning eller statistisk sikker forbedring påstås.

## Næste større modeludvidelse

Odds som alternativ eller supplement til holdets målmodel, med bookmaker-margin fjernet, tydelig håndtering af manglende markeder og tidsstempler samt en sammenligning med/uden odds. Aktuelle odds må ikke være input til historiske forecasts. Intet af dette er implementeret i dette eksperiment.

## Afsluttet: gennemsnit og spænd over de tre gemte seeds

Ingen nye simulationer er kørt ved afslutningen. Den afledte rapport `20260927T103255952384Z_ef96891a` bevarer alle ni oprindelige kørsler og registrerer kildefilens SHA-256. Gennemsnit [min–maks] er variation mellem seeds, ikke statistisk usikkerhed mellem kampe.

### Alle 1.779 observationer

| Variant | Minut-MAE | Minut-RMSE | Point-MAE | Point-RMSE | DNP-Brier | CRPS |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 1,0 | 18.229 [18.222–18.233] | 23.396 [23.393–23.401] | 1.374 [1.373–1.376] | 2.190 [2.189–2.191] | 0.1110 [0.1110–0.1111] | 0.8099 [0.8096–0.8104] |
| Prior 0,25 | 13.982 [13.977–13.986] | 22.450 [22.439–22.465] | 1.269 [1.268–1.271] | 2.172 [2.171–2.174] | 0.1085 [0.1084–0.1087] | 0.8069 [0.8065–0.8075] |
| Prior 0,10 | 12.928 [12.916–12.944] | 22.503 [22.487–22.519] | 1.242 [1.242–1.242] | 2.174 [2.174–2.175] | 0.1102 [0.1102–0.1102] | 0.8110 [0.8107–0.8116] |
| Reference | 11.471 [11.471–11.471] | 22.511 [22.511–22.511] | 1.298 [1.298–1.298] | 2.421 [2.421–2.421] | 0.1120 [0.1120–0.1120] | 1.2980 [1.2980–1.2980] |

### 536 observationer med regelmæssig tidligere spilletid

| Variant | Minut-MAE | Minut-RMSE | Point-MAE | Point-RMSE | DNP-Brier | CRPS |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 1,0 | 21.445 [21.425–21.464] | 27.207 [27.191–27.222] | 2.548 [2.544–2.551] | 3.383 [3.381–3.386] | 0.0810 [0.0809–0.0811] | 1.7416 [1.7398–1.7438] |
| Prior 0,25 | 17.560 [17.539–17.600] | 26.784 [26.758–26.827] | 2.640 [2.636–2.645] | 3.384 [3.381–3.390] | 0.0800 [0.0799–0.0803] | 1.7645 [1.7626–1.7680] |
| Prior 0,10 | 16.732 [16.713–16.759] | 27.047 [27.021–27.071] | 2.664 [2.662–2.666] | 3.391 [3.390–3.392] | 0.0819 [0.0818–0.0821] | 1.7765 [1.7749–1.7782] |
| Reference | 14.528 [14.528–14.528] | 27.453 [27.453–27.453] | 2.897 [2.897–2.897] | 3.807 [3.807–3.807] | 0.0840 [0.0840–0.0840] | 2.8966 [2.8966–2.8966] |

0,25 er fortsat en kandidat til senere afprøvning, ikke en ny standard. I den regelmæssige gruppe stiger gennemsnitlig point-MAE fra 2,548 til 2,640 og CRPS fra 1,742 til 1,765; 0,10 forværrer dem yderligere. De samlede minutgevinster ophæver ikke denne afvejning.

### Eksisterende odds-adapter: status uden nye downloads

Football-Data.co.uk `fixtures.csv` er en valgfri rå adapter. Den tidligere audit fandt 1X2, over/under 2,5 og asiatisk handicap (bookmakere samt Max/Avg/Betfair Exchange), men adapteren normaliserer ingen markeder og fjerner ikke margin. `available_at = retrieved_at`; CSV har ingen dokumenteret observations-/publikationstid pr. pris, og closing-kolonnerne var tomme i det auditerede snapshot. Der er ingen stabile hold-/kamp-ID’er eller færdig kobling til FPL: eksplicitte navnealiaser og afklaret kickoff-tidszone mangler (kun 15/20 bogstavelige PL-navnematches i Step 2A). Feedet kan indeholde igangværende/afsluttede kampe og manglende markeder. Aktuelle odds må ikke indsættes i historiske forecasts.

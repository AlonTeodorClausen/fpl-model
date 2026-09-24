# Forklaringer og minutdiagnostik — baseline v1

`component_baseline_v1` og alle standardparametre/formler er bevaret. Diagnostikversionen er `explanations_minutes_v1`. Scoring eksponerer komponenter fra de samme simulerede hændelser; deres gennemsnit summerer til spillerens xP, også i DGW/blanke GWs. Ingen nye tilfældige træk bruges til forklaringen. Regressionstesten fastholder fingerprints for point og minutter fra versionen før ændringen.

Spillerforklaringen viser hentet historik og den historik, modellen faktisk anvender. Ved usikker nævner viser den eksplicit aggregate-/prior-fallback; observerede frekvenser fra ufuldstændige rækker er ikke deltagelsesestimater. Manglende starts forbliver ukendte i observationstabellen, selv hvis v1 bruger en 60-minuttersproxy. xG/xA-eksponering medregner kun minutter med kendt felt. Betingede minutparametre er centre før afrunding og afklipning, ikke de faktiske betingede simulationsgennemsnit. Skadesfaktoren skalerer start/indhop; DNP er resten.

## Sammenligningsgrundlag

Diagnostikken kan anvendes direkte på allerede gemte `evaluation.rows` med `minute_diagnostics(rows, data, config)`. Den ændrer ikke forudsigelserne. Appens nye rapporter inkluderer både spillerforklaringer og denne diagnostik. Historiske grupper bruger kun final-rækker med tidligere GW **og** kickoff før forecast-deadline. Usikker historiknævner afvises. Senere observerede rettelser forbliver en retrospektiv begrænsning; dette er ikke et bevis på historisk datatilgængelighed.

- Hele puljen: alle evaluerbare spiller-GW-rækker, ikke alle 667 spillere uanset historik.
- Regelmæssig tidligere spilletid: mindst 2 tidligere kampe, mindst 60 minutter i gennemsnit og spilletid i mindst 75 % af kampene.
- Startergrupper: 0 %; >0 og <75 %; ≥75 %; ukendt ved manglende starts.
- Minutgrupper: 0; (0,30); [30,60); ≥60 tidligere gennemsnitsminutter.
- Bias = forudsagte minus faktiske GW-minutter. Begge metoder evalueres på identiske rækker. En spiller kan skifte gruppe mellem GWs; antal unikke spillere pr. gruppe kan derfor ikke lægges sammen.

## Fund fra det eksisterende 24. september-snapshot

Beregnet på de eksisterende 1.779 evalueringsrækker fra `20260924T164629668707Z_0c22d357`, 593 spillere, GW3–5. Ingen genindsamling eller tuning.

| Tidligere historik | n | Baseline bias / MAE / RMSE | Reference bias / MAE / RMSE |
|---|---:|---:|---:|
| Alle evaluerbare | 1779 | +3,31 / 18,22 / 23,40 | +1,79 / 11,47 / 22,51 |
| Regelmæssig spilletid | 536 | −4,42 / 21,46 / 27,22 | +8,61 / 14,53 / 27,45 |
| Ingen tidligere starter | 994 | +7,67 / 12,85 / 16,44 | −2,06 / 4,84 / 14,23 |
| ≥75 % tidligere starter | 539 | −3,97 / 21,56 / 27,34 | +8,75 / 14,67 / 27,54 |
| Nul tidligere minutter | 712 | +9,12 / 10,60 / 12,28 | −1,07 / 1,07 / 7,95 |

Frekvensprioren på én kamp med 45 % start og 10 % indhop giver aldrig-startede en gennemsnitlig startchance på 11,8 %. Gruppen med ≥75 % tidligere starter har observeret 97,6 %, men modellen giver 83,8 %. Her løftes indhop fra 1,3 % til 3,6 %. Nul-minutgruppen får ca. 10,19 forventede minutter mod faktisk 1,07. Keepere har 0 % historiske indhop, men en modelchance på 2,6 %. Det er strukturel evidens for uhensigtsmæssig fælles udglatning; det isolerer ikke dens kausale andel af alle fejl.

Referencegennemsnittet overvurderer de regelmæssige spilleres faktiske minutter, mens baseline har marginalt bedre RMSE for denne gruppe, men betydeligt dårligere MAE. Kun 2–4 kampe ligger bag hver forecast her. Skader, rolleskift, afklippet normalfordeling og konservativ udvælgelse påvirker også resultatet.

**Én anbefalet næste ændring:** adskil styrken af start-/indhop-frekvensprioren fra prioren for betingede minutter, og afprøv en svagere frekvensprior mod den uændrede v1 på samme rækker. Ingen ny værdi vælges eller implementeres her; en ny tærskel skal testes på et bredere kronologisk grundlag.

## Risiko for dobbelt holdstyrke

Den historiske spiller-xG/xA-rate afspejler allerede eget holds offensive miljø og tidligere modstandere. V1 multiplicerer raten med `(venue-målprior × eget holds angreb × modstanderens forsvar, afklippet) / liga-målbase × attack_scale`. Eget holds angreb kan derfor tælles igen; modstanderjusteringen er heller ikke normaliseret mod spillerens historiske kampmix. Udglatning dæmper, men fjerner ikke risikoen. Dette er en vurdering af formlen, ikke empirisk dokumentation for størrelsen af dobbeltregning. Formlen er uændret.

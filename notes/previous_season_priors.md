# Spillerprior fra sidste sæson — ét isoleret forsøg

`previous_season_attack_prior_v1` er fravalgt som standard. Vælg **Mit hold → Planlæg transfers → Prognosemodel → Eksperiment: spillerprior fra sidste sæson** under Baseline eller Odds til angreb og forsvar. Det kombineres ikke med bonus-, rolle- eller dødboldseksperimenter. Resultater findes under **Analyse og eksperimenter → Spillerprior fra sidste sæson · xG/xA**.

## Afgrænsning og beregning

Genbruger `history_past` fra allerede gemte officielle element-summary-svar. Kun **seneste afsluttede sæson** (2025/26 for den konfigurerede 2026-2027-sæson) anvendes. Ingen nye data, ingen navnematching, ingen fallback til ældre sæsoner. Endpointets aktuelle FPL-player-ID forbindes med den officielle bootstrap-identitet, og `element_code` skal matche bootstrap `code`. Tidligere klub og position er ikke kendt fra dette eksportformat.

For xG og xA hver for sig, med `E = sidste sæsons minutter / 90`:

```
spillerprior = (sidste sæsons sum + 3 × positionsprior) / (E + 3)
aktuel rate = (årets hidtil observerede sum + prior_games × spillerprior)
              / (årets kendte 90-minutseksponering + prior_games)
```

`SeasonPriorConfig.position_prior_90s=3` er et fast udgangspunkt, ikke tunet. `BaselineConfig.prior_games=3` bevarer den eksisterende samlede priorstyrke. En hel tidligere sæson får altså ikke samme vægt som 30–38 nye kampe. Ved meget kort tidligere spilletid ligger spillerprior tættere på positionen; efterhånden overtager den aktuelle sæsons observationer. Ukendt felt giver positions-fallback for netop dét felt; et verificeret numerisk nul er et observeret nul. Nul/manglende sæsonminutter bruges ikke som divisor. Manglende/uklar identitet, kilde eller tid og flere eligible versioner giver eksplicit fallback, ikke et gæt.

Sæsonhistorik er summer, ikke oplysninger om aktuelle start-/indhop-/DNP-chancer. Minutmodellen, skadesfaktorer, bonus og forsvar er uændrede. Der korrigeres ikke for alder, klubskifte, rolle, ændret position eller straffespark. Assistdefinitionen er også uændret: xA er stadig modellens proxy for FPL-assists. Før forventede statistikkers nyere sæsoner understøttes, kræves en separat dækningskontrol; placeholder-nuller i meget gamle API-felter må ikke antages at være data.

Uden odds ændres kun mål-/assistrater. Med angrebsodds ændres spillernes relative vægte i **den eksisterende** normalisering til holdets målbudget; intet ekstra holdstyrkemultiplikator tilføjes. Holdkammerater uden eget sæsonprior kan derfor også få ændret andel. Den eksisterende xA/xG-baserede assistandel kan ændres. Et lille prior er ikke en uafhængig holdstyrkeanalyse.

Baseline-RNG forbruges som før. Erstatningsmål/-assists uden odds har separate strømme; med odds genbruges den eksisterende separate angrebsstrøm. For samme seed bevares minutter og alle ikke-angrebskomponenter præcist. Manglende prior uden ændret holdfordeling giver identisk fallback, og baseline uden tilvalg er uændret.

## Tid og sporbarhed

Indlæsning er read-only efter snapshot-checksumkontrol. Der gemmes originalt snapshot-ID, råsti, SHA-256, bootstrap-identitetsreference, retrieved_at og available_at. Sidstnævnte er seneste nødvendige inputtid, ikke slutdatoen for den gamle sæson. Live kræves `available_at <= forecast_origin_at` samt eksisterende GW-deadlinekontrol. Fremtidige versioner kan ikke ændre et historisk as-of-valg.

Retrospektiv udviklingsdiagnostik tillader eksplicit senere hentede **tidligere sæson**-summer. Forecast-rundens og den aktuelle sæsons slutaggregater bruges ikke. Årets kamphistorik er begrænset til tidligere kampe som i den eksisterende evaluering. Dette er ikke bevis for, hvilke historiske versioner vi havde ved gamle deadlines. Aktuel spillerpulje/position og senere labelrevisioner er fortsat begrænsninger. Ingen aktuelle odds i historisk evaluering.

Forecastcache, transfer-/strategirapport og gemte prognoser registrerer modelversion, konfiguration og forklaringer. Rådata og genererede resultater forbliver gitignored. Ingen downloads ved appstart eller genkørsel.

## Kørsel uden netværk

```bash
.venv/bin/python scripts/compare_season_priors.py \
  --snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --context-snapshot data/raw/2026-10-12_051541027780Z_e7171f9555904b94908001be74937c16 \
  --odds-snapshot data/raw/2026-10-09_044610511257Z_bb08becd841f43c0ab0aa492560237b9 \
  --draws 3000 --seed 42
```

Udelad context/odds for kun retrospektiv evaluering. Forecast-kommandoen vælger næste officielle fremtidige GW og gemmer nye versionsmapper. Samme spillerdata, rækker, seed-strategi og konfiguration bruges på begge sider. Ingen parameterjagt.

## Faktisk kørsel 13. oktober 2026

667 gyldige svar: 533 har mindst én tidligere sæson, 480 en 2025/26-række. **409 spillere** har positive minutter og gyldig xG/xA. **258 fallback**: 71 uden positive minutter og 187 uden 2025/26-række. Ingen er udfyldt med fiktive nuller.

GW3–5: **udviklingsdata**, 1.779 rækker, 593 spillere, 3.000 scenarier, seed 42 + GW. 1.170 evalueringsrækker har spillerprior, 609 bruger positions-fallback.

| Model | Point-MAE | Point-RMSE | CRPS |
|---|---:|---:|---:|
| Baseline | 1,3734 | 2,1895 | 0,8099 |
| Sidste sæson | 1,3678 | 2,1928 | 0,8109 |
| Tidligere pointgennemsnit | 1,2980 | 2,4206 | — |

Regelmæssige spillere (536 rækker): MAE 2,5442 → 2,5354, RMSE 3,3804 → 3,3829 og CRPS 1,7400 → 1,7387. Forsvarere og angribere får lidt lavere RMSE; midtbanespillere højere. Samlet små, blandede forskelle; én seed-strategi uden sikkerhedspåstande. **Behold baseline som standard**. Få tidligere kampe og allerede brugte udviklingsrunder kan ikke afgøre generalisering.

GW7-prognose: 10/10 allerede gemte William Hill-kampe, 3.000 scenarier, seed 42. Eksempler (angrebsoddsreference → samme model med sæsonprior): Saka 5,738 → 6,048; B. Fernandes 4,392 → 4,723; Haaland 7,663 → 7,822. Ændringerne er kun mål/assists. Spillerhistorik og odds er fra 9. oktober, officiel kampkontekst fra 12. oktober; det er ikke friske priser/skadesoplysninger. Referenceprognosens point- og minutarrays er bit-identiske med den tidligere gemte oddsreference fra bonusforsøget.

Lokale resultater:

- `artifacts/season_priors/development/20261013T182245156864Z_032c987d/report.json`
- `artifacts/season_priors/forecasts/20261013T182247565832Z_f16e421c/`

Ingen faktisk outcome-evaluering af GW7 endnu. Næste aftalte punkt er FPL-specifik assistkorrektion; den er ikke del af dette forsøg.

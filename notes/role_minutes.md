# Rollespecifik spilletid – ét afgrænset eksperiment

`component_role_transitions_v2` er valgfri. `component_baseline_v1` er fortsat standard; den tidligere `recent_role_v1` er bevaret. Ingen nye data, odds, skadesmodel, angrebskomponenter eller parametersøgning indgår i forsøget.

## Kontrakt

Kun komplette, endelige spiller/kamp-rækker før forecast bruges. Mindst to rækker og kendte starts/minutes kræves; ellers beholdes den eksisterende baseline og fallback mærkes. Manglende kampe er aldrig DNP. Kampe med uklar historisk klubtilknytning indgår ikke i prioren. En spiller klassificeres på hele sin hidtidige observerede historik:

- starter: mindst 75% starter;
- reserve: højst 25% deltagelse;
- substitute: højst 25% starter og mindst 50% deltagelse;
- rotation: øvrige.

Dette er observationsgrupper, ikke en vurdering af trænerens intention eller verificeret helbred.

For hver tidligere kamp klassificeres rollen **før den pågældende kamp**, og dens faktiske start/indhop/DNP bliver en historisk overgang. Alle positionens tidligere overgange giver en positionsprior; overgange fra samme rolle giver en rolleprior. Den spiller, der forudsiges, udelades fra begge peer-priorer. Spillerens egne tidligere overgange fra den nuværende rolle indgår separat.

Med tællevektorer for start/indhop/DNP:

```
position = (peer_position_counts + [0.45, 0.10, 0.45]) / (n_position + 1)
role = (peer_role_counts + k * position) / (n_role + k)
player = (own_role_counts + k * role) / (n_own_role + k)
k = EvolutionConfig.transition_prior_games = 3
```

3 er en eksplicit, **ikke optimeret** udglatningsantagelse. Manglende rolleobservationer bruger positionsprioren; manglende positionsevidens bruger de eksisterende baseline-priormiddelværdier. Forklaringer gemmer rolle, tællinger, fixture-ID'er, priorer og sparsom dækning.

Minutter givet start og indhop estimeres separat: positionens observerede betingede minutter udglattes mod den eksisterende start-/indhopprior; spillerens egne betingede minutter udglattes mod denne positionsprior. `BaselineConfig.minutes_prior_games=1` bevares. Betingede middelværdier afgrænses som før til 1–90 og 1–59 minutter. Skadesfaktoren anvendes én gang efter rolleberegningen; manuelle tilgængeligheds-/returbegrænsninger bruger fortsat eksisterende kontrakt. Den historiske rolle kan dog allerede afspejle skadefravær – dette er ikke en kausal eller kalibreret adskillelse mellem skade og rotation.

Simulation, scoring og per-minut-rater er uændrede. Ændrede minutter kan ændre forventede mål/assists og point; der tilføjes ingen ændring i angrebsraterne. Den isolerede appvariant bruger ikke odds eller fælles mål. Fremtidige GWs bruger samme observerede rollehistorik og den valgte tilgængelighedspolitik; taktiske rolleændringer fremskrives ikke.

## Kørsel og app

```bash
.venv/bin/python scripts/compare_role_minutes.py \
  --snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --draws 2000 --seed 42
```

Kommandoen henter intet. Den sammenligner baseline, eksisterende rollemodel, den ene nye kandidat og tidligere gennemsnit på identiske evalueringsrækker. Alle bruger seed + GW. Nye mapper under `artifacts/role_minutes/` bevarer komplette rækker, konfiguration, datakilde/hash, kodehash, gruppedefinitioner og resultater. Ingen tidligere rapporter overskrives.

I **Mit hold → Prognosemodel → Eksperiment · rollespecifik spilletid** kan den vælges til transferplanlægning. **Analyse og eksperimenter → Rollespecifik spilletid · udviklingssammenligning** viser gemte resultater uden nye simulationer. Forecastcachen inkluderer den nye kode og konfiguration, så gamle prognoser ikke genbruges som nye.

## Gennemført sammenligning

9. oktober-snapshot, 1.779 rækker / 593 spillere, GW3–5, 2.000 scenarier, seed 42 + GW. Den oprindelige baseline og tidligere rollemodel reproducerer de allerede gemte evalueringsrækker præcist. Resultat: `artifacts/role_minutes/20261012T183847190122Z_2323c1aa/comparison.json`.

| Model | Minut-MAE | Minut-RMSE | Point-MAE | Point-RMSE | DNP-Brier | CRPS |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 18,222 | 23,395 | 1,376 | 2,191 | 0,11097 | 0,81040 |
| Tidligere rollemodel | 17,565 | 22,796 | 1,319 | 2,173 | 0,10749 | 0,79496 |
| Ny rollespecifik model | 14,983 | 23,139 | 1,259 | 2,177 | 0,11172 | 0,80486 |
| Tidligere gennemsnit | 11,471 | 22,511 | 1,298 | 2,421 | 0,11201 | — |

Vigtige afvejninger mod baseline:

- Regelmæssige spillere (536 rækker, eksisterende definition): minut-MAE 21,46 → 19,44, bias −4,42 → −1,21. **Point-MAE forværres** 2,551 → 2,585 og DNP-Brier 0,08094 → 0,08302.
- Reserver (762 rækker): minut-MAE 11,11 → 4,08; bias +8,88 → +1,14.
- Startergruppen (539 rækker, ikke identisk med regelmæssig-gruppen): minut-MAE 21,56 → 19,49.
- Rotation (244 rækker): minut-MAE **30,49 → 32,85**, DNP-Brier **0,175 → 0,211**.
- Indhoppere (234 rækker): minut-MAE **20,92 → 21,46**.

Kandidaten forbedrer gennemsnitlige minutfejl for startere og reserver, men ikke alle fejlmål eller alle grupper. Den simple minutreference har fortsat lavere samlet MAE; den tidligere rollemodel har bedre samlet DNP-Brier og CRPS. Derfor forbliver baseline standard. Dette er allerede anvendte **udviklingsdata**, ikke uafhængig test eller sikker dokumentation for en fordel over andre managers. Senere hentede historiske labels dokumenterer ikke datatilgængelighed ved tidligere deadlines. Ingen GW6-udfald er indgået, og ingen tærskler er tilpasset efter resultatet.

Anbefaling: behold kandidaten til prospektiv sammenligning, især for stabile startere/reserver; undersøg senere rotationsgruppens rolleændringer og fraværsårsager. Implementér ikke næste udvidelse som del af dette trin.

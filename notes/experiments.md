# Modelforsøg · status

Samme oversigt vises under **Analyse og eksperimenter**. Kilden er `src/fpl_model/experiment_overview.py`. Pensionerede forsøg kan ikke længere vælges i appen. Koden, rapporterne og noterne ligger i git-historikken, og gemte forslag, der brugte dem, kan stadig åbnes.

| Forsøg | Status | Ændrer | Resultat |
|---|---|---|---|
| Standardmodel (`component_baseline_v1`) | Standard | Hele prognosen | Reference. Bedre point-MAE end det simple gennemsnit i GW8–10, men dårligere minut-MAE for faste spillere. |
| [Odds til angreb og forsvar](attacking_odds.md) | Tilvalg | Mål, assists og clean sheets fra bookmakerodds | Endnu ikke efterkontrolleret på endelige udfald. Kræver manuelt hentede odds. |
| [Minutmodel v2](minutes_v2.md) | Afprøves | Kun spilletid | Frosset 15. november. Afprøves prospektivt på GW12–15. |
| [Defensiv oddsvariant](defensive_odds.md) | Pensioneret | Kun clean sheets og indkasserede mål | 0 af 10 kampe fik odds i testen. Dækket af oddsmodellen for angreb og forsvar. |
| [Rolle, returminutter og fælles mål](model_evolution.md) | Pensioneret | Nyere rollehistorik, returantagelser, fælles holdmål | Faste spilleres minut-MAE 21,46 → 22,92. Afløses af v2. |
| [Rollespecifik spilletid](role_minutes.md) | Pensioneret | Spilletid ud fra rolle | Det simple gennemsnit var stadig bedre samlet. Afløses af v2. |
| [Frekvensprior 0,25 og 0,10](frequency_prior_experiment.md) | Pensioneret | Svagere udglatning af start/indhop | Færre minutfejl, men dårligere point-CRPS for faste spillere. |
| [Dødboldsroller](set_piece_roles.md) | Pensioneret | Mål og assists til dødboldsskytter | Antagede vægte uden data at kalibrere mod. |
| [Præstationsafhængig bonus](conditional_bonus.md) | Pensioneret | Kun bonus | Små, blandede forskelle. |
| [Sidste sæsons xG/xA som prior](previous_season_priors.md) | Pensioneret | Kun xG/xA-udgangspunkt | Små, blandede forskelle. |
| [FPL-assistkorrektion](fpl_assist_correction.md) | Pensioneret | Én fælles assistfaktor | Dårligere: point-MAE 2,5442 → 2,5665 for faste spillere. |

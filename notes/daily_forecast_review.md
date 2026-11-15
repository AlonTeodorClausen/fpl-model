# Efterkontrol af daglige transferforslag

Under **Analyse og eksperimenter → Efter runden** kan et gemt forslag fra **Mit hold** nu følges frem til officielle udfald. Vælg et opdateret officielt datagrundlag og tryk **Efterkontrollér gemt prognose**. Ingen prognose genberegnes, og der hentes ikke nye data i dette forløb.

Standardvalget er seneste afsluttede GW med en gemt kørsel før deadline, derefter sidste oprettelsestid før deadline (med origin og sti som deterministiske tie-breakers). Standardvalget bruger kun kørsler med standardmodellen; kørsler med en forsøgsmodel, fx minutmodel v2, er mærket i listen og vælges manuelt. Det er en operationel udvælgelsesregel, ikke et valg af den kørsel, der bagefter klarede sig bedst. Andre gemte kørsler kan åbnes manuelt; de må ikke sammenblandes til en performancepåstand.

## Hvad opgøres?

- Den gemte anbefaling og den gemte behold-plan scores med deres faste XI, bænk, anfører/vice, autosubs, chips og hits. Det er hypotetiske planer, ikke dokumentation for brugerens faktiske transfers.
- Hver GW kan opgøres separat, når officielle fixtures/GW er finished/data-checked og alle nødvendige spillerudfald er endelige. En manglende række er aldrig DNP. Hele horisontens gevinst vises først, når alle runder er opgjort.
- Point-MAE/RMSE/CRPS, minut-bias/MAE/RMSE og DNP-Brier vises samlet, pr. GW, position og historikgruppe. Gruppen regular bruger kun den gemte forudgående historik: mindst to kampe, gennemsnitligt mindst 60 minutter og deltagelse i mindst 75% af kampene.
- Modellen og referencegennemsnittet vurderes på præcis samme spiller-GW-rækker. Referencen bruger kun final historik fra den oprindelige kilde, tilgængelig før prognosens origin. Ufuldstændigt historikvindue udelukker sammenligningen; øvrige modeludfald kan ses særskilt.
- CRPS kræver den originale scenariecache. Mangler den, vises ingen rekonstrueret CRPS. Rapportens spilleroversigter skal stemme med den cache, der bruges.
- Den simple reference er en punktprognose: dens CRPS og pointinterval er ikke tilgængelige. Modellens percentiler må ikke kopieres til referencen. En rettet efterkontrol gemmes som en ny version; ældre rapporter bevares, men genbruges ikke som den rettede beregning.
- Ved flere kampe i samme GW skaleres referencens point- og minutgennemsnit med kampantal. Sandsynligheden for nul minutter i hele runden antager uafhængige kampe. Det er en enkel referenceantagelse, ikke en estimeret afhængighedsmodel.
- Kort uden spilleminutter tæller som deltagelse ved autosubs/anfører, jf. [FPLs regelbeskrivelse](https://www.premierleague.com/es/news/4661029). Minutdiagnostikkens nulminutsmål holdes separat.
- Hvis den officielle kampplan indeholder andre spillerkampe end den gemte prognose, afventer spilleren med `fixture_universe_changed`; manglende kampe scores ikke som et komplet udfald.

## Proveniens

Rapporter med separate `input_sources` og rapporter med én præcis top-level `snapshot_path`, `snapshot_id` og `manifest_sha256` understøttes. Begge verificeres mod de oprindelige bytes og officielle deadlines. En nyere kilde erstatter aldrig en manglende gammel kilde. Lokale tidsstempler/checksums er registreret dokumentation, ikke ekstern attestering af, hvornår prognosen blev skabt.

Efterkontrollen er en ny fil under `artifacts/forecast_reviews/`; input, cache og gammel rapport ændres ikke. UI genbruger kun resultatet, når beregningsversionen er den aktuelle, og prognosehash, udfaldskilde **og** officiel kampkontekst er de samme. Rådata og genererede resultater følger eksisterende ignore-regler.

## Verificeret lokalt eksempel, 7. november 2026

Sidste gemte før-deadline-kørsel for GW8:
`artifacts/transfers/20261023T133449649991Z_6594f210/report.json`.
Udfaldssnapshot: `2026-11-06_175837732767Z_42716fdf2d574c8bb88cfbcd8a1964ce`.
Rettet efterkontrol (`forecast_review_v3`): `artifacts/forecast_reviews/20261107T091352950331Z_42b770aa/report.json`. Den tidligere version er bevaret. Point-, minut- og DNP-mål er uændrede; referencens tidligere kopierede pointinterval er fjernet. Intervaldækning angiver antallet af rækker med begge intervalgrænser; uden sådanne rækker er dækning ukendt.
Dette er én udvalgt, tidligere gemt kørsel. Det er ikke en uafhængig benchmark eller evidens for statistisk sikker forbedring.

| Runde | Samme evalueringsrækker | Model point-MAE | Reference point-MAE | Model minut-MAE | Reference minut-MAE | Forslag / behold |
|---|---:|---:|---:|---:|---:|---:|
| GW8 | 593 | 1,190 | 1,310 | 15,02 | 15,62 | 35 / 34 |
| GW9 | 593 | 1,126 | 1,220 | 15,66 | 14,82 | 40 / 39 |

668 spillerudfald pr. runde er endelige; 75 pr. runde mangler et sammenligneligt verificeret historikvindue. GW10–11 afventer, så ingen samlet fire-runders realiseret gevinst rapporteres. Minutmodellen er dårligere end referencen i GW9 trods lavere pointfejl. Ingen automatisk tuning eller skift af standardmodel.

Samme kontrol fra terminalen:

```bash
.venv/bin/python scripts/evaluate_saved_forecast.py \
  --forecast artifacts/transfers/20261023T133449649991Z_6594f210/report.json \
  --outcome-snapshot data/raw/2026-11-06_175837732767Z_42716fdf2d574c8bb88cfbcd8a1964ce
```

Næste afgrænsede modelarbejde er den allerede planlagte sammenligning af baseline med eksisterende angreb+forsvar-odds på fremtidige gemte prognoser. Ingen nutidige odds må sættes ind i disse historiske forecasts.

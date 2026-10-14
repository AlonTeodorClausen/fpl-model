# Mit hold og transferforslag

Start: `.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false`.

## Forløb
1. Vælg et officielt snapshot. Det samme snapshot leverer spillerpulje, priser, skader, historik, kampe og deadlines. Alder vises; appen henter ikke data.
2. Indtast holdet og **salgsværdier**, bank, resterende gratis transfers samt allerede foretagne transfers denne GW. Beløb i £m konverteres til heltal i £0,1m uden afrunding. Skift af spiller nulstiller salgsværdien. Eksempelknappen udfylder spillere fra brugerens billede og én gratis transfer, men opfinder ikke priser/bank.
3. **Gem hold** skriver atomisk til `data/processed/my_team.json`. **Genindlæs gemt hold** gendanner det. Forslag foretager ingen ændringer på FPL eller i det gemte hold.
4. Horisonten starter ved næste fremtidige officielle GW, så transfers og eventuelle hits placeres korrekt. Vælg horisont 1–4, maksimalt transferantal, behold/udeluk og model. Baseline er standard; den defensive oddsvariant bruger et eksplicit valgt gemt William Hill-snapshot. Hits er som standard ikke tilladt.
5. Sammenlign med at beholde holdet. Se pakkevis bank, gratis transfers, hits, simuleret nettogevinst og målværdi; åbn XI, ordnet bænk, anfører/vice pr. GW. Rapporter genåbnes fra samme side.

## Budget og regler
Bank efter = bank nu + faktiske salgsværdier for solgte spillere − aktuelle købspriser for købte. Beholdte spillere købes ikke igen, og en generel £100m-grænse erstatter aldrig dette budget. Der gælder 2 GK/5 DEF/5 MID/3 FWD, højst tre fra hver klub og lovlige opstillinger. Ejede, ikke længere købbare spillere må beholdes, men må ikke købes ind. Ukendte ID’er og hold fra en anden sæson kræver rettelse. En trup med over tre fra en klub efter en virkelig klubtransfer kræver manuel rettelse i denne første version.

Regler verificeret 2026-10-08: én ny gratis transfer hver GW, op til fem opsparede, fire points fradrag pr. ekstra transfer og højst 20 transfers i samme GW. `min(5, max(0, gratis_nu − nye_transfers) + 1)` gælder næste GW. Fradraget trækkes kun én gang i første GW. Tidligere betalte hits er fælles for hold-alternativerne og indgår ikke som nye omkostninger. Snapshotregler, der ændrer cap/opsparing, afvises.

Kilder: [officielle regler](https://www.premierleague.com/es/news/4661029), [transfer- og salgsprisforklaring](https://www.premierleague.com/en/news/2174907/fpl-basics-explained-how-to-make-transfers).

## Optimering og sammenligning
Én fælles trup vælges for hele horisonten, med særskilt XI/anfører pr. GW. Der genereres behold-alternativet og bedste fundne pakke for hvert lovligt, præcist transferantal. Låste egne spillere beholdes; udelukkelser gælder forslagene, mens referenceholdet altid er uændret. Alle GWs vægtes ens.

MILP-målværdien er summen af XI-xP + ekstra anfører-xP + 0,1 × bænk-xP, minus nye hits. Bænk og vice prioriteres som i den eksisterende optimizer. Solverstatus/gap vises; gap kommer fra solverens punktmålværdi før det konstante fradrag. Der påstås ikke et optimum for alle mulige autosub-/bænkscenarier.

Alle pakker og behold-holdet evalueres i **samme separate evalueringsscenarier**, inklusive autosubs, anfører og vice. Opstillinger vælges før disse scenarier observeres; der må ikke optimeres en ny opstilling inden for hvert udfald. Simulerede nettogevinster er parvise forskelle til behold-holdet, ikke summer af udskiftede spilleres xP. Målværdi og simulerede holdpoint vises separat. Små forskelle kan være simulationsstøj.

## Prognoser, cache og provenance
`transfer_planner.forecast_bundle` bruger eksisterende simulation og standard `component_baseline_v1` eller den defensive oddsvariant. Ingen modelparametre/formler er ændret. Ét fælles forecast-origin bruges for alle GWs; ingen fremtidige data eller opfundne mellemresultater. Et GW-specifikt seed afledes deterministisk af seed 42/GW/stream til hhv. prognose og evaluering. Derfor er de numeriske samples ikke identiske med tidligere enkelt-GW-kørsler med det direkte seed 42.

Cache under `artifacts/transfer_forecasts/` identificeres af indholdet i data, konfiguration, origin, horisont, odds, seed, draws og modelkodechecksums. Scenarier har checksum og indlæses uden pickle. Hold-, bank- og transferbegrænsninger er ikke cache-nøgler: genberegning af forslag genbruger prognoserne. I en appsession genbruges samme origin ved samme prognosevalg; nye inputvalg eller en ny session får en ny origin, uden at kilde-timestamps ændres.

Rapporter under `artifacts/transfers/<run>/report.json` gemmer profil, inputprovenance, modelversion, konfiguration, deadlines, cache-reference, oddsfit/fallback, pakker og GW-opstillinger. Tidligere rapporter og rå snapshots overskrives ikke. Lokale profiler, scenarier og rapporter er allerede gitignored.

## Begrænsninger
- **Alle transfers nu, derefter samme trup.** Nye gratis transfers opspares og vises; værdien af at vente prissættes ikke. Ingen chips.
- Nuværende start-/indhop-/skadesfaktorer holdes faste gennem horisonten. Ingen raskmeldingsprognose, nye skader eller model for fælles rotation. GWs simuleres uafhængigt.
- Faste fremtidige priser; salgsværdier angives af brugeren, ikke udledt af et billede eller aktuelle købspriser. Manglende værdier blokerer beregning.
- En blank GW har ingen tildelte kampe. Dobbelte GWs summeres pr. spiller inden autosubs/anfører. Kampe uden GW placeres ikke ved gæt; uafklarede kampe/tider vises. Planen kan senere ændre sig.
- Odds bruges kun ved eksakt matching, komplette William Hill-markeder og gyldig observationstid før origin/deadline. Hver manglende/ugyldig kamp får baseline-fallback. Odds ændrer kun clean sheets/indkasserede mål.
- Foreløbige, ikke dokumenteret kalibrerede sandsynligheder. Forslag er prognosesammenligninger, ikke dokumenteret bedre performance.

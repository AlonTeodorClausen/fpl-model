# Rolle, returminutter, fælles mål og efterkontrol

Opt-in: **Eksperiment · rolle, returminutter og fælles mål** under Mit hold. `component_baseline_v1` forbliver uændret standard. Tidligere oddsvarianter er bevaret. Ingen nye data hentes automatisk.

## Spilletid

`component_role_minutes_v1` bruges til isoleret retrospektiv diagnostik. Kun en komplet observeret historik bruges som frekvensnævner; huller, ukendt klubhistorik og ukendte starts beholder eksisterende markeret fallback. Positionspriorer estimeres fra tidligere komplette historikker. Ældre egen historik bestemmer et spillerprior-center, udglattet mod positionen. De seneste tre kampe vægtes med halveringstid to kampe og priorstyrke 1. Betingede minutter bruger ældre eget gennemsnit og nyere vægtede observationer. Vindue/halveringstid/priorstyrke er eksplicitte i `EvolutionConfig`, ikke optimeret på resultaterne. xG/xA-rateestimation er uændret.

Positionspriorens spillerunivers i retrospektiv evaluering bestemmes før forecast og før target-dækningsfilteret. Ellers ville en senere manglende target-række indirekte kunne ændre andre spilleres tidligere prognoser. En regressionstest dækker dette.

## Skader og tilbagevenden

Tilgængelighed, startchance givet tilgængelighed og minutter ved start/indhop er separate. Officiel FPL-spillechance bruges stadig som en praktisk tilgængelighedsfaktor, ikke som en dokumenteret medicinsk sandsynlighed. FPL-nyhed, snapshot og oprindelig tilgængelighedstid gemmes. `news_added` er ikke automatisk bevis for historisk tilgængelighed.

I appen kan en spiller/GW få en manuel betinget startchance og hårde minutlofter ved start/indhop. Begrundelse kræves; kildelink er valgfrit. Ingen returdato eller procent udledes automatisk fra fritekst. Tomt felt beholder modellen. Antagelser registreret efter forecast afvises; senere GWs får ikke automatisk nye antagelser. Eksisterende scenarie for 75%-tvivl og følsomhedsanalyse bevares særskilt og tydeligt som antagelser.

## Sammenhængende mål – begrænset første version

`component_shared_goals_v1` kombinerer rollemodellen med fælles kampmål. Samme mål/tid bruges til indkasserede mål/clean sheets og til fordeling af scorer/assist. Odds er kilde, når den eksisterende matching, market- og tidskontrol godkender dem; ellers bruges baseline-holdmål. Mål vægtes efter xG-rate blandt spillere på banen på måltidspunktet, og assist efter xA blandt andre aktive spillere. Ingen selv-assist. Hvert holdmål har én scorer eller en eksplicit ikke-tilskrevet post, aldrig en opdigtet spiller. Assistandelen er fortsat en ukalibreret xA/xG-proxy. Ekstra offensiv holdmultiplikator anvendes ikke.

**Afgrænsning:** Spillernes minutter er stadig uafhængige, så der er endnu ikke en sammenhængende virkelig XI, præcis målmandsudelukkelse eller realistisk antal indskiftninger. Bonus er den gamle marginale model, ikke BPS-rangering. Selvmål er udeladt i denne eksperimentelle variant, fordi en separat uafhængig selvmålsproces ville bryde målafstemningen. Straffespark/dødbolde og FPL-specifikke assistdefinitioner er ikke særskilt modelleret. Det er ikke en fuldstændig kampsimulator.

## Gemte prognoser og endelige udfald

`scripts/run_model_evolution.py` gemmer officielle inputreferencer, verificerede rå checksums, konfiguration, kodehash, oprindelsestid, faktisk skrivetid, officiel deadline og scenario-arrays for baseline, eksisterende angrebsoddsreference og ny variant. Hver kørsel får en ny mappe; rapport og arrays kontrolleres med checksums. Lokal `recorded_pre_deadline` kræver råreferencer og faktisk lagring før deadline. Der er ikke ekstern tidsattestation. Gamle data bliver ikke nye ved genkørsel.

`scripts/evaluate_saved_forecast.py` læser disse uændrede arrays og bruger den eksisterende final-outcome-selector. Endelige labels må være hentet efter forecast. Der beregnes point/minut-bias, MAE/RMSE, CRPS, DNP-Brier, DNP-kalibreringsgrupper og 10–90%-intervaldækning. Tal opdeles pr. position; rapportens GW er eksplicit. Provisoriske/manglende/conflicted targets, flyttede kampe og ændret DGW-univers scores ikke som nul. Blanke GWs holdes særskilt. Udfaldsrapporten gemmes i en ny mappe, aldrig i forecastfilen. Ingen nye features beregnes under efterkontrollen.

## Kommandoer

```bash
.venv/bin/python scripts/run_model_evolution.py \
  --snapshot data/raw/<officielt-snapshot> \
  --odds-snapshot data/raw/<odds-snapshot> --draws 3000 --seed 42

.venv/bin/python scripts/evaluate_saved_forecast.py \
  --forecast artifacts/model_forecasts/<kørsel> \
  --outcome-snapshot data/raw/<senere-officielt-snapshot>
```

App: **Analyse og eksperimenter → Modeludvikling** viser gemte prognoser, rolleforklaringer, udviklingsdiagnostik og en eksplicit knap til efterkontrol mod allerede indlæste labels. Den foretager ingen downloads eller nye simulationer.

## Første kørsel – udviklingsdata, ikke uafhængig test

9. oktober-snapshot; 1.779 evalueringsrækker, 593 spillere, GW3–5; samme rækker og seeds for begge minuttermodeller. Samlet minut-MAE 18,22 → 17,57, RMSE 23,40 → 22,80, DNP-Brier 0,1110 → 0,1075. Point-MAE 1,376 → 1,319 og CRPS 0,810 → 0,795. **Regelmæssige spillere forværres:** minut-MAE 21,46 → 22,92 (536 rækker), bias −4,42 → −7,00. Den simple tidligere-minut-reference har samlet MAE 11,47. Derfor ingen udskiftning af standardmodel, ingen yderligere parametersøgning.

GW7-forecast er gemt før deadline med 10/10 dækkede odds-kampe, 3.000 scenarier og seed 42. Slutresultater mangler fortsat; efterkontrol er afventende. Udviklingsdiagnostikken evaluerer kun rolleændringen, ikke fælles mål med aktuelle odds.

## Praktisk efterkontrol af GW6 og senere runder

**Analyse og eksperimenter → Efter runden** sammenligner de oprindeligt gemte prognoser med endelige officielle spillerlabels. Der vises point-/minut-bias, MAE/RMSE, DNP-Brier og forudsagt/observeret DNP, pr. position og for regelmæssige spillere. Gruppens definition er fortsat mindst to tidligere kampe, gennemsnitligt mindst 60 minutter og deltagelse i mindst 75%. Grupperne bruger kun historikken gemt i prognosen; manglende eller ufuldstændig historik er `unresolved`. Alle modeller scores på præcis samme spiller/GW-rækker. DGWs kræver alle de oprindeligt forventede kampe; ændret kampunivers, manglende labels og konflikter holdes ude og vises med årsag.

Ældre `artifacts/defensive_odds/*/comparison.json` indeholder middelværdier og percentiler, men ingen fulde scenario-arrays. De kan derfor **ikke give CRPS**. Der opfindes ingen fordeling, og ingen prognose genberegnes. Nyere `artifacts/model_forecasts/*` har verificerede arrays og kan give CRPS. Syntetiske oddsdemonstrationer afvises. Ældre rapporter mærkes `legacy_declared_pre_deadline` ved verificerede råreferencer og konsistente deklarerede tider; det er svagere dokumentation end den nyere lagringskontrakt. Efter-deadline-prognoser markeres `not_pre_deadline`, og manglende proveniens `unverified_provenance`.

Rundestatus vises fra det seneste verificerede officielle kontekstsnapshot, separat fra udfaldssnapshottet. En nyere bootstrap/fixture-hentning kan ikke opgradere ældre spillerlabels til `final`. Appens initiale datavalg foretrækker det seneste snapshot med spillerhistorik frem for et rent kontekstsnapshot. Begge kan fortsat vælges eksplicit. Rapporterne gemmes som nye lokale versioner under `artifacts/forecast_reviews/`, med kildehash, udfaldsreferencer og tidspunkt. Gamle rapporter og rådata overskrives ikke. Appen genindlæser gemte efterkontroller for samme prognosehash og udfaldssnapshot.

Faktisk kontrol 12. oktober 2026 kl. 05:15 UTC: GW6 var **ikke finished/data_checked**. Ni af ti kampe var `finished_provisional`, ingen var `finished`; sidste kamp stod til 12. oktober kl. 19:00 UTC. Kun bootstrap og fixtures blev opdateret. Efterkontrollen af prognosen fra 6. oktober mod eksisterende spillerhistorikker fra 9. oktober gav **0 scorebare / 667 afventende spillere** for begge modeller. Det er ikke et performance-resultat. Der blev ikke hentet alle spillerhistorikker igen, kørt simulationer eller ændret modelparametre.

Den gennemførte offline-kommando:

```bash
.venv/bin/python scripts/evaluate_saved_forecast.py \
  --forecast artifacts/defensive_odds/20261006T152853017651Z_c8b9174b/comparison.json \
  --outcome-snapshot data/raw/2026-10-09_044607688918Z_0828f65a3da54be49c3a53a5986a7ac5 \
  --context-snapshot data/raw/2026-10-12_051541027780Z_e7171f9555904b94908001be74937c16
```

Når FPL har endelige og datakontrollerede resultater: brug den eksisterende `scripts/capture_all_players.py --season 2026-2027 --request-interval 0.5` én gang og vælg det nye udfaldssnapshot i kommandoen/appens datavalg. Behold den oprindelige forecastfil. Nye indsamlinger er altid eksplicitte handlinger; der er ingen automatisk overvågning. Evalueringen er af enkeltspillerprognoser, ikke realiserede holdpoint med autosubs. En enkelt runde er ikke dokumentation for en sikker modelgevinst.

# Odds til angreb og forsvar — første eksperiment

`component_baseline_v1` forbliver standard. `component_defensive_odds_v1` ændrer fortsat kun clean sheets og indkasserede mål. Ny valgfri `component_attacking_odds_v1` ændrer derudover mål og assists. Spilletid, skadesfaktor, frekvensprior, bonus og øvrige hændelser er identiske med den defensive variant ved samme seed.

## Fordeling

For hver dækket kamp/klub bruges det eksisterende positive oddsafledte holdmål `λ`. For alle klubbens spillere i det komplette officielle bootstrap beregnes:

- `e_i = E[minutter_i] / 90`, inklusive start/indhop/DNP og den eksisterende afrundede/afklippede minutfordeling.
- `G = sum(xG90_i × e_i)` og `A = sum(xA90_i × e_i)`, med de eksisterende udglattede spillerrater/priorer.
- Målrate pr. 90: `λ × xG90_i / G`. Forventede spillermål summerer derfor analytisk til `λ`.
- Assistandel: `min(1, A/G)`; assist-rate pr. 90: `λ × assistandel × xA90_i / A`.

Assistandelen er en **proxy fra xA/xG**, ikke en kalibreret FPL-assist-sandsynlighed. Præcise FPL-assists og leverandør-xA har forskellige definitioner. Ingen ekstra angrebs-/modstanderfaktor multipliceres på. `attack_scale` skal være 1 i denne variant; markedets måltal erstatter skaleringen. Kamp uden gyldige odds bruger præcis baseline; et hold uden positiv xG/xA-eksponering får særskilt offensiv fallback. Dette er synligt i hver spillers kampforklaring.

Komplet spillerpulje er nødvendig for fordelingens nævner: filtrér først spillere efter simulation, aldrig før. Priors, mangelfuld historik og usikker spilletid påvirker spillerandelene og kan stadig give forkerte prognoser. Straffesparks-/dødboldsroller er endnu ikke særskilt estimeret.

## Simulation, sporbarhed og begrænsninger

Eksisterende baselinetræk forbruges uændret. Odds-mål/assists trækkes fra en separat stream `SeedSequence([seed, fixture_id, player_id, 314159])`. Indkasserede mål bruger den allerede implementerede defensive stream. Spillerhændelser er fortsat uafhængige og behøver **ikke** summere til den simulerede kampscore. Konsistent fordeling af konkrete mål/assists og fælles holdopstillinger er næste særskilte simulationsændring, ikke noget v1 foregiver at løse.

Samme William Hill-politik, marginfjernelse, Poisson-fit, eksakte kampmatching og deadline-/available_at-kontrol genbruges. Ingen aktuelle odds i retrospektiv evaluering. Cache-nøgler indeholder scope og kodehash; tidligere prognoser ændres ikke. Sammenligningen gemmer baseline, den defensive reference og den nye variant med samme data, simulationsantal og seed. Player changes opdeler angreb/forsvar og viser også forskellen fra den defensive reference.

## Kørsel

I **Mit hold → Planlæg transfers → Prognosemodel** vælges **Odds til angreb og forsvar · William Hill**. Ingen netværkskald sker ved valg eller genkørsel. I **Analyse og eksperimenter → Oddsmodeller** findes gemte sammenligninger og fordelingen af mål/assists pr. spiller.

```bash
.venv/bin/python scripts/compare_defensive_odds.py \
  --history-snapshot <officielt-snapshot> \
  --context-snapshot <samme-officielle-snapshot> \
  --odds-snapshot <odds-snapshot> --odds-source the_odds_api \
  --odds-scope attack_and_defence --draws 3000 --seed 42
```

Eksisterende odds fra 9. oktober kan bruges til en fremtidig GW7-deadline, men er ikke nye priser. Kildernes alder vises separat. Ændrede xP/holdforslag dokumenterer ikke bedre præcision.

## Videre retning — status efter næste leverance

Første version af rolleminutter, separate returantagelser, fælles kampmål/scorer/assist og efterkontrol af gemte scenariofordelinger er nu implementeret særskilt. Se [modeludvikling](model_evolution.md). Den ændrer ikke denne marginale oddsvariant eller baseline. Rollemodellen forværrer regelmæssige spilleres minutfejl på udviklingsdata og er derfor fortsat opt-in. Fælles faktisk XI, BPS-rangering og automatisk valideret nyhedstolkning er ikke implementeret.

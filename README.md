# FPL Lab

En lokal app, der forudsiger point for alle FPL-spillere ud fra gratis officielle data, simulerer dit hold og foreslår transfers før næste deadline. Prognoserne gemmes, så de bagefter kan holdes op mod de faktiske resultater.

## Start

Fra repositoryets rod:

```bash
make install
```

```bash
make app
```

Åbn http://127.0.0.1:8501. `make test` kører de offline tests. Alle kommandoer bruger projektets egen `.venv`.

## Arbejdsgang hver runde

1. **Hent data.** Når forrige runde er færdigspillet og FPL har bekræftet resultaterne, hent frisk data med knappen **Hent seneste data** på **Mit hold**, eller fra terminalen:

   ```bash
   .venv/bin/python scripts/capture_all_players.py --season 2026-2027 --request-interval 0.5
   ```

2. **Opdatér dit hold.** På **Mit hold**: hent holdet med dit hold-ID, bekræft bank, gratis transfers og transfers allerede foretaget, og tryk **Gem hold**. FPL offentliggør ikke dine præcise salgsværdier, så listepriserne er estimater. Kontrollér salgsværdien for de spillere, du overvejer at sælge.
3. **Planlæg og sammenlign.** Vælg horisont og tryk **Sammenlign transferforslag**. Resultatet viser den anbefalede handling, den forventede gevinst mod at beholde holdet og opstillingen.
4. **Gem før deadline.** Den sidste gemte kørsel før deadline er den, der tæller i evalueringen. Under afprøvningen af minutmodel v2 (GW12–15) gemmes også en kørsel med v2 i **Analyse og eksperimenter → Transferlaboratorium**.
5. **Efterkontrollér.** Når runden er færdig og nye data er hentet: **Analyse og eksperimenter → Efter runden** sammenligner den gemte prognose med de faktiske udfald.

## Modellen kort

For hver spiller og kamp estimeres spilletid (start, indhop eller ingen spilletid, og minutter), mål og assists ud fra xG/xA, holdets mål for og imod, clean sheets, bonus og øvrige hændelser. Tusindvis af scenarier giver en pointfordeling for hver spiller og for dit hold. Optimeringen finder de bedste lovlige transfers, opstilling og anfører. Siden **Model** i appen forklarer hvert trin med formler og et regneeksempel.

- **Standardmodellen** (`component_baseline_v1`) bruges på **Mit hold**.
- **Minutmodel v2** ændrer kun spilletiden og afprøves på GW12–15. Se [specifikation og udviklingskontrol](notes/minutes_v2.md).
- **Odds til angreb og forsvar** kan vælges i Transferlaboratoriet, hvis der er hentet odds.
- Alle andre forsøg er pensioneret. Se [status for alle modelforsøg](notes/experiments.md).

Hvordan prognoser og nye modeller vurderes, er fastlagt på forhånd i [evalueringsprotokollen](notes/evaluation_protocol.md), som også indeholder logbogen over runderne.

## Begrænsninger

- Fordelingerne er **ikke dokumenteret kalibrerede**. Få runder er evalueret prospektivt.
- Spilletid er uafhængig mellem spillere. Modellen kender ikke en sammenhængende startellever.
- Skadesstatus er FPL's officielle chance for næste runde. Senere runder er scenarier, ikke prognoser for raskmelding.
- Salgsværdier fra holdimporten er estimater, og forslaget kan derfor overvurdere din bank.
- Bonus er en tilnærmelse, ikke en fuld BPS-beregning.
- Optimeringen maksimerer forventede point. Den tager ikke højde for rang, ejerskab eller risikovilje.

## Mere

- [Teknisk reference](notes/technical_reference.md): data, antagelser, evaluering, gæstetilstand og kommandoer i detaljer.
- [Efterkontrol af gemte forslag](notes/daily_forecast_review.md)
- [Chips](notes/chips.md) og [transferforløb](notes/my_team_transfers.md)
- Gamle prognosecaches kan flyttes til side med `make prune-caches` (prøvekørsel; tilføj `--apply` i scriptet for at flytte). Alt, en efterkontrol kan få brug for, beholdes.

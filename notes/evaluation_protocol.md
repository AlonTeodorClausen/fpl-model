# Præregistreret evalueringsprotokol

Fastlagt 15. november 2026, før GW11-deadline (21. november). Formålet er at bestemme på forhånd, hvordan prognoser og nye modelvarianter vurderes, så resultaterne ikke kan fortolkes efter, hvad der passer bedst bagefter. Ændringer i protokollen dateres og tilføjes nederst; de gælder kun for runder, der ikke er spillet endnu.

## Data og runder

- **Udviklingsdata:** GW3–10. Alle resultater herfra er allerede set eller brugt til diagnostik og kan ikke dokumentere en forbedring.
- **Prospektive vurderingsrunder:** GW11 og frem. En runde tæller kun, hvis prognosen er gemt før officiel deadline og efterkontrolleres med `evaluate_saved_forecast.py` mod endelige officielle labels.
- **Valg af kørsel:** den eksisterende regel i `notes/daily_forecast_review.md`: sidste gemte kørsel før deadline. Ingen manuel udvælgelse af kørsler bagefter.
- **Faste indstillinger:** `component_baseline_v1` som standard, seed 42, 3.000 prognosescenarier, ingen hits som standard.

## Mål

**Primære mål (afgør accept):**
1. Point-CRPS på de fælles evalueringsrækker (hele puljen).
2. Minut-MAE i gruppen `regular` (mindst to tidligere kampe, mindst 60 minutter i gennemsnit, deltagelse i mindst 75%).

**Sekundære mål (rapporteres altid, kan blokere):**
- Point-MAE/RMSE og minut-bias, samlet og pr. position.
- DNP-Brier samlet og for `regular`.
- Dækning af 80%-pointintervallet for `regular` og øvrige. Målområde 0,75–0,85.

**Beslutningsmål:**
- Kumulativ realiseret gevinst: gemt forslag minus gemt behold-plan, summeret over alle opgjorte runder.
- Forventet gevinst for samme runder, så det kan ses, om modellen systematisk over- eller undervurderer værdien af transfers.

## Accept af en ny modelvariant

En kandidat (fx minutmodel v2) sammenlignes med `component_baseline_v1` på præcis samme spiller-GW-rækker og seeds. Kriterierne fastlægges, før kandidaten bruges på vurderingsrunder:

- Mindst **fire** prospektive runder, som ikke er brugt til at udvikle eller justere kandidaten.
- **Accept**, hvis begge gælder:
  - point-CRPS samlet er lavere end baseline, og
  - minut-MAE for `regular` er lavere end baseline.
- **Blokering**, uanset primære mål, hvis noget af følgende gælder:
  - DNP-Brier for `regular` er mere end 0,005 dårligere,
  - minut-bias for `regular` er mere end 3 minutter længere fra 0 end baseline,
  - 80%-intervaldækningen for `regular` ligger uden for 0,70–0,90.
- **Blandet resultat** (et primært mål bedre, et dårligere): kandidaten forbliver et eksperiment. Ingen kombination af kriterier opfindes bagefter.
- Monte Carlo-støj: forskelle mindre end spændet over tre seeds (42, 43, 44) tolkes som ingen forskel.

Kun én komponent ændres ad gangen. Parametre må ikke justeres efter at have set udfald i vurderingsrunderne; en justeret kandidat starter forfra med nye runder.

## Logbog

| GW | Gemt kørsel | Point-CRPS model | Point-MAE model / ref | Minut-MAE regular model / ref | Forslag / behold | Forventet gevinst |
|---|---|---:|---:|---:|---:|---:|
| 8 (udvikling) | `artifacts/transfers/20261023T133449649991Z_6594f210` | 0,797 | 1,190 / 1,310 | 18,86 / 18,57 | 35 / 34 | 0,81 |
| 9 (udvikling) | samme | 0,755 | 1,126 / 1,220 | 20,22 / 17,45 | 40 / 39 | 1,90 |
| 10 (udvikling) | `artifacts/transfers/20261106T180710726635Z_8e580a61` | 0,720 | 1,074 / 1,133 | 16,73 / 16,00 | 60 / 59 | 2,29 |
| 11 | | | | | | |

GW8–9 er hentet fra efterkontrollen `artifacts/forecast_reviews/20261107T091352950331Z_42b770aa/report.json` (`forecast_review_v3`, udfaldssnapshot `42716fdf2d574c8bb88cfbcd8a1964ce`). Point-CRPS er modellens på de 593 fælles rækker; minut-MAE er gruppen `regular` (156 rækker pr. runde). Realiseret gevinst var +1 point i både GW8 og GW9. Kørslen fra 23. oktober tillod hits, men begge planer brugte nul. For GW10 er sidste gemte kørsel før deadline (6. november kl. 18:30 UTC) kørslen fra kl. 18:07 UTC, ikke kørslen fra 23. oktober. Den er efterkontrolleret i `artifacts/forecast_reviews/20261115T165659890631Z_12c9b54b/report.json` (`forecast_review_v3`, udfaldssnapshot `539c4edb0d8346fca9567cf112b57f59`, hentet 15. november, 672/672 spillere): 670 endelige udfald, 593 fælles rækker og 154 i `regular`. Realiseret gevinst var +1 point mod 2,29 forventet. Minutmodellen er igen dårligere end referencen for `regular` (bias −3,1 min), mens DNP-Brier for `regular` er bedre (0,039 mod 0,066) og 80%-dækningen er 0,82.

Udviklingsrunderne samlet: realiseret gevinst +3 point mod 5,00 forventet. Det er tre runder og ikke evidens for noget; det er en baggrund for at holde øje med, om modellen systematisk overvurderer værdien af transfers.

## Registrerede kandidater

| Kandidat | Frosset | Vurderingsrunder | Status |
|---|---|---|---|
| `component_minutes_v2` ([specifikation](minutes_v2.md)) | 15. november 2026, commit `0e5e6e4` | GW12–15 | Afventer |

For hver vurderingsrunde gemmes både en standardprognose og en v2-prognose før deadline, med samme datagrundlag, seed 42 og 3.000 scenarier. Begge efterkontrolleres mod samme endelige udfald.

## Ændringer i protokollen

Ingen endnu.

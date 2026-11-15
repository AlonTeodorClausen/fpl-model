# Minutmodel v2

Fastlagt 15. november 2026, før kandidaten er evalueret på nogen runde. Parametrene herunder er valgt på forhånd ud fra fodboldlogik, ikke ved at afprøve værdier på GW3–10. Ifølge [evalueringsprotokollen](evaluation_protocol.md) må de ikke justeres efter at have set udfald; en justeret kandidat starter forfra.

Modelnavn: `component_minutes_v2`. Kun spilletiden ændres. Mål, assists, clean sheets, bonus og alt andet er som i `component_baseline_v1`.

## Hvad v1 gør, og hvad der er galt

v1 tæller, hvor ofte spilleren har startet, er kommet ind som indskifter eller ikke har spillet, og trækker frekvenserne en anelse mod en fælles prior. Alle tidligere kampe vægter lige meget. Minutter ved start trækkes fra en normalfordeling omkring spillerens gennemsnit med spredning 8 og klippes ved 90.

Tre problemer:

1. **Afklipningen ved 90 trækker gennemsnittet ned.** En spiller, der altid spiller 90 minutter, har et gennemsnit på omkring 89. Normalfordelingen omkring 89 lægger næsten halvdelen af sandsynligheden over 90, og den bliver klippet til 90. Resultatet er cirka 86 minutter i gennemsnit, ikke 89. Det passer med den negative minutbias for faste spillere i GW8–10.
2. **Gamle kampe vægter lige så meget som nye.** En spiller, der har mistet pladsen for tre uger siden, beholder en høj startchance alt for længe.
3. **Samme prior for alle positioner.** En målmand, der ikke starter, kommer næsten aldrig ind. En angriber gør det ofte. v1 bruger samme indhop-prior for alle.

## Hvad v2 gør

Spilletiden deles i tre trin, og hvert trin estimeres for sig:

1. **P(start).** Vægtet andel af tidligere kampe, hvor spilleren startede.
2. **P(indhop | ikke start).** Vægtet andel af de kampe, hvor spilleren ikke startede, men kom ind.
3. **Minutter givet rolle.** Ved start: sandsynlighed for at spille hele kampen (90 minutter) og ellers et gennemsnit for, hvornår spilleren bliver skiftet ud. Ved indhop: gennemsnitlige indhopminutter.

Detaljer:

- **Nyere kampe vægter mest.** Vægten halveres for hver 5 kampe bagud (halveringstid 5 kampe).
- **Positionspriors fra data.** For hver position samles alle spilleres tidligere kampe før prognosetidspunktet. Herfra beregnes positionens startandel, indhopandel blandt ikke-starter, andel hele kampe blandt starter, minutter ved tidlig udskiftning og indhopminutter. Spillerens egne tal trækkes mod positionens tal med en styrke svarende til 2 kampe. Målmænd får dermed automatisk en indhopchance tæt på 0.
- **Hele kampe trækkes for sig.** Ved start trækkes først, om spilleren spiller hele kampen (90 minutter). Hvis ikke, trækkes udskiftningstidspunktet fra en normalfordeling omkring spillerens gennemsnit for tidlige udskiftninger, spredning 12, klippet til 1–88. Gennemsnittet bliver dermed det, data viser, uden afklipningsbias.
- **Tilbage efter fravær.** Hvis spilleren har misset mindst de 2 seneste kampe (0 minutter), og FPL nu melder spilleren fuldt klar, tolkes de missede kampe som fravær og ikke som tabt plads. De tæller ikke med i rolleestimatet. Første kamp tilbage får startchancen ganget med 0,7; resten flyttes til indhop. Reglen kan kun bruges i live-prognoser, fordi FPL's historiske skadesstatus ikke er gemt. I den retrospektive udviklingsevaluering er den derfor slået fra.
- **Skadesstatus.** FPL's officielle chance for at spille ganges på, præcis som i v1.
- **Fallback.** Spillere uden mindst 2 komplette, endelige historikrækker med kendt start beholder v1's tal og markeres med fallback.

## Faste parametre

| Parameter | Værdi |
|---|---:|
| Halveringstid for vægte | 5 kampe |
| Prior-styrke, formniveau (seneste kampe mod spillerens sæson) | 2 kampe |
| Prior-styrke, sæsonniveau (sæson mod v1-prior 45 % / positionens tal) | 1 kamp |
| Hel kamp | 89 minutter eller mere |
| Spredning for tidlig udskiftning | 12 minutter |
| Startchance-faktor efter fravær | 0,7 |
| Fravær kræver | mindst 2 kampe i træk med 0 minutter og FPL-status fuldt klar |

## Evaluering

Prospektivt på GW12–15 mod `component_baseline_v1` efter protokollens kriterier: lavere point-CRPS samlet og lavere minut-MAE for `regular`, uden at nogen blokeringsgrænse overskrides. En retrospektiv kørsel på GW3–10 må kun bruges som kontrol af, at modellen virker teknisk. Den er ikke evidens og må ikke føre til ændringer i tabellen ovenfor.

Prognoser med v2 skal gemmes før hver deadline, ligesom med standardmodellen, og med samme seed og antal scenarier.

## Ændringer

**15. november 2026, før nogen prospektiv runde: én designrettelse efter den tekniske kontrol.**

Den tekniske kontrol på GW3–10 viste, at den første udgave gav faste spillere omkring 11 minutter for lidt (minut-MAE 26,2 mod 20,8 for v1). Årsagen var en designfejl, ikke en kodefejl. Positionens startandel blev beregnet over hele truppen, også reserver, der næsten aldrig spiller. Udgangspunktet blev derfor kun 28–44 %. Med få kampe og vægte under 1 trak modellen faste spillere langt ned mod det tal. En angriber med 2 starter i 2 kampe fik 63 % startchance; v1 giver 82 %. Indhopchancen for ikke-startende midtbanespillere blev også for høj (30 %), fordi den ikke tog højde for spillerens egen sæson.

Rettelsen har to niveauer i stedet for ét:

1. **Sæsonniveau.** Spillerens egne tal for hele sæsonen, uden vægte. Startchancen trækkes mod v1's faste prior (45 %, styrke 1 kamp), præcis som i v1. De øvrige trin (indhop når spilleren ikke starter, hel kamp, udskiftningsminutter, indhopminutter) trækkes mod positionens tal med styrke 1.
2. **Formniveau.** De vægtede seneste kampe (halveringstid 5) trækkes mod spillerens sæsonniveau med styrke 2.

Alt andet er uændret: tre trin, halveringstid 5, hel kamp trukket for sig, spredning 12, fravær og faktor 0,7. Kandidaten fryses efter denne ene rettelse, uanset hvad den næste tekniske kontrol viser, medmindre den afslører en egentlig programmeringsfejl. Resultatet af kontrollen noteres herunder, men er stadig ikke evidens.

**Teknisk kontrol efter rettelsen, GW3–10, seed 42, 1.000 scenarier, 4.744 fælles spiller-GW-rækker.** Udviklingsdata, ikke evidens.

| | v1 | v2 |
|---|---:|---:|
| Point-CRPS, alle | 0,800 | 0,788 |
| Point-MAE, alle | 1,313 | 1,227 |
| Minut-MAE, alle | 17,6 | 14,5 |
| DNP-Brier, alle | 0,116 | 0,110 |
| Point-CRPS, `regular` (1.332 rækker) | 1,689 | 1,692 |
| Point-MAE, `regular` | 2,518 | 2,553 |
| Minut-MAE, `regular` | 20,8 | 17,2 |
| Minut-bias, `regular` | −1,9 | +3,9 |
| DNP-Brier, `regular` | 0,080 | 0,079 |

Det simple gennemsnit af tidligere minutter har minut-MAE 15,7 for `regular` på de samme rækker, så v2 slår det stadig ikke for faste spillere. v2 overvurderer nu faste spilleres minutter lidt, hvor v1 undervurderede dem. Point-CRPS for `regular` er næsten uændret. Gevinsten ligger mest hos de øvrige spillere.

Kandidaten er hermed frosset. Den prospektive afprøvning på GW12–15 afgør, om den accepteres.

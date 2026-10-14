# Mit hold: standardprognose og chips

Hovedsiden bruger `component_baseline_v1` med uændrede modelparametre. Modelvarianter,
oddsvalg og bonus-/prior-/assistforsøg findes under **Analyse og eksperimenter →
Transferlaboratorium**. Den tidligere analyseside findes under **Prognoser og evaluering**.
Baseline er et stabilt udgangspunkt, ikke dokumenteret bedst i alle situationer.

## Brug

1. Åbn Mit hold og Redigér hold. Bekræft dine resterende chips og første spille-GW
   under **Mine chips**. Gamle holdprofiler starter med ukendt chipstatus.
2. Gem holdet. Det gemmes kun lokalt; appen aktiverer aldrig en chip på FPL.
3. Vælg 1–4 GWs og **Transfers uge for uge**. Vælg en chip pr. ønsket GW under
   **Chips i denne plan**. Ingen chip er standard.
4. Sammenlign forslagene. Rapporten indeholder behold, almindelige transferplaner
   og planer med de valgte chips. Se aktive/permanente trupper, bank, FT, hits og
   opstillinger. Resultaterne gemmes under den eksisterende ignorerede artifactmappe.

En allerede aktiv chip skal registreres med dens GW. Planen uden chip er da kun en
hypotetisk reference og kan ikke blive anbefalet som en mulig handling.

## Regler og beregning

- **Triple Captain:** to ekstra kopier af kaptajnens point i stedet for én. Vice
  overtager ved kaptajnens manglende deltagelse. Negative point tredobles også.
- **Bench Boost:** alle 15 spilleres point plus almindelig kaptajnbonus; ingen ekstra
  autosub-point oveni. Kandidatsøgningen værdisætter hele truppen i chipugen.
- **Wildcard:** permanente transfers uden hits. Bank og salgsværdier finansierer
  omlægningen; budgettet bliver ikke nulstillet til £100m.
- **Free Hit:** midlertidig trup. Permanent trup, bank og anskaffelsesgrundlag genskabes
  efter runden. Det gælder også en Free Hit i horisontens sidste GW.
- WC/FH bevarer opsparede gratis transfers uden ny optjening i chipugen. Andre uger
  følger det eksisterende regnskab med loft på fem FT og fire point pr. ekstra transfer.
- WC/FH-omlægninger tæller ikke mod brugerens maksimum for almindelige transfers.
- En chip pr. GW og en af hver slags pr. sæsonhalvdel. Verificerede regler gælder
  2026/27: første sæt GW1–19, andet GW20–38. Ingen WC/FH i ens første spille-GW.
  FH kan ikke bruges i to på hinanden følgende GWs, heller ikke GW19/20.

Hvis der allerede er foretaget transfers før første-GW WC/FH, kræves den bekræftede
trup, bank, FT og eksisterende hits fra før ugens handler. Den kan indtastes som JSON
under Mine chips. Penge er heltal i £0,1m, og spillere identificeres med officielle
FPL-ID'er. Manglende oplysninger gættes ikke. Almindelige forslag fungerer uden denne
historik. Allerede afholdte hits er kun med i rapporten, når de er eksplicit registreret;
ellers beskriver almindelige forslag point efter nye hitomkostninger.

## Begrænsninger

Chipuger vælges manuelt. Der er endnu ingen automatisk chipkalender frem til GW19.
Prognoser og fremtidige priser genbruges gennem den valgte korte horisont. Senere
skader, prisændringer og nye nyheder simuleres ikke som en komplet fremtidig proces.

Alle planer bruger samme spillerprognoser og evalueringsscenarier. Chips ændrer ikke
spillernes rå xP. XI, bænk og anfører/vice vælges på separate planlægningsscenarier.
MILP finder kandidattrupper med en tilnærmet målfunktion; den efterfølgende præcise
opstillingssøgning garanterer ikke globalt bedste transfertrup. Solver-gap vedrører
kandidatsøgningen. Chipgevinsten mod bedste fundne plan uden chips er betinget af
horisonten, modellen og de fundne kandidater, ikke chipværdien over hele sæsonen.

Regelkilder kontrolleret 14. oktober 2026:
- https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627
- https://www.premierleague.com/es/news/4661029

Officiel deadline bruges fra snapshot; kalenderdatoer fra artikler hardcodes ikke.

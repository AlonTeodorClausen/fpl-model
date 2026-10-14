# Transferstrategier og tilgængelighed pr. GW

## Brug
Åbn appens **Mit hold**, indlæs/redigér holdet og vælg 1–4 GWs. **Transfers uge for uge** er standard. Vælg maksimum pr. GW og samlet maksimum, behold/udeluk og om hits er tilladt. **Alle transfers nu** bevarer det tidligere forløb.

Der vises en behold-reference uden nogen transfers og bedste fundne fortsættelse for hvert lovligt antal transfers nu. 0 nu er derfor en anden strategi end behold i hele horisonten. Låsninger gælder hele horisonten; en udelukket ejet spiller skal ud i første GW. Behold-referencen er altid uændret.

Hver plan viser ud/ind, bank, køb/salg, FT før/efter, hits samt XI, ordnet bænk, anfører og vice for alle GWs. Anbefalingen følger optimizerens målværdi. Simulerede holdpoint inklusive autosubs er en separat evaluering i fælles scenarier, med gevinst mod behold-holdet under samme forudsætninger. Solverstatus og gap vises; tidsbegrænsede løsninger kaldes ikke bevist optimale.

## Regnskab og optimering
MILP vælger trup, køb, salg, XI og anfører for hver GW i én samlet optimering. Bank må ikke være negativ i nogen GW; fremtidige salg kan ikke finansiere køb nu. Brugerens aktuelle salgsværdi gælder, indtil den oprindelige beholdning sælges. Genkøb og senere videresalg bruger den faste markedspris, så gamle salgsrabatter ikke fejlagtigt genanvendes.

Gratis transfers føres som eksakte tilstandsovergange: én ny pr. GW, maksimum fem; hver transfer ud over tilgængelige FT koster fire point i den relevante GW. Allerede foretagne transfers tæller mod første GWs cap; tidligere betalte hits er fælles og medregnes ikke igen. Ingen chips. Reglerne følger den allerede verificerede [officielle transferbeskrivelse](https://www.premierleague.com/en/news/2174907/fpl-basics-explained-how-to-make-transfers).

Alle GWs vægtes ens. Målværdien er XI-xP + ekstra anfører-xP + 0,1 × bænk-xP minus hits. Priser og klubidentitet holdes faste. Nuværende information bruges til alle uger; optimeringen må ikke reagere på fremtidige simulerede udfald. Genberegn efter nye data. Der sættes ingen kunstig pointværdi på FT efter horisontens slutning, og den ukendte informationsværdi af at vente optimeres ikke.

## FPL-nyheder og manuelle antagelser
Skadespanelet viser snapshot-ID, hentetid, status, `chance_of_playing_next_round`, `news` og `news_added` fra de allerede gemte officielle data. `news_added` er et kildefelt og bruges ikke til at backfille historisk tilgængelighed. Ingen automatisk scraping eller tekstfortolkning.

En tom manuel faktor betyder uændret FPL-faktor. En eksplicit faktor mellem 0 og 1 erstatter den eksisterende faktor, frem for at multiplicere den endnu en gang. 0 betyder ude; 1 betyder ingen ekstra reduktion af modellens historikbaserede start-/indhopchance. Det er ikke 100% startchance. Betingede minutter og angrebs-/forsvarsformler ændres ikke. Historikken kan allerede afspejle tidligere skadesfravær; faktoren gør ikke historiske frekvenser til en estimeret frekvens for en fuldt rask spiller.

Manuelle antagelser kræver begrundelse og registreringstid <= forecast-origin. Valgfrit kildelink gemmes uden automatisk hentning. De gemmes pr. spiller/GW i prognosecache og rapport; rå snapshots omskrives ikke. Ingen automatisk raskmelding ud fra en manglende returdato. Uden override videreføres den nuværende faktor til senere GWs og mærkes som antagelse.

Baseline er uændret ved fravær af overrides. Scenarier får en særskilt modelversion med `__manual_availability_v1`. En ændring for én spiller bevarer alle andre spilleres tilfældighedsstrøm og simulerede udfald. De to scenarier bruger samme seedstrategi, draws og øvrige inputs. Der er stadig ikke en sammenhængende simuleret helbredsproces mellem GWs.

## Følsomhed
Vælg én spiller og to mulige tilbagekomst-GWs. A/B er eksplicit hypotetiske: faktor 0 før tilbagekomst, 1 fra tilbagekomst; ingen antaget optrapning af betingede minutter. Disse scenarier erstatter den valgte spillers øvrige manuelle faktorer. A er hovedrapporten; B vises separat og gemmes med alle opstillinger og inputreferencer.

Rapporten viser både:
- A-planerne fastholdt og vurderet i B, med en B-specifik behold-reference.
- Nye optimerede B-planer og om de anbefalede køb/salg **nu** ændres.

Sammenligningen afviser ændringer i snapshot, inputreferencer, odds, model/kode, konfiguration, origin, GWs, seed og simulationsantal. Kun tilgængelighedsantagelser må variere. Dette er beslutningsfølsomhed, ikke ny information, kalibrering eller dokumenteret forbedring.

## Lokal verifikation 2026-10-09
Offline tests dækker kontantbudget pr. GW, salg/genkøb, opsparede FT, hits, locks, udelukkelser, inputrækkefølge, uændret baseline, isolerede tilfældighedsstrømme, provenance og appforløbet.

En kørsel på brugerens gemte hold og eksisterende snapshots af 6. oktober brugte GW6–9, 3.000 scenarier, seed 42, højst to transfers pr. GW og fire i alt, uden hits. Odds: 10/10, 10/10, 0/10, 0/10; de sidste to GWs bruger baseline-fallback. Ingen nye downloads. Hypotetisk tilbagekomst af João Pedro blev afprøvet separat, ikke som officiel nyhed. Resultater og profiler forbliver lokale/gitignored.

Verifikation afsluttet: **675 tests bestået, 5 live-tests fravalgt**. Uændrede baseline-point, minutter og forklaringer blev desuden sammenlignet bit-for-bit med den committede simulation for to seeds. Det fokuserede review fandt ét provenancehul i følsomhedskontrollen; det er rettet og dækket af regressionstest.

Den gemte kørsel på eksisterende data gav 234,08 simulerede point ved behold, 249,21 for 0→2→1→1 og 249,48 for 1→1→1→1. Begge transferplaner havde solver-gap 0. Forskellen på 0,27 point er lille og er ikke sikker evidens for, at det er bedre at handle nu. Data er fra 6. oktober; dette er en test af arbejdsgangen, ikke en opdateret anbefaling baseret på nye skadesnyheder.

## Opdatering: næste-runde-flag er ikke en permanent skadesprognose
Appen tilbyder nu to eksplicitte horisontpolitikker. Ved mere end én GW foreslår brugerfladen **Scenarie: 75%-tvivl ophører efter første GW**. Det ændrer kun spillere med officiel status `d` og præcis 75% til næste runde. Første GW beholder den officielle faktor; senere GWs får faktor 1. Dette er en synligt mærket planlægningsantagelse, ikke en udledt returdato, medicinsk prognose eller kalibreret sandsynlighed. Den gælder hele spillerpuljen efter samme regel. Lavere/ukendte spillechancer, øvrige skadesflag og karantæner nulstilles ikke automatisk.

**Forsigtig: viderefør nuværende FPL-faktor** bevarer den tidligere adfærd. `forecast_bundle` har fortsat denne forsigtige standard ved programmatisk brug, og selve `component_baseline_v1` er uændret. Scenariet mærkes med `__short_doubt_scenario_v1` og gemmer hver berørt spiller/GW, den oprindelige faktor og begrundelsen separat fra manuelle antagelser. Manuel faktor har forrang i begge politikker. Rå nyheder/status omskrives aldrig.

Spillerforklaringen i strategirapporten viser faktor, startchance pr. kamp, historikkampe, forventede minutter og xP pr. GW. Faktor 1 fjerner kun den ekstra skadesreduktion; historiske frekvenser kan allerede indeholde fravær, og spilleren kan stadig blive valgt til bænken. Ved væsentlige transferbeslutninger bør begge politikker sammenholdes. Ingen automatisk læsning af pressekonferencer eller påstand om verificeret raskmelding.

## Autosub-aware opstillingsvalg (9. oktober 2026)
Den tidligere vægtede bænk bruges nu kun til at generere kandidattrupper/transfersekvenser. For hver funden trup og GW gennemgås alle **3.300 lovlige XI/bænkrækkefølger**, inklusive begge målmænd. Alle lovlige anfører/vice-par sammenlignes også. Målværdien er gennemsnitlige holdpoint inklusive lovlige autosubs, anfører og vice, minus eventuelle hits. En opstilling vælges før udfaldet og fastholdes i alle scenarier.

Algoritmen samler identiske deltagelsesmønstre og deres point, så også sammenhængen mellem point og fravær bevares. Formationskrav kontrolleres ved hver reserve; en spiller, der spiller få minutter, blokerer autosub præcis som enhver anden deltagelse. DGW-deltagelse bygger på, om spilleren spillede i mindst én af rundens kampe. Målmænd udskiftes kun med målmand. De valgte resultater kontrolleres mod den eksisterende holdevaluator.

Planlægning bruger de allerede beregnede prognosescenarier fra `SeedSequence([seed, event, 0])`. Evaluering bruger fortsat den separate strøm med sidste indeks 1. Begge gemmes nu i cache. Ældre caches uden planlægningsscenarier må genberegnes fra de samme snapshots; evalueringsscenarier må aldrig bruges som erstatning. Ingen forecast-parametre eller nye datakilder er tilføjet.

Samme metode bruges til behold-holdet, alle transferkandidater og følsomhedsscenarier. Anbefalingen rangerer behold og de fundne kandidater efter planlægningspoint, ikke evalueringspoint. Rapporten gemmer den tidligere opstilling og kandidatsøgningens målværdi separat samt nye opstillinger og gevinst ved ændret opstillingsvalg. Solver/gap beskriver fortsat kun MILP-kandidatsøgningen. Der påstås **ikke globalt optimale transfertrupper** under autosub-målet, og ingen statistisk sikker forbedring eller ny modelkalibrering.

På de uændrede snapshots/prognoser fra 9. oktober (3.000 scenarier, seed 42, GW6–9) ændres behold-holdets GW6-opstilling til João Pedro i XI, Gvardiol som første markreserve og B. Fernandes som vice. De Cuyper er fortsat anfører. Separate evalueringspoint går fra 55,673 til 56,122 i GW6; over fire runder fra 235,445 til 236,282. Alle spillerprognoser er verificeret identiske med den forrige rapport. Aktuel rapport og teknisk verifikation ligger lokalt under `artifacts/autosubs_20261009/`.

Verifikation: 683 offline-tests bestået; fem live-tests fravalgt. Nye tests dækker DNP-bænkdækning, indhop som blokerer autosub, flere fravær og vice, deterministisk rækkefølge, overensstemmelse med eksisterende pointberegning samt at ændrede evalueringsscenarier ikke kan ændre opstillinger/anbefalinger.

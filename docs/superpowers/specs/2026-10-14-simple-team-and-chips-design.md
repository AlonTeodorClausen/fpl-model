# Mit hold: standardprognose og manuelle chips

Status: konkret design til godkendelse. Ingen produktkode er ændret.

## Formål og afgrænsning

Brugeren skal kunne få en transferanbefaling uden at vælge mellem forskningsmodeller.
Første leverance understøtter alle fire chips med manuelt valgt GW i den eksisterende
1–4-GW-plan. Automatiske chipplaceringer og strategi helt til GW19 er næste leverance.
Hovedsiden må ikke fremstille den korte plan som en fuld GW19-optimering.

Ingen nye modelkomponenter, downloads, parameterændringer eller ændringer af snapshots.
Eksisterende lokale hold, rapporter og eksperimenter skal fortsat kunne åbnes.

## Eksisterende dele, der genbruges

- `ui/my_team.py`: holdeditor, lokal lagring, datavalg, transferforslag og resultatvisning.
- `transfer_planner.forecast_bundle`: prognoser og cache pr. datagrundlag, konfiguration,
  horisont og origin. Chips ændrer holdevaluering, ikke spillernes rå prognoser.
- `optimizer/transfer_sequences.py`: fælles MILP for køb/salg, bank, gratis transfers og
  lovlige trupper. I dag ingen chips og højst fire GWs.
- `optimizer/lineup.py`: opstillingsvalg inklusive autosubs på separate planlægningsscenarier.
- `optimizer/squad.py`: scenariebaseret pointberegning, anfører/vice og lovlighed.
- `sequence_planner.py`: behold-reference, alternative førsteugestransfers, separat
  evaluering og rapportering. Solver-gap gælder fortsat kun kandidatsøgningen.

## Hovedside og modeller

Hovedsiden viser **Standardprognose** med `component_baseline_v1`, uændret konfiguration
og alle model-eksperimenter slået fra. Der vises datatidspunkt, faktiske antagelser om
tilgængelighed og et link til Analyse og eksperimenter. Baseline kaldes ikke bevist bedst.

De seks modelvalg og ekstra bonus-/prior-/assistforsøg flyttes til analysesiden med
genbrug af de eksisterende beregningsfunktioner. Gemte oddsrapporter bevarer deres
modelnavn og provenance; de ommærkes aldrig til Standardprognose.

Øvrige valg på hovedsiden: horisont, transfergrænser, hits, behold/udeluk og chips.
Scenarier/seed og tekniske indstillinger ligger under avancerede indstillinger.
Ingen datahentning eller simulation starter ved en almindelig Streamlit-genkørsel.

## Chipbeholdning og brugervalg

Gem en versionsmærket, sæsonbundet chipstatus i den lokale holdprofil. Hver af de to
sæsonhalvdele har fire chips med status `available`, `used` eller `unknown`; brugt GW
kan angives. Gamle profiler indlæses med ukendt status, aldrig automatisk fire ledige chips.
Ukendt status blokerer valg af den pågældende chip, men ikke almindelige transferforslag.

Brugeren kan vælge Ingen chip eller en tilgængelig chip pr. GW i den aktive horisont.
Flere chips i forskellige GWs er tilladt. Én chip pr. GW, ingen gentagelse af samme
chip fra samme sæt, og ingen Free Hit i på hinanden følgende GWs, heller ikke GW19/20.
Deadline og sæson kommer fra officiel kontekst; en udløbet deadline kan ikke vælges.
Wildcard og Free Hit er ikke tilgængelige i holdets første GW. Ukendt første-GW-status
kræver manuel bekræftelse før disse chips kan vælges.

Regler for sæson 2026/27: første sæt kan bruges i GW1–19, andet sæt GW20–38. Ukendt
sæsons regelsæt skal give tydelig fejl frem for at genbruge regler uden verifikation.
Oversigten viser udløb ved officiel GW19-deadline og antal ledige chips; den anbefaler
ikke automatisk en chipuge endnu.

## Fælles regnskab og begrænsninger

Tilføj ét genbrugeligt chipregelsæt med validering og ugentlige tilstandsovergange.
Reglerne bruges af planner, eftervalidering og rapporter, ikke af UI alene.
En uge har både en permanent trup/bank og en aktiv pointgivende trup/bank.
Uden Free Hit er de to identiske. Priser antages fortsat faste, salgsværdier eksplicitte.

Almindelige transfers bruger eksisterende FT/hit-regler. WC/FH-transfers giver ingen
hits og bruger ikke opsparede gratis transfers. FT-beholdningen føres uændret videre
fra chipugen, uden den almindelige ekstra optjening i den uge. TC/BB bruger almindelige
transferregler. Allerede påløbne hits skal holdes særskilt fra nye hitomkostninger.

De almindelige maksimumgrænser for transfers gælder almindelige transfers; WC/FH-omlægning
vises særskilt og begrænses ikke af eksempelvis maks. to almindelige transfers pr. GW.
Alle trupper skal overholde budget, positioner og klubgrænser. Behold/udeluk gælder aktive
trupper i alle valgte GWs; en spiller kan derfor vende tilbage fra FH i den permanente
trup, men skal sælges, hvis udelukkelsen fortsat skal overholdes i næste aktive trup.
Umulige kombinationer giver en konkret forklaring.

Eksisterende profil indeholder kun nuværende bank, salgsværdier, resterende FT og antal
foretagne transfers. Den kan ikke rekonstruere tilstanden før allerede udførte handler.
Ved WC/FH i første GW og `transfers_made > 0` kræves derfor en særskilt manuelt bekræftet
tilstand fra før ugens handler: trup/salgsværdier/bank/FT og eksisterende hits.
Uden disse oplysninger afvises chipberegningen med præcis forklaring; almindelig plan
virker fortsat. Ingen historik eller tilbagebetalingsværdi må gættes. En aktiv chip på
FPL skal også bekræftes, så den ikke behandles som stadig frit tilgængelig.

## Chipberegning

**Triple Captain:** den normale ekstra anførerkopi bliver til to ekstra kopier. Vice
overtager ved kaptajnens manglende deltagelse efter eksisterende regler. Chippen indgår
både i kandidatmålet, det præcise opstillingsvalg og den separate evaluering.

**Bench Boost:** alle 15 spilleres point tæller én gang plus almindelig anførerbonus.
Ingen yderligere autosub-point lægges oveni. Lovlig XI og anfører/vice vælges stadig.
Kandidatsøgningen værdisætter hele truppen i chipugen, ikke kun den nuværende bænkvægt.

**Wildcard:** køb/salg ændrer den permanente trup. De gamle spillere finansierer indkøb
med faktiske salgsværdier; modellen nulstiller ikke budgettet til £100m. Bank, nyt
ejerskab og anskaffelsesgrundlag følger med ind i senere GWs.

**Free Hit:** optimizer vælger en midlertidig aktiv trup finansieret af den permanente
trups salgsværdi og bank. I næste GW gendannes permanent trup, bank og oprindelige
salgsværdier under antagelsen om faste priser. Midlertidige køb må ikke skabe overskud
eller påvirke permanente anskaffelsesgrundlag. Også en FH i horisontens sidste GW
skal have en eksplicit terminal tilstand, der viser tilbageførslen.

## Sammenligning, cache og rapporter

Prognoser beregnes én gang og genbruges i alle planer. Plan- og lineupcache udvides med
chipplan, chipbeholdning og relevante profilversioner. Chips må ikke genbruge et cached
lineupresultat fra en uge uden chip. Model- og planner-versioner gemmes separat.

Vis behold-holdet uden chips, bedste almindelige transferplan og forslag med brugerens
chipplan på samme prognoser og separate evalueringsscenarier. Vis både gevinst mod
behold og forskel til bedste fundne plan uden chips. Chipforskellen er betinget af den
valgte horisont og begrænsede kandidatsøgning; den er ikke en global optimal chipværdi.
Hvis chippen allerede er aktiv og bindende på FPL, markeres alternativet uden chip som
en hypotetisk reference, ikke som en handling brugeren stadig kan vælge.

Førsteuges-WC/FH har ét forslag om fri omlægning; undgå at køre 16 næsten identiske
pakker for 0–15 transfers. Senere chipuger optimeres sammen med ugentlige transfers.

Rapport pr. GW: chip, aktive/permanente trupper, ud/ind, bank, gratis transfers før/efter,
hits, XI/bænk/anfører/vice, kandidatmål, opstillingsmål og simulerede point. BB-bænkpoint
benævnes BB-bidrag, ikke autosubs. Rapporter indeholder chipstatusens kilde og antagelser.
Gamle rapporter vises uændret og kræver ikke et nyt chipfelt.

## Verifikation og færdigkriterier

1. Gamle profiler/rapporter kan indlæses; ingen lokal profil overskrives uden Gem hold.
2. Hovedsiden har ét standardmodelvalg; alle eksisterende analysefunktioner kan stadig nås.
3. TC testes med spillende anfører, fraværende anfører, fraværende vice og negative point.
4. BB tester alle 15 præcis én gang, kaptajnbidrag og ingen dobbelttælling af autosubs.
5. WC tester permanent ejerskab, faktiske salgsværdier, bank og uændret opsparet FT.
6. FH tester tilbageførsel inkl. anskaffelsesgrundlag, FT og sidste-GW-terminal tilstand.
7. Regler tester én chip/GW, sæsonhalvdele, ukendt/brugt chip, første GW og FH19/FH20.
8. Manglende historik før allerede udførte WC/FH-handler giver eksplicit blokering.
9. Plan og evalueringscache skelner chips. Ingen-chip-resultat matcher tidligere adfærd.
10. Parrede sammenligninger bruger samme forecast/scenarier; chips ændrer ingen spillerforecast.
11. Kør relevante offline-tests, derefter fuld offline-suite og Streamlit-appkontrol med
    eksisterende data. Kontrollér en komplet gem/genindlæs/beregn/vis-gang uden netværk.

## Senere leverance: GW19-strategi

Automatisk placering af chips og længere horisont implementeres efter denne leverance.
Den får nær beslutningshorisont på 3–4 GWs og strategisk kalender frem til GW19, med
ugentlig genplanlægning. Ingen garanti om fremtidig skadesstatus, priser eller odds.
Terminal værdi af trup og FT skal designes og efterprøves før en lang plan anbefales;
ingen skjult arbitrær værdi tilføjes i denne leverance.

## Regelkilder

Kontrolleret 14. oktober 2026:
- https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627
- https://www.premierleague.com/es/news/4661029

Deadlines hentes fortsat fra gemt officiel API-kontekst, ikke fra artiklers kalenderdatoer.

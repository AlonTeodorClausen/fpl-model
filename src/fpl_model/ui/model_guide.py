"""Read-only, code-grounded methodology for the forecast and decision model."""
import streamlit as st

from fpl_model.models.baseline import BaselineConfig, model_version, player_parameters


_VARIANTS = {
    'component_baseline_v1': 'Standardprognose',
    'component_defensive_odds_v1': 'Odds kun til forsvar',
    'component_attacking_odds_v1': 'Odds til angreb og forsvar',
    'component_role_minutes_v1': 'Forsøg med nylig spillerrolle',
    'component_role_transitions_v2': 'Forsøg med rolleskift i spilletid',
    'component_shared_goals_v1': 'Forsøg med fælles holdmål',
    'component_minutes_v2': 'Minutmodel v2 (afprøves)',
}


def worked_minutes_example(config):
    """Six complete fixtures, evaluated by the same parameter code as live forecasts."""
    rows = [dict(event=1, fixture_id=i, minutes=m, starts=s)
            for i, (m, s) in enumerate([(90, 1), (85, 1), (80, 1), (75, 1), (20, 0), (0, 0)], 1)]
    baseline = player_parameters(dict(element_type=3, status='a'), rows, 6, config)
    doubtful = player_parameters(dict(element_type=3, status='d',
                                      chance_of_playing_next_round=75), rows, 6, config)
    return dict(p_start_before_status=baseline['p_start'],
                p_sub_before_status=baseline['p_sub'],
                p_dnp_before_status=1-baseline['p_start']-baseline['p_sub'],
                p_start_after_status=doubtful['p_start'],
                p_sub_after_status=doubtful['p_sub'],
                p_dnp_after_status=1-doubtful['p_start']-doubtful['p_sub'],
                start_minutes=baseline['start_minutes'], sub_minutes=baseline['sub_minutes'])


def _position_priors(config):
    rows = []
    for pos, label in ((1, 'Målmand'), (2, 'Forsvarer'), (3, 'Midtbane'), (4, 'Angriber')):
        rates = player_parameters(dict(element_type=pos), [], 0, config)['explanation']['rates']
        rows.append(dict(Position=label, **{'xG/90-prior': rates['goals']['prior_per90'],
                                           'xA/90-prior': rates['assists']['prior_per90']}))
    return rows


def _decimal(value, places=3):
    return f'{value:.{places}f}'.replace('.', ',')


def render():
    config = BaselineConfig()
    standard = model_version(config)
    st.title('Sådan virker modellen')
    st.markdown(f'**Standard på Mit hold:** `{standard}` — en parametrisk Monte Carlo-model '
                'uden odds eller løbende ML-træning. Analyse og eksperimenter ændrer ikke standarden.')
    for key, area in (('transfer_result', 'Mit hold'), ('lab_transfer_result', 'Analyse og eksperimenter')):
        report = st.session_state.get(key)
        forecast = report.get('forecast') if isinstance(report, dict) else None
        if isinstance(forecast, dict) and forecast.get('model_version'):
            version = forecast['model_version']
            st.markdown(f'**Åbent forslag under {area}:** '
                        f'{_VARIANTS.get(version, "Forsøgsvariant")} (`{version}`).')
    st.markdown('**Det estimerede objekt:** en diskret fordeling af FPL-point for spiller $i$ '
                'i gameweek $g$, $Y_{ig}$. Modellen estimerer først spilletid og hændelsesrater, '
                'simulerer dernæst point og overlader holdvalget til en separat optimizer.')

    with st.expander('1 · Data og informationssæt', expanded=True):
        st.markdown('**Datakilder i standardmodellen:** Officiel FPL API leverer '
                    '`bootstrap-static`, `fixtures` og spillerens `element-summary`. '
                    'The Odds API bruges kun, når en oddsvariant er valgt.')
        st.dataframe([
            {'Input': 'Officiel FPL API · bootstrap-static', 'Niveau': 'Spiller/hold/GW',
             'Brug': 'ID, position, pris, status og deadlines'},
            {'Input': 'Officiel FPL API · fixtures', 'Niveau': 'Kamp',
             'Brug': 'Hjemme/ude, kickoff, GW og tidligere resultater'},
            {'Input': 'Officiel FPL API · element-summary', 'Niveau': 'Spiller × kamp',
             'Brug': 'Minutter, starter, xG/xA og øvrige hændelser'},
            {'Input': 'The Odds API · William Hill (valgfri)', 'Niveau': 'Kamp × marked',
             'Brug': 'Kun forsøgsvarianter; 1X2 og over/under præcis 2,5'},
        ], hide_index=True, width='stretch')
        st.markdown('**Informationsmængden ved prognosen:** en historikrække skal være '
                    'observeret senest ved prognosetidspunktet (`available_at ≤ forecast_origin_at`). '
                    'Tidligere holdkampe skal være afsluttet. Data observeret efter den officielle '
                    'GW-deadline kan ikke bruges til den aktuelle prognose. Kampdatoen alene '
                    'dokumenterer ikke historisk tilgængelighed.')
        st.markdown('En eksplicit nulminuttersrække tæller som DNP. **En manglende række gør ikke.** '
                    'Hvis historikkens nævner er ufuldstændig, eller klubtilhørsforhold er uklart, '
                    'markeres fallback til sæsonaggregater eller positionspriorer. FPL Core og '
                    'football-data.org indgår ikke i standardprognosen. Hentetiderne for valgt '
                    'datagrundlag vises under **Mit hold → Data og hentetider**.')

    with st.expander('2 · Spilletid: frekvens, betingede minutter og skader'):
        st.markdown('Tidligere brugbare spiller-kampe klassificeres som start ($S$), indhop '
                    '($B$) eller eksplicit nul minutter. Med $N$ observationer og '
                    f'priorstyrke $\\kappa={config.frequency_prior_games:g}$ kamp:')
        st.latex(r'\widehat p_S=\frac{S+\kappa\pi_S}{N+\kappa},\quad '
                 r'\widehat p_B=\frac{B+\kappa\pi_B}{N+\kappa},\quad '
                 r'\widehat p_0=1-\widehat p_S-\widehat p_B.')
        st.markdown(f'Standardprioren er $\\pi_S={config.prior_start:.2f}$ for start, '
                    f'$\\pi_B={config.prior_sub:.2f}$ for indhop og '
                    f'${1-config.prior_start-config.prior_sub:.2f}$ for DNP. Formlen svarer '
                    'til en Dirichlet-posterior-middelværdi. Implementationen bruger kun '
                    'punktestimatet; parameterusikkerheden trækkes ikke fra posterioren.')
        x = worked_minutes_example(config)
        st.markdown('**Gennemregnet eksempel:** 6 komplette kampe med 4 starter, 1 indhop '
                    f'og 1 eksplicit DNP giver før skadefaktor '
                    f'`p_start = (4+0,45)/7 = {_decimal(x["p_start_before_status"])}`, '
                    f'`p_indhop = (1+0,10)/7 = {_decimal(x["p_sub_before_status"])}` og '
                    f'`p_DNP = {_decimal(x["p_dnp_before_status"])}`. Ved FPL-spillechance 75% '
                    f'ganges de to spilleudfald med 0,75: {_decimal(x["p_start_after_status"])} '
                    f'og {_decimal(x["p_sub_after_status"])}; DNP bliver '
                    f'{_decimal(x["p_dnp_after_status"])}. Faktoren er ikke en medicinsk '
                    'estimeret skadesmodel.')
        st.markdown(f'Minutter **givet** start/indhop udglattes separat mod '
                    f'{config.starter_minutes:g}/{config.sub_minutes:g} minutter med '
                    f'vægt svarende til {config.minutes_prior_games:g} observation. Eksemplet '
                    f'giver centre på {_decimal(x["start_minutes"], 1)} og '
                    f'{_decimal(x["sub_minutes"], 1)} minutter. Scenarier bruger afrundede '
                    'normaltræk omkring centrene (standardafvigelse 8 ved start, 9 ved indhop), '
                    'afgrænset til 1–90 og 1–59 minutter.')
        st.warning('**Kendt svaghed:** afgrænsningen ved 90 trækker gennemsnittet ned. En spiller, '
                   'der altid spiller hele kampen, har et center på omkring 89 minutter, men '
                   'næsten halvdelen af normaltrækkene ligger over 90 og klippes til 90. '
                   'Gennemsnittet bliver derfor omkring 86 minutter. Det passer med, at '
                   'standardmodellen undervurderer faste spilleres minutter med 1–3 minutter i GW8–10.')
        st.markdown('**Minutmodel v2 (afprøves på GW12–15).** Spilletiden deles i tre trin: '
                    'chancen for at starte, chancen for at komme ind *når spilleren ikke starter*, '
                    'og minutter givet rollen. Nyere kampe vægter mest: vægten halveres for hver '
                    '5 kampe bagud. Hvert trin trækkes mod positionens tal fra alle spilleres '
                    'tidligere kampe, med en styrke svarende til 2 kampe, så en målmand, der '
                    'ikke starter, næsten aldrig kommer ind. Ved start trækkes først, om '
                    'spilleren spiller hele kampen; ellers trækkes udskiftningstidspunktet. '
                    'Dermed forsvinder afklipningsfejlen. Har spilleren misset mindst de 2 seneste '
                    'kampe og er nu meldt klar, tæller fraværet ikke som tabt plads, men første '
                    'kamp tilbage får startchancen ganget med 0,7.')
        st.caption('v2 kan vælges i Transferlaboratoriet. Parametrene er fastlagt før evaluering '
                   'og må ikke justeres undervejs; se notes/minutes_v2.md.')
        st.caption('Manglende kampvis historik bruger aktuelle sæsonaggregater som proxy, '
                   'hvis de findes; ellers eksplicitte priors. Ukendt skadechance ved visse '
                   f'FPL-statusser giver faktor {_decimal(config.injury_unknown_factor, 2)}. Fremtidige '
                   'skadeforløb er synlige planlægningsscenarier, ikke forudsagte raskmeldinger.')

    with st.expander('3 · Spillerintensiteter og holdmål'):
        st.markdown('Spillerens kampvise **xG og xA** bruges som henholdsvis mål- og '
                    'assistintensitet. For hændelse $k$, observeret sum $C_{ik}$ og '
                    'eksponering $E_i$ i 90-minuttersenheder:')
        st.latex(r'\widehat r_{ik}=\frac{C_{ik}+\alpha\pi_{k,\mathrm{pos}(i)}}'
                 r'{E_i+\alpha},\qquad \alpha=3.')
        st.markdown('Prioren svarer til tre fulde kampe med positionens standardrate. '
                    'For mål/assists er $C$ forventede hændelser (xG/xA), ikke faktiske '
                    'scoringer. Andre hændelser udglattes fra deres egne observerede antal.')
        st.dataframe(_position_priors(config), hide_index=True, width='stretch')
        st.markdown(f'Holdstyrke estimeres fra tidligere **scorede og indkasserede mål**. '
                    f'Ligagennemsnittet er $m=({config.home_goals:.2f}+'
                    f'{config.away_goals:.2f})/2$. Med $k={config.team_prior_games:g}$ '
                    'pseudokampe er $A_t=(GF_t+km)/(n_t+k)/m$ og '
                    '$D_t=(GA_t+km)/(n_t+k)/m$. Kampens målrater er:')
        st.latex(r'\lambda_H=\operatorname{clip}(H A_H D_A,\,0.15,\,4.5),\qquad '
                 r'\lambda_A=\operatorname{clip}(A A_A D_H,\,0.15,\,4.5).')
        st.markdown(f'Her er hjemme-/udebasis $H={config.home_goals:.2f}$ og '
                    f'$A={config.away_goals:.2f}$. Spillerens standard-intensitet for mål '
                    'og assists multipliceres med $\\lambda_{eget\\ hold}/m$ '
                    f'(angrebsskala {config.attack_scale:g}). Det kan delvis tælle '
                    'holdstyrke dobbelt, fordi spillerens xG/xA allerede er opnået på '
                    'det samme hold. Denne justering er endnu ikke særskilt kalibreret.')

    with st.expander('4 · Monte Carlo, odds og pointfordeling'):
        st.markdown('For hvert scenarie trækkes først spilletid. Mål og assists følger '
                    '**uafhængige Poisson-antal** med intensitet '
                    '$\\widehat r_{ik} M_i/90$ gange kampens angrebsfaktor. Holdenes mål '
                    'trækkes separat som Poisson med rater $\\lambda_H,\\lambda_A$. '
                    'Deres måltidspunkter deles af holdkammerater, så clean sheets er '
                    'korrelerede. Spillernes minutter og egne mål/assists danner derimod '
                    'ikke en fælles, konsistent holdopstilling.')
        st.markdown('**FPL-point beregnes inde i hvert scenarie:** 1 for at spille og '
                    'yderligere 1 ved mindst 60 minutter; mål giver 10/6/5/4 for '
                    'målmand/forsvarer/midtbane/angriber, assists 3. Clean sheet kræver '
                    'mindst 60 minutter og ingen indkasserede mål i spillerens relevante '
                    'interval (4 for målmand/forsvarer, 1 for midtbane). Kort, redninger, '
                    'defensive bidrag og øvrige FPL-komponenter følger samme pointkode. '
                    'Bonus er en begrænset binomialtilnærmelse, ikke en fælles BPS-rangering.')
        st.latex(r'\widehat{xP}_{ig}=R^{-1}\sum_{s=1}^{R}Y_{ig}^{(s)},\qquad '
                 r'\widehat P(\mathrm{DNP})=R^{-1}\sum_{s=1}^{R}'
                 r'\mathbf1\{M_{ig}^{(s)}=0\}.')
        st.markdown('Dobbeltrunder summerer point fra begge kampe. Percentilerne kommer '
                    'fra samme fordeling som xP. Fast seed gør simulationen reproducerbar, '
                    'men siger intet om kalibrering eller modelusikkerhed.')
        st.markdown('**Valgfri oddsvariant:** William Hills komplette 1X2 og over/under '
                    'præcis 2,5 omregnes ved normalisering af inverse decimalodds '
                    '**inden for hvert marked**. Positive Poisson-målrater tilpasses de fem '
                    'markedssandsynligheder ved mindste kvadrater:')
        st.latex(r'q_j=\frac{1/o_j}{\sum_{\ell\in marked}1/o_\ell},\qquad '
                 r'(\widehat\lambda_H,\widehat\lambda_A)='
                 r'\arg\min_{\lambda_H,\lambda_A>0}\sum_{j=1}^{5}'
                 r'(P_j^{Poisson}-q_j)^2.')
        st.markdown('Ugyldigt marked, tvetydig kampmatch, maksimal sandsynlighedsfejl '
                    'over 0,06 eller odds hentet efter prognose/deadline giver eksplicit '
                    'baseline-fallback. **Angreb og forsvar** ændrer clean sheets og '
                    'indkasserede mål og fordeler desuden forventede '
                    'holdmål proportionalt med spillerens xG/xA-rate × forventet spilletid; '
                    'hændelser trækkes stadig individuelt. Bookmakerens `last_update` '
                    'er ikke dokumenteret publikationstid; lokal hentetid styrer tilgængelighed.')

    with st.expander('5 · Optimering af trup, XI og transfers'):
        st.markdown('**Forecasting og beslutning er adskilt.** For hver mulig mængde '
                    'transfers nu (0, 1, 2, …) løser en MILP (mixed-integer linear '
                    'programming) en *åben* plan for op til fire GWs: truppen kan ændres '
                    'igen i senere GWs, men alle beslutninger planlægges med dagens '
                    'informationssæt. En hurtig surrogatmålfunktion summerer xP for XI '
                    'og anfører, plus 0,1 × bænkens xP, minus pointfradrag. Den modellerer '
                    'bank og faktiske salgsværdier, gratis transfers, trupstørrelse og '
                    'positioner samt højst tre spillere pr. klub.')
        st.markdown('For hver **fastlagt trup i hver GW** gennemsøges lovlige XI, '
                    'bænkerækkefølger og anfører/vice på planlægningsscenarier. Autosubs '
                    'og manuelt valgte chips indgår her. Den raffinerede målværdi er '
                    'gennemsnitlige holdpoint minus hits på disse scenarier. Den viste '
                    'gevinst mod uændret hold måles på **separate evalueringsscenarier** '
                    'under de samme prognoser. Opstillingen vælges før udfaldet, aldrig '
                    'med kampresultatet kendt.')
        st.caption('Dette er en risikoneutral pointmålsætning, ikke en vurdering af '
                   'rang, ejerskab eller personlige præferencer. Solver-gap gælder kun '
                   'den lineære kandidatsøgning, ikke et bevis for globalt optimal '
                   'transferstrategi med autosubs. Fremtidige priser antages faste; '
                   'ukendt fremtidig information har ingen værdi i planen, så den bør '
                   'genberegnes efter nye nyheder.')

    with st.expander('6 · Evaluering, identifikation og Begrænsninger'):
        st.markdown('Retrospektiv evaluering bruger kronologiske splits: tidligere '
                    'kampe estimerer parametre, senere endelige spiller-GW-point er mål. '
                    'En simpel reference er spillerens tidligere pointgennemsnit på '
                    '**præcis samme evalueringsrækker**. Point og minutter vurderes med '
                    'MAE/RMSE, DNP med Brier-score og pointfordelingen med CRPS.')
        st.markdown('Det er **ikke** automatisk en strikt historisk før-deadline-test: '
                    'nogle historiske kampdata blev først hentet senere. Aktuelle odds, '
                    'pris/status og slut-sæsonaggregater må ikke være historiske inputs. '
                    'En prospektiv test kræver gemte før-deadline-prognoser og senere '
                    'officielle slutresultater.')
        st.markdown('Fordelingerne er endnu ikke dokumenteret kalibrerede. Uafhængige '
                    'spiller-minutter, skader, bonus og manglende fælles hold-XI kan give '
                    'systematiske fejl. Gemte sammenligninger og faktisk efterkontrol '
                    'findes under **Analyse og eksperimenter**; intet eksperiment bliver '
                    'automatisk ny standard.')

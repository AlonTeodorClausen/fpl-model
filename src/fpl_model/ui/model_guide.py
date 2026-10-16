"""Read-only explanation of the model actually used by the team planner."""
import streamlit as st

from fpl_model.models.baseline import BaselineConfig, model_version


_VARIANTS = {
    'component_baseline_v1': 'Standardprognose',
    'component_defensive_odds_v1': 'Odds kun til forsvar',
    'component_attacking_odds_v1': 'Odds til angreb og forsvar',
    'component_role_minutes_v1': 'Forsøg med nylig spillerrolle',
    'component_role_transitions_v2': 'Forsøg med rolleskift i spilletid',
    'component_shared_goals_v1': 'Forsøg med fælles holdmål',
}


def render():
    config = BaselineConfig()
    standard = model_version(config)
    st.title('Sådan virker modellen')
    st.markdown(f'**Standard på Mit hold:** Standardprognose (`{standard}`) · uden odds. '
                'Analyse og eksperimenter kan bruge andre varianter, men ændrer ikke standarden.')
    for key, area in (('transfer_result', 'Mit hold'), ('lab_transfer_result', 'Analyse og eksperimenter')):
        report = st.session_state.get(key)
        forecast = report.get('forecast') if isinstance(report, dict) else None
        if not isinstance(forecast, dict) or not forecast.get('model_version'):
            continue
        version = forecast['model_version']
        label = _VARIANTS.get(version, 'Forsøgsvariant')
        st.markdown(f'**Åbent forslag under {area}:** {label} (`{version}`).')

    st.markdown('**Fra data til beslutning:** kampvis historik → spilletid og hændelsesrater '
                '→ simulerede FPL-point → opstilling og transferforslag.')

    with st.expander('Datagrundlag og tidsgrænser'):
        st.markdown('**Officiel FPL API** leverer spiller-ID, position, pris og status fra '
                    '`bootstrap-static`, kampe og deadlines fra `fixtures` samt kampvis spillerhistorik '
                    'fra `element-summary`. Den valgte dataversions hentetider står under '
                    '**Mit hold → Data og hentetider**.')
        st.markdown('Kun historik, som er tilgængelig før prognosetidspunktet, indgår som input. '
                    'Manglende kamp-rækker er **ikke** det samme som nul minutter. Ufuldstændig '
                    'spillerhistorik får en markeret fallback til sæsonaggregater eller priors.')
        st.markdown('Gemte William Hill-odds fra **The Odds API** er valgfrie i analysevarianterne. '
                    'De bruges kun, når kampmatching, markeder og tidsgrænser er godkendt; '
                    'ellers bruges holdets baseline-målmodel. FPL Core og football-data.org '
                    'er ikke input til den aktuelle standardprognose.')

    with st.expander('Spilletid: start, indhop og fravær'):
        st.markdown(f'Modellen tæller tidligere starter og indhop i brugbar kampvis historik. '
                    f'Standardprioren er **{config.prior_start:.0%} start**, '
                    f'**{config.prior_sub:.0%} indhop** og '
                    f'**{1-config.prior_start-config.prior_sub:.0%} nul minutter** med styrke '
                    f'**{config.frequency_prior_games:g} kamp**.')
        st.markdown('`P(start) = (starter + k × prior_start) / (kampe + k)`; '
                    '`P(indhop)` beregnes på samme måde. FPL’s spillechance eller skade-/statusfaktor '
                    'ganger start- og indhopssandsynligheden; resten bliver sandsynligheden for '
                    'nul minutter. Det er ikke en diagnose ud fra fri nyhedstekst.')
        st.markdown(f'Givet start eller indhop udglattes gennemsnitsminutter separat mod '
                    f'**{config.starter_minutes:g}** og **{config.sub_minutes:g}** minutter, '
                    f'begge med styrke **{config.minutes_prior_games:g} kamp**. '
                    'En start og et indhop får ikke samme minutfordeling.')
        st.caption('For senere GWs er tilgængelighed en synlig planlægningsantagelse. '
                   'Modellen ved ikke automatisk, hvornår en skade er ovre.')

    with st.expander('Mål, assists, forsvar og FPL-point'):
        st.markdown(f'Spillerens observerede xG/xA pr. 90 minutter udglattes mod en positionsprior '
                    f'med styrke **{config.prior_games:g} fulde kampe**: '
                    '`rate = (historisk xG eller xA + priorstyrke × positionsprior) '
                    '/ (spillede 90-minuttersperioder + priorstyrke)`. '
                    'Kort eller manglende historik får derfor ikke automatisk nul i forventning.')
        st.markdown(f'Holdenes målrater starter ved **{config.home_goals:.2f} hjemme** og '
                    f'**{config.away_goals:.2f} ude**, justeret med tidligere scorede og indkasserede mål '
                    f'og en prior på **{config.team_prior_games:g} kampe**. De påvirker både '
                    'angrebsrater og modstanderens mål i standardsimulationen.')
        st.markdown('For hver kamp trækkes spilletid og spillerhændelser i gentagne scenarier. '
                    'Mål og assists bruger Poisson-antal; modstanderens mål og måltidspunkter '
                    'deles af holdkammerater, så clean sheets hænger sammen. '
                    'FPL-regler omsætter hvert scenarie til point. **xP er gennemsnittet af '
                    'de simulerede point**, og percentiler beskriver spredningen.')
        st.caption('Odds til angreb og forsvar er et særskilt eksperiment: godkendte 1X2- og '
                   'over/under 2,5-markeder giver estimerede holdmål, som fordeles til spillere '
                   'efter xG/xA og forventet spilletid. Det er ikke standard på Mit hold.')

    with st.expander('Fra spillerprognoser til holdforslag'):
        st.markdown('Prognosen og holdvalget er adskilt. Optimeringen bruger de samme '
                    'spiller-scenarier til alle forslag, respekterer budget, positioner, klubgrænse '
                    'og dine transferbegrænsninger og vælger XI, bænk, anfører og viceanfører '
                    'pr. GW. Forslag sammenlignes med at beholde dit hold.')
        st.markdown('**Optimizerens målværdi** bruges til at finde planen. '
                    '**Simulerede holdpoint** vises særskilt og med FPL-autosubs, '
                    'så et usikkert startvalg kan dækkes af bænken. '
                    'Fremtidige priser antages faste i den nuværende planlægning.')

    with st.expander('Begrænsninger og evaluering'):
        st.markdown('Dette er en foreløbig sandsynlighedsmodel, ikke dokumenteret kalibrerede '
                    'sandsynligheder. Spillernes minutter simuleres hver for sig; modellen '
                    'danner ikke en sammenhængende startellever for hvert rigtigt hold. '
                    'Spillernes mål/assists kan i standardmodellen afvige fra et samlet '
                    'simuleret holdresultat, og bonus er en tilnærmelse, ikke en fælles BPS-rangering.')
        st.markdown('Historiske udviklingstests med senere hentede historikdata er ikke det samme '
                    'som en strikt før-deadline-test. Gemte prognoser og faktisk efterkontrol '
                    'vises under **Analyse og eksperimenter**. Holdplaner over flere GWs '
                    'bør genberegnes efter nye kampe, priser og nyheder.')

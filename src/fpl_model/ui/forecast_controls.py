"""Experimental forecast controls, separated from the everyday team workflow."""
import streamlit as st


def standard_forecast_settings():
    return dict(model='Standardprognose',experimental=False,set_pieces=False,role_only=False,
        uses_odds=False,evolution=None,roles=[],odds_scope='defence',set_piece_config=None,
        set_piece_path=None,bonus_config=None,season_prior_config=None,assist_config=None,odds_path=None)


def render_experimental_forecast_controls(data,events,labels,paths,root):
    from fpl_model.ui.my_team import _odds_paths
    model=st.selectbox('Prognosemodel',['Baseline','Defensiv oddsvariant · William Hill','Odds til angreb og forsvar · William Hill','Eksperiment · rolle, returminutter og fælles mål','Eksperiment · rollespecifik spilletid','Eksperiment · dødboldsroller og odds'])
    experimental=model=='Eksperiment · rolle, returminutter og fælles mål'
    from fpl_model.model_evolution import EvolutionConfig
    from fpl_model.ui.model_quality import role_controls
    set_pieces=model=='Eksperiment · dødboldsroller og odds'
    set_piece_config=None;set_piece_path=None
    role_only=model=='Eksperiment · rollespecifik spilletid'
    uses_odds=model!='Baseline' and not role_only
    evolution=(EvolutionConfig(shared_goals=False,minutes_method='role_transitions_v2') if role_only else
               EvolutionConfig() if experimental else None)
    roles=role_controls(data,events,labels) if experimental or role_only else []
    odds_scope='attack_and_defence' if model=='Odds til angreb og forsvar · William Hill' or experimental or set_pieces else 'defence'
    if set_pieces:
        from fpl_model.ui.set_pieces import set_piece_controls
        set_piece_config,set_piece_path=set_piece_controls(paths)
    elif role_only:
        st.info('Eksperiment: faste startere, rotation, indhoppere og reserver estimeres ud fra tidligere kampe og position. Startchance og betingede minutter holdes adskilt. Kun spilletidsmodellen ændres; ingen odds i denne isolerede sammenligning. Baseline er standard.')
        st.caption('Mindst to komplette, endelige historikrækker med kendte starter kræves; ellers baseline-fallback. Svagt belyste roller udglattes mod positionens prior. Ingen kalibreret skadesprognose eller fælles startellever.')
    elif experimental:
        st.info('Eksperiment: nyere start-/indhophistorik, separate returantagelser og fælles kampmål. Odds bruges, hvor dækket; ellers holdets målmodel. Baseline er uændret.')
        st.caption('Minutter er stadig uafhængige mellem spillere; ingen fælles startellever. Bonus er fortsat marginal, og selvmål er udeladt i denne variant. Ikke dokumenteret kalibreret.')
    elif odds_scope=='attack_and_defence':
        st.info('Eksperiment: odds fordeles som mål-/assist-rater efter xG/xA og forventede minutter. Clean sheets og indkasserede mål bruger også odds. Spilletid er uændret; kampe uden odds bruger baseline. Bonus er uændret, medmindre bonuseksperimentet nedenfor vælges.')
    elif model!='Baseline':
        st.caption('Kun clean sheets og indkasserede mål bruger odds. Mål og assists bruger baseline.')
    bonus_config=None
    season_prior_config=None
    assist_config=None
    if model in ('Baseline','Odds til angreb og forsvar · William Hill'):
        if st.checkbox('Eksperiment: præstationsafhængig bonus',value=False):
            from fpl_model.conditional_bonus import BonusConfig
            bonus_config=BonusConfig()
            st.warning('Kun bonus ændres. Læres fra tidligere endelige kampe inklusive indhoppere og afhænger af simulerede mål, assists, clean sheets, defensive bidrag, position og minutter. '
                'Ikke en fælles BPS-rangering; ikke dokumenteret bedre. Utilstrækkelig historik giver markeret bonus-fallback. Se gemt evaluering under Analyse og eksperimenter.')
    if model in ('Baseline','Odds til angreb og forsvar · William Hill') and bonus_config is None:
        if st.checkbox('Eksperiment: spillerprior fra sidste sæson',value=False):
            from fpl_model.season_priors import SeasonPriorConfig
            season_prior_config=SeasonPriorConfig()
            st.warning('Kun xG/xA-prior ændres. Seneste sæson udglattes mod positionen og indgår med tre 90-minutterskampe; årets historik vægter gradvist mere. Spilletid og bonus bevares. Ukendt historik giver positions-fallback. Ingen dokumenteret forbedring.')
    if model in ('Baseline','Odds til angreb og forsvar · William Hill') and bonus_config is None and season_prior_config is None:
        if st.checkbox('Eksperiment: FPL-assistkorrektion',value=False):
            from fpl_model.assist_correction import AssistConfig
            assist_config=AssistConfig()
            st.warning('Kun assists ændres. En fælles faktor læres fra tidligere færdige FPL-assists og xA og udglattes mod 1. Faktoren blander regeldefinitioner, afslutningsheld og støj; den genkender ikke enkelte returer eller vundne straffespark. Baseline er standard.')
    odds_path=None
    if uses_odds:
        odds_paths=_odds_paths(root)
        odds_path=st.selectbox('Gemt odds-snapshot',[None]+odds_paths,index=1 if odds_paths else 0,
                               format_func=lambda p:p.name if p else 'Ingen odds · markeret baseline-fallback')
    return {k: v for k,v in locals().items() if k in ['model', 'experimental', 'set_pieces', 'role_only', 'uses_odds', 'evolution', 'roles', 'odds_scope', 'set_piece_config', 'set_piece_path', 'bonus_config', 'season_prior_config', 'assist_config', 'odds_path']}

"""Experimental forecast controls, separated from the everyday team workflow.

Only the standard model, attacking+defensive odds and minutes model v2 are
offered. Retired experiments stay in git history and notes/experiments.md;
saved reports that used them can still be opened.
"""
import streamlit as st

BASELINE = 'Standardmodel'
ATTACK_ODDS = 'Odds til angreb og forsvar · William Hill'
MINUTES_V2 = 'Eksperiment · minutmodel v2'
MODELS = [BASELINE, ATTACK_ODDS, MINUTES_V2]


def standard_forecast_settings():
    return dict(model='Standardprognose',experimental=False,set_pieces=False,role_only=False,
        uses_odds=False,evolution=None,roles=[],odds_scope='defence',set_piece_config=None,
        set_piece_path=None,bonus_config=None,season_prior_config=None,assist_config=None,odds_path=None)


def render_experimental_forecast_controls(data,events,labels,paths,root):
    from fpl_model.ui.my_team import _odds_paths
    from fpl_model.model_evolution import EvolutionConfig
    settings=standard_forecast_settings()
    model=st.selectbox('Prognosemodel',MODELS)
    settings['model']=model
    if model==ATTACK_ODDS:
        settings.update(uses_odds=True,odds_scope='attack_and_defence')
        st.info('Odds fordeles som mål- og assistrater efter xG/xA og forventede minutter. Clean sheets og '
                'indkasserede mål bruger også odds. Spilletiden er som i standardmodellen; kampe uden odds '
                'bruger standardmodellen.')
        odds_paths=_odds_paths(root)
        settings['odds_path']=st.selectbox('Gemt odds-snapshot',[None]+odds_paths,index=1 if odds_paths else 0,
            format_func=lambda p:p.name if p else 'Ingen odds · markeret fallback til standardmodellen')
    elif model==MINUTES_V2:
        settings.update(experimental=True,evolution=EvolutionConfig(shared_goals=False,minutes_method='minutes_v2'))
        st.info('Kun spilletiden ændres. Startchance, chance for indhop når spilleren ikke starter, og '
                'minutter givet rolle estimeres hver for sig. Nyere kampe vægter mest, positionen giver '
                'udgangspunktet, og hele kampe trækkes for sig, så faste spillere ikke får for få minutter.')
        st.caption('Fastlagt før evaluering og afprøves på GW12–15 mod standardmodellen. '
                   'Se notes/minutes_v2.md.')
    return settings

"""Experimental marginal goal/assist budgets; no extra own-team attack multiplier.

The full official player pool is needed. xG/xA priors remain those of baseline.
Expected minutes include the same clipped/rounded normal draws as simulation.
Independent player event counts still need not equal a sampled match score.
"""
import numpy as np
from scipy.special import ndtr

MODEL_VERSION='component_attacking_odds_v1'


def conditional_minutes_mean(centre,spread,maximum):
    # E[clip(round(N),1,max)] = 1 + sum P(N >= k-.5), k=2..max.
    return float(1+ndtr((centre-(np.arange(2,maximum+1)-.5))/spread).sum())


def team_attack_rates(params, goal_mean):
    exposures={pid:(p['p_start']*conditional_minutes_mean(p['start_minutes'],8,90)+
                    p['p_sub']*conditional_minutes_mean(p['sub_minutes'],9,59))/90 for pid,p in params.items()}
    total_goals=sum(params[i]['goals']*e for i,e in exposures.items())
    total_assists=sum(params[i]['assists']*e for i,e in exposures.items())
    if total_goals<=0 or total_assists<=0:return None
    # xA/xG is an explicit proxy, not an observed FPL-assist probability.
    assist_fraction=min(1.,total_assists/total_goals)
    return {pid:dict(goals_per90=goal_mean*p['goals']/total_goals,
        assists_per90=goal_mean*assist_fraction*p['assists']/total_assists,
        expected_goals=goal_mean*p['goals']*exposures[pid]/total_goals,
        expected_assists=goal_mean*assist_fraction*p['assists']*exposures[pid]/total_assists,
        goal_share=p['goals']*exposures[pid]/total_goals,
        assist_share=p['assists']*exposures[pid]/total_assists,
        expected_exposure_90s=exposures[pid],team_goal_mean=goal_mean,
        team_assist_fraction=assist_fraction,team_xg_exposure=total_goals,team_xa_exposure=total_assists,
        status='odds',method='normalised_xg_xa_minute_shares_v1') for pid,p in params.items()}


def variant_version(scope):
    if scope not in ('defence','attack_and_defence'):raise ValueError('Unknown odds scope')
    return MODEL_VERSION if scope=='attack_and_defence' else 'component_defensive_odds_v1'

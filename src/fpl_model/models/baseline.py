"""Transparent smoothed minutes/event-rate baseline, without ML fitting."""
from dataclasses import dataclass
import math

import numpy as np
from fpl_model.diagnostics import history_summary


@dataclass(frozen=True)
class BaselineConfig:
    prior_games: float = 3.0
    minutes_prior_games: float = 1.0
    starter_minutes: float = 82.0
    sub_minutes: float = 22.0
    prior_start: float = 0.45
    prior_sub: float = 0.10
    attack_scale: float = 1.0
    home_goals: float = 1.55
    away_goals: float = 1.25
    team_prior_games: float = 5.0
    injury_unknown_factor: float = 0.25
    frequency_prior_games: float = 1.0

    def __post_init__(self):
        if any(not math.isfinite(v) for v in self.__dict__.values()): raise ValueError('Finite assumptions required')
        if min(self.prior_games, self.frequency_prior_games, self.minutes_prior_games, self.team_prior_games, self.home_goals, self.away_goals) <= 0:
            raise ValueError('Priors and goal means must be positive')
        if not 0 <= self.prior_start <= 1 or not 0 <= self.prior_sub <= 1-self.prior_start:
            raise ValueError('Invalid start/sub prior')
        if not 1 <= self.starter_minutes <= 90 or not 1 <= self.sub_minutes < 60 or not 0 <= self.injury_unknown_factor <= 1 or self.attack_scale < 0:
            raise ValueError('Invalid minutes/availability/rate assumption')


def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) and v >= 0 else None
    except (ValueError, TypeError):
        return None


def player_parameters(player, history, team_games, config, *, allow_aggregates=True):
    """History rows must already be filtered by information cutoff.

    Live aggregates are used only when no player history is captured. Historical
    evaluation disables them AND current injury/status information entirely.
    """
    pos = player['element_type']; flags = []
    prior = dict(goals={1:.002,2:.06,3:.20,4:.38}[pos], assists={1:.005,2:.09,3:.16,4:.12}[pos],
                 saves=3.0 if pos == 1 else 0., defensive_contribution={1:0,2:8,3:7,4:4}[pos],
                 yellow_cards=.12, red_cards=.006, own_goals=.004, penalties_missed=.005,
                 penalties_saved=.015 if pos == 1 else 0., bonus=.35)
    history = sorted(history, key=lambda r: (r['event'],r['fixture_id']))
    if history:
        n = len(history)
        starts = sum(number(r.get('starts')) if number(r.get('starts')) is not None else r['minutes'] >= 60 for r in history)
        subs = sum(r['minutes'] > 0 for r in history)-starts
        if any(r.get('starts') is None for r in history): flags.append('starts_inferred_from_60_minutes')
        starter = [r['minutes'] for r in history if (r.get('starts') or r['minutes'] >= 60)]
        substitute = [r['minutes'] for r in history if 0 < r['minutes'] < 60 and not r.get('starts')]
        start_mean = (sum(starter)+config.starter_minutes*config.minutes_prior_games)/(len(starter)+config.minutes_prior_games)
        sub_mean = (sum(substitute)+config.sub_minutes*config.minutes_prior_games)/(len(substitute)+config.minutes_prior_games)
        basis = 'player_fixture_history'
    else:
        n = max(0, team_games) if allow_aggregates else 0
        starts, mins = (number(player.get('starts')), number(player.get('minutes'))) if allow_aggregates else (None,None)
        if starts is None or mins is None:
            n = 0; starts = subs = 0; flags.append('minutes_explicit_prior')
        else:
            starts = min(starts, n)
            subs = np.clip((mins-starts*config.starter_minutes)/config.sub_minutes, 0, n-starts)
            flags.append('aggregate_sub_appearance_proxy')
        start_mean, sub_mean = config.starter_minutes, config.sub_minutes
        basis = 'season_aggregates' if allow_aggregates and n else 'explicit_priors'
    k = config.frequency_prior_games
    p_start = (starts+k*config.prior_start)/(n+k)
    p_sub = (max(0,subs)+k*config.prior_sub)/(n+k)
    factor = 1.0
    if allow_aggregates:
        chance = number(player.get('chance_of_playing_next_round'))
        if chance is not None: factor = min(chance/100,1)
        elif player.get('status') in ('s','u','n') or player.get('removed'): factor = 0.
        elif player.get('status') in ('i','d'):
            factor = config.injury_unknown_factor; flags.append('unknown_injury_probability_prior')
    rates = {}; rate_explanation = {}
    fields = {'goals':'expected_goals', 'assists':'expected_assists'}
    for key, default in prior.items():
        field = fields.get(key,key)
        if history:
            known = [r for r in history if number(r.get(field)) is not None]
            count = sum(float(r[field]) for r in known)
            exposure = sum(r['minutes'] for r in known)/90
            if len(known) != len(history): flags.append(field+'_missing_prior')
        elif allow_aggregates:
            value, mins = number(player.get(field)), number(player.get('minutes'))
            if value is None or mins is None:
                count = exposure = 0; flags.append(field+'_missing_prior')
            else: count, exposure = value, mins/90
        else:
            count = exposure = 0
        rates[key] = (count+config.prior_games*default)/(exposure+config.prior_games)
        rate_explanation[key] = dict(field=field, count=float(count), exposure_90s=float(exposure),
            known_rows=len(known) if history else None,
            observed_per90=float(count/exposure) if exposure else None, prior_per90=default,
            prior_90s=config.prior_games, smoothed_per90=float(rates[key]))
    if n < 3: flags.append('short_history_smoothed')
    return dict(**rates, p_start=float(p_start*factor), p_sub=float(p_sub*factor),
                start_minutes=float(np.clip(start_mean,1,90)), sub_minutes=float(np.clip(sub_mean,1,59)),
                history_rows=len(history), basis=basis, fallbacks=sorted(set(flags)),
                explanation=dict(history=history_summary(history),rates=rate_explanation,
                    injury_factor=float(factor),minutes_prior_games=config.minutes_prior_games,
                    frequency_prior_games=k,
                    prior_start=config.prior_start,prior_sub=config.prior_sub,
                    prior_dnp=1-config.prior_start-config.prior_sub,
                    pre_injury_start=float(p_start),pre_injury_sub=float(p_sub),
                    frequency_denominator=n,model_start_count=float(starts),model_sub_count=float(subs),
                    conditional_minutes_prior={'start':config.starter_minutes,'sub':config.sub_minutes}))


def fixture_goal_means(fixture, past_fixtures, config, *, with_context=False):
    base = (config.home_goals+config.away_goals)/2
    def rates(team):
        rows = [f for f in past_fixtures if team in (f['team_h'], f['team_a'])
                and f.get('team_h_score') is not None and f.get('team_a_score') is not None]
        scored = sum(f['team_h_score'] if f['team_h']==team else f['team_a_score'] for f in rows)
        conceded = sum(f['team_a_score'] if f['team_h']==team else f['team_h_score'] for f in rows)
        k = config.team_prior_games
        return (scored+k*base)/(len(rows)+k)/base, (conceded+k*base)/(len(rows)+k)/base
    ha, hd = rates(fixture['team_h']); aa, ad = rates(fixture['team_a'])
    means = (float(np.clip(config.home_goals*ha*ad,.15,4.5)), float(np.clip(config.away_goals*aa*hd,.15,4.5)))
    if with_context:
        return means, (dict(team_attack=ha,opponent_defence=ad,venue_goal_base=config.home_goals),
                       dict(team_attack=aa,opponent_defence=hd,venue_goal_base=config.away_goals))
    return means


def model_version(config):
    if config.frequency_prior_games == 1.0:
        return 'component_baseline_v1'
    return {0.25:'component_frequency_025_v1',0.10:'component_frequency_010_v1'}.get(
        config.frequency_prior_games, 'component_frequency_custom_v1')

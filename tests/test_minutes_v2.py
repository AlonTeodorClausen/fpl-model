"""Minutes v2 splits start, cameo given no start and minutes given role."""
import copy

import numpy as np
import pytest

from fpl_model.minutes_v2 import (FULL_MATCH_MINUTES, VERSION, draw_start_minutes,
                                  returning_from_absence)
from fpl_model.model_evolution import EvolutionConfig
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from test_role_minutes import pool


def v2():
    return EvolutionConfig(shared_goals=False, minutes_method='minutes_v2')


def test_version_and_shared_goals_guard():
    assert v2().version == VERSION
    with pytest.raises(ValueError):
        EvolutionConfig(shared_goals=True, minutes_method='minutes_v2')


def test_full_match_starter_is_not_pulled_below_ninety():
    d = pool()
    for r in d['histories']:
        if r['player_id'] == 1:
            r['minutes'] = 90
    cfg = BaselineConfig()
    old = simulate(d, 5, cfg, draws=4000, seed=1)
    new = simulate(d, 5, cfg, draws=4000, seed=1, evolution=v2())
    i = [p['id'] for p in new.players].index(1)
    started_old = old.minutes[:, i][old.minutes[:, i] >= 60]
    started_new = new.minutes[:, i][new.minutes[:, i] >= 60]
    # v1's clipped normal around ~88 averages clearly below 90; v2 keeps most starts at 90.
    assert started_old.mean() < 88
    assert started_new.mean() > started_old.mean()
    assert new.explanations[1]['role']['status'] == 'estimated'
    assert new.parameters[1]['full_match_prob'] > 0.5


def test_goalkeeper_cameo_prior_is_near_zero_and_forward_higher():
    d = pool()
    sim = simulate(d, 5, BaselineConfig(), draws=200, seed=3, evolution=v2())
    priors = {e['role']['position_prior']['position']: e['role']['position_prior']
              for e in sim.explanations.values() if e['role']['status'] == 'estimated'}
    assert priors[1]['sub_given_no_start'] < 0.05
    assert priors[3]['sub_given_no_start'] > priors[1]['sub_given_no_start']


def test_recent_matches_weigh_more():
    d = pool()
    # Player 6 alternates 80,0,80,0; make one copy lose the place recently and one gain it.
    lost, gained = copy.deepcopy(d), copy.deepcopy(d)
    for data, pattern in ((lost, [90, 90, 0, 0]), (gained, [0, 0, 90, 90])):
        for r in data['histories']:
            if r['player_id'] == 3:
                r['minutes'] = pattern[r['event']-1]
                r['starts'] = int(r['minutes'] >= 60)
    a = simulate(lost, 5, BaselineConfig(), draws=200, seed=4, evolution=v2())
    b = simulate(gained, 5, BaselineConfig(), draws=200, seed=4, evolution=v2())
    assert b.parameters[3]['p_start'] > a.parameters[3]['p_start']


def test_return_from_absence_only_when_fit_and_live():
    rows = [dict(minutes=m) for m in (90, 90, 90, 0, 0)]
    assert returning_from_absence(rows, dict(status='a', chance_of_playing_next_round=None)) == 2
    assert returning_from_absence(rows, dict(status='d', chance_of_playing_next_round=75)) == 0
    assert returning_from_absence(rows[:-1], dict(status='a')) == 0
    d = pool()
    for r in d['histories']:
        if r['player_id'] == 1 and r['event'] >= 3:
            r['minutes'], r['starts'] = 0, 0
    live = simulate(d, 5, BaselineConfig(), draws=200, seed=5, evolution=v2())
    role = live.explanations[1]['role']
    assert role['returning_after_missed_matches'] == 2
    # Absence rows do not count as lost place; first match back is damped by 0.7.
    assert role['fixture_ids'] == [1, 2]
    undamped = role['p_start_given_available']/0.7
    assert role['p_sub_given_available'] >= undamped*0.3 - 1e-12
    retro = simulate(d, 5, BaselineConfig(), draws=200, seed=5, evolution=v2(), retrospective=True)
    assert retro.explanations[1]['role']['returning_after_missed_matches'] == 0


def test_short_history_keeps_baseline_with_fallback():
    d = pool()
    d['histories'] = [r for r in d['histories'] if r['player_id'] != 1 or r['event'] == 1]
    base = simulate(d, 5, BaselineConfig(), draws=200, seed=6)
    new = simulate(d, 5, BaselineConfig(), draws=200, seed=6, evolution=v2())
    assert new.explanations[1]['role']['status'] == 'fallback'
    assert new.parameters[1]['p_start'] == pytest.approx(base.parameters[1]['p_start'])
    assert 'full_match_prob' not in new.parameters[1]


def test_draw_start_minutes_matches_its_mean():
    rng = np.random.default_rng(0)
    par = dict(full_match_prob=0.8, early_exit_minutes=70.0)
    mins = draw_start_minutes(par, rng, 200_000)
    assert mins.max() == 90 and mins.min() >= 1
    assert (mins[mins < 90] <= FULL_MATCH_MINUTES-1).all()
    assert mins.mean() == pytest.approx(0.8*90+0.2*70, abs=0.3)


def test_probabilities_stay_valid():
    sim = simulate(pool(), 5, BaselineConfig(), draws=200, seed=7, evolution=v2())
    for p in sim.parameters.values():
        assert 0 <= p['p_start'] <= 1 and 0 <= p['p_sub'] and p['p_start']+p['p_sub'] <= 1+1e-12

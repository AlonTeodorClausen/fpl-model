"""Runnable prototype: scoring, legality, reproducibility and time separation."""
import copy
import importlib
import importlib.util

import numpy as np
import pytest


def module(name):
    assert importlib.util.find_spec('fpl_model.' + name), name + ' not implemented'
    return importlib.import_module('fpl_model.' + name)


def players():
    rows = []
    for pos, count in ((1, 4), (2, 10), (3, 10), (4, 6)):
        for j in range(count):
            i = len(rows)+1
            rows.append(dict(id=i, player_id=i, element_type=pos, position=pos, team=j%10+1,
                             team_id=j%10+1, now_cost=45+j, price=45+j, web_name=f'P{i}',
                             can_select=True, minutes=360, starts=4, status='a',
                             expected_goals='0.5', expected_assists='0.4', xp=2+i/20))
    return rows


def data():
    fixtures = [dict(id=i, event=i, team_h=1, team_a=2, finished=i<5,
                     kickoff_time=f'2026-09-{i*2:02d}T14:00:00Z', team_h_score=1 if i<5 else None,
                     team_a_score=0 if i<5 else None) for i in range(1, 6)]
    return dict(players=players(), fixtures=fixtures, histories=[],
                events=[dict(id=i, deadline_time=f'2026-09-{i*2:02d}T12:30:00Z') for i in range(1, 6)],
                as_of_at='2026-09-09T12:00:00Z', snapshot_id='synthetic', rules={})


def test_official_scoring_boundaries_and_negative_points():
    score = module('scoring').score_points
    assert score(2, minutes=59, goals_conceded=0, defensive_contribution=9) == 1
    assert score(2, minutes=60, goals_conceded=0, defensive_contribution=10) == 8
    assert score(3, minutes=90, goals=1, assists=1, goals_conceded=1, defensive_contribution=12) == 12
    assert score(1, minutes=90, goals=1, saves=8, penalties_saved=1, goals_conceded=2) == 18
    assert score(4, minutes=20, yellow_cards=0, red_cards=1, own_goals=1) == -4
    assert score(2, minutes=90, goals_conceded=0, defensive_contribution=20) == 8
    assert score(2, minutes=0) == 0


def test_seeded_simulation_percentiles_and_unknown_data_prior():
    m = module('models.baseline'); sim = module('simulation')
    d = data(); cfg = m.BaselineConfig()
    a = sim.simulate(d, 5, cfg, draws=300, seed=42)
    b = sim.simulate(d, 5, cfg, draws=300, seed=42)
    assert np.array_equal(a.points, b.points) and np.array_equal(a.minutes, b.minutes)
    assert not np.array_equal(a.points, sim.simulate(d, 5, cfg, draws=300, seed=43).points)
    table = a.summary()
    assert all(r['p10'] <= r['p50'] <= r['p90'] for r in table)
    assert all(0 <= r['p_no_play'] <= 1 for r in table)
    p = m.player_parameters(dict(id=99, element_type=3, minutes=None, starts=None), [], 4, cfg)
    assert p['p_start'] > 0 and p['goals'] > 0 and p['fallbacks']
    # Blank schedule is explicitly zero, not a missing-stat fallback.
    assert all(r['xp']==0 for r in table if r['team_id'] not in (1, 2))


def test_optimizer_locks_exclusions_budget_and_formation():
    opt = module('optimizer.squad')
    rows = players()
    team = opt.optimize_squad(rows, budget=100, locked=[1], excluded=[30])
    opt.validate_squad(team, rows, budget=100, locked=[1], excluded=[30])
    assert len(team['squad']) == 15 and len(team['starters']) == 11
    assert 1 in team['squad'] and 30 not in team['squad']
    assert team['captain'] in team['starters'] and team['vice_captain'] != team['captain']
    with pytest.raises(ValueError): opt.optimize_squad(rows, budget=1)
    with pytest.raises(ValueError): opt.optimize_squad(rows, budget=100, locked=[1], excluded=[1])


def test_autosubs_respect_defender_minimum_and_vice_captain():
    opt = module('optimizer.squad')
    # XI 1 GK / 3 DEF / 4 MID / 3 FWD; bench GK, MID, DEF, MID.
    positions = [1,2,2,2,3,3,3,3,4,4,4,1,3,2,3]
    rows = [dict(player_id=i, position=p) for i,p in enumerate(positions)]
    team = dict(squad=list(range(15)), starters=list(range(11)), bench=[11,12,13,14], captain=8, vice_captain=4)
    pts = np.full((2,15), 2); active = np.ones((2,15), dtype=bool)
    active[0,[0,1,8]] = False; pts[0,[0,1,8]] = 0
    result = opt.evaluate_squad(team, rows, pts, active)
    # Reserve GK + reserve DEF + first MID cover the 3 absent players; vice doubles.
    assert result['points'][0] == 24
    assert result['bench_points'][0] == 6
    assert result['points'][1] == 24 and result['bench_points'][1] == 0
    active[0,:] = True; active[0,1] = False; pts[0,:] = 2; pts[0,1] = 0
    pts[0,12] = 20; pts[0,13] = 3
    result = opt.evaluate_squad(team, rows, pts, active)
    assert result['bench_points'][0] == 3  # MID cannot replace the third DEF.


def test_backtest_uses_only_prior_gws_and_never_bootstrap_aggregates():
    m = module('backtest.walk_forward'); cfg = module('models.baseline').BaselineConfig()
    d = data()
    d['histories'] = [dict(player_id=1, fixture_id=i, event=i, team_id=1, opponent_team_id=2,
        minutes=90, starts=1, goals_scored=0, assists=0, total_points=2+i, label_state='final',
        expected_goals='0.01', expected_assists='0.01', kickoff_time=f'2026-09-{i*2:02d}T14:00:00Z') for i in range(1,5)]
    before = m.evaluate_sample(d, cfg, draws=200, seed=1)
    assert before['status'] == 'retrospective_limited' and before['n'] == 2
    changed = copy.deepcopy(d)
    changed['players'][0].update(minutes=90000, expected_goals='999', starts=99)
    changed['histories'][-1]['expected_goals'] = '999'
    after = m.evaluate_sample(changed, cfg, draws=200, seed=1)
    assert before['rows'][0] == after['rows'][0]


def test_future_observation_cannot_change_current_forecast():
    cfg=module('models.baseline').BaselineConfig();sim=module('simulation')
    d=data();before=sim.simulate(d,5,cfg,draws=100,seed=7)
    d['histories']=[dict(player_id=1,fixture_id=1,event=1,minutes=90,starts=1,
        expected_goals='500',expected_assists='500',kickoff_time='2026-09-02T14:00:00Z',
        available_at='2026-09-11T12:00:00Z')]
    after=sim.simulate(d,5,cfg,draws=100,seed=7)
    assert np.array_equal(before.points,after.points)


def test_captain_zero_points_is_not_dnp_and_both_missing_give_no_bonus():
    opt=module('optimizer.squad')
    pos=[1,2,2,2,3,3,3,3,4,4,4,1,3,2,3]
    rows=[dict(player_id=i,position=p) for i,p in enumerate(pos)]
    team=dict(squad=list(range(15)),starters=list(range(11)),bench=[11,12,13,14],captain=8,vice_captain=4)
    points=np.zeros((2,15));active=np.ones((2,15),dtype=bool)
    points[:,4]=10;points[:,12]=20;active[1,[8,4]]=False;points[1,4]=0
    evaluated=opt.evaluate_squad(team,rows,points,active)
    assert evaluated['captain_bonus'].tolist()==[0,0]
    assert evaluated['bench_points'][0]==0


def test_dgw_sums_minutes_and_points_without_double_captain_multiplier():
    sim=module('simulation'); cfg=module('models.baseline').BaselineConfig()
    d=data();d['fixtures'].append({**d['fixtures'][-1],'id':99})
    result=sim.simulate(d,5,cfg,draws=300,seed=9)
    assert np.max(result.minutes)>90
    assert np.max(result.minutes)<=180


def test_match_scoring_all_official_component_weights():
    score=module('scoring').score_points
    for pos,goal_points in ((1,10),(2,6),(3,5),(4,4)):
        assert score(pos,minutes=30,goals=1,assists=1,goals_conceded=0,bonus=3,penalties_missed=1)==1+goal_points+3+3-2
    assert score(1,minutes=90,goals_conceded=3,saves=2)==1
    assert score(3,minutes=60,goals_conceded=0,defensive_contribution=11)==3

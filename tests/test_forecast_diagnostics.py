"""Explanations must reconcile, retain baseline v1, and group before forecast."""
import copy
import hashlib
import importlib.util
import numpy as np
import pytest
from test_history_coverage_evaluation import history_data
from fpl_model.models.baseline import BaselineConfig, player_parameters
from fpl_model.simulation import simulate
from fpl_model.backtest.walk_forward import evaluate_sample


def diagnostics():
    assert importlib.util.find_spec('fpl_model.diagnostics'), 'diagnostics missing'
    from fpl_model import diagnostics
    return diagnostics


def test_point_components_reconcile_in_each_scenario_and_position():
    from fpl_model import scoring
    assert hasattr(scoring,'score_components')
    for pos in range(1,5):
        inputs=dict(minutes=np.array([0,20,60,90]),goals=np.array([0,1,2,0]),assists=1,
            goals_conceded=np.array([0,1,2,4]),saves=7,defensive_contribution=12,
            penalties_saved=1,penalties_missed=1,yellow_cards=1,red_cards=1,own_goals=1,bonus=2)
        components=scoring.score_components(pos,**inputs)
        np.testing.assert_array_equal(sum(components.values()),scoring.score_points(pos,**inputs))
        assert components['goals'][1]=={1:10,2:6,3:5,4:4}[pos]
        assert components['red_cards']==-3


def test_parameters_expose_observed_prior_and_smoothed_rates_without_imputing_missing():
    d=history_data(); rows=[r for r in d['histories'] if r['player_id']==1]
    rows[0]['expected_goals']=None
    p=player_parameters(d['players'][0],rows,4,BaselineConfig())
    assert 'explanation' in p
    e=p['explanation']; x=e['rates']['goals']
    assert x['known_rows']==3 and x['exposure_90s']==3
    assert x['observed_per90']==pytest.approx(.01)
    assert x['prior_per90']==.002
    assert x['smoothed_per90']==p['goals']==pytest.approx((.03+3*.002)/6)
    assert e['history']['matches']==4 and e['history']['minutes']==360
    assert e['history']['start_frequency']==1 and e['history']['dnp_frequency']==0
    assert e['injury_factor']==1
    empty=player_parameters(dict(element_type=3),[],4,BaselineConfig())['explanation']
    assert empty['history']['start_frequency'] is None
    assert empty['rates']['goals']['observed_per90'] is None


def test_simulation_component_means_reconcile_dgw_and_blank_without_changing_rng():
    d=history_data();s=simulate(d,5,BaselineConfig(),draws=300,seed=42)
    assert hasattr(s,'explanations')
    for i,p in enumerate(s.players):
        e=s.explanations[p['id']]
        assert sum(e['point_components'].values())==pytest.approx(s.points[:,i].mean())
        assert e['expected_points']==s.points[:,i].mean()
    # Frozen fingerprints from the unmodified component_baseline_v1.
    assert hashlib.sha256(s.points.tobytes()).hexdigest()=='390ab490fe5aea0e546cc37c4b0aecda4b56c99a797f0ef41930f99856d86a91'
    assert hashlib.sha256(s.minutes.tobytes()).hexdigest()=='6f1c6958048d78f2c64025e3d49f986c007f5604b73d2b946c3594df28f02ea8'
    d['fixtures'].append({**d['fixtures'][-1],'id':99})
    s=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    assert len(s.explanations[1]['fixtures'])==2
    for i,p in enumerate(s.players):
        assert sum(s.explanations[p['id']]['point_components'].values())==pytest.approx(s.points[:,i].mean())


def test_minute_groups_use_only_prior_rows_and_preserve_saved_evaluation():
    module=diagnostics();d=history_data();r=evaluate_sample(d,BaselineConfig(),draws=100,seed=42)
    original=copy.deepcopy(r)
    a=module.minute_diagnostics(r['rows'],d,BaselineConfig())
    assert r==original
    assert a['scopes']['all']['n']==4 and a['scopes']['regular']['n']==2
    reserve=next(x for x in a['by_start_history'] if x['group']=='never_started')
    assert reserve['n']==2 and reserve['model']['bias']>0 and reserve['reference']['bias']==0
    assert sum(x['n'] for x in a['by_position'])==4
    future=copy.deepcopy(d)
    for row in future['histories']:
        if row['event']>=3: row.update(minutes=5,starts=0,total_points=100)
    b=module.minute_diagnostics([x for x in r['rows'] if x['event']==3],future,BaselineConfig())
    assert [x for x in a['rows'] if x['event']==3]==b['rows']
    reversed_result=module.minute_diagnostics(list(reversed(r['rows'])),d,BaselineConfig())
    assert a==reversed_result
    x=a['rows'][0]
    assert x['prior']['last_kickoff_at']<x['forecast_origin_at']


def test_unknown_starts_not_classified_as_observed_starter_or_dnp():
    module=diagnostics();d=history_data()
    for r in d['histories']: r['starts']=None
    eval_rows=evaluate_sample(d,BaselineConfig(),draws=100,seed=42)['rows']
    result=module.minute_diagnostics(eval_rows,d,BaselineConfig())
    assert {r['start_group'] for r in result['rows']}=={'unknown_starts'}
    assert all(r['prior']['start_frequency'] is None for r in result['rows'])
    assert result['scopes']['regular']['n']==2 # known minutes suffice, starts not guessed


def test_fixture_adjustment_explains_team_and_opponent_factors():
    s=simulate(history_data(),5,BaselineConfig(),draws=100,seed=42)
    f=s.explanations[1]['fixtures'][0]
    assert 'team_attack' in f and 'opponent_defence' in f
    assert f['own_goal_mean']==pytest.approx(np.clip(f['venue_goal_base']*f['team_attack']*f['opponent_defence'],.15,4.5))
    assert f['attack_factor']==pytest.approx(f['own_goal_mean']/f['league_goal_base']*f['attack_scale'])


def test_report_keeps_explanations_and_diagnostics_separate_from_v1_predictions():
    from fpl_model.prototype import run_prototype
    report,sim,_=run_prototype(history_data(),5,BaselineConfig(),draws=100,seed=42)
    assert report['model_version']=='component_baseline_v1'
    assert report.get('player_explanations')==sim.explanations
    assert report['evaluation'].get('minute_diagnostics',{}).get('scopes',{}).get('all',{}).get('n')==4


def test_explanation_preserves_injury_and_unsafe_history_fallback():
    d=history_data();d['players'][0]['chance_of_playing_next_round']=50
    d['histories']=[r for r in d['histories'] if not (r['player_id']==1 and r['event']==2)]
    s=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    e=s.explanations[1]
    assert e['captured_history']['matches']==3 and e['history']['matches']==0
    assert e['basis']=='season_aggregates'
    assert e['injury_factor']==.5 and e['p_start']==e['pre_injury_start']*.5
    assert 'incomplete_history_denominator' in e['fallbacks']
    assert e['rates']['goals']['observed_per90']==pytest.approx(.5/4)


def test_diagnostic_bias_and_errors_use_saved_predictions_on_identical_rows():
    m=diagnostics();d=history_data()
    r=evaluate_sample(d,BaselineConfig(),draws=100,seed=42)['rows']
    for row in r:
        row.update(actual_minutes=20,predicted_minutes=30,reference_minutes=0)
    a=m.minute_diagnostics(r,d,BaselineConfig())
    assert a['scopes']['all']['model']==dict(bias=10.,mae=10.,rmse=10.)
    assert a['scopes']['all']['reference']==dict(bias=-20.,mae=20.,rmse=20.)
    assert m.minute_diagnostics([],d,BaselineConfig())['scopes']['all']['model'] is None
    d['histories']=[h for h in d['histories'] if h['event']!=1]
    with pytest.raises(ValueError,match='safe prior-history'):
        m.minute_diagnostics(r,d,BaselineConfig())

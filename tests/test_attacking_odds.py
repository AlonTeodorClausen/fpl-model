import copy
import numpy as np
import pytest
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from fpl_model.defensive_odds import build_coverage
from test_defensive_odds import coverage_data


def test_attack_allocation_uses_one_team_goal_budget_and_minute_exposure():
    from fpl_model.attacking_odds import team_attack_rates
    params={1:dict(goals=.5,assists=.2,p_start=.8,p_sub=.1,start_minutes=80.,sub_minutes=20.),
            2:dict(goals=.2,assists=.3,p_start=.6,p_sub=.2,start_minutes=75.,sub_minutes=15.),
            3:dict(goals=.9,assists=.2,p_start=0.,p_sub=0.,start_minutes=80.,sub_minutes=20.)}
    rates=team_attack_rates(params,2.)
    assert sum(r['expected_goals'] for r in rates.values())==pytest.approx(2.)
    assert sum(r['expected_assists'] for r in rates.values())<=2.
    assert rates[3]['expected_goals']==0
    assert rates[1]['goals_per90']/rates[2]['goals_per90']==pytest.approx(2.5)
    assert team_attack_rates({3:params[3]},2.) is None


def test_attack_variant_preserves_minutes_defence_other_components_and_default():
    data,row,source=coverage_data();cfg=BaselineConfig()
    coverage=build_coverage(data,[row],source,5,cfg,data['as_of_at'])
    baseline=simulate(data,5,cfg,draws=1000,seed=42)
    defensive=simulate(data,5,cfg,draws=1000,seed=42,defensive_odds=coverage)
    full=simulate(data,5,cfg,draws=1000,seed=42,defensive_odds=coverage,odds_scope='attack_and_defence')
    np.testing.assert_array_equal(baseline.minutes,full.minutes)
    assert not np.array_equal(defensive.points,full.points)
    for pid,e in full.explanations.items():
        for key,value in e['point_components'].items():
            if key not in ('goals','assists'):
                assert value==defensive.explanations[pid]['point_components'][key]
        assert sum(e['point_components'].values())==pytest.approx(e['expected_points'])
    again=simulate(data,5,cfg,draws=1000,seed=42,defensive_odds=coverage,odds_scope='attack_and_defence')
    np.testing.assert_array_equal(full.points,again.points)


def test_attack_missing_odds_is_exact_baseline_and_future_odds_rejected():
    data,row,source=coverage_data();cfg=BaselineConfig()
    baseline=simulate(data,5,cfg,draws=100,seed=42)
    no_odds=build_coverage(data,[],source,5,cfg,data['as_of_at'])
    fallback=simulate(data,5,cfg,draws=100,seed=42,defensive_odds=no_odds,odds_scope='attack_and_defence')
    np.testing.assert_array_equal(baseline.points,fallback.points)
    assert all(f['attack_odds']['status']=='baseline_fallback' for e in fallback.explanations.values() for f in e['fixtures'])
    coverage=build_coverage(data,[row],source,5,cfg,data['as_of_at'])
    future=copy.deepcopy(coverage);future['source']['available_at']='2026-09-11T00:00:00Z'
    with pytest.raises(ValueError):simulate(data,5,cfg,draws=100,seed=42,defensive_odds=future,odds_scope='attack_and_defence')
    with pytest.raises(ValueError):simulate(data,5,cfg,draws=100,seed=42,defensive_odds=coverage,odds_scope='attack_and_defence',retrospective=True)


def test_attacking_comparison_records_scope_allocation_and_exact_component_delta():
    from fpl_model.odds_comparison import compare_forecasts
    data,row,source=coverage_data();cfg=BaselineConfig()
    coverage=build_coverage(data,[row],source,5,cfg,data['as_of_at'])
    report=compare_forecasts(data,coverage,cfg,draws=100,seed=42,odds_scope='attack_and_defence')
    assert report['baseline']['model_version']=='component_baseline_v1'
    assert report['odds_variant']['model_version']=='component_attacking_odds_v1'
    assert report['odds_scope']=='attack_and_defence'
    assert report['invariants']['minutes_identical']
    assert not report['invariants']['nondefensive_components_identical']
    for p in report['player_changes']:
        assert p['xp_delta']==pytest.approx(p['attacking_points_delta']+p['defensive_points_delta'])
    allocations=[f['attack_odds'] for e in report['odds_variant']['player_explanations'].values() for f in e['fixtures']]
    assert allocations and all('method' in a for a in allocations)
    assert report['attack_coverage']['fully_applied']==1
    for row in report['attack_coverage']['team_budgets']:
        assert row['expected_player_goals']==pytest.approx(row['market_team_goals'])
        assert row['expected_player_assists']<=row['market_team_goals']+1e-12


def test_scope_is_part_of_transfer_cache_and_empty_markets_preserve_scenarios(tmp_path):
    from fpl_model.transfer_planner import forecast_bundle
    from test_transfer_planner import context
    d=context();d['teams']=[dict(id=i,name=f'T{i}') for i in range(1,11)]
    odds=([],dict(source='the_odds_api',available_at=d['as_of_at'],retrieved_at=d['as_of_at'],failure='no_saved_odds'))
    args=dict(origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path,draws=100,odds=odds)
    defence=forecast_bundle(d,[5,6],BaselineConfig(),**args)
    attack=forecast_bundle(d,[5,6],BaselineConfig(),odds_scope='attack_and_defence',**args)
    assert defence['cache_key']!=attack['cache_key']
    assert attack['metadata']['model_version']=='component_attacking_odds_v1'
    for event in (5,6):
        np.testing.assert_array_equal(defence['scenarios'][event]['points'],attack['scenarios'][event]['points'])
    cached=forecast_bundle(d,[5,6],BaselineConfig(),odds_scope='attack_and_defence',**args)
    assert cached['cache_key']==attack['cache_key']


def test_app_exposes_explicit_attack_scope_without_network(monkeypatch,tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile
    from fpl_model.my_team import save_profile
    setup(monkeypatch,tmp_path)
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    model=next(w for w in app.selectbox if w.label=='Prognosemodel')
    assert model.value=='Baseline'
    model.set_value('Odds til angreb og forsvar · William Hill').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    report=app.session_state['lab_transfer_result']
    assert report['forecast']['model_version']=='component_attacking_odds_v1'
    assert report['odds_coverage'][5]['usable']==0
    assert any('mål-/assist' in info.value for info in app.info)

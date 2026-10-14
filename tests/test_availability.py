import copy
import inspect
import numpy as np
import pytest
from fpl_model.simulation import simulate
from fpl_model.models.baseline import BaselineConfig
from test_transfer_planner import context, bundle, mod


def test_replacement_factor_not_second_injury_penalty_and_default_unchanged():
    assert 'availability_overrides' in inspect.signature(simulate).parameters
    d=context();d['players'][0]['chance_of_playing_next_round']=50
    original=copy.deepcopy(d)
    base=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    same=simulate(d,5,BaselineConfig(),draws=100,seed=42,availability_overrides={})
    half=simulate(d,5,BaselineConfig(),draws=100,seed=42,availability_overrides={1:.5})
    fit=simulate(d,5,BaselineConfig(),draws=100,seed=42,availability_overrides={1:1.})
    assert np.array_equal(base.points,same.points) and np.array_equal(base.points,half.points)
    assert fit.parameters[1]['p_start']==pytest.approx(2*base.parameters[1]['p_start'])
    out=simulate(d,5,BaselineConfig(),draws=100,seed=42,availability_overrides={1:0.})
    assert np.all(out.minutes[:,0]==0)
    assert d==original
    for bad in [{1:1.1},{1:float('nan')},{999:0},{1:True}]:
        with pytest.raises(ValueError):simulate(d,5,BaselineConfig(),draws=100,availability_overrides=bad)
    with pytest.raises(ValueError):simulate(d,5,BaselineConfig(),draws=100,retrospective=True,availability_overrides={1:.5})


def assumptions(event=6):
    return [dict(player_id=1,event=event,factor=0.,reason='Manual injury scenario',
                 observed_at='2026-09-09T12:45:00Z',source_url=None)]


def test_gw_specific_override_cache_provenance_and_no_backfill(tmp_path):
    assert 'availability' in inspect.signature(mod().forecast_bundle).parameters
    base=bundle(tmp_path)
    variant=bundle(tmp_path,availability=assumptions())
    assert base['cache_key']!=variant['cache_key']
    assert np.array_equal(base['scenarios'][5]['points'],variant['scenarios'][5]['points'])
    assert np.all(variant['scenarios'][6]['played'][:,0]==False)
    assert variant['metadata']['availability_assumptions']==assumptions()
    assert base['metadata']['model_version']=='component_baseline_v1'
    assert variant['metadata']['model_version']!='component_baseline_v1'
    for bad in [assumptions(99),assumptions()+assumptions(),[dict(assumptions()[0],reason='')],
                [dict(assumptions()[0],observed_at='2026-09-10T12:45:00Z')]]:
        with pytest.raises(ValueError):bundle(tmp_path,availability=bad)


def test_availability_does_not_change_other_players_random_draws():
    d=context();a=simulate(d,5,BaselineConfig(),draws=300,seed=42)
    b=simulate(d,5,BaselineConfig(),draws=300,seed=42,availability_overrides={1:0})
    assert np.array_equal(a.points[:,1:],b.points[:,1:])
    assert np.array_equal(a.minutes[:,1:],b.minutes[:,1:])


def test_short_doubt_policy_is_explicit_bounded_and_manual_takes_precedence():
    from fpl_model.availability import resolve_horizon_availability
    players=[dict(id=1,status='d',chance_of_playing_next_round=75),
             dict(id=2,status='i',chance_of_playing_next_round=0),
             dict(id=3,status='d',chance_of_playing_next_round=50),
             dict(id=4,status='s',chance_of_playing_next_round=75)]
    origin='2026-09-09T13:00:00Z'
    manual=[dict(assumptions()[0],factor=.4)]
    resolved,automatic=resolve_horizon_availability(players,[5,6,7],manual,origin,'short_doubt_next_gw')
    assert {(r['player_id'],r['event']):r['factor'] for r in resolved}=={(1,6):.4,(1,7):1.}
    assert [(r['player_id'],r['event']) for r in automatic]==[(1,7)]
    assert automatic[0]['kind']=='planning_assumption'
    assert automatic[0]['official_factor']==.75
    assert resolve_horizon_availability(players,[5],[],origin,'short_doubt_next_gw')==([],[])
    assert resolve_horizon_availability(players,[5,6],[],origin,'hold_current')==([],[])
    with pytest.raises(ValueError):resolve_horizon_availability(players,[5,6],[],origin,'unknown')


def test_horizon_policy_preserves_first_gw_and_labels_future_assumption(tmp_path):
    d=context();d['players'][0].update(status='d',chance_of_playing_next_round=75)
    kw=dict(origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path,draws=100,seed=42)
    base=mod().forecast_bundle(d,[5,6],BaselineConfig(),**kw)
    scenario=mod().forecast_bundle(d,[5,6],BaselineConfig(),availability_policy='short_doubt_next_gw',**kw)
    assert np.array_equal(base['scenarios'][5]['points'],scenario['scenarios'][5]['points'])
    assert base['cache_key']!=scenario['cache_key']
    assert scenario['metadata']['availability_policy']=='short_doubt_next_gw'
    assert scenario['metadata']['derived_availability_assumptions'][0]['official_factor']==.75
    assert scenario['metadata']['model_version']!='component_baseline_v1'
    assert base['metadata']['model_version']=='component_baseline_v1'
    assert np.array_equal(base['scenarios'][6]['points'][:,1:],scenario['scenarios'][6]['points'][:,1:])

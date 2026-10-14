"""Role-conditioned transitions are historical evidence, not assumed DNP rows."""
import copy
import importlib.util
import numpy as np
import pytest
from fpl_model.models.baseline import BaselineConfig
from fpl_model.model_evolution import EvolutionConfig
from fpl_model.simulation import simulate
from test_history_coverage_evaluation import history_data


def options():
    assert importlib.util.find_spec('fpl_model.role_minutes'), 'Role-specific minutes not implemented'
    return EvolutionConfig(shared_goals=False,minutes_method='role_transitions_v2')


def pool():
    d=history_data();d['players']=[];d['histories']=[]
    patterns=[(1,[90]*4),(1,[0]*4),(2,[85]*4),(2,[0]*4),(3,[20]*4),(3,[80,0,80,0])]
    for repeat in range(8):
        for i,(pos,mins) in enumerate(patterns,1):
            pid=i+10*repeat;d['players'].append(dict(id=pid,element_type=pos,team=1,status='a',web_name=str(pid),now_cost=50))
            for event,minutes in enumerate(mins,1):
                d['histories'].append(dict(player_id=pid,fixture_id=event,event=event,team_id=1,minutes=minutes,
                    starts=int(minutes>=60),label_state='final',total_points=0,
                    expected_goals='0.01',expected_assists='0.01',kickoff_time=f'2026-09-{event*2:02d}T14:00:00Z',available_at=d['as_of_at']))
    return d


def test_starter_sub_rotation_reserve_roles_and_position_specific_cameos():
    d=pool();cfg=BaselineConfig();opt=options()
    old=simulate(d,5,cfg,draws=100,seed=42);new=simulate(d,5,cfg,draws=100,seed=42,evolution=opt)
    assert new.explanations[1]['role']['role']=='starter'
    assert new.explanations[2]['role']['role']=='reserve'
    assert new.explanations[5]['role']['role']=='substitute'
    assert new.explanations[6]['role']['role']=='rotation'
    assert new.parameters[1]['p_start']>old.parameters[1]['p_start']
    assert new.parameters[2]['p_start']<old.parameters[2]['p_start']
    assert new.parameters[5]['p_sub']>new.parameters[5]['p_start']
    assert new.parameters[2]['p_sub']<new.parameters[5]['p_sub']
    assert new.parameters[1]['start_minutes']>old.parameters[1]['start_minutes']
    for p in new.parameters.values():assert 0<=p['p_start']+p['p_sub']<=1


def test_training_role_is_known_before_its_target_and_prior_excludes_self():
    opt=options();from fpl_model.role_minutes import build_role_priors
    d=pool();d['players']=[dict(id=1,element_type=2,team=1),dict(id=2,element_type=2,team=1)]
    d['histories']=[r for r in d['histories'] if r['player_id'] in (1,2) and r['event']<=2]
    for r in d['histories']:
        r['minutes']=90 if r['player_id']==1 and r['event']==2 else 0;r['starts']=int(r['minutes']>0)
    priors=build_role_priors(d['players'],d['histories'],d['fixtures'][:2],BaselineConfig(),opt)
    assert priors[2]['role']=='reserve'
    # Peer 1 was a reserve BEFORE starting fixture 2; self player 2 is excluded.
    assert priors[2]['peer_role_counts']==[1,0,0]
    assert priors[2]['own_role_counts']==[0,0,1]
    assert priors[1]['role']=='rotation' and priors[1]['peer_role_counts']==[0,0,0]


@pytest.mark.parametrize('problem',['missing','unknown_starts','provisional','short'])
def test_unsafe_or_short_history_preserves_baseline_fallback(problem):
    d=pool();opt=options()
    if problem=='missing':d['histories']=[r for r in d['histories'] if not(r['player_id']==1 and r['event']==2)]
    if problem=='short':
        d['histories']=[r for r in d['histories'] if r['event']==1]
        for f in d['fixtures']:
            if f['event'] in (2,3,4):f['finished']=False
    if problem in ('unknown_starts','provisional'):
        for r in d['histories']:
            if r['player_id']==1:r.update({'starts':None} if problem=='unknown_starts' else {'label_state':'provisional'})
    b=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    n=simulate(d,5,BaselineConfig(),draws=100,seed=42,evolution=opt)
    assert n.explanations[1]['role']['status']=='fallback'
    for key in ('p_start','p_sub','start_minutes','sub_minutes'):assert n.parameters[1][key]==b.parameters[1][key]


def test_availability_applied_once_and_rates_unchanged_and_order_reproducible():
    d=pool();opt=options();cfg=BaselineConfig()
    a=simulate(d,5,cfg,draws=300,seed=42,evolution=opt)
    b=simulate(d,5,cfg,draws=300,seed=42,evolution=opt,availability_overrides={1:.75})
    assert b.parameters[1]['p_start']==pytest.approx(a.parameters[1]['p_start']*.75)
    assert b.parameters[1]['p_sub']==pytest.approx(a.parameters[1]['p_sub']*.75)
    for key in ('goals','assists','bonus','defensive_contribution'):assert a.parameters[1][key]==simulate(d,5,cfg,draws=100,seed=42).parameters[1][key]
    d['players'].reverse();d['histories'].reverse()
    c=simulate(d,5,cfg,draws=300,seed=42,evolution=opt)
    np.testing.assert_array_equal(a.points,c.points)
    np.testing.assert_array_equal(a.minutes,c.minutes)


def test_future_outcomes_metadata_and_target_coverage_do_not_change_earlier_forecasts():
    from fpl_model.backtest.walk_forward import evaluate_sample
    d=pool();opt=options();cfg=BaselineConfig()
    a=evaluate_sample(d,cfg,draws=100,seed=42,evolution=opt)
    changed=copy.deepcopy(d)
    for r in changed['histories']:
        if r['event']==4:r.update(minutes=90,starts=1,total_points=99)
    for p in changed['players']:p.update(starts=999,minutes=99999,status='i')
    b=evaluate_sample(changed,cfg,draws=100,seed=42,evolution=opt)
    assert [r for r in a['rows'] if r['event']==3]==[r for r in b['rows'] if r['event']==3]
    changed=copy.deepcopy(d);changed['histories']=[r for r in changed['histories'] if not(r['player_id']==11 and r['event']==4)]
    c=evaluate_sample(changed,cfg,draws=100,seed=42,evolution=opt)
    assert next(r for r in a['rows'] if r['event']==4 and r['player_id']==1)==next(r for r in c['rows'] if r['event']==4 and r['player_id']==1)


def test_new_version_does_not_change_legacy_config_or_baseline_and_cache(tmp_path):
    opt=options();from fpl_model.transfer_planner import forecast_bundle
    d=pool();cfg=BaselineConfig()
    assert EvolutionConfig(shared_goals=False).version=='component_role_minutes_v1'
    assert EvolutionConfig().version=='component_shared_goals_v1'
    assert opt.version=='component_role_transitions_v2'
    b=simulate(d,5,cfg,draws=100,seed=42)
    simulate(d,5,cfg,draws=100,seed=42,evolution=opt)
    np.testing.assert_array_equal(b.points,simulate(d,5,cfg,draws=100,seed=42).points)
    out=forecast_bundle(d,[5],cfg,origin_at=d['as_of_at'],cache_root=tmp_path,draws=100,evolution=opt)
    assert out['metadata']['model_version']=='component_role_transitions_v2'
    assert 'role_minutes.py' in out['metadata']['code_sha256']
    with pytest.raises(ValueError):EvolutionConfig(minutes_method='unknown')
    with pytest.raises(ValueError):EvolutionConfig(transition_prior_games=0)

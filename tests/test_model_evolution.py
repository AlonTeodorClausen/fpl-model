"""Optional model upgrades must preserve baseline and information boundaries."""
import copy
import importlib.util
import numpy as np
import pytest
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from test_history_coverage_evaluation import history_data


def module():
    assert importlib.util.find_spec('fpl_model.model_evolution'), 'Experimental model not implemented'
    from fpl_model import model_evolution
    return model_evolution


def test_role_responds_to_recent_complete_history_and_not_current_aggregates():
    m=module(); d=history_data(); cfg=BaselineConfig()
    a=simulate(d,5,cfg,draws=200,seed=42,evolution=m.EvolutionConfig(shared_goals=False))
    assert a.parameters[1]['p_start']>simulate(d,5,cfg,draws=200,seed=42).parameters[1]['p_start']
    assert a.parameters[5]['p_start']<simulate(d,5,cfg,draws=200,seed=42).parameters[5]['p_start']
    changed=copy.deepcopy(d)
    for p in changed['players']:p.update(minutes=999999,starts=9999)
    b=simulate(changed,5,cfg,draws=200,seed=42,evolution=m.EvolutionConfig(shared_goals=False))
    np.testing.assert_array_equal(a.minutes[:,:2],b.minutes[:,:2])
    assert a.explanations[1]['role']['method']=='recent_role_v1'


def test_missing_history_does_not_become_zero_and_default_stays_identical():
    m=module();d=history_data();cfg=BaselineConfig()
    a=simulate(d,5,cfg,draws=100,seed=42)
    b=simulate(d,5,cfg,draws=100,seed=42,evolution=None)
    np.testing.assert_array_equal(a.points,b.points)
    d['histories']=[r for r in d['histories'] if not(r['player_id']==1 and r['event']==2)]
    c=simulate(d,5,cfg,draws=100,seed=42,evolution=m.EvolutionConfig(shared_goals=False))
    assert c.explanations[1]['role']['status']=='fallback'
    assert 'incomplete_history_denominator' in c.parameters[1]['fallbacks']


def test_availability_role_and_return_minutes_are_separate():
    m=module();d=history_data();opt=m.EvolutionConfig(shared_goals=False)
    a=simulate(d,5,BaselineConfig(),draws=1000,seed=42,evolution=opt)
    records={1:dict(start_given_available=.2,start_minutes_cap=35,sub_minutes_cap=10,
                    reason='Manager interview',source_url='https://example.org/news',observed_at=d['as_of_at'])}
    b=simulate(d,5,BaselineConfig(),draws=1000,seed=42,evolution=opt,
               availability_overrides={1:.75},role_overrides=records)
    assert b.parameters[1]['p_start']==pytest.approx(.75*.2)
    assert b.minutes[:,0].max()<=35
    assert b.explanations[1]['availability']['probability']==.75
    assert b.explanations[1]['availability']['role_assumption']['source_url']=='https://example.org/news'
    for pid in (2,5):
        idx=next(i for i,p in enumerate(a.players) if p['id']==pid)
        np.testing.assert_array_equal(a.minutes[:,idx],b.minutes[:,idx])
    records[1]['observed_at']='2099-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='after'):simulate(d,5,BaselineConfig(),draws=100,seed=42,evolution=opt,role_overrides=records)


def test_joint_goals_reconcile_and_never_credit_an_absent_scorer():
    m=module();d=history_data();opt=m.EvolutionConfig()
    a=simulate(d,5,BaselineConfig(),draws=300,seed=42,evolution=opt)
    b=simulate(d,5,BaselineConfig(),draws=300,seed=42,evolution=opt)
    np.testing.assert_array_equal(a.points,b.points)
    assert a.match_audit
    for match in a.match_audit:
        for team in match['teams']:
            np.testing.assert_array_equal(team['goals'],team['credited_goals']+team['unattributed_goals'])
            assert np.all(team['credited_assists']<=team['credited_goals'])
            assert team['absent_scorer_count']==0
            assert team['self_assist_count']==0
    for pid,e in a.explanations.items():assert sum(e['point_components'].values())==pytest.approx(e['expected_points'])


def test_future_history_cannot_change_role_evaluation():
    m=module();from fpl_model.backtest.walk_forward import evaluate_sample
    d=history_data();opts=m.EvolutionConfig(shared_goals=False)
    a=evaluate_sample(d,BaselineConfig(),draws=100,seed=42,evolution=opts)
    changed=copy.deepcopy(d)
    for r in changed['histories']:
        if r['event']==4:r.update(starts=1,minutes=90,total_points=999)
    b=evaluate_sample(changed,BaselineConfig(),draws=100,seed=42,evolution=opts)
    assert [r for r in a['rows'] if r['event']==3]==[r for r in b['rows'] if r['event']==3]
    assert a['model_version']=='component_role_minutes_v1'


def test_future_target_coverage_cannot_change_other_players_role_prior():
    m=module();from fpl_model.backtest.walk_forward import evaluate_sample
    d=history_data();opts=m.EvolutionConfig(shared_goals=False)
    # Same position makes cross-player priors sensitive to an unsafe target filter.
    d['players'][4]['element_type']=1
    a=evaluate_sample(d,BaselineConfig(),draws=100,seed=42,evolution=opts)
    d['histories']=[r for r in d['histories'] if not(r['player_id']==5 and r['event']==4)]
    b=evaluate_sample(d,BaselineConfig(),draws=100,seed=42,evolution=opts)
    x=next(r for r in a['rows'] if r['player_id']==1 and r['event']==4)
    y=next(r for r in b['rows'] if r['player_id']==1 and r['event']==4)
    assert x['predicted_minutes']==y['predicted_minutes']
    assert x['model_start']==y['model_start']


def test_goal_assignment_on_pitch_excludes_scorer_from_assists():
    m=module();players=[dict(id=1,team=1),dict(id=2,team=1)]
    params={1:dict(goals=1,assists=1),2:dict(goals=1,assists=1)}
    state={1:dict(minutes=np.array([0,90]),entered=np.array([999,0]),exit_at=np.array([-1,90])),
           2:dict(minutes=np.array([90,0]),entered=np.array([0,999]),exit_at=np.array([90,-1]))}
    r,a=m.allocate_shared_goals(players,params,state,{1:np.array([[30],[30]])},np.random.default_rng(42))
    assert r[1]['goals'].tolist()==[0,1] and r[2]['goals'].tolist()==[1,0]
    assert not r[1]['assists'].any() and not r[2]['assists'].any()


def test_new_variant_cache_and_app_are_explicit_and_keep_default(tmp_path,monkeypatch):
    m=module();from fpl_model.transfer_planner import forecast_bundle
    from test_transfer_planner import context
    data=context();base=forecast_bundle(data,[5],BaselineConfig(),origin_at=data['as_of_at'],cache_root=tmp_path/'cache',draws=100)
    new=forecast_bundle(data,[5],BaselineConfig(),origin_at=data['as_of_at'],cache_root=tmp_path/'cache',draws=100,evolution=m.EvolutionConfig())
    assert new['metadata']['model_version']=='component_shared_goals_v1' and new['cache_key']!=base['cache_key']
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
    model=next(w for w in app.selectbox if w.label=='Prognosemodel');assert model.value=='Baseline'
    model.set_value('Eksperiment · rolle, returminutter og fælles mål').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['lab_transfer_result']['forecast']['model_version']=='component_shared_goals_v1'


def test_news_timestamp_is_capture_time_not_forecast_origin():
    m=module();d=history_data();captured=d['as_of_at'];d['as_of_at']='2026-09-09T13:00:00Z'
    d['input_sources']={'history':{'available_at':captured}}
    out=simulate(d,5,BaselineConfig(),draws=100,seed=42,evolution=m.EvolutionConfig(shared_goals=False))
    assert out.explanations[1]['availability']['available_at']==captured

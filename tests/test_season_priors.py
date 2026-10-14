import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from fpl_model.models.baseline import BaselineConfig, player_parameters
from fpl_model.simulation import simulate
from test_prototype import data


def api():
    assert importlib.util.find_spec('fpl_model.season_priors'), 'Previous-season priors missing'
    from fpl_model import season_priors
    return season_priors


def prior_data():
    d=data();d['season']='2026-2027'
    for p in d['players']:p['code']=1000+p['id']
    d['season_histories']=[dict(player_id=1,element_code=1001,season_name='2025/26',minutes=900,
        expected_goals='5.0',expected_assists='2.0',source='fpl_api',
        available_at='2026-09-09T10:00:00Z',retrieved_at='2026-09-09T10:00:00Z',
        provenance=dict(snapshot_id='synthetic',relative_path='raw/fpl_api/element_summary/1.json',sha256='a'*64))]
    return d


def test_previous_season_prior_is_shrunk_and_current_history_dilutes_it():
    m=api();d=prior_data();p=d['players'][0];cfg=BaselineConfig()
    prior=m.player_prior(d,p,d['as_of_at'],m.SeasonPriorConfig())
    assert prior['status']=='used'
    assert prior['rates']['goals']['prior_per90']==pytest.approx((5+3*.002)/13)
    assert prior['rates']['assists']['prior_per90']==pytest.approx((2+3*.005)/13)
    par=player_parameters(p,[],4,cfg,allow_aggregates=False)
    m.apply_prior(par,prior)
    assert par['goals']==pytest.approx((5+.006)/13)
    assert par['p_start']==cfg.prior_start and par['start_minutes']==cfg.starter_minutes
    history=[dict(event=i,fixture_id=i,minutes=90,starts=1,expected_goals='0.1',expected_assists='0.1') for i in range(1,31)]
    par=player_parameters(p,history,30,cfg,allow_aggregates=False);m.apply_prior(par,prior)
    assert par['goals']==pytest.approx((3+3*(5+.006)/13)/33)
    assert par['explanation']['rates']['goals']['prior_90s']==3
    assert par['explanation']['season_prior']['provenance']['sha256']=='a'*64


def test_time_identity_missing_zero_and_conflicts_are_explicit():
    m=api();d=prior_data();p=d['players'][0];opt=m.SeasonPriorConfig()
    for patch,reason in [(dict(season_name='2026/27'),'no_previous_season'),(dict(element_code=999),'identity_mismatch'),
                         (dict(minutes=0),'no_positive_minutes'),(dict(available_at='2099-01-01T00:00:00Z'),'post_cutoff')]:
        changed=copy.deepcopy(d);changed['season_histories'][0].update(patch)
        assert m.player_prior(changed,p,d['as_of_at'],opt)['reason']==reason
    bad=copy.deepcopy(d);bad['season_histories'][0]['expected_assists']=None
    a=m.player_prior(bad,p,d['as_of_at'],opt)
    assert a['status']=='partial' and a['rates']['assists']['status']=='position_fallback'
    bad['season_histories'][0]['expected_goals']='0.00'
    assert m.player_prior(bad,p,d['as_of_at'],opt)['rates']['goals']['status']=='used'
    bad['season_histories'].append(dict(bad['season_histories'][0],expected_goals='99'))
    assert m.player_prior(bad,p,d['as_of_at'],opt)['reason']=='conflicting_previous_season'
    with pytest.raises(ValueError):m.player_prior(d,p,'2026-09-09',opt)
    for value in [0,-1,float('nan'),True]:
        with pytest.raises(ValueError):m.SeasonPriorConfig(position_prior_90s=value)


def test_asof_ignores_future_versions_and_retrospective_is_explicit():
    m=api();d=prior_data();p=d['players'][0];opt=m.SeasonPriorConfig()
    first=m.player_prior(d,p,d['as_of_at'],opt)
    d['season_histories'].append(dict(d['season_histories'][0],expected_goals='99',available_at='2099-01-01T00:00:00Z'))
    assert m.player_prior(d,p,d['as_of_at'],opt)==first
    d['season_histories']=d['season_histories'][:1]
    assert m.player_prior(d,p,'2026-09-01T00:00:00Z',opt)['status']=='position_fallback'
    r=m.player_prior(d,p,'2026-09-01T00:00:00Z',opt,retrospective=True)
    assert r['status']=='used' and r['availability_contract']=='later_captured_previous_season'
    assert r['available_at']==d['season_histories'][0]['available_at']


def test_simulation_keeps_default_and_every_nonattack_component_identical():
    m=api();d=prior_data();cfg=BaselineConfig();b=simulate(d,5,cfg,draws=300,seed=42)
    a=simulate(d,5,cfg,draws=300,seed=42,season_prior_config=m.SeasonPriorConfig())
    np.testing.assert_array_equal(a.minutes,b.minutes)
    np.testing.assert_array_equal(a.points,simulate(d,5,cfg,draws=300,seed=42,season_prior_config=m.SeasonPriorConfig()).points)
    for pid in a.explanations:
        for key,val in b.explanations[pid]['point_components'].items():
            if key not in ('goals','assists'):assert a.explanations[pid]['point_components'][key]==val
    assert not np.array_equal(a.points,b.points)
    missing={**d,'season_histories':[]}
    np.testing.assert_array_equal(b.points,simulate(missing,5,cfg,draws=300,seed=42,season_prior_config=m.SeasonPriorConfig()).points)
    from fpl_model.conditional_bonus import BonusConfig
    with pytest.raises(ValueError):simulate(d,5,cfg,draws=100,season_prior_config=m.SeasonPriorConfig(),bonus_config=BonusConfig())


def test_read_verified_raw_prior_rows_without_mutating_snapshot(tmp_path):
    m=api()
    from fpl_model.io import SnapshotWriter,verify_snapshot
    from test_player_history_ingestion import NOW
    w=SnapshotWriter(tmp_path/'raw',clock=lambda:NOW)
    def write(path,payload,context=None):
        w.write_raw('fpl_api/'+path,json.dumps(payload).encode(),source='fpl_api',required=True,
            request_started_at=NOW,retrieved_at=NOW,request_context=context or {})
    write('bootstrap_static.json',dict(elements=[dict(id=1,code=1001)]))
    row=prior_data()['season_histories'][0]
    write('element_summary/1.json',dict(history_past=[{k:row[k] for k in ('element_code','season_name','minutes','expected_goals','expected_assists')}]),{'element_id':'1'})
    root=w.finalize();before=(root/'manifest.json').read_bytes()
    rows=m.read_season_histories(root,verify_snapshot(root),[dict(id=1,code=1001)])
    assert len(rows)==1 and rows[0]['player_id']==1 and rows[0]['element_code']==1001
    assert rows[0]['provenance']['snapshot_id']==w.run_id and len(rows[0]['provenance']['sha256'])==64
    assert rows[0]['available_at']==NOW.isoformat(timespec='microseconds')
    assert before==(root/'manifest.json').read_bytes()


def evaluation_data():
    d=prior_data()
    d['histories']=[dict(player_id=1,fixture_id=i,event=i,team_id=1,opponent_team_id=2,
        minutes=90,starts=1,total_points=2+i,label_state='final',expected_goals='0.01',expected_assists='0.01',
        kickoff_time=f'2026-09-{i*2:02d}T14:00:00Z',available_at=d['as_of_at']) for i in range(1,5)]
    return d


def test_chronological_evaluation_keeps_rows_and_never_uses_current_season_aggregates():
    from fpl_model.backtest.walk_forward import evaluate_sample
    opt=api().SeasonPriorConfig();d=evaluation_data();cfg=BaselineConfig()
    b=evaluate_sample(d,cfg,draws=100)
    a=evaluate_sample(d,cfg,draws=100,season_prior_config=opt)
    assert [r['player_id'] for r in a['rows']]==[r['player_id'] for r in b['rows']]
    assert a['rows'][0]['season_prior']['status']=='used'
    assert a['rows'][0]['predicted_minutes']==b['rows'][0]['predicted_minutes']
    changed=copy.deepcopy(d);changed['players'][0]['expected_goals']='999';changed['histories'][-1]['expected_goals']='999'
    changed['season_histories'].append(dict(d['season_histories'][0],season_name='2026/27',expected_goals='999'))
    assert evaluate_sample(changed,cfg,draws=100,season_prior_config=opt)['rows'][0]==a['rows'][0]


def test_prior_cache_and_saved_forecast_preserve_configuration_and_sources(tmp_path):
    from fpl_model.transfer_planner import forecast_bundle
    from fpl_model.prediction_evaluation import save_forecasts,load_forecasts
    m=api();d=prior_data();cfg=BaselineConfig();opt=m.SeasonPriorConfig()
    args=dict(origin_at=d['as_of_at'],cache_root=tmp_path/'cache',draws=100,seed=42)
    b=forecast_bundle(d,[5],cfg,**args)
    a=forecast_bundle(d,[5],cfg,**args,season_prior_config=opt)
    assert a['cache_key']!=b['cache_key']
    assert a['metadata']['model_version'].endswith('__'+m.VERSION)
    assert a['metadata']['season_prior_config']['position_prior_90s']==3
    again=forecast_bundle(d,[5],cfg,**args,season_prior_config=opt)
    np.testing.assert_array_equal(a['scenarios'][5]['points'],again['scenarios'][5]['points'])
    sim=simulate(d,5,cfg,draws=100,seed=42,season_prior_config=opt)
    dest=save_forecasts(d,5,{'previous_season':sim},cfg,None,None,tmp_path/'saved',season_prior_config=opt)
    report,arrays=load_forecasts(dest)
    assert report['season_prior_config']['position_prior_90s']==3
    assert report['variants']['previous_season']['explanations']['1']['season_prior']['provenance']['sha256']=='a'*64
    np.testing.assert_array_equal(sim.points,arrays['previous_season_points'])


def test_odds_prior_changes_attack_allocation_only():
    from fpl_model.defensive_odds import build_coverage
    from test_defensive_odds import coverage_data
    d,row,source=coverage_data();d.update(season='2026-2027',season_histories=prior_data()['season_histories'])
    d['players'][0]['code']=1001;opt=api().SeasonPriorConfig();cfg=BaselineConfig()
    coverage=build_coverage(d,[row],source,5,cfg,d['as_of_at'])
    kwargs=dict(draws=200,seed=42,defensive_odds=coverage,odds_scope='attack_and_defence')
    base=simulate(d,5,cfg,**kwargs);new=simulate(d,5,cfg,**kwargs,season_prior_config=opt)
    np.testing.assert_array_equal(base.minutes,new.minutes)
    assert new.parameters[1]['goals']!=base.parameters[1]['goals']
    for pid in base.explanations:
        for k,v in base.explanations[pid]['point_components'].items():
            if k not in ('goals','assists'):assert new.explanations[pid]['point_components'][k]==v
    for sim in (base,new):
        team=[e['fixtures'][0]['attack_odds'] for pid,e in sim.explanations.items() if e['fixtures'] and next(p for p in sim.players if p['id']==pid)['team']==1]
        assert sum(x['expected_goals'] for x in team)==pytest.approx(team[0]['team_goal_mean'])


def test_prior_opt_in_app_default_off_and_result_persisted(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile
    from fpl_model.my_team import save_profile
    setup(monkeypatch,tmp_path);save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    box=next((x for x in app.checkbox if x.label=='Eksperiment: spillerprior fra sidste sæson'),None)
    assert box is not None and not box.value
    assert next(x for x in app.selectbox if x.label=='Prognosemodel').value=='Baseline'
    box.check().run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['lab_transfer_result']['forecast']['season_prior_config']['position_prior_90s']==3


def test_saved_comparison_has_same_rows_explicit_coverage_and_readonly_ui(tmp_path):
    from streamlit.testing.v1 import AppTest
    from fpl_model.transfer_planner import save_report
    script_path=Path(__file__).resolve().parents[1]/'scripts/compare_season_priors.py'
    assert script_path.is_file(),'Season prior comparison missing'
    spec=importlib.util.spec_from_file_location('compare_season_priors',script_path)
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    report=script.compare_evaluation(evaluation_data(),api().SeasonPriorConfig(),draws=100,seed=42)
    assert len(report['summary'])==3 and all(r['n']==2 for r in report['summary'])
    assert report['evaluations']['previous_season']['rows'][0]['season_prior']['status']=='used'
    save_report(report,tmp_path/'artifacts/season_priors/development')
    assert importlib.util.find_spec('fpl_model.ui.season_priors'),'Season prior comparison UI missing'
    app=AppTest.from_string(f'from fpl_model.ui.season_priors import show_season_prior_comparison\nshow_season_prior_comparison({str(tmp_path)!r})').run(timeout=30)
    assert not app.exception
    assert any('point_MAE' in t.value.columns and len(t.value)==3 for t in app.dataframe)
    assert any('udviklingsdata' in w.value for w in app.warning)


def test_prospective_comparison_reconciles_all_point_deltas():
    script_path=Path(__file__).resolve().parents[1]/'scripts/compare_season_priors.py'
    assert script_path.is_file(),'Season prior comparison missing'
    spec=importlib.util.spec_from_file_location('compare_season_priors',script_path)
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    from fpl_model.defensive_odds import build_coverage
    from test_defensive_odds import coverage_data
    d,row,source=coverage_data();d.update(season='2026-2027',season_histories=prior_data()['season_histories']);d['players'][0]['code']=1001
    c=build_coverage(d,[row],source,5,BaselineConfig(),d['as_of_at'])
    sims,report=script.compare_forecast(d,c,api().SeasonPriorConfig(),draws=100,seed=42)
    assert len(sims)==2
    assert report['prior_coverage']['used']==1
    assert all(r['xp_delta']==pytest.approx(r['goal_delta']+r['assist_delta']) for r in report['player_changes'])

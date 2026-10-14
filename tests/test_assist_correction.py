import copy
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from test_prototype import data


def api():
    assert importlib.util.find_spec('fpl_model.assist_correction'),'FPL assist correction missing'
    from fpl_model import assist_correction
    return assist_correction


def training_data():
    d=data()
    d['histories']=[dict(player_id=i%30+1,fixture_id=100+i,event=1+i//100,
        source='fpl_api',label_state='final',minutes=90 if i%2 else 20,
        assists=1 if i%10==0 else 0,expected_assists='0.05',
        observation_id=f'obs-{i}',source_snapshot_id='synthetic',
        available_at='2026-09-09T10:00:00Z',kickoff_time=f'2026-09-{2+2*(i//100):02d}T14:00:00Z') for i in range(300)]
    return d


def test_shrunk_factor_uses_matched_earlier_final_rows_and_original_provenance():
    m=api();d=training_data();cfg=m.AssistConfig()
    fit=m.fit_correction(d,5,d['as_of_at'],cfg)
    assert fit['status']=='fitted' and fit['training_rows']==300
    assert fit['fpl_assists']==30 and fit['expected_assists']==pytest.approx(15)
    assert fit['factor']==pytest.approx(50/35)
    assert fit['training_observations'][0]['observation_id']
    reverse={**d,'histories':list(reversed(d['histories']))}
    assert m.fit_correction(reverse,5,d['as_of_at'],cfg)==fit
    for change in [dict(event=5),dict(kickoff_time='2099-01-01T00:00:00Z'),dict(available_at='2099-01-01T00:00:00Z'),dict(label_state='provisional')]:
        other=copy.deepcopy(d);other['histories'].append(dict(d['histories'][0],fixture_id=9999,assists=9,**change))
        assert m.fit_correction(other,5,d['as_of_at'],cfg)==fit
    with pytest.raises(ValueError):m.fit_correction(d,5,'2026-09-09',cfg)


def test_missing_xa_not_zero_duplicate_rejected_and_sparse_exact_fallback():
    m=api();d=training_data();cfg=m.AssistConfig()
    d['histories'][0]['expected_assists']=None
    fit=m.fit_correction(d,5,d['as_of_at'],cfg)
    assert fit['training_rows']==299 and fit['fpl_assists']==29
    assert fit['rejected']['missing_or_invalid_fields']==1
    dup=copy.deepcopy(d);dup['histories'].append(dict(d['histories'][1],assists=8))
    with pytest.raises(ValueError,match='Duplicate'):m.fit_correction(dup,5,d['as_of_at'],cfg)
    for r in d['histories']:r['expected_assists']='0.0'
    assert m.fit_correction(d,5,d['as_of_at'],cfg)['reason']=='insufficient_xa_exposure'
    for patch in [dict(prior_xa=0),dict(prior_xa=True),dict(min_rows=0),dict(min_xa=float('nan'))]:
        with pytest.raises(ValueError):m.AssistConfig(**patch)
    plain=data();b=simulate(plain,5,BaselineConfig(),draws=100,seed=42)
    c=simulate(plain,5,BaselineConfig(),draws=100,seed=42,assist_config=cfg)
    assert c.assist_model['status']=='baseline_fallback'
    np.testing.assert_array_equal(b.points,c.points)


def test_only_assists_change_and_no_double_correction_with_odds():
    from fpl_model.defensive_odds import build_coverage
    from test_defensive_odds import coverage_data
    m=api();d,row,source=coverage_data();d['histories']=training_data()['histories']
    cfg=BaselineConfig();cov=build_coverage(d,[row],source,5,cfg,d['as_of_at'])
    for kwargs in [{},dict(defensive_odds=cov,odds_scope='attack_and_defence')]:
        b=simulate(d,5,cfg,draws=300,seed=42,**kwargs)
        c=simulate(d,5,cfg,draws=300,seed=42,assist_config=m.AssistConfig(),**kwargs)
        np.testing.assert_array_equal(b.minutes,c.minutes)
        np.testing.assert_array_equal(c.points,simulate(d,5,cfg,draws=300,seed=42,assist_config=m.AssistConfig(),**kwargs).points)
        for pid in b.explanations:
            old=b.explanations[pid]['point_components'];new=c.explanations[pid]['point_components']
            assert all(new[k]==v for k,v in old.items() if k!='assists')
            assert c.parameters[pid]['assists']==pytest.approx(b.parameters[pid]['assists']*50/35)
            if kwargs and b.explanations[pid]['fixtures']:
                a=b.explanations[pid]['fixtures'][0]['attack_odds'];z=c.explanations[pid]['fixtures'][0]['attack_odds']
                assert z['goal_share']==a['goal_share']
                assert z['assist_share']==pytest.approx(a['assist_share'])
                assert z['team_assist_fraction']==pytest.approx(min(1,a['team_assist_fraction']*50/35))
        assert not np.array_equal(b.points,c.points)
    from fpl_model.season_priors import SeasonPriorConfig
    with pytest.raises(ValueError):simulate(d,5,cfg,draws=100,assist_config=m.AssistConfig(),season_prior_config=SeasonPriorConfig())


def evaluation_data():
    from test_conditional_bonus import evaluation_data as fixture
    d=fixture()
    for r in d['histories']:r.update(expected_assists='0.2',assists=int(r['player_id']%3==0))
    return d


def test_evaluation_uses_prefix_and_full_prior_pool_not_target_availability():
    from fpl_model.backtest.walk_forward import evaluate_sample
    m=api();d=evaluation_data();cfg=BaselineConfig();opt=m.AssistConfig(min_rows=20)
    b=evaluate_sample(d,cfg,draws=100,assist_diagnostics=True)
    a=evaluate_sample(d,cfg,draws=100,assist_config=opt,assist_diagnostics=True)
    assert a['assist_fits'][3]['training_gameweeks']==[1,2]
    for x,y in zip(b['rows'],a['rows']):
        assert (x['event'],x['player_id'])==(y['event'],y['player_id'])
        assert x['predicted_minutes']==y['predicted_minutes']
        assert y['predicted']-x['predicted']==pytest.approx(3*(y['predicted_assists']-x['predicted_assists']))
    altered=copy.deepcopy(d)
    for r in altered['histories']:
        if r['event']>=3:r.update(assists=10,expected_assists='100')
    assert evaluate_sample(altered,cfg,draws=100,assist_config=opt)['assist_fits'][3]==a['assist_fits'][3]
    altered['histories']=[r for r in d['histories'] if not (r['event']==3 and r['player_id']==1)]
    assert evaluate_sample(altered,cfg,draws=100,assist_config=opt)['assist_fits'][3]==a['assist_fits'][3]
    assert m.fit_correction(d,3,'2026-09-06T12:00:00Z',opt)['status']=='baseline_fallback'


def test_cache_and_saved_arrays_preserve_fitted_assist_model(tmp_path):
    from fpl_model.transfer_planner import forecast_bundle
    from fpl_model.prediction_evaluation import save_forecasts,load_forecasts
    d=training_data();cfg=BaselineConfig();opt=api().AssistConfig()
    kwargs=dict(origin_at=d['as_of_at'],cache_root=tmp_path/'cache',draws=100,seed=42)
    base=forecast_bundle(d,[5],cfg,**kwargs);new=forecast_bundle(d,[5],cfg,**kwargs,assist_config=opt)
    assert base['cache_key']!=new['cache_key'] and new['metadata']['model_version'].endswith('__fpl_assist_correction_v1')
    assert new['metadata']['assist_training']['5']['factor']==pytest.approx(50/35)
    repeat=forecast_bundle(d,[5],cfg,**kwargs,assist_config=opt)
    assert repeat['assist_models'][5]==new['assist_models'][5]
    sim=simulate(d,5,cfg,draws=100,seed=42,assist_config=opt)
    path=save_forecasts(d,5,{'assist':sim},cfg,None,None,tmp_path/'forecast',assist_config=opt)
    r,arrays=load_forecasts(path)
    assert r['variants']['assist']['assist_model']['training_sha256']==sim.assist_model['training_sha256']
    assert r['assist_config']['prior_xa']==20
    np.testing.assert_array_equal(sim.points,arrays['assist_points'])


def test_assist_option_default_off_and_persisted_in_app(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile
    from fpl_model.my_team import save_profile
    setup(monkeypatch,tmp_path);save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    box=next((x for x in app.checkbox if x.label=='Eksperiment: FPL-assistkorrektion'),None)
    assert box is not None and not box.value
    box.check().run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['lab_transfer_result']['forecast']['assist_config']['prior_xa']==20


def script():
    path=Path(__file__).resolve().parents[1]/'scripts/compare_assists.py'
    assert path.is_file(),'Assist comparison CLI missing'
    spec=importlib.util.spec_from_file_location('compare_assists',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_saved_comparison_ui_reads_metrics_and_folds(tmp_path):
    from streamlit.testing.v1 import AppTest
    from fpl_model.transfer_planner import save_report
    r=script().compare_evaluation(evaluation_data(),api().AssistConfig(min_rows=20),draws=100,seed=42)
    assert len(r['summary'])==3 and all(x['n']==60 for x in r['summary'])
    save_report(r,tmp_path/'artifacts/assist_correction/development')
    assert importlib.util.find_spec('fpl_model.ui.assists'),'Assist UI missing'
    app=AppTest.from_string(f'from fpl_model.ui.assists import show_assist_comparison\nshow_assist_comparison({str(tmp_path)!r})').run(timeout=30)
    assert not app.exception
    assert any('assist_MAE' in x.value.columns and len(x.value)==3 for x in app.dataframe)
    assert any('factor' in x.value.columns for x in app.dataframe)


def test_odds_comparison_only_assist_points_reconciles():
    from fpl_model.defensive_odds import build_coverage
    from test_defensive_odds import coverage_data
    d,row,source=coverage_data();d['histories']=training_data()['histories']
    cov=build_coverage(d,[row],source,5,BaselineConfig(),d['as_of_at'])
    sims,r=script().compare_forecast(d,cov,api().AssistConfig(),draws=100,seed=42)
    assert len(sims)==2 and r['factor']==pytest.approx(50/35)
    assert all(x['xp_delta']==pytest.approx(x['assist_points_delta']) for x in r['player_changes'])

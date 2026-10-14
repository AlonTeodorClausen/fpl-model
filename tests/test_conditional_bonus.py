import copy
import importlib.util

import numpy as np
import pytest

from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from test_prototype import data


def api():
    assert importlib.util.find_spec('fpl_model.conditional_bonus'), 'Conditional bonus not implemented'
    from fpl_model import conditional_bonus
    return conditional_bonus


def training_data():
    d=data()
    # Entirely synthetic: scoring starters earn bonus, non-scoring cameos do not.
    d['histories']=[dict(player_id=(i%30)+1,fixture_id=i+100,event=1+i//90,
        source='fpl_api',observation_id=f'obs-{i}',source_snapshot_id='train',
        kickoff_time=f'2026-09-{2+2*(i//90):02d}T14:00:00Z',
        available_at='2026-09-09T10:00:00Z',label_state='final',
        minutes=90 if i%3 else 20,goals_scored=1 if i%3 else 0,
        assists=0,clean_sheets=0,defensive_contribution=2,bonus=2 if i%3 else 0)
        for i in range(300)]
    return d


def test_fit_uses_only_earlier_final_observations_and_preserves_provenance():
    m=api();d=training_data();cfg=m.BonusConfig()
    first=m.fit_bonus(d,5,d['as_of_at'],cfg)
    assert first['status']=='fitted' and first['training_rows']==300
    assert first['sub60_rows']==100
    assert len(first['training_observations'])==300
    extra=dict(d['histories'][0],fixture_id=9999,bonus=3)
    for change in [dict(available_at='2099-01-01T00:00:00Z'),dict(label_state='provisional'),
                   dict(event=5),dict(kickoff_time='2099-01-01T00:00:00Z')]:
        changed=copy.deepcopy(d);changed['histories'].append(dict(extra,**change))
        fitted=m.fit_bonus(changed,5,d['as_of_at'],cfg)
        assert fitted['training_sha256']==first['training_sha256']
        assert fitted['coefficients']==first['coefficients']
    reverse={**d,'histories':list(reversed(d['histories'])),'players':list(reversed(d['players']))}
    assert m.fit_bonus(reverse,5,d['as_of_at'],cfg)==first
    with pytest.raises(ValueError):m.fit_bonus(d,5,'2026-09-09T12:00:00',cfg)


def test_bounded_bonus_responds_to_goals_and_includes_cameos_not_dnp():
    m=api();d=training_data();model=m.fit_bonus(d,5,d['as_of_at'],m.BonusConfig())
    minutes=np.array([0,20,90,90,90])
    components=dict(goals=np.array([0,0,0,4,12]),assists=np.zeros(5),
        clean_sheets=np.zeros(5),defensive_contribution=np.zeros(5))
    mean=m.expected_bonus(model,4,minutes,components)
    assert mean[0]==0 and 0<mean[1]<3
    assert mean[2]<mean[3]<=mean[4]<=3
    draws=m.sample_bonus(model,4,np.repeat(90,10000),
        dict(goals=np.repeat(4,10000),assists=0,clean_sheets=0,defensive_contribution=0),seed=42,fixture_id=1,player_id=1)
    assert set(draws)<=set(range(4))
    assert draws.mean()==pytest.approx(mean[3],abs=.04)


def test_missing_invalid_sparse_and_duplicate_training_are_explicit():
    m=api();d=training_data();cfg=m.BonusConfig()
    bad=copy.deepcopy(d)
    for row in bad['histories']:row['bonus']=None
    model=m.fit_bonus(bad,5,d['as_of_at'],cfg)
    assert model['status']=='baseline_fallback' and model['rejected']['missing_or_invalid_fields']==300
    empty=m.fit_bonus(data(),5,d['as_of_at'],cfg)
    assert empty['status']=='baseline_fallback'
    dup=copy.deepcopy(d);dup['histories'].append(dict(dup['histories'][0],bonus=3))
    with pytest.raises(ValueError,match='Duplicate'):m.fit_bonus(dup,5,d['as_of_at'],cfg)
    for cfg in [dict(ridge=0),dict(ridge=float('nan')),dict(min_rows=-1)]:
        with pytest.raises(ValueError):m.BonusConfig(**cfg)


def test_simulation_changes_bonus_only_reproducibly_with_exact_sparse_fallback():
    m=api();d=training_data();cfg=BaselineConfig()
    # Irregular synthetic histories are used for bonus fitting only.
    baseline=simulate(d,5,cfg,draws=300,seed=42)
    candidate=simulate(d,5,cfg,draws=300,seed=42,bonus_config=m.BonusConfig())
    np.testing.assert_array_equal(candidate.minutes,baseline.minutes)
    np.testing.assert_array_equal(candidate.points,simulate(d,5,cfg,draws=300,seed=42,bonus_config=m.BonusConfig()).points)
    assert candidate.bonus_model['status']=='fitted'
    assert not np.array_equal(candidate.points,baseline.points)
    for pid,e in baseline.explanations.items():
        c=candidate.explanations[pid]
        for k,v in e['point_components'].items():
            if k!='bonus':assert c['point_components'][k]==v
        assert c['expected_points']-e['expected_points']==pytest.approx(c['point_components']['bonus']-e['point_components']['bonus'])
    empty=data();a=simulate(empty,5,cfg,draws=100,seed=1)
    b=simulate(empty,5,cfg,draws=100,seed=1,bonus_config=m.BonusConfig())
    np.testing.assert_array_equal(a.points,b.points)
    assert b.bonus_model['status']=='baseline_fallback'


def test_retrospective_training_is_explicit_and_future_targets_cannot_enter():
    m=api();d=training_data();d['as_of_at']='2026-09-01T12:00:00Z'
    cfg=m.BonusConfig()
    live=m.fit_bonus(d,3,'2026-09-06T12:30:00Z',cfg)
    old=m.fit_bonus(d,3,'2026-09-06T12:30:00Z',cfg,retrospective=True)
    assert live['training_rows']==0 and old['training_rows']==180
    assert old['availability_contract']=='later_captured_labels_prior_events_only'
    changed=copy.deepcopy(d)
    for r in changed['histories']:
        if r['event']>=3:r['bonus']=3
    assert m.fit_bonus(changed,3,'2026-09-06T12:30:00Z',cfg,retrospective=True)==old


def evaluation_data():
    d=data()
    d['players']=[dict(p,team=1) for p in d['players']]
    d['histories']=[]
    for p in d['players']:
        for event in range(1,5):
            g=int(p['id']%3==0)
            d['histories'].append(dict(player_id=p['id'],fixture_id=event,event=event,team_id=1,opponent_team_id=2,
                source='fpl_api',source_snapshot_id='test',observation_id=f"{p['id']}:{event}",
                label_state='final',kickoff_time=f'2026-09-{event*2:02d}T14:00:00Z',
                available_at='2026-09-09T10:00:00Z',minutes=90,starts=1,goals_scored=g,
                assists=0,clean_sheets=1,defensive_contribution=2,bonus=2*g,
                total_points=2+4*g,expected_goals=str(g),expected_assists='0'))
    return d


def test_evaluation_has_same_rows_and_trains_before_each_fold_not_target_filter():
    from fpl_model.backtest.walk_forward import evaluate_sample
    m=api();d=evaluation_data();cfg=BaselineConfig();opt=m.BonusConfig(min_rows=20)
    b=evaluate_sample(d,cfg,draws=100,seed=42,bonus_diagnostics=True)
    a=evaluate_sample(d,cfg,draws=100,seed=42,bonus_config=opt,bonus_diagnostics=True)
    assert [(r['event'],r['player_id']) for r in a['rows']]==[(r['event'],r['player_id']) for r in b['rows']]
    for x,y in zip(a['rows'],b['rows']):
        assert x['predicted_minutes']==y['predicted_minutes'] and x['p_no_play']==y['p_no_play']
        assert x['predicted']-y['predicted']==pytest.approx(x['predicted_bonus']-y['predicted_bonus'])
    assert a['bonus_fits'][3]['training_gameweeks']==[1,2]
    d['histories']=[r for r in d['histories'] if not (r['event']==3 and r['player_id']==1)]
    missing=evaluate_sample(d,cfg,draws=100,seed=42,bonus_config=opt)
    assert a['bonus_fits'][3]==missing['bonus_fits'][3]


def test_cache_and_saved_forecast_preserve_model_training_and_config(tmp_path):
    from fpl_model.transfer_planner import forecast_bundle
    from fpl_model.prediction_evaluation import save_forecasts,load_forecasts
    m=api();d=training_data();cfg=BaselineConfig();opt=m.BonusConfig()
    kw=dict(origin_at=d['as_of_at'],cache_root=tmp_path/'cache',draws=100,seed=42)
    b=forecast_bundle(d,[5],cfg,**kw)
    a=forecast_bundle(d,[5],cfg,**kw,bonus_config=opt)
    assert a['cache_key']!=b['cache_key']
    assert a['metadata']['model_version'].endswith('__'+m.VERSION)
    assert a['bonus_models'][5]['status']=='fitted'
    assert a['metadata']['bonus_training']['5']['status']=='fitted'
    reused=forecast_bundle(d,[5],cfg,**kw,bonus_config=opt)
    np.testing.assert_array_equal(a['scenarios'][5]['points'],reused['scenarios'][5]['points'])
    s=simulate(d,5,cfg,draws=100,seed=42,bonus_config=opt)
    out=save_forecasts(d,5,{'bonus':s},cfg,None,None,tmp_path/'saved',bonus_config=opt)
    report,arrays=load_forecasts(out)
    assert report['bonus_config']['ridge']==opt.ridge
    assert report['variants']['bonus']['bonus_model']['training_sha256']==s.bonus_model['training_sha256']
    np.testing.assert_array_equal(s.points,arrays['bonus_points'])


def test_bonus_opt_in_in_app_leaves_default_and_saves_selection(monkeypatch,tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile
    from fpl_model.my_team import save_profile
    setup(monkeypatch,tmp_path);save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    checkbox=next((w for w in app.checkbox if w.label=='Eksperiment: præstationsafhængig bonus'),None)
    assert checkbox is not None and not checkbox.value
    assert next(w for w in app.selectbox if w.label=='Prognosemodel').value=='Baseline'
    checkbox.check().run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    result=app.session_state['lab_transfer_result']
    assert result['forecast']['model_version'].endswith('__conditional_bonus_v1')
    assert result['forecast']['bonus_config']['ridge']==1.


def test_odds_bonus_comparison_reconciles_and_is_available_in_analysis(tmp_path):
    from pathlib import Path
    from fpl_model.defensive_odds import build_coverage
    from test_defensive_odds import coverage_data
    spec=importlib.util.spec_from_file_location('compare_bonus',Path(__file__).resolve().parents[1]/'scripts/compare_bonus.py')
    assert spec and Path(spec.origin).exists(),'Bonus comparison command missing'
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    d,row,source=coverage_data();coverage=build_coverage(d,[row],source,5,BaselineConfig(),d['as_of_at'])
    sims,report=script.compare_forecast(d,coverage,api().BonusConfig(),draws=100,seed=42)
    assert report['invariants']['other_components_identical']
    assert all(r['xp_delta']==pytest.approx(r['bonus_delta']) for r in report['player_changes'])


def test_saved_comparison_panel_shows_metrics_and_training_without_new_runs(tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from fpl_model.transfer_planner import save_report
    spec=importlib.util.spec_from_file_location('compare_bonus',Path(__file__).resolve().parents[1]/'scripts/compare_bonus.py')
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    report=script.compare_evaluation(evaluation_data(),api().BonusConfig(min_rows=20),draws=100,seed=42)
    save_report(report,tmp_path/'artifacts/conditional_bonus/development')
    assert importlib.util.find_spec('fpl_model.ui.bonus'),'Bonus results UI missing'
    app=AppTest.from_string(f"from fpl_model.ui.bonus import show_bonus_comparison\nshow_bonus_comparison({str(tmp_path)!r})").run(timeout=30)
    assert not app.exception
    tables=[x.value for x in app.dataframe]
    assert any('bonus_MAE' in t.columns and len(t)==3 for t in tables)
    assert any('training_rows' in t.columns for t in tables)
    assert any('udviklingsdata' in x.value for x in app.warning)

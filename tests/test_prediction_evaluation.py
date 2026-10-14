import copy
import importlib.util
import json
import numpy as np
import pytest
from test_observation_selection import row


def module():
    assert importlib.util.find_spec('fpl_model.prediction_evaluation'), 'Saved-forecast evaluation missing'
    from fpl_model import prediction_evaluation
    return prediction_evaluation


def prediction():
    return dict(season='2026-2027',event=4,forecast_origin_at='2026-09-10T12:00:00Z',
                created_at='2026-09-10T12:01:00Z',deadline_at='2026-09-11T10:00:00Z',
                provenance_status='recorded_pre_deadline',players=[dict(player_id=1,position=2,fixture_ids=[11])])


def test_only_final_outcomes_and_preserved_forecast():
    m=module();p=prediction();before=copy.deepcopy(p)
    samples=np.array([[2],[6],[10]],float);minutes=np.array([[0],[90],[90]])
    r=m.evaluate_predictions(p,samples,minutes,[row()],model_version='test')
    assert r['n']==0 and r['pending'][0]['reason']=='no_final_observation'
    r=m.evaluate_predictions(p,samples,minutes,[row(state='final')],model_version='test')
    assert r['n']==1 and r['points']['mae']==0 and r['dnp']['brier']==pytest.approx(1/9)
    assert r['rows'][0]['target_available_at']>'2026-09-11T10:00:00Z'
    assert r['points']['crps']>=0 and p==before
    assert r['interval_80']['n']==1 and r['by_position'][0]['n']==1


def test_missing_dnp_conflicts_and_postponement_are_not_silently_scored():
    m=module();p=prediction();x=np.ones((100,1));mins=x*90
    assert m.evaluate_predictions(p,x,mins,[],model_version='test')['n']==0
    a=row(state='final');b=row('b',state='final',total_points=8)
    b['official_history']['total_points']=8
    r=m.evaluate_predictions(p,x,mins,[a,b],model_version='test')
    assert r['pending'][0]['reason']=='conflict'
    postponed=row(state='final',event=5);postponed['official_history']['round']=5
    r=m.evaluate_predictions(p,x,mins,[postponed],model_version='test')
    assert r['pending'][0]['reason']=='fixture_moved_event'
    zero=row(state='final',minutes=0,total_points=0);zero['official_history'].update(minutes=0,total_points=0)
    assert m.evaluate_predictions(p,x,mins,[zero],model_version='test')['rows'][0]['actual_dnp']==1


def test_immutable_saved_samples_checksums_and_late_forecast_status(tmp_path):
    m=module();from fpl_model.models.baseline import BaselineConfig
    from fpl_model.simulation import simulate
    from test_history_coverage_evaluation import history_data
    d=history_data();sim=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    out=m.save_forecasts(d,5,{'baseline':sim},BaselineConfig(),None,None,tmp_path)
    saved=(out/'forecast.json').read_bytes()
    report,arrays=m.load_forecasts(out)
    assert report['provenance_status']=='not_pre_deadline' # written after the synthetic Sept deadline
    assert arrays['baseline_points'].shape==(100,len(d['players']))
    second=m.save_forecasts(d,5,{'baseline':sim},BaselineConfig(),None,None,tmp_path)
    assert second!=out and saved==(out/'forecast.json').read_bytes()
    with (out/'scenarios.npz').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError,match='checksum'):m.load_forecasts(out)


def test_added_dgw_fixture_requires_complete_changed_universe():
    m=module();p=prediction();a=row(state='final')
    b=row('b',state='final',fixture_id=12,observation_id='2026-2027:b:1:12')
    b['official_history']['fixture']=12
    r=m.evaluate_predictions(p,np.ones((100,1)),np.ones((100,1))*90,[a,b],model_version='test')
    assert r['n']==0 and r['pending'][0]['reason']=='fixture_universe_changed'


def test_app_shows_saved_prediction_and_pending_outcomes(tmp_path):
    m=module()
    from fpl_model.models.baseline import BaselineConfig
    from fpl_model.simulation import simulate
    from test_history_coverage_evaluation import history_data
    from streamlit.testing.v1 import AppTest
    d=history_data();sim=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    m.save_forecasts(d,5,{'component_baseline_v1':sim},BaselineConfig(),None,None,tmp_path/'artifacts/model_forecasts')
    app=AppTest.from_string('from fpl_model.ui.model_quality import show_model_quality\n'
                           f'show_model_quality({str(tmp_path)!r},dict(histories=[]))').run()
    assert not app.exception
    next(b for b in app.button if b.label=='Efterkontrollér mod indlæste officielle slutresultater').click().run()
    assert not app.exception
    assert list((tmp_path/'artifacts/model_evaluations').glob('*/report.json'))
    assert any('awaiting_final_outcomes' in x.value for x in app.markdown)

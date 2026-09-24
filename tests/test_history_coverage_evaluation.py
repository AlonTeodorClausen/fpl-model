"""Coverage must gate denominators; evaluation groups share identical target rows."""
import copy
import importlib.util
import numpy as np

from test_prototype import data
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from fpl_model.backtest.walk_forward import evaluate_sample


def history_data():
    d=data();d['histories']=[]
    for pid,position,minutes,points in [(1,1,90,4),(5,2,0,0)]:
        for event in range(1,5):
            d['histories'].append(dict(player_id=pid,fixture_id=event,event=event,team_id=1,
                minutes=minutes,starts=int(minutes>0),total_points=points,label_state='final',
                expected_goals='0.01',expected_assists='0.01',
                kickoff_time=f'2026-09-{event*2:02d}T14:00:00Z',available_at=d['as_of_at']))
    return d


def test_missing_fixture_cannot_raise_start_frequency_by_shrinking_denominator():
    d=history_data();d['histories']=[r for r in d['histories'] if r['player_id']==1 and r['event']!=2]
    result=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    par=result.parameters[1]
    assert par['basis']=='season_aggregates'
    assert 'incomplete_history_denominator' in par['fallbacks']
    assert 'expected_missing_fixture_ids' in par and par['expected_missing_fixture_ids']==[2]
    assert len(d['histories'])==3  # no synthetic DNP


def test_group_metrics_minutes_and_dnp_use_same_rows():
    r=evaluate_sample(history_data(),BaselineConfig(),draws=200,seed=42)
    assert r['n']==4 and r['player_count']==2 and r['gameweeks']==[3,4]
    assert {g['position']:g['n'] for g in r['by_position']}=={1:2,2:2}
    assert {g['event']:g['n'] for g in r['by_gameweek']}=={3:2,4:2}
    assert r['minutes']['n']==4 and r['dnp']['n']==4
    assert np.isclose(r['minutes']['mae'],np.mean([abs(x['predicted_minutes']-x['actual_minutes']) for x in r['rows']]))
    assert np.isclose(r['dnp']['brier'],np.mean([(x['p_no_play']-x['actual_dnp'])**2 for x in r['rows']]))
    assert sum(b['n'] for b in r['dnp']['bins'])==4
    assert all(x['position'] in (1,2) and x['prior_rows']>=2 for x in r['rows'])
    assert r['evaluation_version'] and r['model_version'] and r['config']


def test_history_hole_and_missing_target_are_excluded_not_dnp():
    d=history_data()
    d['histories']=[r for r in d['histories'] if not (r['player_id']==1 and r['event']==2)]
    result=evaluate_sample(d,BaselineConfig(),draws=100,seed=42)
    assert result['player_count']==1 and {r['player_id'] for r in result['rows']}=={5}
    assert any(e['player_id']==1 and e['reason']=='incomplete_prior_history' for e in result['excluded'])


def test_future_values_cannot_change_earlier_predictions_or_eligibility():
    d=history_data();a=evaluate_sample(d,BaselineConfig(),draws=100,seed=42)
    changed=copy.deepcopy(d)
    for r in changed['histories']:
        if r['event']==4: r.update(minutes=90,starts=1,total_points=999,expected_goals='999')
    for p in changed['players']: p.update(minutes=99999,starts=999,expected_goals='999',status='i')
    b=evaluate_sample(changed,BaselineConfig(),draws=100,seed=42)
    assert [r for r in a['rows'] if r['event']==3]==[r for r in b['rows'] if r['event']==3]


def test_complete_histories_keep_original_baseline_parameters():
    from fpl_model.models.baseline import player_parameters
    d=history_data();cfg=BaselineConfig()
    result=simulate(d,5,cfg,draws=100,seed=42)
    direct=player_parameters(d['players'][0],[r for r in d['histories'] if r['player_id']==1],4,cfg)
    assert all(result.parameters[1][k]==v for k,v in direct.items())


def test_saved_run_is_versioned_and_records_baseline_and_data(tmp_path):
    import json
    import fpl_model.prototype as service
    assert hasattr(service,'save_run')
    d=history_data();d['manifest_sha256']='test-source-digest'
    report,_,_=service.run_prototype(d,5,BaselineConfig(),draws=100,seed=42)
    assert report['model_version']=='component_baseline_v1'
    assert report['manifest_sha256']=='test-source-digest'
    assert report['code_sha256'] and report['runtime_versions']
    path=service.save_run(report,tmp_path/'first')
    original=(path/'report.json').read_bytes()
    import pytest
    with pytest.raises(FileExistsError): service.save_run(report,tmp_path/'first')
    assert (path/'report.json').read_bytes()==original
    assert json.loads(original)['evaluation']['n']==4

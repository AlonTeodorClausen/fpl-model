"""Stored summaries are evaluated as summaries, never invented distributions."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from test_observation_selection import row


def module():
    assert importlib.util.find_spec('fpl_model.forecast_review'), 'Practical forecast review missing'
    from fpl_model import forecast_review
    return forecast_review


def legacy():
    history=dict(matches=3,mean_minutes=80,played_frequency=1.)
    player=dict(player_id=1,name='Example',position=2,xp=5.,expected_minutes=80.,p_no_play=.2,p10=1.,p90=9.)
    variant=dict(event=4,as_of_at='2026-09-10T12:00:00Z',created_at='2026-09-10T12:01:00Z',
                 model_version='component_baseline_v1',config={},draws=3000,seed=42,players=[player],
                 player_explanations={'1':dict(fixtures=[dict(fixture_id=11)],captured_history=history,history_coverage='complete_observed_window')})
    return dict(kind='current_forecast_comparison',event=4,forecast_origin_at=variant['as_of_at'],
                deadline_at='2026-09-11T10:00:00Z',baseline=variant,
                odds_variant={**copy.deepcopy(variant),'model_version':'component_defensive_odds_v1'})


def test_legacy_summary_scores_actual_same_rows_without_fabricating_crps(tmp_path):
    m=module();p=tmp_path/'comparison.json';p.write_text(json.dumps(legacy()));before=p.read_bytes()
    _,r=m.review_forecast(p,[row(state='final')],tmp_path/'reviews',season='2026-2027')
    assert r['format']=='legacy_summary' and r['provenance_status']=='unverified_provenance'
    for v in r['variants'].values():
        assert v['n']==1 and v['points']['mae']==1 and v['minutes']['bias']==-10
        assert v['points']['crps'] is None and v['dnp']['brier']==pytest.approx(.04)
        assert v['by_history_group']['regular']['n']==1
        assert v['rows'][0]['target_available_at']>'2026-09-11T10:00:00Z'
    assert r['same_player_ids']==[1] and p.read_bytes()==before


def test_no_fake_dnp_and_changed_or_conflicting_targets_excluded(tmp_path):
    m=module();p=tmp_path/'comparison.json';p.write_text(json.dumps(legacy()))
    for obs in ([],[row()], [row(state='final'),row('b',state='final',total_points=9,official_history={**row()['official_history'],'total_points':9})]):
        _,r=m.review_forecast(p,obs,tmp_path/'reviews',season='2026-2027')
        assert all(v['n']==0 and v['points'] is None for v in r['variants'].values())
    zero=row(state='final',minutes=0,total_points=0);zero['official_history'].update(minutes=0,total_points=0)
    _,r=m.review_forecast(p,[zero],tmp_path/'reviews',season='2026-2027')
    assert r['variants']['baseline']['rows'][0]['actual_dnp']==1


def test_synthetic_and_mismatched_comparisons_are_rejected(tmp_path):
    m=module();p=tmp_path/'comparison.json'
    a=legacy();a['kind']='synthetic_offline_example_NOT_CURRENT_FORECAST';p.write_text(json.dumps(a))
    with pytest.raises(ValueError,match='Synthetic'):m.review_forecast(p,[],tmp_path/'reviews',season='2026-2027')
    for key,value in [('seed',43),('config',{'x':2}),('players',[])]:
        a=legacy();a['odds_variant'][key]=value;p.write_text(json.dumps(a))
        with pytest.raises(ValueError):m.review_forecast(p,[],tmp_path/'reviews',season='2026-2027')


def test_late_forecast_not_claimed_prospective_and_same_seed_not_recomputed(tmp_path,monkeypatch):
    m=module();p=tmp_path/'comparison.json';a=legacy();a['baseline']['created_at']='2026-09-15T12:00:00Z'
    p.write_text(json.dumps(a))
    import fpl_model.simulation as sim
    monkeypatch.setattr(sim,'simulate',lambda *a,**k:pytest.fail('Never rerun a forecast in review'))
    _,r=m.review_forecast(p,[row(state='final')],tmp_path/'reviews',season='2026-2027')
    assert r['provenance_status']=='not_pre_deadline'


def test_readiness_uses_flags_not_elapsed_kickoff():
    m=module();c=dict(events=[dict(id=6,finished=False,data_checked=False)],
                        fixtures=[dict(id=51,event=6,finished=False,finished_provisional=True,kickoff_time='2026-10-10T12:00:00Z'),
                                  dict(id=52,event=6,finished=False,finished_provisional=False,kickoff_time='2026-10-12T19:00:00Z')])
    r=m.event_readiness(c,6);assert r['status']=='awaiting_official_finality' and r['provisionally_finished']==1
    assert r['remaining_fixture_ids']==[51,52]
    for f in c['fixtures']:f['finished']=True
    assert m.event_readiness(c,6)['status']=='awaiting_official_finality'
    c['events'][0].update(finished=True,data_checked=True)
    assert m.event_readiness(c,6)['status']=='context_final_labels_still_required'


def test_review_prefers_latest_completed_gw_over_newer_unfinished_deadline():
    from datetime import datetime,timezone
    from fpl_model.ui.forecast_review import preferred_review_index
    choices=[dict(event=6,origin='2026-10-06T10:00:00Z',deadline_at='2026-10-10T10:00:00Z'),
             dict(event=7,origin='2026-10-16T10:00:00Z',deadline_at='2026-10-17T10:00:00Z')]
    context=dict(events=[dict(id=6,finished=True,data_checked=True),
                         dict(id=7,finished=False,data_checked=False)],
                 fixtures=[dict(id=51,event=6,finished=True),dict(id=61,event=7,finished=False)])
    now=datetime(2026,10,18,tzinfo=timezone.utc)
    assert preferred_review_index(choices,context,now)==0
    context['events'][1].update(finished=True,data_checked=True)
    context['fixtures'][1]['finished']=True
    assert preferred_review_index(choices,context,now)==1


def test_review_attributes_labels_to_history_snapshot_not_fresh_context():
    from fpl_model.ui.forecast_review import outcome_source_reference
    data=dict(snapshot_id='new-context',snapshot_path='/raw/new',manifest_sha256='new-hash',
              as_of_at='2026-10-15T10:00:00Z',input_sources=dict(history=dict(
                  snapshot_id='old-history',snapshot_path='/raw/old',manifest_sha256='old-hash',
                  available_at='2026-10-14T20:00:00Z')))
    assert outcome_source_reference(data)==dict(snapshot_id='old-history',snapshot_path='/raw/old',
        manifest_sha256='old-hash',as_of_at='2026-10-14T20:00:00Z')


def test_new_context_snapshot_does_not_displace_full_history_default(tmp_path):
    from fpl_model import prototype_data
    assert hasattr(prototype_data,'preferred_snapshot_index')
    context=tmp_path/'new';history=tmp_path/'old';context.mkdir();history.mkdir()
    (context/'manifest.json').write_text(json.dumps(dict(files=[dict(source='fpl_api',relative_path='raw/fpl_api/bootstrap_static.json',outcome='success')])))
    (history/'manifest.json').write_text(json.dumps(dict(files=[dict(source='fpl_api',relative_path='raw/fpl_api/element_summary/1.json',outcome='success')])))
    assert prototype_data.preferred_snapshot_index([context,history])==1
    assert prototype_data.preferred_snapshot_index([context])==0


def test_saved_scenarios_reuse_crps_and_check_integrity(tmp_path):
    m=module()
    from fpl_model.prediction_evaluation import save_forecasts
    from fpl_model.models.baseline import BaselineConfig
    from fpl_model.simulation import simulate
    from test_history_coverage_evaluation import history_data
    d=history_data();sim=simulate(d,5,BaselineConfig(),draws=100,seed=42)
    path=save_forecasts(d,5,{'baseline':sim},BaselineConfig(),None,None,tmp_path/'forecasts')
    _,r=m.review_forecast(path,[],tmp_path/'reviews')
    assert r['format']=='saved_scenarios' and r['variants']['baseline']['n']==0
    with (path/'scenarios.npz').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='checksum'):m.review_forecast(path,[],tmp_path/'reviews')


def test_legacy_preserves_revisions_order_and_complete_dgw(tmp_path):
    m=module();p=tmp_path/'comparison.json';a=legacy()
    for v in ('baseline','odds_variant'):
        a[v]['player_explanations']['1']['fixtures'].append(dict(fixture_id=12))
    p.write_text(json.dumps(a));first=row(state='final')
    second=row('b',state='final',fixture_id=12,observation_id='2026-2027:b:1:12')
    second['official_history']['fixture']=12
    _,pending=m.review_forecast(p,[first],tmp_path/'reviews')
    assert pending['variants']['baseline']['n']==0
    out,r=m.review_forecast(p,[second,first],tmp_path/'reviews')
    assert r['variants']['baseline']['rows'][0]['actual']==12
    _,again=m.review_forecast(p,[first,second],tmp_path/'reviews')
    assert again['variants']==r['variants']
    revision=copy.deepcopy(first);revision.update(source_snapshot_id='c',observation_id='2026-2027:c:1:11',
        retrieved_at='2026-09-20T12:00:00Z',available_at='2026-09-20T12:00:00Z',total_points=8)
    revision['official_history']['total_points']=8
    original=(out/'report.json').read_bytes()
    _,later=m.review_forecast(p,[first,second,revision],tmp_path/'reviews')
    assert later['variants']['baseline']['rows'][0]['actual']==14
    assert original==(out/'report.json').read_bytes()


def test_discovery_excludes_synthetic_and_app_saves_pending_review(tmp_path):
    m=module();root=tmp_path/'artifacts/defensive_odds/run';root.mkdir(parents=True)
    (root/'comparison.json').write_text(json.dumps(legacy()))
    fake=tmp_path/'artifacts/defensive_odds/fake';fake.mkdir()
    (fake/'comparison.json').write_text(json.dumps({**legacy(),'kind':'synthetic_offline_example_NOT_CURRENT_FORECAST'}))
    assert len(m.reviewable_forecasts(tmp_path))==1
    from streamlit.testing.v1 import AppTest
    from fpl_model.ui import forecast_review as ui
    assert callable(ui.show_forecast_review)
    script='from fpl_model.ui.forecast_review import show_forecast_review\n'+f'show_forecast_review({str(tmp_path)!r},dict(histories=[],snapshot_id="labels"))'
    app=AppTest.from_string(script).run();assert not app.exception
    next(b for b in app.button if b.label=='Efterkontrollér gemt prognose').click().run()
    assert not app.exception
    assert any('0 spillere' in x.value for x in app.info)
    assert list((tmp_path/'artifacts/forecast_reviews').glob('*/report.json'))
    # Saved review survives a new UI session, not only widget session_state.
    app=AppTest.from_string(script).run();assert not app.exception
    assert any('0 spillere' in x.value for x in app.info)


def test_verified_legacy_inputs_deadline_and_raw_tampering(tmp_path):
    m=module()
    from datetime import datetime,timezone
    from fpl_model.io import SnapshotWriter
    from fpl_model.prediction_evaluation import _sha
    time=datetime(2026,9,10,11,tzinfo=timezone.utc)
    w=SnapshotWriter(tmp_path/'raw',clock=lambda:time)
    body=dict(events=[dict(id=4,deadline_time=legacy()['deadline_at'])])
    for file,payload in [('bootstrap_static.json',body),('fixtures.json',[])]:
        w.write_raw('fpl_api/'+file,json.dumps(payload).encode(),source='fpl_api',
                    request_started_at=time,retrieved_at=time,required=True,http_status=200)
    raw=w.finalize();ref=dict(snapshot_path=str(raw),manifest_sha256=_sha(raw/'manifest.json'))
    a=legacy();a.update(input_sources=dict(history=ref,official_context=ref),coverage=dict(source=ref))
    p=tmp_path/'comparison.json';p.write_text(json.dumps(a))
    _,r=m.review_forecast(p,[],tmp_path/'reviews')
    assert r['provenance_status']=='legacy_declared_pre_deadline'
    assert m.read_official_context(raw)['source']['available_at']=='2026-09-10T11:00:00+00:00'
    a['deadline_at']='2026-09-11T11:00:00Z';p.write_text(json.dumps(a))
    with pytest.raises(ValueError,match='Deadline'):m.review_forecast(p,[],tmp_path/'reviews')
    a['deadline_at']=legacy()['deadline_at']
    for v in ('baseline','odds_variant'):a[v]['as_of_at']='2026-09-10T10:00:00Z'
    a['forecast_origin_at']='2026-09-10T10:00:00Z';p.write_text(json.dumps(a))
    with pytest.raises(ValueError,match='after its origin'):m.review_forecast(p,[],tmp_path/'reviews')
    (raw/'raw/fpl_api/fixtures.json').write_bytes(b'[{}]')
    from fpl_model.io import SnapshotIntegrityError
    with pytest.raises(SnapshotIntegrityError):m.read_official_context(raw)


def test_ui_reuses_catalog_until_report_files_change(tmp_path,monkeypatch):
    from fpl_model.ui import forecast_review as ui
    from streamlit.testing.v1 import AppTest
    root=tmp_path/'artifacts/defensive_odds/run';root.mkdir(parents=True)
    p=root/'comparison.json';p.write_text(json.dumps(legacy()))
    script='from fpl_model.ui.forecast_review import show_forecast_review\n'+f'show_forecast_review({str(tmp_path)!r},dict(histories=[]))'
    app=AppTest.from_string(script).run();assert not app.exception
    original=ui.reviewable_forecasts
    def forbidden(*args):raise ValueError('Unchanged catalog was unnecessarily reparsed')
    monkeypatch.setattr(ui,'reviewable_forecasts',forbidden)
    app.run();assert not app.exception
    monkeypatch.setattr(ui,'reviewable_forecasts',original)
    new=tmp_path/'artifacts/defensive_odds/second';new.mkdir()
    (new/'comparison.json').write_text(json.dumps(legacy()))
    app.run();assert not app.exception
    assert len(next(s for s in app.selectbox if s.label=='Prognose til efterkontrol').options)==2

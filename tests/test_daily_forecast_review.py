"""Daily transfer reports are outcomes to score, never forecasts to rerun."""
import json
import hashlib
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from test_observation_selection import row as official_row


def daily_report():
    player = dict(player_id=1, name='Example', position=2, fixture_ids=[11],
                  xp=5., expected_minutes=80., p_no_play=.2, p10=1., p90=9.)
    week = dict(event=4, mean=5., gain=0., hits=0)
    hold = dict(plan_id='hold', count=0, squad=[1], per_gw=[week],
                lineups={'4': dict(starters=[1], bench=[], captain=1, vice_captain=1)})
    return dict(version='transfer_sequences_chips_v3', scope='transfer_sequences',
                created_at='2026-09-10T12:01:00Z',
                forecast=dict(cache_key='a'*64, model_version='component_baseline_v1',
                              forecast_origin_at='2026-09-10T12:00:00Z',
                              source_available_at='2026-09-10T11:00:00Z',
                              deadlines={'4':'2026-09-11T10:00:00Z'}, draws=3000, seed=42,
                              config={'frequency_prior_games':1.}, snapshot_id='sample',
                              manifest_sha256=None, input_sources=None),
                players_by_event={'4':[player]}, packages=[hold],
                recommendation=dict(plan_id='hold'))


def save_daily(root, report=None):
    path = root/'artifacts/transfers/run/report.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report or daily_report()))
    return path


def test_daily_catalogue_and_app_show_saved_report_without_reforecast(tmp_path, monkeypatch):
    from fpl_model.forecast_review import reviewable_forecasts
    from fpl_model.ui import forecast_review as ui
    path = save_daily(tmp_path)
    choices = reviewable_forecasts(tmp_path)
    assert len(choices) == 1
    assert choices[0]['path'] == path and choices[0]['format'] == 'daily_transfer'
    import fpl_model.simulation as simulation
    monkeypatch.setattr(simulation, 'simulate', lambda *a, **k: pytest.fail('No forecast regeneration'))
    script = 'from fpl_model.ui.forecast_review import show_forecast_review\n' + \
             f'show_forecast_review({str(tmp_path)!r},dict(histories=[],season="2026-2027"))'
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert any('dagligt transferforslag' in c.value.lower() for c in app.caption)
    next(b for b in app.button if b.label == 'Efterkontrollér gemt prognose').click().run()
    assert not app.exception
    saved = list((tmp_path/'artifacts/forecast_reviews').glob('*/report.json'))
    assert len(saved) == 1 and json.loads(saved[0].read_text())['format'] == 'daily_transfer'


def test_daily_review_scores_final_only_and_never_invents_crps(tmp_path):
    from fpl_model.forecast_review import review_forecast
    path = save_daily(tmp_path)
    unchanged = path.read_bytes()
    _, pending = review_forecast(path, [], tmp_path/'reviews')
    assert pending['variants']['model']['n'] == 0
    assert pending['events']['4']['pending'][0]['reason'] == 'no_final_observation'
    _, result = review_forecast(path, [official_row(state='final')], tmp_path/'reviews')
    event = result['events']['4']
    assert event['model_all']['n'] == 1
    assert event['model_all']['points']['mae'] == 1
    assert event['model_all']['points']['crps'] is None
    assert event['model_all']['minutes']['bias'] == -10
    assert result['variants']['model']['n'] == result['variants']['reference']['n'] == 0
    assert event['reference_missing'][0]['reason'] == 'no_verified_prior_reference'
    assert path.read_bytes() == unchanged


def test_future_outcome_does_not_enter_input_or_change_saved_forecast(tmp_path):
    from fpl_model.forecast_review import review_forecast
    path = save_daily(tmp_path)
    later = official_row(state='final')
    assert later['available_at'] > daily_report()['forecast']['forecast_origin_at']
    _, result = review_forecast(path, [later], tmp_path/'reviews')
    assert result['events']['4']['model_all']['rows'][0]['target_observation_ids'] == [later['observation_id']]
    from fpl_model.label_contracts import utc
    assert utc(result['forecast_origin_at']) == utc(daily_report()['forecast']['forecast_origin_at'])
    assert result['provenance_status'] == 'unverified_provenance'


def test_real_report_catalogue_can_open_existing_local_daily_report():
    from fpl_model.config import ROOT
    from fpl_model.forecast_review import reviewable_forecasts
    if not list((ROOT/'artifacts/transfers').glob('*/report.json')):
        pytest.skip('No local generated reports in this checkout')
    choices = reviewable_forecasts(ROOT)
    assert any(c['format'] == 'daily_transfer' for c in choices)


def save_cache(root, report, points):
    key=report['forecast']['cache_key']
    path=root/'artifacts/transfer_forecasts'/key
    path.mkdir(parents=True)
    np.savez_compressed(path/'scenarios.npz',points_4=np.asarray(points),
                        played_4=np.asarray(points)>0)
    bundle=dict(cache_key=key,events=[4],metadata=report['forecast'],
                players=[dict(id=1)],rows={'4':report['players_by_event']['4']},
                coverage={'4':None},explanations={'4':{'1':dict(
                    history_coverage='complete_observed_window',
                    captured_history=dict(matches=2,mean_minutes=90,played_frequency=1.,events=[1,2]))}},
                scenarios_sha256=hashlib.sha256((path/'scenarios.npz').read_bytes()).hexdigest())
    (path/'bundle.json').write_text(json.dumps(bundle))
    return path


def test_original_scenarios_supply_crps_but_mismatched_cache_is_rejected(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();path=save_daily(tmp_path,report)
    cache=save_cache(tmp_path,report,[[2],[6],[10]])
    _, result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews')
    assert result['cache_status']=='verified_saved_scenarios'
    assert result['events']['4']['model_all']['points']['crps'] is not None
    assert result['events']['4']['model_all']['rows'][0]['predicted']==5.
    original=json.loads((cache/'bundle.json').read_text())
    original['metadata']['seed']=99
    (cache/'bundle.json').write_text(json.dumps(original))
    with pytest.raises(ValueError,match='cache identity'):
        review_forecast(path,[official_row(state='final')],tmp_path/'reviews')


def test_reference_uses_only_prior_final_available_complete_history():
    from fpl_model.daily_forecast_review import prior_reference
    old=official_row('old','2026-09-08T09:00:00Z','final',event=3,total_points=4,minutes=90)
    future=official_row('future','2026-09-12T09:00:00Z','final',event=3,total_points=30,minutes=0)
    current=official_row('current','2026-09-09T10:00:00Z','final',event=4,total_points=20)
    provisional=official_row('provisional','2026-09-08T10:00:00Z','provisional',event=2,total_points=10)
    for r in (old,future,current,provisional):r['official_history']['total_points']=r['total_points']
    for r in (old,future,provisional):
        r['kickoff_time']='2026-09-05T14:00:00Z'
        r['official_history']['kickoff_time']=r['kickoff_time']
    reference=prior_reference(1,4,'2026-09-10T12:00:00Z',
                              [old,future,current,provisional], 'complete_observed_window')
    assert reference==dict(points=4.,minutes=90.,p_no_play=0.,n=1)
    assert prior_reference(1,4,'2026-09-10T12:00:00Z',[old],
                           'incomplete_history_denominator') is None
    assert prior_reference(1,4,'2026-09-07T12:00:00Z',[old],
                           'complete_observed_window') is None


def test_fixed_team_outcome_includes_autosubs_captain_hits_and_requires_all_labels():
    from fpl_model.daily_forecast_review import score_plan_outcome
    from fpl_model.optimizer.lineup import optimize_lineup
    from fpl_model.optimizer.squad import evaluate_squad
    from test_lineup_optimization import fixture
    rows,points,active=fixture()
    team=optimize_lineup(list(range(15)),rows,points,active)
    actual={r['player_id']:dict(points=int(points[0,i]),minutes=90 if active[0,i] else 0)
            for i,r in enumerate(rows)}
    plan=dict(plan_id='suggested',steps=[dict(event=4,squad=list(range(15)),hits=4)],
              lineups={'4':team},per_gw=[dict(event=4)])
    expected=float(evaluate_squad(team,rows,np.array([[actual[i]['points'] for i in range(15)]]),
                     np.array([[actual[i]['minutes']>0 for i in range(15)]])).get('points')[0]-4)
    result=score_plan_outcome(plan,4,rows,actual)
    assert result['status']=='scored' and result['net_points']==expected
    del actual[14]
    pending=score_plan_outcome(plan,4,rows,actual)
    assert pending['status']=='pending' and pending['missing_player_ids']==[14]


def history_snapshot(root):
    from datetime import datetime, timezone
    from fpl_model.io import SnapshotWriter
    from fpl_model.prediction_evaluation import _sha
    from test_player_fixture_labels import BASE
    time=datetime(2026,9,9,11,tzinfo=timezone.utc)
    writer=SnapshotWriter(root/'data/raw',clock=lambda:time)
    bootstrap=dict(elements=[dict(id=1,team=1,element_type=2)],
                   teams=[dict(id=1),dict(id=2)],
                   events=[dict(id=3,finished=True,data_checked=True),
                           dict(id=4,deadline_time='2026-09-11T10:00:00Z')])
    fixture=dict(id=10,event=3,team_h=1,team_a=2,
                 kickoff_time='2026-09-05T14:00:00Z',started=True,finished=True)
    historical=dict(BASE,fixture=10,round=3,kickoff_time=fixture['kickoff_time'],
                    total_points=4)
    for name,payload,context in [
        ('bootstrap_static.json',bootstrap,{}),('fixtures.json',[fixture],{}),
        ('element_summary/1.json',dict(history=[historical]),{'element_id':'1'})]:
        writer.write_raw('fpl_api/'+name,json.dumps(payload).encode(),source='fpl_api',
                         request_started_at=time,retrieved_at=time,required=True,
                         http_status=200,request_context=context)
    path=writer.finalize()
    return dict(snapshot_path=str(path),snapshot_id=path.name.split('_')[-1],
                manifest_sha256=_sha(path/'manifest.json'),available_at=time.isoformat())


def test_same_row_reference_comes_from_original_verified_pre_origin_history(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report()
    report['forecast']['input_sources']=dict(history=history_snapshot(tmp_path))
    path=save_daily(tmp_path,report)
    save_cache(tmp_path,report,[[2],[6],[10]])
    _,result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews')
    model,reference=result['variants']['model'],result['variants']['reference']
    assert model['n']==reference['n']==1
    assert model['rows'][0]['player_id']==reference['rows'][0]['player_id']==1
    assert model['points']['mae']==1 and reference['points']['mae']==2
    assert model['points']['crps'] is not None and reference['points']['crps'] is None
    assert model['rows'][0]['p10']==1. and model['rows'][0]['p90']==9.
    assert reference['rows'][0]['predicted']==4.
    assert reference['rows'][0]['p10'] is None and reference['rows'][0]['p90'] is None
    assert model['interval_80']==dict(n=1,coverage=1.)
    assert reference['interval_80']==dict(n=0,coverage=None)
    assert result['version']=='forecast_review_v3'
    assert result['provenance_status']=='partially_verified_pre_deadline'
    assert result['events']['4']['reference_missing']==[]
    raw=Path(report['forecast']['input_sources']['history']['snapshot_path'])
    (raw/'raw/fpl_api/element_summary/1.json').write_bytes(b'changed')
    with pytest.raises((ValueError,Exception),match='checksum|SHA|integrity|hash'):
        review_forecast(path,[official_row(state='final')],tmp_path/'reviews')


def test_incomplete_gw_never_scores_team_or_player_even_if_label_row_is_final(tmp_path):
    from fpl_model.forecast_review import review_forecast
    path=save_daily(tmp_path)
    context=dict(events=[dict(id=4,finished=False,data_checked=False)],
                 fixtures=[dict(id=11,event=4,finished=False)])
    _,result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews',context=context)
    assert result['events']['4']['model_all']['n']==0
    assert result['events']['4']['pending'][0]['reason']=='awaiting_official_finality'


def test_daily_review_scores_fixed_suggestion_against_hold_only_with_complete_squad(tmp_path):
    from fpl_model.forecast_review import review_forecast
    from fpl_model.optimizer.lineup import optimize_lineup
    from test_lineup_optimization import fixture
    rows,points,active=fixture()
    lineup=optimize_lineup(list(range(15)),rows,points,active)
    rows=[dict(r,player_id=r['player_id']+1) for r in rows]
    lineup=dict(lineup,starters=[i+1 for i in lineup['starters']],
                bench=[i+1 for i in lineup['bench']],captain=lineup['captain']+1,
                vice_captain=lineup['vice_captain']+1)
    report=daily_report()
    report['players_by_event']['4']=[dict(r,fixture_ids=[11],name=str(r['player_id']),
        expected_minutes=80.,p_no_play=.1,p10=0.,p90=10.) for r in rows]
    hold=dict(plan_id='hold',steps=[dict(event=4,squad=list(range(1,16)),hits=0)],
              lineups={'4':lineup},per_gw=[dict(event=4,hits=0,gain=0.)])
    proposed=dict(plan_id='first_1',steps=[dict(event=4,squad=list(range(1,16)),hits=4)],
                  lineups={'4':lineup},per_gw=[dict(event=4,hits=4,gain=-4.)])
    report['packages']=[hold,proposed]
    report['recommendation']['plan_id']='first_1'
    path=save_daily(tmp_path,report)
    outcomes=[]
    for i in range(1,16):
        r=official_row(str(i),'2026-09-21T12:00:00Z','final',player_id=i,
                       observation_id=f'2026-2027:{i}:{i}:11',total_points=6,minutes=90)
        r['official_history'].update(element=i,total_points=6,minutes=90)
        outcomes.append(r)
    context=dict(events=[dict(id=4,finished=True,data_checked=True)],
                 fixtures=[dict(id=11,event=4,finished=True)])
    _,complete=review_forecast(path,outcomes,tmp_path/'reviews',context=context)
    comparison=complete['team_comparison']['per_gw'][0]
    assert comparison['status']=='scored' and comparison['actual_gain']==-4.
    assert comparison['hold_net_points']-comparison['suggested_net_points']==4.
    _,partial=review_forecast(path,outcomes[:-1],tmp_path/'reviews',context=context)
    assert partial['team_comparison']['per_gw'][0]['status']=='pending'
    assert partial['team_comparison']['per_gw'][0]['missing_player_ids']==[15]


def test_daily_review_ui_shows_comparable_and_pending_results_without_false_claims(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report()
    report['forecast']['input_sources']=dict(history=history_snapshot(tmp_path))
    path=save_daily(tmp_path,report)
    save_cache(tmp_path,report,[[2],[6],[10]])
    output,result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews')
    script='import json\nfrom pathlib import Path\nfrom fpl_model.ui.forecast_review import render_daily_review\n' + \
           f'render_daily_review(json.loads(Path({str(output/"report.json")!r}).read_text()))'
    app=AppTest.from_string(script).run()
    assert not app.exception
    assert any('GW4' in m.value for m in app.markdown)
    assert any('samme' in c.value.lower() and 'rækker' in c.value.lower() for c in app.caption)
    assert any('hypotetisk' in c.value.lower() for c in app.caption)
    assert any('afventer' in c.value.lower() or 'mangler' in c.value.lower() for c in app.caption)


def test_default_daily_reference_is_last_saved_before_deadline_not_best_after_result():
    from datetime import datetime,timezone
    from fpl_model.ui.forecast_review import preferred_review_index
    context=dict(events=[dict(id=4,finished=True,data_checked=True)],
                 fixtures=[dict(id=11,event=4,finished=True)])
    choices=[dict(event=4,format='daily_transfer',origin=origin,
                  deadline_at='2026-09-11T10:00:00Z',created_at=created)
             for origin,created in [('2026-09-10T12:00:00Z','2026-09-10T12:01:00Z'),
                                    ('2026-09-10T13:00:00Z','2026-09-12T12:01:00Z')]]
    assert preferred_review_index(choices,context,datetime(2026,9,21,tzinfo=timezone.utc))==0


def test_single_snapshot_reference_is_verified_without_rewriting_old_report(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();ref=history_snapshot(tmp_path)
    report['forecast'].update({k:ref[k] for k in ('snapshot_path','snapshot_id','manifest_sha256')})
    report['forecast']['source_available_at']=ref['available_at']
    path=save_daily(tmp_path,report);original=path.read_bytes()
    save_cache(tmp_path,report,[[2],[6],[10]])
    _,result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews')
    assert result['variants']['reference']['n']==1
    assert result['variants']['reference']['rows'][0]['predicted']==4.
    assert result['verified_input_sources']
    assert path.read_bytes()==original


def test_daily_cli_handles_daily_review_result(tmp_path,monkeypatch,capsys):
    from scripts import evaluate_saved_forecast as cli
    path=save_daily(tmp_path)
    monkeypatch.setattr(cli,'load_data',lambda p:dict(histories=[],season='2026-2027'))
    monkeypatch.setattr(cli,'read_official_context',lambda p:dict(
        events=[dict(id=4,finished=False,data_checked=False)],fixtures=[]))
    assert cli.main(['--forecast',str(path),'--outcome-snapshot','unused',
                     '--output-root',str(tmp_path/'reviews')])==0
    assert 'GW4' in capsys.readouterr().out


def test_daily_rejects_outcomes_from_another_season(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();report['profile']={'season':'2025-2026'}
    with pytest.raises(ValueError,match='season'):
        review_forecast(save_daily(tmp_path,report),[],tmp_path/'reviews',season='2026-2027')


def test_report_created_before_forecast_origin_is_not_prospective(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();report['created_at']='2026-09-10T11:59:00Z'
    _,result=review_forecast(save_daily(tmp_path,report),[],tmp_path/'reviews')
    assert result['provenance_status']=='not_pre_deadline'


def test_claimed_source_time_cannot_hide_later_raw_capture(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();ref=history_snapshot(tmp_path)
    ref['available_at']='2026-09-08T00:00:00Z'
    report['forecast']['input_sources']={'history':ref}
    with pytest.raises(ValueError,match='availability precedes'):
        review_forecast(save_daily(tmp_path,report),[],tmp_path/'reviews')


def test_daily_ui_leads_with_team_result_and_shows_model_without_reference(tmp_path):
    from fpl_model.forecast_review import review_forecast
    path=save_daily(tmp_path)
    out,result=review_forecast(path,[official_row(state='final')],tmp_path/'reviews')
    result['team_comparison'].update(status='scored',horizon_actual_gain=3.,per_gw=[
        dict(event=4,status='scored',hold_net_points=40.,suggested_net_points=43.,
             actual_gain=3.,predicted_gain=1.)])
    (out/'report.json').write_text(json.dumps(result))
    script='import json\nfrom pathlib import Path\nfrom fpl_model.ui.forecast_review import render_daily_review\n'+\
        f'render_daily_review(json.loads(Path({str(out/"report.json")!r}).read_text()))'
    app=AppTest.from_string(script).run()
    assert not app.exception
    assert any(m.label=='Forslagets gevinst' and m.value=='+3.0 point' for m in app.metric)
    assert any('Tekniske referencer'==e.label for e in app.expander)
    assert any('uden sammenlignelig reference' in c.value for c in app.caption)
    assert any('model' in str(d.value) and '1' in str(d.value) for d in app.dataframe)


def test_partial_horizon_never_shows_completed_gain_metric(tmp_path):
    from fpl_model.forecast_review import review_forecast
    out,_=review_forecast(save_daily(tmp_path),[],tmp_path/'reviews')
    script='import json\nfrom pathlib import Path\nfrom fpl_model.ui.forecast_review import render_daily_review\n'+\
        f'render_daily_review(json.loads(Path({str(out/"report.json")!r}).read_text()))'
    app=AppTest.from_string(script).run()
    assert not app.exception
    assert not any(m.label=='Forslagets gevinst' for m in app.metric)


def test_review_cache_requires_same_official_context():
    from fpl_model.ui.forecast_review import review_matches_sources
    result=dict(format='daily_transfer',version='forecast_review_v3',forecast_sha256='f',outcome_source={'snapshot_id':'labels'},
                outcome_context_source={'snapshot_id':'old_context'})
    assert review_matches_sources(result,'f',{'snapshot_id':'labels'},dict(source={'snapshot_id':'old_context'}))
    assert not review_matches_sources(result,'f',{'snapshot_id':'labels'},dict(source={'snapshot_id':'new_context'}))
    result['version']='forecast_review_v2'
    assert not review_matches_sources(result,'f',{'snapshot_id':'labels'},dict(source={'snapshot_id':'old_context'}))


def test_daily_report_predictions_must_match_original_cache(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();path=save_daily(tmp_path,report)
    save_cache(tmp_path,report,[[2],[6],[10]])
    report['players_by_event']['4'][0]['xp']=999.
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='player summaries'):
        review_forecast(path,[official_row(state='final')],tmp_path/'reviews')


def test_double_gameweek_reference_is_on_the_same_scale_as_target(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();report['forecast']['input_sources']={'history':history_snapshot(tmp_path)}
    report['players_by_event']['4'][0]['fixture_ids']=[11,12]
    path=save_daily(tmp_path,report);save_cache(tmp_path,report,[[2],[6],[10]])
    outcomes=[official_row(state='final',fixture_id=f,observation_id=f'2026-2027:a:1:{f}',total_points=4)
              for f in (11,12)]
    for o in outcomes:o['official_history'].update(fixture=o['fixture_id'],total_points=4)
    _,result=review_forecast(path,outcomes,tmp_path/'reviews')
    reference=result['variants']['reference']['rows'][0]
    assert reference['predicted']==8 and reference['predicted_minutes']==180
    from fpl_model.daily_forecast_review import prior_reference
    history=[official_row(state='final',event=3,fixture_id=f,minutes=m) for f,m in ((9,90),(10,0))]
    for o in history:o.update(available_at='2026-09-08T10:00:00Z',kickoff_time='2026-09-05T14:00:00Z')
    assert prior_reference(1,4,report['forecast']['forecast_origin_at'],history,
                           'complete_observed_window',fixture_count=2)['p_no_play']==.25


def test_newly_assigned_fixture_is_not_silently_missing_from_final_outcome(tmp_path):
    from fpl_model.forecast_review import review_forecast
    report=daily_report();report['players_by_event']['4'][0]['team_id']=1
    context=dict(events=[dict(id=4,finished=True,data_checked=True)],
                 fixtures=[dict(id=f,event=4,finished=True,team_h=1,team_a=2) for f in (11,12)])
    _,result=review_forecast(save_daily(tmp_path,report),[official_row(state='final')],tmp_path/'reviews',context=context)
    assert result['all_final_count']==0
    assert result['pending'][0]['reason']=='fixture_universe_changed'


def test_card_only_captain_blocks_autosub_and_vice_switch(tmp_path):
    from fpl_model.forecast_review import review_forecast
    from fpl_model.optimizer.lineup import optimize_lineup
    from test_lineup_optimization import fixture
    rows,points,active=fixture();lineup=optimize_lineup(list(range(15)),rows,points,active)
    rows=[dict(r,player_id=r['player_id']+1,team_id=1,fixture_ids=[11],name=str(r['player_id']),
               expected_minutes=80.,p_no_play=.1,p10=0.,p90=10.) for r in rows]
    lineup=dict(lineup,starters=[i+1 for i in lineup['starters']],bench=[i+1 for i in lineup['bench']])
    captain=lineup['starters'][0]
    lineup.update(captain=captain,vice_captain=lineup['starters'][1])
    report=daily_report();report['players_by_event']['4']=rows
    report['packages']=[dict(plan_id='hold',count=0,lineups={'4':lineup},per_gw=[dict(event=4,hits=0,gain=0)])]
    outcomes=[]
    for i in range(1,16):
        o=official_row(state='final',player_id=i,observation_id=f'2026-2027:a:{i}:11',
                       minutes=0 if i==captain else 90,total_points=-1 if i==captain else 2,
                       yellow_cards=int(i==captain),red_cards=0)
        o['official_history'].update(element=i,minutes=o['minutes'],total_points=o['total_points'],
                                     yellow_cards=int(i==captain),red_cards=0)
        outcomes.append(o)
    context=dict(events=[dict(id=4,finished=True,data_checked=True)],
                 fixtures=[dict(id=11,event=4,finished=True,team_h=1,team_a=2)])
    _,result=review_forecast(save_daily(tmp_path,report),outcomes,tmp_path/'reviews',context=context)
    assert result['team_comparison']['per_gw'][0]['hold_net_points']==18.

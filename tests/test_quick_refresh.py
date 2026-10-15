"""Fast official-context refresh keeps older histories honest and immutable."""
import json
from datetime import datetime, timezone

import pytest

from fpl_model.io import SnapshotWriter, verify_snapshot
from fpl_model.quick_refresh import capture_official_context, latest_history_snapshot, select_history_snapshot, load_current_inputs


def _snapshot(root, when, *, history, player_price=50, finished=False, started=False, player_ids=(1,)):
    clock=lambda: datetime.fromisoformat(when.replace('Z','+00:00'))
    writer=SnapshotWriter(root,clock=clock)
    metadata=dict(purpose='official_full_player_history' if history else 'official_context_refresh',
                  season='2026-2027',overall='complete')
    if history:metadata.update(player_count=str(len(player_ids)),successful_players=str(len(player_ids)))
    writer.set_run_metadata(metadata)
    bootstrap=dict(
        elements=[dict(id=i,code=100+i,web_name=f'P{i}',team=1,element_type=3,now_cost=player_price,
                       status='d' if not history else 'a',chance_of_playing_next_round=75 if not history else None)
                  for i in player_ids],
        teams=[dict(id=1,name='One'),dict(id=2,name='Two')],
        events=[dict(id=1,deadline_time='2026-10-01T10:00:00Z',finished=True,data_checked=True),
                dict(id=2,deadline_time='2026-10-20T10:00:00Z',finished=finished,data_checked=finished),
                dict(id=3,deadline_time='2026-11-01T10:00:00Z',finished=False,data_checked=False)],
        element_types=[dict(id=i,squad_select=n) for i,n in ((1,2),(2,5),(3,5),(4,3))],
        game_settings=dict(squad_squadsize=15,squad_squadplay=11,squad_team_limit=3))
    fixtures=[dict(id=11,event=1,team_h=1,team_a=2,kickoff_time='2026-10-01T15:00:00Z',
                   started=True,finished=True,team_h_score=1,team_a_score=0),
              dict(id=12,event=2,team_h=1,team_a=2,kickoff_time='2026-10-15T15:00:00Z',
                   started=started or finished,finished=finished,team_h_score=2 if finished else None,team_a_score=1 if finished else None)]
    for name,payload in [('bootstrap_static.json',bootstrap),('fixtures.json',fixtures)]:
        writer.write_raw('fpl_api/'+name,json.dumps(payload).encode(),source='fpl_api',required=True,
                         request_started_at=clock(),retrieved_at=clock(),http_status=200,
                         request_url='https://fantasy.premierleague.com/api/'+name)
    if history:
        for i in player_ids:
            payload=dict(history=[dict(element=i,fixture=11,round=1,opponent_team=2,was_home=True,
                          kickoff_time='2026-10-01T15:00:00Z',minutes=90,starts=1,total_points=6)])
            writer.write_raw(f'fpl_api/element_summary/{i}.json',json.dumps(payload).encode(),
                             source='fpl_api',required=False,request_started_at=clock(),retrieved_at=clock(),
                             http_status=200,request_url=f'https://fantasy.premierleague.com/api/element-summary/{i}/',
                             request_context={'element_id':str(i)})
    return writer.finalize()


def test_fast_refresh_fetches_only_context_and_never_overwrites(tmp_path):
    from test_player_labels_workflow import Session
    client=Session()
    path=capture_official_context(tmp_path/'raw',season='2026-2027',session=client)
    manifest=verify_snapshot(path)
    assert len(client.calls)==2
    assert manifest['run_metadata']['purpose']=='official_context_refresh'
    assert len(manifest['files'])==2
    assert all('element_summary' not in e['relative_path'] for e in manifest['files'])
    again=capture_official_context(tmp_path/'raw',season='2026-2027',session=Session())
    assert again!=path and verify_snapshot(path)==manifest


def test_composite_uses_new_status_and_prices_but_old_history_time(tmp_path):
    history=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'raw','2026-10-14T10:00:00Z',history=False,player_price=62,player_ids=(1,2))
    data=load_current_inputs(context,history,season='2026-2027')
    assert data['players'][0]['now_cost']==62 and data['players'][0]['status']=='d'
    assert data['histories'][0]['minutes']==90
    assert data['histories'][0]['source_snapshot_id']==history.name.split('_')[-1]
    assert data['input_sources']['history']['available_at']=='2026-10-10T10:00:00+00:00'
    assert data['input_sources']['official_context']['available_at']=='2026-10-14T10:00:00+00:00'
    assert data['coverage']['new_player_ids_without_history']==[2]
    assert data['coverage']['history_refresh_required'] is True
    assert data['as_of_at']=='2026-10-14T10:00:00+00:00'


def test_same_player_pool_without_new_finished_games_is_fast_refresh_ready(tmp_path):
    history=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'raw','2026-10-14T10:00:00Z',history=False,player_price=62)
    data=load_current_inputs(context,history)
    assert data['coverage']['history_refresh_required'] is False
    assert data['coverage']['newly_finished_fixture_ids']==[]


def test_newly_started_game_is_not_silently_treated_as_current_history(tmp_path):
    history=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'raw','2026-10-15T16:00:00Z',history=False,started=True)
    data=load_current_inputs(context,history)
    assert data['coverage']['newly_started_fixture_ids']==[12]
    assert data['coverage']['history_refresh_required'] is True


def test_newly_finished_match_requires_full_history_and_future_history_rejected(tmp_path):
    history=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'raw','2026-10-16T10:00:00Z',history=False,finished=True)
    data=load_current_inputs(context,history,season='2026-2027')
    assert data['coverage']['history_refresh_required'] is True
    assert data['coverage']['newly_finished_fixture_ids']==[12]
    late_history=_snapshot(tmp_path/'raw','2026-10-18T10:00:00Z',history=True)
    with pytest.raises(ValueError,match='after official context'):
        load_current_inputs(context,late_history,season='2026-2027')


def test_history_selection_uses_latest_complete_capture_not_future_or_context(tmp_path):
    early=_snapshot(tmp_path/'raw','2026-10-08T10:00:00Z',history=True)
    latest=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    context=_snapshot(tmp_path/'raw','2026-10-14T10:00:00Z',history=False)
    future=_snapshot(tmp_path/'raw','2026-10-18T10:00:00Z',history=True)
    assert latest_history_snapshot([early,latest,context,future],context,season='2026-2027')==latest
    assert latest_history_snapshot([latest,future],early,season='2026-2027') is None
    assert latest_history_snapshot([early,latest,future],early,season='2026-2027')==early
    assert select_history_snapshot([early,latest,context,future],context,season='2026-2027')==latest
    assert select_history_snapshot([early,latest,context,future],early,season='2026-2027')==early


def test_smart_refresh_skips_player_requests_when_history_is_current(tmp_path,monkeypatch):
    from fpl_model import quick_refresh
    prior=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    fresh=_snapshot(tmp_path/'raw','2026-10-14T10:00:00Z',history=False,player_price=62)
    monkeypatch.setattr(quick_refresh,'capture_official_context',lambda *a,**k:fresh)
    def forbidden(*a,**k):raise AssertionError('No player-history requests needed')
    monkeypatch.setattr('fpl_model.full_player_capture.capture_all_players',forbidden)
    result=quick_refresh.refresh_official_data(tmp_path/'raw',season='2026-2027',known_paths=[prior])
    assert result['status']=='context_only' and result['selected_snapshot']==fresh
    assert result['history_snapshot']==prior and result['history_required'] is False
    assert verify_snapshot(prior)['run_metadata']['overall']=='complete'


def test_smart_refresh_fetches_history_after_changed_fixture_and_keeps_context(tmp_path,monkeypatch):
    from fpl_model import quick_refresh
    prior=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    fresh=_snapshot(tmp_path/'raw','2026-10-16T10:00:00Z',history=False,finished=True)
    complete=_snapshot(tmp_path/'raw','2026-10-16T11:00:00Z',history=True,finished=True)
    monkeypatch.setattr(quick_refresh,'capture_official_context',lambda *a,**k:fresh)
    calls=[];progress=[]
    def capture(root,**kwargs):
        calls.append(kwargs['season'])
        kwargs['progress'](dict(completed=1,total=1,status='success'))
        return complete
    monkeypatch.setattr('fpl_model.full_player_capture.capture_all_players',capture)
    result=quick_refresh.refresh_official_data(tmp_path/'raw',season='2026-2027',known_paths=[prior],progress=progress.append)
    assert calls==['2026-2027'] and result['status']=='history_complete'
    assert result['context_snapshot']==fresh and result['selected_snapshot']==complete
    assert result['changed_fixture_ids']==[12]
    assert [row['stage'] for row in progress]==['context','history','player','complete']


def test_smart_refresh_never_selects_partial_player_capture(tmp_path,monkeypatch):
    from fpl_model import quick_refresh
    prior=_snapshot(tmp_path/'raw','2026-10-10T10:00:00Z',history=True)
    fresh=_snapshot(tmp_path/'raw','2026-10-16T10:00:00Z',history=False,finished=True)
    clock=lambda:datetime.fromisoformat('2026-10-16T11:00:00+00:00')
    writer=SnapshotWriter(tmp_path/'raw',clock=clock)
    writer.set_run_metadata(dict(purpose='official_full_player_history',season='2026-2027',
                                 overall='partial',player_count='1',successful_players='0'))
    writer.write_raw('fpl_api/bootstrap_static.json',b'{}',source='fpl_api',required=True,
                     request_started_at=clock(),retrieved_at=clock(),http_status=200)
    partial=writer.finalize()
    monkeypatch.setattr(quick_refresh,'capture_official_context',lambda *a,**k:fresh)
    monkeypatch.setattr('fpl_model.full_player_capture.capture_all_players',lambda *a,**k:partial)
    result=quick_refresh.refresh_official_data(tmp_path/'raw',season='2026-2027',known_paths=[prior])
    assert result['status']=='history_partial' and result['selected_snapshot']==fresh
    assert result['history_snapshot']==prior and result['attempted_history_snapshot']==partial
    assert verify_snapshot(partial)['run_metadata']['overall']=='partial'

"""Real writer/adapters/normalizer; only HTTP and sleeping are replaced."""
import importlib
import importlib.util
import json

from test_player_labels_workflow import Response, Session
from fpl_model.io import verify_snapshot
from fpl_model.player_fixture_labels import normalize_snapshot


class PoolSession(Session):
    def get(self,url,**kwargs):
        if '/element-summary/' in url:
            self.calls.append(url)
            pid=int(url.rstrip('/').split('/')[-1])
            if pid==77: return Response({'history':[]})
            if pid==203: return Response({'error':'unavailable'},503)
            return Response({'history':[dict(element=pid,fixture=11,round=4,
                opponent_team=2,was_home=True,kickoff_time='2026-09-12T14:00:00Z',
                minutes=0,starts=0,total_points=0)]})
        response=super().get(url,**kwargs)
        if '/bootstrap-static/' in url:
            payload=json.loads(response.content)
            payload['elements']=[dict(id=i,team=1,element_type=1) for i in (1,77,203)]
            return Response(payload)
        return response


def test_full_capture_uses_bootstrap_ids_and_publishes_explicit_partial_coverage(tmp_path):
    assert importlib.util.find_spec('fpl_model.full_player_capture')
    capture=importlib.import_module('fpl_model.full_player_capture').capture_all_players
    session=PoolSession();progress=[]
    path=capture(tmp_path/'raw',season='2026-2027',session=session,sleep=lambda _:None,progress=progress.append)
    manifest=verify_snapshot(path)
    assert manifest['run_metadata']['overall']=='partial'
    assert manifest['run_metadata']['player_count']=='3'
    assert progress[-1]['completed']==3
    result=normalize_snapshot(path,season='2026-2027',element_ids=[1,77,203],allow_missing=True)
    q=result['quality']
    assert q['attempted_players']==3 and q['successful_responses']==2
    assert q['empty_history_players']==[77] and q['failed_players']==[203]
    assert q['accepted_rows']==1 and q['explicit_zero_minute_rows']==1
    assert result['labels'][0]['minutes']==0
    assert [p['history_status'] for p in q['players']]==['rows_observed','empty_observed_history','request_failed']
    assert len(session.calls)==7  # two context + one each success + three failed attempts


def test_missing_capture_remains_missing_not_empty(tmp_path):
    from test_player_fixture_labels import snapshot
    path=snapshot(tmp_path)
    result=normalize_snapshot(path,season='2026-2027',element_ids=[1,2],allow_missing=True)
    assert result['quality']['missing_response_players']==[2]
    assert result['quality']['empty_history_players']==[]

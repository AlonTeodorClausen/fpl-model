import copy
import importlib
import json
from pathlib import Path
import pytest
from test_fpl_api import response,session_for,NOW
from test_my_team import profile
from test_prototype import players


def mod():return importlib.import_module('fpl_model.team_import')


def payloads():
    pool=players()
    for p in pool:p['code']=10000+p['id']
    boot=dict(elements=pool,events=[dict(id=1,deadline_time='2026-08-01T10:00:00Z'),dict(id=5,deadline_time='2026-09-01T10:00:00Z')])
    entry=dict(id=3533723,name='Example Team',current_event=5)
    picks=dict(active_chip=None,entry_history=dict(event=5,bank=7),picks=[dict(element=p['player_id'],position=i+1,is_captain=i==0,is_vice_captain=i==1) for i,p in enumerate(profile()['players'])])
    return boot,entry,picks


def test_id_and_link_parsing_rejects_untrusted_urls():
    for text in ['3533723',' https://fantasy.premierleague.com/entry/3533723/event/6 ',
                 'https://fantasy.premierleague.com/en/entry/3533723/history','fantasy.premierleague.com/entry/3533723/']:
        assert mod().parse_team_id(text)==3533723
    for text in ['', '0','-1','abc','https://evil.com/entry/3533723','https://fantasy.premierleague.com.evil.org/entry/3533723',
                 'https://me@fantasy.premierleague.com/entry/3533723','https://fantasy.premierleague.com/my-team','1/2']:
        with pytest.raises(ValueError):mod().parse_team_id(text)


def test_public_capture_preserves_bytes_and_never_guesses_economy(tmp_path):
    boot,entry,picks=payloads();raw=[json.dumps(x,indent=2).encode()+b'\n' for x in (boot,entry,picks)]
    session=session_for(*(response(x) for x in raw))
    result=mod().capture_team('3533723',tmp_path/'raw',session=session,clock=lambda:NOW)
    assert result['entry_id']==3533723 and result['event']==5
    assert len(result['players'])==15 and result['bank_at_deadline']==7
    draft=mod().make_draft(result,dict(players=boot['elements'],events=boot['events'],season='2026-2027'))
    assert all(p['selling_price'] is None for p in draft['players'])
    assert draft['free_transfers'] is None and draft['transfers_made'] is None and draft['bank']==7
    root=Path(result['snapshot_path']);manifest=json.loads((root/'manifest.json').read_text())
    assert [ (root/f['relative_path']).read_bytes() for f in manifest['files'] ]==raw
    assert (root/'COMPLETE').is_file()
    assert all(call.kwargs['allow_redirects'] is False for call in session.get.call_args_list)
    assert all('my-team' not in call.args[0] for call in session.get.call_args_list)


def test_bad_payload_and_http_failure_preserve_old_profile(tmp_path):
    boot,entry,picks=payloads()
    for kind in ['404','html','duplicates','freehit','preseason']:
        e=copy.deepcopy(entry);p=copy.deepcopy(picks)
        if kind=='duplicates':p['picks'][1]['element']=p['picks'][0]['element']
        if kind=='freehit':p['active_chip']='freehit'
        if kind=='preseason':e['current_event']=None
        replies=[response(json.dumps(boot).encode()),response(json.dumps(e).encode()),response(json.dumps(p).encode())]
        if kind=='404':replies[1]=response(b'{"detail":"Not found"}',status=404)
        if kind=='html':replies[1]=response(b'<html>error</html>',content_type='text/html')
        with pytest.raises(ValueError):mod().capture_team('3533723',tmp_path/kind,session=session_for(*replies),clock=lambda:NOW)
        assert not list((tmp_path/kind).glob('*/COMPLETE'))
        assert list((tmp_path/kind/'.staging').glob('*/manifest.json'))


def test_mapping_requires_canonical_identity_and_explicit_local_money_reuse(tmp_path):
    boot,entry,picks=payloads();res=mod().capture_team('3533723',tmp_path,session=session_for(*(response(json.dumps(x).encode()) for x in (boot,entry,picks))),clock=lambda:NOW)
    data=dict(players=boot['elements'],events=boot['events'],season='2026-2027')
    saved=profile();before=copy.deepcopy(saved)
    d=mod().make_draft(res,data,previous=saved,keep_existing=True)
    assert d['players']==saved['players'] and d['bank']==saved['bank'] and saved==before
    wrong=copy.deepcopy(data);wrong['players'][0]['code']+=1
    with pytest.raises(ValueError,match='identitet'):mod().make_draft(res,wrong)
    with pytest.raises(ValueError):mod().make_draft(res,dict(data,season='2025-2026'))
    wrong_saved=copy.deepcopy(saved);wrong_saved['players'][0]['player_id']=999
    with pytest.raises(ValueError):mod().make_draft(res,data,previous=wrong_saved,keep_existing=True)


def test_missing_canonical_code_cannot_match_by_absence():
    imported=dict(season='2026-2027',players=[dict(id=1,team=1,element_type=1)])
    data=dict(season='2026-2027',players=[dict(id=1,team=1,element_type=1)])
    with pytest.raises(ValueError,match='identitet'):mod().make_draft(imported,data)

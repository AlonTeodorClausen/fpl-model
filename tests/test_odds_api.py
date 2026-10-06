"""Offline API translation, provenance, explicit acquisition and defensive scope."""
import copy
import importlib
import json
from datetime import datetime, timezone
import numpy as np
import pytest
import requests
from test_defensive_odds import coverage_data
from fpl_model.defensive_odds import build_coverage
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate


def api_context():
    d,_,source=coverage_data()
    source.update(source='the_odds_api')
    updated='2026-09-09T10:59:00Z'
    event=dict(id='api-event',sport_key='soccer_epl',commence_time='2026-09-10T14:00:00Z',
        home_team='Manchester United',away_team='Tottenham Hotspur',bookmakers=[
        dict(key='williamhill',title='William Hill',last_update=updated,markets=[
            dict(key='h2h',last_update=updated,outcomes=[dict(name='Manchester United',price=2.),dict(name='Draw',price=3.5),dict(name='Tottenham Hotspur',price=4.)]),
            dict(key='totals',last_update=updated,outcomes=[dict(name='Over',price=1.9,point=2.5),dict(name='Under',price=1.9,point=2.5)])])])
    return d,event,source


def cover(event=None,source=None):
    d,e,s=api_context()
    return build_coverage(d,[e if event is None else event],s if source is None else source,5,BaselineConfig(),d['as_of_at'])


def test_api_prices_use_existing_fit_and_preserve_separate_timestamps():
    from fpl_model.defensive_odds import fit_market,COLUMNS
    _,e,s=api_context();c=cover();f=c['fixtures'][0]
    assert c['usable']==1
    old=fit_market(dict(zip(COLUMNS,[2.,3.5,4.,1.9,1.9])))
    assert f['home_goals']==old['home_goals'] and f['away_goals']==old['away_goals']
    assert c['bookmaker']=='williamhill'
    assert f['market_provenance']['event_id']==e['id']
    assert f['market_provenance']['bookmaker_last_update']=='2026-09-09T10:59:00Z'
    assert c['source']['available_at']==s['available_at']
    assert f['columns']==['home','draw','away','over25','under25']


@pytest.mark.parametrize('change,reason',[
    ('other_book','missing_williamhill'),('duplicate_book','duplicate_williamhill'),
    ('no_draw','invalid_h2h_market'),('line35','missing_totals_2_5'),
    ('one_side','invalid_totals_2_5'),('mix_books','missing_totals_market'),
    ('duplicate_market','duplicate_h2h_market'),('invalid_price','invalid_decimal_price'),
    ('future_update','invalid_provider_update'),('naive_update','invalid_provider_update'),
    ('kickoff','no_exact_fixture_market'),('unknown_team','no_exact_fixture_market'),
])
def test_api_invalid_inputs_fall_back_without_book_or_line_substitution(change,reason):
    _,e,_=api_context();b=e['bookmakers'][0]
    if change=='other_book':b['key']='bet365'
    elif change=='duplicate_book':e['bookmakers'].append(copy.deepcopy(b))
    elif change=='no_draw':b['markets'][0]['outcomes'].pop(1)
    elif change=='line35':
        for o in b['markets'][1]['outcomes']:o['point']=3.5
    elif change=='one_side':b['markets'][1]['outcomes'].pop()
    elif change=='mix_books':
        other=copy.deepcopy(b);other['key']='casumo';e['bookmakers'].append(other);b['markets'].pop()
    elif change=='duplicate_market':b['markets'].append(copy.deepcopy(b['markets'][0]))
    elif change=='invalid_price':b['markets'][0]['outcomes'][0]['price']=True
    elif change=='future_update':b['markets'][0]['last_update']='2026-09-09T11:01:00Z'
    elif change=='naive_update':b['last_update']='2026-09-09T10:59:00'
    elif change=='kickoff':e['commence_time']='2026-09-10T15:00:00Z'
    elif change=='unknown_team':e['home_team']='United'
    c=cover(e)
    assert c['usable']==0 and c['fixtures'][0]['reason']==reason


def test_api_extra_fields_lines_and_order_do_not_change_fit():
    _,e,_=api_context();a=cover(e)
    b=e['bookmakers'][0];b['markets'][0]['outcomes'].reverse()
    b['markets'][1]['outcomes'] += [dict(name=n,price=2.,point=3.5) for n in ('Over','Under')]
    b['unknown']='allowed';e['unknown']='allowed';b['markets'].reverse()
    assert cover(e)['fixtures'][0]['home_goals']==a['fixtures'][0]['home_goals']


def test_api_cutoff_deadline_duplicates_and_failed_fit(monkeypatch):
    from fpl_model import defensive_odds
    d,e,s=api_context()
    for stamp in ['2026-09-09T13:00:00Z','2026-09-10T12:30:00Z']:
        assert cover(source={**s,'available_at':stamp})['usable']==0
    stamp=d['events'][-1]['deadline_time']
    assert build_coverage(d,[e],{**s,'available_at':stamp},5,BaselineConfig(),stamp)['fixtures'][0]['reason']=='odds_not_before_deadline'
    assert build_coverage(d,[e,e],s,5,BaselineConfig(),d['as_of_at'])['fixtures'][0]['reason']=='duplicate_fixture_markets'
    def fail(*a,**k):raise RuntimeError('solver failed')
    monkeypatch.setattr(defensive_odds,'least_squares',fail)
    assert cover()['fixtures'][0]['reason']=='poisson_fit_failed'


def test_api_overlay_preserves_minutes_and_every_nondefensive_component():
    d,e,s=api_context();cfg=BaselineConfig()
    a=simulate(d,5,cfg,draws=1000,seed=42)
    c=build_coverage(d,[e],s,5,cfg,d['as_of_at'])
    assert c['usable']==1
    b=simulate(d,5,cfg,draws=1000,seed=42,defensive_odds=c)
    np.testing.assert_array_equal(a.minutes,b.minutes)
    for pid in a.explanations:
        for k,v in a.explanations[pid]['point_components'].items():
            if k not in ('clean_sheets','goals_conceded'):assert b.explanations[pid]['point_components'][k]==v
        assert a.explanations[pid]['fixtures']==b.explanations[pid]['fixtures']
    assert not np.array_equal(a.points,b.points)


class Response:
    def __init__(self,body,status=200):
        self.content=body;self.status_code=status
        self.headers={'Content-Type':'application/json','x-requests-last':'2','x-requests-used':'2','x-requests-remaining':'498'}
    def __enter__(self):return self
    def __exit__(self,*args):pass


class Session:
    def __init__(self,response):self.response=response;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if isinstance(self.response,Exception):raise self.response
        return self.response


def test_capture_exact_bytes_quota_and_offline_loading(tmp_path,capsys,caplog):
    m=importlib.import_module('fpl_model.data_sources.the_odds_api')
    from fpl_model.io import SnapshotWriter,verify_snapshot
    from fpl_model.odds_comparison import load_odds
    body=(json.dumps([api_context()[1]],indent=2)+'\n').encode();s=Session(Response(body))
    w=SnapshotWriter(tmp_path);result=m.fetch_odds(w,api_key='secret-local-value',session=s)
    assert result.status=='success' and result.quota=={'last':2,'used':2,'remaining':498}
    assert not w.final_path.exists()
    path=w.finalize();manifest=verify_snapshot(path)
    assert (path/result.raw_path).read_bytes()==body
    rows,source=load_odds(path,source_name='the_odds_api')
    assert rows==[api_context()[1]] and source['source']=='the_odds_api'
    assert source['sha256'] and source['available_at']==source['retrieved_at']
    assert len(s.calls)==1 and s.calls[0][1]['allow_redirects'] is False
    assert s.calls[0][1]['params']['markets']=='h2h,totals'
    assert s.calls[0][1]['params']['regions']=='uk'
    assert 'secret-local-value' not in json.dumps(manifest)+capsys.readouterr().out+caplog.text


@pytest.mark.parametrize('failure',[401,429,503,'transport','invalid_json','echo'])
def test_capture_failures_have_no_retry_and_no_secret(tmp_path,capsys,caplog,failure):
    m=importlib.import_module('fpl_model.data_sources.the_odds_api')
    from fpl_model.io import SnapshotWriter
    secret='test-never-persist'
    response=Response(b'{"message":"error"}',failure) if isinstance(failure,int) else (
        requests.ConnectionError('https://private?apiKey='+secret) if failure=='transport' else
        Response(secret.encode() if failure=='echo' else b'<html>error</html>'))
    s=Session(response);w=SnapshotWriter(tmp_path)
    result=m.fetch_odds(w,api_key=secret,session=s)
    assert result.status!='success' and len(s.calls)==1
    assert all(secret.encode() not in p.read_bytes() for p in w.staging_path.rglob('*') if p.is_file())
    assert secret not in capsys.readouterr().out+caplog.text


def test_cli_reads_local_key_without_modification_and_only_explicitly_fetches(tmp_path,monkeypatch,capsys):
    from scripts.fetch_odds_api import main
    m=importlib.import_module('fpl_model.data_sources.the_odds_api')
    env=tmp_path/'.env';text='OTHER=value\nODDS_API_KEY="private-test" # local\n';env.write_text(text)
    s=Session(Response(json.dumps([api_context()[1]]).encode()))
    from contextlib import nullcontext
    monkeypatch.setattr(m.requests,'Session',lambda:nullcontext(s))
    assert main(['--env-file',str(env),'--data-root',str(tmp_path/'data')])==0
    assert env.read_text()==text and len(s.calls)==1
    out=capsys.readouterr().out
    assert '498' in out and 'private-test' not in out


def test_api_invalid_event_and_outcome_structures_are_explicit_fallback():
    _,e,_=api_context()
    e['home_team']=['Manchester United']
    assert cover(e)['usable']==0
    _,e,_=api_context()
    e['bookmakers'][0]['markets'][0]['outcomes'][0]['name']=['Manchester United']
    assert cover(e)['fixtures'][0]['reason']=='invalid_h2h_market'


def test_missing_credentials_do_not_request_or_finalize(tmp_path):
    from fpl_model.data_sources.the_odds_api import fetch_odds
    from fpl_model.io import SnapshotWriter
    w=SnapshotWriter(tmp_path);s=Session(Response(b'[]'))
    r=fetch_odds(w,api_key='',session=s)
    assert r.status=='skipped' and s.calls==[] and not w.final_path.exists()
    assert json.loads((w.staging_path/'manifest.json').read_text())['failures'][0]['outcome']=='skipped'


def test_invalid_api_response_never_loads_as_usable(tmp_path):
    from fpl_model.data_sources.the_odds_api import fetch_odds
    from fpl_model.io import SnapshotWriter
    from fpl_model.odds_comparison import load_odds
    w=SnapshotWriter(tmp_path)
    fetch_odds(w,api_key='local-test',session=Session(Response(b'{}')))
    rows,meta=load_odds(w.finalize(),source_name='the_odds_api')
    assert rows==[] and meta['failure']=='no_unique_valid_odds_response'


def test_api_offensive_scoring_arrays_are_identical_scenario_by_scenario(monkeypatch):
    import fpl_model.simulation as sim
    actual_score=sim.score_components;captured=[]
    def record(*args,**kwargs):
        result=actual_score(*args,**kwargs)
        if isinstance(kwargs.get('minutes'),np.ndarray):
            captured.append({k:np.asarray(v).copy() for k,v in result.items()})
        return result
    monkeypatch.setattr(sim,'score_components',record)
    d,e,s=api_context();cfg=BaselineConfig()
    sim.simulate(d,5,cfg,draws=100,seed=42)
    before=list(captured);captured.clear()
    sim.simulate(d,5,cfg,draws=100,seed=42,defensive_odds=cover())
    assert before and len(before)==len(captured)
    for a,b in zip(before,captured):
        for k in a:
            if k not in ('clean_sheets','goals_conceded'):np.testing.assert_array_equal(a[k],b[k])

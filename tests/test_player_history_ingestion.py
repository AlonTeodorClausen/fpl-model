"""Mock transport only; SnapshotWriter and validation remain real."""
import hashlib
import json
from datetime import datetime, timezone

import pytest
import requests

from fpl_model.io import SnapshotWriter, SnapshotStateError, verify_snapshot
from fpl_model.data_sources import fpl_player_history as adapter

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


class Response:
    def __init__(self, body, status=200, media='application/json'):
        self.content, self.status_code = body, status
        self.headers = {'Content-Type': media}
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Session:
    def __init__(self, response): self.response, self.calls = response, []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception): raise self.response
        return self.response


def test_exact_raw_provenance_and_caller_finalization(tmp_path):
    writer = SnapshotWriter(tmp_path, clock=lambda: NOW)
    body = b' {"history": [], "history_past": [], "fixtures": []}\r\n'
    session = Session(Response(body))
    adapter.fetch_player_histories(writer, [12], session=session, clock=lambda: NOW)
    assert not writer.final_path.exists()
    raw = writer.staging_path / 'raw/fpl_api/element_summary/12.json'
    assert raw.read_bytes() == body
    manifest = verify_snapshot(writer.finalize())
    f = manifest['files'][0]
    assert f['sha256'] == hashlib.sha256(body).hexdigest() and f['size_bytes'] == len(body)
    assert f['request_context'] == {'element_id': '12'}
    assert f['available_at'] == f['retrieved_at'] == NOW.isoformat(timespec='microseconds')
    assert session.calls == [('https://fantasy.premierleague.com/api/element-summary/12/', {'timeout': (10, 30), 'allow_redirects': False})]


@pytest.mark.parametrize('response', [Response(b'', 200), Response(b'<html>bad</html>',200,'text/html'), Response(b'{}'), Response(b'{"history":null}'), Response(b'{"history":[]} ',403), Response(b'limited',429), Response(b'failed',503), requests.Timeout('PRIVATE_SECRET')])
def test_explicit_failure_no_retry_no_fake_history(tmp_path, response):
    writer = SnapshotWriter(tmp_path, clock=lambda: NOW)
    session = Session(response)
    with pytest.raises(adapter.FPLSourceError):
        adapter.fetch_player_histories(writer, [12], session=session, clock=lambda: NOW)
    assert len(session.calls) == 1
    manifest = json.loads((writer.staging_path/'manifest.json').read_text())
    assert manifest['failures'] or any(f['outcome']=='http_error' for f in manifest['files'])
    assert 'PRIVATE_SECRET' not in json.dumps(manifest)
    if isinstance(response, Response):
        assert (writer.staging_path/'raw/fpl_api/element_summary/12.json').read_bytes() == response.content
    with pytest.raises(SnapshotStateError): writer.finalize()
    assert not writer.final_path.exists()


@pytest.mark.parametrize('ids', [[], [True], [0], [1,1], ['1']])
def test_bounded_explicit_ids_before_any_network(tmp_path, ids):
    session = Session(Response(b'{"history":[]}'))
    with pytest.raises(ValueError):
        adapter.fetch_player_histories(SnapshotWriter(tmp_path), ids, session=session)
    assert session.calls == []


def test_ids_can_cover_a_dynamic_full_pool():
    assert adapter.validate_element_ids(range(1000, 1803)) == tuple(range(1000, 1803))


def test_optional_retries_preserve_bodies_and_respect_retry_after(tmp_path):
    responses = [Response(b'busy', 429), Response(b' {"history":[]}\r\n')]
    responses[0].headers['Retry-After'] = '4'
    class Sequence(Session):
        def get(self, url, **kwargs):
            self.calls.append(url)
            return responses.pop(0)
    session=Sequence(None); waits=[]; progress=[]
    writer=SnapshotWriter(tmp_path, clock=lambda: NOW)
    results=adapter.fetch_player_histories(writer,[12],session=session,clock=lambda: NOW,
        required=False,max_attempts=3,request_interval=.5,sleep=waits.append,progress=progress.append)
    assert results[0]['status']=='success' and results[0]['attempts']==2
    assert waits==[4.0] and progress[-1]['completed']==1
    path=writer.finalize(); manifest=verify_snapshot(path)
    assert [f['http_status'] for f in manifest['files']]==[429,200]
    assert [(path/f['relative_path']).read_bytes() for f in manifest['files']]==[b'busy',b' {"history":[]}\r\n']
    assert all(f['required'] is False for f in manifest['files'])


@pytest.mark.parametrize('status, retry_after, attempts',[(503,'',3),(429,'120',1),(403,'',1)])
def test_optional_failure_is_bounded_and_does_not_become_empty_history(tmp_path,status,retry_after,attempts):
    response=Response(b'failure',status);response.headers['Retry-After']=retry_after
    session=Session(response);writer=SnapshotWriter(tmp_path,clock=lambda:NOW)
    result=adapter.fetch_player_histories(writer,[1,2],session=session,clock=lambda:NOW,
        required=False,max_attempts=3,request_interval=.5,sleep=lambda _:None)
    assert len(session.calls)==(attempts if status==429 else 2*attempts)
    assert result[0]['status']=='http_error' and result[0]['raw_path'] is None
    if status==429: assert result[1]['status']=='deferred' and result[1]['attempts']==0
    assert len(verify_snapshot(writer.finalize())['failures'])==(2 if status==429 else 2*attempts)


def test_final_503_retry_after_is_honored_before_the_next_player(tmp_path):
    waits=[];request_sleep_totals=[]
    responses=[Response(b'busy',503) for _ in range(3)]+[Response(b'{"history":[]}')]
    for response in responses[:3]: response.headers['Retry-After']='10'
    class Sequence:
        def get(self,url,**kwargs):
            request_sleep_totals.append(sum(waits))
            return responses.pop(0)
    writer=SnapshotWriter(tmp_path,clock=lambda:NOW)
    result=adapter.fetch_player_histories(writer,[1,2],session=Sequence(),clock=lambda:NOW,
        required=False,max_attempts=3,request_interval=.5,sleep=waits.append)
    assert result[0]['status']=='http_error' and result[1]['status']=='success'
    assert request_sleep_totals[3]-request_sleep_totals[2]>=10

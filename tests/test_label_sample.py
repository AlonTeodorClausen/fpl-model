"""All payloads are synthetic; these tests never need stored live data/network."""
import csv
import hashlib
import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from fpl_model.io import SnapshotWriter, verify_snapshot


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load('capture_label_sample')
audit = load('audit_label_sample')
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


class Response:
    def __init__(self, body=b'{}', status=200, content_type='application/json'):
        self.content, self.status_code = body, status
        self.headers = {'Content-Type': content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def fetch(writer, client, **kwargs):
    return capture.capture(writer, client, source='fpl_api', url='https://fantasy.premierleague.com/api/element-summary/1/',
                           relative='element_summary/1.json', kind='json', clock=lambda: NOW, **kwargs)


def test_capture_exact_bytes_before_parsing_and_caller_finalization(tmp_path):
    writer = SnapshotWriter(tmp_path)
    body = b' { "history" : [] }\r\n'
    client = Client([Response(body)])
    path = fetch(writer, client, required=True)
    assert (writer.staging_path / path).read_bytes() == body
    assert not writer.final_path.exists()
    manifest = verify_snapshot(writer.finalize())
    entry = manifest['files'][0]
    assert entry['sha256'] == hashlib.sha256(body).hexdigest()
    assert entry['size_bytes'] == len(body)
    assert entry['available_at'] == entry['retrieved_at']
    assert client.calls[0][1] == {'timeout': (10, 30), 'allow_redirects': False}


@pytest.mark.parametrize('response', [Response(b'', 200), Response(b'<html>error</html>', 200, 'text/html'), Response(b'not JSON', 200), Response(b'failure', 503)])
def test_invalid_required_response_preserved_and_not_retried(tmp_path, response):
    writer = SnapshotWriter(tmp_path)
    client = Client([response])
    with pytest.raises(capture.CaptureError):
        fetch(writer, client, required=True)
    assert len(client.calls) == 1
    assert next(writer.staging_path.glob('raw/fpl_api/attempt_01/element_summary/*.json')).read_bytes() == response.content
    assert json.loads((writer.staging_path / 'manifest.json').read_text())['failures']


def test_optional_retries_keep_attempts_and_429_stops(tmp_path):
    writer = SnapshotWriter(tmp_path)
    client = Client([Response(b'bad', 502), Response()])
    sleeps = []
    fetch(writer, client, required=False, sleep=sleeps.append)
    manifest = verify_snapshot(writer.finalize())
    assert len(manifest['files']) == 2 and len(manifest['failures']) == 1
    assert sleeps == [1.0]
    second = SnapshotWriter(tmp_path)
    limited = Client([Response(b'rate limited', 429)])
    with pytest.raises(capture.CaptureError):
        fetch(second, limited, required=False)
    assert len(limited.calls) == 1


def test_transport_retries_are_bounded_and_exception_secrets_not_saved(tmp_path):
    writer = SnapshotWriter(tmp_path)
    client = Client([requests.Timeout('SECRET')] * 3)
    sleeps = []
    with pytest.raises(capture.CaptureError):
        fetch(writer, client, required=False, sleep=sleeps.append)
    assert len(client.calls) == 3 and sleeps == [1.0, 2.0]
    assert 'SECRET' not in (writer.staging_path / 'manifest.json').read_text()


@pytest.fixture
def snapshots(tmp_path):
    baseline = SnapshotWriter(tmp_path / 'raw')
    sample = SnapshotWriter(tmp_path / 'raw')
    for writer in (baseline, sample):
        writer.pin_source_commit('fpl_core', capture.EXPECTED_SHA)

    def raw(writer, name, obj, source='fpl_api'):
        if name.endswith('.csv'):
            stream = io.StringIO(newline='')
            output = csv.DictWriter(stream, fieldnames=list(obj[0]))
            output.writeheader()
            output.writerows(obj)
            body = stream.getvalue().encode()
        else:
            body = json.dumps(obj).encode()
        writer.write_raw(source + '/' + name, body, source=source, required=source == 'fpl_api',
                         request_started_at=NOW, retrieved_at=NOW, available_at=NOW,
                         **({'commit_sha': capture.EXPECTED_SHA} if source == 'fpl_core' else {}))

    teams = [dict(id=1, code=3, name='Arsenal'), dict(id=2, code=7, name='Villa')]
    player = dict(id=1, code=101, team=1, team_code=3, first_name='A', second_name='B', web_name='B', minutes=180, element_type=2)
    events = [dict(id=3, finished=True, data_checked=True), dict(id=4, finished=False, data_checked=False)]
    fixtures = [dict(id=gw, event=gw, team_h=1, team_a=2, kickoff_time=f'2026-09-0{gw}T14:00:00Z', started=True, finished=gw == 3) for gw in (3, 4)]
    for writer in (baseline, sample):
        raw(writer, 'bootstrap_static.json', dict(teams=teams, elements=[player], events=events))
        raw(writer, 'fixtures.json', fixtures)
    raw(baseline, 'teams.csv', teams, 'fpl_core')
    raw(baseline, 'players.csv', [dict(player_id=1, player_code=101, team_code=3, first_name='A', second_name='B', web_name='B')], 'fpl_core')
    raw(baseline, 'playerstats.csv', [dict(id=1, gw=gw, minutes=90) for gw in (3, 4)], 'fpl_core')
    raw(sample, 'element_summary/1.json', {'history': [dict(element=1, fixture=gw, round=gw, opponent_team=2, was_home=True, kickoff_time=f['kickoff_time'], minutes=90, starts=1, total_points=2) for gw, f in zip((3, 4), fixtures)]})
    for gw in (3, 4):
        folder = f'By Gameweek/GW{gw}/'
        raw(sample, folder + 'matches.csv', [dict(match_id=f'm{gw}', home_team='3.0', away_team='7.0', kickoff_time=fixtures[gw-3]['kickoff_time'][:-1], tournament='prem', finished=gw == 3)], 'fpl_core')
        raw(sample, folder + 'playermatchstats.csv', [dict(player_id=1, match_id=f'm{gw}', minutes_played=91, xg='')], 'fpl_core')
    return baseline.finalize(), sample.finalize()


def test_capture_is_bounded_pinned_and_finalized_once(snapshots, tmp_path, monkeypatch):
    responses = [Response()] * 14 + [Response(b'id,value\n1,x\n', content_type='text/csv')] * 6
    client = Client(responses)
    monkeypatch.setattr(capture.requests, 'Session', lambda: client)
    finalized = []
    original = SnapshotWriter.finalize

    def finalize(writer):
        finalized.append(writer.run_id)
        return original(writer)

    monkeypatch.setattr(SnapshotWriter, 'finalize', finalize)
    path, partial = capture.run(snapshots[0], tmp_path / 'captured')
    assert not partial and len(finalized) == 1
    assert len(client.calls) == 20
    assert len([u for u, _ in client.calls if 'element-summary' in u]) == 12
    core_urls = [u for u, _ in client.calls if 'githubusercontent' in u]
    assert len(core_urls) == 6 and all(capture.EXPECTED_SHA in u and '/main/' not in u for u in core_urls)
    assert len(verify_snapshot(path)['files']) == 20


def test_offline_audit_is_deterministic_and_read_only(snapshots):
    before = {p: p.read_bytes() for root in snapshots for p in root.rglob('*') if p.is_file()}
    report = audit.audit(*snapshots)
    assert report == audit.audit(*snapshots)
    assert report['label_states'] == {'final': 1, 'provisional': 1}
    assert report['comparison_counts']['minutes'] == {'unexplained': 2}
    assert report['comparison_counts']['expected_goals'] == {'missing in one source': 2}
    assert len(report['aggregate_minutes_discrepancies']) == 1
    assert len(report['fixture_crosswalk']['candidates']) == 2
    assert not report['fixture_crosswalk']['canonicalisation_approved']
    assert before == {p: p.read_bytes() for root in snapshots for p in root.rglob('*') if p.is_file()}


def test_report_cannot_overwrite_or_write_into_raw(snapshots, tmp_path):
    with pytest.raises(SystemExit):
        audit.main([*map(str, snapshots), '--output', str(snapshots[1] / 'report')])
    args = [*map(str, snapshots), '--output', str(tmp_path / 'report')]
    audit.main(args)
    # Different output directories must not change the serialized report bytes.
    other = tmp_path / 'reproduced'
    audit.main([*map(str, snapshots), '--output', str(other)])
    for path in (tmp_path / 'report').iterdir():
        assert path.read_bytes() == (other / path.name).read_bytes()
    with pytest.raises(FileExistsError):
        audit.main(args)


@pytest.mark.parametrize('body', [b'a,a\n1,2', b'a,b\n1', b'a,b\n"broken'])
def test_csv_parser_rejects_malformed_without_imputation(body):
    with pytest.raises((ValueError, csv.Error)):
        audit.csv_rows(body)


def test_candidate_rule_rejects_collisions_and_never_matches_by_name():
    f = dict(id=1, team_h=1, team_a=2, kickoff_time='2026-09-03T14:00:00Z')
    m = dict(match_id='m1', home_team='3.0', away_team='7.0', kickoff_time='2026-09-03T14:00:00', tournament='prem')
    codes = {3: 1, 7: 2}
    assert len(audit.fixture_candidates([f], [m], codes)['candidates']) == 1
    for fixtures, matches in [([f, {**f, 'id': 2}], [m]), ([f], [m, {**m, 'match_id': 'm2'}]), ([f], [m, m])]:
        result = audit.fixture_candidates(fixtures, matches, codes)
        assert not result['candidates'] and result['collisions']
    assert audit.fixture_candidates([f], [{**m, 'home_team': 'Arsenal'}], codes)['invalid']
    assert audit.fixture_candidates([f], [{**m, 'kickoff_time': '2026-09-03T15:00:00'}], codes)['unmatched']
    assert not audit.fixture_candidates([f], [{**m, 'tournament': 'champions-league'}], codes)['candidates']

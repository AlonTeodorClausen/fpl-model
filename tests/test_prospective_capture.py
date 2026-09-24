"""Real writer/adapters/normalizer/readiness with fake HTTP and an explicit clock."""
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest
import requests

from fpl_model.label_contracts import utc
from test_forecast_freeze import PLAYERS, START, DEADLINE
from test_player_labels_workflow import Response


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/freeze_forecast_origin.py'
    assert path.exists(), 'Prospective capture CLI not implemented'
    spec = importlib.util.spec_from_file_location('freeze_forecast_origin', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Session:
    def __init__(self, *, deadline=DEADLINE, fail=False, quarantine=False, empty=False):
        self.deadline, self.fail, self.quarantine, self.empty = deadline, fail, quarantine, empty
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.endswith('/bootstrap-static/'):
            return Response(dict(elements=[dict(id=p, team=1, element_type=1) for p in PLAYERS],
                teams=[dict(id=1), dict(id=2)], element_types=[dict(id=1)],
                events=[dict(id=4, deadline_time='2026-09-12T12:30:00Z', finished=True, data_checked=True),
                        dict(id=5, deadline_time=self.deadline, finished=False, data_checked=False),
                        dict(id=6, deadline_time='2026-10-10T10:00:00Z', finished=False, data_checked=False)]))
        if url.endswith('/fixtures/'):
            return Response([dict(id=11, event=4, team_h=1, team_a=2, kickoff_time='2026-09-12T14:00:00Z', started=True, finished=True),
                             dict(id=12, event=5, team_h=1, team_a=2, kickoff_time='2026-09-19T14:00:00Z', started=False, finished=False)])
        pid = int(url.rstrip('/').rsplit('/', 1)[-1])
        history = dict(element=pid, fixture=11, round=4, opponent_team=2, was_home=True,
                       kickoff_time='2026-09-12T14:00:00Z', minutes=-1 if self.quarantine else 90, starts=1, total_points=6)
        return Response({'history': [] if self.empty else [history]}, 503 if self.fail else 200)


def run(tmp_path, *, session=None, clock=None, **kwargs):
    return module().run_capture(raw_root=tmp_path/'raw', report_root=tmp_path/'reports',
        freeze_root=tmp_path/'freezes', season='2026-2027', event=kwargs.pop('event', 'next'),
        max_input_age=kwargs.pop('max_input_age', timedelta(minutes=30)),
        session=session or Session(), clock=clock or (lambda: utc(START)), **kwargs)


def test_end_to_end_fresh_eight_responses_are_frozen_and_verified(tmp_path):
    s = Session()
    path = run(tmp_path, session=s)
    m = module()
    frozen = m.verify_freeze(path)
    assert frozen['status'] == 'ready' and frozen['event'] == 5
    assert len(s.calls) == 8
    assert {int(u.rstrip('/').split('/')[-1]) for u in s.calls[2:]} == set(PLAYERS)
    assert all(i['requirements']['history']['reference']['source_snapshot_id'] == frozen['fresh_snapshot_id'] for i in frozen['inputs'])
    assert all(i['observations'][0]['label_state'] == 'final' for i in frozen['inputs'])
    # Past final history is allowed information; future outcome selection isn't.
    assert '"targets"' not in (path/'freeze.json').read_text()
    assert len(frozen['handoff']['player_fixtures']) == 6


def test_later_capture_creates_new_freeze_and_keeps_prior_inputs_identical(tmp_path):
    m = module()
    first = run(tmp_path)
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    second = run(tmp_path, clock=lambda: utc(START)+timedelta(minutes=1))
    assert first != second
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before
    assert m.verify_freeze(first)['fresh_snapshot_id'] != m.verify_freeze(second)['fresh_snapshot_id']


def test_deadline_change_is_preserved_across_captures_and_old_freeze_unchanged(tmp_path):
    m = module()
    first = run(tmp_path)
    old = (first/'freeze.json').read_bytes()
    second = run(tmp_path, session=Session(deadline='2026-09-18T17:35:00Z'), clock=lambda: utc(START)+timedelta(minutes=1))
    new = m.verify_freeze(second)
    assert new['deadline']['revision_detected']
    assert {v['forecast_origin_at'] for v in new['deadline']['observations']} == {'2026-09-18T17:30:00+00:00', '2026-09-18T17:35:00+00:00'}
    assert new['forecast_origin_at'] == '2026-09-18T17:35:00+00:00'
    assert (first/'freeze.json').read_bytes() == old


def test_after_explicit_deadline_and_stale_and_quarantine_are_rejected(tmp_path):
    m = module()
    late = run(tmp_path, event=5, clock=lambda: utc('2026-09-18T17:31:00Z'))
    assert 'deadline_reached' in m.verify_freeze(late, require_ready=False)['reasons']
    stale = run(tmp_path, max_input_age=timedelta(minutes=10))
    assert 'stale_inputs' in m.verify_freeze(stale, require_ready=False)['reasons']
    bad = run(tmp_path, session=Session(quarantine=True))
    assert 'inputs_not_ready' in m.verify_freeze(bad, require_ready=False)['reasons']


def test_failed_fresh_capture_preserves_failure_and_never_reuses_old_freeze(tmp_path):
    first = run(tmp_path)
    old = (first/'freeze.json').read_bytes()
    with pytest.raises(module().FPLSourceError):
        run(tmp_path, session=Session(fail=True))
    assert len(list((tmp_path/'freezes').glob('*/COMPLETE.json'))) == 1
    assert (first/'freeze.json').read_bytes() == old
    failed = list((tmp_path/'raw/.staging').glob('*/manifest.json'))
    assert len(failed) == 1 and json.loads(failed[0].read_text())['status'] == 'failed'


def test_cli_exit_status_summary_and_explicit_policy(tmp_path, monkeypatch, capsys):
    m = module()
    original = m.run_capture
    monkeypatch.setattr(m, 'run_capture', lambda **kw: original(**kw, session=Session(), clock=lambda: utc(START)))
    args = ['--season', '2026-2027', '--event', 'next', '--raw-root', str(tmp_path/'raw'),
            '--report-root', str(tmp_path/'reports'), '--freeze-root', str(tmp_path/'freezes'), '--max-input-age', '30m']
    assert m.main(args) == 0
    out = capsys.readouterr().out
    assert 'phase_b: not_started' in out and 'status: ready' in out and 'event: 5' in out
    args[-1] = '10m'
    assert m.main(args) == 2
    assert 'stale_inputs' in capsys.readouterr().out
    for value in ('0m', '-1h', 'nan', '30', 'forever'):
        with pytest.raises(ValueError):
            m.parse_max_age(value)


def test_capture_crossing_selected_next_deadline_does_not_roll_to_another_event(tmp_path):
    calls = [0]
    def clock():
        calls[0] += 1
        return utc(START) if calls[0] < 5 else utc(DEADLINE)+timedelta(seconds=1)
    p = run(tmp_path, clock=clock)
    f = module().verify_freeze(p, require_ready=False)
    assert f['event'] == 5 and f['status'] == 'rejected'
    assert 'deadline_reached' in f['reasons']


def test_verifier_detects_changed_raw_and_normalization_sources(tmp_path):
    m = module()
    p = run(tmp_path)
    f = m.verify_freeze(p)
    report = Path(f['source_report']['report_path'])/'labels.jsonl'
    original = report.read_bytes()
    report.write_bytes(b'{}\n')
    with pytest.raises(ValueError):
        m.verify_freeze(p)
    report.write_bytes(original)
    raw = Path(f['source_report']['raw_snapshot_path'])/'raw/fpl_api/fixtures.json'
    raw.write_bytes(b'[]')
    with pytest.raises(m.SnapshotError):
        m.verify_freeze(p)


def test_explicit_prior_report_deadline_is_preserved_without_reusing_inputs(tmp_path):
    m = module()
    first = run(tmp_path/'earlier')
    old = m.verify_freeze(first)
    second = run(tmp_path/'later', prior_reports=[old['source_report']['report_path']],
                 session=Session(deadline='2026-09-18T17:35:00Z'), clock=lambda: utc(START)+timedelta(minutes=1))
    new = m.verify_freeze(second)
    assert new['deadline']['revision_detected']
    assert all(i['requirements']['history']['reference']['source_snapshot_id'] == new['fresh_snapshot_id'] for i in new['inputs'])


def test_captured_empty_history_is_ready_and_does_not_infer_dnp(tmp_path):
    f = module().verify_freeze(run(tmp_path, session=Session(empty=True)))
    assert f['status'] == 'ready'
    assert all(i['history_status'] == 'empty_observed_history' and not i['observations'] for i in f['inputs'])


def test_cli_transport_failure_is_nonzero_and_does_not_echo_exception_secrets(tmp_path, monkeypatch, capsys):
    m = module()
    original = m.run_capture
    class BrokenSession(Session):
        def get(self, url, **kwargs):
            if '/element-summary/' in url:
                raise requests.RequestException('secret=test-token-must-not-be-logged')
            return super().get(url, **kwargs)
    monkeypatch.setattr(m, 'run_capture', lambda **kw: original(**kw, session=BrokenSession(), clock=lambda: utc(START)))
    assert m.main(['--season', '2026-2027', '--event', '5', '--max-input-age', '30m',
                   '--raw-root', str(tmp_path/'raw'), '--report-root', str(tmp_path/'reports'),
                   '--freeze-root', str(tmp_path/'freezes')]) == 1
    captured = capsys.readouterr()
    assert 'no previous capture was substituted' in captured.err
    assert 'test-token' not in captured.err + captured.out
    assert not list((tmp_path/'freezes').glob('*/COMPLETE.json'))


@pytest.mark.parametrize('reference_kind', ['raw', 'observation'])
def test_verifier_binds_frozen_references_to_the_actual_source(tmp_path, reference_kind):
    from fpl_model.forecast_freeze import digest
    m = module()
    frozen = m.verify_freeze(run(tmp_path))
    if reference_kind == 'raw':
        frozen['inputs'][0]['requirements']['history']['reference']['sha256'] = 'b'*64
    else:
        frozen['inputs'][0]['observations'][0]['observation_id'] = 'not-a-real-observation'
    frozen['input_sha256'] = frozen['handoff']['input_sha256'] = digest(frozen['inputs'])
    new = m.write_freeze(frozen, tmp_path/'other', clock=lambda: utc(START))
    with pytest.raises(ValueError):
        m.verify_freeze(new)

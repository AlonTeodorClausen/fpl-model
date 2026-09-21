"""Offline integration through immutable snapshots, normalized reports and CLI."""
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from fpl_model.player_fixture_labels import normalize_snapshot, write_report
from test_player_fixture_labels import NOW, snapshot


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/audit_replay_readiness.py'
    assert path.exists(), 'Step 2E audit CLI missing'
    spec = importlib.util.spec_from_file_location('audit_replay_readiness', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def reports(tmp_path):
    case = dict(history=[{}], event_patch={'deadline_time': '2026-09-12T12:30:00Z'},
                extra_event={'id': 5, 'deadline_time': '2026-09-22T12:00:00Z', 'finished': False},
                extra_fixture={'id': 12, 'event': 5, 'kickoff_time': '2026-09-22T14:00:00Z', 'started': False, 'finished': False})
    old = snapshot(tmp_path, case)
    later_case = {**case, 'history': [{}, {'fixture': 12, 'round': 5, 'kickoff_time': '2026-09-22T14:00:00Z'}],
                  'extra_event': {**case['extra_event'], 'finished': True},
                  'extra_fixture': {**case['extra_fixture'], 'started': True, 'finished': True}}
    new = snapshot(tmp_path, later_case, now=NOW + timedelta(days=2))
    return [write_report(normalize_snapshot(p, season='2026-2027', element_ids=[1]), tmp_path / 'reports') for p in (old, new)]


def test_cli_verifies_sources_writes_versioned_outputs_and_never_changes_inputs(reports, tmp_path, capsys):
    m = module()
    original = {p: p.read_bytes() for root in (tmp_path / 'raw', tmp_path / 'reports') for p in root.rglob('*') if p.is_file()}
    result = m.audit_reports(reports, events=[4, 5])
    assert result == m.audit_reports(reports[::-1], events=[5, 4])
    assert result['summary']['readiness'] == {'not_replayable': 1, 'ready': 1}
    historical, prospective = result['records']
    assert historical['inputs']['observations'] == []
    assert prospective['targets'][0]['observation']['label_state'] == 'final'
    assert prospective['targets'][0]['observation']['available_at'] > prospective['forecast_origin_at']
    output = tmp_path / 'audits'
    assert m.main(['--reports', *map(str, reports), '--events', '4', '5', '--output-root', str(output)]) == 0
    assert 'not_replayable' in capsys.readouterr().out
    directory = output / result['audit_id']
    assert set(p.name for p in directory.iterdir()) == {'manifest.json', 'quality.json', 'provenance_trace.json', 'COMPLETE.json'}
    second = m.write_audit(result, tmp_path / 'reproduced')
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}
    with pytest.raises(FileExistsError):
        m.write_audit(result, output)
    with pytest.raises(ValueError):
        m.write_audit(result, reports[0] / 'nested')
    assert original == {p: p.read_bytes() for root in (tmp_path / 'raw', tmp_path / 'reports') for p in root.rglob('*') if p.is_file()}


def test_future_capture_only_changes_targets_not_historical_information(reports):
    m = module()
    before = m.audit_reports(reports[:1], events=[4, 5])
    after = m.audit_reports(reports, events=[4, 5])
    for a, b in zip(before['records'], after['records']):
        for key in ('inputs', 'readiness', 'reasons', 'forecast_origin_at'):
            assert a[key] == b[key]


def test_corrupt_or_duplicate_source_reports_rejected(reports):
    m = module()
    with pytest.raises(ValueError):
        m.audit_reports([reports[0], reports[0]], events=[5])
    (reports[0] / 'labels.jsonl').write_text('{}\n')
    with pytest.raises(ValueError):
        m.audit_reports(reports, events=[5])

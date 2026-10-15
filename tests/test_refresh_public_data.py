"""Operator refresh only advances the guest pointer after a ready capture."""

from datetime import datetime, timezone

from test_quick_refresh import _snapshot


def _at(monkeypatch, cli, value):
    monkeypatch.setattr(cli, '_now', lambda: datetime.fromisoformat(value.replace('Z', '+00:00')))


def test_no_fetch_publishes_existing_verified_data_without_network(tmp_path, monkeypatch, capsys):
    from scripts import refresh_public_data as cli

    raw = tmp_path / 'data/raw'
    _snapshot(raw, '2026-10-10T10:00:00Z', history=True)
    context = _snapshot(raw, '2026-10-14T10:00:00Z', history=False)
    monkeypatch.setattr(cli, 'refresh_official_data', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('offline publication must not fetch')))
    _at(monkeypatch, cli, '2026-10-14T11:00:00Z')
    out = tmp_path / 'artifacts/public_data'
    exit_code = cli.main(['--season', '2026-2027', '--raw-root', str(raw),
                          '--publication-root', str(out), '--no-fetch'])
    assert exit_code == 0
    assert (out / 'active.json').is_file()
    assert context.name in capsys.readouterr().out


def test_partial_refresh_keeps_previous_publication(tmp_path, monkeypatch):
    from scripts import refresh_public_data as cli
    from fpl_model.public_data import publish_public_data

    raw = tmp_path / 'data/raw'
    history = _snapshot(raw, '2026-10-10T10:00:00Z', history=True)
    context = _snapshot(raw, '2026-10-14T10:00:00Z', history=False)
    out = tmp_path / 'artifacts/public_data'
    publish_public_data(raw, out, context_snapshot=context, history_snapshot=history,
                        season='2026-2027', checked_at='2026-10-14T11:00:00Z')
    pointer = (out / 'active.json').read_bytes()
    partial = _snapshot(raw, '2026-10-15T16:00:00Z', history=False, started=True)
    monkeypatch.setattr(cli, 'refresh_official_data', lambda *a, **k: dict(
        status='history_partial', context_snapshot=partial,
        attempted_history_snapshot=partial, selected_snapshot=partial))
    _at(monkeypatch, cli, '2026-10-15T16:01:00Z')
    assert cli.main(['--season', '2026-2027', '--raw-root', str(raw),
                     '--publication-root', str(out)]) == 2
    assert (out / 'active.json').read_bytes() == pointer


def test_successful_refresh_publishes_its_new_context_and_history(tmp_path, monkeypatch):
    from scripts import refresh_public_data as cli
    from fpl_model.public_data import read_active_public_data

    raw = tmp_path / 'data/raw'
    history = _snapshot(raw, '2026-10-10T10:00:00Z', history=True)
    context = _snapshot(raw, '2026-10-14T10:00:00Z', history=False)
    calls = []

    def refresh(*args, **kwargs):
        calls.append(kwargs['known_paths'])
        return dict(status='context_only', selected_snapshot=context,
                    context_snapshot=context, history_snapshot=history)

    monkeypatch.setattr(cli, 'refresh_official_data', refresh)
    _at(monkeypatch, cli, '2026-10-14T11:00:00Z')
    out = tmp_path / 'artifacts/public_data'
    assert cli.main(['--season', '2026-2027', '--raw-root', str(raw),
                     '--publication-root', str(out)]) == 0
    active = read_active_public_data(raw, out)
    assert active['context_path'] == context and active['history_path'] == history
    assert calls and history in calls[0]

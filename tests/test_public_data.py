"""Only verified official context/history pairs may become public inputs."""

import pytest

from test_quick_refresh import _snapshot


def _sources(tmp_path):
    raw = tmp_path / 'data/raw'
    history = _snapshot(raw, '2026-10-10T10:00:00Z', history=True)
    context = _snapshot(raw, '2026-10-14T10:00:00Z', history=False, player_price=62)
    return raw, history, context


def _publish(raw, publication_root, context, history, *, checked_at='2026-10-14T11:00:00Z'):
    from fpl_model.public_data import publish_public_data

    return publish_public_data(raw, publication_root, context_snapshot=context,
                               history_snapshot=history, season='2026-2027',
                               checked_at=checked_at)


def test_publication_pins_verified_sources_and_keeps_each_version(tmp_path):
    from fpl_model.public_data import read_active_public_data

    raw, history, context = _sources(tmp_path)
    root = tmp_path / 'artifacts/public_data'
    first = _publish(raw, root, context, history)
    first_manifest = (root / 'runs' / f"{first['publication_id']}.json").read_bytes()
    second = _publish(raw, root, context, history)
    active = read_active_public_data(raw, root)
    assert first['publication_id'] != second['publication_id']
    assert (root / 'runs' / f"{first['publication_id']}.json").read_bytes() == first_manifest
    assert active['publication_id'] == second['publication_id']
    assert active['context_path'] == context and active['history_path'] == history
    assert active['readiness']['status'] == 'ready'
    assert active['context_manifest_sha256'] and active['history_manifest_sha256']


def test_unready_refresh_cannot_replace_the_active_publication(tmp_path):
    from fpl_model.public_data import read_active_public_data

    raw, history, context = _sources(tmp_path)
    root = tmp_path / 'artifacts/public_data'
    first = _publish(raw, root, context, history)
    pointer = (root / 'active.json').read_bytes()
    started = _snapshot(raw, '2026-10-15T16:00:00Z', history=False, started=True)
    with pytest.raises(ValueError, match='not ready'):
        _publish(raw, root, started, history, checked_at='2026-10-15T16:01:00Z')
    with pytest.raises(ValueError, match='complete full-player'):
        _publish(raw, root, context, context)
    with pytest.raises(ValueError, match='not ready'):
        _publish(raw, root, context, history, checked_at='2026-10-16T11:00:00Z')
    assert (root / 'active.json').read_bytes() == pointer
    assert read_active_public_data(raw, root)['publication_id'] == first['publication_id']


def test_public_reader_rejects_missing_or_modified_pointer_and_raw_bytes(tmp_path):
    from fpl_model.public_data import read_active_public_data

    raw, history, context = _sources(tmp_path)
    root = tmp_path / 'artifacts/public_data'
    with pytest.raises(ValueError, match='No active'):
        read_active_public_data(raw, root)
    _publish(raw, root, context, history)
    original = (root / 'active.json').read_bytes()
    (root / 'active.json').write_text('{"publication_id":"../elsewhere"}')
    with pytest.raises(ValueError, match='Invalid public'):
        read_active_public_data(raw, root)
    (root / 'active.json').write_bytes(original)
    (context / 'raw/fpl_api/bootstrap_static.json').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='Invalid public'):
        read_active_public_data(raw, root)


def test_publication_refuses_paths_outside_the_configured_raw_root(tmp_path):
    raw, history, context = _sources(tmp_path)
    other = tmp_path / 'other'
    with pytest.raises(ValueError, match='raw root'):
        _publish(other, tmp_path / 'artifacts/public_data', context, history)

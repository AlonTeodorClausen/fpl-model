"""Explicit, atomic selection of verified shared inputs for the guest UI."""

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from fpl_model.io import SnapshotError, verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.quick_refresh import load_current_inputs
from fpl_model.readiness import assess_deadline_readiness


def _snapshot(raw_root, path):
    root = Path(raw_root).resolve()
    snapshot = Path(path).resolve()
    if snapshot.parent != root or Path(path).is_symlink():
        raise ValueError('Public inputs must be direct children of the configured raw root')
    manifest = verify_snapshot(snapshot)
    return snapshot, manifest, sha256((snapshot / 'manifest.json').read_bytes()).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _write_new(path, payload):
    with path.open('xb') as file:
        file.write(payload)
        file.flush()
        os.fsync(file.fileno())


def publish_public_data(raw_root, publication_root, *, context_snapshot,
                        history_snapshot, season, checked_at,
                        max_context_age_hours=24):
    """Publish a ready source pair, then atomically move only the active pointer."""
    root = Path(raw_root).resolve()
    destination = Path(publication_root).resolve()
    if destination.is_relative_to(root):
        raise ValueError('Public reports must not be stored inside raw snapshots')
    context, context_manifest, context_sha = _snapshot(root, context_snapshot)
    history, history_manifest, history_sha = _snapshot(root, history_snapshot)
    metadata = history_manifest.get('run_metadata', {})
    if (metadata.get('purpose') != 'official_full_player_history'
            or metadata.get('overall') != 'complete'
            or metadata.get('season') != season
            or metadata.get('successful_players') != metadata.get('player_count')):
        raise ValueError('Public history must be a complete full-player capture')
    data = load_current_inputs(context, history, season=season)
    readiness = assess_deadline_readiness(data, checked_at,
                                          max_context_age_hours=max_context_age_hours)
    if readiness['status'] != 'ready':
        raise ValueError('Public inputs are not ready: ' + ','.join(readiness['reasons']))
    publication_id = uuid4().hex
    report = dict(schema_version=1, publication_id=publication_id, season=season,
                  checked_at=utc(checked_at).isoformat(),
                  context_snapshot=context.name, context_snapshot_id=context_manifest['run_id'],
                  context_manifest_sha256=context_sha,
                  history_snapshot=history.name, history_snapshot_id=history_manifest['run_id'],
                  history_manifest_sha256=history_sha, readiness=readiness)
    destination.mkdir(parents=True, exist_ok=True)
    runs = destination / 'runs'
    runs.mkdir(exist_ok=True)
    payload = _json_bytes(report)
    _write_new(runs / f'{publication_id}.json', payload)
    pointer = _json_bytes(dict(schema_version=1, publication_id=publication_id,
                               publication_sha256=sha256(payload).hexdigest()))
    temporary = destination / f'.active-{uuid4().hex}.tmp'
    try:
        _write_new(temporary, pointer)
        os.replace(temporary, destination / 'active.json')
    finally:
        temporary.unlink(missing_ok=True)
    return dict(report, context_path=context, history_path=history)


def read_active_public_data(raw_root, publication_root):
    """Refuse absent, altered or moved publications instead of guessing a snapshot."""
    root = Path(publication_root)
    pointer_path = root / 'active.json'
    if not pointer_path.is_file():
        raise ValueError('No active public data publication')
    try:
        pointer = json.loads(pointer_path.read_bytes())
        publication_id = pointer['publication_id']
        if pointer['schema_version'] != 1 or not re.fullmatch(r'[0-9a-f]{32}', publication_id):
            raise ValueError()
        payload = (root / 'runs' / f'{publication_id}.json').read_bytes()
        if sha256(payload).hexdigest() != pointer['publication_sha256']:
            raise ValueError()
        report = json.loads(payload)
        if report['schema_version'] != 1 or report['publication_id'] != publication_id:
            raise ValueError()
        context, context_manifest, context_sha = _snapshot(raw_root, Path(raw_root) / report['context_snapshot'])
        history, history_manifest, history_sha = _snapshot(raw_root, Path(raw_root) / report['history_snapshot'])
        if (context_sha != report['context_manifest_sha256'] or history_sha != report['history_manifest_sha256']
                or context_manifest['run_id'] != report['context_snapshot_id']
                or history_manifest['run_id'] != report['history_snapshot_id']):
            raise ValueError()
        return dict(report, context_path=context, history_path=history)
    except (OSError, ValueError, KeyError, TypeError, SnapshotError):
        raise ValueError('Invalid public data publication') from None

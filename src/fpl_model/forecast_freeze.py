"""Phase-A input-only freeze contract. No outcome attachment or feature creation.

Immutability is enforced by exclusive publication and verified hashes, as for raw
snapshots. This is not a WORM filesystem or externally attested clock service.
"""
import copy
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.replay_readiness import information_for

SAMPLE_PLAYERS = (1, 2, 5, 12, 26, 439)


def utc_now():
    return datetime.now(timezone.utc)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _input_only(value):
    if isinstance(value, dict):
        if value.get('purpose') == 'outcome_only' or any(
            'target' in key.lower() or ('outcome' in key.lower() and key != 'outcome') for key in value
        ):
            raise ValueError('Outcome information cannot enter a freeze')
        # Raw provenance uses "outcome" for HTTP success, not a player target.
        if 'outcome' in value and not (value['outcome'] == 'success' and value.get('source') == 'fpl_api'
                                      and value.get('relative_path', '').startswith('raw/fpl_api/')):
            raise ValueError('Only raw HTTP outcome metadata is allowed')
        for child in value.values():
            _input_only(child)
    elif isinstance(value, list):
        for child in value:
            _input_only(child)


def deadline_observations(replay):
    return [dict(event=o['event'], forecast_origin_at=o['forecast_origin_at'],
                 evidence=copy.deepcopy(o['deadline_evidence']))
            for o in replay['origins'] if o['forecast_origin_at'] and o['deadline_evidence']]


def prepare_freeze(replay, *, fresh_snapshot_id, capture_started_at, freeze_created_at,
                   max_input_age, deadline_versions, source_report):
    """Deterministic payload for explicit input versions, clock values and policy.

    Readiness uses only the fresh capture. Older versions are deadline evidence,
    never fallback inputs. Only the six fixed players and one event are allowed.
    """
    if not isinstance(max_input_age, timedelta) or max_input_age <= timedelta(0):
        raise ValueError('Explicit positive maximum input age required')
    if sorted(r['player_id'] for r in replay['records']) != list(SAMPLE_PLAYERS) or len(replay['origins']) != 1:
        raise ValueError('Exactly the existing six players and one event required')
    created, started = utc(freeze_created_at), utc(capture_started_at)
    origin = replay['origins'][0]
    deadline = utc(origin['forecast_origin_at']) if origin['forecast_origin_at'] else None
    reasons, players, inputs, ages = [], [], [], []
    if deadline is None:
        reasons.append('unresolved_deadline')
    elif created >= deadline:
        reasons.append('deadline_reached')
    if created < started:
        reasons.append('invalid_capture_clock')
    for record in sorted(replay['records'], key=lambda r: r['player_id']):
        if record['event'] != origin['event'] or record['forecast_origin_at'] != origin['forecast_origin_at']:
            raise ValueError('Inconsistent replay origin')
        _input_only(record['inputs'])
        info = (information_for(record) if record['readiness'] == 'ready'
                else copy.deepcopy(record['inputs']))
        inputs.append(info)
        players.append(dict(player_id=record['player_id'], readiness=record['readiness'],
                            reasons=sorted(record['reasons'])))
        if record['readiness'] != 'ready':
            reasons.append('inputs_not_ready')
        refs = [dict(kind=key, **r['reference']) for key, r in info['requirements'].items()
                if r.get('reference')]
        refs += [dict(kind='observation', **r) for r in info['observations']]
        for ref in refs:
            available, retrieved = utc(ref['available_at']), utc(ref['retrieved_at'])
            if ref['source_snapshot_id'] != fresh_snapshot_id or retrieved < started:
                reasons.append('not_fresh_capture')
            if available < retrieved or available > created:
                reasons.append('invalid_capture_clock')
            age = (deadline - available).total_seconds() if deadline else None
            passed = age is not None and 0 <= age <= max_input_age.total_seconds()
            ages.append(dict(player_id=record['player_id'], kind=ref['kind'],
                observation_id=ref.get('observation_id'), relative_path=ref.get('relative_path'),
                available_at=available.isoformat(), age_at_origin_seconds=age, passed=passed))
    if not ages or not all(r['passed'] for r in ages):
        reasons.append('stale_inputs')
    ages.sort(key=lambda r: (r['player_id'], r['kind'], r['relative_path'] or '', r['observation_id'] or ''))

    selected = next(iter(deadline_observations(replay)), None)
    versions = [copy.deepcopy(v) for v in [*deadline_versions, *deadline_observations(replay)]
                if v['event'] == origin['event']]
    unique = {}
    by_time = defaultdict(set)
    for version in versions:
        version['forecast_origin_at'] = utc(version['forecast_origin_at']).isoformat()
        ref = version['evidence']['reference']
        ref['available_at'], ref['retrieved_at'] = utc(ref['available_at']).isoformat(), utc(ref['retrieved_at']).isoformat()
        if utc(ref['available_at']) > created or utc(ref['retrieved_at']) > utc(ref['available_at']):
            reasons.append('invalid_capture_clock')
        by_time[ref['available_at']].add(version['forecast_origin_at'])
        unique[canonical_bytes(version)] = version
    versions = sorted(unique.values(), key=lambda v: (utc(v['evidence']['reference']['available_at']), canonical_bytes(v)))
    if any(len(values) > 1 for values in by_time.values()):
        reasons.append('conflicting_deadline_observations')
    reasons = sorted(set(reasons))
    return dict(schema_version=1, contract='prospective_six_player_freeze_v1', phase='2F-A',
        season=replay['season'], event=origin['event'], forecast_origin_at=origin['forecast_origin_at'],
        capture_started_at=started.isoformat(), freeze_created_at=created.isoformat(),
        fresh_snapshot_id=fresh_snapshot_id, player_ids=list(SAMPLE_PLAYERS),
        status='rejected' if reasons else 'ready', reasons=reasons, players=players, inputs=inputs,
        input_sha256=digest(inputs), source_report=copy.deepcopy(source_report),
        deadline=dict(selected=selected, observations=versions,
                      revision_detected=len({v['forecast_origin_at'] for v in versions}) > 1,
                      policy='use_fresh_official_observation_and_preserve_prior_versions'),
        freshness=dict(max_input_age_seconds=max_input_age.total_seconds(),
                       basis='forecast_origin_at_minus_available_at',
                       passed=bool(ages) and all(r['passed'] for r in ages), references=ages),
        handoff=dict(phase_b_status='not_started', input_sha256=digest(inputs),
                     player_fixtures=[dict(player_id=i['player_id'], fixture_id=f)
                                      for i in inputs for f in i['relevant_fixture_ids']],
                     linking_rule='season_and_canonical_official_player_id_and_fixture_id',
                     scope='captured_team_schedule_not_a_participation_assertion'))


def _validate(manifest):
    _input_only(manifest)
    if manifest['contract'] != 'prospective_six_player_freeze_v1' or manifest['schema_version'] != 1:
        raise ValueError('Unknown freeze contract')
    if manifest['player_ids'] != list(SAMPLE_PLAYERS) or sorted(i['player_id'] for i in manifest['inputs']) != list(SAMPLE_PLAYERS):
        raise ValueError('Invalid player scope')
    if digest(manifest['inputs']) != manifest['input_sha256'] or manifest['handoff']['input_sha256'] != manifest['input_sha256']:
        raise ValueError('Input digest mismatch')
    if manifest['status'] not in {'ready', 'rejected'}:
        raise ValueError('Invalid freeze status')
    if manifest['status'] == 'ready':
        cutoff, created = utc(manifest['forecast_origin_at']), utc(manifest['freeze_created_at'])
        if created >= cutoff or manifest['reasons'] or not manifest['freshness']['passed']:
            raise ValueError('Not a valid prospective ready freeze')
        start = utc(manifest['capture_started_at'])
        maximum = manifest['freshness']['max_input_age_seconds']
        if maximum <= 0 or start > created or len(manifest['players']) != len(SAMPLE_PLAYERS):
            raise ValueError('Invalid capture policy or scope')
        for player, info in zip(manifest['players'], manifest['inputs']):
            if player['player_id'] != info['player_id'] or info['event'] != manifest['event']:
                raise ValueError('Conflicting player or event identity')
            information_for(dict(readiness=player['readiness'], inputs=info, forecast_origin_at=cutoff.isoformat()))
            refs = [r['reference'] for r in info['requirements'].values()] + info['observations']
            for ref in refs:
                available, retrieved = utc(ref['available_at']), utc(ref['retrieved_at'])
                if not start <= retrieved <= available <= created or ref['source_snapshot_id'] != manifest['fresh_snapshot_id']:
                    raise ValueError('Input is not from this completed fresh capture')
                if not 0 <= (cutoff - available).total_seconds() <= maximum:
                    raise ValueError('Input fails the recorded freshness policy')


def _write_new(path, body):
    with path.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def write_freeze(manifest, output_root, *, clock=utc_now):
    """Unique run directories and completion marker last; never overwrite/resume.

    Interrupted publication leaves no valid completion marker. Reject consumers
    must use verify_freeze rather than accepting a directory or JSON alone.
    """
    _validate(manifest)
    root = Path(output_root).resolve()
    source = manifest['source_report']
    if source and (root.is_relative_to(Path(source['raw_snapshot_path']).resolve().parent)
                   or root.is_relative_to(Path(source['report_path']).resolve())):
        raise ValueError('Freeze output must be outside protected source storage')
    def publication_time():
        now = utc(clock())
        if now < utc(manifest['freeze_created_at']):
            raise ValueError('Publication clock moved backwards')
        if manifest['status'] == 'ready' and now >= utc(manifest['forecast_origin_at']):
            raise ValueError('Deadline reached before publication')
        return now
    publication_time()
    directory = root / ('step2fa_' + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    body = canonical_bytes(manifest)
    _write_new(directory / 'freeze.json', body)
    published = publication_time()
    marker = dict(schema_version=1, freeze_id=directory.name, status=manifest['status'],
                  published_at=published.isoformat(), freeze_sha256=hashlib.sha256(body).hexdigest(),
                  input_sha256=manifest['input_sha256'])
    _write_new(directory / 'COMPLETE.json', canonical_bytes(marker))
    return directory


def verify_freeze(directory, *, require_ready=True, verify_sources=True):
    """Read-only phase-B prerequisite; does not attach or select any final labels."""
    root = Path(directory)
    if root.is_symlink() or any(p.is_symlink() for p in root.iterdir()):
        raise ValueError('Symlink freeze is not immutable source evidence')
    if {p.name for p in root.iterdir()} != {'freeze.json', 'COMPLETE.json'}:
        raise ValueError('Incomplete or unexpected freeze files')
    body = (root / 'freeze.json').read_bytes()
    marker = json.loads((root / 'COMPLETE.json').read_bytes())
    result = json.loads(body)
    if marker['freeze_sha256'] != hashlib.sha256(body).hexdigest() or marker['input_sha256'] != result['input_sha256'] or marker['status'] != result['status']:
        raise ValueError('Freeze integrity mismatch')
    _validate(result)
    if require_ready and result['status'] != 'ready':
        raise ValueError('Rejected attempt is not a ready freeze')
    published = utc(marker['published_at'])
    if published < utc(result['freeze_created_at']) or (result['status'] == 'ready' and published >= utc(result['forecast_origin_at'])):
        raise ValueError('Invalid prospective publication timestamp')
    if verify_sources:
        source = result['source_report']
        raw = Path(source['raw_snapshot_path'])
        snapshot = verify_snapshot(raw)
        if snapshot['run_id'] != result['fresh_snapshot_id'] or hashlib.sha256((raw / 'manifest.json').read_bytes()).hexdigest() != source['manifest_sha256']:
            raise ValueError('Freeze source snapshot mismatch')
        report = Path(source['report_path'])
        complete = (report / 'COMPLETE.json').read_bytes()
        if hashlib.sha256(complete).hexdigest() != source['report_sha256']:
            raise ValueError('Normalization report changed')
        for name, sha in json.loads(complete)['files'].items():
            if name not in {'labels.jsonl', 'quarantine.jsonl', 'quality.json'} or hashlib.sha256((report / name).read_bytes()).hexdigest() != sha:
                raise ValueError('Normalized source changed')
        files = {r['relative_path']: r for r in snapshot['files']}
        rows = {r['observation_id']: r for r in
                (json.loads(line) for line in (report / 'labels.jsonl').read_text().splitlines())}
        for info in result['inputs']:
            for requirement in info['requirements'].values():
                ref = requirement.get('reference')
                if ref is None:
                    continue  # Rejected attempts can contain missing requirements.
                original = files.get(ref['relative_path'])
                if original is None or original['sha256'] != ref['sha256'] or ref['source_snapshot_id'] != snapshot['run_id']:
                    raise ValueError('Frozen raw reference differs from its source')
                if utc(original['retrieved_at']) != utc(ref['retrieved_at']) or utc(original.get('available_at', original['retrieved_at'])) != utc(ref['available_at']):
                    raise ValueError('Frozen raw availability differs from its source')
            for ref in info['observations']:
                original = rows.get(ref['observation_id'])
                fields = ('player_id', 'fixture_id', 'event', 'label_state', 'source_snapshot_id', 'provenance')
                if original is None or any(ref[k] != original[k] for k in fields):
                    raise ValueError('Frozen observation differs from its normalized source')
                if any(utc(ref[k]) != utc(original[k]) for k in ('available_at', 'retrieved_at')):
                    raise ValueError('Frozen observation availability differs from its source')
    return result

"""Official-only label normalization, preserving independent observation versions.

This is not a cross-source canonical dataset or an as-of feature selector. Null
optional values stay null; missing rows never become synthetic appearances.
"""
import copy
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fpl_model.data_sources.fpl_player_history import validate_element_ids
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import LabelState, ObservationTime, label_state, utc

SCHEMA_VERSION = 1
INTEGER_FIELDS = ('minutes', 'starts', 'goals_scored', 'assists', 'clean_sheets',
                  'goals_conceded', 'own_goals', 'penalties_saved', 'penalties_missed',
                  'yellow_cards', 'red_cards', 'saves', 'bonus', 'bps',
                  'clearances_blocks_interceptions', 'recoveries', 'tackles',
                  'defensive_contribution', 'total_points')
DECIMAL_FIELDS = ('influence', 'creativity', 'threat', 'ict_index', 'expected_goals',
                  'expected_assists', 'expected_goal_involvements', 'expected_goals_conceded')
STAT_FIELDS = INTEGER_FIELDS + DECIMAL_FIELDS


def _index(rows, name):
    if not isinstance(rows, list):
        raise ValueError('Invalid context list: ' + name)
    result = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= 0 or row['id'] in result:
            raise ValueError('Missing or ambiguous context ID: ' + name)
        result[row['id']] = row
    return result


def _stat_errors(history):
    errors = []
    for field in INTEGER_FIELDS:
        value = history.get(field)
        if value is not None and (type(value) is not int or (field not in ('total_points', 'bps') and value < 0)):
            errors.append('invalid_' + field)
    for field in DECIMAL_FIELDS:
        value = history.get(field)
        if value is None:
            continue
        try:
            if not isinstance(value, str) or not Decimal(value).is_finite() or Decimal(value) < 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            errors.append('invalid_' + field)
    return errors


def normalize_snapshot(snapshot, *, season, element_ids):
    """Return accepted labels, unusable quarantine and explicit coverage/quality.

    One snapshot supplies all context. The caller names the season; an existing
    run season must agree. The historical club comes from fixture + was_home,
    never from present-day player.team. Current membership differences are noted.
    """
    ids = validate_element_ids(element_ids)
    if not re.fullmatch(r'\d{4}-\d{4}', season) or int(season[5:]) != int(season[:4]) + 1:
        raise ValueError('Expected explicit YYYY-YYYY season')
    root = Path(snapshot).resolve()
    manifest = verify_snapshot(root)
    if manifest.get('run_metadata', {}).get('season', season) != season:
        raise ValueError('Snapshot season differs from requested season')

    def read(suffix):
        entries = [e for e in manifest['files'] if e['source'] == 'fpl_api' and e['relative_path'].endswith('/' + suffix) and e['outcome'] == 'success']
        if len(entries) != 1:
            raise ValueError('Missing or ambiguous official capture: ' + suffix)
        entry = entries[0]
        data = json.loads((root / entry['relative_path']).read_bytes())
        ObservationTime(None, utc(entry['retrieved_at']), utc(entry.get('available_at', entry['retrieved_at'])))
        return data, entry

    bootstrap, bootstrap_meta = read('bootstrap_static.json')
    fixtures_data, fixtures_meta = read('fixtures.json')
    players = _index(bootstrap['elements'], 'players')
    teams = _index(bootstrap['teams'], 'teams')
    events = _index(bootstrap['events'], 'events')
    fixtures = _index(fixtures_data, 'fixtures')
    accepted, quarantine, coverage = [], [], []
    membership_differences = []
    for pid in ids:
        payload, history_meta = read(f'element_summary/{pid}.json')
        if history_meta.get('request_context', {}).get('element_id') != str(pid):
            raise ValueError('History provenance element ID disagrees with request')
        history = payload.get('history') if isinstance(payload, dict) else None
        if not isinstance(history, list):
            raise ValueError('Missing or malformed history is not an empty history')
        context = [history_meta, fixtures_meta, bootstrap_meta]
        available = max(utc(e.get('available_at', e['retrieved_at'])) for e in context).isoformat()
        provenance = [{**e, 'effective_available_at': e.get('available_at', e['retrieved_at']),
                       'availability_basis': 'manifest' if 'available_at' in e else 'retrieval_fallback'} for e in context]
        version = dict(schema_version=SCHEMA_VERSION, season=season, source='fpl_api',
                       source_snapshot_id=manifest['run_id'], retrieved_at=history_meta['retrieved_at'],
                       history_available_at=history_meta.get('available_at', history_meta['retrieved_at']),
                       available_at=available, source_published_at=None, provenance=provenance)
        duplicates = Counter(r['fixture'] for r in history if isinstance(r, dict) and type(r.get('fixture')) is int)
        state_counts = Counter()
        for row_index, h in enumerate(history):
            reasons = []
            if not isinstance(h, dict):
                reasons.append('malformed_history_row')
                h_dict = {}
            else:
                h_dict = h
            fid = h_dict.get('fixture')
            fixture = fixtures.get(fid, {}) if type(fid) is int else {}
            event = events.get(fixture.get('event'), {}) if type(fixture.get('event')) is int else {}
            state, reason = label_state(h_dict, fixture, event, element_id=pid)
            if state == LabelState.UNUSABLE:
                reasons.append(reason)
            if pid not in players:
                reasons.append('unknown_player_id')
            if type(fid) is int and duplicates[fid] > 1:
                reasons.append('duplicate_player_fixture')
            if any(type(fixture.get(k)) is not int or fixture[k] not in teams for k in ('team_h', 'team_a')):
                reasons.append('unknown_fixture_team_id')
            reasons.extend(_stat_errors(h_dict))
            if reasons:
                quarantine.append({**version, 'requested_player_id': pid, 'source_history_index': row_index,
                                   'label_state': 'unusable', 'reasons': sorted(set(reasons)),
                                   'official_history': copy.deepcopy(h)})
                state_counts['unusable'] += 1
                continue
            own_team = fixture['team_h'] if h['was_home'] else fixture['team_a']
            if players[pid].get('team') != own_team:
                membership_differences.append({'player_id': pid, 'fixture_id': fid, 'fixture_team_id': own_team,
                                               'current_team_id': players[pid].get('team')})
            row = {**version, 'observation_id': f"{season}:{manifest['run_id']}:{pid}:{fid}",
                   'player_id': pid, 'fixture_id': fid, 'event': h['round'], 'team_id': own_team,
                   'opponent_team_id': h['opponent_team'], 'was_home': h['was_home'],
                   'kickoff_time': h['kickoff_time'], 'event_time': h['kickoff_time'],
                   **{k: h.get(k) for k in STAT_FIELDS}, 'label_state': state.value, 'label_state_reason': reason,
                   'missing_fields': [k for k in STAT_FIELDS if k not in h],
                   'null_fields': [k for k in STAT_FIELDS if k in h and h[k] is None],
                   'official_history': copy.deepcopy(h), 'source_history_index': row_index}
            # Verify the output against source values, without scoring or imputation.
            if any(row[k] != h.get(k) for k in STAT_FIELDS):
                raise ValueError('Normalized official value changed')
            accepted.append(row)
            state_counts[state.value] += 1
        coverage.append({'player_id': pid, 'history_rows': len(history), 'states': dict(sorted(state_counts.items())),
                         'history_status': 'empty_observed_history' if not history else 'rows_observed'})
    accepted.sort(key=lambda r: (r['player_id'], r['fixture_id']))
    quality = dict(schema_version=SCHEMA_VERSION, audit_id='step2c_' + manifest['run_id'],
                   source_snapshot_id=manifest['run_id'], season=season, snapshot_path=str(root),
                   manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
                   requested_element_ids=list(ids), players=coverage,
                   accepted_rows=len(accepted), quarantined_rows=len(quarantine),
                   label_states=dict(sorted(Counter(r['label_state'] for r in accepted + quarantine).items())),
                   explicit_zero_minute_rows=sum(r['minutes'] == 0 for r in accepted),
                   empty_history_players=[p['player_id'] for p in coverage if p['history_rows'] == 0],
                   current_team_differences=membership_differences,
                   missing_fields={k: sum(k in r['missing_fields'] for r in accepted) for k in STAT_FIELDS},
                   null_fields={k: sum(k in r['null_fields'] for r in accepted) for k in STAT_FIELDS},
                   source_value_checks={'checked_rows': len(accepted), 'mismatches': 0},
                   status='accepted_with_quarantine' if quarantine else 'accepted',
                   limitations=['Absence is unknown, never an inferred DNP.',
                                'Fixture-side identity does not independently prove historical registration.',
                                'Core is later enrichment only; no Core values used.',
                                'Historical input availability is not inferred from event timestamps.'])
    verify_snapshot(root)
    return {'labels': accepted, 'quarantine': quarantine, 'quality': quality}


def write_report(result, output_root):
    """Exclusive versioned output; COMPLETE.json is written last, with file hashes."""
    root = Path(output_root).resolve()
    snapshot = Path(result['quality']['snapshot_path']).resolve()
    if root.is_relative_to(snapshot.parent):
        raise ValueError('Reports must be outside raw snapshot storage')
    directory = root / result['quality']['audit_id']
    directory.mkdir(parents=True, exist_ok=False)
    def json_text(obj):
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False)
    payloads = {
        'labels.jsonl': ''.join(json_text(r) + '\n' for r in result['labels']),
        'quarantine.jsonl': ''.join(json_text(r) + '\n' for r in result['quarantine']),
        'quality.json': json.dumps(result['quality'], indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n',
    }
    digests = {}
    for name, text in payloads.items():
        body = text.encode('utf-8')
        with (directory/name).open('xb') as stream:
            stream.write(body)
        digests[name] = hashlib.sha256(body).hexdigest()
    with (directory/'COMPLETE.json').open('x') as stream:
        json.dump({'schema_version': SCHEMA_VERSION, 'files': digests}, stream, sort_keys=True, indent=2)
        stream.write('\n')
    return directory

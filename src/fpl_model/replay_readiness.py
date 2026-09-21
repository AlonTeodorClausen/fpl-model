"""Bounded official-FPL replay references. No features or participation inference.

Source payloads must come from checksum-verified captures (the audit CLI enforces
this). Observation selection delegates to Step 2D. Raw context selection applies
the same inclusive cutoff before inspecting payloads or resolving conflicts.
"""
import copy
import json
import re
from collections import Counter, defaultdict

from fpl_model.label_contracts import utc
from fpl_model.observation_selection import select_as_of, select_outcome


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _reference(source):
    r = copy.deepcopy(source['reference'])
    if r['source'] != 'fpl_api' or not r['relative_path'].startswith('raw/fpl_api/'):
        raise ValueError('Official FPL provenance required')
    if not r['source_snapshot_id'] or not re.fullmatch('[0-9a-f]{64}', r['sha256']):
        raise ValueError('Snapshot identity and checksum required')
    r['available_at'] = utc(r['available_at']).isoformat()
    r['retrieved_at'] = utc(r['retrieved_at']).isoformat()
    if utc(r['available_at']) < utc(r['retrieved_at']):
        raise ValueError('Cannot backdate source availability')
    return r


def _rank(source):
    r = _reference(source)
    return (utc(r['available_at']), utc(r['retrieved_at']), r['source_snapshot_id'],
            r['relative_path'], r['sha256'])


def _select_source(sources, kind, cutoff, player_id=None):
    # Future payloads, conflicts and versions cannot influence this selection.
    eligible = [s for s in sources if s['kind'] == kind and s.get('player_id') == player_id
                and utc(s['reference']['available_at']) <= cutoff]
    if not eligible:
        return None, dict(status='missing', reason='lacking_pre_origin_provenance', reference=None)
    by_time = defaultdict(list)
    by_version = defaultdict(list)
    for s in eligible:
        r = _reference(s)
        by_time[r['available_at']].append(s)
        by_version[(r['source_snapshot_id'], r['relative_path'])].append(s)
    if (any(len({_json(s) for s in group}) > 1 for group in by_version.values())
            or any(len({_json(s['payload']) for s in group}) > 1 for group in by_time.values())):
        return None, dict(status='conflicted', reason='conflicting_source_versions', reference=None)
    chosen = max(eligible, key=_rank)
    ties = sorted({_json(_reference(s)) for s in eligible if _rank(s)[0] == _rank(chosen)[0]})
    return chosen, dict(status='available', reason=None, reference=_reference(chosen),
                        equal_time_versions=[json.loads(r) for r in ties])


def _event(bootstrap, event):
    matches = [e for e in bootstrap.get('events', []) if e.get('id') == event]
    return matches[0] if len(matches) == 1 else None


def forecast_origin(sources, event):
    """Anchor to the earliest captured official deadline, never today's clock.

    A later capture cannot rewrite an existing historical origin. If the selected
    pre-origin bootstrap has revised that deadline, readiness requires review.
    The anchor evidence is audit metadata, not automatically information-eligible.
    """
    candidates = []
    # Once anchored, later payloads (including malformed deadline revisions) are
    # irrelevant to the historical origin definition.
    for s in sorted((s for s in sources if s['kind'] == 'bootstrap'), key=_rank):
        if candidates and _rank(s)[0] > _rank(candidates[0][0])[0]:
            break
        e = _event(s['payload'], event)
        if e and e.get('deadline_time'):
            candidates.append((s, utc(e['deadline_time'])))
    if not candidates:
        return dict(event=event, forecast_origin_at=None, status='unresolved', deadline_evidence=None)
    first = min(_rank(s)[0] for s, _ in candidates)
    earliest = [(s, deadline) for s, deadline in candidates if _rank(s)[0] == first]
    if len({deadline for _, deadline in earliest}) != 1:
        return dict(event=event, forecast_origin_at=None, status='conflicted', deadline_evidence=None)
    source, deadline = max(earliest, key=lambda pair: _rank(pair[0]))
    return dict(event=event, forecast_origin_at=deadline.isoformat(), status='established',
                deadline_evidence=dict(purpose='origin_definition_only', reference=_reference(source),
                                       field=f'events[id={event}].deadline_time',
                                       observed_by_origin=first <= deadline))


def _observation_ref(row):
    return dict(observation_id=row['observation_id'], source_snapshot_id=row['source_snapshot_id'],
                available_at=utc(row['available_at']).isoformat(),
                retrieved_at=utc(row['retrieved_at']).isoformat(),
                player_id=row['player_id'], fixture_id=row['fixture_id'], event=row['event'],
                label_state=row['label_state'],
                appearance='explicit_zero' if row['minutes'] == 0 else 'positive_minutes',
                provenance=copy.deepcopy(row['provenance']))


def _information(sources, observations, quarantine, *, season, player_id, origin):
    inputs = dict(purpose='as_of_information', player_id=player_id, event=origin['event'],
                  forecast_origin_at=origin['forecast_origin_at'], requirements={},
                  relevant_fixture_ids=[], observations=[], history_selections=[],
                  history_status='unresolved', fixture_context='unresolved')
    if origin['forecast_origin_at'] is None:
        reason = 'conflicting_official_deadline' if origin['status'] == 'conflicted' else 'unresolved_official_deadline'
        return inputs, [reason], 'conflicted' if origin['status'] == 'conflicted' else 'not_replayable'
    cutoff = utc(origin['forecast_origin_at'])
    reasons = []
    chosen = {}
    for kind in ('bootstrap', 'fixtures', 'history'):
        chosen[kind], requirement = _select_source(sources, kind, cutoff, player_id if kind == 'history' else None)
        inputs['requirements'][kind] = requirement
        if requirement['reason']:
            reasons.append(requirement['reason'])
    bootstrap, fixtures, history = (chosen[k] for k in ('bootstrap', 'fixtures', 'history'))
    team = None
    if bootstrap:
        b = bootstrap['payload']
        event = _event(b, origin['event'])
        if not event or not event.get('deadline_time'):
            reasons.append('unresolved_pre_origin_deadline')
        elif utc(event['deadline_time']) != cutoff:
            reasons.append('deadline_revision_requires_review')
        players = [p for p in b.get('elements', []) if p.get('id') == player_id]
        teams = [t.get('id') for t in b.get('teams', [])]
        if len(players) != 1 or players[0].get('team') not in teams:
            reasons.append('unresolved_player_team_identity')
        else:
            team = players[0]['team']
            inputs['team_id_at_capture'] = team
    if fixtures and team is not None:
        schedule = fixtures['payload']
        ids = [f['id'] for f in schedule]
        if len(ids) != len(set(ids)):
            reasons.append('conflicting_fixture_identity')
        else:
            relevant = [f for f in schedule if f.get('event') == origin['event']
                        and team in (f.get('team_h'), f.get('team_a'))]
            inputs['relevant_fixture_ids'] = sorted(f['id'] for f in relevant)
            inputs['fixture_context'] = 'captured_team_schedule_only'
            if not relevant:
                # Empty schedule may be a blank GW, postponement or unknown mapping.
                reasons.append('unresolved_empty_event_schedule')
    if history:
        history_rows = history['payload'].get('history')
        if not isinstance(history_rows, list):
            reasons.append('unresolved_history_payload')
        else:
            inputs['history_status'] = 'rows_observed' if history_rows else 'empty_observed_history'
            snapshot = history['reference']['source_snapshot_id']
            q = [q for q in quarantine if q.get('requested_player_id', q.get('player_id')) == player_id
                 and q['source_snapshot_id'] == snapshot and utc(q['available_at']) <= cutoff]
            if q:
                reasons.append('quarantined_history')
            pair_ids = {h.get('fixture') for h in history_rows if isinstance(h, dict)}
            if any(type(f) is not int or f <= 0 for f in pair_ids) or len(pair_ids) != len(history_rows):
                reasons.append('quarantined_history')
            for fid in sorted(f for f in pair_ids if type(f) is int and f > 0):
                selection = select_as_of(observations, season=season, player_id=player_id,
                                         fixture_id=fid, cutoff_at=cutoff)
                inputs['history_selections'].append(dict(fixture_id=fid, status=selection.status,
                    issues=selection.issues, equal_time_versions=selection.tie_versions,
                    duplicate_versions=selection.duplicate_versions))
                if selection.status == 'conflict':
                    reasons.append('conflicted_history_observation')
                elif selection.status != 'selected':
                    reasons.append('unresolved_normalized_history')
                else:
                    row = selection.for_information()
                    # A newer raw response cannot be declared normalized using an
                    # older row when its own context arrives after the cutoff.
                    if utc(row['available_at']) < utc(history['reference']['available_at']):
                        reasons.append('unresolved_latest_history_version')
                    inputs['observations'].append(_observation_ref(row))
    reasons = sorted(set(reasons))
    if any('conflict' in r for r in reasons):
        state = 'conflicted'
    elif 'lacking_pre_origin_provenance' in reasons:
        state = 'not_replayable'
    else:
        state = 'partial' if reasons else 'ready'
    return inputs, reasons, state


def _targets(observations, quarantine, *, season, player_id, event, scheduled_ids):
    # Outcome-only universe can grow with later captures, never the input universe.
    ids = set(scheduled_ids) | {r['fixture_id'] for r in observations
                              if r['season'] == season and r['player_id'] == player_id and r['event'] == event}
    targets = []
    for fid in sorted(ids):
        result = select_outcome(observations, season=season, player_id=player_id, fixture_id=fid)
        final_ref = _observation_ref(result.observation) if result.observation else None
        quarantined = [q for q in quarantine if q.get('season') == season
                       and q.get('requested_player_id', q.get('player_id')) == player_id
                       and isinstance(q.get('official_history'), dict)
                       and q['official_history'].get('fixture') == fid
                       and (final_ref is None or utc(q['available_at']) >= utc(final_ref['available_at']))]
        blocked = bool(quarantined) and result.status != 'conflict'
        targets.append(dict(purpose='outcome_only', fixture_id=fid,
                            status='quarantined' if blocked else result.status,
                            observation=None if blocked else final_ref,
                            historical_final_reference=final_ref if blocked else None,
                            quarantine=sorted([dict(source_snapshot_id=q['source_snapshot_id'],
                                available_at=utc(q['available_at']).isoformat(), reasons=q.get('reasons', []))
                                for q in quarantined], key=_json),
                            eligible_versions=result.eligible_versions, issues=result.issues))
    return targets


def build_replay(sources, observations, *, season, player_ids, events, quarantine=()):
    """Pure deterministic replay manifest; sources and observations are immutable inputs.

    Required references: bootstrap (deadline/player/team), complete fixture response,
    selected player's history response and its observed, normalized history rows.
    No fixed history length, scoring statistics, freshness threshold or target is
    required. Empty captured history is valid; absent history is not.
    """
    if not re.fullmatch(r'\d{4}-\d{4}', season) or int(season[5:]) != int(season[:4]) + 1:
        raise ValueError('Explicit season required')
    if not player_ids or len(set(player_ids)) > 6 or not events:
        raise ValueError('Explicit bounded sample of at most six players and events required')
    if any(type(i) is not int or i <= 0 for i in [*player_ids, *events]):
        raise ValueError('Positive official IDs required')
    origins = [forecast_origin(sources, event) for event in sorted(set(events))]
    records = []
    for origin in origins:
        for pid in sorted(set(player_ids)):
            inputs, reasons, readiness = _information(sources, observations, quarantine,
                                                     season=season, player_id=pid, origin=origin)
            records.append(dict(season=season, player_id=pid, event=origin['event'],
                forecast_origin_at=origin['forecast_origin_at'], readiness=readiness, reasons=reasons,
                provenance_class=('lacking_pre_origin_provenance' if 'lacking_pre_origin_provenance' in reasons
                                  else 'unresolved_origin' if origin['forecast_origin_at'] is None else 'pre_origin_captured'),
                inputs=inputs, targets=_targets(observations, quarantine, season=season, player_id=pid,
                        event=origin['event'], scheduled_ids=inputs['relevant_fixture_ids'])))
    return dict(schema_version=1, contract='minimal_official_replay_v1', season=season,
                player_ids=sorted(set(player_ids)), origins=origins, records=records,
                summary=dict(records=len(records), readiness=dict(sorted(Counter(r['readiness'] for r in records).items())),
                             reasons=dict(sorted(Counter(reason for r in records for reason in r['reasons']).items()))))


def information_for(record):
    """The information accessor returns only pre-origin references, never targets.

    It accepts only ready manifests and rechecks their availability boundary. This
    is an API separation, not a security boundary for arbitrary caller-made dicts.
    """
    if record['readiness'] != 'ready' or record['inputs']['purpose'] != 'as_of_information':
        raise ValueError('Only replay-ready information is accessible')
    inputs = record['inputs']
    cutoff = utc(record['forecast_origin_at'])
    if utc(inputs['forecast_origin_at']) != cutoff:
        raise ValueError('Conflicting information cutoff')
    for key in ('bootstrap', 'fixtures', 'history'):
        r = inputs['requirements'][key]
        if r['status'] != 'available' or utc(r['reference']['available_at']) > cutoff:
            raise ValueError('Input reference unavailable at origin')
    for r in inputs['observations']:
        if utc(r['available_at']) > cutoff:
            raise ValueError('Observation unavailable at origin')
    return copy.deepcopy(inputs)

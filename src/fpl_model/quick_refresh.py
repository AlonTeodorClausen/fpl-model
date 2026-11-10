"""Explicit official context refresh with audited player-history reuse.

The smart workflow captures context first, then updates player histories only
when coverage changed. Reused histories retain their original provenance.
"""
from contextlib import nullcontext
from pathlib import Path

import requests

from fpl_model.data_sources.fpl_api import _utc_now, fetch_fpl_snapshot
from fpl_model.io import SnapshotWriter, verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.prototype_data import load_data


def capture_official_context(raw_root, *, season, session=None, clock=_utc_now):
    """Publish a new immutable bootstrap/fixtures capture; never request histories."""
    writer = SnapshotWriter(raw_root, clock=clock)
    writer.set_run_metadata(dict(purpose='official_context_refresh', season=season))
    try:
        with requests.Session() if session is None else nullcontext(session) as client:
            fetch_fpl_snapshot(writer, session=client, clock=clock)
        return writer.finalize()
    except BaseException:
        writer.mark_failed()
        raise


def refresh_official_data(raw_root, *, season, known_paths, progress=None,
                          session=None, clock=_utc_now, request_interval=.5):
    """One explicit refresh: context first, then histories only if coverage changed.

    Element-summary returns a whole player history, so a required full-pool
    refresh still makes one request per current player. Never relabel a partial
    capture as complete or replace an old raw file with new bytes.
    """
    from fpl_model.full_player_capture import capture_all_players

    def announce(stage, **fields):
        if progress is not None:
            progress(dict(stage=stage, **fields))

    context = capture_official_context(raw_root, season=season, session=session, clock=clock)
    announce('context', context_snapshot=context)
    history = latest_history_snapshot([*known_paths, context], context, season=season)
    try:
        coverage = (load_current_inputs(context, history, season=season)['coverage']
                    if history is not None else {})
    except ValueError as exc:
        if str(exc) != 'History source is incomplete; select a complete full-pool capture':
            raise
        # A run can have all HTTP responses but still contain quarantined labels.
        # Such a history cannot be reused; fetch a new full-pool capture.
        history = None
        coverage = {}
    changed = sorted(set(coverage.get('newly_started_fixture_ids', []))
                     | set(coverage.get('newly_finished_fixture_ids', []))
                     | set(coverage.get('revised_result_fixture_ids', [])))
    required = history is None or coverage['history_refresh_required']
    base = dict(context_snapshot=context, history_snapshot=history,
                history_required=required, changed_fixture_ids=changed,
                new_player_ids=coverage.get('new_player_ids_without_history', []))
    if not required:
        announce('complete', status='context_only')
        return dict(**base, status='context_only', selected_snapshot=context,
                    attempted_history_snapshot=None)

    announce('history', changed_fixture_ids=changed, new_player_ids=base['new_player_ids'])
    def player_progress(row):
        announce('player', **row)
    capture = capture_all_players(raw_root, season=season, session=session,
                                  clock=clock, request_interval=request_interval,
                                  progress=player_progress)
    metadata = verify_snapshot(capture).get('run_metadata', {})
    complete = (metadata.get('purpose') == 'official_full_player_history'
                and metadata.get('season') == season
                and metadata.get('overall') == 'complete'
                and metadata.get('successful_players') == metadata.get('player_count'))
    status = 'history_complete' if complete else 'history_partial'
    announce('complete', status=status, attempted_history_snapshot=capture)
    return dict(**base, status=status, selected_snapshot=capture if complete else context,
                attempted_history_snapshot=capture)


def _reference(data):
    return dict(snapshot_id=data['snapshot_id'], snapshot_path=data['snapshot_path'],
                manifest_sha256=data['manifest_sha256'], available_at=data['as_of_at'])


def latest_history_snapshot(paths, context_path, *, season, include_incomplete=False):
    """Find a full-pool anchor no later than context; refresh reuse requires complete.

    The UI can include incomplete attempts so a later context does not conceal
    missing responses or quarantine behind an older complete capture.
    """
    context = Path(context_path).resolve()
    context_manifest = verify_snapshot(context)
    context_time = max(utc(e.get('available_at', e['retrieved_at'])) for e in context_manifest['files']
                       if e['source'] == 'fpl_api' and e['relative_path'].endswith(
                           ('/bootstrap_static.json', '/fixtures.json')))
    candidates = []
    for path in paths:
        manifest = verify_snapshot(path)
        metadata = manifest.get('run_metadata', {})
        complete=(metadata.get('overall') == 'complete'
                  and metadata.get('successful_players') == metadata.get('player_count'))
        if (metadata.get('purpose') != 'official_full_player_history'
                or metadata.get('season') != season or (not include_incomplete and not complete)):
            continue
        history_times = [utc(e.get('available_at', e['retrieved_at'])) for e in manifest['files']
                         if e['source'] == 'fpl_api' and '/element_summary/' in e['relative_path']
                         and e['outcome'] == 'success']
        if include_incomplete:
            # An all-failed run has no successful element-summary entry. Its
            # recorded attempts still establish when the missing data was seen.
            history_times=[utc(e.get('available_at',e['retrieved_at'])) for e in manifest['files']
                           if e['source']=='fpl_api' and e['outcome']=='success']
            history_times.extend(utc(e['recorded_at']) for e in manifest.get('failures',[])
                                 if e['source']=='fpl_api')
        if history_times and max(history_times) <= context_time:
            candidates.append((max(history_times), manifest['run_id'], Path(path)))
    return max(candidates)[2] if candidates else None


def select_history_snapshot(paths, context_path, *, season, include_incomplete=False):
    """Use own rows or an earlier full-pool anchor; incomplete reuse is opt-in."""
    chosen = Path(context_path).resolve()
    manifest = verify_snapshot(chosen)
    if (manifest.get('run_metadata', {}).get('purpose') == 'official_full_player_history'
            or any(e['source'] == 'fpl_api' and e['outcome'] == 'success'
                   and '/element_summary/' in e['relative_path'] for e in manifest['files'])):
        return chosen
    return latest_history_snapshot(paths, chosen, season=season, include_incomplete=include_incomplete)


def load_current_inputs(context_snapshot, history_snapshot, *, season='2026-2027',
                        include_season_history=False, allow_incomplete_history=False):
    """Combine current metadata with an earlier history source.

    No rows are copied into raw storage. Every reused label retains its original
    observation ID, availability time and snapshot provenance. A newly finished
    fixture is reported as an unmet history refresh, never filled as a DNP.
    Incomplete histories are opt-in for the UI; their missing responses and
    quarantine remain visible to readiness. Refresh reuse still requires complete.
    """
    context_path = Path(context_snapshot).resolve()
    history_path = Path(history_snapshot).resolve()
    context = load_data(context_path, season=season)
    if context_path == history_path:
        if include_season_history:
            context = load_data(context_path, season=season, include_season_history=True)
        ref = _reference(context)
        context['input_sources'] = dict(history=ref, official_context=ref, player_metadata=ref)
        missing=context['coverage']['missing_response_players']
        context['coverage'] = dict(context['coverage'],
            history_refresh_required=bool(missing or context['coverage']['quarantined_rows']),
            newly_finished_fixture_ids=[],newly_started_fixture_ids=[],
            new_player_ids_without_history=missing)
        return context
    manifest = verify_snapshot(history_path)
    metadata = manifest.get('run_metadata', {})
    if metadata.get('season') and metadata['season'] != season:
        raise ValueError('History and official context use different seasons')
    history = load_data(history_path, season=season, include_season_history=include_season_history)
    if utc(history['as_of_at']) > utc(context['as_of_at']):
        raise ValueError('Player history was captured after official context')
    if (not allow_incomplete_history and
            (history['coverage']['missing_response_players'] or history['coverage']['quarantined_rows'])):
        raise ValueError('History source is incomplete; select a complete full-pool capture')
    old_teams = {t['id']: t['name'] for t in history['teams']}
    new_teams = {t['id']: t['name'] for t in context['teams']}
    if old_teams != new_teams:
        raise ValueError('Official team identities changed; history reuse needs review')
    old_players = {p['id']: p for p in history['players']}
    current_players = {p['id']: p for p in context['players']}
    new_ids = sorted(set(current_players) - set(old_players))
    changed_team_ids = sorted(i for i in set(current_players) & set(old_players)
                              if current_players[i]['team'] != old_players[i]['team'])
    old_fixtures = {f['id']: f for f in history['fixtures']}
    newly_finished = sorted(f['id'] for f in context['fixtures'] if f.get('finished')
                            and not old_fixtures.get(f['id'], {}).get('finished'))
    newly_started = sorted(f['id'] for f in context['fixtures'] if f.get('started')
                           and not old_fixtures.get(f['id'], {}).get('started'))
    revised_results = sorted(f['id'] for f in context['fixtures'] if f.get('finished')
                             and old_fixtures.get(f['id'], {}).get('finished')
                             and any(f.get(k) != old_fixtures[f['id']].get(k)
                                     for k in ('team_h_score', 'team_a_score', 'event')))
    old_coverage = history['coverage']
    by_id = {p['player_id']: p for p in old_coverage['players']}
    player_coverage = [by_id.get(i, dict(player_id=i, history_rows=None,
                        history_status='not_in_history_snapshot', attempted=False))
                       for i in sorted(current_players)]
    covered_ids = set(current_players) & set(old_players)
    context['histories'] = [r for r in history['histories'] if r['player_id'] in covered_ids]
    context['quarantine'] = list(history.get('quarantine',[]))
    if include_season_history:
        context['season_histories'] = [r for r in history['season_histories'] if r['player_id'] in covered_ids]
    missing_ids=sorted(set(new_ids) | (set(old_coverage['missing_response_players']) & set(current_players)))
    context['coverage'] = dict(old_coverage, players=player_coverage,
        requested_element_ids=sorted(current_players),
        missing_response_players=missing_ids,
        new_player_ids_without_history=new_ids,
        changed_team_player_ids=changed_team_ids,
        newly_finished_fixture_ids=newly_finished,newly_started_fixture_ids=newly_started,
        revised_result_fixture_ids=revised_results,
        history_refresh_required=bool(missing_ids or old_coverage['quarantined_rows']
                                      or newly_started or newly_finished or revised_results),
        history_snapshot_id=history['snapshot_id'])
    context_ref=_reference(context)
    context['input_sources'] = dict(history=_reference(history), official_context=context_ref,
        player_metadata=context_ref,
        player_metadata_note='Prices, status and news use the fresh official context; '
                             'player-fixture histories retain their older retrieval time.')
    return context

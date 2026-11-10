"""Operational pre-deadline status from captured official sources.

This is a data-readiness check, not a forecast-quality or injury assessment.
Optional odds can fall back to baseline without invalidating official inputs.
"""
import math
from collections import Counter

from fpl_model.label_contracts import utc


def assess_deadline_readiness(data, now, *, max_context_age_hours=24,
                              odds_coverage=None):
    observed_now = utc(now)
    if not math.isfinite(max_context_age_hours) or max_context_age_hours <= 0:
        raise ValueError('Positive finite context-age limit required')
    sources = data.get('input_sources') or {}
    context = sources.get('official_context') or {}
    history = sources.get('history') or {}
    context_at = utc(context.get('available_at', data['as_of_at']))
    history_at = utc(history.get('available_at', data['as_of_at']))
    context_age = (observed_now-context_at).total_seconds()/3600
    history_age = (observed_now-history_at).total_seconds()/3600
    future = sorted(((utc(e['deadline_time']),e['id']) for e in data['events']
                     if utc(e['deadline_time']) > observed_now))
    deadline,event = future[0] if future else (None,None)
    coverage = data.get('coverage') or {}
    missing = sorted(coverage.get('missing_response_players') or [])
    quarantine=data.get('quarantine') or []
    quarantined_players=sorted({r['requested_player_id'] for r in quarantine
                                if type(r.get('requested_player_id')) is int})
    quarantine_reasons=dict(sorted(Counter(reason for row in quarantine
        for reason in row.get('reasons',[])).items()))
    quarantined_rows=max(int(coverage.get('quarantined_rows') or 0),len(quarantine))
    changed = sorted(set(coverage.get('newly_started_fixture_ids') or [])
                     | set(coverage.get('newly_finished_fixture_ids') or [])
                     | set(coverage.get('revised_result_fixture_ids') or []))
    in_progress = sorted(f['id'] for f in data.get('fixtures',[])
                         if f.get('started') and not f.get('finished'))
    hard=[];limited=[];attention=[]
    if deadline is None:hard.append('no_future_deadline')
    if context_age < 0 or history_age < 0:hard.append('source_after_check_time')
    if {'unknown_player_id','unknown_fixture_team_id','duplicate_player_fixture'} & quarantine_reasons.keys():
        hard.append('identity_conflict')
    if coverage.get('history_refresh_required'):limited.append('history_refresh_required')
    if missing:limited.append('missing_player_histories')
    if quarantined_rows:limited.append('quarantined_player_rows')
    if in_progress:limited.append('fixtures_in_progress')
    if context_age > max_context_age_hours:attention.append('context_stale')
    summary=None
    if odds_coverage is not None:
        usable=odds_coverage['usable'];expected=odds_coverage['expected_fixtures']
        if not isinstance(usable,int) or not isinstance(expected,int) or expected<0 or not 0<=usable<=expected:
            raise ValueError('Invalid odds coverage')
        summary=dict(usable=usable,expected_fixtures=expected)
        if expected==0:attention.append('odds_coverage_unresolved')
        elif usable<expected:attention.append('odds_fallback')
    blocked=hard+limited
    reasons=blocked+attention
    return dict(status='blocked' if blocked else 'attention' if attention else 'ready',
        new_forecast_status='blocked' if hard else 'limited' if limited else 'ready',
        hard_blockers=hard,limited_reasons=limited,
        reasons=reasons,event=event,deadline_at=deadline.isoformat() if deadline else None,
        checked_at=observed_now.isoformat(),context_available_at=context_at.isoformat(),
        history_available_at=history_at.isoformat(),context_age_hours=context_age,
        history_age_hours=history_age,max_context_age_hours=max_context_age_hours,
        context_snapshot_id=context.get('snapshot_id',data.get('snapshot_id')),
        history_snapshot_id=history.get('snapshot_id',data.get('snapshot_id')),
        missing_player_ids=missing,quarantined_player_ids=quarantined_players,
        quarantined_rows=quarantined_rows,quarantine_reason_counts=quarantine_reasons,
        changed_fixture_ids=changed,
        in_progress_fixture_ids=in_progress,odds_coverage=summary)

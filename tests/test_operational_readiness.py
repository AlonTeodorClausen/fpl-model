"""The deadline panel must describe actual source availability, not infer DNP."""
from datetime import datetime, timezone

import pytest


def sample():
    return dict(
        as_of_at='2026-10-14T20:00:00Z', snapshot_id='context-1',
        events=[dict(id=7,deadline_time='2026-10-17T10:00:00Z'),
                dict(id=8,deadline_time='2026-10-23T17:30:00Z')],
        fixtures=[dict(id=61,event=7,started=False,finished=False)],
        players=[dict(id=1)],histories=[dict(player_id=1,fixture_id=51)],
        coverage=dict(history_refresh_required=False,missing_response_players=[],
                      quarantined_rows=0,newly_started_fixture_ids=[],
                      newly_finished_fixture_ids=[],new_player_ids_without_history=[]),
        input_sources=dict(history=dict(snapshot_id='history-1',available_at='2026-10-14T19:00:00Z'),
                           official_context=dict(snapshot_id='context-1',available_at='2026-10-14T20:00:00Z')),
    )


def test_ready_state_has_official_deadline_and_distinct_source_ages():
    from fpl_model.readiness import assess_deadline_readiness
    result=assess_deadline_readiness(sample(),datetime(2026,10,15,8,tzinfo=timezone.utc))
    assert result['status']=='ready' and result['event']==7
    assert result['deadline_at']=='2026-10-17T10:00:00+00:00'
    assert result['context_age_hours']==12 and result['history_age_hours']==13
    assert result['reasons']==[]


def test_missing_histories_and_provisional_match_block_ready_without_inventing_zero():
    from fpl_model.readiness import assess_deadline_readiness
    data=sample();data['coverage'].update(history_refresh_required=True,
        missing_response_players=[2],newly_started_fixture_ids=[52])
    result=assess_deadline_readiness(data,datetime(2026,10,15,8,tzinfo=timezone.utc))
    assert result['status']=='blocked'
    assert 'history_refresh_required' in result['reasons']
    assert 'missing_player_histories' in result['reasons']
    assert result['missing_player_ids']==[2]
    assert result['changed_fixture_ids']==[52]


def test_stale_context_and_partial_odds_are_attention_not_false_blocker():
    from fpl_model.readiness import assess_deadline_readiness
    data=sample()
    result=assess_deadline_readiness(data,datetime(2026,10,16,8,tzinfo=timezone.utc),
        max_context_age_hours=24,odds_coverage=dict(usable=7,expected_fixtures=10))
    assert result['status']=='attention'
    assert result['reasons']==['context_stale','odds_fallback']
    assert result['odds_coverage']==dict(usable=7,expected_fixtures=10)
    assert result['context_age_hours']==36


def test_passed_deadline_and_naive_clock_never_report_ready():
    from fpl_model.readiness import assess_deadline_readiness
    data=sample();data['events']=data['events'][:1]
    result=assess_deadline_readiness(data,datetime(2026,10,18,tzinfo=timezone.utc))
    assert result['status']=='blocked' and 'no_future_deadline' in result['reasons']
    with pytest.raises(ValueError):assess_deadline_readiness(data,datetime(2026,10,15))

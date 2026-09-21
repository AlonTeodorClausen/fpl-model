"""Leakage boundaries use explicit synthetic source versions, never the network."""
import copy
import hashlib
import importlib
import importlib.util
import json

import pytest

from test_observation_selection import row


SEASON = '2026-2027'
BEFORE = '2026-09-14T12:00:00Z'
DEADLINE = '2026-09-18T17:30:00Z'
AFTER = '2026-09-21T12:00:00Z'


def module():
    assert importlib.util.find_spec('fpl_model.replay_readiness'), 'Replay readiness is not implemented'
    return importlib.import_module('fpl_model.replay_readiness')


def sources(snapshot='a', available=BEFORE, *, deadline=DEADLINE, history=None, team=1):
    payloads = [
        ('bootstrap', {'events': [{'id': 5, 'deadline_time': deadline}],
                       'elements': [{'id': 1, 'team': team}], 'teams': [{'id': 1}, {'id': 2}]}),
        ('fixtures', [{'id': 12, 'event': 5, 'team_h': 1, 'team_a': 2,
                       'kickoff_time': '2026-09-19T14:00:00Z'}]),
        ('history', {'history': [row()['official_history']] if history is None else history}),
    ]
    paths = ['bootstrap_static.json', 'fixtures.json', 'element_summary/1.json']
    return [dict(kind=kind, player_id=1 if kind == 'history' else None, payload=payload,
                 reference=dict(source='fpl_api', source_snapshot_id=snapshot,
                                relative_path='raw/fpl_api/' + path,
                                sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                                retrieved_at=available, available_at=available))
            for (kind, payload), path in zip(payloads, paths)]


def replay(src=None, rows=None, **kwargs):
    return module().build_replay(sources() if src is None else src,
                                 [row()] if rows is None else rows,
                                 season=SEASON, player_ids=[1], events=[5], **kwargs)['records'][0]


def target():
    r = row('later', AFTER, 'final', fixture_id=12, event=5,
            observation_id=SEASON + ':later:1:12')
    r['official_history'].update(fixture=12, round=5)
    return r


def test_prospective_ready_requires_pre_origin_sources_and_uses_asof_history():
    result = replay()
    assert result['readiness'] == 'ready'
    assert result['forecast_origin_at'] == '2026-09-18T17:30:00+00:00'
    assert result['inputs']['relevant_fixture_ids'] == [12]
    assert result['provenance_class'] == 'pre_origin_captured'
    assert result['inputs']['observations'][0]['observation_id'] == SEASON + ':a:1:11'
    assert result['inputs']['observations'][0]['label_state'] == 'provisional'
    assert result['targets'][0]['status'] == 'no_final_observation'
    info = module().information_for(result)
    assert 'targets' not in info and 'deadline_evidence' not in info
    info['relevant_fixture_ids'].append(999)
    assert result['inputs']['relevant_fixture_ids'] == [12]


def test_post_deadline_capture_is_explicitly_not_replayable():
    result = replay(sources('later', AFTER), [target()])
    assert result['readiness'] == 'not_replayable'
    assert result['provenance_class'] == 'lacking_pre_origin_provenance'
    assert 'lacking_pre_origin_provenance' in result['reasons']
    assert result['inputs']['observations'] == []
    assert result['inputs']['relevant_fixture_ids'] == []
    assert result['targets'][0]['observation']['observation_id'] == target()['observation_id']
    with pytest.raises(ValueError):
        module().information_for(result)


def test_future_snapshots_and_targets_do_not_change_information_or_readiness():
    before = replay()
    later_sources = sources('later', AFTER, team=2)
    # A future deadline revision and conflicting future observations cannot leak back.
    later_sources[0]['payload']['events'][0]['deadline_time'] = '2026-09-18T19:00:00Z'
    after = replay(sources() + later_sources, [row(), target()])
    for field in ('readiness', 'reasons', 'inputs', 'forecast_origin_at'):
        assert before[field] == after[field]
    assert after['targets'][0]['observation']['available_at'] == '2026-09-21T12:00:00+00:00'
    assert module().information_for(before) == module().information_for(after)
    historical = replay(sources('later', AFTER), [target()])
    expanded = replay(sources('later', AFTER) + sources('future', '2026-09-23T12:00:00Z'), [target()])
    assert historical['inputs'] == expanded['inputs']
    assert historical['readiness'] == expanded['readiness'] == 'not_replayable'


def test_conflicting_observations_block_readiness_independent_of_order():
    conflict = row('b', total_points=9)
    conflict['official_history']['total_points'] = 9
    for rows in ([row(), conflict], [conflict, row()]):
        result = replay(rows=rows)
        assert result['readiness'] == 'conflicted'
        assert 'conflicted_history_observation' in result['reasons']


def test_source_conflicts_block_ready_but_equivalent_ties_are_deterministic():
    a, b = sources('a'), sources('b')
    expected = replay(a + b)
    assert expected['readiness'] == 'ready'
    assert expected == replay(list(reversed(a + b)))
    conflict = sources('c', team=2)
    assert replay(a + conflict)['readiness'] == 'conflicted'


def test_missing_history_lacks_provenance_and_empty_captured_history_is_not_dnp():
    result = replay(sources()[:2], [])
    assert result['readiness'] == 'not_replayable'
    assert result['inputs']['requirements']['history']['status'] == 'missing'
    empty = replay(sources(history=[]), [])
    assert empty['readiness'] == 'ready'
    assert empty['inputs']['history_status'] == 'empty_observed_history'
    assert empty['inputs']['observations'] == []


def test_post_origin_history_cannot_fill_a_missing_pre_origin_input():
    result = replay(sources()[:2] + sources('late', AFTER)[2:], [target()])
    assert result['readiness'] == 'not_replayable'
    assert result['inputs']['requirements']['history']['reason'] == 'lacking_pre_origin_provenance'


def test_unknown_deadline_unresolved_and_naive_timestamps_rejected():
    src = sources()
    del src[0]['payload']['events'][0]['deadline_time']
    result = replay(src)
    assert result['forecast_origin_at'] is None and result['readiness'] == 'not_replayable'
    assert 'unresolved_official_deadline' in result['reasons']
    with pytest.raises(ValueError):
        replay(sources(deadline='2026-09-18T17:30:00'))
    with pytest.raises(ValueError):
        replay(sources(available='2026-09-14T12:00:00'))


def test_pre_origin_deadline_revision_requires_review_not_guessing():
    later = sources('b', '2026-09-15T12:00:00Z', deadline='2026-09-18T18:30:00Z')
    result = replay(sources() + later)
    assert result['readiness'] == 'partial'
    assert 'deadline_revision_requires_review' in result['reasons']


def test_quarantined_history_prevents_ready_without_inventing_zero():
    q = {**row(), 'requested_player_id': 1, 'label_state': 'unusable', 'reasons': ['invalid_minutes']}
    result = replay(rows=[], quarantine=[q])
    assert result['readiness'] == 'partial'
    assert 'quarantined_history' in result['reasons']
    assert not result['inputs']['observations']


def test_unknown_team_does_not_invent_fixture_membership():
    result = replay(sources(team=999))
    assert result['readiness'] == 'partial'
    assert result['inputs']['relevant_fixture_ids'] == []


def test_deadline_boundary_is_inclusive_and_mutations_cannot_bypass_accessor():
    result = replay(sources(available=DEADLINE), [])
    # A captured history with a row but no normalized version is unresolved.
    assert result['readiness'] == 'partial'
    good = replay(sources(available=DEADLINE, history=[]), [])
    assert good['readiness'] == 'ready'
    bad = copy.deepcopy(good)
    bad['inputs']['requirements']['history']['reference']['available_at'] = AFTER
    with pytest.raises(ValueError):
        module().information_for(bad)


def test_rescheduled_target_remains_attached_to_the_pre_origin_fixture():
    moved = target()
    moved['event'] = moved['official_history']['round'] = 6
    result = replay(rows=[row(), moved])
    assert result['targets'][0]['fixture_id'] == 12
    assert result['targets'][0]['observation']['event'] == 6
    assert result['inputs']['relevant_fixture_ids'] == [12]


def test_future_only_history_addition_does_not_change_missing_input_state():
    before = replay(sources()[:2], [])
    after = replay(sources()[:2] + sources('later', AFTER)[2:], [target()])
    for key in ('inputs', 'readiness', 'reasons'):
        assert before[key] == after[key]


def test_future_bad_deadline_cannot_poison_established_origin():
    later = sources('later', AFTER, deadline='not a timestamp')
    assert replay(sources() + later)['inputs'] == replay()['inputs']


def test_equal_time_official_deadline_conflict_is_unresolved():
    conflicting = sources('b', deadline='2026-09-18T18:00:00Z')
    result = replay(sources() + conflicting)
    assert result['readiness'] == 'conflicted'
    assert result['forecast_origin_at'] is None


def test_future_quarantine_cannot_change_pre_origin_history():
    q = {**row('later', AFTER), 'requested_player_id': 1, 'label_state': 'unusable'}
    assert replay(quarantine=[q]) == replay()


def test_later_target_conflicts_cannot_contaminate_ready_information():
    a = target()
    b = copy.deepcopy(a)
    b['total_points'] = b['official_history']['total_points'] = 99
    result = replay(rows=[row(), a, b])
    assert result['readiness'] == 'ready'
    assert result['targets'][0]['status'] == 'conflict'
    assert result['targets'][0]['observation'] is None
    assert result['inputs'] == replay()['inputs']


def test_newer_quarantine_blocks_final_target_without_changing_inputs():
    q = {**target(), 'label_state': 'unusable', 'requested_player_id': 1,
         'available_at': '2026-09-22T12:00:00Z', 'reasons': ['invalid_minutes']}
    result = replay(rows=[row(), target()], quarantine=[q])
    assert result['readiness'] == 'ready'
    assert result['targets'][0]['status'] == 'quarantined'
    assert result['targets'][0]['observation'] is None
    assert result['targets'][0]['historical_final_reference']['observation_id'] == target()['observation_id']


def test_dgw_schedule_keeps_both_fixture_references_without_inferred_dnp():
    src = sources()
    src[1]['payload'].append({**src[1]['payload'][0], 'id': 13})
    result = replay(src)
    assert result['readiness'] == 'ready'
    assert result['inputs']['relevant_fixture_ids'] == [12, 13]
    assert [t['status'] for t in result['targets']] == ['no_final_observation', 'no_final_observation']


def test_no_scheduled_fixture_is_unresolved_not_inferred_blank_gameweek():
    src = sources()
    src[1]['payload'] = []
    result = replay(src)
    assert result['readiness'] == 'partial'
    assert 'unresolved_empty_event_schedule' in result['reasons']


def test_all_source_and_observation_ordering_is_irrelevant():
    src = sources() + sources('later', AFTER)
    rows = [row(), target(), row('later', AFTER, 'final')]
    assert replay(src, rows) == replay(src[::-1], rows[::-1])

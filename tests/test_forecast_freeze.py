"""Phase-A contracts: explicit clocks, six players, no network or outcomes."""
import copy
import importlib
import importlib.util
import json
from datetime import timedelta

import pytest

from fpl_model.label_contracts import utc
from fpl_model.replay_readiness import build_replay
from test_replay_readiness import sources, row

PLAYERS = [1, 2, 5, 12, 26, 439]
START = '2026-09-18T17:10:00Z'
CREATED = '2026-09-18T17:11:00Z'
DEADLINE = '2026-09-18T17:30:00Z'


def module():
    assert importlib.util.find_spec('fpl_model.forecast_freeze'), 'Phase-A freeze contract missing'
    return importlib.import_module('fpl_model.forecast_freeze')


def replay():
    src = sources(available=START)
    src[0]['payload']['elements'] = [dict(id=p, team=1) for p in PLAYERS]
    rows = []
    for pid in PLAYERS:
        r = row(available=START, player_id=pid, observation_id=f'2026-2027:a:{pid}:11')
        r['official_history']['element'] = pid
        r['provenance'][0]['relative_path'] = f'raw/fpl_api/element_summary/{pid}.json'
        rows.append(r)
        h = copy.deepcopy(src[2])
        h.update(player_id=pid, payload={'history': [r['official_history']]})
        h['reference']['relative_path'] = f'raw/fpl_api/element_summary/{pid}.json'
        if pid == 1:
            src[2] = h
        else:
            src.append(h)
    return build_replay(src, rows, season='2026-2027', player_ids=PLAYERS, events=[5])


def prepare(r=None, **overrides):
    kwargs = dict(fresh_snapshot_id='a', capture_started_at=START, freeze_created_at=CREATED,
                  max_input_age=timedelta(minutes=30), deadline_versions=[], source_report={})
    kwargs.update(overrides)
    return module().prepare_freeze(replay() if r is None else r, **kwargs)


def test_pre_deadline_freeze_keeps_inputs_only_and_reports_ages():
    r = replay()
    r['records'][0]['targets'] = [{'purpose': 'outcome_only', 'secret_future_value': 99}]
    frozen = prepare(r)
    assert frozen['status'] == 'ready'
    assert frozen['player_ids'] == PLAYERS
    assert frozen['forecast_origin_at'] == '2026-09-18T17:30:00+00:00'
    assert frozen['freshness']['max_input_age_seconds'] == 1800
    assert {x['age_at_origin_seconds'] for x in frozen['freshness']['references']} == {1200}
    assert frozen['freshness']['passed']
    assert 'secret_future_value' not in json.dumps(frozen)
    assert '"targets"' not in json.dumps(frozen)
    assert frozen['handoff']['phase_b_status'] == 'not_started'
    assert len(frozen['handoff']['player_fixtures']) == 6


@pytest.mark.parametrize('created', [DEADLINE, '2026-09-18T17:31:00Z'])
def test_at_or_after_deadline_rejected(created):
    f = prepare(freeze_created_at=created)
    assert f['status'] == 'rejected'
    assert 'deadline_reached' in f['reasons']


def test_stale_but_pre_origin_is_rejected_without_changing_provenance_readiness():
    f = prepare(max_input_age=timedelta(minutes=10))
    assert f['status'] == 'rejected' and 'stale_inputs' in f['reasons']
    assert not f['freshness']['passed']
    assert all(p['readiness'] == 'ready' for p in f['players'])


@pytest.mark.parametrize('readiness', ['partial', 'conflicted', 'not_replayable'])
def test_non_ready_players_prevent_ready_freeze(readiness):
    r = replay()
    r['records'][0]['readiness'] = readiness
    r['records'][0]['reasons'] = ['synthetic_missing_or_conflicting_input']
    f = prepare(r)
    assert f['status'] == 'rejected' and f['players'][0]['readiness'] == readiness


def test_old_source_fallback_and_future_to_creation_references_rejected():
    f = prepare(fresh_snapshot_id='different')
    assert f['status'] == 'rejected' and 'not_fresh_capture' in f['reasons']
    f = prepare(freeze_created_at='2026-09-18T17:09:00Z')
    assert f['status'] == 'rejected'


def test_versions_preserve_old_and_new_deadline_and_selected_source():
    r = replay()
    old = copy.deepcopy(r['origins'][0]['deadline_evidence'])
    old['reference'].update(source_snapshot_id='old', retrieved_at='2026-09-17T12:00:00Z',
                            available_at='2026-09-17T12:00:00Z')
    old_version = dict(event=5, forecast_origin_at='2026-09-18T18:00:00Z', evidence=old)
    f = prepare(r, deadline_versions=[old_version])
    assert f['deadline']['revision_detected']
    assert len(f['deadline']['observations']) == 2
    assert f['deadline']['selected']['evidence']['reference']['source_snapshot_id'] == 'a'
    assert f['forecast_origin_at'] == '2026-09-18T17:30:00+00:00'
    assert f['status'] == 'ready'


def test_equal_time_deadline_conflict_rejected_instead_of_tiebreak():
    r = replay()
    old = dict(event=5, forecast_origin_at='2026-09-18T18:00:00Z', evidence=r['origins'][0]['deadline_evidence'])
    f = prepare(r, deadline_versions=[old])
    assert f['status'] == 'rejected' and 'conflicting_deadline_observations' in f['reasons']


def test_deterministic_content_and_new_immutable_destination_each_publication(tmp_path):
    m = module()
    a = prepare()
    r = replay()
    r['records'].reverse()
    b = prepare(r)
    assert a == b
    p = m.write_freeze(a, tmp_path, clock=lambda: utc(CREATED))
    original = {f.name: f.read_bytes() for f in p.iterdir()}
    q = m.write_freeze(b, tmp_path, clock=lambda: utc(CREATED))
    assert p != q
    assert (p / 'freeze.json').read_bytes() == (q / 'freeze.json').read_bytes()
    assert m.verify_freeze(p, verify_sources=False) == a
    assert {f.name: f.read_bytes() for f in p.iterdir()} == original
    (p / 'freeze.json').write_text('{}')
    with pytest.raises(ValueError):
        m.verify_freeze(p, verify_sources=False)


def test_publication_rechecks_clock_and_never_publishes_ready_after_deadline(tmp_path):
    m = module()
    with pytest.raises(ValueError):
        m.write_freeze(prepare(), tmp_path, clock=lambda: utc(DEADLINE))
    assert not list(tmp_path.glob('*/COMPLETE.json'))


def test_rejected_attempt_cannot_be_read_as_valid_freeze(tmp_path):
    m = module()
    f = prepare(max_input_age=timedelta(minutes=1))
    p = m.write_freeze(f, tmp_path, clock=lambda: utc(CREATED))
    with pytest.raises(ValueError):
        m.verify_freeze(p, verify_sources=False)
    assert m.verify_freeze(p, require_ready=False, verify_sources=False)['status'] == 'rejected'


def test_contaminated_information_section_is_rejected_not_serialized():
    r = replay()
    r['records'][0]['inputs']['targets'] = [{'future': 'must_not_escape'}]
    with pytest.raises(ValueError):
        prepare(r)


def test_only_exact_sample_and_aware_times_and_explicit_positive_freshness_allowed():
    r = replay()
    r['records'].pop()
    with pytest.raises(ValueError):
        prepare(r)
    with pytest.raises(ValueError):
        prepare(freeze_created_at='2026-09-18T17:11:00')
    with pytest.raises(ValueError):
        prepare(max_input_age=timedelta(0))


def test_deadline_crossed_during_publication_leaves_no_valid_completion(tmp_path):
    m = module()
    times = iter([utc(CREATED), utc(DEADLINE)])
    with pytest.raises(ValueError):
        m.write_freeze(prepare(), tmp_path, clock=lambda: next(times))
    assert list(tmp_path.glob('*/freeze.json'))
    assert not list(tmp_path.glob('*/COMPLETE.json'))
    for path in tmp_path.iterdir():
        with pytest.raises(ValueError):
            m.verify_freeze(path, verify_sources=False)


def test_publication_rejects_mutated_future_input_even_when_digest_recomputed(tmp_path):
    m = module()
    f = prepare()
    f['inputs'][0]['requirements']['history']['reference']['available_at'] = '2026-09-18T18:00:00Z'
    f['input_sha256'] = f['handoff']['input_sha256'] = m.digest(f['inputs'])
    with pytest.raises(ValueError):
        m.write_freeze(f, tmp_path, clock=lambda: utc(CREATED))


def test_freshness_boundary_exact_maximum_passes():
    assert prepare(max_input_age=timedelta(minutes=20))['status'] == 'ready'
    assert prepare(max_input_age=timedelta(minutes=20)-timedelta(microseconds=1))['status'] == 'rejected'


def test_writer_rechecks_creation_time_not_just_forecast_cutoff(tmp_path):
    m = module()
    f = prepare()
    f['inputs'][0]['requirements']['history']['reference']['available_at'] = '2026-09-18T17:20:00Z'
    f['input_sha256'] = f['handoff']['input_sha256'] = m.digest(f['inputs'])
    with pytest.raises(ValueError):
        m.write_freeze(f, tmp_path, clock=lambda: utc(CREATED))


def test_requirement_mapping_order_does_not_change_deterministic_payload():
    r = replay()
    r['records'][0]['inputs']['requirements'] = dict(reversed(list(r['records'][0]['inputs']['requirements'].items())))
    assert prepare(r) == prepare()

from datetime import datetime, timedelta, timezone

import pytest

from fpl_model.label_contracts import LabelState, ObservationTime, integer_id, label_state, utc

NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('value', ['88', '88.0', 88])
def test_identifiers_are_lossless(value):
    assert integer_id(value) == 88


@pytest.mark.parametrize('value', [True, False, 0, -1, '88.5', '', None, 'NaN', 'Infinity'])
def test_invalid_identifiers_rejected(value):
    with pytest.raises(ValueError):
        integer_id(value)


def test_time_requires_timezone_and_strict_forecast_cutoff():
    with pytest.raises(ValueError):
        utc('2026-09-14T12:00:00')
    observation = ObservationTime(NOW - timedelta(days=10), NOW, NOW)
    assert not observation.eligible_at(NOW)
    assert observation.eligible_at(NOW + timedelta(microseconds=1))
    assert utc('2026-09-14T14:00:00+02:00') == NOW
    with pytest.raises(ValueError):
        ObservationTime(NOW, NOW, NOW - timedelta(days=1))


def test_publication_requires_evidence_but_never_automatically_backdates():
    published = NOW - timedelta(days=1)
    with pytest.raises(ValueError):
        ObservationTime(None, NOW, NOW, published)
    with pytest.raises(ValueError):
        ObservationTime(None, NOW, NOW, NOW + timedelta(hours=1), 'documented')
    value = ObservationTime(None, NOW, NOW, published, 'documented publication semantics')
    assert not value.eligible_at(published + timedelta(hours=1))


@pytest.fixture
def label():
    history = dict(element=1, fixture=31, round=4, opponent_team=2, was_home=True,
                   kickoff_time='2026-09-12T14:00:00Z', minutes=90, starts=1, total_points=2)
    fixture = dict(id=31, event=4, team_h=1, team_a=2, kickoff_time=history['kickoff_time'], started=True, finished=True)
    event = dict(id=4, finished=True, data_checked=True)
    return history, fixture, event


def test_finality_needs_fixture_and_checked_event(label):
    h, f, e = label
    assert label_state(h, f, e, element_id=1)[0] == LabelState.FINAL
    assert label_state(h, {**f, 'finished': False, 'finished_provisional': True}, e, element_id=1)[0] == LabelState.PROVISIONAL
    assert label_state(h, f, {**e, 'finished': False}, element_id=1)[0] == LabelState.PROVISIONAL
    assert label_state(h, f, {**e, 'data_checked': False}, element_id=1)[0] == LabelState.PROVISIONAL


def test_zero_minutes_and_negative_points_are_not_missing(label):
    h, f, e = label
    assert label_state({**h, 'minutes': 0, 'starts': 0, 'total_points': -1}, f, e, element_id=1)[0] == LabelState.FINAL
    assert label_state(None, f, e, element_id=1)[0] == LabelState.UNUSABLE


@pytest.mark.parametrize('change', [dict(element=2), dict(fixture=99), dict(round=3), dict(opponent_team=1),
                                   dict(was_home='True'), dict(minutes=None), dict(minutes=True), dict(minutes=-1),
                                   dict(total_points=None), dict(starts=2), dict(kickoff_time='2026-09-12T15:00:00Z')])
def test_invalid_label_context_is_unusable(label, change):
    h, f, e = label
    assert label_state({**h, **change}, f, e, element_id=1)[0] == LabelState.UNUSABLE


def test_postponed_and_double_gameweek_fixtures_are_separate(label):
    h, f, e = label
    assert label_state(h, {**f, 'event': None, 'kickoff_time': None}, e, element_id=1)[0] == LabelState.UNUSABLE
    assert label_state(h, {**f, 'started': False}, e, element_id=1)[0] == LabelState.UNUSABLE
    # A second fixture in the same event needs its own history row and state.
    assert label_state(h, {**f, 'id': 41}, e, element_id=1)[0] == LabelState.UNUSABLE
    assert label_state({**h, 'fixture': 41}, {**f, 'id': 41}, e, element_id=1)[0] == LabelState.FINAL

"""Synthetic contracts, not evidence of live DGW/transfer/postponement behaviour."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fpl_model.io import SnapshotWriter
from fpl_model import player_fixture_labels as labels

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
CASES = json.loads((Path(__file__).parent/'fixtures/player_fixture_labels/contract_cases.json').read_text())['cases']
BASE = dict(element=1, fixture=11, round=4, was_home=True, opponent_team=2,
            kickoff_time='2026-09-12T14:00:00Z', minutes=90, starts=1, total_points=6,
            goals_scored=0, assists=0, clean_sheets=1, goals_conceded=0, own_goals=0,
            penalties_saved=0, penalties_missed=0, yellow_cards=0, red_cards=0, saves=1,
            bonus=0, bps=24, influence='30.0', creativity='0.0', threat='0.0', ict_index='3.0',
            expected_goals='0.00', expected_assists='0.01', expected_goal_involvements='0.01',
            expected_goals_conceded='0.20', clearances_blocks_interceptions=2, recoveries=3,
            tackles=0, defensive_contribution=5)


def snapshot(tmp_path, case=None, *, now=NOW, later_context=False):
    case = case or {'history':[{}]}
    clock_time = [now]
    writer = SnapshotWriter(tmp_path/'raw', clock=lambda: clock_time[0])
    writer.set_run_metadata({'season':'2026-2027'})
    fixture = dict(id=11, event=4, team_h=1, team_a=2, kickoff_time=BASE['kickoff_time'], started=True, finished=True)
    fixture.update(case.get('fixture_patch', {}))
    fixtures=[fixture]
    if 'extra_fixture' in case: fixtures.append({**fixture, **case['extra_fixture']})
    if case.get('duplicate_fixture'): fixtures.append(dict(fixture))
    event = dict(id=4, finished=True, data_checked=True)
    event.update(case.get('event_patch',{}))
    bootstrap = dict(elements=[dict(id=1,code=100,team=case.get('current_team',1),element_type=1)],
                     teams=[dict(id=i) for i in (1,2,3)],events=[event])
    if 'extra_event' in case:
        bootstrap['events'].append({**event, **case['extra_event']})
    if case.get('unknown_player'): bootstrap['elements']=[]
    history=[{**BASE,**patch} for patch in case['history']]
    for row in history:
        for field in case.get('omit_fields', []):
            row.pop(field, None)
    body=json.dumps({'history':history,'fixtures':[],'history_past':[]},ensure_ascii=False).encode()
    def raw(name, data, when, context=None):
        clock_time[0] = when
        writer.write_raw('fpl_api/'+name,data,source='fpl_api',required=True,
                         request_started_at=when,retrieved_at=when,available_at=when,
                         http_status=200,request_context=context or {})
    raw('element_summary/1.json',body,now,{'element_id':'1'})
    context_time=now+timedelta(minutes=5) if later_context else now
    raw('bootstrap_static.json',json.dumps(bootstrap).encode(),context_time)
    raw('fixtures.json',json.dumps(fixtures).encode(),context_time)
    return writer.finalize()


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['name'])
def test_contract_edge_cases(tmp_path,case):
    result=labels.normalize_snapshot(snapshot(tmp_path,case),season='2026-2027',element_ids=[1])
    assert len(result['labels'])==case['want_rows']
    assert [r['label_state'] for r in result['labels']]==case['want_states']
    assert len(result['quarantine'])==case.get('want_quarantine',0)
    if 'want_teams' in case: assert [r['team_id'] for r in result['labels']]==case['want_teams']
    if not case['history']: assert result['quality']['players'][0]['history_rows']==0


def test_schema_values_and_time_do_not_recalculate_or_backdate(tmp_path):
    path=snapshot(tmp_path,later_context=True)
    row=labels.normalize_snapshot(path,season='2026-2027',element_ids=[1])['labels'][0]
    assert row['player_id']==1 and row['fixture_id']==11 and row['team_id']==1 and row['opponent_team_id']==2
    assert row['event']==4 and row['was_home'] is True
    assert row['expected_assists']=='0.01' and row['total_points']==6
    assert row['official_history']==BASE
    assert row['retrieved_at']=='2026-09-21T12:00:00.000000+00:00'
    assert row['available_at']=='2026-09-21T12:05:00+00:00'
    assert row['source_published_at'] is None
    assert len(row['provenance'])==3 and all(p['sha256'] for p in row['provenance'])


@pytest.mark.parametrize('patch', [dict(element=2),dict(opponent_team=3),dict(fixture=99),dict(was_home='true'),dict(minutes=None),dict(starts='1'),dict(expected_goals='NaN'),dict(goals_scored='1'),dict(total_points=True),dict(kickoff_time='2026-09-12T14:00:00')])
def test_invalid_context_or_value_is_quarantined(tmp_path,patch):
    result=labels.normalize_snapshot(snapshot(tmp_path,{'history':[patch]}),season='2026-2027',element_ids=[1])
    assert result['labels']==[] and len(result['quarantine'])==1
    q=result['quarantine'][0]
    assert q['label_state']=='unusable' and q['reasons'] and q['official_history']=={**BASE,**patch}


def test_unknown_optional_fields_and_absence_stay_distinct(tmp_path):
    path=snapshot(tmp_path,{'history':[{'provider_extension':'kept','saves':None}]})
    result=labels.normalize_snapshot(path,season='2026-2027',element_ids=[1])
    assert result['labels'][0]['saves'] is None
    assert result['labels'][0]['official_history']['provider_extension']=='kept'
    assert 'saves' in result['labels'][0]['null_fields']


def test_absent_optional_stat_is_not_a_zero(tmp_path):
    result=labels.normalize_snapshot(snapshot(tmp_path,{'history':[{}], 'omit_fields':['expected_goals','starts']}),season='2026-2027',element_ids=[1])
    row=result['labels'][0]
    assert row['label_state']=='final' and row['starts'] is None and row['expected_goals'] is None
    assert set(row['missing_fields'])=={'starts','expected_goals'} and row['null_fields']==[]


def test_unknown_canonical_player_is_quarantined(tmp_path):
    result=labels.normalize_snapshot(snapshot(tmp_path,{'history':[{}], 'unknown_player':True}),season='2026-2027',element_ids=[1])
    assert not result['labels'] and 'unknown_player_id' in result['quarantine'][0]['reasons']


def test_reschedule_keeps_each_observed_event_and_date(tmp_path):
    earlier=snapshot(tmp_path)
    moved=next(c for c in CASES if c['name']=='rescheduled_consistently')
    later=snapshot(tmp_path,moved,now=NOW+timedelta(days=1))
    a=labels.normalize_snapshot(earlier,season='2026-2027',element_ids=[1])['labels'][0]
    b=labels.normalize_snapshot(later,season='2026-2027',element_ids=[1])['labels'][0]
    assert a['fixture_id']==b['fixture_id']==11
    assert a['event']==4 and b['event']==5
    assert a['kickoff_time']=='2026-09-12T14:00:00Z' and b['kickoff_time']=='2026-09-20T14:00:00Z'
    assert a['observation_id']!=b['observation_id']


def test_duplicate_rows_quarantined_together_not_last_wins(tmp_path):
    result=labels.normalize_snapshot(snapshot(tmp_path,{'history':[{},{}]}),season='2026-2027',element_ids=[1])
    assert result['labels']==[] and len(result['quarantine'])==2
    assert all('duplicate_player_fixture' in q['reasons'] for q in result['quarantine'])


def test_ambiguous_global_context_rejected(tmp_path):
    with pytest.raises(ValueError):
        labels.normalize_snapshot(snapshot(tmp_path,{'history':[{}],'duplicate_fixture':True}),season='2026-2027',element_ids=[1])


def test_missing_capture_is_not_an_empty_history(tmp_path):
    with pytest.raises(ValueError):
        labels.normalize_snapshot(snapshot(tmp_path),season='2026-2027',element_ids=[1,2])


def test_versions_preserve_provisional_and_final_observations(tmp_path):
    first=snapshot(tmp_path,{'history':[{}],'event_patch':{'data_checked':False}})
    second=snapshot(tmp_path,now=NOW+timedelta(days=1))
    a=labels.normalize_snapshot(first,season='2026-2027',element_ids=[1]);b=labels.normalize_snapshot(second,season='2026-2027',element_ids=[1])
    assert a['labels'][0]['label_state']=='provisional' and b['labels'][0]['label_state']=='final'
    assert a['labels'][0]['observation_id']!=b['labels'][0]['observation_id']
    assert a['labels'][0]['fixture_id']==b['labels'][0]['fixture_id']==11
    original={p:p.read_bytes() for root in (first,second) for p in root.rglob('*') if p.is_file()}
    out=labels.write_report(a,tmp_path/'audits')
    before={p.name:p.read_bytes() for p in out.iterdir() if p.is_file()}
    labels.write_report(b,tmp_path/'audits')
    assert before=={p.name:p.read_bytes() for p in out.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):labels.write_report(a,tmp_path/'audits')
    other=labels.write_report(a,tmp_path/'reproduced')
    assert before=={p.name:p.read_bytes() for p in other.iterdir() if p.is_file()}
    assert original=={p:p.read_bytes() for root in (first,second) for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):labels.write_report(a,first/'artifacts')

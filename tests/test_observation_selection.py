"""Synthetic observation contracts; no network or inferred participation."""
import copy
import importlib
import importlib.util
import itertools

import pytest


def module():
    assert importlib.util.find_spec('fpl_model.observation_selection') is not None, 'Step 2D selectors are not implemented'
    return importlib.import_module('fpl_model.observation_selection')


def row(snapshot='a', available='2026-09-14T12:00:00Z', state='provisional', **changes):
    h=dict(element=1,fixture=11,round=4,opponent_team=2,was_home=True,kickoff_time='2026-09-12T14:00:00Z',minutes=90,total_points=6)
    r=dict(season='2026-2027',source='fpl_api',source_snapshot_id=snapshot,
           observation_id=f'2026-2027:{snapshot}:1:11',player_id=1,fixture_id=11,
           event=4,team_id=1,opponent_team_id=2,was_home=True,kickoff_time=h['kickoff_time'],
           minutes=90,total_points=6,label_state=state,retrieved_at=available,available_at=available,
           source_history_index=0,official_history=h,
           provenance=[dict(source='fpl_api',relative_path='raw/fpl_api/element_summary/1.json',sha256='a'*64,retrieved_at=available)])
    r.update(changes)
    return r


def asof(rows, cutoff='2026-09-14T12:00:00Z', **kwargs):
    return module().select_as_of(rows,season='2026-2027',player_id=1,fixture_id=11,cutoff_at=cutoff,**kwargs)


def outcome(rows, **kwargs):
    return module().select_outcome(rows,season='2026-2027',player_id=1,fixture_id=11,**kwargs)


def test_inclusive_aware_cutoff_and_future_invariance():
    old=row();future=row('b','2026-09-21T12:00:00Z','final')
    original=copy.deepcopy([old,future])
    result=asof([old]);assert result.status=='selected' and result.observation==old
    assert asof([future,old])==result
    assert asof([old],cutoff='2026-09-14T14:00:00+02:00')==result
    assert asof([future]).status=='no_eligible_observation'
    assert [old,future]==original
    for cutoff in ['2026-09-14T12:00:00',None]:
        with pytest.raises(ValueError):asof([old],cutoff=cutoff)


def test_late_final_is_outcome_only_and_cannot_be_used_as_information():
    future=row('b','2026-09-21T12:00:00Z','final')
    selected=outcome([future])
    assert selected.status=='selected' and selected.purpose=='outcome_only'
    assert asof([future]).observation is None
    with pytest.raises(ValueError):selected.for_information()
    assert asof([row()]).for_information()==row()
    assert outcome([future],outcome_cutoff_at='2026-09-14T12:00:00Z').status=='no_final_observation'


def test_future_conflicts_cannot_change_past_selection():
    future=row('b','2026-09-21T12:00:00Z','final')
    conflicting={**future,'total_points':99,'official_history':{**future['official_history'],'total_points':99}}
    assert asof([row(),future,conflicting])==asof([row()])
    assert outcome([row(),future,conflicting]).status=='conflict'


def test_allowed_states_do_not_hide_same_version_conflict():
    assert asof([row()],allowed_states={'final'}).status=='no_allowed_state'
    conflict=row(state='final')
    assert asof([row(),conflict],allowed_states={'final'}).status=='conflict'
    with pytest.raises(ValueError):asof([row()],allowed_states={'unusable'})


def test_equal_time_equivalence_uses_provenance_and_reports_ties():
    a,b=row('a'),row('b')
    expected=asof([a,b])
    assert expected.observation['source_snapshot_id']=='b' and len(expected.tie_versions)==2
    assert asof([b,a])==expected
    duplicated=asof([a,a])
    assert duplicated.observation==a and duplicated.duplicate_versions


@pytest.mark.parametrize('same_version',[True,False])
def test_equal_time_conflicting_values_fail_regardless_of_order(same_version):
    a=row();b=row('a' if same_version else 'b',total_points=8)
    b['official_history']={**b['official_history'],'total_points':8}
    for rows in itertools.permutations([a,b]):
        result=asof(rows)
        assert result.status=='conflict' and result.observation is None


def test_inconsistent_same_version_provenance_and_backdating_rejected():
    a=row();b=row(provenance=[{**a['provenance'][0],'sha256':'b'*64}])
    assert asof([a,b]).status=='conflict'
    with pytest.raises(ValueError):asof([row(retrieved_at='2026-09-21T12:00:00Z')])
    with pytest.raises(ValueError):asof([row(source='fpl_core')])
    with pytest.raises(ValueError):asof([row(team_id=True)])


def test_latest_final_revision_and_earlier_provisional_remain_auditable():
    a=row();b=row('b','2026-09-21T12:00:00Z','final')
    c=row('c','2026-09-22T12:00:00Z','final',total_points=7)
    c['official_history']={**c['official_history'],'total_points':7}
    assert outcome([c,a,b]).observation==c
    assert len(outcome([a,b,c]).eligible_versions)==2
    assert asof([a,b,c]).observation==a
    transitions=module().transition_audit([c,a,b])
    assert not transitions['issues'] and len(transitions['transitions'])==2
    first,last=transitions['transitions']
    assert (first['earlier_state'],first['later_state'])==('provisional','final')
    assert last['changed_fields']['total_points']['earlier']==6
    assert last['changed_fields']['total_points']['later']==7
    assert last['classification']=='official_revision'


def test_quarantine_missing_provisional_and_explicit_zero_are_distinct():
    m=module();q={**row(),'label_state':'unusable','requested_player_id':1,'reasons':['duplicate_player_fixture']}
    q.pop('player_id');q.pop('fixture_id')
    u=[dict(player_id=1,fixture_id=11,expectation='expected',evidence=['explicit test contract'])]
    def audit(rows,quarantine=()):
        return m.completeness_audit(u,rows,quarantine=quarantine,season='2026-2027',purpose='as_of',cutoff_at='2026-09-14T12:00:00Z')['pairs'][0]
    assert audit([])['classification']=='missing_observation'
    assert audit([row()])['classification']=='provisional'
    assert audit([], [q])['classification']=='quarantined'
    z=row(state='final',minutes=0);z['official_history']={**z['official_history'],'minutes':0}
    zero=audit([z]);assert zero['classification']=='final' and zero['appearance']=='explicit_zero'
    futureq={**q,'available_at':'2026-09-22T12:00:00Z','retrieved_at':'2026-09-22T12:00:00Z'}
    assert audit([], [futureq])==audit([])


def test_fixture_universe_does_not_expand_current_or_historical_clubs():
    m=module()
    fixtures=[dict(id=11,team_h=1,team_a=2),dict(id=12,team_h=1,team_a=2),dict(id=13,team_h=2,team_a=3)]
    players=[dict(id=1,team=3)] # current team does not prove membership for any past date
    u=m.fixture_universe(season='2026-2027',players=players,teams=[dict(id=i) for i in (1,2,3)],fixtures=fixtures,
        pairs=[(1,11),(1,12),(1,13)],observations=[row()],context_available_at='2026-09-14T12:00:00Z')
    assert [p['expectation'] for p in u]==['expected','unresolved','unresolved']
    past=m.fixture_universe(season='2026-2027',players=players,teams=[dict(id=i) for i in (1,2,3)],fixtures=fixtures,
        pairs=[(1,11)],observations=[row()],context_available_at='2026-09-14T12:00:00Z',cutoff_at='2026-09-13T12:00:00Z')
    assert past[0]['expectation']=='unresolved'


def test_season_scope_and_provenance_availability_are_enforced():
    other=row(season='2025-2026',observation_id='2025-2026:a:1:11')
    assert asof([other]).status=='no_eligible_observation'
    late_context=row(provenance=[{**row()['provenance'][0], 'effective_available_at':'2026-09-21T12:00:00Z'}])
    with pytest.raises(ValueError):asof([late_context])
    future=row('b','2026-09-21T12:00:00Z',provenance=[])
    assert asof([row(),future])==asof([row()])


def test_provisional_zero_remains_visible_without_becoming_an_outcome():
    z=row(minutes=0);z['official_history']={**z['official_history'],'minutes':0}
    u=[dict(player_id=1,fixture_id=11,expectation='expected',evidence=['contract'])]
    p=module().completeness_audit(u,[z],season='2026-2027',purpose='outcome')['pairs'][0]
    assert p['classification']=='provisional' and p['appearance']=='explicit_zero'
    assert p['selection_status']=='no_final_observation' and p['selected_version'] is None


def test_future_expectation_evidence_does_not_establish_past_completeness():
    u=[dict(player_id=1,fixture_id=11,expectation='expected',evidence=['later history'],expectation_available_at='2026-09-21T12:00:00Z')]
    p=module().completeness_audit(u,[],season='2026-2027',purpose='as_of',cutoff_at='2026-09-14T12:00:00Z')['pairs'][0]
    assert p['classification']=='unresolved_expectation'


@pytest.mark.parametrize('field', ['available_at','retrieved_at'])
def test_naive_observation_timestamps_are_rejected(field):
    with pytest.raises(ValueError):asof([row(**{field:'2026-09-14T12:00:00'})])


def test_latest_allowed_as_of_version_wins_at_inclusive_boundary():
    a=row();b=row('b','2026-09-21T12:00:00Z','final')
    c=row('c','2026-09-22T12:00:00Z','provisional')
    assert asof([c,a,b],cutoff='2026-09-22T12:00:00Z').observation==c
    assert asof([c,a,b],cutoff='2026-09-22T12:00:00Z',allowed_states={'final'}).observation==b
    assert outcome([c,a,b]).observation==b


def test_result_and_information_access_do_not_mutate_source_versions():
    source=row()
    result=asof([source])
    exposed=result.for_information()
    exposed['official_history']['total_points']=99
    assert source['official_history']['total_points']==6
    assert result.observation['official_history']['total_points']==6

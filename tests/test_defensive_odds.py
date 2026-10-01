"""Defensive-only odds: no guessed identities, future prices, or attack changes."""
import copy
import importlib.util
import numpy as np
import pytest
from test_history_coverage_evaluation import history_data
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate


def odds_module():
    assert importlib.util.find_spec('fpl_model.defensive_odds'), 'odds integration missing'
    from fpl_model import defensive_odds
    return defensive_odds


def test_margin_removal_and_poisson_fit_recover_known_rates():
    m=odds_module()
    probs,margin=m.remove_margin([2,3,4])
    assert sum(probs)==pytest.approx(1) and probs==pytest.approx([6/13,4/13,3/13])
    assert margin==pytest.approx(1/2+1/3+1/4-1)
    for invalid in ([1,2,3],[0,2,3],[float('nan'),2,3]):
        with pytest.raises(ValueError): m.remove_margin(invalid)
    p=m.goal_probabilities(1.8,.8)
    row=dict(zip(m.COLUMNS,[1/(p[k]*1.04) for k in m.PROB_KEYS]))
    result=m.fit_market(row)
    assert result['home_goals']==pytest.approx(1.8,abs=1e-5)
    assert result['away_goals']==pytest.approx(.8,abs=1e-5)
    assert result['max_probability_error']<1e-6
    assert result['home_clean_sheet']==pytest.approx(np.exp(-.8))
    with pytest.raises(ValueError): m.fit_market({})
    with pytest.raises(ValueError): m.fit_market(dict(zip(m.COLUMNS,[50,1.02,50,1.02,50])))


def match_context():
    return [dict(id=1,name='Man Utd'),dict(id=2,name='Spurs')],[dict(id=9,team_h=1,team_a=2,event=6,kickoff_time='2026-10-10T16:30:00Z')]


def test_exact_alias_and_london_kickoff_matching_rejects_unknown_ambiguous_and_dst():
    m=odds_module();teams,fixtures=match_context()
    row=dict(Div='E0',Date='10/10/2026',Time='17:30',HomeTeam='Man United',AwayTeam='Tottenham')
    assert m.match_fixture(row,teams,fixtures)['fixture_id']==9
    for bad in ({**row,'HomeTeam':'United'}, {**row,'Time':'16:30'}, {**row,'HomeTeam':'Tottenham','AwayTeam':'Man United'}):
        assert m.match_fixture(bad,teams,fixtures)['status']!='matched'
    assert m.match_fixture(row,teams,fixtures+[dict(fixtures[0],id=10)])['status']=='ambiguous_fixture'
    for date in ('29/03/2026','25/10/2026'):
        assert m.match_fixture({**row,'Date':date,'Time':'01:30'},teams,fixtures)['status']=='invalid_kickoff'


def coverage_data():
    d=history_data();d['teams']=[dict(id=1,name='Man Utd'),dict(id=2,name='Spurs')]
    f=d['fixtures'][-1]
    r=dict(Div='E0',Date='10/09/2026',Time='15:00',HomeTeam='Man United',AwayTeam='Tottenham',
           B365H='2.0',B365D='3.5',B365A='4.0',**{'B365>2.5':'1.9','B365<2.5':'1.9'})
    source=dict(available_at='2026-09-09T11:00:00Z',retrieved_at='2026-09-09T11:00:00Z',
                source_published_at=None,raw_path='raw/fixtures.csv',sha256='a'*64)
    return d,r,source


def test_coverage_deadline_cutoff_invalid_markets_and_duplicate_rows():
    m=odds_module();d,r,source=coverage_data()
    a=m.build_coverage(d,[r],source,5,BaselineConfig(),d['as_of_at'])
    assert a['usable']==1 and a['fixtures'][0]['status']=='odds'
    for later in ('2026-09-09T13:00:00Z','2026-09-10T12:30:00Z'):
        b=m.build_coverage(d,[r],{**source,'available_at':later},5,BaselineConfig(),d['as_of_at'])
        assert b['usable']==0 and b['fixtures'][0]['status']=='baseline_fallback'
    for rows in ([],[dict(r,B365H='')],[r,r]):
        b=m.build_coverage(d,rows,source,5,BaselineConfig(),d['as_of_at'])
        assert b['usable']==0 and b['fixtures'][0]['reason']
    later_origin='2026-09-10T12:30:00Z'
    b=m.build_coverage(d,[r],{**source,'available_at':later_origin},5,BaselineConfig(),later_origin)
    assert b['usable']==0 # equal deadline is too late for odds


def test_only_concession_components_change_and_fallback_is_bit_identical():
    m=odds_module();d,r,source=coverage_data();cfg=BaselineConfig()
    a=simulate(d,5,cfg,draws=1000,seed=42)
    cover=m.build_coverage(d,[r],source,5,cfg,d['as_of_at'])
    b=simulate(d,5,cfg,draws=1000,seed=42,defensive_odds=cover)
    np.testing.assert_array_equal(a.minutes,b.minutes)
    for pid in a.explanations:
        ea,eb=a.explanations[pid],b.explanations[pid]
        for key in ea['point_components']:
            if key not in ('clean_sheets','goals_conceded'):
                assert ea['point_components'][key]==eb['point_components'][key]
        assert ea['fixtures']==eb['fixtures'] # offensive factors remain unchanged
    assert not np.array_equal(a.points,b.points)
    c=simulate(d,5,cfg,draws=1000,seed=42,defensive_odds=m.build_coverage(d,[],source,5,cfg,d['as_of_at']))
    np.testing.assert_array_equal(a.points,c.points)
    with pytest.raises(ValueError,match='historical'):
        simulate(d,5,cfg,draws=100,seed=42,retrospective=True,defensive_odds=cover)
    future=copy.deepcopy(cover);future['source']['available_at']='2026-09-10T13:00:00Z'
    with pytest.raises(ValueError):simulate(d,5,cfg,draws=100,seed=42,defensive_odds=future)


def test_comparison_keeps_baseline_default_and_skips_historical_evaluation(monkeypatch):
    from fpl_model import prototype
    m=odds_module();d,r,source=coverage_data()
    def forbidden(*a,**k):raise AssertionError('Do not evaluate historical rows with new odds')
    monkeypatch.setattr(prototype,'evaluate_sample',forbidden)
    assert importlib.util.find_spec('fpl_model.odds_comparison')
    from fpl_model.odds_comparison import compare_forecasts
    cfg=BaselineConfig();c=m.build_coverage(d,[r],source,5,cfg,d['as_of_at'])
    result=compare_forecasts(d,c,cfg,draws=100,seed=42,budget=100)
    assert result['baseline']['model_version']=='component_baseline_v1'
    assert result['odds_variant']['model_version']=='component_defensive_odds_v1'
    assert result['baseline']['evaluation']['status']=='not_run'
    assert result['odds_variant']['defensive_odds']['source']==source
    assert result['default_model_changed'] is False
    for row in result['player_changes']:
        assert row['xp_delta']==pytest.approx(row['defensive_points_delta'])
        assert row['minutes_delta']==0


def test_raw_snapshot_loading_preserves_provenance_and_excludes_invalid_200(tmp_path):
    from datetime import datetime,timezone
    from fpl_model.io import SnapshotWriter
    from fpl_model.odds_comparison import load_odds
    now=datetime.now(timezone.utc);w=SnapshotWriter(tmp_path/'raw')
    body=b'\xef\xbb\xbfDiv,Date,Time,HomeTeam,AwayTeam\r\nE0,10/10/2026,17:30,Man United,Tottenham\r\n'
    w.write_raw('football_data_uk/attempt_01/fixtures.csv',body,source='football_data_uk',required=False,
        request_started_at=now,retrieved_at=now,available_at=now,http_status=200,content_type='text/csv')
    p=w.finalize();rows,source=load_odds(p)
    assert rows[0]['Div']=='E0' and source['source_published_at'] is None
    assert source['available_at']==source['retrieved_at'] and source['sha256']
    assert (p/source['raw_path']).read_bytes()==body
    w=SnapshotWriter(tmp_path/'raw');now=datetime.now(timezone.utc)
    w.write_raw('football_data_uk/attempt_01/fixtures.csv',b'<html>',source='football_data_uk',required=False,
        request_started_at=now,retrieved_at=now,http_status=200)
    w.record_failure(source='football_data_uk',required=False,request_started_at=now,
        relative_path='raw/football_data_uk/attempt_01/fixtures.csv',error_code='invalid_payload')
    rows,source=load_odds(w.finalize())
    assert rows==[] and source['failure']=='no_unique_valid_odds_response'


def test_updated_fixture_context_cannot_reuse_a_prepared_match():
    m=odds_module();d,r,source=coverage_data();cfg=BaselineConfig()
    cover=m.build_coverage(d,[r],source,5,cfg,d['as_of_at'])
    changed=copy.deepcopy(d);changed['fixtures'][-1]['kickoff_time']='2026-09-10T15:00:00Z'
    with pytest.raises(ValueError,match='fixture'):
        simulate(changed,5,cfg,draws=100,seed=42,defensive_odds=cover)


def test_failed_fit_is_explicit_baseline_fallback(monkeypatch):
    m=odds_module();d,r,source=coverage_data()
    def fail(*a,**k):raise RuntimeError('solver failed')
    monkeypatch.setattr(m,'least_squares',fail)
    cover=m.build_coverage(d,[r],source,5,BaselineConfig(),d['as_of_at'])
    assert cover['usable']==0 and cover['fixtures'][0]['reason']=='poisson_fit_failed'


def test_odds_report_cannot_mislabel_a_baseline_historical_evaluation():
    from fpl_model.prototype import run_prototype
    m=odds_module();d,r,source=coverage_data();cfg=BaselineConfig()
    c=m.build_coverage(d,[r],source,5,cfg,d['as_of_at'])
    with pytest.raises(ValueError,match='historical'):
        run_prototype(d,5,cfg,draws=100,seed=42,defensive_odds=c)

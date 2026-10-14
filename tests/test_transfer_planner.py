import copy
import importlib
import importlib.util
import json

import numpy as np
import pytest
from test_prototype import data
from test_my_team import profile
from fpl_model.models.baseline import BaselineConfig


def mod():
    assert importlib.util.find_spec('fpl_model.transfer_planner'), 'forecast/transfer service missing'
    return importlib.import_module('fpl_model.transfer_planner')


def context():
    d=data();d['season']='2026-2027';d['manifest_sha256']='example'
    d['events'].append(dict(id=6,deadline_time='2026-09-17T12:30:00Z'))
    d['fixtures'].append(dict(d['fixtures'][-1],id=6,event=6,kickoff_time='2026-09-17T14:00:00Z'))
    return d


def bundle(tmp_path, **kwargs):
    return mod().forecast_bundle(context(),[5,6],BaselineConfig(),origin_at='2026-09-09T13:00:00Z',
                                 cache_root=tmp_path,draws=100,seed=42,**kwargs)


def test_bundle_cache_and_shared_scenarios(tmp_path,monkeypatch):
    m=mod();b=bundle(tmp_path)
    # A second request for the exact inputs must not simulate anything.
    def forbidden(*a,**k):raise AssertionError('recomputed forecasts')
    monkeypatch.setattr(m,'simulate',forbidden)
    cached=bundle(tmp_path)
    assert cached['cache_key']==b['cache_key']
    assert np.array_equal(cached['scenarios'][5]['points'],b['scenarios'][5]['points'])
    p=profile();before=copy.deepcopy(p)
    report=m.compare_packages(cached,p,max_transfers=1,locked=[1])
    assert p==before
    hold=report['packages'][0]
    assert hold['count']==0 and hold['total_gain']==0 and hold['next_gw_gain']==0
    assert hold['bank_after']==p['bank']
    assert report['scope']=='transfers_now_then_hold'
    proposal=report['packages'][1]
    assert proposal['total_gain']==pytest.approx(proposal['total_points']-hold['total_points'])
    assert len(proposal['per_gw'])==2
    path=m.save_report(report,tmp_path/'reports')
    saved=json.loads((path/'report.json').read_text())
    assert saved['forecast']['cache_key']==b['cache_key']
    assert saved['profile']==p


def test_future_cutoff_seed_and_cache_invalidation(tmp_path):
    m=mod();cfg=BaselineConfig();d=context()
    first=bundle(tmp_path)
    d['players'][0]['now_cost']+=1
    changed=m.forecast_bundle(d,[5,6],cfg,origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path,draws=100,seed=42)
    assert first['cache_key']!=changed['cache_key']
    with pytest.raises(ValueError):m.forecast_bundle(d,[5],cfg,origin_at='2026-09-08T13:00:00Z',cache_root=tmp_path)
    with pytest.raises(ValueError):m.forecast_bundle(d,[5],cfg,origin_at='2026-09-10T13:00:00Z',cache_root=tmp_path)
    with pytest.raises(ValueError):m.forecast_bundle(d,[5],cfg,origin_at='2026-09-09T13:00:00',cache_root=tmp_path)


def test_immediate_transfers_cannot_skip_the_next_gw(tmp_path):
    # Otherwise current free transfers/hits would be incorrectly booked in GW6.
    with pytest.raises(ValueError,match='næste'):
        mod().forecast_bundle(context(),[6],BaselineConfig(),origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path)


def test_refreshed_player_status_uses_context_time_not_older_history_time(tmp_path):
    from fpl_model.model_evolution import EvolutionConfig
    d=context()
    d['input_sources']=dict(history=dict(available_at='2026-09-08T10:00:00Z'),
                            player_metadata=dict(available_at='2026-09-09T12:00:00Z'))
    out=mod().forecast_bundle(d,[5],BaselineConfig(),origin_at='2026-09-09T13:00:00Z',
                              cache_root=tmp_path,draws=100,evolution=EvolutionConfig(shared_goals=False))
    assert out['explanations'][5]['1']['availability']['available_at']=='2026-09-09T12:00:00Z'


def test_blank_double_gw_and_uncovered_odds(tmp_path):
    m=mod();d=context();d['teams']=[dict(id=i,name=f'T{i}') for i in range(1,11)]
    d['fixtures'].append(dict(d['fixtures'][-1],id=99))
    odds=([],dict(source='the_odds_api',available_at=d['as_of_at'],retrieved_at=d['as_of_at'],failure='no_saved_odds'))
    b=m.forecast_bundle(d,[5,6],BaselineConfig(),origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path,draws=100,odds=odds)
    assert b['coverage'][6]['usable']==0
    assert b['coverage'][6]['expected_fixtures']==2
    table={r['player_id']:r for r in b['rows'][6]}
    assert table[1]['expected_minutes']>90 and table[3]['xp']==0
    assert table[3]['fixture_ids']==[] and table[1]['fixture_ids']==[6,99]
    assert b['metadata']['availability_policy']=='current_availability_held_constant'


def test_exclusions_do_not_rewrite_hold_comparator_and_hits_only_once(tmp_path):
    m=mod();b=bundle(tmp_path);p=profile();p['bank']=200
    report=m.compare_packages(b,p,max_transfers=2,excluded=[1],allow_hits=True)
    assert 1 in report['packages'][0]['squad']
    assert all(1 not in q['squad'] for q in report['packages'][1:])
    two=next(q for q in report['packages'] if q['count']==2)
    assert two['per_gw'][0]['hits']==4 and two['per_gw'][1]['hits']==0
    assert two['total_points']==pytest.approx(sum(x['mean'] for x in two['per_gw']))

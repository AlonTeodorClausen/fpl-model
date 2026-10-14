import importlib.util
import copy
import pytest
from test_transfer_planner import bundle
from test_my_team import profile


def module():
    assert importlib.util.find_spec('fpl_model.sequence_planner'),'sequence workflow missing'
    from fpl_model import sequence_planner
    return sequence_planner


def test_hold_distinct_from_zero_now_and_all_gains_paired(tmp_path):
    m=module();b=bundle(tmp_path);p=profile();before=copy.deepcopy(p)
    report=m.compare_sequences(b,p,max_per_gw=2,max_total=2)
    assert p==before and report['scope']=='transfer_sequences'
    assert [p['plan_id'] for p in report['packages']]==['hold','first_0','first_1']
    hold=report['packages'][0]
    assert hold['total_gain']==0
    assert all(s['count']==0 for s in hold['steps'])
    assert any(f['first_count']==2 and 'fradrag' in f['reason'] for f in report['unavailable_packages'])
    for plan in report['packages']:
        assert plan['total_gain']==pytest.approx(plan['total_points']-hold['total_points'])
        assert len(plan['per_gw'])==2
        assert plan['next_gw_gain']==plan['per_gw'][0]['gain']
        assert sum(s['count'] for s in plan['steps'])<=2
    assert report['recommendation']['criterion']=='optimizer_objective'


def test_exclude_applies_to_proposals_not_hold_and_hits_each_week(tmp_path):
    m=module();b=bundle(tmp_path);p=profile();p['bank']=200
    report=m.compare_sequences(b,p,max_per_gw=2,max_total=2,excluded=[1],allow_hits=True)
    assert 1 in report['packages'][0]['steps'][0]['squad']
    assert any(f['first_count']==0 for f in report['unavailable_packages'])
    for plan in report['packages'][1:]:
        assert all(1 not in s['squad'] for s in plan['steps'])
        assert [r['hits'] for r in plan['per_gw']]==[s['hits'] for s in plan['steps']]


def test_sensitivity_revalues_fixed_plans_and_reoptimizes_separately(tmp_path):
    m=module();base=bundle(tmp_path);p=profile()
    r=m.compare_sequences(base,p,max_per_gw=1,max_total=2)
    from test_availability import assumptions
    alt=bundle(tmp_path,availability=assumptions(5))
    sensitivity=m.compare_sensitivity(r,alt,label='Example only')
    assert len(sensitivity['fixed_plans'])==len(r['packages'])
    assert sensitivity['alternative']['forecast']['cache_key']==alt['cache_key']
    assert sensitivity['base_cache_key']==base['cache_key']
    assert sensitivity['fixed_plans'][0]['gain_in_alternative']==0
    assert r['forecast']['availability_assumptions']==[]
    wrong=copy.deepcopy(alt);wrong['metadata']['seed']=55
    with pytest.raises(ValueError):m.compare_sensitivity(r,wrong,label='wrong seed')


def test_sensitivity_rejects_changed_odds_or_code_provenance(tmp_path):
    m=module();b=bundle(tmp_path);r=m.compare_sequences(b,profile(),max_per_gw=0,max_total=0)
    for bad in ('odds','code','model'):
        alt=copy.deepcopy(b)
        if bad=='odds':alt['coverage'][5]={'source':{'snapshot_id':'different_odds'}}
        elif bad=='code':alt['metadata']['code_sha256']['simulation.py']='changed'
        else:alt['metadata']['model_version']='different_model'
        with pytest.raises(ValueError):m.compare_sensitivity(r,alt,label='not just an injury change')

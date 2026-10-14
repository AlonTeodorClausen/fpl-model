from copy import deepcopy
import pytest
from test_transfer_sequences import case
from test_chips import ready_profile,context
from fpl_model.optimizer.transfer_sequences import optimize_sequence


def run(chips,events=(6,7),*,p=None,rows=None,**kwargs):
    default,base=case();p=p or default;rows=rows or base
    p['chip_inventory']=ready_profile()['chip_inventory']
    return optimize_sequence({e:deepcopy(rows) for e in events},p,chip_plan=chips,chip_context=context(events),
        first_count=None if chips.get(events[0]) in ('wildcard','free_hit') else 0,**kwargs)


@pytest.mark.parametrize('chip',['wildcard','free_hit'])
def test_rebuild_not_ordinary_limits_and_ft_kept(chip):
    p,rows=case();rows[2]['xp']=30
    out=run({6:chip},p=p,rows=rows,max_per_gw=0,max_total=0)
    assert 3 in out['steps'][0]['squad']
    assert out['steps'][0]['hits']==0 and out['steps'][0]['next_gw']==1
    assert out['steps'][0]['ordinary_count']==0
    assert out['steps'][0]['relocation_count']>0
    assert out['steps'][1]['squad']==(out['steps'][0]['squad'] if chip=='wildcard' else sorted(r['player_id'] for r in p['players']))


def test_fh_spread_retention_restore_and_terminal():
    p,rows=case();rows[0]['price']=80;p['players'][0]['selling_price']=70
    rows[0]['xp']=100;rows[2]['xp']=40
    original=sorted(r['player_id'] for r in p['players'])
    result=run({6:'free_hit'},events=(6,),p=p,rows=rows,max_per_gw=0,max_total=0)
    assert 1 in result['steps'][0]['squad'] and 3 in result['steps'][0]['squad']
    assert result['terminal_state']['squad']==original
    assert result['terminal_state']['bank']==p['bank']
    assert result['terminal_state']['selling_prices'][1]==70
    assert result['terminal_state']['free_transfers']==1


def test_fh_cannot_raise_cash_and_wc_changes_permanent_state():
    p,rows=case();rows[2]['price']=60;rows[2]['xp']=100
    locks=[r['player_id'] for r in p['players'] if r['player_id']!=1]
    with pytest.raises(ValueError):run({6:'free_hit'},events=(6,),p=p,rows=rows,locked=locks,excluded=[1])
    p['bank']=10
    out=run({6:'wildcard'},p=p,rows=rows,locked=locks,excluded=[1],max_per_gw=0,max_total=0)
    assert out['steps'][0]['bank_after']==0
    assert out['steps'][1]['bank_after']==0
    assert out['terminal_state']['selling_prices'][3]==60


def test_two_chips_and_captain_objective():
    p,rows=case();rows[2]['xp']=40
    out=run({6:'wildcard',7:'triple_captain'},p=p,rows=rows,max_per_gw=0,max_total=0)
    lineup=out['lineups'][7];lookup={r['player_id']:r for r in rows}
    assert lineup['expected_xi_captain']==pytest.approx(sum(lookup[i]['xp'] for i in lineup['starters'])+2*lookup[lineup['captain']]['xp'])


def test_chip_requires_deadline_context():
    p,rows=case()
    with pytest.raises(ValueError):optimize_sequence({6:rows},p,chip_plan={6:'wildcard'},first_count=None)


def test_report_pairs_chip_plan_with_no_chip_and_hypothetical_active(tmp_path):
    from test_transfer_planner import bundle
    from test_my_team import profile
    from fpl_model.sequence_planner import compare_sequences
    b=bundle(tmp_path);p=profile();p['chip_inventory']=ready_profile()['chip_inventory']
    e=b['events'][0]
    report=compare_sequences(b,p,max_per_gw=0,max_total=0,chip_plan={e:'triple_captain'})
    assert {r['comparison_family'] for r in report['packages']}=={'hold','ordinary','chip'}
    chip=next(r for r in report['packages'] if r['comparison_family']=='chip')
    normal=next(r for r in report['packages'] if r['comparison_family']=='ordinary')
    assert chip['gain_vs_best_no_chip']==pytest.approx(chip['total_points']-normal['total_points'])
    assert chip['lineups'][e]['chip']=='triple_captain'
    assert report['forecast']==b['metadata']
    p['chip_inventory']['active_chip']=dict(event=e,name='triple_captain')
    report=compare_sequences(b,p,max_per_gw=0,max_total=0,chip_plan={e:'triple_captain'})
    assert report['recommendation']['plan_id'].startswith('chip_')
    assert all(r['hypothetical'] for r in report['packages'] if r['comparison_family']!='chip')


def test_current_owned_lock_survives_pre_transfer_origin():
    p,rows=case();previous=deepcopy(p['players'])
    p['players'][0]=dict(player_id=3,selling_price=50);p['transfers_made']=1
    p['pre_transfer_state']=dict(players=previous,bank=0,free_transfers=2,event=6,
        existing_hits=0,confirmed_at='2026-10-01T00:00:00Z')
    for chip in ('wildcard','free_hit'):
        out=run({6:chip},events=(6,),p=p,rows=rows,locked=[3])
        assert 3 in out['steps'][0]['squad']

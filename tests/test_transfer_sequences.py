import copy
import importlib.util
import pytest
from test_prototype import players
from test_my_team import profile


def solve(tables, p=None, **kwargs):
    assert importlib.util.find_spec('fpl_model.optimizer.transfer_sequences'), 'sequence optimizer missing'
    from fpl_model.optimizer.transfer_sequences import optimize_sequence
    return optimize_sequence(tables, p or profile(), **kwargs)


def case():
    p=profile(); p['bank']=0
    rows=players()
    for r in rows:r.update(price=50,xp=1.)
    for r in p['players']:r['selling_price']=50
    return p,rows


def test_wait_accumulates_free_transfers_and_two_moves_next_week():
    p,rows=case(); rows[3]['team_id']=10; later=copy.deepcopy(rows)
    # Two cheap goalkeeper upgrades worth waiting for, one FT now -> two later.
    for r in later:
        if r['player_id'] in (3,4):r['xp']=20 if r['player_id']==3 else 10
    result=solve({6:rows,7:later},p,first_count=0,max_per_gw=2,max_total=2)
    assert [s['count'] for s in result['steps']]==[0,2]
    assert result['steps'][1]['in']==[3,4]
    assert [s['available'] for s in result['steps']]==[1,2]
    assert result['hits']==0
    assert all(s['bank_after']==0 for s in result['steps'])


def test_no_future_cash_can_finance_current_purchase():
    p,rows=case();p['players'][0]['selling_price']=40
    locks=[r['player_id'] for r in p['players'] if r['player_id']!=1]
    with pytest.raises(ValueError):solve({6:rows,7:rows},p,first_count=1,max_per_gw=1,max_total=2,locked=locks,excluded=[1])
    p['bank']=10
    result=solve({6:rows,7:rows},p,first_count=1,max_per_gw=1,max_total=1,locked=locks,excluded=[1])
    assert result['steps'][0]['bank_after']==0


def test_sell_buy_back_then_resell_uses_new_acquisition_price():
    p,rows=case();p['players'][0]['selling_price']=40;p['bank']=10;p['free_transfers']=5
    lock=[r['player_id'] for r in p['players'] if r['player_id']!=1]
    tables={g:copy.deepcopy(rows) for g in (6,7,8)}
    for g,best in [(6,3),(7,1),(8,3)]:
        for r in tables[g]:
            if r['player_id']==best:r['xp']=30
    result=solve(tables,p,first_count=1,max_per_gw=1,max_total=3,locked=lock)
    assert [s['out'] for s in result['steps']]==[[1],[3],[1]]
    assert [s['bank_after'] for s in result['steps']]==[0,0,0]
    assert result['steps'][2]['sale_proceeds']==50


def test_hits_booked_in_each_relevant_gw_and_no_hits_default():
    p,rows=case()
    with pytest.raises(ValueError):solve({6:rows},p,first_count=2,max_per_gw=2,max_total=2)
    result=solve({6:rows,7:rows},p,first_count=2,max_per_gw=2,max_total=2,allow_hits=True)
    assert result['steps'][0]['hits']==4 and result['steps'][1]['hits']==0
    assert result['objective']==pytest.approx(sum(l['objective'] for l in result['lineups'].values())-4)


def test_state_constraints_order_and_original_input_unchanged():
    p,rows=case(); p['free_transfers']=5
    before=copy.deepcopy(p)
    result=solve({6:rows,7:rows},p,first_count=0,max_per_gw=0,max_total=0)
    assert [s['next_gw'] for s in result['steps']]==[5,5]
    assert p==before
    assert result==solve({7:rows[::-1],6:rows[::-1]},p,first_count=0,max_per_gw=0,max_total=0)
    for invalid in [dict(locked=[1],excluded=[1]),dict(max_total=-1),dict(first_count=1,max_per_gw=0)]:
        with pytest.raises(ValueError):solve({6:rows},p,**invalid)
    p['transfers_made']=20
    with pytest.raises(ValueError):solve({6:rows},p,first_count=1)

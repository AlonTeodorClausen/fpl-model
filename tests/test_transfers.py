import copy
import importlib
import importlib.util

import pytest
from test_prototype import players
from test_my_team import profile


def opt(*a, **kw):
    assert importlib.util.find_spec('fpl_model.optimizer.transfers'), 'transfer optimizer missing'
    return importlib.import_module('fpl_model.optimizer.transfers').optimize_transfers(*a, **kw)


def test_actual_sale_proceeds_and_bank_not_market_value():
    p=profile();p['bank']=7
    locked=[r['player_id'] for r in p['players'] if r['player_id']!=1]
    result=opt({6:players()},p,count=1,locked=locked,excluded=[1])
    assert result['out']==[1] and result['in']==[3] and result['bank_after']==0
    assert result['transfer_schedule'][0]['used']==1
    assert result['solver']['status']=='optimal' and result['solver']['gap']>=0
    p['bank']=6  # Old market value 45 would incorrectly finance the buy at 47.
    with pytest.raises(ValueError):opt({6:players()},p,count=1,locked=locked,excluded=[1])


def test_same_squad_different_lineups_across_horizon():
    p=profile();p['bank']=200
    locks=[r['player_id'] for r in p['players'] if r['player_id']!=17]
    first,second=players(),players()
    for r in first+second:r['xp']=0
    for row in first:
        if row['player_id']==22:row['xp']=10
        if row['player_id']==23:row['xp']=4
    for row in second:
        if row['player_id']==22:row['xp']=1
        if row['player_id']==23:row['xp']=20
    one=opt({6:first},p,count=1,locked=locks,excluded=[17])
    two=opt({6:first,7:second},p,count=1,locked=locks,excluded=[17])
    assert one['in']==[22] and two['in']==[23]
    assert all(set(t['squad'])==set(two['squad']) for t in two['lineups'].values())
    assert two['lineups'][7]['captain']==23
    assert all(len(t['starters'])==11 and len(t['bench'])==4 for t in two['lineups'].values())


def test_hold_unselectable_player_and_never_buy_unselectable():
    rows=players();rows[0]['can_select']=False;rows[2]['can_select']=False
    p=profile();p['bank']=100
    hold=opt({6:rows},p,count=0)
    assert hold['out']==hold['in']==[] and 1 in hold['squad']
    assert hold['bank_after']==100
    p['free_transfers']=2
    proposal=opt({6:rows},p,count=2)
    assert len(proposal['in'])==len(proposal['out'])==2 and 3 not in proposal['in']


def test_constraints_hits_and_deterministic_input_order():
    p=profile();p['bank']=100
    with pytest.raises(ValueError):opt({6:players()},p,count=2)
    result=opt({6:players(),7:players()},p,count=2,allow_hits=True,locked=[1],excluded=[2])
    assert result['hits']==4 and 1 in result['squad'] and 2 not in result['squad']
    assert result['objective']==pytest.approx(sum(t['objective'] for t in result['lineups'].values())-4)
    reverse=opt({7:list(reversed(players())),6:list(reversed(players()))},p,count=2,allow_hits=True,locked=[1],excluded=[2])
    assert reverse==result
    with pytest.raises(ValueError):opt({6:players()},p,count=1,locked=[1],excluded=[1])
    with pytest.raises(ValueError):opt({6:players()},p,count=1,locked=[3])


def test_horizon_requires_same_ids_prices_and_identities():
    rows=copy.deepcopy(players());rows[0]['price']+=1
    with pytest.raises(ValueError):opt({6:players(),7:rows},profile(),count=0)

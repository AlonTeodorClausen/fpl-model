import copy
import importlib
import importlib.util

import pytest
from test_prototype import players


def mod():
    assert importlib.util.find_spec('fpl_model.my_team'), 'profile contract not implemented'
    return importlib.import_module('fpl_model.my_team')


def profile():
    ids = [1, 2, 5, 6, 7, 8, 9, 17, 18, 19, 20, 21, 28, 29, 30]
    return dict(schema_version=1, season='2026-2027', players=[dict(player_id=i, selling_price=40) for i in ids],
                bank=10, free_transfers=1, transfers_made=0)


def test_profile_roundtrip_edit_and_money(tmp_path):
    m=mod(); p=profile()
    assert m.money('4.6')==46
    assert m.money(0)==0
    for bad in ['4.61', '-1', 'NaN', None, True]:
        with pytest.raises(ValueError): m.money(bad)
    m.validate_profile(p,players(),season='2026-2027')
    path=tmp_path/'my_team.json'; m.save_profile(p,path)
    assert m.load_profile(path)==p
    p['bank']=20; m.save_profile(p,path)
    assert m.load_profile(path)['bank']==20


@pytest.mark.parametrize('change', ['duplicate','position','unknown','price','bank','ft','season','cap'])
def test_profile_rejects_invalid_input(change):
    p=profile(); pool=players()
    if change=='duplicate':p['players'][1]=p['players'][0]
    if change=='position':p['players'][0]['player_id']=10
    if change=='unknown':p['players'][0]['player_id']=999
    if change=='price':p['players'][0]['selling_price']=999
    if change=='bank':p['bank']=-1
    if change=='ft':p['free_transfers']=6
    if change=='season':p['season']='2025-2026'
    if change=='cap':p['transfers_made']=21
    with pytest.raises(ValueError):mod().validate_profile(p,pool,season='2026-2027')


def test_transfer_accounting_hits_and_rollover():
    m=mod()
    assert m.transfer_schedule(1,0,[6,7,8,9])==[
        dict(event=6,available=1,used=0,remaining=1,next_gw=2,hits=0),
        dict(event=7,available=2,used=0,remaining=2,next_gw=3,hits=0),
        dict(event=8,available=3,used=0,remaining=3,next_gw=4,hits=0),
        dict(event=9,available=4,used=0,remaining=4,next_gw=5,hits=0)]
    s=m.transfer_schedule(1,2,[6,7],allow_hits=True)
    assert s[0]['hits']==4 and s[1]['hits']==0 and s[1]['available']==1
    assert m.transfer_schedule(5,0,[6,7])[-1]['next_gw']==5
    with pytest.raises(ValueError): m.transfer_schedule(1,2,[6])
    with pytest.raises(ValueError): m.transfer_schedule(5,2,[6],transfers_made=19)


def test_owned_unselectable_player_can_be_retained():
    p=profile();pool=copy.deepcopy(players());pool[0]['can_select']=False
    mod().validate_profile(p,pool,season='2026-2027')

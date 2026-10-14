from copy import deepcopy
import pytest
from test_my_team import profile
from fpl_model.chips import (normalize_chip_inventory, validate_chip_plan,
                            chip_transfer_account, resolve_chip_origin)


def ready_profile():
    p=profile(); inv=normalize_chip_inventory(p)
    inv['entry_start_event']=1
    for half in inv['halves'].values():
        for r in half.values():r.update(status='available',source='manual',confirmed_at='2026-10-01T00:00:00Z')
    p['chip_inventory']=inv
    return p


def context(events=(6,7)):
    return dict(deadlines={e:'2026-10-20T10:00:00Z' for e in events},origin_at='2026-10-14T10:00:00Z')


def test_legacy_unknown_not_available_and_no_mutation():
    p=profile();before=deepcopy(p)
    assert normalize_chip_inventory(p)['halves']['first']['wildcard']['status']=='unknown'
    assert validate_chip_plan({},p,[6],**context())=={}
    with pytest.raises(ValueError):validate_chip_plan({6:'wildcard'},p,[6],**context())
    assert p==before


@pytest.mark.parametrize('chip',['wildcard','free_hit'])
def test_chip_transfer_account(chip):
    assert chip_transfer_account(3,8,chip)==dict(used=0,remaining=3,next_gw=3,hits=0)


@pytest.mark.parametrize('chip',[None,'triple_captain','bench_boost'])
def test_normal_account(chip):
    assert chip_transfer_account(1,2,chip)==dict(used=1,remaining=0,next_gw=1,hits=4)


def test_schedule_validation_and_active():
    p=ready_profile()
    assert validate_chip_plan({'6':'wildcard'},p,[6],**context())=={6:'wildcard'}
    for plan in ({6:'unknown'},{6:'wildcard',7:'wildcard'},{8:'bench_boost'}):
        with pytest.raises(ValueError):validate_chip_plan(plan,p,[6,7],**context())
    p['chip_inventory']['active_chip']=dict(event=6,name='triple_captain')
    with pytest.raises(ValueError):validate_chip_plan({6:'bench_boost'},p,[6],**context())
    with pytest.raises(ValueError):validate_chip_plan({},p,[6],**context())


def test_cross_half_freehit_first_gw_used_expired_unknown_season():
    p=ready_profile()
    with pytest.raises(ValueError):validate_chip_plan({19:'free_hit',20:'free_hit'},p,[19,20],**context((19,20)))
    p['chip_inventory']['halves']['first']['free_hit'].update(status='used',used_event=19)
    with pytest.raises(ValueError):validate_chip_plan({20:'free_hit'},p,[20],**context((20,)))
    p=ready_profile();p['chip_inventory']['entry_start_event']=6
    with pytest.raises(ValueError):validate_chip_plan({6:'wildcard'},p,[6],**context())
    p=ready_profile()
    with pytest.raises(ValueError):validate_chip_plan({6:'wildcard'},p,[6],deadlines={6:'2026-01-01T00:00:00Z'},origin_at='2026-10-01T00:00:00Z')
    p['season']='2030-2031'
    with pytest.raises(ValueError):validate_chip_plan({6:'wildcard'},p,[6],**context())


def test_missing_pre_transfer_state_rejected():
    p=ready_profile();p['transfers_made']=1
    with pytest.raises(ValueError,match='før'):resolve_chip_origin(p,'free_hit')
    assert resolve_chip_origin(p,None)==p
    p['pre_transfer_state']=dict(players=deepcopy(p['players']),bank=10,free_transfers=2,
        existing_hits=0,event=6,confirmed_at='2026-10-01T00:00:00Z')
    origin=resolve_chip_origin(p,'free_hit')
    assert origin['free_transfers']==2 and origin['transfers_made']==0
    assert p['transfers_made']==1


def test_profile_persists_chip_status_and_rejects_corruption(tmp_path):
    from fpl_model.my_team import save_profile,load_profile
    p=ready_profile();f=tmp_path/'team.json';save_profile(p,f)
    assert load_profile(f)==p
    p['chip_inventory']['season']='wrong'
    with pytest.raises(ValueError):save_profile(p,f)


def test_chip_scoring_and_lineup_cache():
    import numpy as np
    from test_prototype import players
    from fpl_model.optimizer.lineup import optimize_lineup,refine_plan
    from fpl_model.optimizer.squad import evaluate_squad
    rows=players();ids=[r['player_id'] for r in profile()['players']]
    pts=np.ones((4,len(rows)));active=np.ones_like(pts,dtype=bool)
    team=optimize_lineup(ids,rows,pts,active)
    idx={r['player_id']:i for i,r in enumerate(rows)};c=idx[team['captain']];v=idx[team['vice_captain']]
    pts[0,c]=-2;active[1,c]=False;active[2,[c,v]]=False
    normal=evaluate_squad(team,rows,pts,active)
    tc=evaluate_squad(team,rows,pts,active,chip='triple_captain')
    np.testing.assert_array_equal(tc['points'],normal['points']+normal['captain_bonus'])
    bb=evaluate_squad(team,rows,pts,active,chip='bench_boost')
    ix=[idx[i] for i in ids]
    np.testing.assert_array_equal(bb['points'],(pts[:,ix]*active[:,ix]).sum(axis=1)+normal['captain_bonus'])
    for chip in ('triple_captain','bench_boost'):
        chosen=optimize_lineup(ids,rows,pts,active,chip=chip)
        assert chosen['objective']==pytest.approx(evaluate_squad(chosen,rows,pts,active,chip=chip)['points'].mean())
    with pytest.raises(ValueError):evaluate_squad(team,rows,pts,active,chip='bad')
    cache={};bundle=dict(rows={6:rows},planning_scenarios={6:dict(points=pts,played=active)})
    for chip in (None,'triple_captain','bench_boost'):
        plan=dict(lineups={6:deepcopy(team)},steps=[dict(event=6,chip=chip)],objective=0,hits=0)
        refine_plan(plan,bundle,cache)
        assert plan['lineups'][6]['chip']==chip
    assert len(cache)==3


def test_unknown_previous_fh_week_cannot_authorize_fh20():
    p=ready_profile();p['chip_inventory']['halves']['first']['free_hit'].update(status='used',used_event=None)
    with pytest.raises(ValueError):validate_chip_plan({20:'free_hit'},p,[20],**context((20,)))


def test_pre_transfer_state_invalid_and_unconfirmed_not_saved(tmp_path):
    from fpl_model.my_team import save_profile
    p=ready_profile();p['pre_transfer_state']={'event':6}
    with pytest.raises(ValueError):save_profile(p,tmp_path/'profile.json')


def test_recorded_chip_and_selected_or_active_chip_cannot_share_event():
    p=ready_profile();p['chip_inventory']['halves']['first']['bench_boost'].update(status='used',used_event=6)
    with pytest.raises(ValueError):validate_chip_plan({6:'triple_captain'},p,[6],**context())
    p['chip_inventory']['active_chip']=dict(event=6,name='triple_captain')
    with pytest.raises(ValueError):normalize_chip_inventory(p)


@pytest.mark.parametrize('active,plan,events',[
    ({'event':6,'name':'triple_captain'},{7:'triple_captain'},[7]),
    ({'event':19,'name':'free_hit'},{20:'free_hit'},[20]),
])
def test_active_chip_counts_as_history_outside_horizon(active,plan,events):
    p=ready_profile();p['chip_inventory']['active_chip']=active
    with pytest.raises(ValueError):validate_chip_plan(plan,p,events,**context(events))

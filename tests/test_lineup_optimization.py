import copy
import importlib
import numpy as np
import pytest
from fpl_model.optimizer.squad import evaluate_squad


def optimize(*args,**kwargs):
    return importlib.import_module('fpl_model.optimizer.lineup').optimize_lineup(*args,**kwargs)


def fixture():
    positions=[1,1]+[2]*5+[3]*5+[4]*3
    rows=[dict(player_id=i,position=p,team_id=i//3,price=50,xp=0) for i,p in enumerate(positions)]
    points=np.zeros((100,15));active=np.ones_like(points,dtype=bool)
    # Ten high-valued guaranteed starters plus Egan (DEF6) or Joao (FWD14).
    points[:,[0,2,3,4,7,8,9,10,12,13]]=10
    points[:,6]=4
    points[:50,14]=7;active[50:,14]=False
    return rows,points,active


def test_autosub_option_beats_unconditional_xp_and_cameo_blocks_cover():
    rows,points,active=fixture();squad=list(range(15))
    chosen=optimize(squad,rows,points,active)
    assert 14 in chosen['starters'] and 6 in chosen['bench']
    value=evaluate_squad(chosen,rows,points,active)
    assert chosen['objective']==pytest.approx(value['points'].mean())
    assert chosen['planning_bench_points']==pytest.approx(value['bench_points'].mean())
    # A one-point cameo replaces the DNP: no insurance, so use Egan instead.
    active[:,14]=True;points[50:,14]=1;points[:50,14]=6
    cameo=optimize(squad,rows,points,active)
    assert 6 in cameo['starters'] and 14 in cameo['bench']


def test_exact_objective_agrees_with_existing_autosubs_and_order_is_deterministic():
    rows,_,_=fixture();rng=np.random.default_rng(7)
    active=rng.random((100,15))>.25;points=rng.integers(-2,12,(100,15))*active
    before=copy.deepcopy(rows)
    team=optimize(list(range(15)),rows,points,active)
    assert team['objective']==pytest.approx(evaluate_squad(team,rows,points,active)['points'].mean())
    reversed_team=optimize(list(reversed(range(15))),rows[::-1],points[:,::-1],active[:,::-1])
    assert team==reversed_team and rows==before
    assert team['lineup_search']['exhaustive']


def test_missing_planning_scenarios_never_falls_back_to_evaluation(tmp_path):
    from test_transfer_planner import bundle
    from test_my_team import profile
    from fpl_model.sequence_planner import compare_sequences
    b=bundle(tmp_path);b.pop('planning_scenarios',None)
    with pytest.raises(ValueError,match='planlægning'):
        compare_sequences(b,profile(),max_per_gw=0,max_total=0)


def test_evaluation_draws_cannot_choose_lineups_or_recommendation(tmp_path):
    from test_transfer_planner import bundle
    from test_my_team import profile
    from fpl_model.sequence_planner import compare_sequences
    b=bundle(tmp_path);a=compare_sequences(b,profile(),max_per_gw=1,max_total=1)
    changed=copy.deepcopy(b)
    for s in changed['scenarios'].values():s['points'][:]=1000;s['played'][:]=False
    c=compare_sequences(changed,profile(),max_per_gw=1,max_total=1)
    assert a['recommendation']==c['recommendation']
    assert [p['lineups'] for p in a['packages']]==[p['lineups'] for p in c['packages']]
    assert [p['objective'] for p in a['packages']]==[p['objective'] for p in c['packages']]
    assert a['packages'][0]['total_points']!=c['packages'][0]['total_points']


def test_captain_vice_cover_and_legality_with_multiple_absences():
    rows,points,active=fixture()
    # A high-upside captain misses half the scenarios; vice must still score.
    points[:,7]=30;points[50:,7]=0;active[50:,7]=False
    active[:30,[0,2,3]]=False;points[:30,[0,2,3]]=0
    points[:,1]=3;points[:,5]=4
    team=optimize(list(range(15)),rows,points,active)
    assert team['captain']==7
    assert team['vice_captain']!=7 and team['vice_captain'] in team['starters']
    score=evaluate_squad(team,rows,points,active)
    assert score['captain_bonus'][60]>0
    assert team['objective']==pytest.approx(score['points'].mean())

import copy
import importlib.util
import numpy as np
import pytest
from fpl_model.attacking_odds import team_attack_rates
from fpl_model.models.baseline import BaselineConfig
from fpl_model.simulation import simulate
from fpl_model.defensive_odds import build_coverage
from test_defensive_odds import coverage_data


def api():
    assert importlib.util.find_spec('fpl_model.set_piece_roles'), 'Set-piece contract not implemented'
    from fpl_model import set_piece_roles
    return set_piece_roles


def params():
    return {i:dict(goals=.2,assists=.2,p_start=p,p_sub=0,start_minutes=82.,sub_minutes=22.) for i,p in [(1,1.),(2,1.),(3,0.)]}


def roles():
    return [dict(player_id=i,team_id=1,penalties_order=i,direct_freekicks_order=i,corners_and_indirect_freekicks_order=i) for i in (1,2,3)]


def test_reallocation_conserves_budgets_does_not_add_penalty_xg_and_preserves_inputs():
    m=api();p=params();rates=team_attack_rates(p,2.);before=copy.deepcopy(rates)
    out=m.allocate_roles(rates,roles(),m.SetPieceConfig())
    assert rates==before
    assert sum(r['expected_goals'] for r in out.values())==pytest.approx(2.)
    assert sum(r['expected_assists'] for r in out.values())==pytest.approx(sum(r['expected_assists'] for r in rates.values()))
    assert out[1]['expected_goals']>rates[1]['expected_goals']
    assert out[1]['expected_assists']>rates[1]['expected_assists']
    assert out[3]['expected_goals']==out[3]['expected_assists']==0
    for r in out.values():
        assert r['set_pieces']['historical_nonpenalty_xg_known'] is False
        assert sum(r['set_pieces']['goal_share_components'].values())==pytest.approx(r['goal_share'])
        assert r['set_pieces']['kind']=='assumed_budget_reallocation'
    assert all(r['goals_per90']>=0 and r['assists_per90']>=0 for r in out.values())


def test_no_role_no_confidence_and_conflicts_keep_original_rates():
    m=api();rates=team_attack_rates(params(),2.)
    variants=[([],m.SetPieceConfig()),(roles(),m.SetPieceConfig(role_confidence=0)),
        ([dict(r,penalties_order=1,direct_freekicks_order=1,corners_and_indirect_freekicks_order=1) for r in roles()],m.SetPieceConfig())]
    for records,cfg in variants:
        out=m.allocate_roles(rates,records,cfg)
        for i in rates:
            for k in ('goals_per90','assists_per90','expected_goals','expected_assists'):assert out[i][k]==rates[i][k]
    conflicted=m.allocate_roles(rates,variants[-1][0],m.SetPieceConfig())
    assert conflicted[1]['set_pieces']['markets']['penalties_order']['status']=='conflicted'


def test_bench_primary_hands_role_to_second_and_no_players_is_fallback():
    m=api();p=params();p[1]['p_start']=0;p[3]['p_start']=1
    r=team_attack_rates(p,2.);out=m.allocate_roles(r,roles(),m.SetPieceConfig())
    assert out[2]['expected_goals']>r[2]['expected_goals']
    assert out[1]['expected_goals']==0
    assert m.allocate_roles(r,list(reversed(roles())),m.SetPieceConfig())==out
    missing=m.allocate_roles(r,[dict(x,penalties_order=None) for x in roles()],m.SetPieceConfig())
    assert missing[2]['set_pieces']['markets']['penalties_order']['status']=='unknown'


def evidence(data):
    return dict(source=dict(snapshot_id='roles',available_at=data['as_of_at'],retrieved_at=data['as_of_at'],
        raw_path='raw/fpl_api/bootstrap_static.json',sha256='0'*64),
        players=[dict(player_id=p['id'],team_id=p['team'],penalties_order=i+1,
            direct_freekicks_order=i+1,corners_and_indirect_freekicks_order=i+1) for i,p in enumerate(data['players'])])


def test_simulation_preserves_minutes_other_components_default_and_blocks_future_roles():
    m=api();d,row,source=coverage_data();cfg=BaselineConfig()
    coverage=build_coverage(d,[row],source,5,cfg,d['as_of_at']);record=evidence(d)
    kwargs=dict(draws=200,seed=42,defensive_odds=coverage,odds_scope='attack_and_defence')
    b=simulate(d,5,cfg,**kwargs)
    c=simulate(d,5,cfg,**kwargs,set_piece_config=m.SetPieceConfig(),set_piece_source=record)
    np.testing.assert_array_equal(b.minutes,c.minutes)
    for pid,e in b.explanations.items():
        for k,v in e['point_components'].items():
            if k not in ('goals','assists'):assert c.explanations[pid]['point_components'][k]==v
    np.testing.assert_array_equal(b.points,simulate(d,5,cfg,**kwargs).points)
    bad=copy.deepcopy(record);bad['source']['available_at']='2099-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='after'):simulate(d,5,cfg,**kwargs,set_piece_config=m.SetPieceConfig(),set_piece_source=bad)
    with pytest.raises(ValueError):simulate(d,5,cfg,**kwargs,set_piece_config=m.SetPieceConfig(),set_piece_source=record,retrospective=True)
    # No eligible odds -> original baseline, role metadata cannot conjure an odds budget.
    empty=build_coverage(d,[],source,5,cfg,d['as_of_at'])
    f=simulate(d,5,cfg,draws=200,seed=42,defensive_odds=empty,odds_scope='attack_and_defence',set_piece_config=m.SetPieceConfig(),set_piece_source=record)
    np.testing.assert_array_equal(f.points,simulate(d,5,cfg,draws=200,seed=42).points)


def test_role_identity_and_config_are_strict():
    m=api();d,_,_=coverage_data();record=evidence(d)
    record['players'][0]['team_id']=999
    with pytest.raises(ValueError):m.validate_source(record,d['players'],d['as_of_at'])
    for kw in [dict(penalty_goal_share=-1),dict(penalty_goal_share=.9,direct_goal_share=.2),dict(role_confidence=float('nan'))]:
        with pytest.raises(ValueError):m.SetPieceConfig(**kw)


def test_load_roles_preserves_raw_provenance_and_detects_modified_source(tmp_path):
    import json
    from datetime import datetime,timezone
    from fpl_model.io import SnapshotWriter,SnapshotIntegrityError
    m=api();now=datetime(2026,9,9,tzinfo=timezone.utc)
    writer=SnapshotWriter(tmp_path,clock=lambda:now)
    body=json.dumps({'elements':[dict(id=1,team=1,penalties_order=1)]}).encode()
    writer.write_raw('fpl_api/bootstrap_static.json',body,source='fpl_api',request_started_at=now,retrieved_at=now,required=True,http_status=200)
    writer.finalize();source=m.load_roles(writer.final_path)
    assert datetime.fromisoformat(source['source']['retrieved_at'])==now
    assert source['players'][0]['direct_freekicks_order'] is None
    assert (writer.final_path/source['source']['raw_path']).read_bytes()==body
    assert source['source']['source_published_at'] is None
    raw=writer.final_path/source['source']['raw_path'];raw.chmod(0o600);raw.write_bytes(b'changed')
    with pytest.raises(SnapshotIntegrityError):m.load_roles(writer.final_path)


def test_cache_includes_roles_configuration_and_explanations(tmp_path):
    m=api();from fpl_model.transfer_planner import forecast_bundle
    from test_transfer_planner import context
    d=context();source=evidence(d)
    odds=([],dict(source='the_odds_api',available_at=d['as_of_at'],retrieved_at=d['as_of_at'],failure='no_saved_odds'))
    kw=dict(origin_at='2026-09-09T13:00:00Z',cache_root=tmp_path,draws=100,odds=odds,odds_scope='attack_and_defence')
    a=forecast_bundle(d,[5],BaselineConfig(),**kw)
    b=forecast_bundle(d,[5],BaselineConfig(),**kw,set_piece_config=m.SetPieceConfig(),set_piece_source=source)
    assert b['metadata']['model_version']==m.VERSION and a['cache_key']!=b['cache_key']
    assert b['metadata']['set_piece_source']==source['source']
    np.testing.assert_array_equal(a['scenarios'][5]['points'],b['scenarios'][5]['points'])
    c=forecast_bundle(d,[5],BaselineConfig(),**kw,set_piece_config=m.SetPieceConfig(role_confidence=.1),set_piece_source=source)
    assert c['cache_key']!=b['cache_key']


def test_app_exposes_roles_as_assumptions_without_network(monkeypatch,tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_my_team_app import setup
    from test_my_team import profile
    from fpl_model.my_team import save_profile
    from test_transfer_planner import context
    setup(monkeypatch,tmp_path);m=api();monkeypatch.setattr(m,'load_roles',lambda p:evidence(context()))
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    model=next(w for w in app.selectbox if w.label=='Prognosemodel')
    assert model.value=='Baseline'
    model.set_value('Eksperiment · dødboldsroller og odds').run()
    assert not app.exception
    assert any('non-penalty' in x.value for x in app.warning)
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    report=app.session_state['lab_transfer_result']
    assert report['forecast']['model_version']==m.VERSION
    assert report['forecast']['set_piece_config']['role_confidence']==.5


def test_comparison_report_is_reconciled_and_persisted_for_future_evaluation(tmp_path):
    from pathlib import Path
    from fpl_model.prediction_evaluation import save_forecasts,load_forecasts
    spec=importlib.util.spec_from_file_location('compare_set_pieces',Path(__file__).resolve().parents[1]/'scripts/compare_set_pieces.py')
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    m=api();d,row,source=coverage_data();cfg=BaselineConfig();record=evidence(d)
    coverage=build_coverage(d,[row],source,5,cfg,d['as_of_at'])
    sims,report=script.compare(d,coverage,record,m.SetPieceConfig(),draws=100,seed=42)
    assert report['invariants']['team_budgets_conserved']
    assert all(r['xp_delta']==pytest.approx(r['goal_points_delta']+r['assist_points_delta']) for r in report['player_changes'])
    out=save_forecasts(d,5,sims,cfg,None,coverage,tmp_path,set_piece_config=m.SetPieceConfig())
    saved,arrays=load_forecasts(out)
    assert saved['set_piece_config']['role_confidence']==.5
    assert m.VERSION+'_points' in arrays
    assert 'set_piece_roles.py' in saved['code_sha256']


def test_missing_priority_slot_is_unknown_not_guessed():
    m=api();rates=team_attack_rates(params(),2.)
    records=[roles()[0],roles()[2]]
    out=m.allocate_roles(rates,records,m.SetPieceConfig())
    assert out[1]['set_pieces']['markets']['penalties_order']['reason']=='missing_order_slot'
    assert out[1]['goals_per90']==rates[1]['goals_per90']

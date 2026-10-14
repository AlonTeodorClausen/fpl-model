"""Offline prospective sensitivity comparison using captured official roles/odds."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.models.baseline import BaselineConfig
from fpl_model.odds_comparison import load_inputs,load_odds
from fpl_model.defensive_odds import build_coverage
from fpl_model.set_piece_roles import SetPieceConfig,load_roles,VERSION
from fpl_model.simulation import simulate
from fpl_model.prediction_evaluation import save_forecasts
from fpl_model.label_contracts import utc


def compare(data,coverage,roles,options,*,draws=3000,seed=42):
    cfg=BaselineConfig();event=coverage['event']
    sims={'component_baseline_v1':simulate(data,event,cfg,draws=draws,seed=seed)}
    common=dict(draws=draws,seed=seed,defensive_odds=coverage,odds_scope='attack_and_defence')
    sims['component_attacking_odds_v1']=simulate(data,event,cfg,**common)
    sims[VERSION]=simulate(data,event,cfg,**common,set_piece_config=options,set_piece_source=roles)
    old=sims['component_attacking_odds_v1'];new=sims[VERSION]
    if not np.array_equal(old.minutes,new.minutes):raise ValueError('Set-piece roles changed minutes')
    changes=[];budgets={}
    for before,after in zip(old.summary(),new.summary()):
        pid=before['player_id'];b=old.explanations[pid];a=new.explanations[pid]
        if any(v!=a['point_components'][k] for k,v in b['point_components'].items() if k not in ('goals','assists')):
            raise ValueError('Set-piece roles changed nonattacking components')
        delta=after['xp']-before['xp']
        g=a['point_components']['goals']-b['point_components']['goals']
        assist=a['point_components']['assists']-b['point_components']['assists']
        if not np.isclose(delta,g+assist):raise ValueError('Unreconciled point difference')
        orders=next(r for r in roles['players'] if r['player_id']==pid)
        changes.append(dict(player_id=pid,name=before['name'],position=before['position'],
            expected_minutes=before['expected_minutes'],original_odds_xp=before['xp'],role_scenario_xp=after['xp'],
            xp_delta=delta,goal_points_delta=g,assist_points_delta=assist,
            penalties_order=orders.get('penalties_order'),direct_freekicks_order=orders.get('direct_freekicks_order'),
            corners_and_indirect_freekicks_order=orders.get('corners_and_indirect_freekicks_order')))
        for fixture in a['fixtures']:
            allocation=fixture['attack_odds'];key=(fixture['fixture_id'],before['team_id'])
            group=budgets.setdefault(key,dict(fixture_id=key[0],team_id=key[1],expected_goals=0.,expected_assists=0.,
                team_goal_budget=None,team_assist_budget=None,status=allocation['status'],role_coverage=None))
            if allocation['status']!='odds':continue
            group['expected_goals']+=allocation['expected_goals'];group['expected_assists']+=allocation['expected_assists']
            group.update(team_goal_budget=allocation['team_goal_mean'],team_assist_budget=allocation['team_goal_mean']*allocation['team_assist_fraction'],
                role_coverage=allocation['set_pieces']['markets'])
    for b in budgets.values():
        if b['status']=='odds' and (not np.isclose(b['expected_goals'],b['team_goal_budget']) or not np.isclose(b['expected_assists'],b['team_assist_budget'])):
            raise ValueError('Set-piece roles changed the team goal/assist budget')
    return sims,dict(model_version=VERSION,kind='assumed_role_sensitivity_not_performance',event=event,draws=draws,seed=seed,
        usable_fixtures=coverage['usable'],expected_fixtures=coverage['expected_fixtures'],
        player_changes=sorted(changes,key=lambda r:(-abs(r['xp_delta']),r['player_id'])),
        team_budgets=list(budgets.values()),invariants=dict(minutes_identical=True,nonattacking_components_identical=True,team_budgets_conserved=True))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--context-snapshot',type=Path,required=True,help='Official fixture/deadline context and role source')
    p.add_argument('--odds-snapshot',type=Path,required=True)
    p.add_argument('--draws',type=int,default=3000);p.add_argument('--seed',type=int,default=42)
    p.add_argument('--penalty-goal-share',type=float,default=.10);p.add_argument('--direct-goal-share',type=float,default=.02)
    p.add_argument('--indirect-assist-share',type=float,default=.15);p.add_argument('--role-confidence',type=float,default=.5)
    p.add_argument('--output-root',type=Path,default=Path('artifacts/set_piece_forecasts'))
    args=p.parse_args(argv);origin=datetime.now(timezone.utc).isoformat()
    data=load_inputs(args.snapshot,args.context_snapshot,origin);roles=load_roles(args.context_snapshot)
    event=min((e['id'] for e in data['events'] if utc(e['deadline_time'])>utc(origin)),default=None)
    if event is None:p.error('No future official deadline in captured context')
    odds,source=load_odds(args.odds_snapshot,'the_odds_api')
    coverage=build_coverage(data,odds,source,event,BaselineConfig(),origin)
    options=SetPieceConfig(args.penalty_goal_share,args.direct_goal_share,args.indirect_assist_share,args.role_confidence)
    print(f'GW{event}: baseline, attacking odds and explicit role sensitivity; no downloads.',flush=True)
    sims,comparison=compare(data,coverage,roles,options,draws=args.draws,seed=args.seed)
    data['input_sources']['set_piece_roles']=roles['source']
    out=save_forecasts(data,event,sims,BaselineConfig(),None,coverage,args.output_root,set_piece_config=options)
    with (out/'comparison.json').open('x') as f:json.dump(comparison,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(output=str(out),event=event,odds_coverage=coverage['usable'],top_changes=comparison['player_changes'][:5]),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())

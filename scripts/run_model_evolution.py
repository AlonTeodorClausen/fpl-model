"""Offline role/shared-goal forecast and chronological role diagnostic. No downloads."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.models.baseline import BaselineConfig
from fpl_model.model_evolution import EvolutionConfig
from fpl_model.odds_comparison import load_inputs,load_odds
from fpl_model.defensive_odds import build_coverage
from fpl_model.label_contracts import utc
from fpl_model.simulation import simulate
from fpl_model.backtest.walk_forward import evaluate_sample
from fpl_model.prediction_evaluation import save_forecasts,evaluate_saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--odds-snapshot',type=Path)
    parser.add_argument('--draws',type=int,default=3000)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--recent-matches',type=int,default=3)
    parser.add_argument('--half-life-matches',type=float,default=2.)
    parser.add_argument('--skip-development',action='store_true')
    parser.add_argument('--output-root',type=Path,default=Path('artifacts/model_forecasts'))
    args=parser.parse_args(argv)
    origin=datetime.now(timezone.utc).isoformat()
    data=load_inputs(args.snapshot,args.snapshot,origin)
    event=min((e['id'] for e in data['events'] if utc(e['deadline_time'])>utc(origin)),default=None)
    if event is None:parser.error('No future official deadline in captured data')
    config=BaselineConfig();options=EvolutionConfig(recent_matches=args.recent_matches,half_life_matches=args.half_life_matches)
    coverage=None
    if args.odds_snapshot:
        rows,source=load_odds(args.odds_snapshot,'the_odds_api');coverage=build_coverage(data,rows,source,event,config,origin)
    simulations={}
    print(f'GW{event}: baseline, derefter eksisterende oddsreference og nyt eksperiment.',flush=True)
    simulations['component_baseline_v1']=simulate(data,event,config,draws=args.draws,seed=args.seed)
    if coverage is not None:
        simulations['component_attacking_odds_v1']=simulate(data,event,config,draws=args.draws,seed=args.seed,
            defensive_odds=coverage,odds_scope='attack_and_defence')
    simulations[options.version]=simulate(data,event,config,draws=args.draws,seed=args.seed,
        defensive_odds=coverage,odds_scope='attack_and_defence' if coverage is not None else 'defence',evolution=options)
    output=save_forecasts(data,event,simulations,config,options,coverage,args.output_root)
    if not args.skip_development:
        print('Kronologisk rolle-evaluering på samme rækker; ingen odds eller aktuelle skader.',flush=True)
        role=EvolutionConfig(recent_matches=args.recent_matches,half_life_matches=args.half_life_matches,shared_goals=False)
        baseline=evaluate_sample(data,config,draws=min(args.draws,2000),seed=args.seed)
        candidate=evaluate_sample(data,config,draws=min(args.draws,2000),seed=args.seed,evolution=role)
        if [(r['player_id'],r['event']) for r in baseline['rows']]!=[(r['player_id'],r['event']) for r in candidate['rows']]:
            raise ValueError('Development variants must share evaluation rows')
        # Exclusive sidecar; does not rewrite the already frozen forecast.
        with (output/'development.json').open('x') as f:json.dump({'baseline':baseline,'recent_role':candidate},f,ensure_ascii=False,allow_nan=False)
    evaluated,result=evaluate_saved(output,data['histories'],args.output_root.parent/'model_evaluations')
    print(json.dumps(dict(output=str(output),event=event,coverage=coverage['usable'] if coverage else 0,
        evaluation=str(evaluated),scored={k:v['n'] for k,v in result['variants'].items()})))
    return 0


if __name__=='__main__':raise SystemExit(main())

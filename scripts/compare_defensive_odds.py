"""Compare defensive-only odds against v1 using existing immutable captures. Offline."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.models.baseline import BaselineConfig
from fpl_model.label_contracts import utc
from fpl_model.odds_comparison import load_inputs,load_odds,compare_forecasts,synthetic_demo,save_comparison
from fpl_model.defensive_odds import build_coverage


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history-snapshot',required=True,type=Path)
    p.add_argument('--context-snapshot',required=True,type=Path)
    p.add_argument('--odds-snapshot',required=True,type=Path)
    p.add_argument('--forecast-origin-at',default=None)
    p.add_argument('--event',type=int)
    p.add_argument('--draws',type=int,default=3000)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--budget',type=float,default=100)
    p.add_argument('--include-offline-example',action='store_true')
    args=p.parse_args(argv)
    origin=utc(args.forecast_origin_at) if args.forecast_origin_at else datetime.now(timezone.utc)
    data=load_inputs(args.history_snapshot,args.context_snapshot,origin.isoformat())
    upcoming=[e['id'] for e in data['events'] if utc(e['deadline_time'])>origin]
    event=args.event if args.event is not None else min(upcoming,default=None)
    if event not in upcoming:p.error('Select a GW whose verified official deadline is still in the future')
    rows,source=load_odds(args.odds_snapshot);config=BaselineConfig()
    coverage=build_coverage(data,rows,source,event,config,origin.isoformat())
    result=compare_forecasts(data,coverage,config,draws=args.draws,seed=args.seed,budget=args.budget)
    out=save_comparison(result)
    print(json.dumps(dict(output=str(out),event=event,usable=coverage['usable'],expected=coverage['expected_fixtures'],
        source_rows=coverage['total_source_rows'],pl_rows=coverage['premier_league_rows'],reasons=sorted({f['reason'] for f in coverage['fixtures'] if f['reason']}))))
    if args.include_offline_example:
        demo=synthetic_demo(data,event,config,draws=args.draws,seed=args.seed,budget=args.budget)
        print('SYNTHETIC OFFLINE EXAMPLE, NOT CURRENT ODDS:',save_comparison(demo))
    return 0


if __name__=='__main__':raise SystemExit(main())

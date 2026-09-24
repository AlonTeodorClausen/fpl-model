"""Run the complete single-GW prototype offline on an immutable FPL snapshot."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None,''}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.models.baseline import BaselineConfig
from fpl_model.prototype_data import load_data, snapshot_paths
from fpl_model.prototype import run_prototype, save_run
from fpl_model.label_contracts import utc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path)
    p.add_argument('--raw-root',type=Path,default=Path(__file__).resolve().parents[1]/'data/raw')
    p.add_argument('--event',type=int)
    p.add_argument('--draws',type=int,default=3000)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--budget',type=float,default=100)
    p.add_argument('--locked',type=int,nargs='*',default=[])
    p.add_argument('--excluded',type=int,nargs='*',default=[])
    p.add_argument('--prior-games',type=float,default=3)
    p.add_argument('--attack-scale',type=float,default=1)
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    paths=snapshot_paths(args.raw_root)
    if not args.snapshot and not paths: p.error('No verified official snapshot found')
    data=load_data(args.snapshot or paths[0])
    upcoming=[e['id'] for e in data['events'] if utc(e['deadline_time'])>utc(data['as_of_at'])]
    if args.event is None and not upcoming: p.error('Snapshot has no upcoming GW')
    event=args.event or min(upcoming)
    report,_,_=run_prototype(data,event,BaselineConfig(prior_games=args.prior_games,attack_scale=args.attack_scale),
                             draws=args.draws,seed=args.seed,budget=args.budget,locked=args.locked,excluded=args.excluded)
    if args.output and args.output.resolve().is_relative_to(args.raw_root.resolve()):
        raise ValueError('Outputs cannot be written into raw storage')
    out=save_run(report,args.output)
    lookup={r['player_id']:r for r in report['players']}
    print(json.dumps(dict(output=str(out.resolve()),event=event,players=len(report['players']),
        cost=report['team']['cost'],captain=lookup[report['team']['captain']]['name'],
        team_distribution=report['team_distribution'],evaluation={k:report['evaluation'][k]
            for k in ('status','n','player_count','gameweeks','model','reference','minutes','dnp','excluded_counts')}),indent=2,ensure_ascii=False))
    return 0


if __name__=='__main__': raise SystemExit(main())

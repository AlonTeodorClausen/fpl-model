"""Explicit fresh full-pool capture. No network on Streamlit reruns."""
import argparse
import json
import sys
from pathlib import Path

if __package__ in {None,''}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

from fpl_model.full_player_capture import capture_all_players
from fpl_model.player_fixture_labels import normalize_snapshot, write_report
from fpl_model.io import SnapshotError
from fpl_model.data_sources.fpl_api import FPLSourceError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True)
    parser.add_argument('--raw-root',type=Path,default=Path(__file__).resolve().parents[1]/'data/raw')
    parser.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parents[1]/'artifacts/player_history')
    parser.add_argument('--request-interval',type=float,default=.5)
    args=parser.parse_args(argv)
    if args.output_root.resolve().is_relative_to(args.raw_root.resolve()):
        parser.error('Normalized outputs must be outside raw storage')
    def progress(row):
        if row['completed']==1 or row['completed']%20==0 or row['completed']==row['total'] or row['status']!='success':
            print(f"players {row['completed']}/{row['total']} | id={row['player_id']} {row['status']} attempts={row['attempts']}",flush=True)
    try:
        snapshot=capture_all_players(args.raw_root,season=args.season,
            request_interval=args.request_interval,progress=progress)
        bootstrap=json.loads((snapshot/'raw/fpl_api/bootstrap_static.json').read_bytes())
        result=normalize_snapshot(snapshot,season=args.season,
            element_ids=[p['id'] for p in bootstrap['elements']],allow_missing=True)
        report=write_report(result,args.output_root)
    except (FPLSourceError,SnapshotError,ValueError,OSError) as error:
        print(f'capture_failed: {type(error).__name__}; captured bytes remain under {args.raw_root}',file=sys.stderr)
        return 1
    q=result['quality']
    print(json.dumps(dict(snapshot=str(snapshot),report=str(report),
        players=len(bootstrap['elements']),attempted=q['attempted_players'],successful=q['successful_responses'],
        empty_histories=len(q['empty_history_players']),failed=q['failed_players'],
        deferred=q['deferred_players'],usable_observations=q['accepted_rows'],
        quarantined=q['quarantined_rows'],explicit_zero_rows=q['explicit_zero_minute_rows']),indent=2))
    return 2 if q['missing_response_players'] or q['quarantined_rows'] else 0


if __name__=='__main__': raise SystemExit(main())

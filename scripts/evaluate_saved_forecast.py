"""Score a frozen prediction against locally captured final official outcomes."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.prototype_data import load_data
from fpl_model.forecast_review import read_official_context, review_forecast


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast',required=True,type=Path)
    parser.add_argument('--outcome-snapshot',required=True,type=Path)
    parser.add_argument('--context-snapshot',type=Path,help='Optional newer official round status; never upgrades player labels')
    parser.add_argument('--output-root',type=Path,default=Path('artifacts/forecast_reviews'))
    args=parser.parse_args(argv)
    data=load_data(args.outcome_snapshot)
    context=read_official_context(args.context_snapshot or args.outcome_snapshot)
    source={k:data.get(k) for k in ('snapshot_id','snapshot_path','manifest_sha256','as_of_at')}
    out,result=review_forecast(args.forecast,data['histories'],args.output_root,
        season=data['season'],context=context,outcome_source=source)
    print(out)
    print(result['outcome_context']['status'])
    for name,r in result['variants'].items():print(name,r['status'],r['n'])
    return 0


if __name__=='__main__':raise SystemExit(main())

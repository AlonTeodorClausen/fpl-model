"""Compare exactly three minutes-frequency priors offline on an existing run."""
import argparse
import json
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.minutes_experiment import run_experiment, save_experiment, summarize_saved
from fpl_model.prototype_data import load_data


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--reference-run',type=Path,help='Run all three variants from a prototype report.json')
    source.add_argument('--saved-comparison',type=Path,help='Summarize existing seeds; no simulation or snapshot load')
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    if args.saved_comparison:
        report=summarize_saved(args.saved_comparison)
    else:
        anchor=json.loads(args.reference_run.read_text())
        report=run_experiment(load_data(Path(anchor['snapshot_path'])),anchor)
        report['anchor_path']=str(args.reference_run.resolve())
        report['anchor_file_sha256']=hashlib.sha256(args.reference_run.read_bytes()).hexdigest()
    out=save_experiment(report,args.output)
    print(json.dumps(dict(output=str(out.resolve()),n=report['n'],gameweeks=report['gameweeks'],
        seeds=report['seeds'],draws=report['draws'],data_role=report['data_role'],
        seed_summary=[r for r in report['seed_summary'] if r['dimension']=='scope' and r['group']=='all']),indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())

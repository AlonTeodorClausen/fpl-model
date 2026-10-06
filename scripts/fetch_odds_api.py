"""Explicit single-request EPL odds capture. Never called by the app/comparison."""
import argparse
import json
from pathlib import Path
import shlex
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.config import ROOT, DATA
from fpl_model.io import SnapshotWriter,SnapshotStateError
from fpl_model.data_sources.the_odds_api import fetch_odds


def _local_key(path):
    keys=[]
    try:
        for line in path.read_text().splitlines():
            line=line.strip()
            if line.startswith('export '):line=line[7:]
            if line.partition('=')[0].strip()=='ODDS_API_KEY':
                values=shlex.split(line.partition('=')[2],comments=True)
                if len(values)!=1:raise ValueError()
                keys.extend(values)
    except (OSError,ValueError):raise ValueError('Cannot read an unambiguous local ODDS_API_KEY') from None
    if len(keys)!=1:raise ValueError('Cannot read an unambiguous local ODDS_API_KEY')
    return keys[0]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path,default=ROOT/'.env')
    p.add_argument('--data-root',type=Path,default=DATA)
    a=p.parse_args(argv)
    try:key=_local_key(a.env_file)
    except ValueError:
        print('Missing or invalid local ODDS_API_KEY; no request made.');return 2
    w=SnapshotWriter(a.data_root/'raw')
    result=fetch_odds(w,api_key=key)
    try:path=w.finalize()
    except SnapshotStateError:path=w.staging_path
    print(json.dumps(dict(snapshot=str(path),status=result.status,http_status=result.http_status,quota=result.quota,
                          quota_note='last=call credits; used=cumulative; remaining=remaining credits; null=unavailable')))
    return 0 if result.status=='success' else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # Never echo a request URL, credential or exception message on CLI failure.
        print('Capture stopped safely ('+type(exc).__name__+'); no automatic retry.');raise SystemExit(1)

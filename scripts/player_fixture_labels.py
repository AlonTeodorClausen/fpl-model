"""Bounded official-FPL label workflow; explicit players, no Core or model joins.

capture: create one new immutable raw snapshot, then normalize it.
normalize: read one existing verified snapshot, with no network access.
Both write a new Step 2C report directory and never replace prior observations.
"""
import argparse
import re
import sys
from contextlib import nullcontext
from pathlib import Path

import requests

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fpl_model.data_sources.fpl_api import FPLSourceError, fetch_fpl_snapshot
from fpl_model.data_sources.fpl_player_history import fetch_player_histories, validate_element_ids
from fpl_model.io import SnapshotError, SnapshotWriter
from fpl_model.player_fixture_labels import normalize_snapshot, write_report


def capture_sample(raw_root, *, season, element_ids, session=None):
    ids = validate_element_ids(element_ids)
    if not re.fullmatch(r'\d{4}-\d{4}', season) or int(season[5:]) != int(season[:4]) + 1:
        raise ValueError('Expected explicit YYYY-YYYY season')
    writer = SnapshotWriter(raw_root)
    writer.set_run_metadata({'purpose': 'step2c_official_player_labels', 'season': season,
                             'element_ids': ','.join(map(str, ids))})
    try:
        with requests.Session() if session is None else nullcontext(session) as client:
            fetch_fpl_snapshot(writer, session=client)
            fetch_player_histories(writer, ids, session=client)
        return writer.finalize()
    except BaseException:
        writer.mark_failed()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for name in ('capture', 'normalize'):
        sub = modes.add_parser(name)
        sub.add_argument('--season', required=True)
        sub.add_argument('--elements', nargs='+', type=int, required=True)
        sub.add_argument('--output-root', type=Path, required=True)
        if name == 'capture':
            sub.add_argument('--raw-root', type=Path, required=True)
        else:
            sub.add_argument('--snapshot', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = (capture_sample(args.raw_root, season=args.season, element_ids=args.elements)
                    if args.mode == 'capture' else args.snapshot)
        result = normalize_snapshot(snapshot, season=args.season, element_ids=args.elements)
        directory = write_report(result, args.output_root)
    except (FPLSourceError, SnapshotError, ValueError, OSError) as error:
        # Error class only; arbitrary HTTP/OS exception text may disclose secrets.
        print(f'workflow_failed: {type(error).__name__}', file=sys.stderr)
        return 1
    print(f"snapshot: {snapshot}\nreport: {directory}\nlabels: {len(result['labels'])}\nquarantined: {len(result['quarantine'])}\nstates: {result['quality']['label_states']}")
    return 2 if result['quarantine'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

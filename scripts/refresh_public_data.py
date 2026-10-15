"""Refresh official inputs once and publish only a verified guest-ready version.

Use --no-fetch to publish an existing capture without network requests. Run this
as an operator job, never from a visitor's Streamlit rerun.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fpl_model.config import ROOT
from fpl_model.io import SnapshotError
from fpl_model.prototype_data import snapshot_paths
from fpl_model.public_data import publish_public_data
from fpl_model.quick_refresh import refresh_official_data, select_history_snapshot


def _now():
    return datetime.now(timezone.utc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--raw-root', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--publication-root', type=Path, default=ROOT / 'artifacts/public_data')
    parser.add_argument('--no-fetch', action='store_true', help='Publish existing verified captures only')
    parser.add_argument('--request-interval', type=float, default=.5)
    args = parser.parse_args(argv)

    def progress(row):
        if row['stage'] == 'context':
            print('Official context captured; checking player-history coverage', flush=True)
        elif row['stage'] == 'history':
            print('Player histories require refresh', flush=True)
        elif row['stage'] == 'player' and (row['completed'] == 1 or row['completed'] % 20 == 0
                                          or row['completed'] == row['total'] or row['status'] != 'success'):
            print(f"players {row['completed']}/{row['total']} | {row['status']}", flush=True)

    try:
        paths = snapshot_paths(args.raw_root)
        if args.no_fetch:
            if not paths:
                raise ValueError('No completed official snapshots are available')
            selected = paths[0]
            capture_status = 'existing_capture'
        else:
            result = refresh_official_data(args.raw_root, season=args.season,
                                           known_paths=paths, progress=progress,
                                           request_interval=args.request_interval)
            capture_status = result['status']
            if capture_status == 'history_partial':
                print('not_published: player histories are partial; active publication is unchanged')
                return 2
            selected = result['selected_snapshot']
        history = select_history_snapshot([*paths, selected], selected, season=args.season)
        if history is None:
            raise ValueError('No complete player-history snapshot precedes the selected context')
        published = publish_public_data(args.raw_root, args.publication_root,
                                        context_snapshot=selected, history_snapshot=history,
                                        season=args.season, checked_at=_now())
    except (ValueError, SnapshotError) as exc:
        print(f'not_published: {type(exc).__name__}; active publication is unchanged', file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f'refresh_failed: {type(exc).__name__}; active publication is unchanged', file=sys.stderr)
        return 1
    print(json.dumps(dict(status='published', capture_status=capture_status,
                          publication_id=published['publication_id'],
                          context_snapshot=published['context_snapshot'],
                          history_snapshot=published['history_snapshot'],
                          checked_at=published['checked_at'],
                          event=published['readiness']['event'],
                          deadline_at=published['readiness']['deadline_at']), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

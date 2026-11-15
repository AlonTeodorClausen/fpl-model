"""Move old transfer-forecast caches aside, keeping every cache a review may need.

Kept:
- the newest N caches (by modification time);
- every cache referenced by a saved forecast review;
- for every GW deadline, the cache of the last saved transfer report created
  before that deadline. That is the run the evaluation protocol scores, so its
  scenarios must survive until the round is reviewed (CRPS needs them).

Everything else is moved, never deleted, to artifacts/transfer_forecasts/_to_delete/.
Dry run by default; pass --apply to move.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
KEY = re.compile(r'[0-9a-f]{64}')


def _time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def protected_keys(artifacts):
    """Cache keys referenced by reviews or by the last pre-deadline report per GW."""
    keep = {}
    for path in (artifacts/'forecast_reviews').glob('*/report.json'):
        key = ((_read(path) or {}).get('forecast_metadata') or {}).get('cache_key')
        if isinstance(key, str):
            keep[key] = f'review {path.parent.name}'
    latest = {}
    for path in (artifacts/'transfers').glob('*/report.json'):
        report = _read(path) or {}
        forecast = report.get('forecast') or {}
        key, created = forecast.get('cache_key'), report.get('created_at')
        if not isinstance(key, str) or not created:
            continue
        for event, deadline in (forecast.get('deadlines') or {}).items():
            if _time(created) < _time(deadline):
                best = latest.get(event)
                if best is None or _time(created) > best[0]:
                    latest[event] = (_time(created), key, path.parent.name)
    for event, (_, key, name) in latest.items():
        keep.setdefault(key, f'last run before GW{event} deadline ({name})')
    return keep


def plan(artifacts, newest):
    root = artifacts/'transfer_forecasts'
    caches = sorted((p for p in root.iterdir() if p.is_dir() and KEY.fullmatch(p.name)),
                    key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []
    keep = protected_keys(artifacts)
    for path in caches[:newest]:
        keep.setdefault(path.name, 'newest')
    move = [p for p in caches if p.name not in keep]
    return caches, keep, move


def _size(path):
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--artifacts', type=Path, default=ROOT/'artifacts')
    parser.add_argument('--keep-newest', type=int, default=10)
    parser.add_argument('--apply', action='store_true', help='Move caches instead of only listing them')
    args = parser.parse_args(argv)
    if args.keep_newest < 0:
        parser.error('--keep-newest must be 0 or more')
    caches, keep, move = plan(args.artifacts, args.keep_newest)
    freed = sum(_size(p) for p in move)
    print(f'{len(caches)} caches · keep {len(caches)-len(move)} · move {len(move)} '
          f'({freed/1e6:.0f} MB)')
    for path in caches:
        if path.name in keep:
            print(f'  keep  {path.name[:12]}  {keep[path.name]}')
    if not args.apply:
        print('Dry run. Pass --apply to move the others to _to_delete/.')
        return 0
    target = args.artifacts/'transfer_forecasts'/'_to_delete'
    target.mkdir(parents=True, exist_ok=True)
    for path in move:
        shutil.move(str(path), str(target/path.name))
    print(f'Moved {len(move)} caches to {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

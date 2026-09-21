"""Offline Step 2E: verify existing six-player reports and audit deadline replay."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from scripts.audit_observations import load_report
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.replay_readiness import build_replay


def _bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _sources(report):
    """Only verified successful official raw files for the bounded report sample."""
    root = Path(report['quality']['snapshot_path'])
    manifest = verify_snapshot(root)
    ids = report['quality']['requested_element_ids']
    sources = []
    for entry in manifest['files']:
        if entry['source'] != 'fpl_api' or entry['outcome'] != 'success':
            continue
        path = entry['relative_path']
        kind, pid = None, None
        if path.endswith('/bootstrap_static.json'):
            kind = 'bootstrap'
        elif path.endswith('/fixtures.json'):
            kind = 'fixtures'
        else:
            for player in ids:
                if path.endswith(f'/element_summary/{player}.json'):
                    kind, pid = 'history', player
                    break
        if kind is None:
            continue
        reference = {**entry, 'source_snapshot_id': manifest['run_id'],
                     'manifest_sha256': report['quality']['manifest_sha256'],
                     'available_at': utc(entry.get('available_at', entry['retrieved_at'])).isoformat(),
                     'availability_basis': 'manifest_available_at' if 'available_at' in entry else 'retrieved_at'}
        sources.append(dict(kind=kind, player_id=pid, reference=reference,
                            payload=json.loads((root / path).read_bytes())))
    return sources


def audit_reports(report_paths, *, events):
    loaded = sorted([load_report(path) for path in report_paths], key=lambda r: r['quality']['source_snapshot_id'])
    if not loaded or len({r['quality']['source_snapshot_id'] for r in loaded}) != len(loaded):
        raise ValueError('Distinct verified Step 2C reports required')
    seasons = {r['quality']['season'] for r in loaded}
    samples = {tuple(r['quality']['requested_element_ids']) for r in loaded}
    if len(seasons) != 1 or len(samples) != 1:
        raise ValueError('Reports must use one season and the same bounded player sample')
    sources = [s for r in loaded for s in _sources(r)]
    result = build_replay(sources, [o for r in loaded for o in r['labels']],
                          quarantine=[q for r in loaded for q in r['quarantine']],
                          season=next(iter(seasons)), player_ids=list(next(iter(samples))), events=events)
    result['sources'] = [dict(report_path=r['path'], report_sha256=r['report_sha256'],
                              raw_snapshot_path=r['quality']['snapshot_path'],
                              source_snapshot_id=r['quality']['source_snapshot_id'],
                              manifest_sha256=r['quality']['manifest_sha256']) for r in loaded]
    # This is diagnostics only. It never becomes an input reference or changes a
    # missing input into an available one.
    result['capture_coverage'] = [dict(kind=kind, player_id=pid,
        earliest_available_at=min(utc(s['reference']['available_at']) for s in sources
                                  if (s['kind'], s['player_id']) == (kind, pid)).isoformat())
        for kind, pid in sorted({(s['kind'], s['player_id']) for s in sources}, key=lambda x: (x[0], x[1] or 0))]
    result['summary']['by_event'] = {str(event): dict(sorted(Counter(r['readiness'] for r in result['records']
                                        if r['event'] == event).items())) for event in sorted(set(events))}
    result['summary']['target_references'] = dict(sorted(Counter(t['status'] for r in result['records'] for t in r['targets']).items()))
    result['summary']['quarantined_source_rows'] = sum(len(r['quarantine']) for r in loaded)
    result['audit_id'] = 'step2e_' + hashlib.sha256(_bytes(result)).hexdigest()[:16]
    return result


def write_audit(report, output_root):
    root = Path(output_root).resolve()
    for source in report['sources']:
        if (root.is_relative_to(Path(source['raw_snapshot_path']).resolve().parent)
                or root.is_relative_to(Path(source['report_path']).resolve())):
            raise ValueError('Output must be outside protected inputs')
    directory = root / report['audit_id']
    directory.mkdir(parents=True, exist_ok=False)
    non_ready = [{k: r[k] for k in ('player_id', 'event', 'forecast_origin_at', 'readiness', 'reasons')}
                 for r in report['records'] if r['readiness'] != 'ready']
    trace = [r for r in report['records'] if r['player_id'] == report['player_ids'][0]]
    payloads = {'manifest.json': report,
                'quality.json': dict(audit_id=report['audit_id'], summary=report['summary'], non_ready=non_ready),
                'provenance_trace.json': dict(audit_id=report['audit_id'], origins=report['origins'],
                    capture_coverage=report['capture_coverage'], records=trace,
                    warning='Targets and origin-definition evidence are not information inputs.')}
    digests = {}
    for name, value in payloads.items():
        body = _bytes(value)
        with (directory / name).open('xb') as stream:
            stream.write(body)
        digests[name] = hashlib.sha256(body).hexdigest()
    with (directory / 'COMPLETE.json').open('xb') as stream:
        stream.write(_bytes(dict(schema_version=1, files=digests)))
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, nargs='+', required=True)
    parser.add_argument('--events', type=int, nargs='+', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit_reports(args.reports, events=args.events)
    directory = write_audit(result, args.output_root)
    print(f"audit: {directory}\nsummary: {json.dumps(result['summary'], sort_keys=True)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Phase A only: fresh official capture, six-player readiness, immutable input freeze."""
import argparse
import json
import re
import sys
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path

import requests

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fpl_model.data_sources.fpl_api import FPLSourceError, fetch_fpl_snapshot
from fpl_model.data_sources.fpl_player_history import fetch_player_histories
from fpl_model.forecast_freeze import (SAMPLE_PLAYERS, deadline_observations, prepare_freeze,
                                     utc_now, verify_freeze, write_freeze)
from fpl_model.io import SnapshotError, SnapshotWriter
from fpl_model.label_contracts import utc
from fpl_model.player_fixture_labels import normalize_snapshot, write_report
from fpl_model.replay_readiness import build_replay, forecast_origin
from scripts.audit_observations import load_report
from scripts.audit_replay_readiness import _sources


def parse_max_age(value):
    match = re.fullmatch(r'([1-9][0-9]*)(s|m|h)', value)
    if not match:
        raise ValueError('Maximum input age must be a positive duration such as 30m')
    return timedelta(seconds=int(match[1]) * {'s': 1, 'm': 60, 'h': 3600}[match[2]])


def _event_id(bootstrap, requested, capture_started_at):
    events = bootstrap['events']
    if len({e['id'] for e in events}) != len(events):
        raise ValueError('Conflicting official event identities')
    if requested == 'next':
        future = sorted((utc(e['deadline_time']), e['id']) for e in events
                        if utc(e['deadline_time']) > capture_started_at)
        if not future or (len(future) > 1 and future[0][0] == future[1][0]):
            raise ValueError('No unique next official deadline')
        return future[0][1]
    event = int(requested)
    if event <= 0 or not any(e['id'] == event for e in events):
        raise ValueError('Requested event absent from fresh official bootstrap')
    return event


def _prior_deadlines(freeze_root, prior_reports, season, event):
    versions = []
    # Only completed prior attempts are reusable evidence, never fallback inputs.
    # Incomplete directories remain diagnostic and cannot become valid freezes.
    for marker in sorted(Path(freeze_root).glob('step2fa_*/COMPLETE.json')):
        prior = verify_freeze(marker.parent, require_ready=False)
        if prior['season'] == season:
            versions.extend(prior['deadline']['observations'])
    for path in prior_reports:
        prior = load_report(path)
        if prior['quality']['season'] != season:
            raise ValueError('Prior deadline report belongs to another season')
        origin = forecast_origin(_sources(prior), event)
        versions.extend(deadline_observations({'origins': [origin]}))
    return versions


def run_capture(*, raw_root, report_root, freeze_root, season, event, max_input_age,
                prior_reports=(), session=None, clock=utc_now):
    if not re.fullmatch(r'\d{4}-\d{4}', season) or int(season[5:]) != int(season[:4]) + 1:
        raise ValueError('Explicit YYYY-YYYY season required')
    if not isinstance(max_input_age, timedelta) or max_input_age <= timedelta(0):
        raise ValueError('Explicit positive freshness threshold required')
    for root in (report_root, freeze_root):
        if Path(root).resolve().is_relative_to(Path(raw_root).resolve()):
            raise ValueError('Derived outputs must be outside raw storage')
    started = utc(clock())
    writer = SnapshotWriter(raw_root, clock=clock)
    writer.set_run_metadata(dict(purpose='step2fa_prospective_freeze', season=season,
                                element_ids=','.join(map(str, SAMPLE_PLAYERS))))
    try:
        with requests.Session() if session is None else nullcontext(session) as client:
            fetch_fpl_snapshot(writer, session=client, clock=clock)
            # Select once against the run start, not again after a deadline crosses.
            bootstrap = json.loads((writer.staging_path / 'raw/fpl_api/bootstrap_static.json').read_bytes())
            selected_event = _event_id(bootstrap, event, started)
            fetch_player_histories(writer, SAMPLE_PLAYERS, session=client, clock=clock)
        snapshot = writer.finalize()
    except BaseException:
        writer.mark_failed()
        raise
    normalized = normalize_snapshot(snapshot, season=season, element_ids=SAMPLE_PLAYERS)
    report_path = write_report(normalized, report_root)
    report = load_report(report_path)
    replay = build_replay(_sources(report), report['labels'], quarantine=report['quarantine'],
                          season=season, player_ids=list(SAMPLE_PLAYERS), events=[selected_event])
    previous = _prior_deadlines(freeze_root, prior_reports, season, selected_event)
    source_report = dict(report_path=str(report_path), report_sha256=report['report_sha256'],
                         raw_snapshot_path=str(snapshot), manifest_sha256=report['quality']['manifest_sha256'])
    frozen = prepare_freeze(replay, fresh_snapshot_id=writer.run_id,
                            capture_started_at=started, freeze_created_at=utc(clock()),
                            max_input_age=max_input_age, deadline_versions=previous, source_report=source_report)
    return write_freeze(frozen, freeze_root, clock=clock)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--event', required=True, help='Official event ID, or next (fixed at capture start)')
    parser.add_argument('--max-input-age', required=True, help='Explicit positive duration: 30m, 1h, etc.')
    parser.add_argument('--raw-root', required=True, type=Path)
    parser.add_argument('--report-root', required=True, type=Path)
    parser.add_argument('--freeze-root', required=True, type=Path)
    parser.add_argument('--prior-report', action='append', default=[], type=Path,
                        help='Optional verified Step 2C report for older deadline evidence only')
    args = parser.parse_args(argv)
    try:
        path = run_capture(raw_root=args.raw_root, report_root=args.report_root, freeze_root=args.freeze_root,
                           season=args.season, event=args.event, max_input_age=parse_max_age(args.max_input_age),
                           prior_reports=args.prior_report)
        frozen = verify_freeze(path, require_ready=False)
    except (FPLSourceError, SnapshotError, ValueError, OSError, KeyError) as error:
        print(f'freeze_failed: {type(error).__name__}; no previous capture was substituted', file=sys.stderr)
        return 1
    print(f"freeze: {path}\nevent: {frozen['event']}\nforecast_origin_at: {frozen['forecast_origin_at']}\n"
          f"status: {frozen['status']}\nreasons: {','.join(frozen['reasons']) or 'none'}\n"
          f"freshness_max_seconds: {frozen['freshness']['max_input_age_seconds']}\n"
          f"freshness_passed: {frozen['freshness']['passed']}\n"
          f"deadline_revision: {frozen['deadline']['revision_detected']}\nphase_b: not_started")
    if frozen['deadline']['revision_detected']:
        print('deadline_observations: ' + json.dumps([
            dict(deadline=v['forecast_origin_at'], retrieved_at=v['evidence']['reference']['retrieved_at'])
            for v in frozen['deadline']['observations']], sort_keys=True))
    return 0 if frozen['status'] == 'ready' else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Explicit, bounded official element-summary capture; the caller owns finalization.

Like the existing official FPL adapter: one attempt, connect/read timeout 10/30s,
no redirects, no automatic retry after a required failure. A retry needs a new
snapshot. Raw means response.content bytes, including HTTP content decoding.
"""
import json
from contextlib import nullcontext

import requests

from fpl_model.data_sources.fpl_api import FPLSourceError, FPLContractError, _utc_now
from fpl_model.io import SnapshotWriter


def validate_element_ids(element_ids):
    ids = tuple(element_ids)
    if not 1 <= len(ids) <= 20 or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Supply 1–20 distinct positive integer element IDs explicitly')
    return tuple(sorted(ids))


def fetch_player_histories(writer, element_ids, *, session=None, clock=_utc_now):
    ids = validate_element_ids(element_ids)
    if not isinstance(writer, SnapshotWriter):
        raise TypeError('Expected SnapshotWriter')
    with requests.Session() if session is None else nullcontext(session) as client:
        for element_id in ids:
            url = f'https://fantasy.premierleague.com/api/element-summary/{element_id}/'
            relative = f'fpl_api/element_summary/{element_id}.json'
            started = clock()
            if started.tzinfo is None or started.utcoffset() is None:
                raise ValueError('Request clock must be timezone-aware')
            provenance = dict(source='fpl_api', required=True, request_url=url,
                              request_started_at=started, request_context={'element_id': str(element_id)})
            try:
                with client.get(url, timeout=(10, 30), allow_redirects=False) as response:
                    body = response.content
                    retrieved = clock()
                    status = response.status_code
                    media = response.headers.get('Content-Type', '')
            except (requests.RequestException, KeyboardInterrupt, SystemExit) as exc:
                writer.record_failure(**provenance, error_code='transport_error')
                if not isinstance(exc, requests.RequestException):
                    raise
                raise FPLSourceError('Required player history transport failure') from None
            writer.write_raw(relative, body, **provenance, retrieved_at=retrieved,
                             available_at=retrieved, http_status=status, content_type=media)
            if not 200 <= status < 300:
                writer.record_failure(**provenance, error_code='http_error', relative_path='raw/' + relative)
                raise FPLSourceError(f'Required player history returned HTTP {status}')
            try:
                if media.partition(';')[0].strip().lower() != 'application/json':
                    raise ValueError
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(payload.get('history'), list):
                    raise ValueError
                if not all(isinstance(row, dict) for row in payload['history']):
                    raise ValueError
            except (ValueError, TypeError):
                writer.record_failure(**provenance, error_code='invalid_payload', relative_path='raw/' + relative)
                raise FPLContractError('Required player history failed its source contract') from None

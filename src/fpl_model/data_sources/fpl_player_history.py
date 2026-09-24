"""Official element-summary capture; raw attempts are immutable, caller finalizes.

Legacy sample callers remain fail-fast/required. Whole-pool captures explicitly
opt into optional player requests, pacing and bounded retry, preserving every
body. No failed request is replaced by an old snapshot or an empty history.
"""
import json
import math
import time
from contextlib import nullcontext
from email.utils import parsedate_to_datetime

import requests

from fpl_model.data_sources.fpl_api import FPLSourceError, FPLContractError, _utc_now
from fpl_model.io import SnapshotWriter


def validate_element_ids(element_ids):
    ids = tuple(element_ids)
    if not ids or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Supply distinct positive integer element IDs explicitly')
    return tuple(sorted(ids))


def retry_delay(value, attempt, retrieved_at, maximum=30.0):
    """Numeric/date Retry-After; defer rather than retry before a long server wait."""
    fallback = float(2 ** (attempt - 1))
    try:
        delay = float(value) if value.strip().isdigit() else (parsedate_to_datetime(value) - retrieved_at).total_seconds()
        if not math.isfinite(delay): raise ValueError
    except (ValueError, TypeError, OverflowError):
        delay = fallback
    return None if delay > maximum else max(fallback, delay)


def fetch_player_histories(writer, element_ids, *, session=None, clock=_utc_now,
                           required=True, max_attempts=1, request_interval=0.0,
                           sleep=time.sleep, progress=None):
    ids = validate_element_ids(element_ids)
    if not isinstance(writer, SnapshotWriter): raise TypeError('Expected SnapshotWriter')
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError('Use one to three attempts')
    if required and max_attempts != 1:
        raise ValueError('Retries require explicit partial-capture policy')
    if not math.isfinite(request_interval) or request_interval < 0:
        raise ValueError('Nonnegative finite request interval required')
    results=[]; stop_pool=False
    with requests.Session() if session is None else nullcontext(session) as client:
        for index, element_id in enumerate(ids):
            url = f'https://fantasy.premierleague.com/api/element-summary/{element_id}/'
            context={'element_id':str(element_id)}
            common=dict(source='fpl_api',required=required,request_url=url,request_context=context)
            if stop_pool:
                writer.record_failure(**common,outcome='skipped',error_code='rate_limit_deferred')
                result=dict(player_id=element_id,status='deferred',attempts=0,raw_path=None)
            else:
                if index and request_interval: sleep(request_interval)
                for attempt in range(1,max_attempts+1):
                    relative = (f'fpl_api/attempt_{attempt:02d}/element_summary/{element_id}.json'
                                if max_attempts>1 else f'fpl_api/element_summary/{element_id}.json')
                    started=clock()
                    if started.tzinfo is None or started.utcoffset() is None:
                        raise ValueError('Request clock must be timezone-aware')
                    provenance={**common,'request_started_at':started}
                    result=dict(player_id=element_id,status='request_failed',attempts=attempt,
                                raw_path=None,request_started_at=started.isoformat(),retrieved_at=None)
                    try:
                        with client.get(url,timeout=(10,30),allow_redirects=False) as response:
                            body=response.content;retrieved=clock();status=response.status_code
                            media=response.headers.get('Content-Type','')
                            retry_after=response.headers.get('Retry-After','')
                    except (requests.RequestException,KeyboardInterrupt,SystemExit) as exc:
                        writer.record_failure(**provenance,error_code='transport_error')
                        if not isinstance(exc,requests.RequestException): raise
                        if required: raise FPLSourceError('Required player history transport failure') from None
                        if attempt<max_attempts and isinstance(exc,(requests.Timeout,requests.ConnectionError)):
                            sleep(max(request_interval,2**(attempt-1)));continue
                        break
                    result['retrieved_at']=retrieved.isoformat()
                    writer.write_raw(relative,body,**provenance,retrieved_at=retrieved,
                                     available_at=retrieved,http_status=status,content_type=media)
                    if not 200<=status<300:
                        writer.record_failure(**provenance,error_code='http_error',relative_path='raw/'+relative)
                        result['status']='http_error';result['http_status']=status
                        if required: raise FPLSourceError(f'Required player history returned HTTP {status}')
                        delay=retry_delay(retry_after,attempt,retrieved)
                        if attempt<max_attempts and (status==429 or 500<=status<600) and delay is not None:
                            sleep(max(request_interval,delay));continue
                        # Do not move straight to the next player while the API is rate-limiting us.
                        stop_pool=status==429 or (500<=status<600 and delay is None)
                        if (not stop_pool and 500<=status<600 and retry_after.strip()
                                and index+1<len(ids)):
                            # Retry-After also governs the next player's request
                            # when this player's final attempt has been exhausted.
                            sleep(max(request_interval,delay))
                        break
                    try:
                        if media.partition(';')[0].strip().lower()!='application/json': raise ValueError
                        payload=json.loads(body)
                        if not isinstance(payload,dict) or not isinstance(payload.get('history'),list): raise ValueError
                        if not all(isinstance(row,dict) for row in payload['history']): raise ValueError
                    except (ValueError,TypeError):
                        writer.record_failure(**provenance,error_code='invalid_payload',relative_path='raw/'+relative)
                        result['status']='contract_failed'
                        if required: raise FPLContractError('Required player history failed its source contract') from None
                        break
                    result.update(status='success',raw_path='raw/'+relative,history_rows=len(payload['history']))
                    break
            results.append(result)
            if progress: progress({**result,'completed':index+1,'total':len(ids)})
    return results

"""Explicit optional EPL acquisition. One request, no hidden retries/redirects.

Never persist authenticated URLs, request headers or exception messages. Capture
raw bytes before contract validation. Caller owns finalization. API credit headers
are allowlisted, not an excuse to store the response/request objects.
"""
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import json
import logging
import re
import requests
from fpl_model.io import SnapshotWriter

URL = 'https://api.the-odds-api.com/v4/sports/soccer_epl/odds/'
PARAMS = dict(markets='h2h,totals',regions='uk',oddsFormat='decimal',dateFormat='iso')
TIMEOUT = (10,40)


@dataclass(frozen=True)
class OddsFetchResult:
    status: str
    raw_path: str | None
    quota: dict
    http_status: int | None = None


@contextmanager
def _quiet_transport():
    # urllib3 debug and http.client debug can expose the authenticated URL.
    previous=logging.root.manager.disable
    debug=http.client.HTTPConnection.debuglevel
    logging.disable(logging.CRITICAL)
    http.client.HTTPConnection.debuglevel=0
    try:yield
    finally:
        logging.disable(previous)
        http.client.HTTPConnection.debuglevel=debug


def fetch_odds(writer: SnapshotWriter, *, api_key: str, session=None,
               clock=lambda: datetime.now(timezone.utc)) -> OddsFetchResult:
    provenance=dict(source='the_odds_api',required=False,request_url=URL,
                    request_params=PARAMS,request_context={'sport':'soccer_epl'})
    if not api_key:
        writer.record_failure(**provenance,outcome='skipped',error_code='missing_credentials')
        return OddsFetchResult('skipped',None,{})
    if not re.fullmatch(r'[A-Za-z0-9_-]+',api_key):raise ValueError('Invalid credential format')
    started=clock()
    context=requests.Session() if session is None else nullcontext(session)
    try:
        with _quiet_transport(),context as client:
            with client.get(URL,params={**PARAMS,'apiKey':api_key},timeout=TIMEOUT,allow_redirects=False) as response:
                body=response.content;retrieved=clock();status=response.status_code
                content_type=response.headers.get('Content-Type','').replace(api_key,'[REDACTED]')
                quota={}
                for name in ('last','used','remaining'):
                    value=response.headers.get('x-requests-'+name,'')
                    quota[name]=int(value) if re.fullmatch(r'[0-9]{1,12}',value) else None
    except requests.RequestException as exc:
        writer.record_failure(**provenance,request_started_at=started,
                              error_code='timeout' if isinstance(exc,requests.Timeout) else 'transport_error')
        return OddsFetchResult('request_failed',None,{})
    relative='the_odds_api/soccer_epl/odds.json';raw_path='raw/'+relative
    echoed=api_key.encode() in body
    if echoed:body=body.replace(api_key.encode(),b'[REDACTED]')
    provenance['request_context'].update({'quota_'+k:str(v) for k,v in quota.items() if v is not None})
    provenance['request_context']['response_credentials_redacted']=str(echoed).lower()
    writer.write_raw(relative,body,**provenance,request_started_at=started,retrieved_at=retrieved,
                     available_at=retrieved,http_status=status,content_type=content_type)
    error='credential_echo_redacted' if echoed else 'http_error' if status!=200 else None
    if error is None:
        try:
            payload=json.loads(body)
            if not isinstance(payload,list) or any(not isinstance(e,dict) or e.get('sport_key')!='soccer_epl' for e in payload):
                error='invalid_payload'
        except (ValueError,UnicodeError):error='invalid_payload'
    if error:
        writer.record_failure(**provenance,request_started_at=started,relative_path=raw_path,error_code=error)
    return OddsFetchResult(error or 'success',raw_path if not error else None,quota,status)

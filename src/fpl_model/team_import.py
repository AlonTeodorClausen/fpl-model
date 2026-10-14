"""Explicit public FPL team import. No login, private endpoint or guessed money."""
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from urllib.parse import urlsplit
import requests
from fpl_model.io import SnapshotWriter
from fpl_model.label_contracts import utc
from fpl_model.optimizer.squad import COUNTS

BASE='https://fantasy.premierleague.com/api/'


def parse_team_id(value):
    text=str(value).strip()
    if text.startswith('fantasy.premierleague.com/'):
        text='https://'+text
    if not re.fullmatch(r'[0-9]+',text):
        u=urlsplit(text)
        if u.scheme not in ('http','https') or u.netloc!='fantasy.premierleague.com':
            raise ValueError('Indsæt dit numeriske hold-ID eller et officielt FPL-holdlink.')
        match=re.fullmatch(r'/(?:en/)?entry/([0-9]+)(?:/(?:event/[0-9]+|history))?/?',u.path)
        if not match:raise ValueError('Linket skal være til holdets point- eller historikside med /entry/ID/.')
        text=match[1]
    if not 0<int(text)<=1000000000:raise ValueError('Ugyldigt hold-ID.')
    return int(text)


def _integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Uventet format i det offentlige FPL-svar.')
    return value


def _fetch(writer,client,endpoint,filename,clock):
    url=BASE+endpoint;started=clock()
    try:
        with client.get(url,timeout=(10,30),allow_redirects=False) as r:
            body=r.content;status=r.status_code;media=r.headers.get('Content-Type','');retrieved=clock()
    except requests.RequestException:
        writer.record_failure(source='fpl_team',required=True,request_url=url,request_started_at=started,error_code='transport')
        raise ValueError('FPL kunne ikke kontaktes. Dit gemte hold er uændret; prøv igen senere.') from None
    writer.write_raw(filename,body,source='fpl_team',required=True,request_started_at=started,
                     retrieved_at=retrieved,available_at=retrieved,request_url=url,http_status=status,content_type=media)
    if status!=200:
        if status==404:raise ValueError('Holdet eller den offentlige GW-opstilling blev ikke fundet (HTTP 404). Kontrollér hold-ID.')
        raise ValueError(f'FPL svarede HTTP {status}. Ingen automatisk gentagelse; prøv igen senere.')
    try:
        if media.partition(';')[0].strip().lower()!='application/json':raise ValueError()
        return json.loads(body),utc(retrieved).isoformat()
    except (ValueError,TypeError):
        writer.record_failure(source='fpl_team',required=True,request_url=url,error_code='invalid_json',relative_path='raw/'+filename)
        raise ValueError('FPL returnerede ikke et gyldigt JSON-svar. Dit gemte hold er uændret.') from None


def capture_team(value,raw_root,*,session=None,clock=lambda:datetime.now(timezone.utc)):
    """Three bounded public requests on a button press; finalize only validated imports."""
    entry_id=parse_team_id(value);w=SnapshotWriter(raw_root,clock=clock)
    w.set_run_metadata(dict(purpose='public_team_import',entry_id=str(entry_id)))
    try:
        with requests.Session() if session is None else nullcontext(session) as client:
            prefix=f'fpl_team/{entry_id}/'
            boot,_=_fetch(w,client,'bootstrap-static/',prefix+'bootstrap.json',clock)
            entry,_=_fetch(w,client,f'entry/{entry_id}/',prefix+'entry.json',clock)
            if entry.get('id')!=entry_id:raise ValueError('FPL-svaret matcher ikke det ønskede hold-ID.')
            event=entry.get('current_event')
            if event is None:raise ValueError('Holdet har endnu ingen offentlig GW-opstilling. Brug manuel indtastning indtil første deadline.')
            _integer(event,1,38)
            picks,observed=_fetch(w,client,f'entry/{entry_id}/event/{event}/picks/',prefix+f'picks_gw{event}.json',clock)
        rows=picks['picks'];history=picks['entry_history']
        if history['event']!=event:raise ValueError('FPL returnerede en anden GW end den ønskede.')
        if picks.get('active_chip')=='freehit':
            raise ValueError('Seneste offentlige hold er et midlertidigt Free Hit-hold. Indtast din faste trup manuelt; den bliver ikke gættet.')
        if len(rows)!=15 or {_integer(p['position'],1,15) for p in rows}!=set(range(1,16)):
            raise ValueError('Den offentlige opstilling indeholder ikke 15 entydige pladser.')
        ids=[_integer(p['element'],1,1000000) for p in rows]
        pool={p['id']:p for p in boot['elements']}
        if len(set(ids))!=15 or not set(ids)<=pool.keys():raise ValueError('Opstillingen har dubletter eller ukendte spiller-ID’er.')
        if Counter(pool[i]['element_type'] for i in ids)!=COUNTS:raise ValueError('FPL-holdets positioner matcher ikke 2/5/5/3.')
        events={e['id']:e for e in boot['events']};deadline=utc(events[event]['deadline_time'])
        if deadline>utc(observed):raise ValueError('Den offentlige opstilling gælder en deadline, der endnu ikke er passeret.')
        start=utc(events[1]['deadline_time']);season=f'{start.year}-{start.year+1}'
        bank=history.get('bank')
        if bank is not None:_integer(bank,0,100000)
        result=dict(entry_id=entry_id,name=entry.get('name') or f'FPL #{entry_id}',event=event,season=season,
            observed_at=observed,deadline_at=deadline.isoformat(),bank_at_deadline=bank,
            active_chip=picks.get('active_chip'),picks=sorted(rows,key=lambda p:p['position']),
            players=[{k:pool[i].get(k) for k in ('id','code','team','element_type','web_name','now_cost')} for i in ids])
        path=w.finalize()
        result.update(snapshot_path=str(path),snapshot_id=w.run_id)
        return result
    except BaseException as exc:
        w.mark_failed()
        if isinstance(exc,(KeyError,TypeError,AttributeError)):
            raise ValueError('FPL-svaret mangler nødvendige holdoplysninger; ingen ændringer er gemt.') from None
        raise


def make_draft(imported,data,*,previous=None,keep_existing=False):
    if imported['season']!=data['season']:raise ValueError('Holdets sæson matcher ikke dit valgte datagrundlag.')
    pool={p['id']:p for p in data['players']}
    for p in imported['players']:
        old=pool.get(p['id'])
        if old is None or p.get('code') is None or any(old.get(k)!=p.get(k) for k in ('code','team','element_type')):
            raise ValueError('Spilleridentitet eller klub matcher ikke prognosedata. Opdatér det officielle datagrundlag først.')
    provenance={k:imported[k] for k in ('entry_id','event','observed_at','deadline_at','snapshot_id','snapshot_path')}
    if keep_existing:
        if not previous or previous.get('season')!=data['season'] or {p['player_id'] for p in previous['players']}!={p['id'] for p in imported['players']}:
            raise ValueError('Lokal økonomi kan kun genbruges for præcis samme trup og sæson.')
        draft=deepcopy(previous);provenance['economy_source']='explicitly_reused_local_values'
    else:
        draft=dict(schema_version=1,season=data['season'],players=[dict(player_id=p['id'],selling_price=None) for p in imported['players']],
                   bank=imported['bank_at_deadline'],free_transfers=None,transfers_made=None)
        provenance['economy_source']='bank_at_deadline_other_values_unknown'
    draft['import_provenance']=provenance
    return draft

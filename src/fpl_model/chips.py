"""Season-specific chip contracts. No forecasting and no writes to an FPL account."""
from copy import deepcopy
from fpl_model.label_contracts import utc

CHIPS=('wildcard','free_hit','triple_captain','bench_boost')
LABELS={'wildcard':'Wildcard','free_hit':'Free Hit','triple_captain':'Triple Captain','bench_boost':'Bench Boost'}
REBUILDS=('wildcard','free_hit')
VERSION='chips_2026_27_v1'


def _int(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Ugyldigt heltal i chipoplysninger.')
    return value


def normalize_chip_inventory(profile):
    raw=profile.get('chip_inventory')
    if raw is None:
        return dict(version=1,season=profile['season'],entry_start_event=None,active_chip=None,
            halves={h:{c:dict(status='unknown',used_event=None,source=None,confirmed_at=None) for c in CHIPS}
                    for h in ('first','second')})
    inv=deepcopy(raw)
    if inv.get('version')!=1 or inv.get('season')!=profile['season']:raise ValueError('Chipstatus har forkert version/sæson.')
    start=inv.get('entry_start_event')
    if start is not None:_int(start,1,38)
    used=[]
    for h,(lo,hi) in {'first':(1,19),'second':(20,38)}.items():
        half=inv.get('halves',{}).get(h,{})
        if set(half)!=set(CHIPS):raise ValueError('Chipstatus mangler et helt sæt.')
        for name,row in half.items():
            if row.get('status') not in ('unknown','available','used'):raise ValueError('Ukendt chipstatus.')
            event=row.get('used_event')
            if event is not None:
                _int(event,lo,hi)
                if row['status']!='used':raise ValueError('Brugt GW kræver status brugt.')
                used.append((event,name))
            if row['status']!='unknown':
                if not row.get('source') or not row.get('confirmed_at'):raise ValueError('Bekræft chipstatus og tidspunkt.')
                utc(row['confirmed_at'])
    if len({e for e,_ in used})!=len(used):raise ValueError('Kun én chip pr. GW.')
    fh=sorted(e for e,c in used if c=='free_hit')
    if any(b-a==1 for a,b in zip(fh,fh[1:])):raise ValueError('Free Hit kan ikke bruges i to GWs i træk.')
    active=inv.get('active_chip')
    if active is not None:
        _int(active.get('event'),1,38)
        if active.get('name') not in CHIPS:raise ValueError('Ukendt aktiv chip.')
        if any(e==active['event'] and c!=active['name'] for e,c in used):
            raise ValueError('Aktiv chip kolliderer med en allerede registreret chip i samme GW.')
    return inv


def validate_chip_plan(plan,profile,events,*,deadlines,origin_at):
    inv=normalize_chip_inventory(profile);result={}
    for key,name in plan.items():
        if isinstance(key,bool):raise ValueError('Ugyldig chip-GW.')
        event=int(key)
        if str(event)!=str(key) or event in result:raise ValueError('Tvetydig chip-GW.')
        if event not in events or name not in CHIPS:raise ValueError('Chip/GW findes ikke i den valgte horisont.')
        result[event]=name
    active=inv.get('active_chip')
    if active and active['event'] in events and result.get(active['event'])!=active['name']:
        raise ValueError('En allerede aktiv chip er bindende i denne plan.')
    if not result:return {}
    if profile['season']!='2026-2027':raise ValueError('Chipregler er kun verificeret for 2026-2027.')
    recorded={r['used_event']:c for h in inv['halves'].values() for c,r in h.items() if r.get('used_event') is not None}
    if active:recorded[active['event']]=active['name']
    seen=set();fh=[active['event']] if active and active['name']=='free_hit' else []
    for half in inv['halves'].values():
        if half['free_hit'].get('used_event') is not None:fh.append(half['free_hit']['used_event'])
    for event,name in sorted(result.items()):
        if event in recorded and recorded[event]!=name:raise ValueError('Kun én chip pr. GW, inklusive allerede registrerede chips.')
        deadline=deadlines.get(event,deadlines.get(str(event)))
        if deadline is None or utc(deadline)<=utc(origin_at):raise ValueError('Chip kræver en fremtidig officiel deadline.')
        half='first' if event<=19 else 'second';item=(half,name)
        if active and active['name']==name and active['event']!=event and (active['event']<=19)==(event<=19):
            raise ValueError('Den aktive chip er allerede brugt i denne sæsonhalvdel.')
        if item in seen:raise ValueError('Samme chip kan kun bruges én gang pr. sæsonhalvdel.')
        seen.add(item);row=inv['halves'][half][name]
        is_active=active==dict(event=event,name=name)
        if row['status']!='available' and not (is_active and row['status']=='used' and row.get('used_event')==event):
            raise ValueError(f'{LABELS[name]} er brugt eller har ukendt status.')
        start=inv.get('entry_start_event')
        if name in REBUILDS and (start is None or event<=start):
            raise ValueError('Bekræft første spille-GW; WC/FH kan ikke bruges i den første GW.')
        if name=='free_hit':
            previous=inv['halves']['first']['free_hit']
            if event==20 and previous['status'] in ('used','unknown') and previous.get('used_event') is None:
                raise ValueError('Bekræft om første Free Hit blev brugt i GW19 før et Free Hit i GW20.')
            fh.append(event)
    fh=sorted(set(fh))
    if any(b-a==1 for a,b in zip(fh,fh[1:])):raise ValueError('Free Hit kan ikke bruges i to GWs i træk.')
    if min(events) in result and result[min(events)] in REBUILDS and profile['transfers_made']:
        resolve_chip_origin(profile,result[min(events)])
        if profile['pre_transfer_state']['event']!=min(events):raise ValueError('Tilstanden før transfers gælder en anden GW.')
    return result


def chip_transfer_account(free,count,chip=None):
    _int(free,0,5);_int(count,0,20)
    if chip not in (None,*CHIPS):raise ValueError('Ukendt chip.')
    if chip in REBUILDS:return dict(used=0,remaining=free,next_gw=free,hits=0)
    used=min(free,count);remaining=free-used
    return dict(used=used,remaining=remaining,next_gw=min(5,remaining+1),hits=4*max(0,count-free))


def resolve_chip_origin(profile,first_chip=None):
    result=deepcopy(profile)
    if first_chip not in REBUILDS or not profile['transfers_made']:return result
    state=profile.get('pre_transfer_state')
    if not state:raise ValueError('WC/FH kræver bekræftet trup, bank og FT fra før ugens transfers.')
    from fpl_model.my_team import _shape
    for key in ('players','bank','free_transfers'):
        if key not in state:raise ValueError('Manglende tilstand før transfers.')
        result[key]=deepcopy(state[key])
    _int(state.get('event'),1,38);_int(state.get('existing_hits'),0,80)
    if state['existing_hits']%4:raise ValueError('Eksisterende hits skal være delelige med fire.')
    utc(state['confirmed_at']);result['transfers_made']=0
    _shape(result)
    return result

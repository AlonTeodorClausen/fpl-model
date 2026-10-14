"""Explicit manual availability scenarios, not calibrated injury diagnoses."""
from copy import deepcopy
import math
from fpl_model.label_contracts import utc


def validate_assumptions(records, player_ids, events, origin):
    out=[]; seen=set()
    for r in records or []:
        pid,event=r.get('player_id'),r.get('event');factor=r.get('factor')
        if type(pid) is not int or pid not in player_ids or type(event) is not int or event not in events:
            raise ValueError('Skadesantagelsen har ukendt spiller/GW.')
        if (pid,event) in seen:raise ValueError('Flere skadesantagelser for samme spiller/GW.')
        if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not math.isfinite(factor) or not 0<=factor<=1:
            raise ValueError('Tilgængelighedsfaktor skal være mellem 0 og 1.')
        if not isinstance(r.get('reason'),str) or not r['reason'].strip():
            raise ValueError('En manuel skadesantagelse kræver en begrundelse.')
        if utc(r['observed_at'])>utc(origin):raise ValueError('Skadesantagelsen er registreret efter prognosetidspunktet.')
        seen.add((pid,event));out.append(deepcopy(r))
    return sorted(out,key=lambda r:(r['event'],r['player_id']))


def resolve_horizon_availability(players, events, records, origin, policy='hold_current'):
    """An explicit planning scenario, never an inferred medical return date.

    Only the official `d` + 75% category is eligible. Severe/unknown injuries,
    suspensions and unavailable players are not automatically cleared. The first
    GW is unchanged and manual player/GW assumptions always take precedence.
    """
    if policy not in ('hold_current','short_doubt_next_gw'):
        raise ValueError('Ukendt politik for fremtidig tilgængelighed.')
    manual=validate_assumptions(records,{p['id'] for p in players},events,origin)
    occupied={(r['player_id'],r['event']) for r in manual}
    derived=[]
    if policy=='short_doubt_next_gw':
        for p in players:
            if p.get('status')!='d' or p.get('chance_of_playing_next_round')!=75:
                continue
            for event in sorted(events)[1:]:
                if (p['id'],event) in occupied:continue
                derived.append(dict(player_id=p['id'],event=event,factor=1.,official_factor=.75,
                    observed_at=utc(origin).isoformat(),kind='planning_assumption',source_url=None,
                    reason='Planlægningsscenarie: 75%-tvivl ophører efter første GW; ingen verificeret raskmelding.'))
    return sorted(manual+derived,key=lambda r:(r['event'],r['player_id'])), sorted(derived,key=lambda r:(r['event'],r['player_id']))

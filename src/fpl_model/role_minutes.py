"""Untuned role-conditioned transitions learned strictly from earlier match rows.

Callers supply only history before forecast. Missing fixtures are never DNP;
unsafe histories retain baseline. A training role uses the prefix BEFORE its
outcome. Peer priors exclude the predicted player's own evidence.
"""
import numpy as np
from fpl_model.history_coverage import history_window
from fpl_model.label_contracts import utc


def classify_role(rows):
    if not rows:return 'unresolved'
    start=sum(r['starts'] for r in rows)/len(rows)
    played=sum(r['minutes']>0 for r in rows)/len(rows)
    if start>=.75:return 'starter'
    if played<=.25:return 'reserve'
    if start<=.25 and played>=.5:return 'substitute'
    return 'rotation'


def _safe(rows,past,team):
    return (len(rows)>=2 and history_window(rows,past,team)['usable'] and
        all(r.get('label_state')=='final' and r.get('starts') in (0,1) and
            isinstance(r.get('minutes'),(int,float)) and np.isfinite(r['minutes']) and
            0<=r['minutes']<=90 and not(r['starts'] and r['minutes']==0) for r in rows))


def build_role_priors(players,histories,past,config,options):
    """Player-specific leave-one-out priors; deterministic under input reordering."""
    evidence={}
    for p in sorted(players,key=lambda p:p['id']):
        own=sorted((r for r in histories if r['player_id']==p['id']),key=lambda r:(utc(r['kickoff_time']),r['fixture_id']))
        if not _safe(own,past,p['team']):continue
        transitions={}
        for i in range(1,len(own)):
            role=classify_role(own[:i]);counts=transitions.setdefault(role,np.zeros(3))
            r=own[i];counts[0 if r['starts'] else 1 if r['minutes']>0 else 2]+=1
        evidence[p['id']]=dict(position=p['element_type'],role=classify_role(own),transitions=transitions,rows=own)
    result={};k=options.transition_prior_games
    default=np.array([config.prior_start,config.prior_sub,1-config.prior_start-config.prior_sub])
    for pid,own in evidence.items():
        peers=[e for other,e in evidence.items() if other!=pid and e['position']==own['position']]
        pc=sum((v for e in peers for v in e['transitions'].values()),np.zeros(3))
        rc=sum((e['transitions'].get(own['role'],np.zeros(3)) for e in peers),np.zeros(3))
        oc=own['transitions'].get(own['role'],np.zeros(3))
        position=(pc+default)/(pc.sum()+1)
        role=(rc+k*position)/(rc.sum()+k)
        prediction=(oc+k*role)/(oc.sum()+k)
        entry=dict(role=own['role'],position=own['position'],peer_position_counts=pc.tolist(),
            peer_role_counts=rc.tolist(),own_role_counts=oc.tolist(),probabilities=prediction.tolist(),
            position_probabilities=position.tolist(),role_probabilities=role.tolist(),
            transition_prior_games=k,fixture_ids=[r['fixture_id'] for r in own['rows']],
            peer_players=len(peers),sparse_role_prior=bool(rc.sum()==0),conditional_minutes={})
        for field,is_start,baseline,maximum in [('start_minutes',True,config.starter_minutes,90),('sub_minutes',False,config.sub_minutes,59)]:
            peer=[r['minutes'] for e in peers for r in e['rows'] if r['minutes']>0 and bool(r['starts'])==is_start]
            self_minutes=[r['minutes'] for r in own['rows'] if r['minutes']>0 and bool(r['starts'])==is_start]
            strength=config.minutes_prior_games
            centre=(sum(peer)+strength*baseline)/(len(peer)+strength)
            value=float(np.clip((sum(self_minutes)+strength*centre)/(len(self_minutes)+strength),1,maximum))
            entry['conditional_minutes'][field]=dict(value=value,peer_prior=centre,peer_rows=len(peer),own_rows=len(self_minutes),prior_games=strength)
        result[pid]=entry
    return result


def apply_role_transition(par,prior):
    e=par['explanation']
    if prior is None or par['history_coverage']!='complete_observed_window':
        e['role']=dict(method='role_transitions_v2',status='fallback',reason='requires_two_complete_final_rows_with_known_starts')
        return
    start,sub,_=prior['probabilities'];factor=e['injury_factor']
    par.update(p_start=start*factor,p_sub=sub*factor)
    for key,value in prior['conditional_minutes'].items():par[key]=value['value']
    e.update(pre_injury_start=start,pre_injury_sub=sub)
    e['role']=dict(prior,method='role_transitions_v2',status='estimated',
        p_start_given_available=start,p_sub_given_available=sub)

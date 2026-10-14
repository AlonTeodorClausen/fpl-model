"""Opt-in, untuned role/return-minutes and shared-goal experiment.

Baseline v1 is untouched. Historical callers must supply earlier, complete rows.
This is not a calibrated injury diagnosis or a coherent real-world team XI.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np
from fpl_model.label_contracts import utc


@dataclass(frozen=True)
class EvolutionConfig:
    recent_matches: int = 3
    half_life_matches: float = 2.
    role_prior_games: float = 1.
    shared_goals: bool = True
    minutes_method: str = "recent_role_v1"
    transition_prior_games: float = 3.

    def __post_init__(self):
        if type(self.recent_matches) is not int or self.recent_matches<1:
            raise ValueError('Positive recent match window required')
        if any(not math.isfinite(v) or v<=0 for v in (self.half_life_matches,self.role_prior_games,self.transition_prior_games)):
            raise ValueError('Positive finite role assumptions required')
        if self.minutes_method not in ('recent_role_v1','role_transitions_v2'):raise ValueError('Unknown minutes method')
        if type(self.shared_goals) is not bool:raise ValueError('shared_goals must be boolean')

    @property
    def version(self):
        if self.minutes_method=='role_transitions_v2':
            return 'component_shared_goals_role_transitions_v2' if self.shared_goals else 'component_role_transitions_v2'
        return 'component_shared_goals_v1' if self.shared_goals else 'component_role_minutes_v1'


def position_priors(players, histories, past, config):
    """Only complete, same-team histories inform positional prior centres."""
    from fpl_model.history_coverage import history_window
    result={}
    for pos in (1,2,3,4):
        rows=[]
        for p in players:
            if p['element_type']!=pos:continue
            own=[h for h in histories if h['player_id']==p['id']]
            if history_window(own,past,p['team'])['usable']:
                rows += [h for h in own if h.get('starts') in (0,1)]
        n=len(rows); starts=sum(r['starts'] for r in rows);subs=sum(r['minutes']>0 and not r['starts'] for r in rows)
        result[pos]=dict(start=(starts+config.prior_start)/(n+1),sub=(subs+config.prior_sub)/(n+1),
                         rows=n,position=pos)
    return result


def apply_role(par, history, prior, options, config):
    e=par['explanation'];old=sorted(history,key=lambda r:(utc(r['kickoff_time']),r['fixture_id']))
    if not old or par['history_coverage']!='complete_observed_window' or any(r.get('starts') not in (0,1) for r in old):
        # Existing explicit fallback remains; no shrinking an incomplete denominator.
        e['role']=dict(method='recent_role_v1',status='fallback',reason=par['history_coverage'] if old else 'no_usable_history')
        return
    recent=old[-options.recent_matches:];older=old[:-options.recent_matches]
    k=options.role_prior_games
    older_start=sum(r['starts'] for r in older);older_sub=sum(r['minutes']>0 and not r['starts'] for r in older)
    centre_start=(older_start+k*prior['start'])/(len(older)+k)
    centre_sub=(older_sub+k*prior['sub'])/(len(older)+k)
    w=2.**(-np.arange(len(recent)-1,-1,-1)/options.half_life_matches)
    start=(sum(v*r['starts'] for v,r in zip(w,recent))+k*centre_start)/(w.sum()+k)
    sub=(sum(v*(r['minutes']>0 and not r['starts']) for v,r in zip(w,recent))+k*centre_sub)/(w.sum()+k)
    factor=e['injury_factor'];par['p_start']=float(start*factor);par['p_sub']=float(sub*factor)
    for field,is_start,default,maximum in [('start_minutes',True,config.starter_minutes,90),('sub_minutes',False,config.sub_minutes,59)]:
        older_m=[r['minutes'] for r in older if r['minutes']>0 and bool(r['starts'])==is_start]
        centre=(sum(older_m)+config.minutes_prior_games*default)/(len(older_m)+config.minutes_prior_games)
        known=[(v,r['minutes']) for v,r in zip(w,recent) if r['minutes']>0 and bool(r['starts'])==is_start]
        par[field]=float(np.clip((sum(v*m for v,m in known)+config.minutes_prior_games*centre)/
                                 (sum(v for v,_ in known)+config.minutes_prior_games),1,maximum))
    e.update(pre_injury_start=float(start),pre_injury_sub=float(sub))
    e['role']=dict(method='recent_role_v1',status='estimated',options=asdict(options),
        position_prior=prior,older_rows=len(older),recent_fixture_ids=[r['fixture_id'] for r in recent],
        recent_weights=w.tolist(),prior_start=centre_start,prior_sub=centre_sub,
        effective_recent_rows=float(w.sum()),p_start_given_available=float(start),p_sub_given_available=float(sub))


def apply_return_assumption(par, record, origin):
    if not record:return
    if utc(record['observed_at'])>utc(origin):raise ValueError('Role assumption observed after forecast origin')
    if not record.get('reason','').strip():raise ValueError('Role assumption needs a reason')
    e=par['explanation'];factor=e['injury_factor']
    value=record.get('start_given_available')
    if value is not None:
        if isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=1:raise ValueError('Invalid conditional start probability')
        # Preserve chance of a cameo conditional on not starting, not its absolute mass.
        sub_given_bench=e['pre_injury_sub']/max(1-e['pre_injury_start'],1e-12)
        e['pre_injury_start']=value;e['pre_injury_sub']=(1-value)*min(1,sub_given_bench)
        par['p_start']=value*factor;par['p_sub']=e['pre_injury_sub']*factor
    for key,maximum in [('start_minutes_cap',90),('sub_minutes_cap',59)]:
        value=record.get(key)
        if value is not None:
            if type(value) is not int or not 1<=value<=maximum:raise ValueError('Invalid return minutes cap')
            par[key]=value
    e['return_assumption']=dict(record)


def allocate_shared_goals(players, params, states, goal_times, rng):
    """A goal has one on-pitch scorer and at most one distinct on-pitch assister.

    No active eligible scorer -> explicitly unattributed, not a fabricated player.
    Independent player minutes remain a limitation; this does not claim a legal XI.
    """
    ids=[p['id'] for p in players];draws=len(next(iter(states.values()))['minutes'])
    result={pid:dict(goals=np.zeros(draws,int),assists=np.zeros(draws,int)) for pid in ids};audit=[]
    for team in sorted({p['team'] for p in players}):
        team_ids=[p['id'] for p in players if p['team']==team];times=goal_times[team]
        scored=np.zeros(draws,int);assisted=np.zeros(draws,int);unknown=np.zeros(draws,int)
        g=np.array([params[i]['goals'] for i in team_ids]);a=np.array([params[i]['assists'] for i in team_ids])
        starts=np.column_stack([states[i]['entered'] for i in team_ids]);ends=np.column_stack([states[i]['exit_at'] for i in team_ids])
        for j in range(times.shape[1]):
            t=times[:,j];valid=t<90
            active=(t[:,None]>=starts)&(t[:,None]<ends)
            gw=active*g;aw=active*a;total=gw.sum(axis=1)
            choice=_choose(gw,rng);ok=valid&(total>0)
            unknown+=valid&~ok;scored+=ok
            for k,pid in enumerate(team_ids):result[pid]['goals']+=ok&(choice==k)
            fraction=np.minimum(1,aw.sum(axis=1)/np.maximum(total,1e-12))
            aw[np.arange(draws),choice]=0
            helper=_choose(aw,rng);has_assist=ok&(rng.random(draws)<fraction)&(aw.sum(axis=1)>0)
            assisted+=has_assist
            for k,pid in enumerate(team_ids):result[pid]['assists']+=has_assist&(helper==k)
        audit.append(dict(team_id=team,goals=(times<90).sum(axis=1),credited_goals=scored,
            credited_assists=assisted,unattributed_goals=unknown,absent_scorer_count=0,self_assist_count=0))
    return result,audit


def _choose(weights,rng):
    total=weights.sum(axis=1);u=rng.random(len(total))*total
    return np.minimum((u[:,None]>=np.cumsum(weights,axis=1)).sum(axis=1),weights.shape[1]-1)

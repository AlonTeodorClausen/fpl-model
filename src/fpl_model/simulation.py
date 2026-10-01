"""Seeded fixture scenarios with shared concession times and explicit approximations.

Attack counts are independent Poisson, not allocations of shared team goals.
Bonus approximates 0–3 with a binomial and is not a match BPS ranking. Minutes
are independent across players; no coherent XI or GK exclusion is imposed.
"""
from dataclasses import dataclass
import numpy as np

from fpl_model.label_contracts import utc
from fpl_model.models.baseline import player_parameters, fixture_goal_means
from fpl_model.scoring import score_components
from fpl_model.diagnostics import history_summary
from fpl_model.history_coverage import history_window


@dataclass
class Simulation:
    players: list
    points: np.ndarray
    minutes: np.ndarray
    parameters: dict
    event: int
    seed: int | None
    explanations: dict

    def summary(self):
        rows = []
        for i,p in enumerate(self.players):
            q = np.quantile(self.points[:,i], [.1,.5,.9])
            rates = self.parameters[p['id']]
            rows.append(dict(player_id=p['id'], name=p.get('web_name',str(p['id'])),
                position=p['element_type'], team_id=p['team'], price=p.get('now_cost'),
                can_select=p.get('can_select',True), xp=float(self.points[:,i].mean()),
                expected_minutes=float(self.minutes[:,i].mean()), p10=float(q[0]), p50=float(q[1]), p90=float(q[2]),
                p_no_play=float((self.minutes[:,i]==0).mean()), basis=rates['basis'],
                history_rows=rates['history_rows'], fallbacks=', '.join(rates['fallbacks'])))
        return rows


def simulate(data, event, config, *, draws=3000, seed=None, retrospective=False, defensive_odds=None):
    if not 100 <= draws <= 100000: raise ValueError('Use 100–100000 scenarios')
    events = {e['id']:e for e in data['events']}
    if event not in events: raise ValueError('Unknown official GW')
    deadline = utc(events[event]['deadline_time'])
    cutoff = deadline if retrospective else utc(data['as_of_at'])
    if not retrospective and cutoff > deadline: raise ValueError('Snapshot is after this GW deadline; use retrospective evaluation instead')
    overrides={}
    if defensive_odds is not None:
        if retrospective: raise ValueError('Odds overlay is prohibited in historical evaluation')
        from fpl_model.defensive_odds import eligible_overrides
        overrides=eligible_overrides(defensive_odds,event,cutoff,deadline,data['fixtures'])
    rng = np.random.default_rng(seed)
    players = sorted(data['players'], key=lambda p:p['id'])
    points = np.zeros((draws,len(players)),dtype=np.int32)
    minutes = np.zeros_like(points)
    past = [f for f in data['fixtures'] if f.get('finished') and f.get('kickoff_time')
            and utc(f['kickoff_time']) < cutoff and (not retrospective or (f.get('event') or 999) < event)]
    histories = [r for r in data['histories'] if utc(r['kickoff_time']) < cutoff
                 and (not retrospective or r['event'] < event)
                 and (retrospective or (r.get('available_at') is not None
                                       and utc(r['available_at']) <= cutoff))]
    params = {}; explanations = {}
    for p in players:
        own=[r for r in histories if r['player_id']==p['id']]
        coverage=history_window(own,past,p['team'])
        par=player_parameters(p,own if coverage['usable'] else [],coverage['expected_rows'],config,
                              allow_aggregates=not retrospective)
        par['expected_missing_fixture_ids']=coverage['expected_missing_fixture_ids']
        par['history_coverage']=coverage['state']
        if not coverage['usable']:
            par['fallbacks']=sorted(set(par['fallbacks']+[coverage['state']]))
        params[p['id']]=par
        explanations[p['id']]=dict(**par['explanation'],
            captured_history=history_summary(own),history_coverage=coverage['state'],
            basis=par['basis'],fallbacks=par['fallbacks'],
            p_start=par['p_start'],p_sub=par['p_sub'],p_dnp=1-par['p_start']-par['p_sub'],
            start_minutes=par['start_minutes'],sub_minutes=par['sub_minutes'],
            fixtures=[],point_components={key:0. for key in score_components(p['element_type'],minutes=0)})
    for f in sorted((f for f in data['fixtures'] if f.get('event')==event), key=lambda f:f['id']):
        lambdas, context = fixture_goal_means(f,past,config,with_context=True)
        # Same opponent goal times for every teammate. This models clean-sheet correlation.
        goal_times = {}
        for team, lam in zip((f['team_h'],f['team_a']),lambdas):
            counts = rng.poisson(lam,draws)
            times = rng.uniform(0,90,size=(draws,int(counts.max(initial=0))))
            goal_times[team] = np.where(np.arange(times.shape[1])[None,:] < counts[:,None],times,999)
        if f['id'] in overrides:
            # Always consume the original baseline RNG above: minute/attack draws
            # stay bit-identical. Only defensive goal times use a separate stream.
            defence_rng=np.random.default_rng(np.random.SeedSequence([seed,f['id'],271828]) if seed is not None else None)
            for team,lam in zip((f['team_h'],f['team_a']),overrides[f['id']]):
                counts=defence_rng.poisson(lam,draws)
                times=defence_rng.uniform(0,90,size=(draws,int(counts.max(initial=0))))
                goal_times[team]=np.where(np.arange(times.shape[1])[None,:]<counts[:,None],times,999)
        for i,p in enumerate(players):
            if p['team'] not in (f['team_h'],f['team_a']): continue
            par = params[p['id']]; pos = p['element_type']
            u = rng.random(draws); start = u < par['p_start']; sub = (u >= par['p_start']) & (u < par['p_start']+par['p_sub'])
            mins = np.where(start,np.clip(np.rint(rng.normal(par['start_minutes'],8,draws)),1,90),
                            np.where(sub,np.clip(np.rint(rng.normal(par['sub_minutes'],9,draws)),1,59),0)).astype(int)
            played = mins>0; exposure=mins/90
            red = (rng.random(draws) < np.minimum(par['red_cards']*exposure,1)).astype(int)
            yellow = ((rng.random(draws) < np.minimum(par['yellow_cards']*exposure,1)) & (red==0)).astype(int)
            own_team_idx = 0 if p['team']==f['team_h'] else 1
            opponent = f['team_a'] if own_team_idx==0 else f['team_h']
            times = goal_times[opponent]
            entered = np.where(start,0,90-mins)
            departed = np.where(red>0,90,np.where(start,mins,90))
            conceded = (((times >= entered[:,None]) & (times < departed[:,None])).sum(axis=1)*played)
            attack_factor = lambdas[own_team_idx]/((config.home_goals+config.away_goals)/2)*config.attack_scale
            sampled = {key:rng.poisson(par[key]*exposure*(attack_factor if key in ('goals','assists') else 1))
                       for key in ('goals','assists','saves','defensive_contribution','penalties_saved','penalties_missed','own_goals')}
            sampled['bonus'] = rng.binomial(3,np.clip(par['bonus']*exposure/3,0,1))
            components = score_components(pos, minutes=mins, goals_conceded=conceded,
                               red_cards=red,yellow_cards=yellow,**sampled)
            pts = sum(components.values())
            e=explanations[p['id']]
            for key,value in components.items(): e['point_components'][key]+=float(np.asarray(value).mean())
            e['fixtures'].append(dict(**context[own_team_idx],fixture_id=f['id'],opponent_team_id=opponent,
                home=own_team_idx==0,own_goal_mean=lambdas[own_team_idx],
                opponent_goal_mean=lambdas[1-own_team_idx],
                league_goal_base=(config.home_goals+config.away_goals)/2,
                attack_scale=config.attack_scale,attack_factor=attack_factor))
            points[:,i] += pts.astype(np.int32); minutes[:,i] += mins
    for i,p in enumerate(players):
        explanations[p['id']]['expected_points']=float(points[:,i].mean())
        explanations[p['id']]['expected_minutes']=float(minutes[:,i].mean())
        explanations[p['id']]['p_no_play_gw']=float((minutes[:,i]==0).mean())
    return Simulation(players,points,minutes,params,event,seed,explanations)

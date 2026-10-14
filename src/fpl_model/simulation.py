"""Seeded fixture scenarios with shared concession times and explicit approximations.

Attack counts are independent Poisson, not allocations of shared team goals.
Bonus approximates 0–3 with a binomial and is not a match BPS ranking. Minutes
are independent across players; no coherent XI or GK exclusion is imposed.
"""
from dataclasses import dataclass, field
import numpy as np
from copy import deepcopy

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
    match_audit: list = field(default_factory=list)
    bonus_model: dict | None = None
    assist_model: dict | None = None

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


def simulate(data, event, config, *, draws=3000, seed=None, retrospective=False, defensive_odds=None, availability_overrides=None, odds_scope='defence', evolution=None, role_overrides=None, set_piece_config=None, set_piece_source=None, bonus_config=None, season_prior_config=None, assist_config=None):
    if not 100 <= draws <= 100000: raise ValueError('Use 100–100000 scenarios')
    from fpl_model.attacking_odds import team_attack_rates, variant_version
    variant_version(odds_scope)
    if odds_scope=='attack_and_defence' and defensive_odds is None:
        raise ValueError('Attacking odds require explicit coverage, including fallback records')
    if odds_scope=='attack_and_defence' and config.attack_scale!=1.:
        raise ValueError('Attacking odds require attack_scale=1; the market goal budget replaces this factor')
    events = {e['id']:e for e in data['events']}
    if event not in events: raise ValueError('Unknown official GW')
    deadline = utc(events[event]['deadline_time'])
    cutoff = deadline if retrospective else utc(data['as_of_at'])
    if not retrospective and cutoff > deadline: raise ValueError('Snapshot is after this GW deadline; use retrospective evaluation instead')
    if season_prior_config is not None:
        from fpl_model.season_priors import player_prior, apply_prior
        if any(x is not None for x in (evolution,set_piece_config,bonus_config)):
            raise ValueError("Previous-season priors are an isolated experiment")
    assist_model=None
    if assist_config is not None:
        from fpl_model.assist_correction import fit_correction, apply_correction
        if any(x is not None for x in (evolution,set_piece_config,bonus_config,season_prior_config)):
            raise ValueError("Assist correction is an isolated experiment")
        assist_model=fit_correction(data,event,cutoff,assist_config,retrospective=retrospective)
    bonus_model=None
    if bonus_config is not None:
        from fpl_model.conditional_bonus import fit_bonus, sample_bonus
        if evolution is not None or set_piece_config is not None:
            raise ValueError('Conditional bonus is an isolated experiment; do not combine with other experiments')
        bonus_model=fit_bonus(data,event,cutoff,bonus_config,retrospective=retrospective)
    if set_piece_config is not None:
        from fpl_model.set_piece_roles import validate_source, allocate_roles
        if retrospective or evolution is not None or odds_scope!='attack_and_defence':
            raise ValueError('Set-piece sensitivity requires isolated live attacking-odds model')
        validate_source(set_piece_source,data['players'],min(cutoff,deadline))
    overrides={}
    if defensive_odds is not None:
        if retrospective: raise ValueError('Odds overlay is prohibited in historical evaluation')
        from fpl_model.defensive_odds import eligible_overrides
        overrides=eligible_overrides(defensive_odds,event,cutoff,deadline,data['fixtures'])
    role_overrides = role_overrides or {}
    if role_overrides and (evolution is None or retrospective):
        raise ValueError("Return assumptions require the experimental live model")
    if set(role_overrides)-{p["id"] for p in data["players"]}:raise ValueError("Unknown role player")
    availability_overrides = availability_overrides or {}
    if retrospective and availability_overrides:
        raise ValueError('Manual availability cannot enter historical evaluation')
    if any(type(pid) is not int or pid not in {p['id'] for p in data['players']}
           or isinstance(v,bool) or not isinstance(v,(float,int)) or not np.isfinite(v) or not 0<=v<=1
           for pid,v in availability_overrides.items()):
        raise ValueError('Invalid availability override')
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
    params = {}; explanations = {}; original_params = {}; match_audit=[]
    if evolution:
        from fpl_model.model_evolution import position_priors, apply_role, apply_return_assumption, allocate_shared_goals
        from fpl_model.role_minutes import build_role_priors, apply_role_transition
        priors=(build_role_priors(data.get('role_prior_players',players),histories,past,config,evolution)
                if evolution.minutes_method=='role_transitions_v2' else
                position_priors(data.get('role_prior_players',players),histories,past,config))
    for p in players:
        own=[r for r in histories if r['player_id']==p['id']]
        coverage=history_window(own,past,p['team'])
        par=player_parameters(p,own if coverage['usable'] else [],coverage['expected_rows'],config,
                              allow_aggregates=not retrospective)
        par['expected_missing_fixture_ids']=coverage['expected_missing_fixture_ids']
        par['history_coverage']=coverage['state']
        if not coverage['usable']:
            par['fallbacks']=sorted(set(par['fallbacks']+[coverage['state']]))
        if evolution:
            if evolution.minutes_method=='role_transitions_v2':apply_role_transition(par,priors.get(p['id']))
            else:apply_role(par,own,priors[p['element_type']],evolution,config)
        original_params[p['id']]=deepcopy(par)
        if season_prior_config is not None:
            apply_prior(par,player_prior(data,p,cutoff,season_prior_config,retrospective=retrospective))
        if assist_model is not None:
            apply_correction(par,assist_model)
        if p['id'] in availability_overrides:
            factor=availability_overrides[p['id']]
            par['p_start']=par['explanation']['pre_injury_start']*factor
            par['p_sub']=par['explanation']['pre_injury_sub']*factor
            par['explanation']['official_injury_factor']=par['explanation']['injury_factor']
            par['explanation']['injury_factor']=factor
            par['explanation']['availability_source']='manual_scenario'
            par['fallbacks']=sorted(set(par['fallbacks']+['manual_availability_scenario']))
        if evolution:
            apply_return_assumption(par,role_overrides.get(p['id']),cutoff)
            par['explanation']['availability']=dict(probability=par['explanation']['injury_factor'],
                source='historical_status_unknown' if retrospective else 'manual_scenario' if p['id'] in availability_overrides else 'official_fpl',
                news=None if retrospective else p.get('news'),news_added=None if retrospective else p.get('news_added'),
                snapshot_id=data.get('snapshot_id'),available_at=None if retrospective or p['id'] in availability_overrides else data.get('player_metadata_available_at',data.get('input_sources',{}).get('history',{}).get('available_at',data['as_of_at'])),
                role_assumption=role_overrides.get(p['id']))
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
        attack_rates={};fixture_states={};fixture_components={};fixture_indices={}
        if odds_scope=='attack_and_defence' and f['id'] in overrides:
            for team,lam in zip((f['team_h'],f['team_a']),overrides[f['id']]):
                allocated=team_attack_rates({p['id']:params[p['id']] for p in players if p['team']==team},lam)
                if allocated:
                    if set_piece_config is not None:
                        allocated=allocate_roles(allocated,[r for r in set_piece_source['players'] if r['team_id']==team],set_piece_config)
                        for r in allocated.values():r['set_pieces']['source']=set_piece_source['source']
                    attack_rates.update(allocated)
        for i,p in enumerate(players):
            if p['team'] not in (f['team_h'],f['team_a']): continue
            par = params[p['id']]; pos = p['element_type']
            own_team_idx = 0 if p['team']==f['team_h'] else 1
            opponent = f['team_a'] if own_team_idx==0 else f['team_h']
            times = goal_times[opponent]
            attack_factor = lambdas[own_team_idx]/((config.home_goals+config.away_goals)/2)*config.attack_scale
            original=original_params[p['id']]
            state={}
            draw_par=dict(par,goals=original['goals'],assists=original['assists']) if (season_prior_config or assist_config) else par
            if p['id'] in availability_overrides or p['id'] in role_overrides:
                # Replay this player's random draws with the replacement factor,
                # then restore the baseline stream for every other player.
                before=deepcopy(rng.bit_generator.state)
                _draw_player(original,pos,times,attack_factor,rng,draws)
                after=deepcopy(rng.bit_generator.state)
                rng.bit_generator.state=before
                mins,components=_draw_player(draw_par,pos,times,attack_factor,rng,draws,state_out=state)
                rng.bit_generator.state=after
            else:
                mins,components=_draw_player(draw_par,pos,times,attack_factor,rng,draws,state_out=state)
            if season_prior_config is not None and p['id'] not in attack_rates:
                # Preserve baseline RNG/nonattack draws; replace only changed rates.
                for tag,key,weight in [(63511,'goals',{1:10,2:6,3:5,4:4}[pos]),(63512,'assists',3)]:
                    if par[key]!=original[key]:
                        prior_rng=np.random.default_rng(np.random.SeedSequence([seed,f['id'],p['id'],tag]) if seed is not None else None)
                        components[key]=weight*prior_rng.poisson(par[key]*mins/90*attack_factor)
            if assist_model is not None and p['id'] not in attack_rates and par['assists']!=original['assists']:
                assist_rng=np.random.default_rng(np.random.SeedSequence([seed,f['id'],p['id'],73519]) if seed is not None else None)
                components['assists']=3*assist_rng.poisson(par['assists']*mins/90*attack_factor)
            if p['id'] in attack_rates and not (evolution and evolution.shared_goals):
                attack_rng=np.random.default_rng(np.random.SeedSequence([seed,f['id'],p['id'],314159]) if seed is not None else None)
                allocation=attack_rates[p['id']]
                components['goals']=attack_rng.poisson(allocation['goals_per90']*mins/90)*{1:10,2:6,3:5,4:4}[pos]
                components['assists']=3*attack_rng.poisson(allocation['assists_per90']*mins/90)
            if bonus_model and bonus_model['status']=='fitted':
                components['bonus']=sample_bonus(bonus_model,pos,mins,components,seed=seed,fixture_id=f['id'],player_id=p['id'])
            fixture_states[p['id']]=state;fixture_components[p['id']]=components;fixture_indices[p['id']]=i
            pts = sum(components.values())
            e=explanations[p['id']]
            for key,value in components.items(): e['point_components'][key]+=float(np.asarray(value).mean())
            e['fixtures'].append(dict(**context[own_team_idx],fixture_id=f['id'],opponent_team_id=opponent,
                home=own_team_idx==0,own_goal_mean=lambdas[own_team_idx],
                opponent_goal_mean=lambdas[1-own_team_idx],
                league_goal_base=(config.home_goals+config.away_goals)/2,
                attack_scale=config.attack_scale,attack_factor=attack_factor))
            if odds_scope=='attack_and_defence':
                e['fixtures'][-1]['attack_odds']=attack_rates.get(p['id'],dict(status='baseline_fallback',
                    reason='no_eligible_odds' if f['id'] not in overrides else 'no_positive_team_attack_exposure'))
                if p['id'] in attack_rates:
                    e['fixtures'][-1]['baseline_attack_factor_not_applied']=e['fixtures'][-1].pop('attack_factor')
                    e['fixtures'][-1]['attack_factor']=None
                    e['fixtures'][-1]['own_goal_mean']=overrides[f['id']][own_team_idx]
            points[:,i] += pts.astype(np.int32); minutes[:,i] += mins
        if evolution and evolution.shared_goals:
            joint_rng=np.random.default_rng(np.random.SeedSequence([seed,f['id'],161803]) if seed is not None else None)
            fixture_players=[p for p in players if p['id'] in fixture_states]
            allocated,audit=allocate_shared_goals(fixture_players,params,fixture_states,goal_times,joint_rng)
            match_audit.append(dict(fixture_id=f['id'],teams=audit))
            for p in fixture_players:
                pid=p['id'];components=fixture_components[pid];i=fixture_indices[pid]
                replacements=dict(goals=allocated[pid]['goals']*{1:10,2:6,3:5,4:4}[p['element_type']],
                    assists=allocated[pid]['assists']*3,own_goals=np.zeros(draws,int))
                for key,value in replacements.items():
                    delta=value-np.asarray(components[key]);points[:,i]+=delta.astype(np.int32)
                    explanations[pid]['point_components'][key]+=float(delta.mean())
                detail=explanations[pid]['fixtures'][-1]
                detail.pop('attack_odds',None)
                detail['attack_factor']=None
                detail['own_goal_mean']=(overrides[f['id']] if f['id'] in overrides else lambdas)[0 if p['team']==f['team_h'] else 1]
                detail['shared_goals']=dict(method='on_pitch_allocation_v1',
                    goal_source='odds' if f['id'] in overrides else 'baseline_team_goals',
                    own_goals_policy='omitted_in_joint_experiment')
    for i,p in enumerate(players):
        if bonus_model:
            explanations[p['id']]['conditional_bonus']={k:bonus_model[k] for k in
                ('version','status','reason','training_rows','sub60_rows','training_sha256','training_gameweeks','availability_contract')}
        explanations[p['id']]['expected_points']=float(points[:,i].mean())
        explanations[p['id']]['expected_minutes']=float(minutes[:,i].mean())
        explanations[p['id']]['p_no_play_gw']=float((minutes[:,i]==0).mean())
    return Simulation(players,points,minutes,params,event,seed,explanations,match_audit,bonus_model,assist_model)


def _draw_player(par, pos, times, attack_factor, rng, draws, state_out=None):
    u = rng.random(draws); start = u < par['p_start']; sub = (u >= par['p_start']) & (u < par['p_start']+par['p_sub'])
    mins = np.where(start,np.clip(np.rint(rng.normal(par['start_minutes'],8,draws)),1,90),
                    np.where(sub,np.clip(np.rint(rng.normal(par['sub_minutes'],9,draws)),1,59),0)).astype(int)
    mins=np.where(start,np.minimum(mins,par.get("start_minutes_cap",90)),np.minimum(mins,par.get("sub_minutes_cap",59)))
    played = mins>0; exposure=mins/90
    red = (rng.random(draws) < np.minimum(par['red_cards']*exposure,1)).astype(int)
    yellow = ((rng.random(draws) < np.minimum(par['yellow_cards']*exposure,1)) & (red==0)).astype(int)
    entered = np.where(start,0,90-mins)
    departed = np.where(red>0,90,np.where(start,mins,90))
    if state_out is not None:
        state_out.update(minutes=mins,entered=np.where(played,entered,999),exit_at=np.where(played,np.where(start,mins,90),-1))
    conceded = (((times >= entered[:,None]) & (times < departed[:,None])).sum(axis=1)*played)
    sampled = {key:rng.poisson(par[key]*exposure*(attack_factor if key in ('goals','assists') else 1))
               for key in ('goals','assists','saves','defensive_contribution','penalties_saved','penalties_missed','own_goals')}
    sampled['bonus'] = rng.binomial(3,np.clip(par['bonus']*exposure/3,0,1))
    components = score_components(pos, minutes=mins, goals_conceded=conceded,
                       red_cards=red,yellow_cards=yellow,**sampled)
    return mins, components

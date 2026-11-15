"""Small, factual decision summaries from existing optimizer reports."""


def decision_evidence(report, chosen):
    """Allocate a fixed plan's paired team-point change; no new scenarios."""
    hold=next((p for p in report['packages'] if p.get('plan_id')=='hold' or
               p.get('count')==0 and not p.get('steps')),None)
    if hold is None:
        raise ValueError('Missing unchanged-team comparison')
    chosen_weeks={int(r['event']):r for r in chosen['per_gw']}
    hold_weeks={int(r['event']):r for r in hold['per_gw']}
    if chosen_weeks.keys()!=hold_weeks.keys():
        raise ValueError('Plans must cover the same gameweeks')
    if not all('player_mean_points' in r for r in (*chosen_weeks.values(),*hold_weeks.values())):
        return dict(available=False)
    keys=('xi','autosub','captain')
    by_player={}
    weeks=[]
    for event in sorted(chosen_weeks):
        selected=chosen_weeks[event];reference=hold_weeks[event]
        left={int(i):v for i,v in selected['player_mean_points'].items()}
        right={int(i):v for i,v in reference['player_mean_points'].items()}
        changes={key+'_delta':sum(v[key] for v in left.values())-sum(v[key] for v in right.values())
                 for key in keys}
        hits_delta=selected['hits']-reference['hits']
        changes['bench_delta']=changes['autosub_delta']
        changes.update(event=event,hits_delta=hits_delta,
                       gain=sum(changes[key+'_delta'] for key in keys)-hits_delta)
        if abs(changes['gain']-selected['gain'])>1e-6:
            raise ValueError('Team contribution allocation does not reconcile with paired gain')
        weeks.append(changes)
        for i in left.keys()|right.keys():
            by_player[i]=by_player.get(i,0.)+left.get(i,{}).get('total',0.)-right.get(i,{}).get('total',0.)
    horizon={key+'_delta':sum(week[key+'_delta'] for week in weeks) for key in keys}
    horizon['bench_delta']=horizon['autosub_delta']
    horizon['hits_delta']=sum(week['hits_delta'] for week in weeks)
    horizon['gain']=sum(horizon[key+'_delta'] for key in keys)-horizon['hits_delta']
    if abs(horizon['gain']-chosen['total_gain'])>1e-6:
        raise ValueError('Horizon contribution allocation does not reconcile with paired gain')
    names={r['player_id']:r['name'] for r in next(iter(report['players_by_event'].values()),[])}
    def squads(plan):
        if plan.get('steps'):
            return {i for step in plan['steps'] for i in step['squad']}
        return set(plan.get('squad',[]))
    selected_ids,hold_ids=squads(chosen),squads(hold)
    drivers=[dict(player_id=i,name=names.get(i,str(i)),change=value,
                  kind='ind' if i in selected_ids-hold_ids else
                       'ud' if i in hold_ids-selected_ids else 'opstilling/anfører')
             for i,value in by_player.items() if abs(value)>1e-8]
    drivers.sort(key=lambda row:(-row['change'],row['player_id']))
    return dict(available=True,next_gw=weeks[0],weeks=weeks,horizon=horizon,drivers=drivers)


def sequence_decision(report):
    plans = report['packages']
    chosen = next((p for p in plans if p['plan_id'] == report['recommendation']['plan_id']), None)
    hold = next((p for p in plans if p['plan_id'] == 'hold'), None)
    if chosen is None or hold is None or not chosen['steps'] or not chosen['per_gw']:
        raise ValueError('Incomplete strategy comparison')
    first = chosen['steps'][0]
    return dict(plan_id=chosen['plan_id'], label=chosen['label'], event=first['event'],
                count=first['count'], out=first['out'], **{'in': first['in']},
                bank_after=first['bank_after'], hits=chosen['hits'],
                next_gw_gain=chosen['next_gw_gain'], horizon_gain=chosen['total_gain'],
                hold_points=hold['total_points'], plan_points=chosen['total_points'],
                objective=chosen['objective'], hypothetical=chosen.get('hypothetical', False))


def immediate_decision(report):
    plans = report['packages']
    if not plans:
        raise ValueError('Empty transfer comparison')
    chosen = max(plans, key=lambda p: (p['objective'], -p['count']))
    hold = next((p for p in plans if p['count'] == 0), None)
    if hold is None:
        raise ValueError('Missing hold comparison')
    return dict(count=chosen['count'], out=chosen['out'], **{'in': chosen['in']},
                bank_after=chosen['bank_after'], hits=chosen['hits'],
                next_gw_gain=chosen['next_gw_gain'], horizon_gain=chosen['total_gain'],
                hold_points=hold['total_points'], plan_points=chosen['total_points'],
                objective=chosen['objective'])


def alternative_previews(plans, selected):
    """Compact, distinct report alternatives; never recompute their outcomes."""
    def preview_key(plan):
        step = plan['steps'][0] if plan.get('steps') else plan
        return (tuple(step.get('out', ())), tuple(step.get('in', ())), step.get('chip'),
                round(plan['next_gw_gain'], 2), round(plan['total_gain'], 2),
                plan.get('hits', 0))

    seen = {preview_key(selected)}
    rows = []
    for plan in sorted(plans, key=lambda row: -row['objective']):
        key = preview_key(plan)
        if plan is selected or key in seen:
            continue
        seen.add(key)
        label = plan['label'] if 'label' in plan else f'{plan["count"]} transfers'
        if plan.get('hypothetical'):
            label += ' · hypotetisk'
        rows.append(dict(label=label, next_gw_gain=plan['next_gw_gain'],
                         total_gain=plan['total_gain'], hits=plan['hits']))
        if len(rows) == 3:
            break
    return rows

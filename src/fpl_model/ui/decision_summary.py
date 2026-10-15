"""Small, factual decision summaries from existing optimizer reports."""


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
